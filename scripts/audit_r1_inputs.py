"""Read-only R1 financial feasibility audit; no returns, labels or network calls."""
from pathlib import Path
import csv
import hashlib
import json

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'experiments/r1/input_audit_v1'
INPUTS={
    'profit':'experiments/m2/m2_history_cache_audit_v1/20260906T095714683879Z/available_requests.json',
    'cash':'experiments/m2/m2_supplementary_data_v1/20260906T072711741731Z/requests.json'}
METHODS={'profit':'query_profit_data','cash':'query_cash_flow_data'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    source=[];frames={}
    for kind,name in INPUTS.items():
        path=ROOT/name
        requests=json.loads(path.read_text(encoding='utf-8'))
        source.append({'path':name,'sha256':sha(path),'kind':'manifest'})
        rows=[];seen=set();count=0
        for request in requests:
            if request['method']!=METHODS[kind]:continue
            params=request['params']
            if int(params['year'])>2020 or (int(params['year'])==2020 and int(params['quarter'])>2):
                raise ValueError('financial request outside permitted source period')
            p=Path(request['path']);digest=sha(p)
            if digest!=request['sha256']:raise ValueError('raw cache changed')
            if p in seen:continue
            seen.add(p);count+=1
            source.append({'path':str(p.relative_to(ROOT)),'sha256':digest,'kind':kind})
            raw=list(csv.DictReader(p.read_text(encoding='utf-8').splitlines()))
            if len(raw)>1:raise ValueError('ambiguous quarterly versions')
            for row in raw:
                expected=pd.Period(year=int(params['year']),quarter=int(params['quarter']),freq='Q').end_time.strftime('%Y-%m-%d')
                if row['code']!=params['code'] or row['statDate']!=expected:raise ValueError('request identity mismatch')
                rows.append(row)
        frame=pd.DataFrame(rows)
        for col in ['pubDate','statDate']:frame[col]=pd.to_datetime(frame[col],errors='raise')
        if (frame.statDate>frame.pubDate).any() or frame.duplicated(['code','statDate']).any():raise ValueError('invalid fiscal identity')
        for col in frame.columns.difference(['code','pubDate','statDate']):frame[col]=pd.to_numeric(frame[col],errors='coerce')
        frame.to_parquet(OUT/(kind+'.parquet'),index=False);frames[kind]=frame
        print(kind,'requests',count,'records',len(frame),flush=True)
    p=frames['profit'];c=frames['cash'];joined=p.merge(c,on=['code','statDate'],suffixes=('_profit','_cash'),validate='one_to_one')
    joined=joined[joined.pubDate_profit.le('2020-07-31') & joined.pubDate_cash.le('2020-07-31')]
    identity=(joined.netProfit/joined.MBRevenue)-joined.npMargin
    cash_identity=joined.CFOToNP*joined.npMargin-joined.CFOToOR
    def summary(x):
        x=x.replace([np.inf,-np.inf],np.nan).dropna().abs()
        return {'rows':len(x),'median_abs_error':float(x.median()),'p95_abs_error':float(x.quantile(.95)),
                'within_1e_5':int(x.le(1e-5).sum()),'within_1e_3':int(x.le(1e-3).sum())}
    report={'status':'PASS_DATA_AUDIT_ONLY','protected_returns_loaded':False,'network_requests':0,
        'sources':INPUTS,'rows':{k:len(v) for k,v in frames.items()},'same_fiscal_pairs':len(joined),
        'same_publication_date_pairs':int(joined.pubDate_profit.eq(joined.pubDate_cash).sum()),
        'profit_revenue_ratio_check':summary(identity),'cash_profit_ratio_check':summary(cash_identity),
        'raw_balance_amounts_full_scope_available':False,
        'limitations':['BaoStock revisions remain unknown; same code/fiscal quarter does not guarantee original historical vintage.',
                      'No full-scope assets or raw operating cashflow amount cache. Alternate-source income/balance covers a subset and is not silently mixed.',
                      'Published values after 2020-07-31 are preserved in source cache but excluded from feasibility pairs.']}
    joined.to_parquet(OUT/'same_period_pairs.parquet',index=False)
    (OUT/'source_hashes.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
    (OUT/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
