"""Check finite lightweight-model drafts against archived primary evidence.

Passing proves traceability and basic numeric support, not semantic correctness,
complete version recall, or permission to use the data in factor research.
"""
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'experiments/r2/r2_parallel_review_v1'
BOUNDS = ('parent_profit_lower_yuan', 'parent_profit_upper_yuan', 'yoy_lower_percent', 'yoy_upper_percent')
NUMERIC = BOUNDS + ('parent_profit_point_yuan', 'yoy_point_percent')
SCALES = {'yuan': 1, '1k_yuan': 1000, '10k_yuan': 10000, '1m_yuan': 1000000, '100m_yuan': 100000000}
FIELDS = {'period', 'parent_profit_range', 'yoy_range', 'signature_date', 'prior_reference', 'issue'}


def compact(text):
    return re.sub(r'\s+', '', text)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def pages(text):
    parts = re.split(r'=== PAGE (\d+) ===', text)
    return {int(parts[i]): parts[i+1] for i in range(1, len(parts), 2)}


def source_numbers(quote):
    # Preserve digit whitespace: never recreate the old amount/year joining bug.
    s = quote.replace('，', ',').replace('−', '-').replace('－', '-')
    s = re.sub(r'\d{1,3}(?:,\d{3})+(?:\.\d+)?', lambda m: m[0].replace(',', ''), s)
    return {abs(Decimal(m)) for m in re.findall(r'(?<![\d.])[+-]?\d+(?:\.\d+)?(?![\d.])', s)}


