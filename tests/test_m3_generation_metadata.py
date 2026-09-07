import json

import pytest

from quant_research.m3.generation_metadata import catalog,enrich
from quant_research.m3.candidates import ResearchHypothesis
from quant_research.m3.campaign import CampaignLedger
from test_m3_campaign import candidate,spec


def test_metadata_comes_from_exact_formula_not_model_claims():
    item=candidate('returns * turnover / (volume + 1)','META_PROBE')
    item['input_fields']={'returns':'close/open minus one'}
    result=enrich(item,catalog())
    assert result['expression']==item['expression'] and result['direction']==item['direction']
    assert set(result['input_fields'])=={'returns','turnover','volume'}
    assert 'NOT close/open' in result['input_fields']['returns']
    assert ResearchHypothesis(**result)
    assert item['input_fields']=={'returns':'close/open minus one'}


def test_unknown_or_future_formula_is_not_repaired():
    for text in ['Returns','Ref(close,-1)','close > vwap','volume.mean(20)']:
        with pytest.raises(ValueError):enrich(candidate(text),catalog())


def test_frozen_call_catalog_controls_recovery_and_old_calls_stay_unchanged(tmp_path):
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec())
    item=candidate('returns * volume','META_ONE');item['input_fields']={'returns':'incorrect'}
    old=ledger.reserve_call('study',0,400,{'model':'local','parents':[]})
    response={'content':json.dumps({'candidates':[item]})}
    ledger.finish_call(old,response,100)
    assert ledger.materialize_call('study',old)['proposals'][0]['status']=='INVALID'
    fixed=catalog();fixed['fields']['returns']='Frozen canonical close-to-close definition'
    new=ledger.reserve_call('study',0,400,{'model':'local','parents':[],
        'metadata_policy':'canonical_catalog_v1','calculation_catalog':fixed})
    ledger.finish_call(new,response,100)
    first=ledger.materialize_call('study',new)
    assert first['proposals'][0]['status']=='ACCEPTED'
    assert first==CampaignLedger(ledger.path).materialize_call('study',new)
    stored=json.loads(ledger.snapshot('study')['proposals'][1]['payload'])
    assert stored['input_fields']['returns']=='Frozen canonical close-to-close definition'
    assert json.loads(ledger.snapshot('study')['calls'][1]['response'])==response
