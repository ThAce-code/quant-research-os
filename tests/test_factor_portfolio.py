"""Independent portfolio arithmetic and isolated Qlib execution tests."""

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest


def sample_report():
    return pd.DataFrame(
        {
            'return': [-0.08, 0.12, -0.03],
            'bench': [0.01, -0.02, 0.02],
            'cost': [0.01, 0.02, 0.01],
            'turnover': [0.2, 0.4, 0.2],
        },
        index=pd.bdate_range('2020-01-02', periods=3),
    )


def test_costs_compound_nav_and_arithmetic_excess_are_distinct():
    from quant_research.factors.portfolio import portfolio_metrics

    metrics = portfolio_metrics(sample_report())
    # Net daily returns: -9%, +10%, -4%. Include the initial NAV of one.
    final_nav = 0.91 * 1.10 * 0.96
    excess = np.array([-0.10, 0.12, -0.06])
    assert metrics['gross_return'] == pytest.approx(0.92 * 1.12 * 0.97 - 1)
    assert metrics['net_return'] == pytest.approx(final_nav - 1)
    assert metrics['net_cagr'] == pytest.approx(final_nav ** (238 / 3) - 1)
    assert metrics['net_mdd'] == pytest.approx(-0.09)
    assert metrics['net_excess_annual'] == pytest.approx(excess.mean() * 238)
    assert metrics['net_excess_ir'] == pytest.approx(excess.mean() / excess.std(ddof=1) * np.sqrt(238))
    assert metrics['net_excess_mdd'] == pytest.approx(-0.10)
    assert metrics['gross_excess_annual'] == pytest.approx(0.0)
    assert metrics['mean_turnover'] == pytest.approx(0.8 / 3)
    assert metrics['annual_cost_drag'] == pytest.approx(0.04 / 3 * 238)
    assert metrics['test_days'] == 3


@pytest.mark.parametrize('field', ['return', 'bench', 'cost', 'turnover'])
@pytest.mark.parametrize('invalid', [np.nan, np.inf, -np.inf])
def test_metrics_reject_nonfinite_daily_values(field, invalid):
    from quant_research.factors.portfolio import portfolio_metrics

    report = sample_report()
    report.loc[report.index[0], field] = invalid
    with pytest.raises(ValueError, match='nonfinite'):
        portfolio_metrics(report)


@pytest.mark.parametrize('cost', [0.0, -0.01])
def test_positive_turnover_requires_positive_cost(cost):
    from quant_research.factors.portfolio import portfolio_metrics

    report = sample_report()
    report.loc[report.index[0], 'cost'] = cost
    with pytest.raises(ValueError, match='cost'):
        portfolio_metrics(report)


def test_empty_and_invalid_reports_are_rejected():
    from quant_research.factors.portfolio import portfolio_metrics

    with pytest.raises(ValueError, match='empty'):
        portfolio_metrics(sample_report().iloc[:0])
    with pytest.raises(ValueError, match='column'):
        portfolio_metrics(sample_report().drop(columns='cost'))
    report = sample_report()
    report.iloc[0, report.columns.get_loc('turnover')] = -0.01
    with pytest.raises(ValueError, match='turnover'):
        portfolio_metrics(report)
    report = sample_report()
    report.iloc[0, report.columns.get_loc('return')] = -1.0
    with pytest.raises(ValueError, match='net return'):
        portfolio_metrics(report)


@pytest.mark.parametrize('periods', [1, 3])
@pytest.mark.parametrize('daily_return', [0.0, 0.1])
def test_undefined_ir_is_null_and_idle_days_need_no_cost(periods, daily_return):
    from quant_research.factors.portfolio import portfolio_metrics

    report = pd.DataFrame(
        {'return': daily_return, 'bench': 0.0, 'cost': 0.0, 'turnover': 0.0},
        index=pd.bdate_range('2020-01-02', periods=periods),
    )
    metrics = portfolio_metrics(report)
    assert metrics['net_excess_ir'] is None
    assert metrics['net_return'] == pytest.approx((1 + daily_return) ** periods - 1)
    assert metrics['net_mdd'] == metrics['annual_cost_drag'] == 0


@pytest.mark.parametrize('problem', ['duplicate', 'unsorted', 'not_datetime', 'nat'])
def test_report_dates_must_be_unique_ordered_datetimes(problem):
    from quant_research.factors.portfolio import portfolio_metrics

    report = sample_report()
    if problem == 'duplicate':
        report.index = [report.index[0], report.index[0], report.index[2]]
    elif problem == 'unsorted':
        report = report.iloc[::-1]
    elif problem == 'not_datetime':
        report.index = [1, 2, 3]
    else:
        report.index = [report.index[0], pd.NaT, report.index[2]]
    with pytest.raises(ValueError, match='date'):
        portfolio_metrics(report)


