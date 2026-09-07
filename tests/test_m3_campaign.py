from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path

import pytest

from quant_research.m3.campaign import CampaignLedger, CampaignSpec, expression_signature


def spec(name='study', **changes):
    return replace(CampaignSpec(name, ['2015-01-01','2020-07-31'], 3, 2, 2, 1000, 2, 42,
                                'new fixed research budget'), **changes)


def candidate(expression='Log(close / open)', name='CANDIDATE'):
    p=Path(__file__).resolve().parents[1]/'configs/m3/paper_pilot.json'
    row=json.loads(p.read_text())['candidates'][0]
    return {**row, 'name':name, 'expression':expression}


def test_restart_does_not_refund_failed_or_uncertain_calls(tmp_path):
    p=tmp_path/'c.sqlite'; ledger=CampaignLedger(p); ledger.create(spec())
    ticket=ledger.reserve_call('study',0,400)
    ledger.finish_call(ticket,error='network response unknown')
    restarted=CampaignLedger(p); restarted.create(spec())
    restarted.reserve_call('study',0,400)
    with pytest.raises(ValueError,match='budget exhausted'): restarted.reserve_call('study',1,100)
    with pytest.raises(ValueError,match='immutable'): restarted.create(spec(max_calls=8))


def test_concurrent_workers_cannot_overspend(tmp_path):
    ledger=CampaignLedger(tmp_path/'c.sqlite');ledger.create(spec(max_calls=1))
    def attempt(_):
        try:return ledger.reserve_call('study',0,400)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=4) as workers: results=list(workers.map(attempt, range(4)))
    assert sum(v is not None for v in results)==1


def test_cross_campaign_duplicates_and_invalid_attempts_consume_budget(tmp_path):
    ledger=CampaignLedger(tmp_path/'c.sqlite');ledger.create(spec());ledger.create(spec('next'))
    assert ledger.propose('study',0,candidate())['status']=='ACCEPTED'
    assert ledger.propose('next',0,candidate('(Log(Div(close, open)))','RENAMED'))['status']=='DUPLICATE'
    bad=candidate('Ref(close,-1)')
    assert ledger.propose('next',0,bad)['status']=='INVALID'
    ledger.propose('next',0,bad)
    with pytest.raises(ValueError,match='proposal budget'):ledger.propose('next',0,candidate())


def test_seed_import_blocks_existing_expression(tmp_path):
    ledger=CampaignLedger(tmp_path/'c.sqlite');ledger.create(spec())
    ledger.import_expression('Log(close/open)',1,'prior-study')
    result=ledger.propose('study',0,candidate())
    assert result['status']=='DUPLICATE' and result['reason']=='prior-study'
    assert expression_signature('open + close',1)==expression_signature('Add(close, open)',1)
    assert expression_signature('open - close',1)!=expression_signature('close - open',1)


def test_parent_lineage_and_protected_feedback_fail_closed(tmp_path):
    ledger=CampaignLedger(tmp_path/'c.sqlite');ledger.create(spec())
    first=ledger.propose('study',0,candidate())['proposal_id']
    with pytest.raises(ValueError,match='earlier'):ledger.propose('study',0,candidate(),[first])
    next_id=ledger.propose('study',1,candidate('close/open','CHILD'),[first])['proposal_id']
    ledger.reserve_evaluation(next_id)
    with pytest.raises(ValueError,match='only explicitly'):
        ledger.finish_evaluation(next_id,'bad',{'scope':'qualification','protected_accessed':True})
    with pytest.raises(ValueError,match='protected'):
        ledger.finish_evaluation(next_id,'bad',{'scope':'research_only','protected_accessed':False,
                                               'period':['2021-01-01','2022-01-01']})
    evidence={'scope':'research_only','protected_accessed':False,'period':['2015-01-01','2016-12-31'],
              'decision':'REJECT','rank_ic':-.02}
    ledger.finish_evaluation(next_id,'research-run',evidence)
    snap=CampaignLedger(tmp_path/'c.sqlite').snapshot('study')
    assert json.loads(snap['proposals'][1]['parents'])==[first]
    assert json.loads(snap['evaluations'][0]['evidence'])==evidence


def test_provider_overrun_stops_campaign(tmp_path):
    ledger=CampaignLedger(tmp_path/'c.sqlite');ledger.create(spec())
    ticket=ledger.reserve_call('study',0,50)
    ledger.finish_call(ticket,{'bad':'provider exceeded limit'},used_output_tokens=51)
    with pytest.raises(ValueError,match='not open'):ledger.propose('study',0,candidate())


def test_no_duplicate_evaluation_or_budget_extension(tmp_path):
    ledger=CampaignLedger(tmp_path/'c.sqlite');ledger.create(spec(max_evaluations=1))
    proposal=ledger.propose('study',0,candidate())['proposal_id'];ledger.reserve_evaluation(proposal)
    with pytest.raises(ValueError,match='budget'):ledger.reserve_evaluation(proposal)
    with pytest.raises(ValueError,match='round budget'):ledger.propose('study',2,candidate())


@pytest.mark.parametrize('change',[{'max_calls':True},{'research_period':['2020-01-01','2021-01-01']},
                                  {'max_proposals':0},{'max_evaluations':4}])
def test_invalid_spec(change):
    with pytest.raises(ValueError):spec(**change)
