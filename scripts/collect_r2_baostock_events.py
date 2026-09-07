"""Serial, checkpointed acquisition for the explicitly authorized R2 BaoStock batch."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import socket
import sys
import time
import pandas as pd
from quant_research.baostock_data import DeadlineSocket, session_lock

ROOT = Path(__file__).resolve().parents[1]


def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))


def write(p, value):
    temporary=p.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(p)


def artifact_hashes(out):
    """Runtime locks are not evidence and may be unreadable while held on Windows."""
    return {str(p.relative_to(out)):sha(p) for p in out.rglob('*')
            if p.is_file() and p.name!='artifact_hashes.json' and not p.name.endswith('.lock')}


def seal_archive(out,state):
    original_error=sys.exc_info()[0] is not None
    try:write(out/'artifact_hashes.json',artifact_hashes(out))
    except Exception as exc:
        state.update(status='STOPPED',manifest_error=repr(exc));write(out/'status.json',state)
        if not original_error:raise
        print(f'ARCHIVE_ERROR (original collection failure preserved): {exc!r}',file=sys.stderr,flush=True)


def plan(config):
    members=pd.read_parquet(ROOT/config['membership']);codes=set();unions={}
    for start,end in config['membership_windows']:
        subset=set(members.loc[(pd.to_datetime(members.start)<=end)&(pd.to_datetime(members.end)>=start),'instrument'])
        converted={s[:2].lower()+'.'+s[2:] for s in subset}
        unions[start[:4]]=sorted(converted);codes.update(converted)
    ordered=list(dict.fromkeys(config['audit_sentinels']+sorted(codes)))
    jobs=[{'method':method,'params':{'code':code,'start_date':config['start_date'],'end_date':config['end_date']}}
          for code in ordered for method in config['methods']]
    assert len(jobs)<=config['max_data_queries']
    return jobs,unions


def main():
    import baostock as bs
    from baostock.common import context,contants
    config_path=ROOT/'configs/r2/baostock_event_bulk.json';config=read(config_path)
    jobs,unions=plan(config)
    out=ROOT/'experiments/r2'/config['name'];out.mkdir(parents=True,exist_ok=True)
    (out/'responses').mkdir(exist_ok=True)
    bindings={str(p.relative_to(ROOT)):sha(p) for p in [config_path,Path(__file__),ROOT/config['membership']]}
    if (out/'bindings.json').exists():assert read(out/'bindings.json')==bindings,'Frozen source changed'
    else:
        write(out/'bindings.json',bindings);write(out/'plan.json',jobs);write(out/'member_unions.json',unions)
        (out/'collector_source.py').write_bytes(Path(__file__).read_bytes())
        (out/'config.json').write_bytes(config_path.read_bytes())
    state=read(out/'status.json') if (out/'status.json').exists() else {'status':'PLANNED','planned_queries':len(jobs),'completed':0,'nonempty':0,'rows':0,'started_at':now(),'returns_loaded':False}
    if state['status']=='PASS':print(json.dumps(state));return
    if state['status'] not in ['PLANNED','RUNNING']:raise ValueError('Stopped attempt requires explicit failure resolution; no automatic retry')
    for i,job in enumerate(jobs):
        path=out/'responses'/f'{i:04d}.json'
        if path.exists():
            saved=read(path)
            if saved['status']!='PASS':raise ValueError('Uncertain/failed checkpoint is not replayed')
            assert saved['request']==job
    state.update(status='RUNNING');write(out/'status.json',state)
    with session_lock(ROOT/'data/raw/baostock'):
        try:
            socket.setdefaulttimeout(config['request_timeout_seconds'])
            login=bs.login();write(out/'login.json',{'at':now(),'code':login.error_code,'message':login.error_msg})
            if login.error_code!='0':raise RuntimeError(f'login {login.error_code}: {login.error_msg}')
            context.default_socket=DeadlineSocket(context.default_socket,config['request_timeout_seconds'])
            for i,job in enumerate(jobs):
                path=out/'responses'/f'{i:04d}.json'
                if path.exists():continue
                record={'status':'RESERVED','request':job,'started_at':now()};write(path,record)
                response=getattr(bs,job['method'])(**job['params'])
                record.update(code=response.error_code,message=response.error_msg,fields=response.fields,
                              data=response.data,finished_at=now())
                if response.error_code!='0':
                    record['status']='FAIL';write(path,record)
                    raise RuntimeError(f'{response.error_code}: {response.error_msg}; {job}')
                if len(response.data)==int(contants.BAOSTOCK_PER_PAGE_COUNT):
                    record['status']='FULL_PAGE_REQUIRES_REVIEW';write(path,record)
                    raise RuntimeError('Pagination required; frozen one-page budget reached')
                if any(len(row)!=len(response.fields) for row in response.data):raise ValueError('Field/row width mismatch')
                record['status']='PASS';write(path,record)
                state.update(completed=i+1,nonempty=state['nonempty']+bool(response.data),rows=state['rows']+len(response.data),updated_at=now())
                write(out/'status.json',state)
                print(f"BAOSTOCK_BULK {i+1}/{len(jobs)} {job['params']['code']} {job['method']} rows={len(response.data)} total={state['rows']}",flush=True)
                time.sleep(config['minimum_request_spacing_seconds'])
            state.update(status='PASS',finished_at=now());write(out/'status.json',state)
        except BaseException as exc:
            state.update(status='STOPPED',error=repr(exc),finished_at=now());write(out/'status.json',state);raise
        finally:
            if getattr(context,'default_socket',None) is not None:context.default_socket.close()
            seal_archive(out,state)
    print(json.dumps(state,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
