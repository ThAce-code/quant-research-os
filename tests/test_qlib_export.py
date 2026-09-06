import numpy as np
import pandas as pd

from quant_research.canonical import canonicalize
from quant_research.qlib_export import export_instrument
from test_data import bars, factors


def test_binary_roundtrip_price_volume_and_suspension(tmp_path):
    frame = canonicalize(bars(), factors())
    calendar = pd.to_datetime(['2017-05-23', '2017-05-24', '2017-05-25', '2017-05-26'])
    export_instrument(frame, calendar, tmp_path)
    read = lambda field: np.fromfile(tmp_path / 'features/sh600000' / f'{field}.day.bin', dtype='<f4')
    close, factor, volume, vwap = [read(f) for f in ['close', 'factor', 'volume', 'vwap']]
    assert close[0] == 1  # offset in complete trading calendar
    assert close[1] == 1  # first valid adjusted price normalized to 1
    assert np.isclose(close[2] / factor[2], 12.93)
    assert np.isclose(volume[2] * factor[2], 222373433)
    assert np.isclose(vwap[2] * volume[2], 2803027088)
    assert np.isnan(close[3])
    assert read('blocked')[3] == 1
