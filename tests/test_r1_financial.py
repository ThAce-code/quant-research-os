import numpy as np
import pandas as pd

from quant_research.r1.financial import events_for_symbol,transfer,surplus,FINANCIAL


def row(period,pub,**kwargs):return {'code':'sz.000001','statDate':pd.Timestamp(period),'pubDate':pd.Timestamp(pub),**kwargs}


def test_same_quarter_dependencies_wait_for_later_release_and_never_fill_old_value():
    p=pd.DataFrame([row('2014-12-31','2015-03-01',netProfit=10,MBRevenue=100,npMargin=.1),
                    row('2015-03-31','2015-04-01',netProfit=20,MBRevenue=100,npMargin=.2)])
    c=pd.DataFrame([row('2014-12-31','2015-03-01',CFOToOR=.3,CFOToNP=3),
                    row('2015-03-31','2015-04-05',CFOToOR=.3,CFOToNP=1.5)])
    e=events_for_symbol(p,c,'sz.000001','2015-04-10')[FINANCIAL[0]]
    dates=pd.date_range('2015-03-30','2015-04-07');values,_=transfer(e,dates)
    assert values.loc['2015-04-01']==.3-.1
    assert values.loc['2015-04-02':'2015-04-05'].isna().all()
    assert np.isclose(values.loc['2015-04-06'],.1)
    prefix,_=transfer(e[e.pubDate<='2015-04-03'],dates[:5])
    pd.testing.assert_series_equal(prefix,values.iloc[:5])


def test_seasonal_dependencies_use_same_quarter_and_delay_late_prior_reports():
    p=pd.DataFrame([row('2013-03-31','2013-04-20',netProfit=5,MBRevenue=80,npMargin=.0625),
                    row('2014-03-31','2015-05-01',netProfit=10,MBRevenue=100,npMargin=.1,gpMargin=.2),
                    row('2015-03-31','2015-04-20',netProfit=18,MBRevenue=120,npMargin=.15,gpMargin=.28)])
    c=pd.DataFrame(columns=['statDate','pubDate'])
    events=events_for_symbol(p,c,'sz.000001','2015-05-10')
    dates=pd.date_range('2015-04-20','2015-05-03')
    news,_=transfer(events[FINANCIAL[2]],dates);acc,_=transfer(events[FINANCIAL[3]],dates)
    assert news.loc['2015-04-21':'2015-05-01'].isna().all()
    assert np.isclose(news.loc['2015-05-02'],.08) and np.isclose(acc.loc['2015-05-02'],.05)


def test_ambiguous_revenue_not_used_and_inconsistent_cash_ratio_is_missing():
    p={'netProfit':10,'MBRevenue':100,'npMargin':.1}
    assert np.isclose(surplus(p,{'CFOToOR':.3,'CFOToNP':3}),.2)
    assert np.isclose(surplus({**p,'MBRevenue':50},{'CFOToOR':.3,'CFOToNP':3}),.2)
    assert np.isnan(surplus(p,{'CFOToOR':.3,'CFOToNP':1}))
