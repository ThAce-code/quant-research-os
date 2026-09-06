"""Source-faithful daily bars and observed historical membership intervals."""
import numpy as np
import pandas as pd


def canonicalize(raw: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        raise ValueError('empty daily bars')
    data = raw.copy().rename(columns={'date': 'datetime', 'turn': 'turnover'})
    data['datetime'] = pd.to_datetime(data['datetime'])
    if data.duplicated(['code', 'datetime']).any():
        raise ValueError('duplicate daily bars')
    if data.code.nunique() != 1:
        raise ValueError('expected one instrument')
    data = data.sort_values('datetime').reset_index(drop=True)
    data['instrument'] = data.code.str.replace('.', '', regex=False).str.upper()
    for col in ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount',
                'turnover', 'pctChg', 'tradestatus', 'isST']:
        data[col] = pd.to_numeric(data[col], errors='raise') if col in data else np.nan
    # Index responses do not expose a stock trading-status field.
    index = data.code.iloc[0] == 'sh.000300'
    if index:
        data['tradestatus'] = 1
        data['isST'] = 0
    elif data.tradestatus.isna().any() or data.isST.isna().any():
        raise ValueError('missing stock status')
    data['is_suspended'] = data.tradestatus.ne(1) | data.volume.fillna(0).le(0)
    active = ~data.is_suspended
    prices = data[['open', 'high', 'low', 'close']]
    if (prices.loc[active].isna().any().any()
            or prices.loc[active].le(0).any().any()
            or not np.isfinite(prices.loc[active]).all().all()):
        raise ValueError('invalid active price')
    if ((data.high < prices.max(axis=1)) | (data.low > prices.min(axis=1)))[active].any():
        raise ValueError('invalid OHLC price ordering')
    if data.loc[active, ['volume', 'amount']].isna().any().any():
        raise ValueError('missing traded volume or amount')
    if data[['volume', 'amount']].lt(0).any().any():
        raise ValueError('negative volume or amount')
    if factors.empty:
        data['factor'] = 1.0
    else:
        if set(factors.code) != set(data.code):
            raise ValueError('factor instrument mismatch')
        events = factors[['dividOperateDate', 'backAdjustFactor']].copy()
        events.columns = ['effective_date', 'factor']
        events['effective_date'] = pd.to_datetime(events.effective_date)
        events['factor'] = pd.to_numeric(events.factor, errors='raise')
        if events.effective_date.duplicated().any() or events.factor.le(0).any() or not np.isfinite(events.factor).all():
            raise ValueError('invalid adjustment factors')
        data = pd.merge_asof(data, events.sort_values('effective_date'),
                             left_on='datetime', right_on='effective_date', direction='backward')
        data['factor'] = data.factor.fillna(1.0)
        data = data.drop(columns='effective_date')
    data['change'] = data.pctChg / 100.0
    data['is_st'] = data.isST.eq(1)
    return data.drop(columns=['code', 'pctChg', 'isST'])


def membership_intervals(snapshots, calendar) -> pd.DataFrame:
    dates = [pd.Timestamp(x).strftime('%Y-%m-%d') for x in calendar]
    if [d for d, _ in snapshots] != dates:
        raise ValueError('membership coverage must match every requested trading day')
    opened, records = {}, []
    previous = None
    for date, frame in snapshots:
        if frame.empty or frame.code.duplicated().any():
            raise ValueError(f'invalid membership on {date}')
        if pd.to_datetime(frame.updateDate).gt(pd.Timestamp(date)).any():
            raise ValueError(f'future membership snapshot on {date}')
        members = set(frame.code.str.replace('.', '', regex=False).str.upper())
        for code in sorted(set(opened) - members):
            records.append((code, opened.pop(code), previous))
        for code in sorted(members - set(opened)):
            opened[code] = date
        previous = date
    records.extend((code, start, previous) for code, start in opened.items())
    return pd.DataFrame(records, columns=['instrument', 'start', 'end']).sort_values(['instrument', 'start'])
