import importlib.util
from pathlib import Path
import pytest
from filelock import FileLock

path=Path(__file__).resolve().parents[1]/'scripts/collect_r2_baostock_events.py'
spec=importlib.util.spec_from_file_location('collector_lock_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_live_windows_lock_is_excluded_but_responses_are_hashed(tmp_path):
    raw=tmp_path/'response.json';raw.write_bytes(b'{"data":[]}')
    with FileLock(tmp_path/'.resume.lock',timeout=0):
        result=module.artifact_hashes(tmp_path)
    assert result=={'response.json':module.sha(raw)}


def test_raw_file_failure_does_not_mask_original_network_error(tmp_path,monkeypatch):
    def denied(_):raise PermissionError('unreadable response.json')
    monkeypatch.setattr(module,'artifact_hashes',denied)
    state={'status':'STOPPED','error':'network failure'}
    with pytest.raises(RuntimeError,match='network failure'):
        try:raise RuntimeError('network failure')
        finally:module.seal_archive(tmp_path,state)
    assert module.read(tmp_path/'status.json')['error']=='network failure'
    assert 'unreadable response.json' in module.read(tmp_path/'status.json')['manifest_error']
    assert not (tmp_path/'artifact_hashes.json').exists()


def test_successful_collection_cannot_hide_manifest_failure(tmp_path,monkeypatch):
    def denied(_):raise PermissionError('raw file')
    monkeypatch.setattr(module,'artifact_hashes',denied)
    with pytest.raises(PermissionError):module.seal_archive(tmp_path,{'status':'PASS'})
    assert module.read(tmp_path/'status.json')['status']=='STOPPED'
