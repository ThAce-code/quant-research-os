"""Costed M1 ranking portfolios executed by the caller's initialized Qlib."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd


TRADING_DAYS = 238
REPORT_COLUMNS = ['return', 'bench', 'cost', 'turnover']


def _validate_dates(index, label):
    if (not isinstance(index, pd.DatetimeIndex) or index.empty or index.hasnans
            or index.has_duplicates or not index.is_monotonic_increasing):
        raise ValueError(f'{label} dates must be nonempty, unique, ordered datetimes')


def portfolio_metrics(report: pd.DataFrame) -> dict:
    """Summarize Qlib's gross daily returns and explicit transaction costs.

    ``drawdown_convention`` is initial-capital-inclusive: net NAV starts at
    1.0, while cumulative arithmetic excess starts at 0.0. Negative values
    indicate drawdown. Excess annualization uses 238 days and sample standard
    deviation (ddof=1); an undefined information ratio is returned as None.
    Qlib's ``return`` is gross of the separately reported ``cost``.
    """
    if report.empty:
        raise ValueError('empty portfolio report')
    _validate_dates(report.index, 'portfolio report')
    if not set(REPORT_COLUMNS).issubset(report.columns):
        raise ValueError('missing portfolio report columns')
    values = report[REPORT_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('nonfinite backtest values')
    gross, bench, cost, turnover = values.T
    if np.any(turnover < 0):
        raise ValueError('negative portfolio turnover')
    if np.any(cost < 0) or np.any(cost[turnover > 0] <= 0):
        raise ValueError('trading days must incur positive costs')

    net = gross - cost
    if np.any(net <= -1):
        raise ValueError('daily net return must be greater than -100%')
    excess = net - bench
    with np.errstate(over='ignore', invalid='ignore'):
        nav = np.r_[1.0, np.cumprod(1.0 + net)]
        cumulative_excess = np.r_[0.0, np.cumsum(excess)]
        standard_deviation = float(excess.std(ddof=1)) if len(excess) > 1 and np.ptp(excess) > 0 else 0.0
        metrics = {
            'gross_return': float(np.prod(1.0 + gross) - 1.0),
            'net_return': float(nav[-1] - 1.0),
            'net_cagr': float(nav[-1] ** (TRADING_DAYS / len(net)) - 1.0),
            'net_mdd': float(np.min(nav / np.maximum.accumulate(nav) - 1.0)),
            'net_excess_annual': float(excess.mean() * TRADING_DAYS),
            'net_excess_ir': (
                float(excess.mean() / standard_deviation * np.sqrt(TRADING_DAYS))
                if standard_deviation > 0 else None
            ),
            'net_excess_mdd': float(np.min(cumulative_excess - np.maximum.accumulate(cumulative_excess))),
            'gross_excess_annual': float((gross - bench).mean() * TRADING_DAYS),
            'mean_turnover': float(turnover.mean()),
            'annual_cost_drag': float(cost.mean() * TRADING_DAYS),
            'test_days': len(report),
        }
    if not all(np.isfinite(value) for value in metrics.values() if value is not None):
        raise ValueError('nonfinite portfolio metrics')
    return metrics


def run_portfolios(
    scores: pd.DataFrame,
    start,
    end,
    backtest_config: dict,
    output: Path,
    expected_dates: pd.DatetimeIndex,
) -> dict:
    """Run Top10%/20% ranking portfolios and save validated daily reports.

    The fixed CSI300 research portfolio sizes are 30 and 60; Qlib determines
    actual fills and holdings. TopkDropoutStrategy itself consumes the prior
    trading day's signal. Keep the complete score history, including the day
    before ``start``, and do not shift it a second time here. The caller owns
    Qlib initialization, including the sealed data provider and fee settings.
    """
    _validate_dates(scores.index, 'score')
    if scores.columns.has_duplicates:
        raise ValueError('duplicate score instruments')
    _validate_dates(expected_dates, 'expected backtest')
    signal = scores.rename_axis(index='datetime', columns='instrument').stack(future_stack=True).dropna().sort_index()
    signal.name = 'score'
    if signal.empty:
        raise ValueError('empty portfolio scores')
    if not np.isfinite(signal.to_numpy(dtype=float)).all():
        raise ValueError('nonfinite portfolio scores')
    from qlib.backtest import backtest

    reports, metrics = {}, {}
    for name, topk in [('top10', 30), ('top20', 60)]:
        portfolio, _ = backtest(
            start_time=start,
            end_time=end,
            strategy={
                'class': 'TopkDropoutStrategy',
                'module_path': 'qlib.contrib.strategy',
                'kwargs': {'signal': signal, 'topk': topk, 'n_drop': topk},
            },
            executor={
                'class': 'SimulatorExecutor',
                'module_path': 'qlib.backtest.executor',
                'kwargs': {'time_per_step': 'day', 'generate_portfolio_metrics': True},
            },
            **deepcopy(backtest_config),
        )
        report, _ = portfolio['1day']
        if not pd.DatetimeIndex(report.index).equals(expected_dates):
            raise ValueError(f'{name} backtest date coverage mismatch')
        metrics[name] = portfolio_metrics(report)
        reports[name] = report

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, report in reports.items():
        report.to_csv(output / f'{name}_daily.csv')
    return metrics
