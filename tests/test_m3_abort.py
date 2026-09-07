import json

import pytest

from quant_research.m3.campaign import CampaignLedger
from test_m3_campaign import spec,candidate


@pytest.mark.parametrize('outcome',['unknown','overrun','unmaterialized_budget_race'])
def test_terminal_abort_preserves_unrecoverable_budget_and_raw_response(tmp_path,outcome):
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec(max_proposals=2))
    ticket=ledger.reserve_call('study',0,400,{'model':'fixture','parents':[]})
    if outcome=='overrun':ledger.finish_call(ticket,{'content':'raw output'},401)
    if outcome=='unmaterialized_budget_race':
        ledger.finish_call(ticket,{'content':json.dumps({'candidates':[candidate('close','A'),candidate('open','B')]})},100)
        ledger.propose('study',0,candidate())
        with pytest.raises(ValueError,match='budget exhausted'):ledger.materialize_call('study',ticket)
        # Batch transaction must have rolled back its partial first insertion.
        assert len(ledger.snapshot('study')['proposals'])==1
    before=ledger.snapshot('study')
    result=ledger.abort('study','Worker stopped; preserve the unresolved attempt.')
    after=ledger.snapshot('study')
    assert after['calls']==before['calls'] and after['proposals']==before['proposals']
    assert result['refunded_calls']==result['refunded_tokens']==0
    restarted=CampaignLedger(ledger.path)
    assert restarted.abort('study',result['reason'])==result
    with pytest.raises(ValueError,match='not open'):restarted.reserve_call('study',0,100)
    with pytest.raises(ValueError,match='not open'):restarted.freeze('study',[],{})
    with pytest.raises(ValueError,match='immutable'):restarted.abort('study','another reason')
