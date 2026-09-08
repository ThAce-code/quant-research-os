"""Pre-return feasibility gate for two finite event-guidance definitions."""
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.m2.core import neutralize
from build_r2_event_ledger import read,write,sha


def event_features(events,calendar,membership,max_age):
    calendar=pd.DatetimeIndex(calendar)
    out={name:pd.DataFrame(np.nan,index=calendar,columns=membership.columns) for name in
         ('R2_GUIDANCE_MIDPOINT','R2_GUIDANCE_LOWER')}
    groups=defaultdict(list)
    for e in events:groups[e['code']].append(e)
    for code,rows in groups.items():
        instrument=('SH' if code.startswith('6') else 'SZ')+code
        if instrument not in membership:continue
        rows=sorted(rows,key=lambda e:(e['available_date'],e['event_id']))
        for i,e in enumerate(rows):
            start=calendar.searchsorted(pd.Timestamp(e['available_date']))
            end=min(start+max_age,len(calendar))
            if i+1<len(rows):end=min(end,calendar.searchsorted(pd.Timestamp(rows[i+1]['available_date'])))
            # Every newer document clears the previous forecast, even if missing,
            # quarantined, actual-result rather than forecast, or out of membership.
            if e['kind']!='forecast' or e['data_status'].startswith('QUARANTINED'):continue
            if e['yoy_value_kind']=='RANGE':lo,hi=e['yoy_lower_percent'],e['yoy_upper_percent']
            elif e['yoy_value_kind']=='POINT':lo=hi=e['yoy_point_percent']
            else:continue
            if lo is None or hi is None:continue
            for name,value in [('R2_GUIDANCE_MIDPOINT',(lo+hi)/2),('R2_GUIDANCE_LOWER',lo)]:
                out[name].loc[calendar[start:end],instrument]=np.sign(value)*np.log1p(abs(value)/100)
    return {name:p.where(membership) for name,p in out.items()}


def main():
    config_path=ROOT/'configs/r2/event_feature_gate.json';c=read(config_path)
    out=ROOT/'experiments/r2'/c['run_id']
    if out.exists():raise ValueError('immutable feasibility run exists')
    assert c['max_return_evaluations']==0 and c['period'][1]<'2021-01-01'
    paths=[config_path,Path(__file__),ROOT/c['events'],ROOT/c['calendar'],ROOT/c['membership'],
           ROOT/c['controls']/'log_size.parquet',ROOT/c['controls']/'industry.parquet']
    for name,expected in c['input_hashes'].items():
        assert sha(ROOT/name)==expected,name
    events=read(ROOT/c['events'])
    full=pd.DatetimeIndex(pd.read_parquet(ROOT/c['calendar']).datetime)
    calendar=full[(full>=c['period'][0])&(full<=c['period'][1])]
    intervals=pd.read_parquet(ROOT/c['membership'])
    members=pd.DataFrame(False,index=calendar,columns=sorted(intervals.instrument.unique()))
    for row in intervals.itertuples(index=False):members.loc[row.start:row.end,row.instrument]=True
    size=pd.read_parquet(ROOT/c['controls']/'log_size.parquet').reindex(index=calendar,columns=members.columns)
    industry=pd.read_parquet(ROOT/c['controls']/'industry.parquet').reindex(index=calendar,columns=members.columns)
    features=event_features(events,calendar,members,c['active_trading_dates'])
    result=[];out.mkdir(parents=True)
    for name,p in features.items():
        neutral,checks=neutralize(p,size,industry,min_group=c['min_industry_members'])
        counts=neutral.notna().sum(axis=1)
        eligible=counts.ge(c['min_cross_section'])
        years={str(y):int(eligible[calendar.year==y].sum()) for y in (2015,2016)}
        passed=bool(eligible.sum()>=c['min_valid_dates'] and all(n>=c['min_dates_per_year'] for n in years.values()))
        result.append({'candidate':name,'raw_observed_cells':int(p.notna().sum().sum()),
                       'raw_max_cross_section':int(p.notna().sum(axis=1).max()),
                       'neutralized_observed_cells':int(neutral.notna().sum().sum()),
                       'eligible_dates':int(eligible.sum()),'eligible_dates_by_year':years,
                       'gate':'PASS_COVERAGE_ONLY' if passed else 'NO_GO_DATA_COVERAGE',
                       'research_admission':False,'alpha_confirmed':False})
        p.to_parquet(out/(name+'_raw.parquet'));neutral.to_parquet(out/(name+'_neutral.parquet'))
        pd.DataFrame({'raw_count':p.notna().sum(axis=1),'neutralized_count':counts}).to_csv(out/(name+'_coverage.csv'))
    summary={'run_id':c['run_id'],'candidates':result,'price_or_label_reads':False,'return_evaluations':0,
             'full_technical_increment_tested':False,'independent_alpha_confirmed':False,
             'qualification_executed':False,'lockbox_executed':False}
    write(out/'summary.json',summary)
    write(out/'source_hashes.json',{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in paths})
    write(out/'artifact_hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
