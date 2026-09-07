"""Extract archived primary documents and reconcile snapshot gaps, without returns."""
import hashlib
import json
from pathlib import Path
import re
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def mentioned_previous_dates(text):
    """Extract references for review; not proof that a prior document was retrieved."""
    s=re.sub(r'\s+','',text)
    if '前次业绩预告情况' not in s:return []
    section=s.split('前次业绩预告情况',1)[1]
    for stop in ['修正后的预计','修正后预计','3、','3.','3．']:
        section=section.split(stop,1)[0]
    return sorted({f'{int(y):04d}-{int(m):02d}-{int(d):02d}' for y,m,d in re.findall(r'(20\d\d)年(\d{1,2})月(\d{1,2})日',section)})


def annual_q1_fields(text,year):
    """Only explicit current-Q1 parent-profit template fields; never infer missing values."""
    s=re.sub(r'\s+','',text).replace(',','').replace('，','').replace('−','-')
    period=rf'{year}年1[-—－至]3月归属于上市公司股东的净利润'
    number=r'([+-]?\d+(?:\.\d+)?)'
    amounts=re.findall(period+r'区间[（(]万元[）)]'+number+r'至'+number,s)
    growth=re.findall(period+r'变动幅度'+number+r'[%％]至'+number+r'[%％]',s)
    if len(set(amounts))!=1 or len(set(growth))!=1:return None
    a,b=map(float,amounts[0]);g,h=map(float,growth[0])
    return {'parent_profit_lower_yuan':min(a,b)*10000,'parent_profit_upper_yuan':max(a,b)*10000,
            'yoy_lower_percent':min(g,h),'yoy_upper_percent':max(g,h),
            'status':'EXPLICIT_TEMPLATE_EXTRACTED_REQUIRES_REVIEW'}


