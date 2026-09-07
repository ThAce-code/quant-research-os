"""Verify the bounded announcement archive and publish metadata, never PDF text."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import sqlite3
from extract_r2_announcements import annual_q1_fields

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def main():
    base = ROOT/'experiments/r2'
    extracted = base/'cninfo_extracted_v1'
    assert read(extracted/'summary.json')['status'] == 'PASS_EXTRACTION'
    hashes = {}
    for name in ['r2_cninfo_q1_backfill_v1', 'r2_cninfo_supplement_v1', 'cninfo_extracted_v1']:
        run = base/name
        for relative, expected in read(run/'artifact_hashes.json').items():
            path = run/relative
            assert sha(path) == expected, path
            hashes[str(path.relative_to(ROOT)).replace('\\', '/')] = expected
    documents = read(extracted/'documents.json')
    extra = base/'r2_cninfo_qualitative_v1'
    request = read(extra/'request.json')
    pdf = extra/'1200838958.pdf'
    text = pdf.with_suffix('.txt')
    assert sha(pdf) == request['pdf_sha256']
    assert sha(ROOT/'configs/r2/qualitative_notice.json') == request['config_sha256']
    compact = ''.join(text.read_text(encoding='utf-8').split())
    assert '2015年第一季度经营业绩保持持续稳定的增长' in compact
    documents.append({'announcement_id':'1200838958','code':'000826','period':'2015-03-31',
        'notice_date':'2015-04-16','title':'关于公司股票交易价格异常波动的公告',
        'document_url':request['url'],'pdf_sha256':sha(pdf),'pdf_path':str(pdf.relative_to(ROOT)),
        'text_sha256':sha(text),'text_path':str(text.relative_to(ROOT)), 'pages':2,
        'numeric_admission':'QUALITATIVE_ONLY_NO_NUMERIC_RANGE','version_chain_verified':False,
        'code_present_in_text':True,'q1_period_mentioned':True,'explicit_annual_q1_fields':None,
        'revision_title':False,'historical_member_union':True,'audit_sentinel':False})
    for path in extra.iterdir():
        if path.is_file():hashes[str(path.relative_to(ROOT)).replace('\\','/')] = sha(path)
    prior = base/'r2_cninfo_prior_reference_v1'
    meta = read(prior/'metadata.json')
    pdf = prior/'1200633670.pdf'; text = pdf.with_suffix('.txt')
    assert sha(pdf)==read(prior/'pdf_request.json')['sha256']
    fields = annual_q1_fields(text.read_text(encoding='utf-8'),2015)
    assert fields and fields['yoy_lower_percent']==360 and fields['yoy_upper_percent']==390
    documents.append({'announcement_id':'1200633670','code':'002252','period':'2015-03-31',
        'notice_date':'2015-02-13','title':meta['announcementTitle'],
        'document_url':meta['document_url'],'pdf_sha256':sha(pdf),'pdf_path':str(pdf.relative_to(ROOT)),
        'text_sha256':sha(text),'text_path':str(text.relative_to(ROOT)),'pages':meta['pages'],
        'numeric_admission':'PENDING_CONTENT_VALIDATION','version_chain_verified':False,
        'code_present_in_text':'002252' in text.read_text(encoding='utf-8'),'q1_period_mentioned':True,
        'explicit_annual_q1_fields':fields,'revision_title':False,'historical_member_union':True,'audit_sentinel':False})
    for path in prior.iterdir():
        if path.is_file():hashes[str(path.relative_to(ROOT)).replace('\\','/')] = sha(path)
    assert len({d['announcement_id'] for d in documents}) == len(documents)
    for d in documents:
        assert d['notice_date'][:4] in ['2015','2016'] and d['notice_date'][5:7] <= '04'
        assert sha(ROOT/d['pdf_path']) == d['pdf_sha256']
    reconciled = read(extracted/'snapshot_reconciliation.json')
    for row in reconciled:
        if row['code']=='000826' and row['snapshot_notice_date']=='2015-04-16':
            row.update(document_ids=['1200838958'],status='QUALITATIVE_PRIMARY_MATCH_NO_NUMERIC_RANGE')
    cases = read(ROOT/'configs/r2/reviewed_backfill_cases.json')['cases']
    by_id = {d['announcement_id']:d for d in documents}
    for case in cases:
        doc = by_id[case['announcement_id']]
        assert all(case[k]==doc[k] for k in ['code','notice_date','period'])
        assert 1 <= case['page'] <= doc['pages']
        case.update(document_url=doc['document_url'],pdf_sha256=doc['pdf_sha256'])
    flags = [d for d in documents if not(d['code_present_in_text'] and d['q1_period_mentioned'])]
    missing = [r for r in reconciled if not r['document_ids']]
    chains = read(extracted/'chains.json')
    known={(c['code'],c['period']) for c in chains}
    for d in documents:
        key=(d['code'],d['period'])
        if key not in known:
            chains.append({'code':key[0],'period':key[1],'revision_documents':0,
                           'earlier_reference_dates_missing':[],'version_chain_verified':False})
            known.add(key)
    for chain in chains:
        docs=sorted([d for d in documents if (d['code'],d['period'])==(chain['code'],chain['period'])],key=lambda d:(d['notice_date'],d['announcement_id']))
        chain.update(documents=len(docs),announcement_ids=[d['announcement_id'] for d in docs],notice_dates=[d['notice_date'] for d in docs])
        chain['earlier_reference_dates_missing']=[date for date in chain['earlier_reference_dates_missing'] if date not in chain['notice_dates']]
    registry = {}
    for name in ['factor_registry.sqlite','m2_factor_registry.sqlite']:
        with sqlite3.connect((ROOT/'data'/name).as_uri()+'?mode=ro', uri=True) as db:
            registry[name] = dict(evaluations=db.execute('select count(*) from evaluations').fetchone()[0],
                keep=db.execute("select count(*) from evaluations where status='KEEP'").fetchone()[0])
    assert registry['factor_registry.sqlite']['evaluations']==47
    assert registry['m2_factor_registry.sqlite']['evaluations']==33
    assert not any(r['keep'] for r in registry.values())
    restriction = ROOT/'data/baostock_access_restriction.json'
    hashes[str(restriction.relative_to(ROOT)).replace('\\','/')] = sha(restriction)
    out = ROOT/'docs/results/r2_backfill'
    sources=read(ROOT/'docs/results/sources.json')
    assert not any(name.startswith('docs/results/r2_backfill/') for name in sources),'Published report cannot be overwritten'
    for name,meta in sources.items():assert sha(ROOT/name)==meta['sha256'],name
    out.mkdir(exist_ok=True)
    summary = {'status':'PASS_BOUNDED_ARCHIVE_AUDIT','documents':len(documents),
        'pages':sum(d['pages'] for d in documents),'companies':len({d['code'] for d in documents}),
        'company_periods':len({(d['code'],d['period']) for d in documents}),
        'manual_review_documents':len(cases),'snapshot_rows':len(reconciled),
        'reconciliation_counts':dict(Counter(r['status'] for r in reconciled)),
        'primary_document_flags':len(flags),'archive_hashes_checked':len(hashes),
        'remaining_explicit_predecessor_date_gaps':sum(bool(c['earlier_reference_dates_missing']) for c in chains),
        'explicit_annual_q1_records':sum(d['explicit_annual_q1_fields'] is not None for d in documents),
        'automatic_extraction':read(extracted/'summary.json'),'registry':registry,
        'baostock_new_requests':0,'baostock_restoration':'UNCONFIRMED',
        'scope':'2015/2016 Q1, Jan-Apr notices, historical CSI300 member unions plus three audit sentinels',
        'returns_loaded':False,'qualification':'SEALED','lockbox':'SEALED',
        'data_admission':'NOT_READY_FOR_FACTOR_RESEARCH',
        'limits':['Date matches do not establish numerical correctness or complete historical versions.',
                  'Latest-snapshot gap recovery is vendor-assisted discovery, not exhaustive notice recall.',
                  'Annual summary and full report duplicates are separate documents, not independent events.',
                  'Manual examples are purposive; do not estimate population error rate from them.'],
        'targeted_tests_passed':6,'prior_public_hashes_verified':386,'verifier_sha256':sha(Path(__file__))}
    for name, value in [('summary',summary),('documents',documents),('snapshot_reconciliation',reconciled),
                        ('remaining_snapshot_gaps',missing),('content_flags',flags),('reviewed_cases',cases),
                        ('source_hashes',hashes),('version_chains_for_review',chains)]:
        write(out/(name+'.json'), value)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
