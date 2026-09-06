import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from quant_research.m2.quarterly import clean_events, daily_panel, validate_config


def test_rejects_date_expansion_and_endpoint_expansion():
    c = json.loads((Path(__file__).parents[1] / 'configs/factors/m2_quarterly.json').read_text())
    assert len(validate_config(c)) == 13
    c['end'] = '2021-01-01'
    with pytest.raises(ValueError):
        validate_config(c)


def test_quarantine_bad_publications_and_conflicting_revisions():
    frame = pd.DataFrame({'code': ['sh.600000'] * 5,
                          'pubDate': ['2015-04-01', '', '2016-04-01', '2016-04-01', '2021-01-01'],
                          'statDate': ['2014-12-31', '2015-03-31', '2015-12-31', '2015-12-31', '2016-09-30'],
                          'x': ['1', '2', '3', '4', '5']})
    clean, bad = clean_events(frame, 'sh.600000', ['x'], '2016-12-31')
    assert clean.x.tolist() == [1]
    assert len(bad) == 4


def test_daily_join_respects_exchange_gaps_missing_latest_and_period_age():
    dates = pd.DatetimeIndex(['2015-04-30', '2015-05-04', '2015-05-05', '2016-10-03'])
    e = pd.DataFrame({'pubDate': pd.to_datetime(['2015-04-30', '2015-05-04']),
                      'statDate': pd.to_datetime(['2014-12-31', '2015-03-31']), 'x': [1., np.nan]})
    a = daily_panel(e, dates, ['x'])
    assert np.isnan(a.iloc[0].x)
    assert a.iloc[1].x == 1
    assert np.isnan(a.iloc[2].x)
    changed = e.copy(); changed.loc[1, 'x'] = 99
    b = daily_panel(changed, dates, ['x'])
    pd.testing.assert_frame_equal(a.iloc[:2], b.iloc[:2])
    late = pd.DataFrame({'pubDate': pd.to_datetime(['2016-09-30']),
                        'statDate': pd.to_datetime(['2014-12-31']), 'x': [99]})
    assert np.isnan(daily_panel(late, dates, ['x']).iloc[-1].x)


def test_numeric_missing_preserved_and_malformed_quarantined():
    f = pd.DataFrame({'code': ['sh.600000'] * 3,
                      'pubDate': ['2015-04-01', '2015-07-01', '2015-10-01'],
                      'statDate': ['2015-03-31', '2015-06-30', '2015-09-30'], 'x': ['', 'bad', 'inf']})
    clean, bad = clean_events(f, 'sh.600000', ['x'], '2016-12-31')
    assert len(clean) == 1 and clean.x.isna().all()
    assert len(bad) == 2