@pytest.mark.parametrize('problem', ['duplicate_dates', 'duplicate_instruments', 'empty', 'all_missing', 'infinite'])
def test_invalid_scores_are_rejected_before_backtest(monkeypatch, tmp_path, problem):
    from quant_research.factors.portfolio import run_portfolios
    import qlib.backtest

    scores = pd.DataFrame({'SH600000': [1.0, 2.0, 3.0]}, index=sample_report().index)
    if problem == 'duplicate_dates':
        scores.index = [scores.index[0], scores.index[0], scores.index[2]]
    elif problem == 'duplicate_instruments':
        scores = pd.concat([scores, scores], axis=1)
    elif problem == 'empty':
        scores = scores.iloc[:0]
    elif problem == 'all_missing':
        scores[:] = np.nan
    else:
        scores.iloc[0, 0] = np.inf

    def never_backtest(**kwargs):
        pytest.fail('invalid input reached Qlib backtest')

    monkeypatch.setattr(qlib.backtest, 'backtest', never_backtest)
    with pytest.raises(ValueError, match='score|date|instrument'):
        run_portfolios(scores, '2020-01-02', '2020-01-06', backtest_config(), tmp_path, sample_report().index)


def test_duplicate_expected_dates_are_rejected_before_backtest(monkeypatch, tmp_path):
    from quant_research.factors.portfolio import run_portfolios
    import qlib.backtest

    dates = sample_report().index
    scores = pd.DataFrame({'SH600000': [1.0, 2.0, 3.0]}, index=dates)

    def never_backtest(**kwargs):
        pytest.fail('invalid calendar reached Qlib backtest')

    monkeypatch.setattr(qlib.backtest, 'backtest', never_backtest)
    with pytest.raises(ValueError, match='date'):
        run_portfolios(scores, dates[0], dates[-1], backtest_config(), tmp_path, dates[[0, 0, 2]])


def backtest_config():
    return {
        'account': 100_000,
        'benchmark': 'SH000300',
        'exchange_kwargs': {
            'limit_threshold': 0.095, 'deal_price': 'close',
            'open_cost': 0.0005, 'close_cost': 0.0015, 'min_cost': 5,
        },
    }


def test_portfolios_pass_all_scores_and_fixed_strategy_to_qlib(monkeypatch, tmp_path):
    from quant_research.factors.portfolio import run_portfolios
    import qlib.backtest

    report = sample_report()
    dates = pd.bdate_range('2020-01-01', periods=5)
    scores = pd.DataFrame({'SH600000': [1, 2, 3, 4, 5], 'SZ000001': [np.nan, 3, 2, 1, 0]}, index=dates)
    original_scores = scores.copy(deep=True)
    config = backtest_config()
    original_config = deepcopy(config)
    calls = []

    def fake_backtest(**kwargs):
        calls.append(kwargs)
        return {'1day': (report, {})}, {}

    monkeypatch.setattr(qlib.backtest, 'backtest', fake_backtest)
    metrics = run_portfolios(scores, dates[1], dates[3], config, tmp_path, report.index)
    assert set(metrics) == {'top10', 'top20'}
    assert [call['strategy']['kwargs']['topk'] for call in calls] == [30, 60]
    assert [call['strategy']['kwargs']['n_drop'] for call in calls] == [30, 60]
    for name, call in zip(('top10', 'top20'), calls):
        assert call['strategy']['class'] == 'TopkDropoutStrategy'
        assert call['strategy']['module_path'] == 'qlib.contrib.strategy'
        signal = call['strategy']['kwargs']['signal']
        assert isinstance(signal, pd.Series)
        assert signal.name == 'score'
        assert signal.index.names == ['datetime', 'instrument']
        assert signal.loc[(dates[0], 'SH600000')] == 1  # prior-day score survives
        assert signal.loc[(dates[4], 'SH600000')] == 5  # caller's complete history survives
        assert len(signal) == 9  # missing values are omitted, never imputed
        assert call['exchange_kwargs'] == original_config['exchange_kwargs']
        assert call['benchmark'] == original_config['benchmark']
        assert call['account'] == original_config['account']
        assert call['executor']['kwargs']['generate_portfolio_metrics'] is True
        stored = pd.read_csv(tmp_path / f'{name}_daily.csv', index_col=0, parse_dates=True)
        pd.testing.assert_frame_equal(stored, report, check_freq=False)
    assert config == original_config
    pd.testing.assert_frame_equal(scores, original_scores)


