from pathlib import Path
import json
import sqlite3

import pytest

from quant_research.m3.auditor import audit,evidence_pack,digest
from quant_research.m3.campaign import CampaignLedger
from quant_research.m3.candidates import ResearchHypothesis
from test_m3_campaign import spec,candidate
from test_m3_controller import evidence
from test_m3_generation import endpoint


def frozen(root,screen=False):
    ledger=CampaignLedger(root/'data/m3_campaigns.sqlite');ledger.create(spec())
    with sqlite3.connect(root/'data/factor_registry.sqlite') as db:
        db.execute('CREATE TABLE evaluations(run_id TEXT,factor_id TEXT,report_json TEXT)')
    if screen:
        h=ResearchHypothesis(**candidate());p=ledger.propose('study',0,candidate())['proposal_id']
        run='20160101T010203123456Z';folder=root/'experiments/m3'/run;folder.mkdir(parents=True)
        report={'primary':{'rank_ic':0.001},'q':0.8,'admission_stage':'REJECT'}
        values={'status.json':{'status':'PASS'},'screen_protocol.json':{'period':['2015-01-01','2016-12-31']},
                'results.json':{h.name:report},'batch.json':{'candidates':[candidate()]}}
        for name,value in values.items():(folder/name).write_text(json.dumps(value))
        (folder/'artifact_hashes.json').write_text(json.dumps({name:digest(folder/name) for name in values}))
        with sqlite3.connect(root/'data/factor_registry.sqlite') as db:
            db.execute('INSERT INTO evaluations VALUES (?,?,?)',(run,h.factor().factor_id,json.dumps(report)))
        ledger.reserve_evaluations([p]);ledger.finish_evaluation(p,run,{**evidence(),
            'period':['2015-01-01','2016-12-31'],'decision':'REJECT','result_sha256':digest(folder/'results.json')})
    ledger.freeze('study',[],{})
    return ledger


def answer(citation='BUDGET'):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
        'summary':'Historical engineering evidence only.','observations':[{
            'claim':'This finite campaign cannot establish independent alpha.','evidence_ids':[citation]}]})}}],
        'usage':{'completion_tokens':50}}


def test_two_readonly_opposing_http_reviews_and_restart(tmp_path):
    ledger=frozen(tmp_path,True)
    paths=[ledger.path,tmp_path/'data/factor_registry.sqlite'];before=[p.read_bytes() for p in paths]
    with endpoint(answer(),'chat_completions_schema') as (model,requests):
        result=audit(tmp_path,'study',model)
        assert result['state']=='COMPLETE' and len(requests)==2
        assert 'supportive' in requests[0]['messages'][0]['content']
        assert 'critical' in requests[1]['messages'][0]['content']
        schema=requests[0]['response_format']['json_schema']['schema']
        assert 'observations' in schema['properties'] and 'candidates' not in schema['properties']
        assert audit(tmp_path,'study',model)==result and len(requests)==2
        assert [p.read_bytes() for p in paths]==before


def test_unknown_citation_is_retained_and_never_retried(tmp_path):
    frozen(tmp_path)
    with endpoint(answer('LOCKBOX_2025'),'chat_completions_schema') as (model,requests):
        with pytest.raises(ValueError,match='citation'):audit(tmp_path,'study',model)
        assert audit(tmp_path,'study',model)['state']=='STOPPED_REVIEW_ATTEMPT'
        assert len(requests)==1
    state=json.loads((tmp_path/'experiments/m3_audits/study/review_v1/state.json').read_text())
    assert state['calls'][0]['raw_response'] and state['calls'][0]['status']=='FAILED'


def test_changed_numerical_artifact_and_registry_fail_before_model_call(tmp_path):
    frozen(tmp_path,True);assert 'SCREEN_1' in evidence_pack(tmp_path,'study')['evidence']
    path=tmp_path/'experiments/m3/20160101T010203123456Z/results.json';old=path.read_bytes()
    path.write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):evidence_pack(tmp_path,'study')
    path.write_bytes(old)
    with sqlite3.connect(tmp_path/'data/factor_registry.sqlite') as db:db.execute("UPDATE evaluations SET report_json='{}'")
    with pytest.raises(ValueError,match='numerical registry'):evidence_pack(tmp_path,'study')


def test_protected_or_unfinished_campaign_cannot_be_reviewed(tmp_path):
    ledger=frozen(tmp_path)
    with pytest.raises(ValueError,match='frozen campaign'):evidence_pack(tmp_path,'missing')
    with ledger.connect() as db:
        row=json.loads(db.execute('SELECT payload FROM campaign_freezes').fetchone()[0])
    # A foreign imported store has no campaign triggers; the reader still checks.
    other=tmp_path/'foreign';(other/'data').mkdir(parents=True)
    row['spec']['research_period'][1]='2025-12-31'
    with sqlite3.connect(other/'data/m3_campaigns.sqlite') as db:
        db.executescript('CREATE TABLE campaign_freezes(campaign TEXT,payload TEXT); CREATE TABLE model_results(proposal INTEGER); CREATE TABLE proposals(id INTEGER,campaign TEXT);')
        db.execute('INSERT INTO campaign_freezes VALUES (?,?)',('study',json.dumps(row)))
    with pytest.raises(ValueError,match='protected'):evidence_pack(other,'study')
