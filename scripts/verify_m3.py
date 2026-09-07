"""Replay paper formulas from canonical bars and sampled IC without the DSL."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
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
              'verification_scope':'direct canonical formulas, sampled rank correlations, artifacts and registry; not full independent portfolio/model validation'}
    write(folder/'independent_verification.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('run', type=Path)
    verify(p.parse_args().run)
