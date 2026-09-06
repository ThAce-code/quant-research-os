"""One bounded research job: extract Alpha158, map its geometry, diagnose BP."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import hashlib
import traceback
import numpy as np
import pandas as pd
from filelock import FileLock
from scipy.stats import spearmanr

from ..factors.data import load_factor_data, forward_labels
from ..factors.analytics import daily_ic,summarize_ic
from ..factors.engine import verify_baseline,strict_write_json as write
from ..factors.provenance import verify_data_identity
from ..integrity import file_hashes
from .alpha_map import family,check_dates,mean_rank_correlation,cluster_basis,compress_basis,conditional_residual


def run(root):
    with FileLock(str(root/'data/factor_engine.lock'),timeout=0):
        return _run(root)


def _run(root):
    config=json.loads((root/'configs/factors/m2_alpha_map.json').read_text())
    check_dates(config)
    output=root/'experiments/m2'/config['name']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state={'status':'RUNNING','stage':'extract'};write(output/'status.json',state)
    write(output/'config.json',config)
    print(f'ALPHA_MAP {output}',flush=True)
    try:
        snapshot=[root/'configs/factors/m2_alpha_map.json',root/'scripts/run_alpha_map.py',root/'run-alpha-map.ps1',
                  root/'src/quant_research/m2/alpha_map.py',root/'src/quant_research/m2/alpha_map_run.py']
        source={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot}
        for p in snapshot:
            target=output/'source'/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        verify_data_identity(root,baseline,frozen)
        provider=root/'data/qlib'/baseline['name']
        if file_hashes(provider,'**/*')!=frozen['original_provenance']['qlib_files_sha256']:
            raise ValueError('provider differs from M0')
        market=load_factor_data(root,baseline)
        dates=market.membership.loc[config['start']:config['end']].index
        mask=(market.membership & market.tradable).loc[dates]
        symbols=mask.any()[lambda s:s].index.tolist()
        import qlib
        from qlib.data import D
        from qlib.contrib.data.handler import Alpha158
        qlib.init(provider_uri=str(provider),region='cn',kernels=1,expression_cache=None,dataset_cache=None)
        expressions,names=Alpha158.get_feature_config(None)
        if len(names)!=158 or len(set(names))!=158:raise ValueError('unexpected Alpha158 catalog')
        catalog=pd.DataFrame({'feature':names,'expression':expressions,'family':[family(n) for n in names]})
        catalog.to_csv(output/'catalog.csv',index=False)
        print('Extracting exact 158 Qlib expressions',flush=True)
        features=D.features(symbols,expressions,start_time=config['start'],end_time=config['end'])
        features.columns=names
        features=features.reorder_levels(['datetime','instrument']).sort_index()
        eligible=mask.rename_axis(index='datetime',columns='instrument').stack(future_stack=True)
        features=features.loc[eligible.reindex(features.index).fillna(False)].replace([np.inf,-np.inf],np.nan)
        features.to_parquet(output/'features.parquet')
        rows=[]
        for split in ['basis_fit','diagnostic']:
            period=config[split]
            labels=forward_labels(market,config['horizon'],period)
            expected=market.membership.loc[period[0]:period[1]].to_numpy().sum()
            directory=output/split;directory.mkdir()
            for name in names:
                panel=features[name].unstack('instrument').loc[period[0]:period[1]]
                daily=daily_ic(panel,labels,config['min_pairs'])
                daily.to_csv(directory/f'{name}_ic.csv')
                rows.append({'feature':name,'family':family(name),'split':split,
                             'coverage':float(panel.notna().to_numpy().sum()/expected),**summarize_ic(daily)})
            print(f'IC complete: {split}',flush=True)
        metrics=pd.DataFrame(rows);metrics.to_csv(output/'feature_metrics.csv',index=False)
        fit=features.loc[config['basis_fit'][0]:config['basis_fit'][1]]
        print('Calculating 158 x 158 daily pairwise Spearman matrix on 2015 only',flush=True)
        corr,counts=mean_rank_correlation(fit,config['min_pairs'])
        corr.to_csv(output/'correlation.csv');counts.to_csv(output/'correlation_days.csv')
        coverage=metrics[metrics.split.eq('basis_fit')].set_index('feature').coverage
        clusters,z,order=cluster_basis(corr,counts,coverage,config['min_correlation_days'],
                                       config['min_basis_coverage'],config['cluster_distance'])
        clusters.to_csv(output/'clusters.csv',index=False)
        reps=clusters.loc[clusters.is_representative,'feature'].tolist()
        basis={'fit_period':config['basis_fit'],'method':config['representative'],'representatives':reps,
               'orientation':config['orientation'],'not_a_KEEP_pool':True,
               'excluded_features':sorted(set(names)-set(clusters.feature)),
               'meaning':'technical representative set; neither independent alphas nor guaranteed full-rank basis'}
        write(output/'basis.json',basis)
        print(f'Frozen technical representatives: {len(reps)}',flush=True)
        compressed,loadings,pca=compress_basis(features[reps],config['basis_fit'],config['pca_variance_target'],config['pca_max_components'])
        loadings.to_csv(output/'pca_loadings.csv');write(output/'pca.json',pca)
        print(f"PCA: {pca['components']} dimensions; variance retained {pca['variance_retained']:.3f}",flush=True)
        # Reuse the exact BP pilot snapshot. No new fundamental data request.
        prior=root/config['candidate_run']
        if json.loads((prior/'status.json').read_text())['status']!='PASS':raise ValueError('candidate pilot not passed')
        paths=[prior/config['candidate']/'scores.parquet',prior/'data/log_circulating_cap_proxy.parquet',prior/'data/industry.parquet']
        expected_hashes=json.loads((prior/'artifact_hashes.json').read_text())
        for path in paths:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hashes[str(path.relative_to(prior))]:
                raise ValueError('candidate input differs from pilot')
        candidate,size,industry=[pd.read_parquet(p) for p in paths]
        diagnostic_dates=dates[(dates>=config['diagnostic'][0])&(dates<=config['diagnostic'][1])]
        matched,residual,checks=conditional_residual(candidate.loc[diagnostic_dates],compressed,
                                                    size.loc[diagnostic_dates],industry.loc[diagnostic_dates],
                                                    config['residual_min_rows_per_parameter'])
        matched.to_parquet(output/'bp_matched.parquet');residual.to_parquet(output/'bp_residual.parquet')
        checks.to_csv(output/'bp_projection_checks.csv',index=False)
        labels=forward_labels(market,config['horizon'],config['diagnostic'])
        results={}
        for name,panel in [('matched',matched),('residual',residual)]:
            daily=daily_ic(panel,labels,config['min_pairs']);daily.to_csv(output/f'bp_{name}_ic.csv')
            results[name]={**summarize_ic(daily),'coverage':float(panel.notna().to_numpy().sum()/market.membership.loc[diagnostic_dates].to_numpy().sum())}
        results['status']='DIAGNOSTIC_ONLY' if not checks.empty else 'INSUFFICIENT_COMMON_SAMPLE'
        results['mean_explained_fraction']=checks.explained_fraction.mean() if not checks.empty else None
        results['conclusion']='Linear residual signal does not establish incremental model returns; rolling add/drop still required.'
        write(output/'bp_conditional.json',results)
        # Small correctness checks for this research operation, not a new audit system.
        sample_day=fit.index.get_level_values('datetime').unique()[30]
        sample=fit.xs(sample_day,level='datetime')[['SUMP5','SUMN5']].dropna()
        if len(sample)>=30 and sample.std().gt(0).all():
            assert spearmanr(sample.iloc[:,0],sample.iloc[:,1]).statistic < -.99
        assert matched.notna().equals(residual.notna())
        if not checks.empty and checks.orthogonality_error.max()>1e-8:raise ValueError('projection check failed')
        # A shorter end request must match the same values in the full extraction.
        short=D.features([symbols[0]],expressions[:13],start_time='2015-06-01',end_time='2015-06-30')
        short.columns=names[:13];short=short.reorder_levels(['datetime','instrument']).sort_index()
        overlap=short.index.intersection(features.index)
        pd.testing.assert_frame_equal(short.loc[overlap].replace([np.inf,-np.inf],np.nan),features.loc[overlap,names[:13]],check_dtype=False)
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in source.items())
        # Plot only the measured geometry; no performance-selected orientation.
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from scipy.cluster.hierarchy import dendrogram,leaves_list
        fig,axes=plt.subplots(1,2,figsize=(17,7))
        ordering=leaves_list(z); sorted_names=np.array(order)[ordering]
        im=axes[0].imshow(corr.loc[sorted_names,sorted_names],vmin=-1,vmax=1,cmap='RdBu_r')
        axes[0].set_title('Alpha158 daily rank correlation | fit: 2015');axes[0].set_xlabel('Cluster-ordered eligible features')
        fig.colorbar(im,ax=axes[0],fraction=.045)
        dendrogram(z,ax=axes[1],no_labels=True,color_threshold=config['cluster_distance'])
        axes[1].axhline(config['cluster_distance'],color='black',ls='--');axes[1].set_title('Complete linkage: 1 - abs(mean daily rho)')
        fig.tight_layout();fig.savefig(output/'alpha_map.png',dpi=140);plt.close(fig)
        family_counts=catalog.groupby('family').size()
        lines=['# M2.1 Alpha158解剖与技术参照', '',
               f'已提取固定Qlib版本的158项原始表达式。2015用于无监督聚类，2016仅作已观察历史诊断。',
               f'90%覆盖率及100个有效相关日门槛后，{len(order)}项进入聚类，得到{len(reps)}个技术代表。',
               '代表按簇内平均绝对相关选取，不按IC或收益挑选；原公式方向不翻转。代表集不等于KEEP池或独立Alpha数量。', '',
               '|经济描述族|特征数|','|---|---:|']
        lines += [f'|{name}|{count}|' for name,count in family_counts.items()]
        lines += ['', '![Alpha158相关与层次聚类](alpha_map.png)', '', '## BP条件信号：2016同样本比较',
                  f"投影前RankIC：{results['matched']['rank_ic']}；投影后RankIC：{results['residual']['rank_ic']}。",
                  f"共同覆盖率：{results['residual']['coverage']:.2%}；状态：{results['status']}。",
                  f"投影平均解释比例：{results['mean_explained_fraction']}。",
                  f"技术代表经仅在2015拟合的PCA压缩至{pca['components']}维，训练方差保留{pca['variance_retained']:.2%}。",
                  '投影同时控制技术主成分、行业与流通市值代理。不同缺失范围不能混比；残差可能含未保留的技术信息。',
                  '这是条件预测诊断，没有进行新的组合回测或LightGBM重训；不升级BP状态。', '',
                  '## 结论边界与下一步',
                  '单特征IC仅用于描述，没有在158项中按最优结果选方向/窗口，未作显著Alpha发现声明。',
                  '月度行业、流通市值代理及供应商修订未知限制继承自首轮。',
                  '无定义或相关日不足的配对在原矩阵保留缺失，仅在聚类距离中按最大距离处理。',
                  '下一项：历史CSI300季度财务与有限经济因子族，之后进行滚动Alpha158+LightGBM add/drop。',
                  '2021–2023资格样本和2024–2025锁箱均未访问。']
        (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        write(output/'verification.json',{'status':'PASS','features':158,'eligible_features':len(order),'representatives':len(reps),
              'extracted_rows':len(features),'prefix_probe_rows':len(overlap),'baseline_unchanged':True,'protected_period_accessed':False,
              'source_hashes':source})
        state.update(status='PASS',stage='complete');write(output/'status.json',state)
        write(output.parent/'latest.json',{'directory':str(output),'run_id':output.name})
        print(f'PASS {output}\n{json.dumps(results,default=str)}',flush=True)
        return output
    except BaseException as exc:
        state.update(status='FAILED',error=str(exc));write(output/'status.json',state)
        (output/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
