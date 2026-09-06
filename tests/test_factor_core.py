import json

import numpy as np
import pandas as pd
import pytest

from quant_research.factors.expressions import Expression, FactorDefinition
from quant_research.factors.data import FactorData, forward_labels, load_factor_data, preprocess
from quant_research.integrity import seal_dataset


def panel(values):
    return pd.DataFrame({'A': values}, index=pd.bdate_range('2020-01-01', periods=len(values)))


def test_historical_lag_and_rolling_are_causal():
    close = panel([1., 2., 4., 8., 16.])
    result = Expression('close / Ref(close, 2) - 1').evaluate({'close': close})
    assert result.A.iloc[:2].isna().all()
    assert result.A.iloc[2:].tolist() == [3., 3., 3.]
    assert Expression('Mean(close, 3)').evaluate({'close': close}).A.iloc[2] == pytest.approx(7 / 3)
    changed = close.copy(); changed.iloc[4] = 99999
    pd.testing.assert_frame_equal(result.iloc[:4], Expression('close / Ref(close, 2) - 1').evaluate({'close': changed}).iloc[:4])


@pytest.mark.parametrize('expression', ['Ref(close,-1)', 'close.shift(-1)', '__import__("os")', 'Mean(close,0)', 'Ref(close,10000)', 'close[0]', 'unknown + close', 'Mean(close, 2.5)'])
def test_reject_future_or_arbitrary_expressions(expression):
    with pytest.raises(ValueError):
        Expression(expression)


def test_missing_window_and_zero_division_stay_missing():
    close = panel([1., np.nan, 3., 0., 5.])
    assert Expression('Mean(close,3)').evaluate({'close': close}).A.iloc[2:4].isna().all()
    assert np.isnan(Expression('close / Ref(close,1)').evaluate({'close': close}).A.iloc[4])


def test_label_uses_next_close_and_purges_full_horizon():
    close = panel([1., 2., 4., 8., 16., 32., 64.])
    member = close.notna(); member.iloc[1] = False
    data = FactorData({'close': close}, member, close.notna(), close.A)
    labels = forward_labels(data, 2, [str(close.index[0].date()), str(close.index[4].date())])
    assert labels.A.iloc[0] == 3
    assert np.isnan(labels.A.iloc[1])  # absent from historical universe at signal date
    assert labels.A.iloc[2:].isna().all()  # exits would cross split end
    data.tradable.iloc[1] = False
    assert np.isnan(forward_labels(data, 2, [close.index[0], close.index[-1]]).A.iloc[0])


def test_processing_is_same_day_and_excludes_nonmembers():
    raw = pd.DataFrame([[1., 2., 1000.], [4., 5., 6.]], columns=list('ABC'))
    member = raw.notna(); member.loc[0, 'C'] = False
    out = preprocess(raw, member)
    assert out.loc[0,'A'] == pytest.approx(-1)
    assert out.loc[0,'B'] == pytest.approx(1)
    assert np.isnan(out.loc[0,'C'])
    raw.loc[1] = [10000.,-1000.,2.]
    pd.testing.assert_series_equal(out.loc[0], preprocess(raw, member).loc[0])


def test_factor_identity_requires_direction_and_valid_expression():
    with pytest.raises(ValueError):
        FactorDefinition('BAD', 'family', 'Ref(close,-1)', 'hypothesis')
    with pytest.raises(ValueError):
        FactorDefinition('BAD', 'family', 'close', 'hypothesis', direction=0)


def test_expression_cross_section_rank_uses_historical_universe():
    close = pd.DataFrame([[1., 2., 100.]], columns=list('ABC'))
    members = pd.DataFrame([[True, True, False]], columns=close.columns)
    rank = Expression('Rank(close)').evaluate({'close':close}, membership=members)
    assert rank.loc[0,'A']==.5 and rank.loc[0,'B']==1
    assert np.isnan(rank.loc[0,'C'])


