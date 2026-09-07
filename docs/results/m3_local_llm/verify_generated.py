"""Replay fixed paper/search-export formulas and sampled IC without the DSL."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT/'src'))
from quant_research.factors.engine import strict_write_json as write
from quant_research.factors.registry import FactorRegistry


def verify(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'artifact_hashes.json').read_text())
    for name, expected in manifest.items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest() == expected, name
    source_hashes = json.loads((folder/'source_hashes.json').read_text())
    for name, expected in source_hashes.items():
        assert hashlib.sha256((folder/'source'/name).read_bytes()).hexdigest() == expected, name
    canonical = ROOT/'data/canonical/baostock_alpha158_csi300_2008_2020'
    results = json.loads((folder/'results.json').read_text())
    pit_equity = None
    if 'PIT_LOW_EQUITY_GROWTH' in results:
        batch = json.loads((folder/'batch.json').read_text())
        binding = batch['data_contract']; path = folder/'source'/binding['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding['sha256']
        meta = json.loads(path.read_text())['fields']['pit_equity_growth']['panel']
        assert hashlib.sha256((ROOT/meta['path']).read_bytes()).hexdigest() == meta['sha256']
        pit_equity = pd.read_parquet(ROOT/meta['path'])
    raw = {n: pd.read_parquet(folder/n/'raw.parquet') for n in results}
    scores = {n: pd.read_parquet(folder/n/'scores.parquet') for n in results}
    reference = next(iter(raw.values()))
    cell_count, ic_count = 0, 0
    close, eligibility = {}, {}
    for symbol in reference.columns:
        b = pd.read_parquet(canonical/f'{symbol}.parquet').set_index('datetime')
        active = ~b.is_suspended & b.close.gt(0)
        o, h, l, c = [(b[k]*b.factor).where(active) for k in ['open','high','low','close']]
        expected = {'PAPER101_INTRADAY_MOM': np.log(c/o),
                    'PAPER101_ALPHA101': (c-o)/(h-l+0.001)}
        vwap = (b.amount/b.volume.where(b.volume.gt(0))*b.factor).where(active)
        expected.update(SAGE_EXPORT_ROW0=-2.0-h,
                        FORGE_EXPORT_ROW0=1/(-0.01*vwap),
                        FORGE_EXPORT_ROW1=2.0-((vwap-(-10.0))-30.0))
        v = (b.volume / b.factor).where(active)
        t = (b.turnover / 100).where(active)
        ret = c / c.shift(1) - 1
        denominator = t-t.rolling(5,min_periods=5).rank(pct=True)
        expected.update(CANDIDATE001_VOL_REVERSAL=ret/denominator,
            CANDIDATE002_VWAP_VOLUME_DIVERGENCE=(c-vwap)/(v+1),
            CANDIDATE003_VOL_REVERSAL_ABS=ret.abs()/denominator,
            CANDIDATE004_VWAP_VOLUME_ABS=(c-vwap).abs()/(v+1),
            CANDIDATE005_VOL_RETURN_RATIO_ABS=ret.abs()/t.rolling(10,min_periods=10).mean(),
            CANDIDATE006_VWAP_RETURN_RATIO_ABS=(c-vwap).abs()/ret.abs())
        expected={k:x.replace([np.inf,-np.inf],np.nan) for k,x in expected.items()}
        if pit_equity is not None:expected['PIT_LOW_EQUITY_GROWTH']=pit_equity[symbol]
        for name in results:
            np.testing.assert_allclose(raw[name][symbol], expected[name].reindex(reference.index),
                                       rtol=1e-12, atol=1e-12, equal_nan=True)
            cell_count += len(reference)
        close[symbol] = c
        change = b.change.astype(np.float32)
        eligibility[symbol] = active & change.lt(.095) & change.gt(-.095)
    calendar = pd.DatetimeIndex(pd.read_parquet(canonical/'calendar.parquet').datetime)
    closes = pd.DataFrame(close).reindex(calendar)
    eligible = pd.DataFrame(eligibility).reindex(calendar).fillna(False)
    label = closes.shift(-6)/closes.shift(-1)-1
    label = label.where(eligible.shift(-1, fill_value=False)&eligible.shift(-6, fill_value=False))
    registry = {row['factor_id']: row for row in FactorRegistry(ROOT/'data/factor_registry.sqlite').evaluations()
                if row['run_id'] == folder.name}
    for name, result in results.items():
        assert registry[result['factor_id']]['status'] == result['status']
        assert result['protected'] == {'qualification_executed': False, 'lockbox_executed': False}
        d = pd.read_csv(folder/name/'ic.csv', index_col=0, parse_dates=True)
        # Exclude final label-purge days; sample 50 spread across observed history.
        selected = d.index[::max(1, len(d)//50)][:50]
        for date in selected:
            pairs = pd.DataFrame({'x': scores[name].loc[date], 'y': label.loc[date]}).dropna()
            got = pairs.x.rank().corr(pairs.y.rank()) if len(pairs) >= 30 else np.nan
            np.testing.assert_allclose(got, d.loc[date,'rank_ic'], rtol=1e-10, atol=1e-12, equal_nan=True)
            ic_count += 1
    report = {'status':'PASS','run_id':folder.name,'raw_cells_replayed':cell_count,
              'rank_ic_dates_replayed':ic_count,'registry_reports_matched':len(results),
              'source_snapshot_hashes_verified':len(source_hashes),
              'verification_scope':'direct canonical formulas or pinned PIT source panel, sampled rank correlations, artifacts and registry; not full independent portfolio/model validation'}
    write(folder/'independent_verification.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('run', type=Path)
    verify(p.parse_args().run)
