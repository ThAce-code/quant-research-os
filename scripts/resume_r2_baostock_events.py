"""Resume the user's clean handoff checkpoint without replaying finished requests."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
from filelock import FileLock

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'experiments/r2/r2_baostock_event_bulk_v1'


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p,value):
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(p)


def recovery_allowed(failure,index,history,policy):
    if (failure.get('status')!='FAIL' or failure.get('data')!=[] or failure.get('fields')!=[]
        or len(history)>=policy['max_session_refreshes']
        or failure.get('request',{}).get('method') not in policy['read_only_methods']):return False
    same=[r for r in history if r['query_index']==index]
    if failure.get('code')==policy['recoverable_code']:
        return len(same)<policy['max_refreshes_per_failed_query']
    if failure.get('code')==policy['recoverable_receive_code']:
        return (len(same)<policy['max_receive_refreshes_per_query']
                and sum(r.get('code')==policy['recoverable_receive_code'] for r in history)<policy['max_receive_refreshes'])
    return False


def archive_failure(run,state,index,policy,history):
    """Keep the explicit rejection and prior manifest; free only that failed slot."""
    path=run/'responses'/f'{index:04d}.json';failure=read(path)
    if not recovery_allowed(failure,index,history,policy):raise ValueError('Failure is not eligible for session recovery')
    folder=run/'session_recoveries'/f'{len(history)+1:04d}';folder.mkdir(parents=True,exist_ok=False)
    for name in ['status.json','login.json','artifact_hashes.json']:
        if (run/name).exists():
            target='prior_manifest.json' if name=='artifact_hashes.json' else name
            (folder/target).write_bytes((run/name).read_bytes())
    event={'query_index':index,'at':datetime.now(timezone.utc).isoformat(),'failed_response_sha256':sha(path),
           'request':failure['request'],'code':failure['code'],'completed_before':state['completed']}
    write(folder/'recovery.json',event)
    path.rename(folder/'failed_response.json')
    return event


def main():
    policy=read(ROOT/'configs/r2/baostock_session_recovery.json')
    env=dict(os.environ);env['PYTHONPATH']=str(ROOT/'src');env['PYTHONIOENCODING']='utf-8'
    with FileLock(RUN/'.resume.lock',timeout=0):
        while True:
            refreshed=False;cooldown=policy['cooldown_seconds']
            with FileLock(ROOT/'data/raw/baostock/.session.lock',timeout=0):
                state=read(RUN/'status.json')
                if state['status']=='PASS':print('Collection complete. No further request sent.');return 0
                if state['status'] not in ['PAUSED_USER_HANDOFF','STOPPED']:
                    raise ValueError('No verified paused/stopped checkpoint; preserve state for inspection')
                for name,expected in read(RUN/'bindings.json').items():assert sha(ROOT/name)==expected,name
                jobs=read(RUN/'plan.json');files=sorted((RUN/'responses').glob('*.json'))
                records=[read(p) for p in files];n=state['completed']
                assert len(files) in [n,n+1]
                for i,(path,record) in enumerate(zip(files,records)):
                    assert path.name==f'{i:04d}.json' and record['request']==jobs[i]
                    if i<n:assert record['status']=='PASS'
                assert sum(len(r['data']) for r in records[:n])==state['rows']
                if state['status']=='STOPPED':
                    for name,expected in read(RUN/'artifact_hashes.json').items():assert sha(RUN/name)==expected,name
                else:
                    for name,expected in read(RUN/'handoff.json')['response_hashes'].items():assert sha(RUN/'responses'/name)==expected,name
                history=[read(p) for p in sorted((RUN/'session_recoveries').glob('*/recovery.json'))]
                if state['status']=='STOPPED':
                    if len(records)!=n+1 or not recovery_allowed(records[-1],n,history,policy):
                        print('Stopped: error is not recoverable or session budget reached. No automatic retry.',flush=True)
                        return 1
                print(f"Validated {n} completed requests; {state['planned_queries']-n} remain.",flush=True)
                if '--check' in sys.argv:
                    print('Check only: no state changed and no request sent; checkpoint is eligible.');return 0
                if not (RUN/'session_recovery_policy.json').exists():
                    write(RUN/'session_recovery_policy.json',policy)
                    (RUN/'session_recovery_source.py').write_bytes(Path(__file__).read_bytes())
                else:
                    assert read(RUN/'session_recovery_policy.json')==policy
                    assert sha(RUN/'session_recovery_source.py')==sha(Path(__file__))
                if state['status']=='STOPPED':
                    archive_failure(RUN,state,n,policy,history);refreshed=True
                    if records[-1]['code']==policy['recoverable_receive_code']:
                        previous=sum(r['query_index']==n for r in history)
                        cooldown=policy['receive_backoff_seconds'][previous]
                    print(f"SESSION_RECOVERY {len(history)+1}/{policy['max_session_refreshes']}: query {n+1}; fresh login after cooldown.",flush=True)
                state.update(status='RUNNING',resumed_by_user_at=datetime.now(timezone.utc).isoformat())
                state.pop('error',None);state.pop('finished_at',None);write(RUN/'status.json',state)
            if refreshed:time.sleep(cooldown)
            process=subprocess.run([sys.executable,'-u',str(ROOT/'scripts/collect_r2_baostock_events.py')],cwd=ROOT,env=env)
            if process.returncode==0:return 0
            # Only bounded, empty, explicitly classified read-only failures pass.


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
