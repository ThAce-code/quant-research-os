import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('r2_event_ledger', ROOT/'scripts/build_r2_event_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def test_date_precision_holiday_and_end_of_calendar():
    calendar = ['2015-04-03', '2015-04-07', '2015-04-08']
    assert ledger.available_date('2015-04-03', calendar) == '2015-04-07'
    assert ledger.available_date('2015-04-04', calendar) == '2015-04-07'
    assert ledger.available_date('2015-04-07', calendar) == '2015-04-08'
    assert ledger.available_date('2015-04-08', calendar) is None


def test_member_union_does_not_imply_member_on_event_date():
    intervals = {'000001': [('2015-03-01', '2015-04-03'), ('2016-01-01', '2016-12-31')]}
    assert ledger.is_member('000001', '2015-04-03', intervals)
    assert not ledger.is_member('000001', '2015-04-07', intervals)
    assert not ledger.is_member('000002', '2015-04-03', intervals)


def record(aid, low=100, high=120, date='2015-03-01'):
    return dict(announcement_id=aid, code='000001', period='2015-03-31', notice_date=date,
                parent_profit_lower_yuan=low, parent_profit_upper_yuan=high,
                yoy_lower_percent=0, yoy_upper_percent=20, issues=[],
                data_status='REVIEWED_NUMERIC_PRIMARY_FACTS', source={'announcement_id': aid})


def test_summary_full_report_dedup_retains_provenance_and_never_dates():
    events = ledger.deduplicate([record('summary'), record('full'), record('later', date='2015-03-02')])
    assert len(events) == 2
    assert events[0]['announcement_ids'] == ['full', 'summary']
    assert len(events[0]['sources']) == 2
    assert all(not e['research_admission'] for e in events)


def test_same_date_conflict_cannot_be_resolved_by_sort_order():
    events = ledger.deduplicate([record('a'), record('b', high=130)])
    assert len(events) == 2
    assert all(e['data_status'] == 'QUARANTINED_PRIMARY_FACTS' for e in events)
    assert all(e['same_date_value_conflict'] for e in events)


def test_revision_never_backfills_original_date_and_unknown_predecessor_fails():
    first, second = ledger.deduplicate([record('a'), record('b', low=50, high=60, date='2015-04-03')])
    first['available_date'] = '2015-03-02'
    second['available_date'] = '2015-04-07'
    with pytest.raises(ValueError, match='unverified predecessor'):
        ledger.local_chain_asof([first, second], '2015-04-07')
    second['supersedes_event_id'] = first['event_id']
    assert ledger.local_chain_asof([first, second], '2015-03-01') is None
    assert ledger.local_chain_asof([first, second], '2015-04-03')['parent_profit_lower_yuan'] == 100
    assert ledger.local_chain_asof([first, second], '2015-04-06')['parent_profit_lower_yuan'] == 100
    assert ledger.local_chain_asof([first, second], '2015-04-07')['parent_profit_lower_yuan'] == 50
    second['data_status'] = 'QUARANTINED_PRIMARY_FACTS'
    with pytest.raises(ValueError, match='quarantined'):
        ledger.local_chain_asof([first, second], '2015-04-07')


def test_missing_page_cannot_borrow_values_from_another_page():
    with pytest.raises(ValueError, match='not present'):
        ledger.page_text('=== PAGE 1 ===\nvalue', 2)
