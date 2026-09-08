"""Finite primary-event integration, preserving frozen ledgers and typed uncertainty."""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

import pandas as pd

from audit_r2_parallel_transcriptions import validate_record, NUMERIC
from build_r2_event_ledger import read, sha, write, available_date, is_member, local_chain_asof, page_text, compact

ROOT = Path(__file__).resolve().parents[1]


def typed_value(row, prefix):
    suffix = 'yuan' if prefix == 'parent_profit' else 'percent'
    return tuple(row.get(k) for k in (prefix+'_value_kind', prefix+'_lower_'+suffix,
                 prefix+'_upper_'+suffix, prefix+'_point_'+suffix))


def deduplicate_typed(records):
    dates = defaultdict(list)
    for row in records:
        dates[(row['code'], row['period'], row['notice_date'], row['kind'])].append(row)
    events = []
    for key, rows in sorted(dates.items()):
        values = defaultdict(list)
        for row in rows:
            values[typed_value(row, 'parent_profit')+typed_value(row, 'yoy')].append(row)
        for index, (_, group) in enumerate(sorted(values.items(), key=lambda pair: str(pair[0])), 1):
            event = {k: deepcopy(v) for k,v in group[0].items() if k not in ('announcement_id','source')}
            event['event_id'] = '_'.join(key)+f'_{index}'
            event['announcement_ids'] = sorted(r['announcement_id'] for r in group)
            event['sources'] = [r['source'] for r in sorted(group,key=lambda r:r['announcement_id'])]
            event['issues'] = sorted({i for r in group for i in r['issues']})
            quarantines = sorted({r['data_status'] for r in group if r['data_status'].startswith('QUARANTINED')})
            if len(values)>1:
                event['data_status']='QUARANTINED_SAME_DATE_VALUES'
            elif quarantines:
                event['data_status']=quarantines[0]
            event['same_date_value_conflict']=len(values)>1
            event['version_status']='EARLIEST_ARCHIVED_NOT_PROVEN_FIRST'
            event['supersedes_event_id']=None
            event['superseded_at_available_date']=None
            event['research_admission']=False
            events.append(event)
    return events


def compare_vendor_growth(event, lower, upper):
    if event['data_status'].startswith('QUARANTINED'):
        return {'status':'QUARANTINED_PRIMARY'}
    if lower in ('',None) or upper in ('',None):
        return {'status':'MISSING_VENDOR_BOUND'}
    try:
        vendor=sorted([Decimal(str(lower)),Decimal(str(upper))])
        if not all(x.is_finite() for x in vendor):raise InvalidOperation
    except InvalidOperation:
        return {'status':'INVALID_VENDOR_NUMBER'}
    kind,lo,hi,point=typed_value(event,'yoy')
    if kind=='RANGE': primary=[lo,hi]
    elif kind=='POINT' and vendor[0]==vendor[1]: primary=[point,point]
    else:return {'status':'NOT_COMPARABLE_VALUE_KIND'}
    delta=max(abs(v-Decimal(str(p))) for v,p in zip(vendor,primary))
    return {'status':'AGREES_WITHIN_0_011_PP' if delta<=Decimal('0.011') else 'SOURCE_DIFFERENCE',
            'max_abs_difference_pp':float(delta), 'diagnostic_only':True}


