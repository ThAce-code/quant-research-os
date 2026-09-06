"""Freeze the concrete collection workload, without scoring new hypotheses."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import hashlib
import json
from datetime import datetime,timezone
import pandas as pd
from quant_research.factors.engine import verify_baseline,strict_write_json as write
from quant_research.factors.provenance import verify_data_identity
from quant_research.m2.supplementary import request_plan


def main(root):
    config_path=root/'configs/factors/m2_supplementary.json'
    c=json.loads(config_path.read_text(encoding='utf-8'))
    baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
    frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');verify_data_identity(root,baseline,frozen)
    canonical=root/'data/canonical'/baseline['name']
    intervals=pd.read_parquet(canonical/'membership.parquet')
    plan=request_plan(intervals,c)
    def cached(row):
        params={'code':row.code,'year':int(row.year),'quarter':int(row.quarter)}
        key=hashlib.sha256(json.dumps({'method':row.method,'params':params},sort_keys=True).encode()).hexdigest()[:24]
        path=root/'data/raw/baostock'/row.method/(key+'.csv')
        if not path.exists() or not path.with_suffix('.json').exists():return False
        meta=json.loads(path.with_suffix('.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('cached response hash mismatch')
        return True
    plan['cached_at_plan_time']=[cached(r) for r in plan.itertuples()]
    output=root/'experiments/m2'/c['name']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    plan.to_csv(output/'request_plan.csv',index=False)
    summary={'status':'PLANNED_NOT_COLLECTED','scope':c['data_period'],'unique_historical_members':int(plan.symbol.nunique()),
             'cashflow_requests':len(plan),'cached_requests':int(plan.cached_at_plan_time.sum()),
             'new_requests_required':int((~plan.cached_at_plan_time).sum()),
             'fields':['CFOToOR'],'hypothesis_count':len(c['hypotheses']),
             'supplementary_scores_computed':False,'supplementary_return_evaluation':'NOT_RUN',
             'industry_and_size_extension':'NOT_RUN','qualification_or_lockbox_access':False,
             'protocol_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest()}
    write(output/'config.json',c);write(output/'status.json',summary)
    plan.groupby('year').agg(requests=('symbol','size'),cached=('cached_at_plan_time','sum')).to_csv(output/'requests_by_year.csv')
    print(str(output),flush=True);print(json.dumps(summary),flush=True)


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
