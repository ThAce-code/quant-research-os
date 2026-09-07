"""Bounded, cached Eastmoney event audit; never loads market returns or scores."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
import requests

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/r2/event_audit.json'


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    c=json.loads(CONFIG.read_text(encoding='utf-8'));out=ROOT/'experiments/r2'/c['name']
    out.mkdir(parents=True,exist_ok=False)
    write(out/'protocol.json',c);write(out/'source_hashes.json',{'config':sha(CONFIG),'script':sha(Path(__file__))})
    records=[];summaries=[];count=0
    write(out/'status.json',{'status':'RUNNING','returns_loaded':False})
    try:
        for kind,report in c['reports'].items():
            for date in c['report_dates']:
                assert date<'2021-01-01' and c['notice_cutoff']<'2021-01-01'
                allrows=[];pages=1;page=1
                while page<=pages:
                    if count>=c['max_requests']:raise ValueError('request budget exhausted')
                    params={'reportName':report,'columns':'ALL','filter':f"(REPORT_DATE='{date}')(NOTICE_DATE<='{c['notice_cutoff']}')",
                        'pageNumber':page,'pageSize':c['page_size'],'sortColumns':'NOTICE_DATE,SECURITY_CODE','sortTypes':'1,1'}
                    file=out/f'{kind}_{date}_{page}.json'
                    record={'kind':kind,'period':date,'page':page,'url':c['endpoint'],'params':params,
                        'fetched_at':datetime.now(timezone.utc).isoformat(),'state':'RESERVED'}
                    records.append(record);count+=1;write(out/'requests.json',records)
                    response=requests.get(c['endpoint'],params=params,timeout=(10,30))
                    file.write_bytes(response.content);record.update(http_status=response.status_code,file=file.name,sha256=sha(file))
                    write(out/'requests.json',records);response.raise_for_status();body=response.json()
                    if not body.get('success') or body.get('result') is None:raise ValueError('provider query failed: '+str(body.get('message')))
                    result=body['result'];rows=result['data'];pages=int(result['pages'])
                    if pages>c['max_pages_per_query']:raise ValueError('query exceeds frozen page budget')
                    for row in rows:
                        if str(row['REPORT_DATE'])[:10]!=date or str(row['NOTICE_DATE'])[:10]>c['notice_cutoff']:raise ValueError('provider violated period filter')
                    allrows.extend(rows);record.update(state='PASS',rows=len(rows),pages=pages,total_count=result['count'])
                    write(out/'requests.json',records);print(f'R2_DATA {kind} {date} page={page}/{pages} rows={len(rows)}',flush=True)
                    page+=1;time.sleep(c['minimum_request_spacing_seconds'])
                if len(allrows)!=int(result['count']):raise ValueError('pagination count mismatch')
                write(out/f'{kind}_{date}_rows.json',allrows)
                keys=sorted({k for row in allrows for k in row})
                times=[k for k in keys if any(v in k for v in ['DATE','TIME'])]
                summary={'kind':kind,'period':date,'rows':len(allrows),'symbols':len({r['SECURITY_CODE'] for r in allrows}),
                    'fields':keys,'time_fields':{},'revision_history_verified':False}
                for field in times:
                    values=[str(r[field]) for r in allrows if r.get(field) is not None]
                    summary['time_fields'][field]={'nonnull':len(values),'min':min(values) if values else None,'max':max(values) if values else None,
                        'after_notice':sum(str(r.get(field) or '')[:10]>str(r['NOTICE_DATE'])[:10] for r in allrows)}
                keys_seen=[(r['SECURITY_CODE'],r['REPORT_DATE'],r.get('PREDICT_FINANCE_CODE')) for r in allrows]
                summary['duplicate_symbol_period_metric_rows']=len(keys_seen)-len(set(keys_seen))
                summaries.append(summary);write(out/'summary.json',summaries)
        write(out/'status.json',{'status':'PASS_DATA_ACQUISITION','queries':len(summaries),'requests':count,'returns_loaded':False,
            'research_admission':'UNVERIFIED_VERSIONS','qualification':'SEALED','lockbox':'SEALED'})
    except Exception as exc:
        write(out/'status.json',{'status':'FAIL','error':str(exc),'requests':count,'returns_loaded':False});raise
    finally:
        write(out/'artifact_hashes.json',{f.name:sha(f) for f in out.iterdir() if f.is_file() and f.name!='artifact_hashes.json'})


if __name__=='__main__':main()
