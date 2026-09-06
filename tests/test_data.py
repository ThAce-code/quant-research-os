"""Small synthetic fixtures exercise accounting identities, not market performance."""
import pandas as pd
import pytest

from quant_research.canonical import canonicalize, membership_intervals
from quant_research.baostock_data import BaoStockCache, DeadlineSocket, checked_frame, session_lock, required_bar_dates


def bars():
    return pd.DataFrame({
        'date': ['2017-05-24', '2017-05-25', '2017-05-26'],
        'code': ['sh.600000'] * 3,
        'open': ['15.38', '11.75', '12.81'], 'high': ['15.52', '12.93', '12.91'],
        'low': ['15.21', '11.72', '12.54'], 'close': ['15.47', '12.93', '12.84'],
        'preclose': ['15.43', '11.75', '12.93'],
        'volume': ['70439028', '222373433', '0'],
        'amount': ['1081376992', '2803027088', '0'],
        'tradestatus': ['1', '1', '0'], 'isST': ['0'] * 3,
        'pctChg': ['0.259235', '10.042560', '0'], 'turn': ['0.32', '0.79', '0'],
    })


def factors():
    return pd.DataFrame({'code': ['sh.600000'] * 2,
                         'dividOperateDate': ['2016-06-23', '2017-05-25'],
                         'backAdjustFactor': ['7.128788', '9.385732']})


def test_factor_only_changes_on_effective_day_and_raw_data_remains():
    result = canonicalize(bars(), factors())
    assert result.factor.tolist() == [7.128788, 9.385732, 9.385732]
    assert result.close.tolist() == [15.47, 12.93, 12.84]
    assert result.instrument.tolist() == ['SH600000'] * 3
    assert result.is_suspended.tolist() == [False, False, True]


def test_factor_before_first_event_defaults_to_one_without_backfill():
    result = canonicalize(bars(), factors().iloc[1:])
    assert result.factor.iloc[0] == 1.0


def test_duplicate_bar_is_an_error():
    with pytest.raises(ValueError, match='duplicate'):
        canonicalize(pd.concat([bars(), bars().iloc[:1]]), factors())


def test_invalid_traded_price_is_an_error():
    raw = bars()
    raw.loc[0, 'close'] = ''
    with pytest.raises(ValueError, match='price'):
        canonicalize(raw, factors())


def test_reentry_keeps_two_distinct_membership_intervals():
    calendar = pd.to_datetime(['2020-01-02', '2020-01-03', '2020-01-06'])
    snapshots = [
        ('2020-01-02', pd.DataFrame({'code': ['sh.600000'], 'updateDate': ['2020-01-01']})),
        ('2020-01-03', pd.DataFrame({'code': ['sz.000001'], 'updateDate': ['2020-01-03']})),
        ('2020-01-06', pd.DataFrame({'code': ['sh.600000'], 'updateDate': ['2020-01-06']})),
    ]
    result = membership_intervals(snapshots, calendar)
    assert result[result.instrument == 'SH600000'][['start', 'end']].values.tolist() == [
        ['2020-01-02', '2020-01-02'], ['2020-01-06', '2020-01-06']]


def test_future_snapshot_and_missing_calendar_day_are_rejected():
    calendar = pd.to_datetime(['2020-01-02', '2020-01-03'])
    future = [('2020-01-02', pd.DataFrame({'code': ['sh.600000'], 'updateDate': ['2020-01-03']}))]
    with pytest.raises(ValueError, match='future'):
        membership_intervals(future, calendar[:1])
    with pytest.raises(ValueError, match='coverage'):
        membership_intervals([], calendar)


def test_api_error_is_not_an_empty_success():
    class ErrorResponse:
        error_code = '10001001'
        error_msg = 'not logged in'
    with pytest.raises(RuntimeError, match='10001001'):
        checked_frame(ErrorResponse())


def test_second_local_baostock_session_is_rejected_before_login(tmp_path):
    from filelock import Timeout
    with session_lock(tmp_path):
        with pytest.raises(Timeout):
            with session_lock(tmp_path):
                pytest.fail('second client must not be allowed to log in')


def test_download_span_keeps_feature_history_and_prices_for_held_positions():
    calendar = pd.bdate_range('2010-01-01', '2013-12-31')
    intervals = pd.DataFrame([
        ('SH600000', '2011-01-03', '2011-06-30'),
        ('SH600001', '2012-01-03', '2012-06-29'),
    ], columns=['instrument', 'start', 'end'])
    config = {'data_start': '2010-01-01', 'data_end': '2013-12-31',
              'segments': {'train': ['2010-01-01', '2011-12-31'], 'test': ['2012-01-01', '2013-12-31']}}
    start, end = required_bar_dates('SH600000', intervals, calendar, config)
    assert start == calendar[calendar.get_loc('2011-01-03') - 60].strftime('%Y-%m-%d')
    assert end == '2011-07-04'  # two future trading dates for the final label
    _, held_end = required_bar_dates('SH600001', intervals, calendar, config)
    assert held_end == '2013-12-31'  # may still be held after exiting the universe


def test_transient_source_error_reconnects_without_caching_partial_data(tmp_path, monkeypatch):
    from types import SimpleNamespace
    class Rows:
        error_code, error_msg, fields = '0', '', ['code']
        def __init__(self): self.done = False
        def next(self): return not self.done
        def get_row_data(self):
            self.done = True
            return ['sh.600000']
    responses = iter([SimpleNamespace(error_code='10002007', error_msg='network receive failed'), Rows()])
    client = SimpleNamespace(fetch=lambda **kwargs: next(responses),
                             login=lambda: SimpleNamespace(error_code='0', error_msg=''))
    source = BaoStockCache(tmp_path)
    source.bs = client
    monkeypatch.setattr('time.sleep', lambda seconds: None)
    assert source.query('fetch').code.tolist() == ['sh.600000']
    assert len(list((tmp_path / 'fetch').glob('*.csv'))) == 1
    assert source.query('fetch').code.tolist() == ['sh.600000']  # no third network call


def test_socket_bounds_whole_response_and_rejects_closed_stream(monkeypatch):
    class Transport:
        def sendall(self, data): pass
        def settimeout(self, timeout): pass
        def recv(self, size): return b''
    now = [0.0]
    monkeypatch.setattr('time.monotonic', lambda: now[0])
    connection = DeadlineSocket(Transport(), request_timeout=90)
    assert connection.send(b'request') == 7
    with pytest.raises(ConnectionError):
        connection.recv(8192)
    now[0] = 91
    with pytest.raises(TimeoutError):
        connection.recv(8192)
