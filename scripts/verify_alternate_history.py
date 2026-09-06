"""Independently replay raw financial values, event dates and every panel cell."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(folder):
    folder=Path(folder);c=read(folder/'config.json')
    assert read(folder/'status.json')['status']=='COLLECTED'
    assert read(folder/'build_verification.json')['status']=='BUILT_PENDING_INDEPENDENT_VERIFICATION'
    for name,digest in read(folder/'build_artifact_hashes.json').items():assert sha(folder/name)==digest,name
    audit=ROOT/c['cache_audit_run'];original=ROOT/c['plan_run']
    plan=pd.read_csv(original/'request_plan.csv');assign=pd.read_csv(folder/'source_assignment.csv').set_index(['symbol','method'])
    complete=pd.read_csv(audit/'stock_method_completeness.csv').set_index(['symbol','method'])
    assert len(assign)==1452 and assign.index.equals(complete.index)
    assert assign.source.eq(np.where(complete.complete_request_history,'baostock','eastmoney_reconstructed')).all()
    member=pd.read_parquet(folder/'membership.parquet')
    pd.testing.assert_frame_equal(member,pd.read_parquet(original/'membership.parquet'))
    canonical=ROOT/'data/canonical'/read(ROOT/'configs/experiments/baostock_alpha158.json')['name']
    calendar=pd.DatetimeIndex(pd.read_parquet(canonical/'calendar.parquet').datetime)
    calendar=calendar[(calendar>=c['data_period'][0])&(calendar<=c['data_period'][1])]
    assert member.index.equals(calendar)
    intervals=pd.read_parquet(canonical/'membership.parquet')
    expected_member=pd.DataFrame(False,index=calendar,columns=member.columns)
    for row in intervals.itertuples():
        if row.instrument in expected_member:expected_member.loc[row.start:row.end,row.instrument]=True
    pd.testing.assert_frame_equal(member,expected_member,check_names=False)
    account=pd.read_csv(folder/'quarter_accounting.csv')
    wanted={(r.symbol,m,str(pd.Period(year=r.year,quarter=r.quarter,freq='Q').end_time.date())) for r in plan.itertuples() for m in c['fields']}
    assert len(account)==40520 and set(zip(account.symbol,account.method,account.period))==wanted
    raw_b={};raw_i={};network_pages=0
    for request in read(folder/'requests.json'):
        path=ROOT/request['path'];assert sha(path)==request['sha256']
        saved=read(path);assert saved['body_sha256']==hashlib.sha256(json.dumps(saved['body'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        assert '2020-06-30' in saved['params']['filter'] and "NOTICE_DATE<='2020-07-31'" in saved['params']['filter']
        dest=raw_i if request['table']=='GINCOME' else raw_b
        for row in (saved['body'].get('result') or {}).get('data',[]):
            symbol=row['SECUCODE'][-2:]+row['SECUCODE'][:6];period=row['REPORT_DATE'][:10]
            assert symbol in request['symbols'] and '2006-01-01'<=period<='2020-06-30'
            assert row['NOTICE_DATE'][:10]<='2020-07-31'
            assert (symbol,period) not in dest
            dest[(symbol,period)]=row
        network_pages+=1
    raw_bs={}
    for n,request in enumerate(read(audit/'available_requests.json')):
        path=Path(request['path']);assert sha(path)==request['sha256']
        params=request['params'];symbol=params['code'][:2].upper()+params['code'][3:]
        if bool(complete.loc[(symbol,request['method']),'complete_request_history']):
            frame=pd.read_csv(path)
            assert len(frame)<=1
            if len(frame):
                row=frame.iloc[0]
                assert row.statDate==str(pd.Period(year=params['year'],quarter=params['quarter'],freq='Q').end_time.date())
                raw_bs[(symbol,request['method'],row.statDate)]=row
        if n%5000==0:print(f'INDEPENDENT RAW {n}',flush=True)
    fields=[f for fs in c['fields'].values() for f in fs]
    panels={f:pd.read_parquet(folder/f'{f}.parquet') for f in fields}
    for p in panels.values():assert p.index.equals(member.index) and p.columns.equals(member.columns)
    cells=0;event_rows=0
    for n,(symbol,group) in enumerate(plan.groupby('symbol')):
        expected={f:[] for f in fields}
        for row in group.itertuples():
            period=str(pd.Period(year=row.year,quarter=row.quarter,freq='Q').end_time.date())
            b=raw_b.get((symbol,period));i=raw_i.get((symbol,period));opening=raw_b.get((symbol,f'{row.year-1}-12-31'))
            for method,names in c['fields'].items():
                if assign.loc[(symbol,method),'source']=='baostock':
                    bs=raw_bs.get((symbol,method,period))
                    if bs is not None and bs.pubDate<=c['data_period'][1]:
                        for f in names:expected[f].append((period,bs.pubDate,float(bs[f])))
                    continue
                for f in names:
                    if f=='roeAvg':current=[b,i];dependencies=[b,i,opening]
                    elif f in ['npMargin','YOYNI']:current=dependencies=[i]
                    else:current=dependencies=[b]
                    present=[x for x in current if x is not None]
                    if not present:continue
                    first=min(x['NOTICE_DATE'][:10] for x in present)
                    assert first>=period
                    all_present=all(x is not None for x in dependencies)
                    available=max(x['NOTICE_DATE'][:10] for x in dependencies) if all_present else first
                    value=np.nan
                    if all_present:
                        try:
                            if f=='roeAvg':value=2*float(i['PARENT_NETPROFIT'])/(float(b['TOTAL_PARENT_EQUITY'])+float(opening['TOTAL_PARENT_EQUITY']))
                            elif f=='npMargin':value=float(i['NETPROFIT'])/float(i['OPERATE_INCOME'])
                            elif f=='YOYNI':value=float(i['NETPROFIT_YOY'])*.01
                            elif f=='YOYAsset':value=float(b['TOTAL_ASSETS_YOY'])*.01
                            else:value=float(b['TOTAL_PARENT_EQUITY_YOY'])*.01
                        except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
                    if not np.isfinite(value):value=np.nan
                    expected[f].append((period,first,value if available==first else np.nan))
                    if available>first and available<=c['data_period'][1]:expected[f].append((period,available,value))
        saved_events=pd.read_parquet(folder/'events'/f'{symbol}.parquet')
        for f in fields:
            e=pd.DataFrame(expected[f],columns=['statDate','pubDate','value'])
            e[['statDate','pubDate']]=e[['statDate','pubDate']].apply(pd.to_datetime)
            e=e.sort_values(['statDate','pubDate']).reset_index(drop=True)
            got=saved_events[saved_events.field.eq(f)][['statDate','pubDate','value']].sort_values(['statDate','pubDate']).reset_index(drop=True)
            pd.testing.assert_frame_equal(got,e,check_dtype=False,check_exact=False,atol=1e-12,rtol=1e-12)
            event_rows+=len(e)
            want=np.full(len(calendar),np.nan)
            if len(e):
                pub=e.pubDate.to_numpy();stat=e.statDate.to_numpy();days=calendar.to_numpy()
                selected=np.where(pub[None,:]<days[:,None],np.arange(len(e))[None,:],-1).max(axis=1)
                safe=np.maximum(selected,0)
                good=(selected>=0)&member[symbol].to_numpy()&((days-pub[safe])/np.timedelta64(1,'D')<=400)&((days-stat[safe])/np.timedelta64(1,'D')<=550)
                want[good]=e.value.to_numpy()[safe[good]]
            np.testing.assert_allclose(panels[f][symbol].to_numpy(),want,rtol=1e-12,atol=1e-12,equal_nan=True)
            cells+=len(want)
        if n%50==0:print(f'INDEPENDENT PANELS {n}/726',flush=True)
    result={'status':'PASS','raw_derived_events_checked':event_rows,'panel_cells_checked':cells,'eastmoney_pages_checked':network_pages,
            'accounted_symbol_method_quarters':len(account),'source_assignment_verified':True,'membership_rebuilt_from_canonical':True,
            'protected_periods_opened':False,'revision_history_verified':False,
            'scope':'Independent raw-value/dependency-date derivation plus fiscal-priority cell replay. Does not certify vendor historical revision accuracy or exact cross-provider equality.'}
    (folder/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main(sys.argv[1])
