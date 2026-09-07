import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_research.factors.data import FactorData
from quant_research.factors.expressions import Expression
from quant_research.m3.data_contract import (CONTRACT_PATH,attach_fields,digest,
                                            freeze_binding,read_contract,validate_contract)

ROOT=Path(__file__).resolve().parents[1]


def fixture(tmp_path):
    contract=json.loads((ROOT/CONTRACT_PATH).read_text())
    folder=tmp_path/'panels';folder.mkdir()
    calendar=pd.bdate_range('2015-01-01',periods=6)
    panel=pd.DataFrame({'A':[1.,np.nan,2.,np.nan]},index=calendar[1:5])
    path=folder/'pit.parquet';panel.to_parquet(path)
    manifest=folder/'manifest.json';manifest.write_text(json.dumps({'pit.parquet':digest(path)}))
    verified=folder/'verification.json';verified.write_text('{"status":"PASS"}')
    canonical=tmp_path/'canonical.json';canonical.write_text('{}')
    def entry(p):return {'path':p.relative_to(tmp_path).as_posix(),'sha256':digest(p)}
    contract['canonical_manifest']=entry(canonical)
    for field in contract['fields'].values():
        if field['kind']!='pit_panel':continue
        field.update(panel=entry(path),manifest=entry(manifest),verification=entry(verified),
                     additional_evidence=[],period=[str(panel.index[0].date()),str(panel.index[-1].date())])
    file=tmp_path/CONTRACT_PATH;file.parent.mkdir(parents=True);file.write_text(json.dumps(contract))
    member=pd.DataFrame(True,index=calendar,columns=['A'])
    market=FactorData({'close':member.astype(float)*10},member,member,member.A.astype(float))
    return contract,market,panel


def test_pit_requires_binding_and_old_daily_batch_stays_compatible(tmp_path):
    assert read_contract(tmp_path,None,{'close'}) is None
    with pytest.raises(ValueError,match='frozen'):read_contract(tmp_path,None,{'pit_roe'})
    with pytest.raises(ValueError,match='unsupported'):read_contract(tmp_path,None,{'news_sentiment'})


def test_actual_panel_identity_reindex_preserves_missing_values_and_market(tmp_path):
    contract,market,panel=fixture(tmp_path)
    before=market.fields['close'].copy()
    binding=freeze_binding(tmp_path,{'pit_roe','close'})
    loaded=read_contract(tmp_path,binding,{'pit_roe','close'})
    out,report=attach_fields(tmp_path,market,loaded,{'pit_roe','close'})
    pd.testing.assert_frame_equal(out.fields['pit_roe'],panel.reindex_like(market.membership))
    pd.testing.assert_frame_equal(out.fields['close'],before)
    assert 'pit_roe' not in market.fields and out.fields['pit_roe'].isna().sum().sum()==4
    assert report['fields']['pit_roe']['eligible_finite_cells']==2
    result=Expression('pit_roe / close').evaluate(out.fields)
    assert result.A.dropna().tolist()==[.1,.2]


def test_changed_panel_rejected_before_parquet_is_read(tmp_path,monkeypatch):
    contract,market,_=fixture(tmp_path)
    path=tmp_path/contract['fields']['pit_roe']['panel']['path'];path.write_bytes(b'changed')
    monkeypatch.setattr(pd,'read_parquet',lambda *a,**k:pytest.fail('unverified panel read'))
    with pytest.raises(ValueError,match='identity'):attach_fields(tmp_path,market,contract,{'pit_roe'})


def test_contract_change_and_protected_period_fail_before_data(tmp_path):
    contract,_,_=fixture(tmp_path)
    binding=freeze_binding(tmp_path,{'pit_roe'})
    path=tmp_path/CONTRACT_PATH;path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError,match='changed'):read_contract(tmp_path,binding,{'pit_roe'})
    bad=copy.deepcopy(contract);bad['fields']['pit_roe']['period'][1]='2021-01-01'
    with pytest.raises(ValueError,match='protected'):validate_contract(bad)


def test_wrong_source_membership_and_failed_verification_rejected(tmp_path):
    contract,market,_=fixture(tmp_path)
    meta=contract['fields']['pit_roe'];manifest=tmp_path/meta['manifest']['path']
    manifest.write_text('{}');meta['manifest']['sha256']=digest(manifest)
    with pytest.raises(ValueError,match='declared source'):attach_fields(tmp_path,market,contract,{'pit_roe'})


def test_failed_verification_or_late_mutation_blocks_success(tmp_path):
    from quant_research.m3.data_contract import verify_input_identity
    contract,market,_=fixture(tmp_path)
    attach_fields(tmp_path,market,contract,{'pit_roe'})
    meta=contract['fields']['pit_roe'];path=tmp_path/meta['verification']['path']
    path.write_text('{"status":"FAIL"}')
    with pytest.raises(ValueError,match='changed during'):verify_input_identity(tmp_path,contract,{'pit_roe'})
    meta['verification']['sha256']=digest(path)
    with pytest.raises(ValueError,match='independent verification'):attach_fields(tmp_path,market,contract,{'pit_roe'})


def test_pipeline_pit_preflight_precedes_market_loading(tmp_path,monkeypatch):
    from quant_research.m3 import pipeline
    from quant_research.m3.pipeline import sha
    from test_m3_campaign import candidate
    h={**candidate('pit_roe','PIT_PROBE'),'input_fields':{'pit_roe':'Published ROE ratio'}}
    batch=json.loads((ROOT/'configs/m3/paper_pilot.json').read_text());batch['candidates']=[h]
    for name in ['configs/experiments/baostock_alpha158.json','configs/factors/m2_family_screen.json']:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
    batch['screen_protocol_sha256']=sha(tmp_path/'configs/factors/m2_family_screen.json')
    path=tmp_path/'batch.json';path.write_text(json.dumps(batch))
    monkeypatch.setattr(pipeline,'_run',lambda *a:pytest.fail('unbound PIT batch reached execution'))
    with pytest.raises(ValueError,match='frozen data contract'):pipeline.run(tmp_path,path)
