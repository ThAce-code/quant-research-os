"""Fiscal-period/sector diagnostics; no new candidate admission decisions."""
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
from ..factors.data import load_factor_data, preprocess, forward_labels
from ..factors.analytics import daily_ic, summarize_ic
from .core import neutralize
from .family_screen import checked_artifact


def sector_codes(industry):
    # Use the stable CSRC code; display names in the old vendor snapshot are mojibake.
    return industry.apply(lambda col: col.astype('string').str.extract(r'^([A-S]\d{2})', expand=False))


def modal_period_mask(periods, eligible):
    chosen = pd.Series(pd.NaT, index=periods.index, dtype='datetime64[ns]')
    for day in periods.index:
        counts = periods.loc[day].where(eligible.loc[day]).dropna().value_counts()
        if len(counts):
            chosen.loc[day] = max(counts.index[counts.eq(counts.max())])
    return periods.eq(chosen, axis=0) & eligible, chosen


def run(root):
    with FileLock(str(root/'data/factor_engine.lock'), timeout=0):
        return _run(root)


def _run(root):
    c = json.loads((root/'configs/factors/m2_comparability.json').read_text(encoding='utf-8'))
    if c['period'] != ['2015-01-01', '2016-12-31'] or max(c['probe_years']) > 2020:
        raise ValueError('diagnostic date boundary changed')
    output = root/'experiments/m2'/c['name']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state = {'status':'RUNNING','stage':'inputs','run_id':output.name}
    write(output/'status.json',state);write(output/'config.json',c)
    print(f'COMPARABILITY_RUN {output}',flush=True)
    try:
        sources=['configs/factors/m2_comparability.json','src/quant_research/m2/comparability.py',
                 'src/quant_research/m2/core.py','src/quant_research/m2/family_screen.py',
                 'src/quant_research/factors/data.py','src/quant_research/factors/analytics.py',
                 'src/quant_research/baostock_data.py','scripts/run_comparability.py']
        hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sources}
        for n in sources:
            target=output/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/n,target)
        write(output/'source_hashes.json',hashes)
        qdir=root/c['quarterly_run'];qhash=json.loads((qdir/'data_manifest.json').read_text())
        sdir=root/c['screen_run'];shash=json.loads((sdir/'artifact_hashes.json').read_text())
        pdir=root/c['pilot_run'];phash=json.loads((pdir/'artifact_hashes.json').read_text())
        for directory in [qdir,sdir,pdir]:
            if json.loads((directory/'status.json').read_text())['status']!='PASS':raise ValueError('input run not passed')
        qc=json.loads(checked_artifact(qdir,'config.json',qhash).read_text())
        original=json.loads(checked_artifact(sdir,'metrics.json',shash).read_text())
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');verify_data_identity(root,baseline,frozen)
        market=load_factor_data(root,baseline)
        members=pd.read_parquet(checked_artifact(qdir,'membership.parquet',qhash))
        dates=members.index;symbols=members.columns
        size=pd.read_parquet(checked_artifact(pdir,'data/log_circulating_cap_proxy.parquet',phash)).reindex(index=dates,columns=symbols)
        industry=pd.read_parquet(checked_artifact(pdir,'data/industry.parquet',phash)).reindex(index=dates,columns=symbols)
        codes=sector_codes(industry);known=codes.notna();financial=codes.isin(c['financial_codes'])
        labels=forward_labels(market,c['horizon'],c['period'])
        active=market.tradable.reindex(index=dates,columns=symbols) & members
        fiscal={};mixed=[];waterfall=[];rows=[];checks=[]
        for method in qc['fields']:
            periods=pd.DataFrame(pd.NaT,index=dates,columns=symbols,dtype='datetime64[ns]')
            for symbol in symbols:
                rel=f'events/{symbol}_{method}_daily.parquet'
                periods[symbol]=pd.to_datetime(pd.read_parquet(checked_artifact(qdir,rel,qhash)).statDate)
            fiscal[method]=periods
            counts=periods.where(members).apply(lambda r:r.value_counts(),axis=1).fillna(0)
            largest=counts.max(axis=1);available=counts.sum(axis=1)
            for year in [2015,2016]:
                use=dates.year==year
                mixed.append({'method':method,'year':year,'days':int(use.sum()),
                              'days_multiple_periods':int(counts.loc[use].gt(0).sum(axis=1).gt(1).sum()),
                              'mean_off_modal_share':float((1-largest/available).loc[use].mean())})
        for name,d in qc['candidates'].items():
            field=d['field'];method=next(k for k,v in qc['fields'].items() if field in v)
            raw=pd.read_parquet(checked_artifact(qdir,field+'.parquet',qhash)).reindex(index=dates,columns=symbols)*d['direction']
            old=pd.read_parquet(checked_artifact(sdir,name+'/scores.parquet',shash)).reindex(index=dates,columns=symbols)
            eligible=members & raw.notna();usable=eligible & active
            exposures=usable & size.notna() & known
            large=industry.where(exposures).apply(lambda r:r.map(r.value_counts()).ge(5),axis=1) & exposures
            for year in [2015,2016]:
                ix=dates.year==year
                waterfall.append({'candidate':name,'year':year,**{k:int(v.loc[ix].to_numpy().sum()) for k,v in
                      {'membership':members,'raw_available':eligible,'active':usable,'known_exposures':exposures,
                       'large_industry_groups':large,'original_neutral':old.notna(),
                       'financial_raw':eligible & financial,'unknown_industry_raw':eligible & ~known}.items()}})
            nonfinancial=exposures & ~financial
            same,chosen=modal_period_mask(fiscal[method],nonfinancial)
            for view,mask in [('nonfinancial',nonfinancial),('nonfinancial_same_fiscal_period',same)]:
                score,check=neutralize(preprocess(raw,mask),size,industry);checks.append(check)
                common=score.notna() & old.notna();score=score.where(common);matched=old.where(common)
                folder=output/name/view;folder.mkdir(parents=True)
                for variant,panel in [('refit',score),('original_matched',matched)]:
                    daily=daily_ic(panel,labels,c['min_pairs']);daily.to_csv(folder/(variant+'_ic.csv'))
                    for year,group in [('all',daily),*[(str(y),g) for y,g in daily.groupby(daily.index.year)]]:
                        rows.append({'candidate':name,'view':view,'variant':variant,'year':year,
                                     **summarize_ic(group),'status':'DIAGNOSTIC_ONLY'})
                if not score.notna().equals(matched.notna()):raise ValueError('comparison samples differ')
            print(f'DIAGNOSTICS {name}',flush=True)
        pd.DataFrame(mixed).to_csv(output/'fiscal_mixing.csv',index=False)
        pd.DataFrame(waterfall).to_csv(output/'coverage_waterfall.csv',index=False)
        pd.DataFrame(rows).to_csv(output/'sensitivity.csv',index=False)
        # Fixed availability probe. No candidate return calculations use these observations.
        probes=[];examples=[]
        with BaoStockCache(root/'data/raw/baostock') as source:
            for code in c['probe_codes']:
                for year in c['probe_years']:
                    for quarter in ([1] if year==2020 else [1,4]):
                        for method in c['probe_methods']:
                            f=source.query(method,allow_empty=True,code=code,year=year,quarter=quarter)
                            probes.append({'code':code,'year':year,'quarter':quarter,'method':method,'rows':len(f),
                                           'pubDate':None if f.empty else str(f.pubDate.iloc[0])})
            for q in [1,2,3,4]:
                f=source.query('query_profit_data',allow_empty=True,code='sh.600519',year=2015,quarter=q)
                examples.extend(f[['pubDate','statDate','roeAvg','npMargin','netProfit']].to_dict('records'))
            f=source.query('query_cash_flow_data',allow_empty=True,code='sh.600519',year=2015,quarter=4)
            cash=f.CFOToOR.iloc[0] if len(f) else None
            write(output/'requests.json',source.manifest)
        pd.DataFrame(probes).to_csv(output/'availability_probes.csv',index=False)
        pd.DataFrame(examples).to_csv(output/'reporting_period_example.csv',index=False)
        e=next(r for r in examples if r['statDate']=='2015-12-31')
        # Issuer 2015 annual report, pp.5 and 41, mirrored by Sina/Stockstar.
        reported_profit=16454996625.22;parent_profit=15503090276.38;revenue=32659583725.28
        checks_issuer={'issuer':'SH600519','statDate':'2015-12-31',
                      'report_url':'https://stock.stockstar.com/notice/JC2016032400000505.shtml',
                      'summary_url':'https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?CompanyCode=10000351&gather=1&id=2269811',
                      'vendor_netProfit_matches_consolidated_profit':abs(float(e['netProfit'])-reported_profit)<.01,
                      'vendor_netProfit_is_not_parent_profit':abs(float(e['netProfit'])-parent_profit)>1,
                      'roeAvg_formula_absolute_error':abs(float(e['roeAvg'])-parent_profit/((63925978438.99+53430402446.09)/2)),
                      'npMargin_absolute_error':abs(float(e['npMargin'])-reported_profit/revenue),
                      'CFOToOR_absolute_error':None if cash is None else abs(float(cash)-17436340141.72/revenue),
                      'scope':'One issuer-year crosscheck; not proof that all vendor fields or vintages are correct'}
        if not checks_issuer['vendor_netProfit_matches_consolidated_profit'] or checks_issuer['roeAvg_formula_absolute_error']>1e-6:
            raise ValueError('issuer crosscheck failed')
        write(output/'issuer_crosscheck.json',checks_issuer)
        canonical=root/'data/canonical'/baseline['name']
        intervals=pd.read_parquet(canonical/'membership.parquet')
        intervals['start']=pd.to_datetime(intervals.start);intervals['end']=pd.to_datetime(intervals.end)
        scope=[]
        for year in range(2008,2021):
            start=pd.Timestamp(f'{year}-01-01');end=min(pd.Timestamp(f'{year}-12-31'),pd.Timestamp('2020-07-31'))
            scope.append({'year':year,'end':str(end.date()),'historical_member_union':int(intervals.loc[intervals.start.le(end)&intervals.end.ge(start),'instrument'].nunique())})
        pd.DataFrame(scope).to_csv(output/'historical_scope.csv',index=False)
        error=max(float(ch.orthogonality_error.max()) for ch in checks if len(ch))
        if error>1e-8:raise ValueError('neutralization orthogonality failed')
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        if any(hashlib.sha256((root/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):raise ValueError('source changed')
        verification={'status':'PASS','original_decisions':{n:r['screen_status'] for n,r in original.items()},
                      'diagnostic_only':True,'max_orthogonality_error':error,'input_hashes_checked':True,
                      'baseline_unchanged':True,'financial_code_rule':c['financial_codes'],
                      'probe_requests':len(probes),'nonempty_probes':sum(p['rows']>0 for p in probes),
                      'full_history_collected':False,'qualification_or_lockbox_requested':False}
        write(output/'verification.json',verification)
        summary=pd.DataFrame(rows);selected=summary[summary.year.eq('all')][['candidate','view','variant','rank_ic','days']]
        text=['# M2.3 基本面可比性诊断','',
              '本批仅诊断2015–2016已观察历史。原三项IC_SCREEN_REJECT不变，不按敏感性结果翻方向或升级。','',
              '## 同日财报统计期混用','',pd.DataFrame(mixed).to_markdown(index=False),'',
              '## 金融行业与同报告期敏感性','',selected.to_markdown(index=False),'',
              'refit为在预定子样本重新中性化；original_matched为原分数限制到完全相同股票。不同view之间仍不是同样本，不能直接择优。','',
              '## 报表口径','',
              '茅台2015年供应商netProfit与年报合并净利润一致，而非归母净利润；roeAvg与归母利润/期初期末平均归母权益一致，不能当成加权ROE或TTM ROE。年度npMargin、CFOToOR对照见issuer_crosscheck.json。',
              '来源：[发行人2015年报全文镜像](https://stock.stockstar.com/notice/JC2016032400000505.shtml)、[年报摘要数据镜像](https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?CompanyCode=10000351&gather=1&id=2269811)。只有一个公司年度得到交叉核对，不能推定全库无修订。','',
              '## 更长研究区间','',
              f'目标2008–2020年7月；固定3只股票、6个年份、3个接口共{len(probes)}项可用性探针，非空{verification["nonempty_probes"]}项。逐年历史成分并集见historical_scope.csv。探针不等于全历史/全股票季度覆盖。',
              '2015–2016为已观察研究区间，2017–2020为已消耗诊断；2021–2023资格与2024–2025锁箱仍保护。','',
              '行业名称存在旧供应商编码乱码，使用已有稳定的CSRC行业代码前缀，不改旧分组或封存数据。供应商历史修订未知、样本筛选损耗、财报时间口径和金融业务可比性仍需在扩展实验中显式保留。']
        (output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
        write(output/'artifact_hashes.json',{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts and p.name!='status.json'})
        state.update(status='PASS',stage='complete');write(output/'status.json',state)
        print('PASS '+str(output),flush=True)
        return output
    except BaseException as exc:
        state.update(status='FAIL',error=str(exc));write(output/'status.json',state)
        (output/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
