"""Audit completed or stopped BaoStock acquisition; no prices, labels or factor evaluation."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import sqlite3
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def classify(row,kind,unions,targets):
    prefix='profitForcastExp' if kind=='forecast' else 'performanceExp'
    period=row.get(prefix+'StatDate','');notice=row.get(prefix+'PubDate','')
    reasons=[]
    if period not in targets:reasons.append('NON_TARGET_REPORT_PERIOD')
    if not notice or pd.isna(pd.to_datetime(notice,errors='coerce')):reasons.append('INVALID_PUBLICATION_DATE')
    elif period in targets and not period[:4]+'-01-01'<=notice<=period[:4]+'-04-30':reasons.append('OUTSIDE_TARGET_NOTICE_WINDOW')
    member=row['code'] in unions.get(period[:4],[])
    if not member:reasons.append('NOT_IN_TARGET_YEAR_MEMBER_UNION')
    return {'report_period':period,'notice_date':notice,'historical_member_union':member,
            'scope_eligible':not reasons,'exclusion_reasons':reasons,
            'version_status':'UNVERIFIED','research_admission':False}


def main():
    run=ROOT/'experiments/r2/r2_baostock_event_bulk_v1';state=read(run/'status.json')
    if state['status'] not in ['PASS','STOPPED']:raise ValueError('Collection has not finished or stopped')
    for name,h in read(run/'artifact_hashes.json').items():assert sha(run/name)==h,name
    jobs=read(run/'plan.json');unions=read(run/'member_unions.json');cfg=read(run/'config.json')
    rows=[];checks=[];missing=[];hashes={}
    for i,job in enumerate(jobs):
        path=run/'responses'/f'{i:04d}.json'
        if not path.exists():missing.append({'index':i,'request':job,'status':'NOT_REQUESTED'});continue
        data=read(path);assert data['request']==job;hashes[str(path.relative_to(ROOT)).replace('\\','/')]=sha(path)
        if data['status']!='PASS':missing.append({'index':i,'request':job,'status':data['status'],'code':data.get('code')});continue
        assert data['code']=='0'
        kind='forecast' if job['method']=='query_forecast_report' else 'express'
        for values in data['data']:
            assert len(values)==len(data['fields'])
            row=dict(zip(data['fields'],values));assert row['code']==job['params']['code']
            rows.append({'kind':kind,'source_request':i,'raw':row,**classify(row,kind,unions,cfg['target_report_dates'])})
        checks.append({'index':i,'code':job['params']['code'],'kind':kind,'rows':len(data['data']),'response_sha256':sha(path)})
    assert len(checks)==state['completed']
    assert sum(c['rows'] for c in checks)==state['rows']
    if state['status']=='PASS':assert not missing and len(checks)==len(jobs)
    recoveries=[]
    for path in sorted((run/'session_recoveries').glob('*/recovery.json')):
        event=read(path);failed=path.parent/'failed_response.json';record=read(failed)
        assert sha(failed)==event['failed_response_sha256']
        assert record['code']=='10001001' and record['data']==[] and record['fields']==[]
        assert record['request']==jobs[event['query_index']]
        recoveries.append(event)
        for source in [path,failed]:hashes[str(source.relative_to(ROOT)).replace('\\','/')]=sha(source)
    if recoveries:
        policy=read(run/'session_recovery_policy.json')
        assert len(recoveries)<=policy['max_session_refreshes']
        assert max(Counter(r['query_index'] for r in recoveries).values())<=policy['max_refreshes_per_failed_query']
    coverage=[]
    for period in cfg['target_report_dates']:
        for kind in ['forecast','express']:
            selected=[r for r in rows if r['kind']==kind and r['report_period']==period]
            eligible=[r for r in selected if r['scope_eligible']]
            code_counts=Counter(r['raw']['code'] for r in selected)
            coverage.append({'period':period,'kind':kind,'raw_target_rows':len(selected),
                'eligible_member_notice_rows':len(eligible),'eligible_companies':len({r['raw']['code'] for r in eligible}),
                'multiple_rows_company_period':sum(n>1 for n in code_counts.values()),
                'member_union_denominator':len(unions[period[:4]])})
    cases=[]
    for case in read(ROOT/'configs/r2/reviewed_backfill_cases.json')['cases']:
        matches=[r['raw'] for r in rows if r['kind']=='forecast' and r['raw']['code'][3:]==case['code'] and r['report_period']==case['period'] and r['notice_date']==case['notice_date']]
        if not matches:status='NO_SAME_DATE_VERSION_RETURNED'
        elif len(matches)>1:status='AMBIGUOUS_MULTIPLE_ROWS'
        else:
            row=matches[0];raw_bounds=[row.get('profitForcastChgPctDwn',''),row.get('profitForcastChgPctUp','')]
            if case['yoy_lower_percent'] is None:status='QUALITATIVE_CASE_REQUIRES_CONTENT_REVIEW'
            elif any(x=='' for x in raw_bounds):status='MISSING_PROVIDER_NUMERIC_BOUNDS'
            else:
                bounds=sorted(map(float,raw_bounds))
                status='YOY_BOUNDS_MATCH' if abs(bounds[0]-case['yoy_lower_percent'])<1e-8 and abs(bounds[1]-case['yoy_upper_percent'])<1e-8 else 'YOY_BOUNDS_MISMATCH'
        cases.append({'announcement_id':case['announcement_id'],'code':case['code'],'period':case['period'],
            'notice_date':case['notice_date'],'status':status,'matching_provider_rows':len(matches),
            'limits':'Date and YoY bounds only; not an amount, text or population-wide version validation'})
    comparisons=[]
    for period in cfg['target_report_dates']:
        source=read(ROOT/f'experiments/r2/r2_event_feasibility_v1/forecast_{period}_rows.json')
        source={(r['SECURITY_CODE'],r['NOTICE_DATE'][:10]):r for r in source if r['PREDICT_FINANCE_CODE']=='004'}
        for item in rows:
            if item['kind']!='forecast' or item['report_period']!=period:continue
            row=item['raw'];other=source.get((row['code'][3:],item['notice_date']))
            status='NO_SAME_DATE_EASTMONEY_ROW'
            if other:
                a=[row.get('profitForcastChgPctDwn',''),row.get('profitForcastChgPctUp','')];b=[other.get('ADD_AMP_LOWER'),other.get('ADD_AMP_UPPER')]
                if any(v in ['',None] for v in a+b):status='MISSING_NUMERIC_BOUND'
                else:status='ADD_AMP_BOUNDS_MATCH' if all(abs(x-y)<1e-6 for x,y in zip(sorted(map(float,a)),sorted(map(float,b)))) else 'ADD_AMP_BOUNDS_MISMATCH'
            comparisons.append({'code':row['code'],'period':period,'notice_date':item['notice_date'],'status':status})
    registry={}
    for name in ['factor_registry.sqlite','m2_factor_registry.sqlite']:
        with sqlite3.connect((ROOT/'data'/name).as_uri()+'?mode=ro',uri=True) as db:
            registry[name]={'evaluations':db.execute('select count(*) from evaluations').fetchone()[0],
                            'keep':db.execute("select count(*) from evaluations where status='KEEP'").fetchone()[0]}
    out=run/'audit';out.mkdir(exist_ok=False)
    result={'status':'PASS_ACQUISITION_AUDIT' if state['status']=='PASS' else 'PARTIAL_ACQUISITION_AUDIT',
        'collection':state,'coverage':coverage,'raw_rows':len(rows),'excluded_rows':sum(not r['scope_eligible'] for r in rows),
        'session_refreshes':len(recoveries),'archived_session_failures':recoveries,
        'case_status_counts':dict(Counter(c['status'] for c in cases)),
        'eastmoney_comparison_counts':dict(Counter(c['status'] for c in comparisons)),
        'registry':registry,'returns_loaded':False,'qualification':'SEALED','lockbox':'SEALED',
        'research_admission':'NOT_READY_PENDING_ORIGINAL_VERSION_AND_CONTENT_VALIDATION',
        'limits':'Historical member-union event coverage, not daily factor coverage. API range includes intervening quarters; raw values retained. Source agreement does not establish independent provenance or historical completeness.',
        'verifier_sha256':sha(Path(__file__))}
    for name,value in [('summary',result),('requests',checks),('missing_requests',missing),('source_hashes',hashes),('case_comparison',cases),('eastmoney_comparison',comparisons),('classified_rows',rows)]:write(out/f'{name}.json',value)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
