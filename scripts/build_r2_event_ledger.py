"""Finite offline event ledger: reviewed primary facts, not a factor-ready panel."""
from bisect import bisect_right
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from extract_r2_announcements import annual_q1_fields

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('parent_profit_lower_yuan', 'parent_profit_upper_yuan',
          'yoy_lower_percent', 'yoy_upper_percent')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def compact(text):
    return re.sub(r'\s+', '', text)


def page_text(text, page):
    parts = re.split(r'=== PAGE (\d+) ===', text)
    pages = {int(parts[i]): parts[i+1] for i in range(1, len(parts), 2)}
    if page not in pages:
        raise ValueError(f'page {page} not present in extracted text')
    return pages[page]


def available_date(notice_date, calendar):
    """Source dates have no dependable intraday precision; same day is forbidden."""
    index = bisect_right(calendar, notice_date)
    return calendar[index] if index < len(calendar) else None


def is_member(code, date, intervals):
    return date is not None and any(start <= date <= end for start, end in intervals.get(code, []))


def deduplicate(records):
    """Equal primary facts share an event; same-date conflicting facts stay isolated."""
    by_date = defaultdict(list)
    for record in records:
        by_date[(record['code'], record['period'], record['notice_date'])].append(record)
    events = []
    for key, rows in sorted(by_date.items()):
        by_value = defaultdict(list)
        for row in rows:
            by_value[tuple(row.get(field) for field in FIELDS)].append(row)
        for serial, (_, group) in enumerate(sorted(by_value.items(), key=lambda x: str(x[0])), 1):
            event = {k: v for k, v in group[0].items() if k not in ('announcement_id', 'source')}
            event['event_id'] = '_'.join(key) + f'_{serial}'
            event['announcement_ids'] = sorted(r['announcement_id'] for r in group)
            event['sources'] = [r['source'] for r in sorted(group, key=lambda r: r['announcement_id'])]
            event['issues'] = sorted({issue for r in group for issue in r['issues']})
            event['same_date_value_conflict'] = len(by_value) > 1
            event['data_status'] = ('QUARANTINED_PRIMARY_FACTS' if len(by_value) > 1 or
                                    any(r['data_status'].startswith('QUARANTINED') for r in group)
                                    else event['data_status'])
            event['version_status'] = 'EARLIEST_ARCHIVED_NOT_PROVEN_FIRST'
            event['supersedes_event_id'] = None
            event['superseded_at_available_date'] = None
            event['research_admission'] = False
            events.append(event)
    return events


def local_chain_asof(events, date):
    """For an explicitly verified local chain only; never a full-market PIT claim."""
    if any(e['data_status'].startswith('QUARANTINED') for e in events):
        raise ValueError('quarantined chain')
    ordered = sorted(events, key=lambda e: e['available_date'])
    for previous, current in zip(ordered, ordered[1:]):
        if current['supersedes_event_id'] != previous['event_id']:
            raise ValueError('unverified predecessor')
    known = [e for e in ordered if e['available_date'] is not None and e['available_date'] <= date]
    return known[-1] if known else None


