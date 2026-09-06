"""Build full original-scope panels with whole-history source assignment."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from quant_research.m2.alternate import field_events, FIELDS
from quant_research.m2.quarterly import daily_panel, clean_events
from quant_research.factors.engine import verify_baseline

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def statements(folder):
    balance={};income={};duplicates=[]
    for request in read(folder/'requests.json'):
        path=ROOT/request['path'];assert sha(path)==request['sha256']
        saved=read(path)
        rows=(saved['body'].get('result') or {}).get('data',[])
        target=income if request['table']=='GINCOME' else balance
        for row in rows:
            key=(row['SECUCODE'],row['REPORT_DATE'][:10])
            if key in target:
                # Cross-table duplicates require review, never arbitrary first/last.
                duplicates.append(key)
            else:target[key]=row
    assert not duplicates, f'Ambiguous cross-table financial reports: {duplicates[:10]}'
    return balance,income


def main(folder):
    folder=Path(folder);assert read(folder/'status.json')['status']=='COLLECTED'
    c=read(folder/'config.json');audit=ROOT/c['cache_audit_run'];original=ROOT/c['plan_run']
    for name,hash_value in c['input_hashes'].items():assert sha((original if name=='request_plan.csv' else audit)/name)==hash_value
    verify_baseline(ROOT,'BL-CN-CSI300-A158-LGBM-001')
    source_names=['scripts/build_alternate_history.py','src/quant_research/m2/alternate.py','src/quant_research/m2/quarterly.py','src/quant_research/m2/core.py']
    hashes={n:sha(ROOT/n) for n in source_names}
    for n in source_names:
        target=folder/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,target)
    write(folder/'build_source_hashes.json',hashes)
    member=pd.read_parquet(original/'membership.parquet')
    plan=pd.read_csv(original/'request_plan.csv')
    complete=pd.read_csv(audit/'stock_method_completeness.csv').set_index(['symbol','method']).complete_request_history
    assert len(member.columns)==726 and len(plan)==20260
    balance,income=statements(folder)
    bs_records={};cache_requests=read(audit/'available_requests.json')
    for n,request in enumerate(cache_requests):
        path=Path(request['path']);assert sha(path)==request['sha256']
        p=request['params'];key=(p['code'],request['method'],p['year'],p['quarter'])
        frame=pd.read_csv(path,dtype=str,keep_default_na=False)
        assert len(frame)<=1, 'Ambiguous BaoStock report versions'
        bs_records[key]=frame
        if n%5000==0:print(f'CACHE {n}/{len(cache_requests)}',flush=True)
    panels={f:member.astype(float)*np.nan for f in FIELDS}
    events_dir=folder/'events';events_dir.mkdir(exist_ok=True)
    assignments=[];accounting=[];comparisons=[];event_count=0
    for n,(symbol,group) in enumerate(plan.groupby('symbol')):
        code=group.code.iloc[0];emcode=symbol[2:]+'.'+symbol[:2]
        periods=[str(pd.Period(year=r.year,quarter=r.quarter,freq='Q').end_time.date()) for r in group.itertuples()]
        b={p:r for (s,p),r in balance.items() if s==emcode};i={p:r for (s,p),r in income.items() if s==emcode}
        needed_balance=set(periods)|{f'{int(p[:4])-1}-12-31' for p in periods}
        for rows,needed in [(b,needed_balance),(i,set(periods))]:
            for period,row in rows.items():
                if period in needed:
                    assert period<=row['NOTICE_DATE'][:10], f'Required invalid date: {symbol} {period}'
        em=field_events(code,periods,b,i)
        if len(em):em=em[em.pubDate.le(pd.Timestamp(c['data_period'][1]))]
        chosen=[]
        for method,fields in c['fields'].items():
            use_bs=bool(complete.loc[(symbol,method)])
            provider='baostock' if use_bs else 'eastmoney_reconstructed'
            assignments.append({'symbol':symbol,'method':method,'source':provider,'planned_quarters':len(group)})
            bs=[]
            for r,period in zip(group.itertuples(),periods):
                raw=bs_records.get((code,method,int(r.year),int(r.quarter)))
                if use_bs:assert raw is not None
                if raw is not None and len(raw):
                    assert raw.statDate.iloc[0]==period
                    bs.append(raw)
                current=em[em.statDate.eq(pd.Timestamp(period)) & em.field.isin(fields)]
                accounting.append({'symbol':symbol,'method':method,'period':period,'source':provider,
                                   'baostock_request_cached':raw is not None,
                                   'source_record_present':bool(len(raw)) if use_bs else bool(len(current)),
                                   'eastmoney_balance_present':period in b,'eastmoney_income_present':period in i})
                if raw is not None and len(raw) and len(current):
                    for field in fields:
                        row=current[current.field.eq(field)].sort_values('pubDate')
                        if row.empty:continue
                        old=pd.to_numeric(raw[field].iloc[0],errors='coerce');new=row.iloc[-1]
                        comparisons.append({'symbol':symbol,'period':period,'field':field,'baostock':old,'eastmoney':new.value,
                                            'baostock_pubDate':raw.pubDate.iloc[0],'eastmoney_available':str(new.pubDate.date()),
                                            'updated_after_notice':bool(new.updated_after_notice)})
            if use_bs:
                raw=pd.concat(bs,ignore_index=True) if bs else pd.DataFrame(columns=['code','pubDate','statDate']+fields)
                raw=raw[pd.to_datetime(raw.pubDate).le(pd.Timestamp(c['data_period'][1]))]
                cleaned,bad=clean_events(raw,code,fields,c['data_period'][1]);assert bad.empty
                long=cleaned.melt(id_vars=['code','pubDate','statDate'],value_vars=fields,var_name='field',value_name='value')
                long['source']='baostock';long['revision_unknown']=True;long['updated_after_notice']=False;long['dependencies_present']=True
                chosen.append(long)
            else:chosen.append(em[em.field.isin(fields)])
        events=pd.concat(chosen,ignore_index=True)
        assert not events.duplicated(['field','statDate','pubDate']).any()
        events.to_parquet(events_dir/f'{symbol}.parquet',index=False);event_count+=len(events)
        for field in FIELDS:
            e=events[events.field.eq(field)][['code','pubDate','statDate','value']].rename(columns={'value':field})
            panels[field][symbol]=daily_panel(e,member.index,[field],400,550)[field].where(member[symbol])
        if n%50==0:print(f'PANELS {n}/726',flush=True)
    member.to_parquet(folder/'membership.parquet')
    pd.DataFrame(assignments).to_csv(folder/'source_assignment.csv',index=False)
    pd.DataFrame(accounting).to_csv(folder/'quarter_accounting.csv',index=False)
    cmp=pd.DataFrame(comparisons);cmp['absolute_difference']=(cmp.baostock-cmp.eastmoney).abs()
    cmp.to_csv(folder/'cross_source_comparison.csv',index=False)
    summary=[]
    for field,g in cmp.groupby('field'):
        finite=g.baostock.notna()&g.eastmoney.notna()
        summary.append({'field':field,'overlapping_records':len(g),'finite_pairs':int(finite.sum()),
                        'within_1e_6':int(g.absolute_difference.le(1e-6).sum()),
                        'within_1e_4':int(g.absolute_difference.le(1e-4).sum()),
                        'median_absolute_difference':float(g.absolute_difference.median()),
                        'max_absolute_difference':float(g.absolute_difference.max()),
                        'same_availability_date':int(g.baostock_pubDate.eq(g.eastmoney_available).sum()),
                        'updated_after_notice':int(g.updated_after_notice.sum())})
    pd.DataFrame(summary).to_csv(folder/'cross_source_summary.csv',index=False)
    coverage=[]
    for field,panel in panels.items():
        panel.to_parquet(folder/f'{field}.parquet')
        for year in sorted(member.index.year.unique()):
            eligible=member.loc[str(year)];n=int((panel.loc[str(year)].notna()&eligible).to_numpy().sum());den=int(eligible.to_numpy().sum())
            coverage.append({'field':field,'year':int(year),'available_cells':n,'eligible_cells':den,'coverage':n/den})
    pd.DataFrame(coverage).to_csv(folder/'coverage.csv',index=False)
    assert len(accounting)==40520 and len(assignments)==1452
    assert all(sha(ROOT/n)==v for n,v in hashes.items())
    result={'status':'BUILT_PENDING_INDEPENDENT_VERIFICATION','symbols':726,'symbol_methods':1452,'planned_quarters':20260,
            'accounted_symbol_method_quarters':len(accounting),'events':event_count,'baostock_requests_verified':len(cache_requests),
            'eastmoney_pages_verified':len(read(folder/'requests.json')),'source_assignment':pd.DataFrame(assignments).source.value_counts().to_dict(),
            'revision_history_verified':False,'protected_periods_opened':False,'factor_results_changed':False}
    write(folder/'build_verification.json',result)
    write(folder/'build_artifact_hashes.json',{str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file() and 'source' not in p.relative_to(folder).parts and p.name!='build_artifact_hashes.json'})
    print(json.dumps(result),flush=True)


if __name__=='__main__':main(sys.argv[1])
