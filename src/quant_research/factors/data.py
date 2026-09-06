"""Sealed market panels with explicit universe, observation and label timing."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..integrity import verify_dataset


@dataclass
class FactorData:
    """Observed panels; execution eligibility only restricts label endpoints.

    ``tradable`` retains the existing active-observation semantics for factor
    values. ``execution_eligible`` additionally applies the frozen Qlib limits;
    None preserves compatibility with manually constructed research fixtures.
    """
    fields: dict
    membership: pd.DataFrame
    tradable: pd.DataFrame
    benchmark: pd.Series
    execution_eligible: pd.DataFrame | None = None


def load_factor_data(root, baseline_config):
    root = Path(root) / 'data/canonical' / baseline_config['name']
    verify_dataset(root, baseline_config)
    calendar = pd.DatetimeIndex(pd.read_parquet(root / 'calendar.parquet').datetime)
    intervals = pd.read_parquet(root / 'membership.parquet')
    symbols = sorted(intervals.instrument.unique())
    membership = pd.DataFrame(False, index=calendar, columns=symbols)
    limit_threshold = baseline_config['backtest']['exchange_kwargs']['limit_threshold']
    frames = []
    for symbol in symbols:
        frame = pd.read_parquet(root / f'{symbol}.parquet').set_index('datetime')
        active = ~frame.is_suspended & frame.close.gt(0)
        out = pd.DataFrame(index=frame.index)
        for field in ['open', 'high', 'low', 'close']:
            out[field] = (frame[field] * frame.factor).where(active)
        out['volume'] = (frame.volume / frame.factor).where(active)
        out['turnover'] = (frame.turnover / 100).where(active)
        out['tradable'] = active
        # Match the exported float32 $change and Qlib's inclusive limits.
        # forbid_all_trade_at_limit=True blocks either direction at both limits.
        change = frame.change.astype(np.float32)
        at_limit = change.ge(limit_threshold) | change.le(-limit_threshold)
        out['execution_eligible'] = active & ~at_limit
        out['instrument'] = symbol
        frames.append(out)
    full = pd.concat(frames).reset_index()
    fields = {name: full.pivot(index='datetime', columns='instrument', values=name).reindex(index=calendar, columns=symbols)
              for name in ['open', 'high', 'low', 'close', 'volume', 'turnover']}
    fields['returns'] = fields['close'] / fields['close'].shift(1) - 1
    tradable = full.pivot(index='datetime', columns='instrument', values='tradable').reindex(index=calendar, columns=symbols).eq(True)
    execution_eligible = full.pivot(index='datetime', columns='instrument', values='execution_eligible').reindex(index=calendar, columns=symbols).eq(True)
    for row in intervals.itertuples():
        membership.loc[row.start:row.end, row.instrument] = True
    benchmark = pd.read_parquet(root / 'SH000300.parquet').set_index('datetime').close.reindex(calendar)
    return FactorData(fields, membership, tradable, benchmark, execution_eligible)


def preprocess(raw, membership):
    scores = raw.where(membership).replace([np.inf, -np.inf], np.nan)
    lo, hi = scores.quantile(.01, axis=1), scores.quantile(.99, axis=1)
    scores = scores.clip(lower=lo, upper=hi, axis=0)
    std = scores.std(axis=1, ddof=0).replace(0, np.nan)
    return scores.sub(scores.mean(axis=1), axis=0).div(std, axis=0)


def forward_labels(data, horizon, segment):
    if type(horizon) is not int or not 1 <= horizon <= 252:
        raise ValueError('label horizon must be 1..252 trading days')
    close = data.fields['close']
    labels = close.shift(-horizon - 1) / close.shift(-1) - 1
    execution = data.execution_eligible if data.execution_eligible is not None else data.tradable
    eligible = data.membership & execution.shift(-1, fill_value=False) & execution.shift(-horizon - 1, fill_value=False)
    exit_date = pd.Series(close.index, index=close.index).shift(-horizon - 1)
    eligible.loc[exit_date.isna() | exit_date.gt(pd.Timestamp(segment[1])), :] = False
    return labels.where(eligible).loc[segment[0]:segment[1]]
