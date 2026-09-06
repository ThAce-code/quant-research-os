"""Serial BaoStock access with resumable, content-hashed raw response files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import time
import pandas as pd
from filelock import FileLock

from .canonical import canonicalize, membership_intervals


class BaoStockError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f'BaoStock {code}: {message}')


class DeadlineSocket:
    """Protect the SDK receive loop from partial streams and silent TCP EOF."""
    def __init__(self, connection, request_timeout=90):
        self.connection = connection
        self.request_timeout = request_timeout
        self.deadline = time.monotonic() + request_timeout

    def send(self, data):
        self.deadline = time.monotonic() + self.request_timeout
        self.connection.settimeout(min(60, self.request_timeout))
        self.connection.sendall(data)
        return len(data)

    def recv(self, size):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('BaoStock whole-response deadline exceeded')
        self.connection.settimeout(min(60, remaining))
        result = self.connection.recv(size)
        if not result:
            raise ConnectionError('BaoStock connection closed before response completed')
        return result

    def close(self):
        self.connection.close()


def checked_frame(response):
    if response.error_code != '0':
        raise BaoStockError(response.error_code, response.error_msg)
    rows = []
    # Avoid SDK get_data(): older paginated paths use removed pandas.append.
    while response.next():
        rows.append(response.get_row_data())
    if response.error_code != '0':
        raise BaoStockError(response.error_code, response.error_msg)
    return pd.DataFrame(rows, columns=response.fields)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def session_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return FileLock(root / '.session.lock', timeout=0)


class BaoStockCache:
    def __init__(self, root):
        self.root = Path(root)
        self.manifest = []
        self.connection = None

    def __enter__(self):
        import baostock as bs
        self.bs = bs
        self.lock = session_lock(self.root)
        self.lock.acquire()
        try:
            socket.setdefaulttimeout(60)
            self.reconnect()
        except BaseException:
            self.lock.release()
            raise
        return self

    def __exit__(self, exc_type, *exc):
        try:
            if exc_type is None:
                self.bs.logout()
        finally:
            if self.connection is not None:
                self.connection.close()
            self.lock.release()

    def reconnect(self):
        if self.connection is not None:
            self.connection.close()
        result = self.bs.login()
        from baostock.common import context
        self.connection = getattr(context, 'default_socket', None)
        if result.error_code != '0':
            raise BaoStockError(result.error_code, result.error_msg)
        if self.connection is not None:
            self.connection = DeadlineSocket(self.connection)
            context.default_socket = self.connection

    def has_cached(self, method, **params):
        key = hashlib.sha256(json.dumps({'method': method, 'params': params}, sort_keys=True).encode()).hexdigest()[:24]
        path = self.root / method / f'{key}.csv'
        return path.exists() and path.with_suffix('.json').exists()

    def query(self, method, *, allow_empty=False, **params):
        request = {'method': method, 'params': params}
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:24]
        folder = self.root / method
        path = folder / f'{key}.csv'
        meta = folder / f'{key}.json'
        if path.exists() and meta.exists():
            provenance = json.loads(meta.read_text(encoding='utf-8'))
            if hashlib.sha256(path.read_bytes()).hexdigest() != provenance['sha256']:
                raise ValueError(f'raw cache checksum mismatch: {path}')
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        else:
            for attempt in range(3):
                try:
                    frame = checked_frame(getattr(self.bs, method)(**params))
                    break
                except BaoStockError as exc:
                    if exc.code not in {'10002007', '10002006', '10001001'} or attempt == 2:
                        raise RuntimeError(f'{exc}; request={request}') from exc
                    print(f'RECONNECT {attempt+1}/2 code={exc.code} request={request}', flush=True)
                    time.sleep(attempt + 1)
                    self.reconnect()
            if frame.empty and not allow_empty:
                raise ValueError(f'empty BaoStock response: {request}')
            folder.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.tmp')
            frame.to_csv(temp, index=False, encoding='utf-8')
            temp.replace(path)
            provenance = {**request, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                          'rows': len(frame), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            write_json(meta, provenance)
        if frame.empty and not allow_empty:
            raise ValueError(f'empty BaoStock cache: {request}')
        self.manifest.append({**provenance, 'path': str(path)})
        return frame


def required_bar_dates(instrument, intervals, calendar, config):
    if instrument == 'SH000300':
        return config['data_start'], config['data_end']
    own = intervals[intervals.instrument.eq(instrument)]
    first, last = pd.Timestamp(own.start.min()), pd.Timestamp(own.end.max())
    start_pos = max(0, calendar.searchsorted(first) - 60)
    start = calendar[start_pos].strftime('%Y-%m-%d')
    first_train_day = calendar[calendar.searchsorted(pd.Timestamp(config['segments']['train'][0]))]
    if first == first_train_day:
        start = config['data_start']
    if last >= pd.Timestamp(config['segments']['test'][0]):
        end = config['data_end']
    else:
        end = calendar[min(len(calendar) - 1, calendar.searchsorted(last) + 2)].strftime('%Y-%m-%d')
    return start, end


def prepare_data(root, config):
    root = Path(root)
    out = root / 'data' / 'canonical' / config['name']
    out.mkdir(parents=True, exist_ok=True)
    with BaoStockCache(root / 'data' / 'raw' / 'baostock') as source:
        days = source.query('query_trade_dates', start_date=config['data_start'], end_date=config['data_end'])
        calendar = pd.DatetimeIndex(pd.to_datetime(days.loc[days.is_trading_day.eq('1'), 'calendar_date']))
        calendar = calendar.sort_values()
        member_calendar = calendar[calendar >= pd.Timestamp(config['segments']['train'][0])]
        snapshots = []
        for i, day in enumerate(member_calendar):
            date = day.strftime('%Y-%m-%d')
            frame = source.query('query_hs300_stocks', date=date)
            if len(frame) != 300:
                raise ValueError(f'CSI300 count on {date}: {len(frame)}')
            snapshots.append((date, frame))
            if i % 100 == 0 or i == len(member_calendar) - 1:
                print(f'MEMBERSHIP {i+1}/{len(member_calendar)} {date}', flush=True)
        intervals = membership_intervals(snapshots, member_calendar)
        intervals.to_parquet(out / 'membership.parquet', index=False)
        pd.DataFrame({'datetime': calendar}).to_parquet(out / 'calendar.parquet', index=False)
        codes = sorted(intervals.instrument.unique()) + ['SH000300']
        audit = []
        base_fields = 'date,code,open,high,low,close,preclose,volume,amount,pctChg'
        for i, instrument in enumerate(codes):
            code = instrument[:2].lower() + '.' + instrument[2:]
            fields = base_fields if code == 'sh.000300' else base_fields + ',turn,tradestatus,isST'
            params = dict(code=code, fields=fields, start_date=config['data_start'],
                          end_date=config['data_end'], frequency='d', adjustflag='3')
            if not source.has_cached('query_history_k_data_plus', **params):
                params['start_date'], params['end_date'] = required_bar_dates(instrument, intervals, calendar, config)
            raw = source.query('query_history_k_data_plus', **params)
            factors = pd.DataFrame() if code == 'sh.000300' else source.query(
                'query_adjust_factor', allow_empty=True, code=code, start_date='1990-01-01', end_date=config['data_end'])
            data = canonicalize(raw, factors)
            if not data.datetime.isin(calendar).all():
                raise ValueError(f'non-trading-day source bars: {code}')
            data.to_parquet(out / f'{instrument}.parquet', index=False)
            audit.append({'instrument': instrument, 'rows': len(data),
                          'first': str(data.datetime.min().date()), 'last': str(data.datetime.max().date()),
                          'suspended_rows': int(data.is_suspended.sum())})
            if i % 20 == 0 or i == len(codes) - 1:
                print(f'BARS {i+1}/{len(codes)} {instrument} rows={len(data)}', flush=True)
        manifest = {'provider': 'baostock', 'universe': 'historical CSI300 queried each trading day',
                    'data_config': {key: config[key] for key in ['name', 'data_start', 'data_end', 'segments']},
                    'instruments': len(codes) - 1, 'calendar_days': len(calendar),
                    'membership_days': len(member_calendar), 'bars': audit, 'requests': source.manifest}
        write_json(out / 'manifest.json', manifest)
    from .integrity import seal_dataset
    seal_dataset(out, audit_raw=True)
    return out