def sealed_execution_fixture(root, changes, limit_threshold=0.095):
    """Small, sealed canonical bars; benchmark has no manufactured limit data."""
    calendar = pd.bdate_range('2020-01-01', periods=len(changes))
    config = {
        'name': 'execution-fixture',
        'data_start': str(calendar[0].date()), 'data_end': str(calendar[-1].date()),
        'segments': {'train': [str(calendar[0].date()), str(calendar[-1].date())]},
        'backtest': {'exchange_kwargs': {'limit_threshold': limit_threshold}},
    }
    canonical = root / 'data' / 'canonical' / config['name']
    canonical.mkdir(parents=True)
    pd.DataFrame({'datetime': calendar}).to_parquet(canonical / 'calendar.parquet')
    symbols = ['SH600000', 'SZ000001']
    pd.DataFrame({'instrument': symbols, 'start': calendar[0], 'end': calendar[-1]}).to_parquet(canonical / 'membership.parquet')
    for stock, change in zip(symbols, [changes, [0.01] * len(changes)]):
        close = 100 * np.cumprod(1 + np.asarray(change))
        if stock == symbols[1]:
            close = close * 2
        frame = pd.DataFrame({
            'datetime': calendar, 'instrument': stock,
            'open': close, 'high': close, 'low': close, 'close': close,
            'factor': 1.0, 'volume': 1000.0, 'turnover': 2.0,
            'is_suspended': False, 'change': change,
        })
        frame.to_parquet(canonical / f'{stock}.parquet')
    pd.DataFrame({'datetime': calendar, 'close': np.arange(len(calendar)) + 100.0}).to_parquet(canonical / 'SH000300.parquet')
    manifest = {'data_config': {key: config[key] for key in ['name', 'data_start', 'data_end', 'segments']},
                'bars': [{'instrument': stock} for stock in symbols + ['SH000300']]}
    (canonical / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    seal_dataset(canonical)
    return config, calendar, canonical


@pytest.mark.parametrize('endpoint', [1, 3], ids=['entry', 'exit'])
@pytest.mark.parametrize('change', [0.095, -0.095, 0.10, -0.10], ids=['limit_up', 'limit_down', 'above_up', 'below_down'])
def test_forward_label_excludes_both_directions_at_either_limit_endpoint(tmp_path, endpoint, change):
    changes = [0.01] * 7
    changes[endpoint] = change
    config, calendar, _ = sealed_execution_fixture(tmp_path, changes)
    data = load_factor_data(tmp_path, config)
    labels = forward_labels(data, 2, [calendar[0], calendar[-1]])
    assert np.isnan(labels.loc[calendar[0], 'SH600000'])
    assert labels.loc[calendar[0], 'SZ000001'] == pytest.approx(1.01 ** 2 - 1)
    assert data.tradable.loc[calendar[endpoint], 'SH600000']
    assert data.fields['close'].loc[calendar[endpoint], 'SH600000'] > 0
    assert not data.execution_eligible.loc[calendar[endpoint], 'SH600000']


def test_limit_signal_day_keeps_scores_when_future_endpoints_are_eligible(tmp_path):
    config, calendar, _ = sealed_execution_fixture(tmp_path, [0.095, 0.01, 0.01, 0.01, 0.01])
    data = load_factor_data(tmp_path, config)
    scores = preprocess(data.fields['close'], data.membership & data.tradable)
    assert scores.loc[calendar[0], 'SH600000'] == pytest.approx(-1.0)
    assert not data.execution_eligible.loc[calendar[0], 'SH600000']
    assert forward_labels(data, 2, [calendar[0], calendar[-1]]).loc[calendar[0], 'SH600000'] == pytest.approx(1.01 ** 2 - 1)


def test_execution_eligibility_uses_frozen_threshold_and_source_change(tmp_path):
    config, calendar, canonical = sealed_execution_fixture(tmp_path, [0.0, 0.08, -0.08, 0.079, -0.079], limit_threshold=0.08)
    path = canonical / 'SH600000.parquet'
    frame = pd.read_parquet(path)
    frame.loc[3:, 'factor'] = 2.0  # adjustment changes do not define an exchange limit
    frame.to_parquet(path)
    seal_dataset(canonical)
    data = load_factor_data(tmp_path, config)
    assert data.execution_eligible['SH600000'].tolist() == [True, False, False, True, True]
    assert data.tradable['SH600000'].all()


def test_future_execution_flags_never_change_earlier_scores_or_cross_split_labels(tmp_path):
    changes = [0.01] * 8
    config, calendar, canonical = sealed_execution_fixture(tmp_path, changes)
    original = load_factor_data(tmp_path, config)
    original_scores = preprocess(original.fields['close'], original.membership & original.tradable)
    original_labels = forward_labels(original, 2, [calendar[0], calendar[5]])
    path = canonical / 'SH600000.parquet'
    frame = pd.read_parquet(path)
    frame.loc[6:, 'change'] = [0.095, -0.095]
    frame.loc[6:, ['open', 'high', 'low', 'close']] = 10000.0
    frame.to_parquet(path)
    seal_dataset(canonical)
    modified = load_factor_data(tmp_path, config)
    modified_scores = preprocess(modified.fields['close'], modified.membership & modified.tradable)
    modified_labels = forward_labels(modified, 2, [calendar[0], calendar[5]])
    pd.testing.assert_frame_equal(original_scores.iloc[:6], modified_scores.iloc[:6])
    pd.testing.assert_frame_equal(original_labels, modified_labels)
    assert modified_labels.iloc[3:].isna().all().all()  # full-horizon exits cross split end
    assert not modified.execution_eligible.iloc[6:]['SH600000'].any()
