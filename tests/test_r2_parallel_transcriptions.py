"""Reject unsupported model transcriptions before any root review or ledger use."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_r2_parallel_transcriptions import validate_record


class TranscriptionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = {'announcement_id': 'one', 'period': '2015-03-31'}
        self.text = '=== PAGE 1 ===\n业绩预告期间：2015年1月1日至2015年3月31日。\n归属于上市公司股东的净利润：亏损300万元至200万元。\n比上年同期下降30%至50%。'
        self.record = dict(announcement_id='one', claim_type='source_claim', document_class='Q1_FORECAST',
            verified_period='2015-03-31', parent_profit_lower_yuan=-3000000, parent_profit_upper_yuan=-2000000,
            yoy_lower_percent=-50, yoy_upper_percent=-30, source_money_unit='10k_yuan', signature_date=None,
            parent_profit_value_kind='RANGE',yoy_value_kind='RANGE',parent_profit_point_yuan=None,yoy_point_percent=None,
            prior_reference=None, issues=[], research_admission=False, extraction_status='DRAFT_EXTRACTED',
            evidence=[{'field':'period','page':1,'quote':'业绩预告期间：2015年1月1日至2015年3月31日。'},
                      {'field':'parent_profit_range','page':1,'quote':'归属于上市公司股东的净利润：亏损300万元至200万元。'},
                      {'field':'yoy_range','page':1,'quote':'比上年同期下降30%至50%。'}])

    def test_loss_and_decline_keep_signs_and_units(self):
        self.assertEqual(validate_record(self.record, self.doc, self.text)['errors'], [])

    def test_fabricated_quote_and_page_fail(self):
        r=copy.deepcopy(self.record);r['evidence'][1]['quote']='盈利500万元至600万元'
        self.assertIn('QUOTE_NOT_IN_PAGE:parent_profit_range',validate_record(r,self.doc,self.text)['errors'])
        r=copy.deepcopy(self.record);r['evidence'][1]['page']=2
        self.assertIn('MISSING_PAGE:2',validate_record(r,self.doc,self.text)['errors'])

    def test_currency_scale_and_unprinted_yoy_fail(self):
        r=copy.deepcopy(self.record);r['parent_profit_lower_yuan']=-300000000
        self.assertIn('UNSUPPORTED_NUMBER:parent_profit_lower_yuan',validate_record(r,self.doc,self.text)['errors'])
        r=copy.deepcopy(self.record);r['yoy_lower_percent']=-80
        self.assertIn('UNSUPPORTED_NUMBER:yoy_lower_percent',validate_record(r,self.doc,self.text)['errors'])

    def test_unknown_period_cannot_admit_values(self):
        r=copy.deepcopy(self.record);r['verified_period']=None
        self.assertIn('NUMERIC_WITHOUT_VERIFIED_Q1_PERIOD',validate_record(r,self.doc,self.text)['errors'])
        r=copy.deepcopy(self.record);r['research_admission']=True
        self.assertIn('RESEARCH_ADMISSION_FORBIDDEN',validate_record(r,self.doc,self.text)['errors'])

    def test_loss_or_decline_cannot_silently_flip_positive(self):
        r=copy.deepcopy(self.record)
        r['parent_profit_lower_yuan']=2000000;r['parent_profit_upper_yuan']=3000000
        self.assertIn('LOSS_SIGN_CONFLICT',validate_record(r,self.doc,self.text)['errors'])
        r=copy.deepcopy(self.record);r['yoy_lower_percent']=30;r['yoy_upper_percent']=50
        self.assertIn('DECLINE_SIGN_CONFLICT',validate_record(r,self.doc,self.text)['errors'])

    def test_approximate_point_is_not_a_lower_bound(self):
        r=copy.deepcopy(self.record);r['parent_profit_value_kind']='APPROX_POINT'
        r['parent_profit_point_yuan']=-3000000
        self.assertIn('VALUE_KIND_CONFLICT:parent_profit',validate_record(r,self.doc,self.text)['errors'])
        r['parent_profit_lower_yuan']=None;r['parent_profit_upper_yuan']=None
        r['evidence'][1]['quote']='归属于上市公司股东的净利润：亏损约300万元。'
        text=self.text.replace('亏损300万元至200万元','亏损约300万元')
        self.assertEqual(validate_record(r,self.doc,text)['errors'],[])

    def test_explicit_dotted_dates_and_rmb_yi_unit(self):
        r=copy.deepcopy(self.record)
        r['evidence'][0]['quote']='2015.1.1—2015.3.31'
        r['evidence'][1]['quote']='归属于母公司净利润：人民币10.4亿-人民币11.5亿'
        r['source_money_unit']='100m_yuan'
        r['parent_profit_lower_yuan']=1040000000;r['parent_profit_upper_yuan']=1150000000
        text='=== PAGE 1 ===\n'+r['evidence'][0]['quote']+'\n'+r['evidence'][1]['quote']+'\n比上年同期下降30%至50%。'
        self.assertEqual(validate_record(r,self.doc,text)['errors'],[])

    def test_unordered_range_and_nan_fail(self):
        r=copy.deepcopy(self.record);r['yoy_lower_percent']=50
        self.assertIn('UNORDERED_RANGE:yoy',validate_record(r,self.doc,self.text)['errors'])
        r=copy.deepcopy(self.record);r['parent_profit_lower_yuan']=float('nan')
        self.assertIn('INVALID_NUMBER:parent_profit_lower_yuan',validate_record(r,self.doc,self.text)['errors'])


if __name__ == '__main__':
    unittest.main()
