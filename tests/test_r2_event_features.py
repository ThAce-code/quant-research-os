import sys
from pathlib import Path
import unittest
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gate_r2_event_features import event_features


class EventFeatureTimingTests(unittest.TestCase):
    def setUp(self):
        self.calendar=pd.bdate_range('2015-04-01',periods=6)
        self.members=pd.DataFrame(True,index=self.calendar,columns=['SZ000001'])
        self.event=dict(code='000001',event_id='a',available_date='2015-04-02',notice_date='2015-04-01',
            kind='forecast',data_status='REVIEWED_PRIMARY_TRANSCRIPTION',
            yoy_value_kind='RANGE',yoy_lower_percent=20,yoy_upper_percent=40,yoy_point_percent=None)

    def test_no_early_signal_and_fixed_expiry(self):
        p=event_features([self.event],self.calendar,self.members,3)['R2_GUIDANCE_MIDPOINT']
        self.assertTrue(np.isnan(p.iloc[0,0]));self.assertAlmostEqual(p.iloc[1,0],np.log1p(.3))
        self.assertTrue(np.isnan(p.iloc[4,0]))

    def test_latest_missing_or_actual_event_clears_old_forecast(self):
        for change in [dict(yoy_value_kind='MISSING'),dict(kind='express'),dict(data_status='QUARANTINED_PRIMARY')]:
            b={**self.event,'event_id':'b','available_date':'2015-04-03',**change}
            p=event_features([self.event,b],self.calendar,self.members,5)['R2_GUIDANCE_MIDPOINT']
            self.assertTrue(np.isnan(p.iloc[2,0]))

    def test_membership_and_open_bound_are_not_filled(self):
        m=self.members.copy();m.iloc[2,0]=False
        p=event_features([self.event],self.calendar,m,4)['R2_GUIDANCE_LOWER']
        self.assertTrue(np.isnan(p.iloc[2,0]))
        b={**self.event,'yoy_value_kind':'OPEN_LOWER'}
        self.assertTrue(event_features([b],self.calendar,m,4)['R2_GUIDANCE_MIDPOINT'].isna().all().all())

if __name__=='__main__':unittest.main()