def main():
    config_path = ROOT/'configs/r2/event_ledger.json'
    config = read(config_path)
    out = ROOT/'experiments/r2'/config['run_id']
    if out.exists():
        raise ValueError('Completed or partial run exists; do not overwrite evidence')
    documents_path = ROOT/'docs/results/r2_backfill/documents.json'
    documents = read(documents_path)
    by_id = {d['announcement_id']: d for d in documents}
    catalog = read(ROOT/'docs/results/sources.json')
    for name, metadata in catalog.items():
        if sha(ROOT/name) != metadata['sha256']:
            raise ValueError(f'published source hash mismatch: {name}')
    texts = {}
    for doc in documents:
        for kind in ('pdf', 'text'):
            if sha(ROOT/doc[f'{kind}_path']) != doc[f'{kind}_sha256']:
                raise ValueError(f'{kind} source mismatch: {doc["announcement_id"]}')
        texts[doc['announcement_id']] = (ROOT/doc['text_path']).read_text(encoding='utf-8')
    bulk = ROOT/'experiments/r2/r2_baostock_event_bulk_v1'
    manifest = read(bulk/'artifact_hashes.json')
    for name, expected in manifest.items():
        if sha(bulk/name) != expected:
            raise ValueError(f'bulk source mismatch: {name}')
    calendar_path = ROOT/'data/canonical/baostock_alpha158_csi300_2008_2020/calendar.parquet'
    membership_path = calendar_path.with_name('membership.parquet')
    calendar = sorted(pd.read_parquet(calendar_path).datetime.dt.strftime('%Y-%m-%d').unique())
    if calendar[-1] >= '2021-01-01':
        raise ValueError('protected calendar outside finite source contract')
    intervals = defaultdict(list)
    for row in pd.read_parquet(membership_path).itertuples(index=False):
        intervals[row.instrument[2:]].append((str(row.start)[:10], str(row.end)[:10]))

    transcriptions = {}
    corrections = []
    for aid, page, low, high, g, h in config['reviewed_annual_tables']:
        doc = by_id[aid]
        value = annual_q1_fields(page_text(texts[aid], page), int(doc['period'][:4]))
        expected = dict(zip(FIELDS, [float(Decimal(str(low))*10000), float(Decimal(str(high))*10000), g, h]))
        if value is None or any(value[f] != expected[f] for f in FIELDS):
            raise ValueError(f'primary table disagrees with transcription: {aid}')
        transcriptions[aid] = {**expected, 'page': page, 'method': 'REVIEWED_EXPLICIT_CURRENT_Q1_TABLE', 'issue': None}
        old = doc['explicit_annual_q1_fields']
        changed = {f: {'old': old[f], 'corrected': expected[f]} for f in FIELDS if old[f] != expected[f]}
        if changed:
            corrections.append({'announcement_id': aid, 'page': page, 'changes': changed,
                                'reason': 'Preserve numeric-cell boundary before next row year; decimal currency scaling',
                                'old_record_was_research_admitted': False})

    cases_path = ROOT/'configs/r2/reviewed_backfill_cases.json'
    for case in read(cases_path)['cases'] + config['extra_transcriptions']:
        aid = case['announcement_id']
        if any(by_id[aid][f] != case[f] for f in ('code', 'period', 'notice_date')):
            raise ValueError(f'case identity mismatch: {aid}')
        if aid in transcriptions and any(case[f] != transcriptions[aid][f] for f in FIELDS):
            raise ValueError(f'template/manual conflict: {aid}')
        transcriptions[aid] = {**case, 'method': 'REVIEWED_PRIMARY_TRANSCRIPTION'}
    basis_path = ROOT/'docs/results/r2_baostock_event_bulk/primary_basis_diagnostics.json'
    for case in read(basis_path):
        aid = case['announcement_id']
        if by_id[aid]['pdf_sha256'] != case['pdf_sha256']:
            raise ValueError('basis source mismatch')
        transcriptions[aid] = dict(zip(FIELDS, case['forecast_profit_bounds_yuan'] + [None, None]))
        transcriptions[aid].update(page=case['source_page'], method='REVIEWED_PRIMARY_AMOUNT_WITH_DERIVED_GROWTH',
                                  issue=case['interpretation'], prior_profit_yuan=case['prior_profit_yuan'],
                                  derived_growth_percent=case['derived_growth_percent'])

    dispositions, records = [], []
    for doc in documents:
        aid = doc['announcement_id']
        row = {'announcement_id': aid, 'code': doc['code'], 'query_period': doc['period'],
               'verified_period': None, 'notice_date': doc['notice_date'], 'title': doc['title'],
               'status': 'PENDING_CONTENT_REVIEW', 'research_admission': False}
        if '取消' in doc['title']:
            row['status'] = 'QUARANTINED_CANCELLED_TIME_UNKNOWN'
        if aid in transcriptions:
            value = transcriptions[aid]
            issues = list(config['document_issues'].get(aid, []))
            if value.get('issue'):
                issues.append(value['issue'])
            source = {'announcement_id': aid, 'url': doc['document_url'], 'page': value['page'],
                      'pdf_sha256': doc['pdf_sha256'], 'text_sha256': doc['text_sha256'],
                      'method': value['method'], 'visual_check_this_batch': aid in config['visual_checks_this_batch']}
            # Qualitative case has a historical reviewed page number but its text
            # extractor did not retain page markers. Never invent such a marker.
            if aid != '1200838958':
                page_text(texts[aid], value['page'])
            row['verified_period'] = doc['period']
            row['reviewed_values'] = {f: value[f] for f in FIELDS}
            if row['status'].startswith('QUARANTINED_CANCELLED'):
                row['source'] = source
                dispositions.append(row)
                continue
            conflict = any(i.startswith(('SOURCE_ARITHMETIC', 'SOURCE_REFERENCE', 'SOURCE_PROSE')) for i in issues)
            status = 'QUARANTINED_PRIMARY_FACTS' if conflict else ('REVIEWED_QUALITATIVE_ONLY' if
                         value[FIELDS[0]] is None else 'REVIEWED_NUMERIC_PRIMARY_FACTS')
            date = available_date(doc['notice_date'], calendar)
            row['status'] = status
            record = {'announcement_id': aid, 'code': doc['code'], 'period': doc['period'],
                      'notice_date': doc['notice_date'], 'available_date': date,
                      'timestamp_precision': 'SOURCE_INDEX_DATE_ONLY', 'kind': 'forecast',
                      'member_at_available_date': is_member(doc['code'], date, intervals),
                      'historical_member_union': doc['historical_member_union'],
                      'audit_sentinel': doc['audit_sentinel'], 'data_status': status,
                      'issues': issues, 'source': source, **{f: value[f] for f in FIELDS},
                      'prior_profit_yuan': value.get('prior_profit_yuan'),
                      'derived_growth_percent': value.get('derived_growth_percent'),
                      'growth_basis': ('DERIVED_ABSOLUTE_PRIOR_DENOMINATOR' if value.get('derived_growth_percent')
                                       else 'EXPLICIT_SOURCE_PERCENT' if value[FIELDS[2]] is not None else 'NOT_NUMERIC'),
                      'comparability_status': 'NOT_SYSTEMATICALLY_VERIFIED',
                      'archive_recall_complete': False, 'research_admission': False}
            if date is None or not (doc['period'][:4]+'-01-01' <= doc['notice_date'] <= doc['period'][:4]+'-04-30'):
                raise ValueError('reviewed event outside date scope')
            records.append(record)
        dispositions.append(row)
    events = deduplicate(records)
    event_by_doc = {aid: e for e in events for aid in e['announcement_ids']}
    links, causal_checks = [], []
    for link in config['reviewed_links']:
        current = event_by_doc[link['revision']]
        reference = compact(page_text(texts[link['revision']], link['reference_page']))
        if any(token not in reference for token in link['reference_tokens']):
            raise ValueError(f'reference tokens missing: {link["revision"]}')
        result = {**link, 'revision_event_id': current['event_id'], 'archive_recall_complete': False}
        if link['prior']:
            previous = event_by_doc[link['prior']]
            if (previous['code'], previous['period']) != (current['code'], current['period']) or previous['notice_date'] >= current['notice_date']:
                raise ValueError('invalid version chronology/identity')
            result['prior_event_id'] = previous['event_id']
            if link['status'] == 'VERIFIED_LOCAL_REFERENCE':
                current['supersedes_event_id'] = previous['event_id']
                current['version_status'] = 'EXPLICIT_REVISION_OF_ARCHIVED_PRIMARY'
                previous['version_status'] = 'ARCHIVED_PRIMARY_WITH_VERIFIED_LATER_REFERENCE'
                previous['superseded_at_available_date'] = current['available_date']
                for date in calendar:
                    if previous['notice_date'] <= date <= current['available_date']:
                        known = local_chain_asof([previous, current], date)
                        expected = current if date >= current['available_date'] else previous if date >= previous['available_date'] else None
                        if known is not expected:
                            raise ValueError('noncausal revision join')
                        causal_checks.append({'chain': [previous['event_id'], current['event_id']],
                                              'date': date, 'known_event_id': known['event_id'] if known else None})
        elif link['status'] == 'EXPLICIT_NO_PRIOR_DISCLOSED':
            current['version_status'] = 'EXPLICIT_NO_PRIOR_DISCLOSED_FORECAST'
        links.append(result)

    vendor = []
    for row_number, row in enumerate(read(bulk/'audit/classified_rows.json')):
        if not row['scope_eligible']:
            continue
        code = row['raw']['code'][3:]
        matched = [e for e in events if (e['code'], e['period'], e['notice_date'], e['kind']) ==
                   (code, row['report_period'], row['notice_date'], row['kind'])]
        candidates = [d['announcement_id'] for d in documents if (d['code'], d['period'], d['notice_date']) ==
                      (code, row['report_period'], row['notice_date'])]
        date = available_date(row['notice_date'], calendar)
        result = {'classified_row_index': row_number, 'source_request': row['source_request'],
                  'code': code, 'kind': row['kind'], 'vendor_report_period': row['report_period'],
                  'vendor_notice_date': row['notice_date'], 'vendor_candidate_available_date': date,
                  'member_at_vendor_candidate_available_date': is_member(code, date, intervals),
                  'matched_event_ids': [e['event_id'] for e in matched],
                  'candidate_document_ids': candidates,
                  'status': 'PRIMARY_CONTENT_PENDING' if candidates else 'NO_SAME_DATE_PRIMARY_IN_ARCHIVE',
                  'date_match_is_not_period_validation': True, 'research_admission': False}
        if matched:
            result['status'] = 'MATCHED_REVIEWED_PRIMARY_EVENT'
            if len(matched) != 1 or matched[0]['data_status'].startswith('QUARANTINED'):
                result['status'] = 'PRIMARY_CONFLICT_QUARANTINE'
            elif row['kind'] == 'forecast':
                event = matched[0]
                bounds = [row['raw'].get(f) for f in ('profitForcastChgPctDwn', 'profitForcastChgPctUp')]
                primary = [event[f] for f in FIELDS[2:]]
                if all(b not in ('', None) for b in bounds) and all(b is not None for b in primary):
                    difference = max(abs(a-b) for a, b in zip(sorted(map(float, bounds)), primary))
                    result['growth_max_abs_difference_pp'] = difference
                    result['growth_comparison'] = 'AGREES_WITHIN_0_011_PP' if difference <= 0.011 else 'SOURCE_DIFFERENCE'
                else:
                    result['growth_comparison'] = 'NOT_COMPARABLE_TO_PRINTED_NUMERIC_RANGE'
        vendor.append(result)

    pending = [d for d in dispositions if d['status'] == 'PENDING_CONTENT_REVIEW']
    summary = {'status': 'PASS_FINITE_LEDGER_AUDIT_WITH_UNRESOLVED_COVERAGE', 'run_id': config['run_id'],
               'documents_accounted': len(dispositions), 'reviewed_document_transcriptions': len(transcriptions),
               'document_status_counts': dict(Counter(d['status'] for d in dispositions)),
               'events_after_dedup': len(events), 'duplicate_documents_collapsed': len(records)-len(events),
               'event_status_counts': dict(Counter(e['data_status'] for e in events)),
               'numeric_events_in_event_date_members': sum(e['member_at_available_date'] and e['data_status'] == 'REVIEWED_NUMERIC_PRIMARY_FACTS' for e in events),
               'verified_local_revision_links': sum(l['status'] == 'VERIFIED_LOCAL_REFERENCE' for l in links),
               'causal_date_checks': len(causal_checks), 'template_records_corrected': len(corrections),
               'bao_scope_rows_accounted': len(vendor), 'bao_matching_reviewed_events': sum(bool(v['matched_event_ids']) for v in vendor),
               'bao_rows_outside_event_date_members': sum(not v['member_at_vendor_candidate_available_date'] for v in vendor),
               'vendor_status_counts': dict(Counter(v['status'] for v in vendor)),
               'pending_documents': len(pending), 'archive_recall_complete': False,
               'research_admission': False, 'new_factors_tested': 0, 'returns_loaded': False,
               'network_requests': 0, 'protected_periods_accessed': False}
    verification = {'prior_published_hashes_verified': len(catalog), 'primary_pdf_hashes_verified': len(documents),
                    'primary_text_hashes_verified': len(documents), 'baostock_manifest_hashes_verified': len(manifest),
                    'all_available_dates_strictly_after_notice': all(e['available_date'] > e['notice_date'] for e in events),
                    'all_available_dates_in_calendar': all(e['available_date'] in calendar for e in events),
                    'factor_registry_writes': False, 'market_price_or_label_reads': False}
    inputs = [config_path, Path(__file__), ROOT/'scripts/extract_r2_announcements.py', documents_path,
              cases_path, basis_path, bulk/'artifact_hashes.json', bulk/'audit/classified_rows.json', calendar_path, membership_path]
    source_hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in inputs}
    out.mkdir(parents=True)
    for name, value in [('summary', summary), ('verification', verification), ('events', events),
                        ('document_dispositions', dispositions), ('version_links', links), ('causal_checks', causal_checks),
                        ('baostock_mapping', vendor), ('extraction_corrections', corrections), ('source_hashes', source_hashes)]:
        write(out/f'{name}.json', value)
    write(out/'artifact_hashes.json', {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