def main():
    config_path=ROOT/'configs/r2/integrated_ledger.json';config=read(config_path)
    out=ROOT/'experiments/r2'/config['run_id']
    if out.exists():raise ValueError('immutable run already exists')
    docs=read(ROOT/'docs/results/r2_backfill/documents.json');by_id={d['announcement_id']:d for d in docs}
    inputs={str(config_path.relative_to(ROOT)).replace('\\','/'):sha(config_path),
            'scripts/integrate_r2_event_ledger.py':sha(Path(__file__))}
    for name in ('docs/results/r2_backfill/documents.json','scripts/audit_r2_parallel_transcriptions.py',
                 'scripts/build_r2_event_ledger.py','scripts/extract_r2_announcements.py'):
        inputs[name]=sha(ROOT/name)
    catalog=read(ROOT/'docs/results/sources.json')
    for name,value in catalog.items():
        if sha(ROOT/name)!=value['sha256']:raise ValueError('public source changed: '+name)
    texts={}
    for d in docs:
        for kind in ('pdf','text'):
            if sha(ROOT/d[kind+'_path'])!=d[kind+'_sha256']:raise ValueError('primary source changed')
        texts[d['announcement_id']]=(ROOT/d['text_path']).read_text(encoding='utf-8')
    def load(name):
        inputs[name]=sha(ROOT/name)
        return read(ROOT/name)
    old=load('docs/results/r2_event_ledger/events.json')
    dispositions=load('docs/results/r2_event_ledger/document_dispositions.json')
    disp={d['announcement_id']:d for d in dispositions}
    calendar_path=ROOT/'data/canonical/baostock_alpha158_csi300_2008_2020/calendar.parquet'
    membership_path=calendar_path.with_name('membership.parquet')
    for p in (calendar_path,membership_path):inputs[str(p.relative_to(ROOT)).replace('\\','/')]=sha(p)
    calendar=sorted(pd.read_parquet(calendar_path).datetime.dt.strftime('%Y-%m-%d').unique())
    assert calendar[-1]<'2021-01-01'
    intervals=defaultdict(list)
    for row in pd.read_parquet(membership_path).itertuples(index=False):
        intervals[row.instrument[2:]].append((str(row.start)[:10],str(row.end)[:10]))
    records=[]
    for event in old:
        for aid in event['announcement_ids']:
            row={k:deepcopy(v) for k,v in event.items() if k not in ('event_id','announcement_ids','sources')}
            for prefix,unit in [('parent_profit','yuan'),('yoy','percent')]:
                lo,hi=(row.get(prefix+f'_{b}_'+unit) for b in ('lower','upper'))
                assert (lo is None)==(hi is None)
                row[prefix+'_value_kind']='MISSING' if lo is None else 'RANGE'
                row[prefix+'_point_'+unit]=None
            row['announcement_id']=aid
            row['source']=next(s for s in event['sources'] if s['announcement_id']==aid)
            records.append(row)
    new_rows=[];checks=[]
    for source in config['transcription_sources']:
        result=load(source);new_rows.extend(result if isinstance(result,list) else result['records'])
    aids=[r['announcement_id'] for r in new_rows]
    if len(aids)!=len(set(aids)):raise ValueError('duplicate transcription identity')
    if any(disp[aid]['status']!='PENDING_CONTENT_REVIEW' for aid in aids):raise ValueError('new source overwrites old review')
    for row in new_rows:
        aid=row['announcement_id'];doc=by_id[aid]
        check=validate_record(row,doc,texts[aid]);checks.append(check)
        if check['errors']:raise ValueError(f'{aid}: {check["errors"]}')
        disposition=disp[aid]
        disposition['review_evidence']=row['evidence'];disposition['review_issues']=row['issues']
        disposition['verified_period']=row['verified_period']
        if row['document_class'] not in ('Q1_FORECAST','Q1_EXPRESS') or row['verified_period'] is None:
            disposition['status']='EXCLUDED_NON_TARGET_EVENT' if row['document_class'] in ('ANNUAL_ONLY','OTHER') else 'UNRESOLVED_CONTENT'
            if any('SEARCH_ABSENCE' in issue or 'Targeted search' in issue for issue in row['issues']) and aid not in config['explicit_non_target_documents']:
                disposition['status']='UNRESOLVED_CONTENT_SEARCH'
            continue
        numeric=any(row.get(f) is not None for f in NUMERIC)
        status='REVIEWED_PRIMARY_TRANSCRIPTION' if numeric else 'REVIEWED_QUALITATIVE_ONLY'
        if aid in config['quarantined_documents']:status=config['quarantined_documents'][aid]
        if '取消' in doc['title']:status='QUARANTINED_CANCELLED_TIME_UNKNOWN'
        disposition['status']=status
        disposition['reviewed_values']={f:row.get(f) for f in NUMERIC}
        date=available_date(doc['notice_date'],calendar)
        if date is None or not (row['verified_period'][:4]+'-01-01'<=doc['notice_date']<=row['verified_period'][:4]+'-04-30'):
            raise ValueError('event outside frozen source dates')
        source={'announcement_id':aid,'url':doc['document_url'],'pdf_sha256':doc['pdf_sha256'],
                'text_sha256':doc['text_sha256'],'evidence':row['evidence'],'method':'MODEL_TRANSCRIPTION_WITH_EVIDENCE_CHECKS_AND_ROOT_REVIEW',
                'visual_check_this_batch':False}
        records.append({'announcement_id':aid,'code':doc['code'],'period':row['verified_period'],
                        'notice_date':doc['notice_date'],'available_date':date,'timestamp_precision':'SOURCE_INDEX_DATE_ONLY',
                        'kind':'forecast' if row['document_class']=='Q1_FORECAST' else 'express',
                        'member_at_available_date':is_member(doc['code'],date,intervals),'historical_member_union':doc['historical_member_union'],
                        'audit_sentinel':doc['audit_sentinel'],'data_status':status,'issues':row['issues'],'source':source,
                        **{f:row.get(f) for f in NUMERIC},'parent_profit_value_kind':row['parent_profit_value_kind'],
                        'yoy_value_kind':row['yoy_value_kind'],'growth_basis':'EXPLICIT_SOURCE_PERCENT' if row['yoy_value_kind']!='MISSING' else 'NOT_NUMERIC',
                        'comparability_status':'NOT_SYSTEMATICALLY_VERIFIED','archive_recall_complete':False,'research_admission':False})
    events=deduplicate_typed(records);event_by_doc={aid:e for e in events for aid in e['announcement_ids']}
    links=load('docs/results/r2_event_ledger/version_links.json');links+=config['additional_links'];causal=[]
    for link in links:
        if link.get('reference_tokens'):
            reference=compact(page_text(texts[link['revision']],link['reference_page']))
            if any(token not in reference for token in link['reference_tokens']):
                raise ValueError('version reference evidence missing')
        current=event_by_doc[link['revision']];link['revision_event_id']=current['event_id']
        prior=event_by_doc.get(link.get('prior'));link['prior_event_id']=prior['event_id'] if prior else None
        if link['status']=='VERIFIED_LOCAL_REFERENCE':
            assert prior and (prior['code'],prior['period'])==(current['code'],current['period'])
            assert prior['notice_date']<current['notice_date']
            current['supersedes_event_id']=prior['event_id'];current['version_status']='EXPLICIT_REVISION_OF_ARCHIVED_PRIMARY'
            prior['superseded_at_available_date']=current['available_date'];prior['version_status']='ARCHIVED_PRIMARY_WITH_VERIFIED_LATER_REFERENCE'
            for date in calendar:
                if prior['notice_date']<=date<=current['available_date']:
                    known=local_chain_asof([prior,current],date)
                    expected=current if date>=current['available_date'] else prior if date>=prior['available_date'] else None
                    assert known is expected
                    causal.append({'chain':[prior['event_id'],current['event_id']],'date':date,'known_event_id':known['event_id'] if known else None})
        elif link['status']=='EXPLICIT_NO_PRIOR_DISCLOSED':current['version_status']='EXPLICIT_NO_PRIOR_DISCLOSED_FORECAST'
    vendor=[]
    for index,row in enumerate(load('experiments/r2/r2_baostock_event_bulk_v1/audit/classified_rows.json')):
        if not row['scope_eligible']:continue
        key=(row['raw']['code'][3:],row['report_period'],row['notice_date'],row['kind'])
        matched=[e for e in events if (e['code'],e['period'],e['notice_date'],e['kind'])==key]
        candidates=[d['announcement_id'] for d in docs if (d['code'],d['period'],d['notice_date'])==key[:3]]
        status='PRIMARY_CONTENT_PENDING' if candidates else 'NO_SAME_DATE_PRIMARY_IN_ARCHIVE'
        if candidates and all(disp[a]['status']=='EXCLUDED_NON_TARGET_EVENT' for a in candidates):status='PRIMARY_DOCUMENTS_NOT_TARGET_EVENT'
        if matched:status='PRIMARY_QUARANTINE' if any(e['data_status'].startswith('QUARANTINED') for e in matched) else 'MATCHED_PRIMARY_EVENT'
        item={'classified_row_index':index,'source_request':row['source_request'],'code':key[0],'period':key[1],
              'notice_date':key[2],'kind':key[3],'matched_event_ids':[e['event_id'] for e in matched],
              'candidate_document_ids':candidates,'status':status,'research_admission':False}
        if len(matched)==1 and row['kind']=='forecast':
            item['growth_diagnostic']=compare_vendor_growth(matched[0],row['raw'].get('profitForcastChgPctDwn'),row['raw'].get('profitForcastChgPctUp'))
        vendor.append(item)
    summary={'run_id':config['run_id'],'documents':len(dispositions),'document_status_counts':dict(Counter(d['status'] for d in dispositions)),
             'new_transcriptions_checked':len(new_rows),'events':len(events),'event_status_counts':dict(Counter(e['data_status'] for e in events)),
             'event_kind_counts':dict(Counter(e['kind'] for e in events)),
             'member_numeric_nonquarantined_events':sum(e['member_at_available_date'] and not e['data_status'].startswith('QUARANTINED') and any(e.get(f) is not None for f in NUMERIC) for e in events),
             'vendor_mapping_counts':dict(Counter(v['status'] for v in vendor)),
             'vendor_growth_diagnostics':dict(Counter(v['growth_diagnostic']['status'] for v in vendor if 'growth_diagnostic' in v)),
             'verified_local_links':sum(l['status']=='VERIFIED_LOCAL_REFERENCE' for l in links),'causal_checks':len(causal),
             'archive_recall_complete':False,'research_admission':False,'new_factor_evaluations':0}
    verification={'old_public_hashes_verified':len(catalog),'primary_hashes_verified':len(docs)*2,
                  'all_available_dates_strictly_after_notice':all(e['available_date']>e['notice_date'] for e in events),
                  'market_price_or_label_reads':False,'registry_writes':False,'protected_observations_accessed':False}
    out.mkdir(parents=True)
    for name,value in [('summary',summary),('verification',verification),('events',events),('document_dispositions',dispositions),
                       ('version_links',links),('causal_checks',causal),('baostock_mapping',vendor),('source_hashes',inputs),('transcription_checks',checks)]:
        write(out/(name+'.json'),value)
    write(out/'artifact_hashes.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
