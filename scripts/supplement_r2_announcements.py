"""Recover exact-date primary reports for gaps left by title-only discovery."""
from datetime import datetime,timezone
import hashlib,json,math,re,shutil,time
from pathlib import Path
import requests
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def relevant_report(title,year):
    if any(w in title for w in ['英文','审计','摘要（英文','业绩说明会','业绩网上','承诺','补偿']):return False
    if '业绩' in title and any(w in title for w in ['预告','快报','预计']):return True
    return str(year-1) in title and any(w in title for w in ['年度报告','年报']) and not any(w in title for w in ['意见','工作','事会','独立董事','监管','问询'])


def main():
    config=ROOT/'configs/r2/backfill_supplement.json';c=read(config);out=ROOT/'experiments/r2'/c['name'];out.mkdir(parents=True,exist_ok=False)
    (out/'pdf').mkdir();(out/'source').mkdir();shutil.copyfile(config,out/'source'/config.name);shutil.copyfile(Path(__file__),out/'source'/Path(__file__).name)
    ids_path=ROOT/'experiments/r2/cninfo_source_probe/stock_identifiers.json'
    ids={r['code']:r['orgId'] for r in read(ids_path)['stockList']};log=[];assets={};gaps=[];results=[]
    write(out/'source_hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in [config,Path(__file__),ids_path]})
    def fetch(url,file,payload=None):
        record={'url':url,'params':payload,'file':str(file.relative_to(out)),'fetched_at':datetime.now(timezone.utc).isoformat(),'state':'RESERVED'}
        log.append(record);write(out/'requests.json',log)
        try:
            r=requests.post(url,data=payload,timeout=(10,30)) if payload is not None else requests.get(url,timeout=(10,30))
            file.write_bytes(r.content);record.update(http_status=r.status_code,sha256=sha(file));r.raise_for_status();record['state']='PASS';return r
        except requests.RequestException as exc:record.update(state='FAIL',error=str(exc));raise
        finally:write(out/'requests.json',log);time.sleep(c['spacing_seconds'])
    def add(row,year,reason):
        path=row['adjunctUrl']
        if not re.fullmatch(r'finalpage/20(?:15|16)-\d\d-\d\d/[\w.-]+\.[Pp][Dd][Ff]',path):raise ValueError('unexpected document path')
        aid=str(row['announcementId']);date=pd.Timestamp(row['announcementTime'],unit='ms',tz='UTC').tz_convert('Asia/Shanghai').strftime('%Y-%m-%d')
        assets[aid]={**row,'notice_date':date,'query_year':year,'historical_member_union':reason!='yearless_sentinel','audit_sentinel':reason=='yearless_sentinel',
            'document_url':'https://static.cninfo.com.cn/'+path,'local_pdf':'pdf/'+aid+'.pdf',
            'archive_pdf_path':str((out/'pdf'/f'{aid}.pdf').relative_to(ROOT)),'retrieval_reason':reason}
    write(out/'status.json',{'status':'RUNNING','returns_loaded':False})
    try:
        for i,case in enumerate(c['cases']):
            code=case['code'];day=case['notice_date'];year=case['year']
            if code not in ids:gaps.append({**case,'reason':'ORG_ID_UNAVAILABLE'});continue
            rows=[];page=1;pages=1
            while page<=pages:
                payload={'pageNum':str(page),'pageSize':'30','column':'szse','tabName':'fulltext','plate':'','stock':code+','+ids[code],
                    'searchkey':'','secid':'','category':'','trade':'','seDate':day+'~'+day,'sortName':'time','sortType':'asc','isHLtitle':'false'}
                body=fetch('https://www.cninfo.com.cn/new/hisAnnouncement/query',out/f'query_{code}_{day}_{page}.json',payload).json()
                total=int(body['totalAnnouncement']);pages=math.ceil(total/30)
                if pages>c['max_query_pages']:raise ValueError('exact-date query budget exceeded')
                rows.extend(body.get('announcements') or []);page+=1
            if len(rows)!=total:raise ValueError('pagination count mismatch')
            hits=[]
            for row in rows:
                if row['secCode']!=code:raise ValueError('stock filter mismatch')
                if relevant_report(row['announcementTitle'],year):add(row,year,'exact_date_gap');hits.append(str(row['announcementId']))
            results.append({**case,'query_rows':len(rows),'selected_ids':hits})
            if not hits:gaps.append({**case,'reason':'NO_RELEVANT_REPORT_ON_SNAPSHOT_DATE'})
            print(f'R2_SUPPLEMENT_INDEX {i+1}/{len(c["cases"])} {code} hits={len(hits)}',flush=True)
        base=ROOT/'experiments/r2/r2_cninfo_q1_backfill_v1'
        for year in [2015,2016]:
            for row in read(base/f'index_{year}_rows.json'):
                if str(row['announcementId']) in c['yearless_announcement_ids']:add(row,year,'yearless_sentinel')
        for row in read(base/'selected.json'):
            if str(row['announcementId']) in c.get('transient_502_recovery_once',[]):add(row,row['query_year'],'single_new_attempt_after_502')
        if len(assets)>c['max_pdfs']:raise ValueError('PDF budget exceeded')
        write(out/'selected.json',list(assets.values()));write(out/'query_results.json',results)
        completed=0
        for row in assets.values():
            aid=str(row['announcementId'])
            try:
                r=fetch(row['document_url'],out/row['local_pdf'])
                if not r.content.startswith(b'%PDF'):raise ValueError('non-PDF response')
                completed+=1;print(f'R2_SUPPLEMENT_PDF {completed}/{len(assets)} {aid}',flush=True)
            except requests.RequestException as exc:
                gaps.append({'announcement_id':aid,'reason':str(exc)})
                if getattr(getattr(exc,'response',None),'status_code',None) in [401,403,429]:raise
        write(out/'gaps.json',gaps);write(out/'status.json',{'status':'PASS_ARCHIVE' if completed==len(assets) else 'PARTIAL_ARCHIVE',
            'documents':completed,'selected':len(assets),'queries':len(results),'gaps':len(gaps),'requests':len(log),'returns_loaded':False})
    except Exception as exc:write(out/'status.json',{'status':'FAIL','error':str(exc),'requests':len(log),'returns_loaded':False});raise
    finally:write(out/'artifact_hashes.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_hashes.json'})


if __name__=='__main__':main()
