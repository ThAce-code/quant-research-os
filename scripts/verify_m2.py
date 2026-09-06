"""Independent raw-response, score/IC and registry reconciliation after a run."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

root = Path(__file__).resolve().parents[1]
run = Path(sys.argv[1]) if len(sys.argv)>1 else Path(json.loads((root/'experiments/m2/m2_value_pilot_v1/latest.json').read_text())['directory'])
config = json.loads((run/'config.json').read_text())
assert json.loads((run/'status.json').read_text())['status'] == 'PASS'
requests = json.loads((run/'data/requests.json').read_text())
valuation_panels = {f: pd.read_parquet(run/'data'/f'{f}.parquet') for f in config['factors'].values()}
source_cells = 0
for item in requests:
    path = Path(item['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
    if item['method'] != 'query_history_k_data_plus': continue
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    symbol = item['params']['code'].replace('.','').upper()
    for field in config['factors'].values():
        saved = valuation_panels[field][symbol]
        if raw.empty:
            assert saved.isna().all(); continue
        index = pd.to_datetime(raw.date)
        values = pd.Series(pd.to_numeric(raw[field].replace('', np.nan)).to_numpy(), index=index)
        expected = values.reindex(saved.index).shift(1)
        np.testing.assert_allclose(saved, expected, equal_nan=True)
        source_cells += len(saved)

labels = pd.read_parquet(run/'labels_h5.parquet')
ic_samples, portfolio_days = 0, 0
for folder in sorted(run.iterdir()):
    if not folder.is_dir() or not (folder/'scores.parquet').exists(): continue
    score = pd.read_parquet(folder/'scores.parquet')
    daily = pd.read_csv(folder/'ic_h5.csv', index_col=0, parse_dates=True)
    for date in daily.index[::17]:
        x,y = score.loc[date].align(labels.loc[date])
        ok = x.notna() & y.notna()
        if ok.sum()<30 or x[ok].std()==0 or y[ok].std()==0: continue
        expected = spearmanr(x[ok],y[ok]).statistic
        assert abs(expected-daily.loc[date,'rank_ic'])<1e-10
        ic_samples += 1
    report = json.loads((folder/'report.json').read_text())
    for which in ['top10','top20']:
        path = pd.read_csv(folder/f'{which}_daily.csv', index_col=0, parse_dates=True, dtype={'bench': np.float32})
        metrics = report['splits']['valid']['portfolio'][which]
        net = path['return']-path.cost
        assert abs((net-path.bench).mean()*238 - metrics['net_excess_annual'])<1e-10
        nav = np.r_[1,np.cumprod(1+net.to_numpy())]
        assert abs(np.min(nav/np.maximum.accumulate(nav)-1) - metrics['net_mdd'])<1e-10
        assert (path.loc[path.turnover>0,'cost']>0).all()
        portfolio_days += len(path)
    with sqlite3.connect(root/'data/m2_factor_registry.sqlite') as db:
        row = db.execute('SELECT report_json FROM evaluations WHERE run_id=? AND factor_id=?', (run.name,'M2_'+folder.name)).fetchone()
        assert row and json.loads(row[0]) == report

industry = pd.read_parquet(run/'data/industry.parquet')
events = pd.read_parquet(run/'data/industry_events.parquet')
industry_cells = 0
for code in ['sh.600000','sz.000001','sh.600519']:
    records = events[events.code.eq(code)].sort_values('snapshot_date')
    for date in industry.index[::11]:
        past = records[records.snapshot_date.lt(date)]
        observed = industry.loc[date,code.replace('.','').upper()]
        if past.empty or (date-past.iloc[-1].snapshot_date).days>62:
            assert pd.isna(observed)
        else: assert observed == past.iloc[-1].industry
        industry_cells += 1
    financial = pd.read_parquet(run/'data'/f'{code}_financial_events.parquet')
    aligned = pd.read_parquet(run/'data'/f'{code}_financial_daily.parquet')
    financial.pubDate = pd.to_datetime(financial.pubDate)
    financial.statDate = pd.to_datetime(financial.statDate)
    for date in aligned.index:
        past = financial[financial.pubDate.lt(date)].sort_values(['statDate','pubDate'])
        if past.empty:
            assert pd.isna(aligned.loc[date,'roeAvg']); continue
        row = past.iloc[-1]
        want = row.roeAvg if (date-row.pubDate).days<=400 else np.nan
        np.testing.assert_allclose(aligned.loc[date,'roeAvg'], want, equal_nan=True)
        source_cells += 1

for name,want in json.loads((run/'source_hashes.json').read_text()).items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==want
increments = json.loads((run/'incremental.json').read_text())
for name in config['factors']:
    blend = pd.read_parquet(run/(name+'_blend')/'scores.parquet')
    reference = pd.read_parquet(run/(name+'_matched_reference')/'scores.parquet')
    pd.testing.assert_frame_equal(blend.notna(), reference.notna())
    a = pd.read_csv(run/(name+'_blend')/'top20_daily.csv', index_col=0)
    b = pd.read_csv(run/(name+'_matched_reference')/'top20_daily.csv', index_col=0)
    pd.testing.assert_index_equal(a.index, b.index)
    delta = (a['return']-a.cost)-(b['return']-b.cost)
    assert abs(delta.mean()*238-increments[name]['annual_delta'])<1e-10
for name,want in json.loads((run/'artifact_hashes.json').read_text()).items():
    assert hashlib.sha256((run/name).read_bytes()).hexdigest()==want
result = {'status':'PASS','source_cells':source_cells,'independent_spearman_samples':ic_samples,
          'portfolio_days':portfolio_days,'industry_cells':industry_cells,'registry_parity':True}
(run/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
