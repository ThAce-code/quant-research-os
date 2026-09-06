"""Export documented Qlib little-endian float32 day bins without vendor edits."""
from pathlib import Path
import numpy as np
import pandas as pd


def export_instrument(frame, calendar, output):
    instrument = frame.instrument.iloc[0]
    folder = Path(output) / 'features' / instrument.lower()
    folder.mkdir(parents=True, exist_ok=True)
    first = calendar.searchsorted(frame.datetime.min())
    last = calendar.searchsorted(frame.datetime.max())
    data = frame.set_index('datetime').reindex(calendar[first:last + 1]).copy()
    active = ~data.is_suspended.fillna(True).astype(bool)
    scale = (data.loc[active, 'close'] * data.loc[active, 'factor']).iloc[0]
    normalized_factor = data.factor / scale
    fields = {'factor': normalized_factor, 'volume': data.volume / normalized_factor,
              'amount': data.amount, 'change': data.change,
              'blocked': (~active).astype(float), 'is_st': data.is_st.astype(float)}
    for price in ['open', 'high', 'low', 'close']:
        fields[price] = (data[price] * normalized_factor).where(active)
    fields['vwap'] = (data.amount / data.volume.replace(0, np.nan) * normalized_factor).where(active)
    for field, values in fields.items():
        np.concatenate(([first], values.to_numpy(dtype=float))).astype('<f4').tofile(folder / f'{field}.day.bin')
    return instrument, str(data.index.min().date()), str(data.index.max().date())


def export_dataset(canonical, output):
    canonical, output = Path(canonical), Path(output)
    calendar = pd.DatetimeIndex(pd.read_parquet(canonical / 'calendar.parquet').datetime)
    for name in ['calendars', 'instruments', 'features']:
        (output / name).mkdir(parents=True, exist_ok=True)
    (output / 'calendars' / 'day.txt').write_text('\n'.join(calendar.strftime('%Y-%m-%d')) + '\n', encoding='utf-8')
    intervals = pd.read_parquet(canonical / 'membership.parquet')
    intervals.to_csv(output / 'instruments' / 'csi300.txt', sep='\t', header=False, index=False)
    records = []
    for path in sorted(canonical.glob('S*.parquet')):
        records.append(export_instrument(pd.read_parquet(path), calendar, output))
    pd.DataFrame(records).to_csv(output / 'instruments' / 'all.txt', sep='\t', header=False, index=False)
    return output
