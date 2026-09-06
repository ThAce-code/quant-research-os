"""Bind a completed source snapshot to the exact canonical and Qlib files used."""
import hashlib
import json
from pathlib import Path
import pandas as pd

from .baostock_data import write_json
from .canonical import canonicalize, membership_intervals


def file_hashes(root, pattern='*.parquet'):
    root = Path(root)
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.glob(pattern)) if path.is_file()}


def audit_raw_to_canonical(root, manifest):
    raw, snapshots, request_count = {}, [], 0
    for request in manifest['requests']:
        path = Path(request['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != request['sha256']:
            raise ValueError(f'raw checksum mismatch: {path}')
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        request_count += 1
        if len(frame) != request['rows']:
            raise ValueError(f'raw row count mismatch: {path}')
        method, params = request['method'], request['params']
        if method == 'query_hs300_stocks':
            snapshots.append((params['date'], frame))
        elif method == 'query_trade_dates':
            days = pd.DatetimeIndex(pd.to_datetime(frame.loc[frame.is_trading_day.eq('1'), 'calendar_date'])).sort_values()
        else:
            raw[(method, params['code'])] = frame
    expected_calendar = pd.DataFrame({'datetime': days})
    pd.testing.assert_frame_equal(pd.read_parquet(root / 'calendar.parquet'), expected_calendar, check_exact=True)
    member_days = days[days >= pd.Timestamp(manifest['data_config']['segments']['train'][0])]
    expected_membership = membership_intervals(snapshots, member_days).reset_index(drop=True)
    pd.testing.assert_frame_equal(pd.read_parquet(root / 'membership.parquet'), expected_membership, check_exact=True)
    for entry in manifest['bars']:
        code = entry['instrument'][:2].lower() + '.' + entry['instrument'][2:]
        expected = canonicalize(raw[('query_history_k_data_plus', code)],
                                raw.get(('query_adjust_factor', code), pd.DataFrame()))
        actual = pd.read_parquet(root / f"{entry['instrument']}.parquet")
        pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    return {'status': 'PASS', 'source_requests': request_count, 'bar_files': len(manifest['bars'])}


def seal_dataset(root, audit_raw=False):
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    expected_files = {'calendar.parquet', 'membership.parquet'} | {
        f"{entry['instrument']}.parquet" for entry in manifest['bars']}
    if {p.name for p in root.glob('*.parquet')} != expected_files:
        raise ValueError('canonical file set differs from source manifest')
    if audit_raw:
        manifest['raw_to_canonical_audit'] = audit_raw_to_canonical(root, manifest)
    manifest['canonical_files'] = file_hashes(root)
    manifest['integrity_version'] = 1
    write_json(root / 'manifest.json', manifest)


def verify_dataset(root, config):
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    identity = {key: config[key] for key in ['name', 'data_start', 'data_end', 'segments']}
    if manifest.get('data_config') != identity:
        raise ValueError('canonical data configuration mismatch; rerun data preparation')
    expected = manifest.get('canonical_files')
    if not expected:
        raise ValueError('canonical dataset has not been sealed')
    actual = file_hashes(root)
    if set(actual) != set(expected):
        raise ValueError('canonical file set mismatch')
    if actual != expected:
        raise ValueError('canonical checksum mismatch')
    return manifest
