"""Archive dated CNINFO earnings-notice indices and original PDFs, no return access."""
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlparse
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/r2/announcement_backfill.json'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def read(p):return json.loads(p.read_text(encoding='utf-8'))


def candidate_title(title,year):
    years=set(re.findall(r'20\d{2}',title))
    return '一季度' in title and '业绩' in title and (not years or str(year) in years)


def main():
    c=read(CONFIG);out=ROOT/'experiments/r2'/c['name'];out.mkdir(parents=True,exist_ok=False)
    (out/'pdf').mkdir();(out/'source').mkdir();shutil.copyfile(Path(__file__),out/'source'/Path(__file__).name);shutil.copyfile(CONFIG,out/'source'/CONFIG.name)
    members=pd.read_parquet(ROOT/c['membership_path']);log=[];selected={};summaries=[]
    write(out/'source_hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in [CONFIG,Path(__file__),ROOT/c['membership_path'],ROOT/'data/baostock_access_restriction.json']})
    def request(url,payload=None,file=None):
        record={'url':url,'payload':payload,'file':str(file.relative_to(out)),'fetched_at':datetime.now(timezone.utc).isoformat(),'state':'RESERVED'}
        log.append(record);write(out/'requests.json',log)
        try:
            r=requests.post(url,data=payload,timeout=(10,30)) if payload is not None else requests.get(url,timeout=(10,30))
            file.write_bytes(r.content);record.update(http_status=r.status_code,sha256=sha(file))
            r.raise_for_status();record['state']='PASS';return r
        except requests.RequestException as exc:
            record.update(state='FAIL',error=str(exc));raise
        finally:
            write(out/'requests.json',log);time.sleep(c['minimum_request_spacing_seconds'])
    write(out/'status.json',{'status':'RUNNING','stage':'index','returns_loaded':False})
    try:
        for year in c['years']:
            assert year<2021
            begin=f'{year}-01-01';end=f'{year}-04-30'
            union=set(members.loc[(pd.to_datetime(members.start)<=end)&(pd.to_datetime(members.end)>=begin),'instrument'].str[2:])
            wanted=union|set(c['audit_sentinels']);rows=[];pages=1;page=1
            while page<=pages:
                payload={'pageNum':str(page),'pageSize':str(c['page_size']),'column':'szse','tabName':'fulltext','plate':'','stock':'',
                    'searchkey':c['keyword'],'secid':'','category':'','trade':'','seDate':begin+'~'+end,
                    'sortName':'time','sortType':'asc','isHLtitle':'false'}
                body=request(c['search_endpoint'],payload,out/f'index_{year}_{page}.json').json()
                total=int(body['totalAnnouncement']);pages=math.ceil(total/c['page_size'])
                if pages>c['max_index_pages_per_year']:raise ValueError('index budget exceeded')
                part=body.get('announcements') or []
                if not part and total:raise ValueError('empty page in nonempty result')
                rows.extend(part);print(f'R2_INDEX {year} {page}/{pages}',flush=True);page+=1
            if len(rows)!=total:raise ValueError('index pagination mismatch')
            write(out/f'index_{year}_rows.json',rows)
            for row in rows:
                title=re.sub('<[^>]*>','',row['announcementTitle'])
                date=pd.Timestamp(row['announcementTime'],unit='ms',tz='UTC').tz_convert('Asia/Shanghai').strftime('%Y-%m-%d')
                if not begin<=date<=end:raise ValueError('notice outside frozen period')
                if row['secCode'] not in wanted:continue
                if not candidate_title(title,year):continue
                relative=row.get('adjunctUrl') or ''
                if not re.fullmatch(r'finalpage/20(?:15|16)-\d\d-\d\d/[A-Za-z0-9_.-]+\.[Pp][Dd][Ff]',relative):raise ValueError('unexpected PDF source path')
                aid=str(row['announcementId'])
                if not aid.isdigit():raise ValueError('invalid announcement ID')
                key=(aid,row['secCode'])
                selected[key]={**row,'announcementTitle':title,'notice_date':date,'query_year':year,
                    'historical_member_union':row['secCode'] in union,'audit_sentinel':row['secCode'] in c['audit_sentinels'],
                    'document_url':c['document_host']+relative,'local_pdf':'pdf/'+aid+'.pdf'}
            summaries.append({'year':year,'query_rows':len(rows),'unique_announcement_ids':len({str(r['announcementId']) for r in rows}),
                              'member_union':len(union),'selected_rows':sum(r['query_year']==year for r in selected.values())})
        assets=list(selected.values());write(out/'selected.json',assets);write(out/'index_summary.json',summaries)
        if len({r['announcementId'] for r in assets})>c['max_documents']:raise ValueError('document budget exceeded')
        failures=[];downloaded=set()
        for row in assets:
            aid=str(row['announcementId']);file=out/row['local_pdf']
            if aid in downloaded:continue
            write(out/'status.json',{'status':'RUNNING','stage':'documents','downloaded':len(downloaded),'selected':len(assets)})
            try:
                response=request(row['document_url'],file=file)
                if not response.content.startswith(b'%PDF'):raise ValueError('response is not PDF')
                downloaded.add(aid);print(f'R2_PDF {len(downloaded)}/{len(assets)} {aid}',flush=True)
            except requests.RequestException as exc:
                failures.append({'announcement_id':aid,'error':str(exc)});write(out/'document_failures.json',failures)
                # Restriction responses stop the provider. Other missing documents remain gaps.
                if getattr(getattr(exc,'response',None),'status_code',None) in [401,403,429]:raise
        write(out/'document_failures.json',failures)
        write(out/'status.json',{'status':'PASS_ARCHIVE' if not failures else 'PARTIAL_ARCHIVE','index_queries':len(c['years']),
            'selected':len(assets),'pdfs':len(downloaded),'failures':len(failures),'requests':len(log),
            'returns_loaded':False,'factor_admission':'NOT_EVALUATED','protected_periods':'SEALED'})
    except Exception as exc:
        write(out/'status.json',{'status':'FAIL','error':str(exc),'requests':len(log),'returns_loaded':False});raise
    finally:
        write(out/'artifact_hashes.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_hashes.json'})


if __name__=='__main__':main()
