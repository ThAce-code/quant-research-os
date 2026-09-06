"""Complete historical fields without changing any failed research hypothesis."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import traceback
import numpy as np
import pandas as pd
from filelock import FileLock
from ..baostock_data import BaoStockCache
from ..factors.engine import strict_write_json as write, verify_baseline
from ..factors.provenance import verify_data_identity
from .supplementary import request_plan
from .quarterly import clean_events, daily_panel
from .industry import industry_key,financial_key


def run(root):
    restriction=root/'data/baostock_access_restriction.json'
    if restriction.exists() and json.loads(restriction.read_text(encoding='utf-8')).get('active'):
        raise RuntimeError('BaoStock explicitly denied access (10001011); wait for provider restoration before network collection')
    with FileLock(str(root/'data/m2_history_completion.lock'),timeout=0):return _run(root)


def _run(root):
    c=json.loads((root/'configs/factors/m2_history_completion.json').read_text(encoding='utf-8'))
    output=root/'experiments/m2'/c['name']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state={'status':'RUNNING','run_id':output.name};write(output/'status.json',state);write(output/'config.json',c)
    print('HISTORY '+str(output),flush=True)
    names=['src/quant_research/m2/history_completion.py','src/quant_research/m2/quarterly.py',
           'src/quant_research/m2/core.py','src/quant_research/m2/supplementary.py',
           'src/quant_research/baostock_data.py','src/quant_research/m2/industry.py','configs/factors/m2_history_completion.json']
    hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
    for n in names:
        dest=output/'source'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/n,dest)
    write(output/'source_hashes.json',hashes)
    try:
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        identity=verify_data_identity(root,baseline,frozen)
        canonical=root/'data/canonical'/baseline['name']
        intervals=pd.read_parquet(canonical/'membership.parquet')
        plan=request_plan(intervals,c);plan.to_csv(output/'request_plan.csv',index=False)
        dates=pd.DatetimeIndex(pd.read_parquet(canonical/'calendar.parquet').datetime)
        dates=dates[(dates>=c['data_period'][0])&(dates<=c['data_period'][1])]
        symbols=sorted(plan.symbol.unique());member=pd.DataFrame(False,index=dates,columns=symbols)
        for r in intervals.itertuples():
            if r.instrument in member:member.loc[r.start:r.end,r.instrument]=True
        member.to_parquet(output/'membership.parquet')
        panels={f:pd.DataFrame(np.nan,index=dates,columns=symbols) for fs in c['fields'].values() for f in fs}
        events=output/'events';events.mkdir();audits=[];done=0;total=len(plan)*len(c['fields'])
        with BaoStockCache(root/'data/raw/baostock') as source:
            for symbol,g in plan.groupby('symbol'):
                for method,fields in c['fields'].items():
                    frames=[]
                    for r in g.itertuples():
                        frame=source.query(method,allow_empty=True,code=r.code,year=int(r.year),quarter=int(r.quarter))
                        expected=pd.Period(year=r.year,quarter=r.quarter,freq='Q').end_time.normalize()
                        if len(frame) and not pd.to_datetime(frame.statDate,errors='coerce').eq(expected).all():raise ValueError('wrong fiscal quarter')
                        frames.append(frame);done+=1
                        if done%200==0:
                            state.update(requests_completed=done,requests_total=total);write(output/'status.json',state)
                            print(f'HISTORY {done}/{total}',flush=True)
                    raw=pd.concat(frames,ignore_index=True)
                    later=pd.to_datetime(raw.pubDate,errors='coerce').gt(c['data_period'][1]) if len(raw) else pd.Series(False,index=raw.index)
                    clean,bad=clean_events(raw.loc[~later],g.code.iloc[0],fields,c['data_period'][1])
                    if len(bad):
                        bad.to_csv(output/'quarantine.csv',index=False);raise ValueError('invalid in-window financial events')
                    clean.to_parquet(events/f'{symbol}_{method}.parquet',index=False)
                    joined=daily_panel(clean,dates,fields,400,550)
                    for field in fields:panels[field][symbol]=pd.to_numeric(joined[field]).where(member[symbol])
                    audits.append({'symbol':symbol,'method':method,'requests':len(g),'rows':len(raw),'accepted':len(clean),'later_publications':int(later.sum())})
                if len(audits)%50==0:write(output/'requests.json',source.manifest)
            write(output/'requests.json',source.manifest)
        rows=[]
        for field,panel in panels.items():
            panel.to_parquet(output/f'{field}.parquet')
            for year in sorted(dates.year.unique()):
                m=member.loc[str(year)];n=int((panel.loc[str(year)].notna()&m).to_numpy().sum());den=int(m.to_numpy().sum())
                rows.append({'field':field,'year':int(year),'available':n,'eligible':den,'coverage':n/den})
        pd.DataFrame(rows).to_csv(output/'coverage.csv',index=False);pd.DataFrame(audits).to_csv(output/'stock_audit.csv',index=False)
        assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        write(output/'verification.json',{'status':'PASS','requests':done,'symbols':len(symbols),'baseline_identity':identity,
              'no_2021_plus_access':True,'no_factor_retest':True,'rows':sum(a['rows'] for a in audits),'accepted':sum(a['accepted'] for a in audits),
              'later_publications':sum(a['later_publications'] for a in audits),'pit_level':c['pit_level']})
        write(output/'artifact_hashes.json',{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*')
              if p.is_file() and 'source' not in p.relative_to(output).parts and p.name!='status.json'})
        state.update(status='PASS',requests_completed=done,requests_total=total);write(output/'status.json',state)
        print('PASS '+str(output),flush=True)
    except BaseException as e:
        if '10001011' in str(e):
            write(root/'data/baostock_access_restriction.json',{'active':True,'code':'10001011','source_run':output.name,
                  'reason':str(e),'observed_at':datetime.now(timezone.utc).isoformat(),
                  'resume_condition':'Provider restriction lifted or missing source data supplied; do not change IP/account to bypass denial'})
        state.update(status='FAIL',error=str(e));write(output/'status.json',state)
        (output/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
