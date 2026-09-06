"""Causal joins, exposure removal and date-block inference for M2."""
import numpy as np
import pandas as pd


def asof_events(events, calendar, date_column, columns, max_age=400):
    """No same-day availability; stale/latest missing values never resurrect old data.

    Events must contain one instrument only. Quarterly records are ordered by
    publication, but an older fiscal period published late cannot replace a newer
    already published period. This does not reconstruct unknown vendor revisions.
    """
    calendar = pd.DatetimeIndex(calendar)
    if calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError('calendar must be unique and ordered')
    e = events.copy()
    if 'code' in e and e.code.nunique() > 1:
        raise ValueError('one instrument per as-of join')
    if e.empty:
        return pd.DataFrame(index=calendar, columns=columns + ['age_days'])
    e[date_column] = pd.to_datetime(e[date_column], errors='raise')
    if e[date_column].isna().any():
        raise ValueError('missing availability date')
    if 'statDate' in e:
        e['statDate'] = pd.to_datetime(e.statDate, errors='raise')
        if e.statDate.isna().any() or (e.statDate > e[date_column]).any():
            raise ValueError('report period after publication')
        e = e.sort_values([date_column, 'statDate'])
        e = e[e.statDate.eq(e.statDate.cummax())]
    else:
        e = e.sort_values(date_column)
    if e.duplicated(date_column).any():
        # Same publication day for multiple periods: newest report wins.
        if 'statDate' not in e:
            raise ValueError('ambiguous availability date')
        if e.duplicated([date_column, 'statDate']).any():
            raise ValueError('ambiguous report revision')
        e = e.drop_duplicates(date_column, keep='last')
    joined = pd.merge_asof(pd.DataFrame({'signal_date': calendar}),
                          e[[date_column] + columns], left_on='signal_date',
                          right_on=date_column, allow_exact_matches=False, direction='backward')
    age = (joined.signal_date - joined[date_column]).dt.days
    result = joined[columns].copy()
    result.loc[age.gt(max_age), :] = np.nan
    result['age_days'] = age
    result.index = calendar
    return result


def circulating_cap(bars):
    """Raw volume is shares; turn is percentage. Not free-float capitalization."""
    ok = (~bars.is_suspended & bars.close.gt(0) & bars.volume.gt(0)
          & bars.turnover.ge(0.01) & bars.turnover.le(100))
    return (bars.close * bars.volume / (bars.turnover / 100)).where(ok)


def neutralize(scores, log_size, industry, min_group=5):
    """Daily OLS with intercept + centered log cap + industry indicators.

    Small groups and missing exposures are excluded, never assigned industry 0.
    Return coefficients' orthogonality error as an implementation check only.
    """
    out = scores * np.nan
    checks = []
    for date in scores.index:
        frame = pd.DataFrame({'y': scores.loc[date], 'size': log_size.loc[date],
                              'industry': industry.loc[date]}).dropna()
        frame = frame[frame.industry.map(frame.industry.value_counts()).ge(min_group)]
        if len(frame) < 30 or frame['size'].std() <= 0:
            continue
        size = (frame['size'] - frame['size'].mean()) / frame['size'].std()
        x = np.column_stack([np.ones(len(frame)), size,
                             pd.get_dummies(frame.industry, drop_first=True, dtype=float)])
        if len(frame) <= x.shape[1] + 5:
            continue
        y = frame.y.to_numpy()
        residual = y - x @ np.linalg.lstsq(x, y, rcond=None)[0]
        scale = residual.std()
        if scale <= 1e-12:
            continue
        out.loc[date, frame.index] = residual / scale
        checks.append({'date': date, 'n': len(frame),
                       'orthogonality_error': float(np.max(np.abs(x.T @ residual)) / len(frame))})
    return out, pd.DataFrame(checks)


def block_inference(series, block=20, samples=2000, seed=42):
    """Circular moving-block bootstrap; positive-mean one-sided null test."""
    values = np.asarray(series, dtype=float)
    # Keep calendar gaps in resampling to avoid compressing separated observations.
    n = len(values)
    if np.isfinite(values).sum() < max(40, block * 2):
        return {'mean': None, 'low': None, 'high': None, 'p': 1.0}
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, (samples, int(np.ceil(n / block))))
    indices = (starts[:, :, None] + np.arange(block)) % n
    draws = np.nanmean(values[indices.reshape(samples, -1)[:, :n]], axis=1)
    mean = float(np.nanmean(values))
    return {'mean': mean, 'low': float(np.nanquantile(draws, .025)),
            'high': float(np.nanquantile(draws, .975)),
            'p': float((1 + np.sum(draws - mean >= mean)) / (samples + 1))}


def bh_adjust(pvalues):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adjusted = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    result = np.empty(len(p)); result[order] = np.minimum(adjusted, 1)
    return result
