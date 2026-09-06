"""Bounded quarterly coverage job. No labels, returns or factor selection."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import traceback

import numpy as np
import pandas as pd
from filelock import FileLock

from ..baostock_data import BaoStockCache
from ..factors.engine import strict_write_json as write, verify_baseline
from ..factors.provenance import verify_data_identity
from .core import asof_events


def validate_config(c):
    if c['start'] != '2015-01-01' or c['end'] != '2016-12-31':
        raise ValueError('new research dates require a separate frozen protocol')
    quarters = pd.period_range(c['first_quarter'], c['last_quarter'], freq='Q')
    if not len(quarters) or quarters[0] != pd.Period('2013Q3') or quarters[-1] != pd.Period('2016Q3'):
        raise ValueError('quarter request range is fixed before collection')
    if c['fields'] != {'query_profit_data': ['roeAvg', 'npMargin'],
                       'query_growth_data': ['YOYNI', 'YOYAsset', 'YOYEquity']}:
        raise ValueError('unsupported quarterly endpoint or fields')
    return quarters


def clean_events(frame, code, fields, end):
    """Quarantine invalid dates/keys and ambiguous revisions, never guess dates."""
    e = frame.copy()
    if e.empty:
        return pd.DataFrame(columns=['code', 'pubDate', 'statDate'] + fields), e
    required = ['code', 'pubDate', 'statDate'] + fields
    if not set(required).issubset(e.columns):
        raise ValueError('quarterly response schema changed')
    pub = pd.to_datetime(e.pubDate, errors='coerce')
    stat = pd.to_datetime(e.statDate, errors='coerce')
    invalid = (pub.isna() | stat.isna() | stat.gt(pub) | e.code.ne(code)
               | ~stat.dt.is_quarter_end | pub.gt(pd.Timestamp(end)))
    reasons = pd.Series('', index=e.index)
    reasons.loc[invalid] = 'invalid_key_date_or_publication_outside_research_window'
    duplicate = e.duplicated(['code', 'pubDate', 'statDate'], keep=False)
    reasons.loc[duplicate] = 'ambiguous_duplicate_revision'
    numeric = e[fields].replace('', np.nan).apply(pd.to_numeric, errors='coerce')
    malformed = (e[fields].ne('') & e[fields].notna() & numeric.isna()).any(axis=1)
    nonfinite = np.isinf(numeric.to_numpy(dtype=float)).any(axis=1)
    reasons.loc[malformed | nonfinite] = 'malformed_numeric'
    bad = reasons.ne('')
    rejected = e.loc[bad].copy(); rejected['reason'] = reasons.loc[bad]
    out = e.loc[~bad, required].copy()
    out['pubDate'] = pub.loc[~bad]; out['statDate'] = stat.loc[~bad]
    out[fields] = numeric.loc[~bad]
    return out, rejected


def daily_panel(events, dates, fields, publication_age=400, period_age=550):
    joined = asof_events(events, dates, 'pubDate', fields + ['statDate'], max_age=publication_age)
    fiscal_age = (pd.Series(dates, index=dates) - pd.to_datetime(joined.statDate)).dt.days
    joined.loc[fiscal_age.gt(period_age), fields] = np.nan
    joined['period_age_days'] = fiscal_age
    return joined


def run(root):
    root = Path(root)
    with FileLock(str(root / 'data/factor_engine.lock'), timeout=0):
        return _run(root)


def _run(root):
    config = json.loads((root / 'configs/factors/m2_quarterly.json').read_text())
    quarters = validate_config(config)
    output = root / 'experiments/m2' / config['name'] / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state = {'status': 'RUNNING', 'stage': 'source_verification', 'run_id': output.name}
    write(output / 'status.json', state); write(output / 'config.json', config)
    print(f'QUARTERLY_RUN {output}', flush=True)
    try:
        paths = ['configs/factors/m2_quarterly.json', 'scripts/run_quarterly.py', 'run-quarterly.ps1',
                 'src/quant_research/m2/quarterly.py', 'src/quant_research/m2/core.py',
                 'src/quant_research/baostock_data.py']
        hashes = {}
        for name in paths:
            p = root / name; target = output / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, target)
            hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
        write(output / 'source_hashes.json', hashes)
        baseline = json.loads((root / 'configs/experiments/baostock_alpha158.json').read_text())
        frozen = verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
        identity = verify_data_identity(root, baseline, frozen)
        canonical = root / 'data/canonical' / baseline['name']
        dates = pd.DatetimeIndex(pd.read_parquet(canonical / 'calendar.parquet').datetime)
        dates = dates[(dates >= config['start']) & (dates <= config['end'])]
        intervals = pd.read_parquet(canonical / 'membership.parquet')
        intervals['start'] = pd.to_datetime(intervals.start, errors='raise')
        intervals['end'] = pd.to_datetime(intervals.end, errors='raise')
        intervals = intervals[(intervals.start <= pd.Timestamp(config['end'])) & (intervals.end >= pd.Timestamp(config['start']))]
        symbols = sorted(intervals.instrument.unique())
        membership = pd.DataFrame(False, index=dates, columns=symbols)
        for r in intervals.itertuples():
            membership.loc[r.start:r.end, r.instrument] = True
        membership.to_parquet(output / 'membership.parquet')
        fields = [f for fs in config['fields'].values() for f in fs]
        panels = {f: pd.DataFrame(np.nan, index=dates, columns=symbols) for f in fields}
        event_dir = output / 'events'; event_dir.mkdir()
        audits, rejected_frames, ages = [], [], []
        total = len(symbols) * len(quarters) * len(config['fields'])
        count = 0
        with BaoStockCache(root / 'data/raw/baostock') as source:
            for i, symbol in enumerate(symbols):
                code = symbol[:2].lower() + '.' + symbol[2:]
                for method, fs in config['fields'].items():
                    frames = []
                    for q in quarters:
                        frame = source.query(method, allow_empty=True, code=code, year=q.year, quarter=q.quarter)
                        # Check each response against its requested fiscal quarter.
                        if not frame.empty and not pd.to_datetime(frame.statDate, errors='coerce').eq(q.end_time.normalize()).all():
                            raise ValueError(f'wrong requested fiscal period: {code} {method} {q}')
                        frames.append(frame); count += 1
                        if count % 100 == 0:
                            state.update(stage='collection', requests_completed=count, requests_total=total,
                                         symbols_completed=i)
                            write(output / 'status.json', state)
                            print(f'REQUESTS {count}/{total}; stocks {i}/{len(symbols)}', flush=True)
                    raw = pd.concat(frames, ignore_index=True)
                    clean, rejected = clean_events(raw, code, fs, config['end'])
                    clean.to_parquet(event_dir / f'{symbol}_{method}.parquet', index=False)
                    if not rejected.empty:
                        rejected['method'] = method; rejected_frames.append(rejected)
                        # Dropping an invalid latest event could resurrect an older
                        # value. Fail closed until the quarantined events are reviewed.
                        pd.concat(rejected_frames, ignore_index=True).to_csv(output / 'quarantine.csv', index=False)
                        raise ValueError(f'quarantined quarterly records require review: {symbol} {method}')
                    joined = daily_panel(clean, dates, fs, config['max_publication_age_days'], config['max_period_age_days'])
                    joined.to_parquet(event_dir / f'{symbol}_{method}_daily.parquet')
                    own = membership[symbol]
                    for f in fs:
                        panels[f][symbol] = joined[f].where(own)
                    ages.append(joined.loc[own, ['age_days', 'period_age_days']])
                    audits.append({'symbol': symbol, 'method': method, 'requests': len(quarters),
                                   'empty_requests': sum(f.empty for f in frames), 'returned_rows': len(raw),
                                   'accepted_rows': len(clean), 'quarantined_rows': len(rejected),
                                   'eligible_days': int(own.sum()),
                                   **{f + '_days': int(joined.loc[own, f].notna().sum()) for f in fs}})
            write(output / 'requests.json', source.manifest)
        audits = pd.DataFrame(audits); audits.to_csv(output / 'stock_audit.csv', index=False)
        rejected = pd.concat(rejected_frames, ignore_index=True) if rejected_frames else pd.DataFrame(columns=['reason'])
        rejected.to_csv(output / 'quarantine.csv', index=False)
        rows = []
        for f, panel in panels.items():
            panel.to_parquet(output / f'{f}.parquet')
            for year in [2015, 2016]:
                eligible = membership.loc[str(year)]
                present = panel.loc[str(year)].notna() & eligible
                rows.append({'field': f, 'year': year, 'eligible_cells': int(eligible.to_numpy().sum()),
                             'available_cells': int(present.to_numpy().sum()),
                             'coverage': float(present.to_numpy().sum() / eligible.to_numpy().sum())})
        coverage = pd.DataFrame(rows); coverage.to_csv(output / 'coverage.csv', index=False)
        age = pd.concat(ages)
        candidates = {name: {**definition, 'coverage_gate': bool(coverage.loc[coverage.field.eq(definition['field']), 'coverage'].ge(config['min_coverage']).all()),
                            'research_status': 'NOT_EVALUATED'} for name, definition in config['candidates'].items()}
        verification = {'status': 'PASS', 'baseline_identity': identity, 'symbols': len(symbols),
                        'requests': count, 'accepted_records': int(audits.accepted_rows.sum()),
                        'quarantined_records': len(rejected), 'quarantine_reasons': rejected.reason.value_counts().to_dict(),
                        'availability': 'strictly after pubDate on the sealed exchange calendar',
                        'publication_age_quantiles': age.age_days.quantile([.5, .95, 1]).to_dict(),
                        'period_age_quantiles': age.period_age_days.quantile([.5, .95, 1]).to_dict(),
                        'pit_level': config['pit_level'], 'no_labels_or_returns_loaded': True,
                        'no_2021_plus_quarters_requested': True, 'candidates': candidates}
        verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
        if any(hashlib.sha256((root / n).read_bytes()).hexdigest() != h for n, h in hashes.items()):
            raise ValueError('source changed during run')
        write(output / 'verification.json', verification)
        artifact_hashes = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts
                           and p.name not in ['status.json']}
        write(output / 'data_manifest.json', artifact_hashes)
        lines = ['# M2.2 quarterly pilot-universe coverage', '',
                 f'Run: `{output.name}`. {len(symbols)} historical CSI300 members; 2015–2016 only.', '',
                 'All fiscal requests span 2013Q3–2016Q3. Publication must be strictly before the signal date; publication age <=400 and fiscal age <=550 days. Membership is historical and date-specific.', '',
                 coverage.to_markdown(index=False), '',
                 f'Accepted records: {verification["accepted_records"]}; quarantined: {len(rejected)}.', '',
                 'Candidates fixed before collection: Quality +roeAvg, Growth +YOYNI, Investment -YOYAsset. Existing BP is the Value reference. Coverage is a data gate, not factor acceptance; no return-based results were calculated.', '',
                 '## Limits', '',
                 '- Vendor historical revisions are unknown; publication alignment does not reconstruct historical vintages.',
                 '- ROE is the vendor reporting-period ratio, not an independently reconstructed TTM ROE. Fiscal-period mixing and restatement risks need sensitivity checks.',
                 '- Asset growth is an investment proxy; financial firms and corporate actions may make it incomparable.',
                 '- Missing newest report fields remain missing. Invalid/ambiguous records are quarantined; no zero-fill or backdated publication.',
                 '- This completes collection for the pilot universe, not the full 2008–2020 research history or M2. No qualification/lockbox access.',
                 '- Next: evaluate the three frozen candidates against BP and the technical reference on this observed history; expand quarterly history before rolling-model claims.']
        (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        state.update(status='PASS', stage='complete', requests_completed=count, requests_total=total, symbols_completed=len(symbols))
        write(output / 'status.json', state)
        print(json.dumps(verification, ensure_ascii=False), flush=True)
        return output
    except BaseException as exc:
        state.update(status='FAIL', error=str(exc)); write(output / 'status.json', state)
        (output / 'traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
