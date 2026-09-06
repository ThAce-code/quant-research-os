import hashlib
from pathlib import Path
import pytest

from quant_research.factors.provenance import verify_data_identity, freeze_sources, verify_sources
from quant_research.factors.expressions import Expression


def test_declared_lookback_includes_return_price_lag():
    assert Expression('Std(returns,20)').lookback == 20


def test_resealed_manifest_cannot_replace_frozen_baseline_identity(tmp_path):
    path=tmp_path/'data/canonical/demo/manifest.json';path.parent.mkdir(parents=True)
    path.write_text('{"snapshot":1}')
    frozen={'original_provenance':{'source_manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
    verify_data_identity(tmp_path,{'name':'demo'},frozen)
    path.write_text('{"snapshot":2,"self_seal":"new"}')
    with pytest.raises(ValueError,match='frozen'):
        verify_data_identity(tmp_path,{'name':'demo'},frozen)


def test_source_copy_precedes_work_and_detects_midrun_changes(tmp_path):
    source=tmp_path/'src/quant_research/factors/a.py';source.parent.mkdir(parents=True)
    source.write_text('x=1\n')
    for name in ['scripts/run_factors.py','run-factors.ps1']:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('command')
    output=tmp_path/'run'
    hashes=freeze_sources(tmp_path,output)
    assert (output/'source/src/quant_research/factors/a.py').read_text()=='x=1\n'
    verify_sources(tmp_path,hashes)
    source.write_text('x=2\n')
    with pytest.raises(ValueError,match='source'):
        verify_sources(tmp_path,hashes)
