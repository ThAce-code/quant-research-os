"""Offline cache salvage after provider refusal; incomplete histories stay withheld."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from quant_research.m2.quarterly import clean_events,daily_panel
from quant_research.factors.engine import strict_write_json as write


def main(root,failed):
    c=json.loads((failed/'config.json').read_text(encoding='utf-8'))
    plan=pd.read_csv(failed/'request_plan.csv');member=pd.read_parquet(failed/'membership.parquet')
    out=root/'experiments/m2/m2_history_cache_audit_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True);print('OFFLINE_AUDIT '+str(out),flush=True)
    panels={f:pd.DataFrame(np.nan,index=member.index,columns=member.columns) for fs in c['fields'].values() for f in fs}
    available=[];missing=[];audits=[];count=0
    for symbol,group in plan.groupby('symbol'):
        for method,fields in c['fields'].items():
            frames=[];complete=True
            for row in group.itertuples():
                request={'method':method,'params':{'code':row.code,'year':int(row.year),'quarter':int(row.quarter)}}
                key=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()[:24]
                path=root/'data/raw/baostock'/method/(key+'.csv');meta=path.with_suffix('.json')
                if not path.exists() or not meta.exists():
                    missing.append({'symbol':symbol,'method':method,**request['params'],'cache_key':key});complete=False
                else:
                    saved=json.loads(meta.read_text(encoding='utf-8'))
                    assert saved['method']==method and saved['params']==request['params']
                    assert hashlib.sha256(path.read_bytes()).hexdigest()==saved['sha256']
                    available.append({**saved,'path':str(path)})
                    frame=pd.read_csv(path,dtype=str,keep_default_na=False)
                    expected=pd.Period(year=row.year,quarter=row.quarter,freq='Q').end_time.normalize()
                    if len(frame):assert pd.to_datetime(frame.statDate,errors='coerce').eq(expected).all()
                    frames.append(frame)
                count+=1
                if count%2000==0:print(f'OFFLINE {count}/40520',flush=True)
            if complete:
                raw=pd.concat(frames,ignore_index=True)
                later=pd.to_datetime(raw.pubDate,errors='coerce').gt(c['data_period'][1]) if len(raw) else pd.Series(False,index=raw.index)
                events,bad=clean_events(raw.loc[~later],group.code.iloc[0],fields,c['data_period'][1]);assert bad.empty
                joined=daily_panel(events,member.index,fields,400,550)
                for f in fields:panels[f][symbol]=pd.to_numeric(joined[f]).where(member[symbol])
            audits.append({'symbol':symbol,'method':method,'complete_request_history':complete,'cached_requests':len(frames),'required_requests':len(group)})
    pd.DataFrame(missing).to_csv(out/'missing_requests.csv',index=False)
    pd.DataFrame(audits).to_csv(out/'stock_method_completeness.csv',index=False)
    write(out/'available_requests.json',available)
    coverage=[]
    for field,panel in panels.items():
        panel.to_parquet(out/f'{field}_complete_histories_only.parquet')
        for year in sorted(member.index.year.unique()):
            m=member.loc[str(year)];n=(panel.loc[str(year)].notna()&m).to_numpy().sum()
            coverage.append({'field':field,'year':int(year),'available_cells':int(n),'member_cells':int(m.to_numpy().sum()),'coverage':float(n/m.to_numpy().sum())})
    pd.DataFrame(coverage).to_csv(out/'coverage_complete_histories_only.csv',index=False)
    result={'status':'PARTIAL_BLOCKED','network_calls':0,'planned_requests':count,'verified_cached_requests':len(available),
            'missing_requests':len(missing),'complete_symbol_methods':sum(a['complete_request_history'] for a in audits),
            'total_symbol_methods':len(audits),'data_complete':not missing,'provider_error':'10001011',
            'source_failed_run':failed.name,'interpretation':'Known incomplete symbol-method histories are entirely withheld; no old-value resurrection or completeness claim'}
    write(out/'verification.json',result);write(out/'status.json',result)
    (out/'report.md').write_text('# M2历史财务离线保全\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+
        '\n\nBaoStock明确拒绝访问后停止网络请求。缺失请求不是字段本身为空；任何缺少季度响应的股票/接口历史整体不进入保全面板，避免未知新公告被旧数据替代。'
        '已验证缓存可以在服务恢复后复用，但本报告不代表完整数据验收。缺失清单见missing_requests.csv。M2整体目标仍未完成。\n',encoding='utf-8')
    write(out/'source_hashes.json',{'scripts/audit_history_cache.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    write(out/'artifact_hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='artifact_hashes.json'})
    print(json.dumps(result),flush=True);print('OFFLINE_DONE '+str(out),flush=True)


if __name__=='__main__':main(Path(__file__).resolve().parents[1],Path(sys.argv[1]))
