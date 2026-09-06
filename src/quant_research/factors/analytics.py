"""Cross-sectional diagnostics and predeclared validation-only decisions."""
import numpy as np
import pandas as pd


def number(value):
    return float(value) if value is not None and np.isfinite(value) else None


def daily_ic(scores, labels, min_pairs=30):
    x, y = scores.align(labels, join='inner')
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x.where(valid), y.where(valid)
    n = valid.sum(axis=1)
    usable = n.ge(min_pairs) & x.std(axis=1).gt(0) & y.std(axis=1).gt(0)
    ic = x.corrwith(y, axis=1).where(usable)
    ric = x.rank(axis=1).corrwith(y.rank(axis=1), axis=1).where(usable)
    return pd.DataFrame({'ic': ic, 'rank_ic': ric, 'n': n})


def summarize_ic(daily):
    result = {'days': int(daily.ic.notna().sum()), 'pairs': int(daily.n.sum())}
    for col, ratio in [('ic','icir'), ('rank_ic','rank_icir')]:
        values = daily[col].dropna()
        mean, std = values.mean(), values.std(ddof=1)
        result[col] = number(mean)
        result[col + '_std'] = number(std)
        result[ratio] = number(mean / std) if std > 0 else None
        result['positive_' + col + '_ratio'] = number(values.gt(0).mean())
    return result


def correlation_matrix(factors, min_pairs=30):
    names = list(factors)
    matrix = pd.DataFrame(np.nan, index=names, columns=names)
    for i, a in enumerate(names):
        for b in names[i:]:
            value = daily_ic(factors[a], factors[b], min_pairs).rank_ic.mean()
            matrix.loc[a,b] = matrix.loc[b,a] = value
    return matrix


def exposure_report(scores, available, min_pairs=30):
    result = {}
    for name in ['size', 'industry', 'volatility', 'turnover']:
        if name not in available:
            result[name] = {'status':'MISSING_DATA', 'value':None,
                            'reason':f'No sealed point-in-time {name} observations in this dataset'}
        else:
            daily = daily_ic(scores, available[name], min_pairs)
            value = number(daily.rank_ic.mean())
            result[name] = {'status':'AVAILABLE' if value is not None else 'INSUFFICIENT_DATA',
                            'value':value, 'days':int(daily.rank_ic.notna().sum()),
                            'method':'mean daily cross-sectional Spearman correlation'}
    return result


def decide_factor(validation, rules, missing_exposures, corr_existing_pool):
    checks = [('coverage', 'min_coverage'), ('days', 'min_days'),
              ('rank_ic', 'min_rank_ic'), ('positive_rank_ic_ratio', 'min_positive_ratio')]
    reasons = []
    for metric, threshold in checks:
        value = validation.get(metric)
        if value is None or not np.isfinite(value) or value < rules[threshold]:
            reasons.append('validation_gate:' + metric)
    net = validation.get('net_excess_annual')
    if net is None or not np.isfinite(net) or net <= 0:
        reasons.append('validation_gate:net_excess_annual')
    if corr_existing_pool is not None and abs(corr_existing_pool) >= rules['max_pool_corr']:
        reasons.append('redundant_with_existing_keep_pool')
    if reasons:
        return 'REJECT', reasons
    reasons = ['missing_exposure:' + name for name in missing_exposures]
    if corr_existing_pool is None:
        reasons.append('existing_keep_pool_unavailable')
    return ('FORWARD', reasons) if reasons else ('KEEP', ['all_validation_gates_passed'])


def quantile_spread(scores, labels, fraction=.2, min_pairs=30):
    if not 0 < fraction <= .5:
        raise ValueError('quantile fraction must be in (0,.5]')
    x, y = scores.align(labels, join='inner')
    # Form groups from observable scores before looking at forward-label availability.
    rank = x.rank(axis=1, method='first', ascending=False)
    count = x.notna().sum(axis=1)
    k = np.ceil(count * fraction)
    top = y.where(rank.le(k, axis=0)).mean(axis=1)
    bottom = y.where(rank.gt(count - k, axis=0)).mean(axis=1)
    usable = (x.notna() & y.notna()).sum(axis=1).ge(min_pairs)
    return pd.DataFrame({'top':top.where(usable), 'bottom':bottom.where(usable),
                         'long_short':(top-bottom).where(usable),
                         'top_labels':y.where(rank.le(k,axis=0)).notna().sum(axis=1),
                         'bottom_labels':y.where(rank.gt(count-k,axis=0)).notna().sum(axis=1)})