@pytest.mark.parametrize('problem', ['missing_day', 'extra_day', 'nonfinite', 'no_cost'])
def test_invalid_qlib_output_is_not_accepted(monkeypatch, tmp_path, problem):
    from quant_research.factors.portfolio import run_portfolios
    import qlib.backtest

    report = sample_report()
    expected = report.index
    scores = pd.DataFrame({'SH600000': [1.0, 2.0, 3.0]}, index=expected)
    if problem == 'missing_day':
        report = report.iloc[1:]
    elif problem == 'extra_day':
        report = pd.concat([report, report.iloc[-1:].set_axis([pd.Timestamp('2020-01-07')])])
    elif problem == 'nonfinite':
        report.iloc[0, report.columns.get_loc('return')] = np.inf
    else:
        report['cost'] = 0.0
    monkeypatch.setattr(qlib.backtest, 'backtest', lambda **kwargs: ({'1day': (report, {})}, {}))
    with pytest.raises(ValueError, match='coverage|nonfinite|cost'):
        run_portfolios(scores, expected[0], expected[-1], backtest_config(), tmp_path, expected)
    assert not list(tmp_path.glob('*_daily.csv'))


def test_real_qlib_uses_prior_day_scores_at_next_close(tmp_path):
    # Qlib config and its provider cache are process-global. The subprocess can
    # only see its temporary provider, never the production dataset.
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), '--qlib-probe', str(tmp_path)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ('top10', 'top20'):
        report = pd.read_csv(tmp_path / 'output' / f'{name}_daily.csv', index_col=0, parse_dates=True)
        assert list(report.index) == list(pd.to_datetime(['2020-01-02', '2020-01-03', '2020-01-06']))
        assert report['turnover'].iloc[0] == pytest.approx(0.95)
        assert report['cost'].iloc[0] == pytest.approx(0.000475)
        assert report['return'].iloc[0] == pytest.approx(0.0, abs=1e-12)
        assert 0.009 < report['return'].iloc[1] < 0.010
        assert 0.018 < report['return'].iloc[2] < 0.020
        assert report.loc[report.turnover > 0, 'cost'].gt(0).all()


def _run_isolated_qlib_probe(root):
    import qlib
    from quant_research.factors.portfolio import run_portfolios

    provider = root / 'provider'
    days = pd.bdate_range('2020-01-01', periods=6)
    (provider / 'calendars').mkdir(parents=True)
    (provider / 'instruments').mkdir()
    (provider / 'calendars' / 'day.txt').write_text('\n'.join(days.strftime('%Y-%m-%d')) + '\n', encoding='utf-8')
    closes = {
        'SH600000': [10, 10, 10.1, 10.1, 10.1, 10.1],
        'SZ000001': [10, 10, 10, 10.2, 10.2, 10.2],
        'SH000300': [10] * 6,
    }
    listing = ''.join(f'{stock}\t2020-01-01\t2020-01-08\n' for stock in closes)
    (provider / 'instruments' / 'all.txt').write_text(listing, encoding='utf-8')
    for stock, values in closes.items():
        directory = provider / 'features' / stock.lower()
        directory.mkdir(parents=True)
        close = np.array(values, dtype=float)
        fields = {
            'close': close, 'open': close, 'high': close, 'low': close,
            'volume': np.repeat(1_000_000.0, 6), 'factor': np.ones(6),
            'change': np.r_[0.0, close[1:] / close[:-1] - 1],
        }
        for field, values in fields.items():
            np.r_[0.0, values].astype('<f4').tofile(directory / f'{field}.day.bin')
    qlib.init(provider_uri=str(provider), region='cn', kernels=1,
              expression_cache=None, dataset_cache=None)
    # Day 0 chooses A, day 1 chooses B, day 2 chooses A. A rises on day 2
    # and B on day 3: only close t+1 execution earns those particular returns.
    scores = pd.DataFrame(
        {'SH600000': [1, np.nan, 1, np.nan], 'SZ000001': [np.nan, 1, np.nan, 1]},
        index=days[:4],
    )
    run_portfolios(scores, days[1], days[3], backtest_config(), root / 'output', days[1:4])


if __name__ == '__main__' and sys.argv[1] == '--qlib-probe':
    _run_isolated_qlib_probe(Path(sys.argv[2]))
