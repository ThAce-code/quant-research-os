import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('resume_r2',ROOT/'scripts/resume_r2_baostock_events.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
POLICY=json.loads((ROOT/'configs/r2/baostock_session_recovery.json').read_text())


def failure(code='10001001'):
    return {'status':'FAIL','code':code,'fields':[],'data':[],
            'request':{'method':'query_performance_express_report','params':{'code':'sh.600252'}}}


def test_only_explicit_empty_not_logged_in_is_recoverable():
    assert module.recovery_allowed(failure(),99,[],POLICY)
    for code in ['10001011','10002007','unknown']:
        assert not module.recovery_allowed(failure(code),99,[],POLICY)
    assert not module.recovery_allowed({**failure(),'data':[['partial']]},99,[],POLICY)
    assert not module.recovery_allowed({**failure(),'status':'RESERVED'},99,[],POLICY)


def test_repeated_same_query_and_total_budget_stop():
    assert not module.recovery_allowed(failure(),99,[{'query_index':99}],POLICY)
    assert not module.recovery_allowed(failure(),99,[{'query_index':i} for i in range(60)],POLICY)
    assert module.recovery_allowed(failure(),100,[{'query_index':99}],POLICY)


def test_failure_archive_preserves_success_and_original_rejection(tmp_path):
    (tmp_path/'responses').mkdir()
    good=tmp_path/'responses/0098.json';good.write_bytes(b'{"status":"PASS","data":[["keep"]]}')
    bad=tmp_path/'responses/0099.json';module.write(bad,failure())
    module.write(tmp_path/'status.json',{'status':'STOPPED','completed':99})
    module.write(tmp_path/'artifact_hashes.json',{'responses/0099.json':module.sha(bad)})
    before=good.read_bytes();failed_bytes=bad.read_bytes()
    event=module.archive_failure(tmp_path,{'completed':99},99,POLICY,[])
    assert good.read_bytes()==before and not bad.exists()
    archive=tmp_path/'session_recoveries/0001'
    assert (archive/'failed_response.json').read_bytes()==failed_bytes
    assert module.sha(archive/'failed_response.json')==event['failed_response_sha256']
    assert module.read(archive/'prior_manifest.json')['responses/0099.json']==event['failed_response_sha256']


def test_resume_reauthenticates_only_the_failed_slot(monkeypatch,tmp_path):
    from types import SimpleNamespace
    run=tmp_path/'run';(run/'responses').mkdir(parents=True)
    (tmp_path/'data/raw/baostock').mkdir(parents=True)
    (tmp_path/'configs/r2').mkdir(parents=True)
    module.write(tmp_path/'configs/r2/baostock_session_recovery.json',POLICY)
    jobs=[{'method':'query_forecast_report','params':{'code':'sh.600252'}},failure()['request']]
    good=run/'responses/0000.json';module.write(good,{'status':'PASS','request':jobs[0],'data':[['kept']]})
    module.write(run/'responses/0001.json',failure())
    module.write(run/'plan.json',jobs);module.write(run/'bindings.json',{})
    module.write(run/'status.json',{'status':'STOPPED','completed':1,'rows':1,'planned_queries':2})
    module.write(run/'artifact_hashes.json',{str(p.relative_to(run)):module.sha(p) for p in run.rglob('*.json')})
    original=good.read_bytes();calls=[]
    monkeypatch.setattr(module,'ROOT',tmp_path);monkeypatch.setattr(module,'RUN',run)
    monkeypatch.setattr(module.sys,'argv',['resume.py']);monkeypatch.setattr(module.time,'sleep',lambda _:None)
    def collector(args,**kwargs):
        calls.append(args)
        assert good.read_bytes()==original and not (run/'responses/0001.json').exists()
        assert module.read(run/'status.json')['status']=='RUNNING'
        module.write(run/'responses/0001.json',{'status':'PASS','request':jobs[1],'data':[]})
        module.write(run/'status.json',{'status':'PASS','completed':2,'rows':1,'planned_queries':2})
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess,'run',collector)
    assert module.main()==0 and len(calls)==1
    assert module.read(run/'session_recoveries/0001/failed_response.json')['code']=='10001001'
    assert good.read_bytes()==original
