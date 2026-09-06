import numpy as np
import pandas as pd
from quant_research.m2.alternate import field_events
from quant_research.m2.quarterly import daily_panel


def statement(notice, **fields):
    return {'NOTICE_DATE':notice,'UPDATE_DATE':notice,**fields}


def test_cross_statement_availability_and_missing_report_do_not_resurrect():
    balance={'2015-12-31':statement('2016-05-01',TOTAL_PARENT_EQUITY=80),
             '2016-03-31':statement('2016-04-20',TOTAL_PARENT_EQUITY=120)}
    income={'2016-03-31':statement('2016-04-25',PARENT_NETPROFIT=10,NETPROFIT=12,OPERATE_INCOME=60),
            '2016-06-30':statement('2016-08-01',PARENT_NETPROFIT=20)}
    events=field_events('sz.000630',['2016-03-31','2016-06-30'],balance,income)
    roe=events[events.field.eq('roeAvg')][['code','statDate','pubDate','value']].rename(columns={'value':'roeAvg'})
    dates=pd.to_datetime(['2016-04-26','2016-05-01','2016-05-02','2016-08-02'])
    result=daily_panel(roe,dates,['roeAvg'])
    assert result.roeAvg.isna().tolist()==[True,True,False,True]
    assert result.roeAvg.iloc[2]==.1
    margin=events[events.field.eq('npMargin')]
    assert margin.iloc[0].value==.2 and margin.iloc[0].pubDate==pd.Timestamp('2016-04-25')


def test_zero_denominator_missing_dependency_and_no_invented_date():
    income={'2016-03-31':statement('2016-04-20',NETPROFIT=1,OPERATE_INCOME=0,NETPROFIT_YOY=-12)}
    events=field_events('sz.000630',['2016-03-31','2016-06-30'],{},income)
    assert set(events.field)=={'roeAvg','npMargin','YOYNI'}
    assert not np.isinf(events.value).any()
    assert events[events.field.eq('npMargin')].value.isna().all()
    assert events[events.field.eq('YOYNI')].value.iloc[0]==-.12
    assert events.statDate.eq(pd.Timestamp('2016-03-31')).all()


def test_revision_flag_is_not_a_claim_of_historical_version_recovery():
    income={'2016-03-31':{'NOTICE_DATE':'2016-04-20','UPDATE_DATE':'2022-04-20','NETPROFIT_YOY':5}}
    events=field_events('sz.000630',['2016-03-31'],{},income)
    assert events.revision_unknown.all() and events.updated_after_notice.all()
    first=events[events.pubDate.eq(pd.Timestamp('2016-04-20'))]
    assert first.value.isna().all()
    revised=events[events.field.eq('YOYNI') & events.pubDate.eq(pd.Timestamp('2022-04-20'))]
    assert revised.value.iloc[0]==.05


def test_financial_income_uses_full_revenue_not_nonfinancial_subcomponent():
    income={'2015-06-30':statement('2015-07-30',ORG_TYPE='证券',NETPROFIT=852050169.99,
                                 TOTAL_OPERATE_INCOME=1352716949.58,OPERATE_INCOME=12068927.54)}
    events=field_events('sz.000712',['2015-06-30'],{},income)
    value=events[events.field.eq('npMargin')].value.iloc[0]
    assert abs(value-.629881)<1e-6
