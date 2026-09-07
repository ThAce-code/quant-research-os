"""One-time, offline repair of the observed Windows-lock manifest failure."""
from pathlib import Path
import json
from filelock import FileLock
from collect_r2_baostock_events import artifact_hashes,read,sha,write

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'experiments/r2/r2_baostock_event_bulk_v1'


def main():
    with FileLock(RUN/'.resume.lock',timeout=0),FileLock(ROOT/'data/raw/baostock/.session.lock',timeout=0):
        state=read(RUN/'status.json');jobs=read(RUN/'plan.json');n=state['completed']
        assert state['status']=='STOPPED' and n==367 and state['rows']==326
        files=sorted((RUN/'responses').glob('*.json'));assert len(files)==n+1
        records=[read(p) for p in files]
        for i,(p,r) in enumerate(zip(files,records)):
            assert p.name==f'{i:04d}.json' and r['request']==jobs[i]
            if i<n:
                assert r['status']=='PASS' and r['code']=='0'
                assert all(len(v)==len(r['fields']) for v in r['data'])
                assert all(dict(zip(r['fields'],v))['code']==jobs[i]['params']['code'] for v in r['data'])
        assert sum(len(r['data']) for r in records[:n])==326
        assert records[-1]['status']=='FAIL' and records[-1]['code']=='10002007' and records[-1]['data']==[]
        stale=read(RUN/'artifact_hashes.json');resolved={};anchored=[]
        for name,expected in stale.items():
            path=RUN/name
            if path.exists() and sha(path)==expected:anchored.append(name);continue
            alternatives=list((RUN/'session_recoveries').glob('*/'+('failed_response.json' if 'responses' in name else Path(name).name)))
            matches=[p for p in alternatives if sha(p)==expected]
            assert matches, f'Unexplained old-manifest mismatch: {name}'
            resolved[name]=str(matches[0].relative_to(RUN))
        previous=read(RUN/'bindings.json')
        for name,expected in previous.items():
            assert sha(ROOT/name)==expected or (name==str(Path('scripts/collect_r2_baostock_events.py')) and sha(RUN/'collector_source.py')==expected),name
        repair=RUN/'repairs/20260907_transport_lock_v1';repair.mkdir(parents=True,exist_ok=False)
        for name in ['bindings.json','artifact_hashes.json','status.json','login.json','collector_source.py','session_recovery_policy.json','session_recovery_source.py']:
            (repair/('before_'+name)).write_bytes((RUN/name).read_bytes())
        (repair/'failed_response_0367.json').write_bytes(files[-1].read_bytes())
        before={p.name:sha(p) for p in files}
        bindings={name:sha(ROOT/name) for name in previous}
        write(RUN/'bindings.json',bindings)
        (RUN/'collector_current_source.py').write_bytes((ROOT/'scripts/collect_r2_baostock_events.py').read_bytes())
        (RUN/'session_recovery_source.py').write_bytes((ROOT/'scripts/resume_r2_baostock_events.py').read_bytes())
        (RUN/'session_recovery_policy.json').write_bytes((ROOT/'configs/r2/baostock_session_recovery.json').read_bytes())
        result={'status':'PASS_OFFLINE_MANIFEST_REPAIR','completed':367,'rows':326,'remaining':323,
            'cause':'Windows locked .resume.lock was included in hashing; stale manifest persisted',
            'stale_entries_resolved_to_archives':resolved,'unchanged_old_manifest_entries':len(anchored),
            'new_successful_records_first_sealed':268,
            'response_files_byte_unchanged':all(sha(p)==before[p.name] for p in files),
            'previous_bindings':previous,'current_bindings':bindings,'new_network_requests':0,
            'limits':'New records have structural and request/count checks, not retrospectively available hashes. No provider replay or research admission.',
            'repair_script_sha256':sha(Path(__file__))}
        write(repair/'repair.json',result)
        (repair/'repair_source.py').write_bytes(Path(__file__).read_bytes())
        write(RUN/'artifact_hashes.json',artifact_hashes(RUN))
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
