import importlib.util
from pathlib import Path
import json
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit_r2',ROOT/'scripts/audit_r2_events.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_forecast_before_period_end_and_revision_is_not_backfilled():
    events=json.loads((ROOT/'configs/r2/document_cases.json').read_text(encoding='utf-8'))['version_fixture']
    assert module.known_forecast(events,'2015-01-24') is None
    original=module.known_forecast(events,'2015-01-26')
    assert original['period']>original['notice_date'] and original['yoy_lower_percent']==0
    assert module.known_forecast(events,'2015-04-09')['document_id']=='2015-011'
    assert module.known_forecast(events,'2015-04-10')['yoy_lower_percent']==-50
    changed=[events[0],{**events[1],'yoy_lower_percent':-99}]
    assert module.known_forecast(changed,'2015-01-26')==original


def test_ambiguous_or_mixed_versions_are_rejected():
    e={'code':'1','period':'2015-03-31','notice_date':'2015-01-24'}
    with pytest.raises(ValueError):module.known_forecast([e,e],'2015-01-26')
    with pytest.raises(ValueError):module.known_forecast([e,{**e,'code':'2'}],'2015-01-26')
