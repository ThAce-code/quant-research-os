import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from integrate_r2_event_ledger import deduplicate_typed, compare_vendor_growth, typed_value


class IntegratedLedgerTests(unittest.TestCase):
    def row(self, aid='a', point=100):
        return dict(announcement_id=aid, code='000001', period='2015-03-31',
                    notice_date='2015-04-01', kind='forecast',
                    parent_profit_value_kind='POINT', parent_profit_point_yuan=point,
                    parent_profit_lower_yuan=None, parent_profit_upper_yuan=None,
                    yoy_value_kind='MISSING', yoy_point_percent=None,
                    yoy_lower_percent=None, yoy_upper_percent=None,
                    data_status='REVIEWED_PRIMARY_TRANSCRIPTION', issues=[], source={},
                    growth_basis='EXPLICIT_SOURCE_PERCENT', research_admission=False)

    def test_different_points_cannot_deduplicate_as_null_bounds(self):
        events=deduplicate_typed([self.row(),self.row('b',200)])
        self.assertEqual(len(events),2)
        self.assertTrue(all(e['data_status']=='QUARANTINED_SAME_DATE_VALUES' for e in events))

    def test_equal_values_retain_both_documents(self):
        events=deduplicate_typed([self.row(),self.row('b')])
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['announcement_ids'],['a','b'])

    def test_point_approximation_and_event_kind_are_distinct(self):
        a=self.row();b=self.row('b');b['parent_profit_value_kind']='APPROX_POINT'
        self.assertEqual(len(deduplicate_typed([a,b])),2)
        b=self.row('b');b['kind']='express'
        events=deduplicate_typed([a,b]);self.assertEqual(len(events),2)
        self.assertFalse(any(e['data_status'].startswith('QUARANTINED') for e in events))

    def test_basis_quarantine_survives_identical_values(self):
        a=self.row();b=self.row('b');b['data_status']='QUARANTINED_COMPARISON_BASIS'
        self.assertTrue(deduplicate_typed([a,b])[0]['data_status'].startswith('QUARANTINED'))

    def test_vendor_range_never_completes_a_primary_open_bound(self):
        a=self.row();a.update(yoy_value_kind='OPEN_LOWER',yoy_lower_percent=50)
        self.assertEqual(compare_vendor_growth(a,'50','100')['status'],'NOT_COMPARABLE_VALUE_KIND')
        a.update(yoy_value_kind='APPROX_POINT',yoy_lower_percent=None,yoy_point_percent=50)
        self.assertEqual(compare_vendor_growth(a,'50','50')['status'],'NOT_COMPARABLE_VALUE_KIND')

    def test_primary_point_and_explicit_range_comparison(self):
        a=self.row();a.update(yoy_value_kind='POINT',yoy_point_percent=50)
        self.assertEqual(compare_vendor_growth(a,'50','50')['status'],'AGREES_WITHIN_0_011_PP')
        self.assertEqual(compare_vendor_growth(a,'40','50')['status'],'NOT_COMPARABLE_VALUE_KIND')
        a.update(yoy_value_kind='RANGE',yoy_point_percent=None,yoy_lower_percent=-30,yoy_upper_percent=-20)
        self.assertEqual(compare_vendor_growth(a,'-20','-30')['status'],'AGREES_WITHIN_0_011_PP')
        self.assertEqual(compare_vendor_growth(a,'','-30')['status'],'MISSING_VENDOR_BOUND')


if __name__=='__main__': unittest.main()
