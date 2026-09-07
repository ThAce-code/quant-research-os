"""Resume the user's clean handoff checkpoint without replaying finished requests."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
from filelock import FileLock

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'experiments/r2/r2_baostock_event_bulk_v1'


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    with FileLock(ROOT/'data/raw/baostock/.session.lock',timeout=0):
        state=read(RUN/'status.json')
        if state['status']=='PASS':
            print('Already complete. No request sent.');return 0
        if state['status']!='PAUSED_USER_HANDOFF':
            raise ValueError('Expected clean user handoff. Preserve current state and ask for inspection; no retry sent.')
        for name,expected in read(RUN/'bindings.json').items():assert sha(ROOT/name)==expected,name
        handoff=read(RUN/'handoff.json')
        files=sorted((RUN/'responses').glob('*.json'))
        assert len(files)==state['completed']==handoff['completed']
        for i,path in enumerate(files):
            assert path.name==f'{i:04d}.json'
            assert sha(path)==handoff['response_hashes'][path.name]
            assert read(path)['status']=='PASS'
        print(f"Validated {state['completed']} completed requests; {state['planned_queries']-state['completed']} remain.",flush=True)
        if '--check' in sys.argv:
            print('Check only: no state changed and no request sent.');return 0
        state.update(status='RUNNING',resumed_by_user_at=datetime.now(timezone.utc).isoformat())
        tmp=RUN/'status.tmp';tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(RUN/'status.json')
    env=dict(os.environ);env['PYTHONPATH']=str(ROOT/'src');env['PYTHONIOENCODING']='utf-8'
    return subprocess.run([sys.executable,'-u',str(ROOT/'scripts/collect_r2_baostock_events.py')],cwd=ROOT,env=env).returncode


if __name__=='__main__':raise SystemExit(main())