def main():
    from pypdf import PdfReader
    run=ROOT/'experiments/r2/r2_cninfo_q1_backfill_v1';state=read(run/'status.json')
    if state['status'] not in ['PASS_ARCHIVE','PARTIAL_ARCHIVE']:raise ValueError('archive incomplete')
    hashes=read(run/'artifact_hashes.json')
    for name,h in hashes.items():assert sha(run/name)==h,name
    out=ROOT/'experiments/r2/cninfo_extracted_v1';out.mkdir(parents=True,exist_ok=False);(out/'text').mkdir()
    selected={str(r['announcementId']):r for r in read(run/'selected.json')}
    supplement=ROOT/'experiments/r2/r2_cninfo_supplement_v1'
    if supplement.exists():
        if read(supplement/'status.json')['status'] not in ['PASS_ARCHIVE','PARTIAL_ARCHIVE']:raise ValueError('supplement incomplete')
        for name,h in read(supplement/'artifact_hashes.json').items():assert sha(supplement/name)==h,name
        selected.update({str(r['announcementId']):r for r in read(supplement/'selected.json')})
    selected=list(selected.values());documents=[];failures=[]
    for sequence,row in enumerate(selected,1):
        if sequence==1 or sequence%10==0:print(f'R2_EXTRACT {sequence}/{len(selected)}',flush=True)
        aid=str(row['announcementId']);pdf=ROOT/row['archive_pdf_path'] if 'archive_pdf_path' in row else run/row['local_pdf']
        try:
            if not pdf.exists() or not pdf.read_bytes().startswith(b'%PDF'):raise ValueError('missing PDF')
            reader=PdfReader(pdf);pages=[p.extract_text() or '' for p in reader.pages]
            text='\n\n'.join(f'=== PAGE {i+1} ===\n{p}' for i,p in enumerate(pages))
            path=out/'text'/f'{aid}.txt';path.write_text(text,encoding='utf-8')
            compact=re.sub(r'\s+','',text)
            code_verified=str(row['secCode']) in compact
            q1_verified=('一季度' in compact or bool(re.search(rf"{row['query_year']}年1[-—－至]3月",compact)) or ('1月1日' in compact and '3月31日' in compact)) and str(row['query_year']) in compact
            record={'announcement_id':aid,'code':row['secCode'],'title':row['announcementTitle'],'notice_date':row['notice_date'],
                'announcement_time_ms':row['announcementTime'],'period':str(row['query_year'])+'-03-31',
                'document_url':row['document_url'],'pdf_sha256':sha(pdf),'pdf_path':str(pdf.relative_to(ROOT)),
                'text_sha256':sha(path),'text_path':str(path.relative_to(ROOT)),
                'pages':len(pages),'text_characters':len(compact),'code_present_in_text':code_verified,'q1_period_mentioned':q1_verified,
                'retrieval_reason':row.get('retrieval_reason','initial_title_query'),
                'historical_member_union':row['historical_member_union'],'audit_sentinel':row['audit_sentinel'],
                'kind':'express' if '快报' in row['announcementTitle'] and '预告' not in row['announcementTitle'] else 'forecast',
                'revision_title':any(k in row['announcementTitle'] for k in ['修正','更正','补充']),
                'previous_dates_for_review':mentioned_previous_dates(text),
                'explicit_annual_q1_fields':annual_q1_fields(text,row['query_year']),
                'numeric_admission':'PENDING_CONTENT_VALIDATION','version_chain_verified':False}
            documents.append(record)
        except Exception as exc:failures.append({'announcement_id':aid,'error':str(exc)})
    write(out/'documents.json',documents);write(out/'extraction_failures.json',failures)
    groups={}
    for d in documents:groups.setdefault((d['code'],d['period']),[]).append(d)
    chains=[]
    for (code,period),docs in sorted(groups.items()):
        docs.sort(key=lambda d:(d['notice_date'],d['announcement_id']))
        own_dates={d['notice_date'] for d in docs};references={date for d in docs for date in d['previous_dates_for_review']}
        chains.append({'code':code,'period':period,'documents':len(docs),'revision_documents':sum(d['revision_title'] for d in docs),
            'announcement_ids':[d['announcement_id'] for d in docs],'notice_dates':[d['notice_date'] for d in docs],
            'earlier_reference_dates_missing':sorted(references-own_dates),'version_chain_verified':False})
    write(out/'chains.json',chains)
    reconciliation=[]
    for year in [2015,2016]:
        period=f'{year}-03-31'
        for kind in ['forecast','express']:
            rows=read(ROOT/f'experiments/r2/r2_event_feasibility_v1/{kind}_{period}_rows.json')
            index={(d['code'],d['notice_date']) for d in documents if d['period']==period}
            members=pd.read_parquet(ROOT/'data/canonical/baostock_alpha158_csi300_2008_2020/membership.parquet')
            union=set(members.loc[(pd.to_datetime(members.start)<=f'{year}-04-30')&(pd.to_datetime(members.end)>=f'{year}-01-01'),'instrument'].str[2:])
            dedup={(r['SECURITY_CODE'],r['NOTICE_DATE'][:10]):r for r in rows if r['SECURITY_CODE'] in union and (kind!='forecast' or r['PREDICT_FINANCE_CODE']=='004')}
            for key,row in sorted(dedup.items()):
                same=[d['announcement_id'] for d in documents if d['period']==period and (d['code'],d['notice_date'])==key]
                reason='MATCHED_DATE_REQUIRES_CONTENT_CHECK' if same else ('OUTSIDE_JAN_APR_SCOPE' if row['NOTICE_DATE'][:10]>f'{year}-04-30' else 'MISSING_PRIMARY_NOTICE_OR_EMBEDDED_IN_OTHER_REPORT')
                reconciliation.append({'code':key[0],'period':period,'kind':kind,'snapshot_notice_date':key[1],
                    'document_ids':same,'status':reason})
    write(out/'snapshot_reconciliation.json',reconciliation)
    summary={'status':'PASS_EXTRACTION' if not failures else 'PARTIAL_EXTRACTION','documents':len(documents),'pages':sum(d['pages'] for d in documents),
        'companies':len({d['code'] for d in documents}),'company_periods':len(chains),
        'multi_notice_company_periods':sum(c['documents']>1 for c in chains),
        'revision_titles':sum(d['revision_title'] for d in documents),
        'code_or_period_check_failures':sum(not(d['code_present_in_text'] and d['q1_period_mentioned']) for d in documents),
        'reference_gap_company_periods':sum(bool(c['earlier_reference_dates_missing']) for c in chains),
        'explicit_annual_q1_records':sum(d['explicit_annual_q1_fields'] is not None for d in documents),
        'extraction_failures':len(failures),'snapshot_matches':sum(bool(r['document_ids']) for r in reconciliation),
        'snapshot_rows':len(reconciliation),'returns_loaded':False,'data_admission':'DOCUMENT_ARCHIVE_ONLY_PENDING_NUMERIC_AND_COMPLETENESS_CHECKS',
        'source_archive_manifest_sha256':sha(run/'artifact_hashes.json'),
        'supplement_manifest_sha256':sha(supplement/'artifact_hashes.json') if supplement.exists() else None,'extractor_sha256':sha(Path(__file__))}
    write(out/'summary.json',summary)
    write(out/'artifact_hashes.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_hashes.json'})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
