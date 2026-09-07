import json

import pytest

from quant_research.m3.campaign import CampaignLedger
from quant_research.m3.loop import run_loop
from test_m3_campaign import spec,candidate
from test_m3_controller import evidence
from test_m3_generation import endpoint
from test_m3_model_feedback import model_evidence


def response(number):
    items=[candidate(),candidate('close/open','SECOND')] if number==1 else [candidate('close-open','CHILD')]
    return {'done':True,'message':{'content':json.dumps({'candidates':items})},'eval_count':200}


def test_two_round_http_fixture_crossover_preserves_negative_model_feedback_and_restarts(tmp_path,monkeypatch):
    # HTTP responses and numerical evaluator are controlled fixtures. This proves
    # orchestration/restart, not real model inference or alpha research.
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec(max_evaluations=3))
    evaluated=[]
    def evaluate(root,obj,campaign,ids):
        obj.reserve_evaluations(ids)
        for p in ids:
            obj.finish_evaluation(p,'screen',evidence())
            obj.record_model_results(campaign,[(p,model_evidence())],'model','LEGACY_VERIFIED_IMPORT')
            evaluated.append(p)
    monkeypatch.setattr('quant_research.m3.loop.evaluate',evaluate)
    with endpoint(response) as (model,requests):
        result=run_loop(tmp_path,ledger,'study',model,'bounded research',candidate())
        assert result['state']=='SEARCH_COMPLETE' and len(requests)==2 and len(evaluated)==3
        context=json.loads(requests[1]['messages'][1]['content'])
        assert context['parents']==[1,2]
        assert context['research_feedback']['1']['latest_decision']=='NO_GO'
        assert set(context['parent_hypotheses'])=={'1','2'}
        child=ledger.snapshot('study')['proposals'][2]
        assert json.loads(child['parents'])==[1,2] and child['round']==1
        assert run_loop(tmp_path,CampaignLedger(ledger.path),'study',model,'bounded research',candidate())==result
        assert len(requests)==2 and len(evaluated)==3
        with pytest.raises(ValueError,match='immutable'):run_loop(tmp_path,ledger,'study',model,'changed brief',candidate())


def test_interrupted_numerical_evaluation_never_restarts_implicitly(tmp_path,monkeypatch):
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec())
    def interrupted(root,obj,campaign,ids):
        obj.reserve_evaluations(ids)
        raise KeyboardInterrupt()
    monkeypatch.setattr('quant_research.m3.loop.evaluate',interrupted)
    with endpoint(response) as (model,requests):
        with pytest.raises(KeyboardInterrupt):run_loop(tmp_path,ledger,'study',model,'brief',candidate())
        result=run_loop(tmp_path,CampaignLedger(ledger.path),'study',model,'brief',candidate())
        assert result['state']=='NEEDS_SCREEN_RECOVERY' and len(requests)==1


def test_failed_provider_does_not_automatically_retry_on_restart(tmp_path):
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec())
    with endpoint({'done':True,'message':{'content':'malformed'}}) as (model,requests):
        with pytest.raises(ValueError):run_loop(tmp_path,ledger,'study',model,'brief',candidate())
        result=run_loop(tmp_path,CampaignLedger(ledger.path),'study',model,'brief',candidate())
        assert result['state']=='STOPPED_EXECUTION_FAILURE' and len(requests)==1
