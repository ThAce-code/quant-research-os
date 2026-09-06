"""Execute the sealed supplementary data workload using the existing cache."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import traceback
import numpy as np
import pandas as pd
from filelock import FileLock
from ..baostock_data import BaoStockCache
from ..factors.engine import strict_write_json as write,verify_baseline
from ..factors.provenance import verify_data_identity
from .supplementary import request_plan
from .quarterly import clean_events,daily_panel
from .core import asof_events,circulating_cap

PROTOCOL_SHA256='5570c504c52b8f53229bd5cec394135d8055003ef2df49d148a846e2e4ccfae5'


def protocol(root):
    p=root/'configs/factors/m2_supplementary.json'
    if hashlib.sha256(p.read_bytes()).hexdigest()!=PROTOCOL_SHA256:raise ValueError('frozen supplementary protocol changed')
    return json.loads(p.read_text(encoding='utf-8'))


def illiquidity(bars):
    close=(bars.close*bars.factor).where(~bars.is_suspended & bars.close.gt(0))
    daily=close.pct_change(fill_method=None).abs()/bars.amount.where(bars.amount.gt(0))
    return np.log1p(1e6*daily.rolling(20,min_periods=20).mean())


def cash_events(raw,code,end):
    # A later publication is expected for 2020Q2. Preserve it in the raw cache
    # but exclude it, without confusing it with malformed in-window evidence.
    pub=pd.to_datetime(raw.pubDate,errors='coerce')
    future=pub.gt(pd.Timestamp(end))
    clean,bad=clean_events(raw.loc[~future].copy(),code,['CFOToOR'],end)
    if len(bad):raise ValueError(f'quarantined cashflow evidence: {code}; {bad.reason.value_counts().to_dict()}')
    return clean,int(future.sum())


def run(root):
    with FileLock(str(root/'data/factor_engine.lock'),timeout=0):return _run(root)


def _run(root):
    c=protocol(root)
    output=root/'experiments/m2'/'m2_supplementary_data_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state={'status':'RUNNING','stage':'prepare','run_id':output.name}
    write(output/'status.json',state);write(output/'config.json',c)
    print(f'SUPPLEMENTARY_DATA {output}',flush=True)
    try:
        names=['configs/factors/m2_supplementary.json','src/quant_research/m2/supplementary_data.py',
               'src/quant_research/m2/supplementary.py','src/quant_research/m2/quarterly.py',
               'src/quant_research/m2/core.py','src/quant_research/baostock_data.py','scripts/collect_supplementary.py']
        hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
        for n in names:
            dest=output/'source'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/n,dest)
        write(output/'source_hashes.json',hashes)
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');identity=verify_data_identity(root,baseline,frozen)
        canonical=root/'data/canonical'/baseline['name']
        all_dates=pd.DatetimeIndex(pd.read_parquet(canonical/'calendar.parquet').datetime)
        dates=all_dates[(all_dates>=c['data_period'][0])&(all_dates<=c['data_period'][1])]
        intervals=pd.read_parquet(canonical/'membership.parquet')
        plan=request_plan(intervals,c);plan.to_csv(output/'request_plan.csv',index=False)
        symbols=sorted(plan.symbol.unique());members=pd.DataFrame(False,index=dates,columns=symbols)
        for r in intervals.itertuples():
            if r.instrument in members:members.loc[r.start:r.end,r.instrument]=True
        members.to_parquet(output/'membership.parquet')
        panels={n:pd.DataFrame(np.nan,index=dates,columns=symbols) for n in ['CFOToOR','ILLIQUIDITY_20','BP','log_size']}
        industry=pd.DataFrame(index=dates,columns=symbols,dtype=object)
        fiscal=pd.DataFrame(pd.NaT,index=dates,columns=symbols,dtype='datetime64[ns]')
        event_dir=output/'events';event_dir.mkdir()
        audits=[];snapshots=[];done=0
        with BaoStockCache(root/'data/raw/baostock') as source:
            for i,(symbol,requests) in enumerate(plan.groupby('symbol')):
                frames=[]
                for r in requests.itertuples():
                    f=source.query(r.method,allow_empty=True,code=r.code,year=int(r.year),quarter=int(r.quarter))
                    expected=pd.Period(year=r.year,quarter=r.quarter,freq='Q').end_time.normalize()
                    if len(f) and not pd.to_datetime(f.statDate,errors='coerce').eq(expected).all():raise ValueError('wrong fiscal quarter')
                    frames.append(f);done+=1
                    if done%200==0:
                        state.update(stage='cashflow',requests_completed=done,requests_total=len(plan),stocks_completed=i)
                        write(output/'status.json',state);print(f'CASHFLOW {done}/{len(plan)} stocks {i}/{len(symbols)}',flush=True)
                raw=pd.concat(frames,ignore_index=True)
                clean,future=cash_events(raw,requests.code.iloc[0],c['data_period'][1])
                clean.to_parquet(event_dir/(symbol+'.parquet'),index=False)
                joined=daily_panel(clean,dates,['CFOToOR'],400,550)
                panels['CFOToOR'][symbol]=pd.to_numeric(joined.CFOToOR).where(members[symbol])
                fiscal[symbol]=pd.to_datetime(joined.statDate).where(members[symbol])
                audits.append({'symbol':symbol,'requests':len(requests),'empty_requests':sum(f.empty for f in frames),
                               'records':len(raw),'usable_records':len(clean),'publication_after_end':future})
                if i%25==0:write(output/'requests.json',source.manifest)
            write(output/'requests.json',source.manifest)
            print('CASHFLOW COMPLETE; extending historical industry and BP',flush=True)
            for date in pd.date_range(pd.Timestamp(c['data_period'][0])-pd.offsets.MonthEnd(1),c['data_period'][1],freq='ME'):
                f=source.query('query_stock_industry',allow_empty=True,date=str(date.date()))
                if len(f) and (pd.to_datetime(f.updateDate).gt(date).any() or f.code.duplicated().any()):raise ValueError('invalid industry snapshot')
                f['snapshot_date']=date;snapshots.append(f)
            events=pd.concat(snapshots,ignore_index=True);events.to_parquet(output/'industry_events.parquet',index=False)
            for i,symbol in enumerate(symbols):
                own=plan[plan.symbol.eq(symbol)].iloc[0];code=own.code
                first=pd.Timestamp(own.first_signal)-pd.Timedelta(days=10)
                first=max(first,pd.Timestamp('2007-09-01'))
                f=source.query('query_history_k_data_plus',allow_empty=True,code=code,fields='date,code,pbMRQ',
                               start_date=str(first.date()),end_date=own.last_signal,frequency='d',adjustflag='3')
                if len(f):
                    f['date']=pd.to_datetime(f.date)
                    if f.date.duplicated().any() or not f.date.isin(all_dates).all():raise ValueError('invalid BP dates')
                    values=pd.to_numeric(f.set_index('date').pbMRQ.replace('',np.nan),errors='raise')
                    lag=values.reindex(all_dates).shift(1).reindex(dates)
                    panels['BP'][symbol]=(1/lag.where(lag.gt(0))).where(members[symbol])
                bars=pd.read_parquet(canonical/(symbol+'.parquet')).set_index('datetime').reindex(all_dates)
                bars['is_suspended']=bars.is_suspended.fillna(True).astype(bool)
                cap=circulating_cap(bars)
                panels['log_size'][symbol]=np.log(cap.where(cap.gt(0))).reindex(dates)
                panels['ILLIQUIDITY_20'][symbol]=illiquidity(bars).reindex(dates).where(members[symbol])
                e=events.loc[events.code.eq(code),['snapshot_date','industry']].copy()
                e['industry']=e.industry.astype('string').str.extract(r'^([A-S]\d{2})',expand=False)
                industry[symbol]=asof_events(e,dates,'snapshot_date',['industry'],max_age=62).industry
                if i%25==0 or i==len(symbols)-1:
                    state.update(stage='exposures',stocks_completed=i+1);write(output/'status.json',state)
                    write(output/'requests.json',source.manifest)
                    print(f'EXPOSURES {i+1}/{len(symbols)}',flush=True)
            write(output/'requests.json',source.manifest)
        for n,p in panels.items():p.to_parquet(output/(n+'.parquet'))
        industry.to_parquet(output/'industry.parquet');fiscal.to_parquet(output/'fiscal_period.parquet')
        pd.DataFrame(audits).to_csv(output/'stock_audit.csv',index=False)
        coverage=[]
        for year in sorted(dates.year.unique()):
            m=members.loc[str(year)];den=int(m.to_numpy().sum())
            for n,p in {**panels,'industry':industry}.items():
                count=int((p.loc[str(year)].notna()&m).to_numpy().sum())
                coverage.append({'year':int(year),'field':n,'available_cells':count,'member_cells':den,'coverage':count/den})
        pd.DataFrame(coverage).to_csv(output/'coverage.csv',index=False)
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        if any(hashlib.sha256((root/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):raise ValueError('source changed during collection')
        write(output/'verification.json',{'status':'PASS','baseline_identity':identity,'cashflow_requests':done,
              'members':len(symbols),'rows_returned':sum(a['records'] for a in audits),
              'rows_after_end_excluded':sum(a['publication_after_end'] for a in audits),
              'no_2021_plus_requests':True,'protocol_sha256':PROTOCOL_SHA256,'research_status':'NOT_EVALUATED',
              'revision_status':'vendor_revision_unknown','BP_lag':'one exchange day','industry_max_age_days':62})
        write(output/'artifact_hashes.json',{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts and p.name!='status.json'})
        state.update(status='PASS',stage='complete',stocks_completed=len(symbols),requests_completed=done)
        write(output/'status.json',state);print('PASS '+str(output),flush=True)
        return output
    except BaseException as exc:
        state.update(status='FAIL',error=str(exc));write(output/'status.json',state)
        (output/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
