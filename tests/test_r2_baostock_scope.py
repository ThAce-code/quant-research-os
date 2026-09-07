import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'scripts/audit_r2_baostock_events.py'
spec=importlib.util.spec_from_file_location('bs_event_audit',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_publication_before_period_end_is_valid_but_future_publication_is_excluded():
    row={'code':'sz.000001','profitForcastExpStatDate':'2015-03-31','profitForcastExpPubDate':'2015-01-20'}
    unions={'2015':['sz.000001']};targets=['2015-03-31']
    assert module.classify(row,'forecast',unions,targets)['scope_eligible']
    row['profitForcastExpPubDate']='2022-01-01'
    assert not module.classify(row,'forecast',unions,targets)['scope_eligible']


def test_combined_query_range_does_not_admit_other_quarters_or_future_members():
    row={'code':'sz.000001','performanceExpStatDate':'2015-12-31','performanceExpPubDate':'2016-02-01'}
    result=module.classify(row,'express',{'2015':[],'2016':['sz.000001']},['2015-03-31','2016-03-31'])
    assert 'NON_TARGET_REPORT_PERIOD' in result['exclusion_reasons']
    assert 'NOT_IN_TARGET_YEAR_MEMBER_UNION' in result['exclusion_reasons']
