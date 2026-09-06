"""Evaluate the two frozen economic hypotheses, with matched BP controls."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import traceback
import numpy as np
import pandas as pd
from filelock import FileLock
from ..factors.engine import strict_write_json as write,verify_baseline
from ..factors.provenance import verify_data_identity
from ..factors.data import load_factor_data,preprocess,forward_labels
from ..factors.analytics import daily_ic,summarize_ic,correlation_matrix
from ..factors.portfolio import run_portfolios,portfolio_metrics
from .supplementary_data import protocol,PROTOCOL_SHA256
from .family_screen import checked_artifact
from .core import neutralize,block_inference,bh_adjust
from .comparability import modal_period_mask


def decision(coverage,stats,years,q,c):
    adequate=all(v is not None and v>=c['min_year_coverage'] for v in coverage.values())
    positive=sum(years.get(str(y),{}).get('rank_ic') is not None and years[str(y)]['rank_ic']>0 for y in c['full_years'])
    passed=(adequate and stats['rank_ic'] is not None and stats['rank_ic']>=c['min_rank_ic']
            and q<=c['max_q'] and positive>=c['positive_full_years_required'])
    return {'screen_status':'IC_SCREEN_PASS' if passed else 'IC_SCREEN_REJECT',
            'screen_coverage_gate':adequate,'positive_full_years':int(positive),
            'model_queue':'DATA_READY_FOR_BOUNDED_MODEL_PROTOCOL' if adequate else 'DATA_COVERAGE_BLOCKED',
            'independent_alpha':'NOT_CONFIRMED'}


def run(root,data):
    with FileLock(str(root/'data/factor_engine.lock'),timeout=0):return _run(root,data)


def _run(root,data):
    c=protocol(root)
    output=root/'experiments/m2'/'m2_supplementary_screen_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state={'status':'RUNNING','stage':'inputs','run_id':output.name};write(output/'status.json',state);write(output/'config.json',c)
    print(f'SUPPLEMENTARY_SCREEN {output}',flush=True)
    try:
        names=['src/quant_research/m2/supplementary_run.py','src/quant_research/m2/supplementary_data.py',
               'src/quant_research/m2/core.py','src/quant_research/m2/comparability.py',
               'src/quant_research/factors/data.py','src/quant_research/factors/analytics.py',
               'src/quant_research/factors/portfolio.py','scripts/run_supplementary.py','configs/factors/m2_supplementary.json']
        hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
        for n in names:
            dest=output/'source'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/n,dest)
        write(output/'source_hashes.json',hashes)
        if json.loads((data/'status.json').read_text())['status']!='PASS':raise ValueError('data collection did not pass')
        manifest=json.loads((data/'artifact_hashes.json').read_text())
        v=json.loads(checked_artifact(data,'verification.json',manifest).read_text())
        if v['protocol_sha256']!=PROTOCOL_SHA256:raise ValueError('data protocol differs')
        frames={n:pd.read_parquet(checked_artifact(data,n+'.parquet',manifest)) for n in
                ['membership','CFOToOR','ILLIQUIDITY_20','BP','log_size','industry','fiscal_period']}
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');verify_data_identity(root,baseline,frozen)
        market=load_factor_data(root,baseline)
        members=frames['membership'];dates=members.index
        pd.testing.assert_frame_equal(members,market.membership.reindex(index=dates,columns=members.columns),check_names=False)
        industry=frames['industry'];size=frames['log_size']
        known=industry.notna();financial=industry.isin(c['financial_codes'])
        universe=members & known & ~financial
        active=market.tradable.reindex(index=dates,columns=members.columns)
        mask=universe & active
        scores={};results={};all_checks=[];counts=[]
        start,end=c['observed_screen'];expected=dates[(dates>=start)&(dates<=end)]
        labels={h:forward_labels(market,h,[start,end]) for h in [c['primary_horizon'],*c['diagnostic_horizons']]}
        for year in sorted(dates.year.unique()):
            use=dates.year==year
            counts.append({'year':int(year),'members':int(members.loc[use].to_numpy().sum()),
                'known_industry':int((members&known).loc[use].to_numpy().sum()),
                'financial':int((members&financial).loc[use].to_numpy().sum()),
                'nonfinancial':int(universe.loc[use].to_numpy().sum())})
        pd.DataFrame(counts).to_csv(output/'universe_counts.csv',index=False)
        for name,field in [('CASHFLOW_MARGIN_YTD','CFOToOR'),('ILLIQUIDITY_20','ILLIQUIDITY_20'),('BP_reference','BP')]:
            raw=preprocess(frames[field],mask)
            score,check=neutralize(raw,size,industry);scores[name]=score;all_checks.append(check)
            folder=output/name;folder.mkdir();score.to_parquet(folder/'scores.parquet');check.to_csv(folder/'neutralization.csv',index=False)
            r={'coverage_by_year':{},'decay':{},'years':{}}
            for year in sorted(expected.year.unique()):
                den=universe.loc[str(year)].to_numpy().sum()
                r['coverage_by_year'][str(year)]=float(score.loc[str(year)].notna().to_numpy().sum()/den) if den else None
            for h,label in labels.items():
                daily=daily_ic(score,label,c['min_pairs']);daily.to_csv(folder/f'ic_h{h}.csv')
                r['decay'][str(h)]=summarize_ic(daily)
                if h==c['primary_horizon']:
                    r['primary']=summarize_ic(daily)
                    r['years']={str(y):summarize_ic(g) for y,g in daily.groupby(daily.index.year)}
                    r['temporal_splits']={label:summarize_ic(daily.loc[a:b]) for label,a,b in
                          [('pilot','2015-01-01','2016-12-31'),('burned_diagnostic','2017-01-01',end)]}
                    r['inference']=block_inference(daily.rank_ic,c['block_length'],c['bootstrap_samples'],c['seed'])
            results[name]=r;print(f'IC {name}',flush=True)
        candidates=list(c['hypotheses'])
        for name,q in zip(candidates,bh_adjust([results[n]['inference']['p'] for n in candidates])):
            r=results[name];r['q']=float(q);r.update(decision(r['coverage_by_year'],r['primary'],r['years'],q,c))
        write(output/'ic_metrics.json',results)
        correlation_matrix({n:s.loc[start:end] for n,s in scores.items()}).to_csv(output/'correlation.csv')
        # Predeclared common-fiscal-period diagnostic, never a new primary test.
        raw=frames['CFOToOR'];eligible=mask & raw.notna() & size.notna()
        same,_=modal_period_mask(frames['fiscal_period'],eligible)
        refit,check=neutralize(preprocess(raw,same),size,industry);all_checks.append(check)
        common=refit.notna() & scores['CASHFLOW_MARGIN_YTD'].notna()
        fiscal={}
        for name,panel in [('refit',refit.where(common)),('original_matched',scores['CASHFLOW_MARGIN_YTD'].where(common))]:
            daily=daily_ic(panel,labels[c['primary_horizon']],c['min_pairs']);daily.to_csv(output/f'fiscal_{name}_ic.csv')
            fiscal[name]=summarize_ic(daily)
        write(output/'fiscal_sensitivity.json',{'status':'DIAGNOSTIC_ONLY',**fiscal})
        import qlib
        qlib.init(provider_uri=str(root/'data/qlib'/baseline['name']),region='cn',kernels=1,expression_cache=None,dataset_cache=None)
        portfolio={}
        for name in candidates:
            common=scores[name].notna() & scores['BP_reference'].notna()
            pair={}
            if not common.loc[start:end].any().any():
                portfolio[name]={'status':'NO_COMMON_SCORES'};continue
            for kind,panel in [('candidate',scores[name].where(common)),('BP_matched',scores['BP_reference'].where(common))]:
                folder=output/name/kind;folder.mkdir()
                print(f'PORTFOLIO {name} {kind}',flush=True)
                metrics=run_portfolios(panel,start,end,baseline['backtest'],folder,expected)
                report=pd.read_csv(folder/'top20_daily.csv',index_col=0,parse_dates=True,dtype={'bench':np.float32})
                restored=portfolio_metrics(report)
                if abs(restored['net_excess_annual']-metrics['top20']['net_excess_annual'])>1e-10:raise ValueError('portfolio CSV changed metrics')
                pair[kind]={'metrics':metrics,'report':report}
            cand,bp=pair['candidate']['report'],pair['BP_matched']['report']
            delta=(cand['return']-cand.cost)-(bp['return']-bp.cost)
            delta.to_csv(output/name/'candidate_minus_BP.csv')
            inc=block_inference(delta,c['block_length'],c['bootstrap_samples'],c['seed'])
            inc['annual_difference']=float(delta.mean()*238)
            portfolio[name]={'status':'PASS','candidate':pair['candidate']['metrics'],'BP_matched':pair['BP_matched']['metrics'],
                             'replacement_difference':inc,'interpretation':'Candidate replaces BP; this is not the incremental effect of adding a candidate to Alpha158 or a blended portfolio'}
        write(output/'portfolio.json',portfolio)
        error=max(float(ch.orthogonality_error.max()) for ch in all_checks if len(ch))
        if error>1e-8:raise ValueError('neutralization check failed')
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        if any(hashlib.sha256((root/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):raise ValueError('source changed')
        table=pd.DataFrame([{'candidate':n,'rank_ic':results[n]['primary']['rank_ic'],'q':results[n]['q'],
               'min_year_coverage':min(v for v in results[n]['coverage_by_year'].values() if v is not None),
               'positive_full_years':results[n]['positive_full_years'],'status':results[n]['screen_status'],
               'model_queue':results[n]['model_queue']} for n in candidates])
        table.to_csv(output/'summary.csv',index=False)
        write(output/'verification.json',{'status':'PASS','data_run':data.name,'protocol_sha256':PROTOCOL_SHA256,
              'primary_tests':2,'max_orthogonality_error':error,'baseline_unchanged':True,'paired_masks_equal':True,
              'no_2021_plus_access':True,'rolling_model_increment':'NOT_RUN','independent_alpha':'NOT_CONFIRMED'})
        text=['# M2.3 固定补充批次结果','',table.to_markdown(index=False),'',
              '2008–2020年7月为数据范围；2015–2020年7月为已观察研究及已消耗诊断。主样本为历史非金融CSI300成分，方向/窗口/门槛未修改。','',
              'IC_SCREEN状态不是FORWARD/KEEP。两个五日主检验统一BH；20日、分期、财报期匹配只诊断。2020为不完整年度。','',
              '## 含成本同样本组合','']
        for n,p in portfolio.items():
            if p['status']=='PASS':
                text.append(f'- {n}: Top60候选超额年化 {p["candidate"]["top20"]["net_excess_annual"]:.2%}; 匹配BP {p["BP_matched"]["top20"]["net_excess_annual"]:.2%}; 替换年化差 {p["replacement_difference"]["annual_difference"]:.2%}。')
        text+=['','替换差不是加入Alpha158的模型增量。Top30只作诊断，未按收益选择组合规模。未冻结或运行滚动模型、资格与锁箱。',
               '','供应商修订未知；现金流为报告期比率，未重建TTM或独立验证全部分母；行业为滞后月度快照，规模为流通市值代理，沿用M0交易成本和涨跌停近似。',
               '','本补充批次后停止新增公式。旧ROE/净利润增长/低资产增长的REJECT不变；数据覆盖通过者可按固定预算进入模型比较，单因子IC弱不等于不存在非线性信息。']
        (output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
        write(output/'artifact_hashes.json',{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts and p.name!='status.json'})
        state.update(status='PASS',stage='complete');write(output/'status.json',state);print('PASS '+str(output),flush=True)
        return output
    except BaseException as exc:
        state.update(status='FAIL',error=str(exc));write(output/'status.json',state)
        (output/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
