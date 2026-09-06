import pandas as pd
import pytest
from quant_research.m2.supplementary import request_plan


def test_requests_bound_membership_and_include_june_2020_reports():
    intervals=pd.DataFrame({'instrument':['SH600000','SZ000001'],
                            'start':['2008-01-01','2019-01-01'],'end':['2026-12-31','2019-05-01']})
    c={'data_period':['2008-01-01','2020-07-31'],'financial_quarter_bounds':['2007Q1','2020Q2']}
    p=request_plan(intervals,c)
    assert p.year.min()==2007 and p.year.max()==2020
    assert p[p.year.eq(2020)].quarter.max()==2
    own=p[p.symbol.eq('SZ000001')]
    assert not ((own.year.eq(2019)) & (own.quarter.gt(1))).any()
    assert own.first_signal.eq('2019-01-01').all()
    c['data_period'][1]='2021-12-31'
    with pytest.raises(ValueError):request_plan(intervals,c)
