from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json

import pytest

from quant_research.m3.campaign import CampaignLedger
from quant_research.m3.controller import model_increment,attach_model
from quant_research.m3.trajectory import retrieve
from test_m3_campaign import spec,candidate
from test_m3_controller import evidence
from quant_research.m3.candidates import ResearchHypothesis


def ready(tmp_path,**changes):
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec(max_model_runs=1,**changes))
    proposal=ledger.propose('study',0,candidate())['proposal_id']
    ledger.reserve_evaluation(proposal)
    ledger.finish_evaluation(proposal,'screen',{**evidence(),'decision':'IC_SCREEN_PASS'})
    return ledger,proposal


def model_evidence():
    return {'scope':'research_only','protected_accessed':False,'period':['2015-01-01','2020-07-31'],
            'stage':'rolling_model','decision':'NO_GO','screen_run':'screen','model_run':'model',
            'comparison':{'rank_ic_increment':{'mean':0.},'decision':'NO_GO'}}


def test_freeze_preserves_all_attempts_and_blocks_further_search(tmp_path):
    ledger,p=ready(tmp_path)
    ledger.propose('study',1,candidate())  # Failed duplicate is still in the search family.
    frozen=ledger.freeze('study',[p],{'config':'digest'})
    assert frozen['proposal_attempts']==2 and frozen['hypothesis_budget']==3
    assert frozen['proposals'][1]['status']=='DUPLICATE'
    assert frozen==CampaignLedger(ledger.path).freeze('study',[p],{'config':'digest'})
    with pytest.raises(ValueError,match='immutable'):ledger.freeze('study',[],{'config':'digest'})
    with pytest.raises(ValueError,match='not open'):ledger.propose('study',1,candidate('close/open'))
    with pytest.raises(ValueError,match='not open'):ledger.reserve_call('study',1,10)


def test_pending_calls_block_freeze_and_recovery_retains_budget(tmp_path):
    ledger,p=ready(tmp_path)
    ticket=ledger.reserve_call('study',0,300)
    with pytest.raises(ValueError,match='pending'):ledger.freeze('study',[p],{})
    ledger.finish_call(ticket,error='known terminal failure')
    frozen=ledger.freeze('study',[p],{})
    assert frozen['calls'][0]['output_budget']==300 and frozen['calls'][0]['state']=='FAILED'


def test_model_reservation_concurrency_and_restart_cannot_rerun(tmp_path):
    ledger,p=ready(tmp_path);ledger.freeze('study',[p],{})
    def attempt(_):
        try:ledger.reserve_model('study');return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(attempt,range(4)))==1
    with pytest.raises(ValueError,match='reserved'):CampaignLedger(ledger.path).reserve_model('study')


def test_legacy_spec_defaults_do_not_grant_new_model_budget(tmp_path):
    ledger=CampaignLedger(tmp_path/'ledger.sqlite')
    old=asdict(spec());old.pop('max_model_runs')
    with ledger.connect() as db:db.execute('INSERT INTO campaigns(id,spec) VALUES (?,?)',('study',json.dumps(old)))
    ledger.create(spec())  # Idempotent schema-compatible read, not a budget migration.
    with pytest.raises(ValueError,match='immutable'):ledger.create(spec(max_model_runs=1))
    p=ledger.propose('study',0,candidate())['proposal_id'];ledger.reserve_evaluation(p)
    ledger.finish_evaluation(p,'screen',{**evidence(),'decision':'IC_SCREEN_PASS'})
    ledger.freeze('study',[p],{})
    with pytest.raises(ValueError,match='no model run budget'):ledger.reserve_model('study')


def test_model_feedback_preserves_screen_and_updates_memory(tmp_path):
    ledger,p=ready(tmp_path)
    ledger.freeze('study',[p],{});ledger.reserve_model('study')
    ledger.record_model_results('study',[(p,model_evidence())],'model','CAMPAIGN_MODEL')
    ledger.record_model_results('study',[(p,model_evidence())],'model','CAMPAIGN_MODEL')
    result=retrieve(CampaignLedger(ledger.path),'study')[0]['evidence']
    assert result['decision']=='IC_SCREEN_PASS'
    assert result['latest_decision']=='NO_GO' and result['model']['model_run']=='model'
    assert ledger.snapshot('study')['model_runs'][0]['state']=='COMPLETE'
    with pytest.raises(ValueError,match='immutable'):
        ledger.record_model_results('study',[(p,{**model_evidence(),'decision':'GO'})],'model','CAMPAIGN_MODEL')


def test_model_feedback_rejects_protected_and_mismatched_screen(tmp_path):
    ledger,p=ready(tmp_path)
    for change in [{'period':['2021-01-01','2021-12-31']},{'screen_run':'unrelated'},{'protected_accessed':True}]:
        with pytest.raises(ValueError):ledger.record_model_results('study',[(p,{**model_evidence(),**change})],'model','LEGACY_VERIFIED_IMPORT')
    assert ledger.snapshot('study')['model_results']==[]


def test_unreserved_model_attachment_rolls_back_all_results(tmp_path):
    ledger,p=ready(tmp_path)
    # Force an invalid reservation state after a valid freeze.
    ledger.freeze('study',[p],{})
    with pytest.raises(ValueError,match='reserved freeze'):
        ledger.record_model_results('study',[(p,model_evidence())],'model','CAMPAIGN_MODEL')
    assert not ledger.snapshot('study')['model_results']


def test_empty_freeze_takes_no_entry_without_calling_kernel(tmp_path):
    ledger,p=ready(tmp_path);ledger.freeze('study',[],{})
    result=model_increment(tmp_path,ledger,'study')
    assert result=={'decision':'NO_ENTRY','fits':0,'portfolios':0}
    assert not ledger.snapshot('study')['model_runs']


def test_cross_batch_selection_checks_names_before_loading_data(tmp_path,monkeypatch):
    from quant_research.m3 import increment
    first=ResearchHypothesis(**candidate());second=ResearchHypothesis(**{**candidate('close/open'),'version':2})
    def source(screen,registry):
        return ([first] if screen.name=='first' else [second]),{'screen_protocol_sha256':'frozen'}
    monkeypatch.setattr(increment,'survivors',source)
    monkeypatch.setattr(increment,'load_factor_data',lambda *a:pytest.fail('must not load market data'))
    with pytest.raises(ValueError,match='names collide'):
        increment.run(tmp_path,tmp_path/'first',selection=[first.hypothesis_id,second.hypothesis_id],more_screens=[tmp_path/'second'])


def test_cross_batch_selection_carries_each_screen_origin_to_kernel(tmp_path,monkeypatch):
    from quant_research.m3 import increment
    first=ResearchHypothesis(**candidate());second=ResearchHypothesis(**candidate('close/open','SECOND'))
    def source(screen,registry):
        return ([first] if screen.name=='first' else [second]),{'screen_protocol_sha256':'frozen'}
    monkeypatch.setattr(increment,'survivors',source)
    for name in ['configs/m3/increment.json','scripts/run_m3_increment.py']:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
    seen={}
    def compute(root,screen,output,selected,registry,origins):
        seen.update(origins)
        assert [h.name for h in selected]==['SECOND','CANDIDATE']
        return output
    monkeypatch.setattr(increment,'_evaluate',compute)
    result=increment.run(tmp_path,tmp_path/'first',selection=[second.hypothesis_id,first.hypothesis_id],more_screens=[tmp_path/'second'])
    assert seen=={first.hypothesis_id:'first',second.hypothesis_id:'second'}
    assert json.loads((result/'admission.json').read_text())['screen_by_hypothesis']==seen