def validate_record(record, doc, text):
    errors, warnings = [], []
    if record.get('announcement_id') != doc['announcement_id']:
        errors.append('IDENTITY_MISMATCH')
    if record.get('claim_type') != 'source_claim':
        errors.append('CLAIM_TYPE_MUST_BE_SOURCE_CLAIM')
    if record.get('research_admission') is not False:
        errors.append('RESEARCH_ADMISSION_FORBIDDEN')
    if record.get('document_class') not in ('Q1_FORECAST', 'Q1_EXPRESS', 'ANNUAL_ONLY', 'OTHER', 'UNRESOLVED'):
        errors.append('INVALID_DOCUMENT_CLASS')
    if record.get('extraction_status') not in ('DRAFT_EXTRACTED', 'NEEDS_REVIEW'):
        errors.append('INVALID_EXTRACTION_STATUS')
    if record.get('source_money_unit') not in (*SCALES, 'mixed', None):
        errors.append('INVALID_MONEY_UNIT')
    if not isinstance(record.get('issues'), list) or any(not isinstance(i, str) for i in record.get('issues', [])):
        errors.append('INVALID_ISSUES')
    numeric = {}
    for field in NUMERIC:
        if field not in record:
            errors.append(f'MISSING_FIELD:{field}')
        value = record.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            errors.append(f'INVALID_NUMBER:{field}')
        elif value is not None:
            numeric[field] = value
    for prefix, low, high in [('profit', *BOUNDS[:2]), ('yoy', *BOUNDS[2:])]:
        if low in numeric and high in numeric and numeric[low] > numeric[high]:
            errors.append(f'UNORDERED_RANGE:{prefix}')
    for prefix, low, high, point in [('parent_profit', *BOUNDS[:2], 'parent_profit_point_yuan'),
                                      ('yoy', *BOUNDS[2:], 'yoy_point_percent')]:
        kind = record.get(prefix+'_value_kind')
        present = tuple(record.get(f) is not None for f in (low, high, point))
        expected = {'RANGE': (True, True, False), 'POINT': (False, False, True),
                    'APPROX_POINT': (False, False, True), 'OPEN_LOWER': (True, False, False),
                    'OPEN_UPPER': (False, True, False), 'MISSING': (False, False, False)}
        if kind not in expected or present != expected[kind]:
            errors.append(f'VALUE_KIND_CONFLICT:{prefix}')
    if numeric and (record.get('verified_period') not in ('2015-03-31', '2016-03-31') or
                    record.get('document_class') not in ('Q1_FORECAST', 'Q1_EXPRESS')):
        errors.append('NUMERIC_WITHOUT_VERIFIED_Q1_PERIOD')
    if record.get('verified_period') is not None and record['verified_period'] != doc['period']:
        errors.append('PERIOD_DIFFERS_FROM_QUERY_TARGET_REVIEW_REQUIRED')

    page_map, evidence = pages(text), record.get('evidence', [])
    by_field = {}
    if not isinstance(evidence, list):
        errors.append('INVALID_EVIDENCE_LIST')
        evidence = []
    for ev in evidence:
        if not isinstance(ev, dict) or ev.get('field') not in FIELDS:
            errors.append('INVALID_EVIDENCE_FIELD')
            continue
        field, page, quote = ev['field'], ev.get('page'), ev.get('quote')
        if not isinstance(quote, str) or not compact(quote):
            errors.append(f'EMPTY_QUOTE:{field}')
            continue
        if isinstance(page, bool) or not isinstance(page, int) or page not in page_map:
            errors.append(f'MISSING_PAGE:{page}')
            continue
        if compact(quote) not in compact(page_map[page]):
            errors.append(f'QUOTE_NOT_IN_PAGE:{field}')
            continue
        by_field.setdefault(field, []).append(quote)
    for field in numeric:
        ev_field = 'parent_profit_range' if field.startswith('parent') else 'yoy_range'
        quotes = by_field.get(ev_field, [])
        if not quotes:
            errors.append(f'MISSING_SUPPORT:{field}')
            continue
        if ev_field == 'parent_profit_range':
            scale = SCALES.get(record.get('source_money_unit'))
            if scale is None:
                errors.append(f'UNRESOLVED_CURRENCY_SCALE:{field}')
                continue
            joined = ''.join(quotes)
            unit_token = {1: '元', 1000: '千元', 10000: '万元', 1000000: '百万元', 100000000: '亿元'}[scale]
            rmb_yi = scale == 100000000 and re.search(r'人民币\d+(?:\.\d+)?亿', compact(joined))
            if unit_token not in compact(joined) and not rmb_yi:
                errors.append(f'UNIT_NOT_IN_QUOTE:{field}')
        else:
            scale = 1
            if not any('%' in q or '％' in q for q in quotes):
                errors.append(f'PERCENT_UNIT_NOT_IN_QUOTE:{field}')
        number = abs(Decimal(str(numeric[field])))/Decimal(scale)
        if not any(number in source_numbers(q) for q in quotes):
            errors.append(f'UNSUPPORTED_NUMBER:{field}')
    money_quote = compact(''.join(by_field.get('parent_profit_range', [])))
    growth_quote = compact(''.join(by_field.get('yoy_range', [])))
    # Enforce only unambiguous language. Mixed prior/current columns, signed
    # intervals and loss narrowing still need source-table semantic review.
    if '亏损' in money_quote and not any(w in money_quote for w in ('盈利', '扭亏')):
        if any(numeric.get(f, 0) > 0 for f in (*BOUNDS[:2], 'parent_profit_point_yuan')):
            errors.append('LOSS_SIGN_CONFLICT')
    if '下降' in growth_quote and not any(w in growth_quote for w in ('增长', '上升', '亏损')):
        if any(numeric.get(f, 0) > 0 for f in (*BOUNDS[2:], 'yoy_point_percent')):
            errors.append('DECLINE_SIGN_CONFLICT')
    for prefix, quote in [('parent_profit', money_quote), ('yoy', growth_quote)]:
        if record.get(prefix+'_value_kind') == 'APPROX_POINT' and not any(w in quote for w in ('约', '左右')):
            errors.append(f'APPROX_POINT_QUALIFIER_MISSING:{prefix}')
    if record.get('verified_period') is not None:
        year = record['verified_period'][:4]
        evidence_period = compact(''.join(by_field.get('period', [])))
        chinese_period = re.search(rf'{year}年(?:度)?(?:第?[一1]季度|1[-—–－~～至]3月|0?1月0?1日.*?0?3月31日)', evidence_period)
        numeric_period = re.search(rf'{year}[./-]0?1[./-]0?1[-—–－~～至]+{year}[./-]0?3[./-]31', evidence_period)
        if not (chinese_period or numeric_period):
            errors.append('EXPLICIT_Q1_PERIOD_EVIDENCE_MISSING')
    if record.get('signature_date') is not None and not by_field.get('signature_date'):
        errors.append('SIGNATURE_DATE_EVIDENCE_MISSING')
    if record.get('prior_reference') is not None and not by_field.get('prior_reference'):
        errors.append('PRIOR_REFERENCE_EVIDENCE_MISSING')
    if record.get('issues'):
        warnings.append('SOURCE_ISSUES_REQUIRE_ROOT_REVIEW')
    if not numeric:
        warnings.append('NO_NUMERIC_FACTS')
    return {'announcement_id': doc['announcement_id'],
            'status': 'PASS_EVIDENCE_CHECKS_ONLY' if not errors else 'REJECT_DRAFT_PENDING_CORRECTION',
            'errors': sorted(set(errors)), 'warnings': warnings,
            'semantic_review_required': True, 'research_admission': False}


