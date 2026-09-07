import json
from pathlib import Path

import pytest

from quant_research.m3.campaign import CampaignLedger
from quant_research.m3.controller import prepare_evaluation, import_candidates, attach_screen
from quant_research.m3.pipeline import sha
from quant_research.m3.candidates import ResearchHypothesis
from quant_research.factors.registry import FactorRegistry
from dataclasses import asdict
from quant_research.m3.trajectory import retrieve, refine
from test_m3_campaign import spec, candidate


def ledger(tmp_path,**changes):
    obj=CampaignLedger(tmp_path/'ledger.sqlite');obj.create(spec(**changes));return obj


def evidence():
    return {'scope':'research_only','protected_accessed':False,'period':['2015-01-01','2016-12-31'],
            'decision':'IC_SCREEN_REJECT','primary':{'rank_ic':-.02}}


def test_batch_reservation_is_atomic_on_late_error(tmp_path):
    obj=ledger(tmp_path,max_evaluations=1)
    first=obj.propose('study',0,candidate())['proposal_id']
    second=obj.propose('study',0,candidate('close/open','SECOND'))['proposal_id']
    with pytest.raises(ValueError,match='budget'):obj.reserve_evaluations([first,second])
    assert not obj.snapshot('study')['evaluations']
    obj.reserve_evaluation(first)
    assert len(obj.snapshot('study')['evaluations'])==1


def test_attachment_replay_is_idempotent_but_replacement_is_not(tmp_path):
    obj=ledger(tmp_path);proposal=obj.propose('study',0,candidate())['proposal_id']
    obj.reserve_evaluation(proposal);obj.finish_evaluation(proposal,'run',evidence())
    restarted=CampaignLedger(obj.path);restarted.finish_evaluation(proposal,'run',evidence())
    with pytest.raises(ValueError,match='already complete'):
        restarted.finish_evaluation(proposal,'run',{**evidence(),'decision':'IC_SCREEN_PASS'})
    assert len(restarted.snapshot('study')['evaluations'])==1


def test_response_recovery_is_atomic_and_never_calls_model(tmp_path):
    obj=ledger(tmp_path)
    ticket=obj.reserve_call('study',0,300,{'model':'fixture','parents':[]})
    raw=json.dumps({'candidates':[candidate(),candidate('close/open','SECOND')]})
    obj.finish_call(ticket,{'content':raw},200)
    restarted=CampaignLedger(obj.path)
    first=restarted.materialize_call('study',ticket)
    assert first==CampaignLedger(obj.path).materialize_call('study',ticket)
    assert len(restarted.snapshot('study')['calls'])==1
    assert len(restarted.snapshot('study')['proposals'])==2


def test_response_budget_race_retains_whole_response_without_partial_import(tmp_path):
    obj=ledger(tmp_path,max_proposals=2,max_evaluations=2)
    ticket=obj.reserve_call('study',0,300,{'model':'fixture','parents':[]})
    obj.finish_call(ticket,{'content':json.dumps({'candidates':[candidate(),candidate('close/open','B')]})},200)
    obj.propose('study',0,candidate('open/close','COMPETITOR'))
    with pytest.raises(ValueError,match='proposal budget'):obj.materialize_call('study',ticket)
    snap=obj.snapshot('study')
    assert len(snap['proposals'])==1 and snap['calls'][0]['state']=='COMPLETE'


def test_freeze_precedes_reservation_and_reexecution_is_blocked(tmp_path):
    obj=ledger(tmp_path);proposal=obj.propose('study',0,candidate())['proposal_id']
    config=tmp_path/'configs/factors/m2_family_screen.json';config.parent.mkdir(parents=True)
    config.write_text(json.dumps({'period':['2015-01-01','2016-12-31']}))
    frozen=prepare_evaluation(tmp_path,obj,'study',[proposal])
    assert json.loads(frozen.read_text())['candidates'][0]==candidate()
    assert obj.snapshot('study')['evaluations'][0]['state']=='RESERVED'
    with pytest.raises(ValueError,match='already reserved'):prepare_evaluation(tmp_path,obj,'study',[proposal])


def test_invalid_manual_item_retained(tmp_path):
    obj=ledger(tmp_path);file=tmp_path/'import.json';file.write_text('{"candidates":[null]}')
    assert import_candidates(obj,'study',0,file,'HUMAN_GENERATED')[0]['status']=='INVALID'
    assert obj.propose('study',0,{**candidate(),'operator_semantics':['malformed']})['status']=='INVALID'


def test_negative_memory_is_retrieved_stably_after_restart(tmp_path):
    obj=ledger(tmp_path);proposal=obj.propose('study',0,candidate())['proposal_id']
    obj.reserve_evaluation(proposal);obj.finish_evaluation(proposal,'run',evidence())
    first=retrieve(obj,'study','CANDIDATE')
    assert first==retrieve(CampaignLedger(obj.path),'study','CANDIDATE')
    assert first[0]['evidence']['primary']['rank_ic']==-.02
    assert retrieve(obj,'study','unknown-term')==[]
    with pytest.raises(ValueError,match='completed research'):
        refine(obj,'study',[999],None,'must not call any model')


def test_screen_attachment_accepts_reserialized_protocol_but_rejects_changed_source(tmp_path):
    obj=ledger(tmp_path);proposal=obj.propose('study',0,candidate())['proposal_id']
    config=tmp_path/'configs/factors/m2_family_screen.json';config.parent.mkdir(parents=True)
    config.write_bytes(b'{"period":["2015-01-01","2016-12-31"]}\r\n')
    frozen=prepare_evaluation(tmp_path,obj,'study',[proposal])
    screen=tmp_path/'screen';source=screen/'source/configs/factors/m2_family_screen.json'
    source.parent.mkdir(parents=True);source.write_bytes(config.read_bytes())
    h=ResearchHypothesis(**candidate());registry=FactorRegistry(tmp_path/'data/factor_registry.sqlite')
    registry.register(h.factor().factor_id,asdict(h.factor()))
    result={'status':'REJECT','admission_stage':'IC_SCREEN_REJECT','primary':{'rank_ic':-.02},'inference':{'p':1.},'q':1.}
    registry.record(screen.name,h.factor().factor_id,result)
    values={'batch.json':json.loads(frozen.read_text()),'screen_protocol.json':json.loads(config.read_text()),
            'results.json':{h.name:result},'status.json':{'status':'PASS'}}
    for name,value in values.items():(screen/name).write_text(json.dumps(value,indent=2))
    (screen/'artifact_hashes.json').write_text(json.dumps({name:sha(screen/name) for name in values}))
    attached=attach_screen(tmp_path,obj,'study',screen,[proposal])
    assert attached['evaluations'][0]['state']=='COMPLETE'
    assert attach_screen(tmp_path,obj,'study',screen,[proposal])==attached
    source.write_text('{}')
    with pytest.raises(ValueError,match='protocol differs'):attach_screen(tmp_path,obj,'study',screen,[proposal])
