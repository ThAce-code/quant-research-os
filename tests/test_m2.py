import numpy as np
import pandas as pd
import pytest
from quant_research.m2.core import asof_events, circulating_cap, neutralize, block_inference, bh_adjust


def test_publication_day_not_available_and_future_changes_do_not_leak():
    dates = pd.bdate_range('2020-04-01', '2020-04-20')
    events = pd.DataFrame({'pubDate': ['2020-04-03', '2020-04-15'],
                           'statDate': ['2019-12-31', '2020-03-31'], 'roe': [.1, .2]})
    a = asof_events(events, dates, 'pubDate', ['roe'])
    assert np.isnan(a.loc['2020-04-03', 'roe'])
    assert a.loc['2020-04-06', 'roe'] == .1
    events.loc[1, 'roe'] = 999
    b = asof_events(events, dates, 'pubDate', ['roe'])
    pd.testing.assert_frame_equal(a.loc[:'2020-04-15'], b.loc[:'2020-04-15'])


def test_old_report_and_missing_latest_and_staleness():
    dates = pd.bdate_range('2020-04-01', '2020-04-30')
    e = pd.DataFrame({'pubDate': ['2020-04-02', '2020-04-06', '2020-04-10'],
                      'statDate': ['2020-03-31', '2019-12-31', '2020-03-31'], 'x': [1, 9, np.nan]})
    a = asof_events(e, dates, 'pubDate', ['x'], max_age=5)
    assert a.loc['2020-04-07', 'x'] == 1
    assert np.isnan(a.loc['2020-04-08', 'x'])
    assert np.isnan(a.loc['2020-04-13', 'x'])


def test_asof_rejects_ambiguous_and_invalid_events():
    dates = pd.bdate_range('2020-04-01', periods=10)
    with pytest.raises(ValueError):
        asof_events(pd.DataFrame({'pubDate':['2020-04-02'], 'statDate':['2020-06-30'], 'x':[1]}), dates, 'pubDate', ['x'])
    with pytest.raises(ValueError):
        asof_events(pd.DataFrame({'d':['2020-04-02']*2, 'x':[1,2]}), dates, 'd', ['x'])


def test_cap_units_and_tiny_turnover():
    bars = pd.DataFrame({'close':[10]*3, 'volume':[1000]*3, 'turnover':[1, 0, .001], 'is_suspended':[False]*3})
    cap = circulating_cap(bars)
    assert cap.iloc[0] == 1000000
    assert cap.iloc[1:].isna().all()


def test_neutralization_removes_known_exposures_and_preserves_missing():
    rng = np.random.default_rng(42)
    dates = pd.date_range('2020-01-01', periods=2)
    size = pd.DataFrame(rng.normal(size=(2,100)), index=dates)
    industry = pd.DataFrame([['A']*50+['B']*50]*2, index=dates)
    scores = 3*size + (industry == 'B')*5 + rng.normal(size=(2,100))
    scores.iloc[0,0] = np.nan
    out, check = neutralize(scores, size, industry)
    assert np.isnan(out.iloc[0,0])
    assert check.orthogonality_error.max() < 1e-10
    assert out.corrwith(size, axis=1).abs().max() < 1e-10
    prefix, _ = neutralize(scores.iloc[:1], size.iloc[:1], industry.iloc[:1])
    pd.testing.assert_frame_equal(out.iloc[:1], prefix)


def test_block_inference_and_multiple_testing():
    positive = block_inference(np.full(100, .01))
    negative = block_inference(np.full(100, -.01))
    assert positive['low'] > 0 and positive['p'] < .01
    assert negative['high'] < 0 and negative['p'] > .9
    assert block_inference([np.nan]*100)['p'] == 1
    np.testing.assert_allclose(bh_adjust([.01,.04,.03]), [.03,.04,.04])


def test_qlib_float32_benchmark_csv_readback(tmp_path):
    from quant_research.factors.portfolio import portfolio_metrics
    dates = pd.bdate_range('2020-01-01', periods=100)
    rng = np.random.default_rng(5)
    frame = pd.DataFrame({'return': rng.normal(.001,.01,100),
                          'bench': rng.normal(.001,.01,100).astype(np.float32),
                          'cost': np.full(100,.0001), 'turnover': np.full(100,.1)}, index=dates)
    original = portfolio_metrics(frame)
    path = tmp_path/'daily.csv'; frame.to_csv(path)
    restored = pd.read_csv(path,index_col=0,parse_dates=True,dtype={'bench':np.float32})
    assert abs(portfolio_metrics(restored)['net_excess_annual']-original['net_excess_annual']) < 1e-12