def main():
    dispatch = read(RUN/'dispatch.json')
    by_id = {d['announcement_id']: d for d in read(ROOT/'docs/results/r2_backfill/documents.json')}
    checks, records, hashes = [], [], {}
    for worker in (1, 2, 3):
        assignment = RUN/f'assignment_{worker}.json'
        if sha(assignment) != dispatch['assignments'][assignment.name]:
            raise ValueError('assignment changed')
        source = read(assignment)['documents']
        output = RUN/f'worker_{worker}.json'
        result = read(output)
        if result.get('worker') != worker or result.get('model') != 'gpt-5.6-luna':
            raise ValueError('worker identity mismatch')
        rows = result['records']
        expected = {d['announcement_id'] for d in source}
        if len(rows) != len(expected) or {r['announcement_id'] for r in rows} != expected:
            raise ValueError(f'incomplete or duplicate worker output: {worker}')
        hashes[output.name] = sha(output)
        for row in rows:
            doc = by_id[row['announcement_id']]
            for kind in ('pdf', 'text'):
                if sha(ROOT/doc[f'{kind}_path']) != doc[f'{kind}_sha256']:
                    raise ValueError('primary source hash mismatch')
            text = (ROOT/doc['text_path']).read_text(encoding='utf-8')
            check = validate_record(row, doc, text)
            checks.append(check)
            records.append({**row, 'source_name': 'CNINFO archived primary announcement',
                            'canonical_url': doc['document_url'], 'notice_date_from_index': doc['notice_date'],
                            'code': doc['code'], 'pdf_sha256': doc['pdf_sha256'], 'text_sha256': doc['text_sha256'],
                            'worker': worker, 'validation': check})
    receipt = {'run_id': 'r2_parallel_review_v1', 'records': len(records),
               'status_counts': dict(Counter(c['status'] for c in checks)), 'worker_sha256': hashes,
               'auditor_sha256': sha(Path(__file__)), 'research_admission': False, 'checks': checks}
    # Every audit attempt is retained; workers may correct drafts before sealing.
    version = 1
    while (RUN/f'validation_{version}.json').exists():
        version += 1
    for name, value in [(f'validation_{version}.json', receipt), (f'validated_drafts_{version}.json', records)]:
        (RUN/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'audit_version': version, 'records': len(records), 'status_counts': receipt['status_counts'],
                      'errors': [{'id': c['announcement_id'], 'errors': c['errors']} for c in checks if c['errors']]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
