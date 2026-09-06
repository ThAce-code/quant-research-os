import pandas as pd
from quant_research.baseline import purged_segments, validate_outputs
import numpy as np
import pytest


def test_last_two_label_dates_do_not_cross_partition_boundary():
    calendar = pd.bdate_range('2014-12-22', '2017-01-10')
    segments = {'train': ['2014-12-22', '2014-12-31'],
                'valid': ['2015-01-01', '2016-12-31'],
                'test': ['2017-01-01', '2017-01-06']}
    result = purged_segments(segments, calendar)
    assert result['train'][1] == '2014-12-29'
    assert result['valid'][1] == '2016-12-28'
    assert result['test'] == segments['test']


def test_failed_or_incomplete_backtest_cannot_be_reported_as_pass():
    index = pd.MultiIndex.from_product([pd.to_datetime(['2020-01-02']), ['SH600000']], names=['datetime', 'instrument'])
    predictions = pd.DataFrame({'score': [0.2]}, index=index)
    labels = pd.DataFrame({'LABEL0': [0.01]}, index=index)
    report = pd.DataFrame({'return': [0.01], 'bench': [0.005], 'cost': [0.001], 'turnover': [0.2]}, index=pd.to_datetime(['2020-01-02']))
    validate_outputs(predictions, labels, report, pd.to_datetime(['2020-01-02']))
    with pytest.raises(ValueError, match='coverage'):
        validate_outputs(predictions, labels, report, pd.to_datetime(['2020-01-02', '2020-01-03']))
    report.loc[:, 'cost'] = np.nan
    with pytest.raises(ValueError, match='nonfinite'):
        validate_outputs(predictions, labels, report, pd.to_datetime(['2020-01-02']))


def test_prediction_alignment_and_zero_cost_trading_are_rejected():
    days = pd.to_datetime(['2020-01-02', '2020-01-03'])
    index = pd.MultiIndex.from_product([days, ['SH600000']], names=['datetime', 'instrument'])
    pred = pd.DataFrame({'score': [.2, .3]}, index=index)
    labels = pd.DataFrame({'LABEL0': [.01, .02]}, index=index)
    report = pd.DataFrame({'return': [.01, .01], 'bench': [.005, .005], 'cost': [.001, .001], 'turnover': [.2, .2]}, index=days)
    with pytest.raises(ValueError, match='prediction.*coverage'):
        validate_outputs(pred.iloc[:1], labels.iloc[:1], report, days)
    with pytest.raises(ValueError, match='alignment'):
        validate_outputs(pred, labels.iloc[:1], report, days)
    report['cost'] = 0
    with pytest.raises(ValueError, match='cost'):
        validate_outputs(pred, labels, report, days)
