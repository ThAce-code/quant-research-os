import numpy as np
import pandas as pd
import pytest

from quant_research.factors.analytics import daily_ic, summarize_ic, correlation_matrix, decide_factor, exposure_report, quantile_spread


def test_ic_sign_sample_count_and_constant_days():
    x = pd.DataFrame([[1,2,3,4],[1,2,3,4],[1,1,1,1]], index=pd.date_range('2020-01-01',periods=3))
    y = pd.DataFrame([[4,3,2,1],[1,2,3,np.nan],[1,2,3,4]], index=x.index)
    d = daily_ic(x,y,min_pairs=3)
    assert d.ic.iloc[0] == pytest.approx(-1)
    assert d.rank_ic.iloc[1] == pytest.approx(1)
    assert d.n.iloc[1] == 3
    assert np.isnan(d.ic.iloc[2])
    s = summarize_ic(d)
    assert s['ic'] == pytest.approx(0)
    assert s['ic_std'] == pytest.approx(np.sqrt(2))
    assert s['positive_ic_ratio'] == .5
    assert s['days'] == 2


def test_correlation_is_daily_cross_section_not_pooled_time():
    x = pd.DataFrame([[1,2,3],[100,200,300]])
    y = pd.DataFrame([[3,2,1],[300,200,100]])
    corr = correlation_matrix({'x':x,'y':y},min_pairs=3)
    assert corr.loc['x','y'] == pytest.approx(-1)


def test_exposure_missing_is_null_and_not_zero():
    x = pd.DataFrame([[1,2,3],[3,2,1]])
    report = exposure_report(x, {'volatility': x}, min_pairs=3)
    assert report['size']['value'] is None
    assert report['industry']['status'] == 'MISSING_DATA'
    assert report['volatility']['value'] == pytest.approx(1)


def test_decision_uses_only_validation_and_preserves_reasons():
    rules={'min_coverage':.7,'min_days':100,'min_rank_ic':.01,'min_positive_ratio':.5,'max_pool_corr':.9}
    valid={'coverage':.9,'days':400,'rank_ic':.02,'positive_rank_ic_ratio':.6,'net_excess_annual':.05}
    status, reasons = decide_factor(valid,rules,['size','industry'],None)
    assert status=='FORWARD' and 'missing_exposure:size' in reasons
    bad={**valid,'rank_ic':-.02}
    assert decide_factor(bad,rules,[],.1)[0]=='REJECT'
    assert decide_factor(valid,rules,[],.99)[0]=='REJECT'
    assert decide_factor(valid,rules,[],.1)[0]=='KEEP'
    assert decide_factor({**valid,'rank_ic':None},rules,[],None)[0]=='REJECT'


def test_long_short_is_mean_forward_spread_without_compounding():
    x=pd.DataFrame([[1,2,3,4,5]])
    y=pd.DataFrame([[.1,.2,.3,.4,.5]])
    result=quantile_spread(x,y,.2,min_pairs=5)
    assert result.long_short.iloc[0]==pytest.approx(.4)
    assert result.top.iloc[0]==.5 and result.bottom.iloc[0]==.1
