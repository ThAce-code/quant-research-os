"""R1-only twenty-day rolling experiment, with fixed family subset comparisons."""
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from filelock import FileLock
from .workflow import (protocol,read,write,sha,snapshot,finish,checked_stage,controls,
                       market_data,reserve,select_representatives,PROTOCOL_SHA)
from ..factors.data import forward_labels
from ..factors.analytics import daily_ic,summarize_ic
from ..factors.registry import FactorRegistry
from ..factors.engine import verify_baseline
from ..integrity import file_hashes
from ..m2.family_screen import checked_artifact
from ..m2.core import block_inference,bh_adjust
from ..m2.rolling import gate,paired_backtest
from ..m3.increment import matched_features
from ..m3.candidates import identity


def variants(selected):
    return {'BASE':[],**{'ADD_'+'_'.join(str(selected.index(n)+1) for n in subset):list(subset)
        for k in range(1,len(selected)+1) for subset in combinations(selected,k)}}


def folds(calendar,c):
    reach=c['horizon']+c['execution_delay']
    if reach!=c['purge_trading_dates']:raise ValueError('purge differs from label reach')
    for year in c['fold_years']:
        train=calendar[(calendar>=c['train_start'])&(calendar<pd.Timestamp(year-1,1,1))]
        valid=calendar[(calendar>=pd.Timestamp(year-1,1,1))&(calendar<pd.Timestamp(year,1,1))]
        test=calendar[(calendar>=pd.Timestamp(year,1,1))&(calendar<=c['evaluation_period'][1])&(calendar.year==year)]
        if min(len(train),len(valid))<=reach or not len(test):raise ValueError('incomplete R1 fold')
        yield {'year':year,'train':[train[0],train[-reach-1]],'valid':[valid[0],valid[-reach-1]],
               'train_label_exit':train[-1],'valid_label_exit':valid[-1],'test':[test[0],test[-1]]}


def schedule(calendar,c):
    dates=calendar[(calendar>=c['evaluation_period'][0])&(calendar<=c['evaluation_period'][1])]
    trades=dates[::c['rebalance_every']]
    return dates,trades,calendar[calendar.get_indexer(trades)-1]


def masks(features,target,calendar,c):
    dates=features.index.get_level_values('datetime')
    for f in folds(calendar,c):
        train=(dates>=f['train'][0])&(dates<=f['train'][1])&target.notna()
        valid=(dates>=f['valid'][0])&(dates<=f['valid'][1])&target.notna()
        start=calendar[calendar<f['test'][0]][-1] if f['year']==c['fold_years'][0] else f['test'][0]
        infer=(dates>=start)&(dates<=f['test'][1])
        yield f,train,valid,infer


def evaluate(features,labels,calendar,c,baseline,provider,output):
    import lightgbm as lgb
    target=(labels.groupby(level='datetime').rank(pct=True)-.5)*3.46
    plans=list(masks(features,target,calendar,c))
    counts=[{'year':f['year'],'train_rows':int(t.sum()),'valid_rows':int(v.sum()),'prediction_rows':int(i.sum())}
            for f,t,v,i in plans]
    write(output/'sample_gate.json',counts)
    if any(r['train_rows']<c['min_train_rows'] or r['valid_rows']<c['min_valid_rows'] for r in counts):
        return {'decision':'DATA_GATE_FAIL','fits':0,'portfolios':0}
    params={k:v for k,v in baseline['model'].items() if k!='loss'}
    params.update(objective='regression',metric='l2',verbosity=-1,seed=c['seed'])
    predictions={n:[] for n in c['variants']};audit=[];(output/'models').mkdir()
    for f,train,valid,infer in plans:
        for name,extra in c['variants'].items():
            columns=list(features.columns[:158])+extra
            ds=lgb.Dataset(features.loc[train,columns],label=target.loc[train])
            vs=lgb.Dataset(features.loc[valid,columns],label=target.loc[valid],reference=ds)
            model=lgb.train(params,ds,num_boost_round=c['num_boost_round'],valid_sets=[vs],
                callbacks=[lgb.early_stopping(c['early_stopping_rounds'],verbose=False),lgb.log_evaluation(0)])
            predictions[name].append(pd.Series(model.predict(features.loc[infer,columns]),index=features.index[infer]))
            model.save_model(str(output/'models'/f'{f["year"]}_{name}.txt'))
            audit.append({'year':f['year'],'variant':name,'train_start':str(f['train'][0]),'train_end':str(f['train'][1]),
                'valid_start':str(f['valid'][0]),'valid_end':str(f['valid'][1]),'train_label_exit':str(f['train_label_exit']),
                'valid_label_exit':str(f['valid_label_exit']),'train_rows':int(train.sum()),'valid_rows':int(valid.sum()),
                'prediction_rows':int(infer.sum()),'features':len(columns),'best_iteration':model.best_iteration,'seed':c['seed']})
            pd.DataFrame(audit).to_csv(output/'folds.csv',index=False)
            print(f'R1_FIT {len(audit)}/{len(plans)*len(c["variants"])} {f["year"]} {name}',flush=True)
    predictions=pd.DataFrame({n:pd.concat(parts).sort_index() for n,parts in predictions.items()})
    if predictions.index.has_duplicates or not np.isfinite(predictions).all().all():raise ValueError('invalid R1 predictions')
    predictions.to_parquet(output/'predictions.parquet')
    evaluation=predictions.index.get_level_values('datetime')>=c['evaluation_period'][0]
    y=labels.reindex(predictions.index[evaluation]).unstack('instrument')
    daily={n:daily_ic(predictions.loc[evaluation,n].unstack('instrument'),y,c['min_prediction_daily_pairs']) for n in predictions}
    for n,frame in daily.items():frame.to_csv(output/f'{n}_ic.csv')
    write(output/'signal_metrics.json',{n:summarize_ic(frame) for n,frame in daily.items()})
    import qlib
    qlib.init(provider_uri=str(provider),region='cn',kernels=1,expression_cache=None,dataset_cache=None)
    dates,trades,signals=schedule(calendar,c)
    pd.DataFrame({'signal_date':signals,'trade_date':trades}).to_csv(output/'schedule.csv',index=False)
    reports={};metrics={}
    for name in predictions:
        signal=predictions.loc[predictions.index.get_level_values('datetime').isin(signals),name]
        report,metric=paired_backtest(signal,c,baseline,dates)
        if (report.loc[~report.index.isin(trades),'cost'].abs()>1e-12).any():raise ValueError('off-schedule trading')
        report.to_csv(output/f'{name}_daily.csv');reports[name]=report;metrics[name]=metric
        print('R1_PORTFOLIO '+name,flush=True)
    write(output/'portfolio.json',metrics)
    names=list(c['variants'])[1:]
    infer=lambda s:block_inference(s,c['block_length'],c['bootstrap_samples'],c['seed'])
    rank={n:infer(daily[n].rank_ic-daily['BASE'].rank_ic) for n in names}
    q=bh_adjust([rank[n]['p'] if rank[n]['p'] is not None else 1. for n in names]+[1.]*(c['model_bh_family_size']-len(names)))
    net={n:r['return']-r.cost for n,r in reports.items()};comparisons={}
    for name,value in zip(names,q):
        delta=net[name]-net['BASE'];ni=infer(delta)
        annual={str(y):float(v.mean()*238) for y,v in delta.groupby(delta.index.year)}
        comparisons[name]={'rank_ic_increment':rank[name],'q':float(value),'net_increment':ni,
            'annual_net_increment':float(delta.mean()*238),'by_year':annual,**gate(rank[name],value,ni,annual,c)}
        delta.to_csv(output/f'{name}_minus_BASE.csv')
    write(output/'comparisons.json',comparisons)
    full=names[-1];diagnostics={}
    for candidate in c['variants'][full]:
        remainder=[n for n in c['variants'][full] if n!=candidate]
        without=next(n for n,s in c['variants'].items() if s==remainder)
        diagnostics[candidate]={'status':'DIAGNOSTIC_ONLY','with':full,'without':without,
            'net_increment':infer(net[full]-net[without]),'rank_ic_increment':infer(daily[full].rank_ic-daily[without].rank_ic)}
    write(output/'drop_diagnostics.json',diagnostics)
    return {'decision':'GO' if any(r['decision']=='GO' for r in comparisons.values()) else 'NO_GO',
        'passing':[n for n,r in comparisons.items() if r['decision']=='GO'],'fits':len(audit),'portfolios':len(reports)}


def run(root,inputs):
    root=Path(root).resolve();inputs=Path(inputs).resolve();c,candidates=protocol(root)
    with FileLock(str(root/'data/factor_engine.lock'),timeout=0):
        checked_stage(inputs);checked_stage(inputs/'screen')
        selected=select_representatives(read(inputs/'screen/results.json'),c,candidates)
        if selected!=read(inputs/'screen/selection.json')['selected']:raise ValueError('selection changed')
        c={**c,'variants':variants(selected)}
        output=inputs/'model';reserve(root,c,'model',output);output.mkdir();snapshot(root,output)
        write(output/'config.json',c);write(output/'status.json',{'status':'RUNNING','stage':'model'})
        try:
            if not selected:result={'decision':'NO_ENTRY','fits':0,'portfolios':0}
            else:
                baseline,market=market_data(root);cache,manifest=controls(root,c)
                provider=root/'data/qlib'/baseline['name'];frozen=verify_baseline(root,c['baseline'])
                if file_hashes(provider,'**/*')!=frozen['original_provenance']['qlib_files_sha256']:raise ValueError('provider identity changed')
                raw=pd.read_parquet(checked_artifact(cache,'alpha158.parquet',manifest))
                panels={n:pd.read_parquet(inputs/n/'scores.parquet') for n in selected}
                labels=forward_labels(market,c['horizon'],c['data_period']).rename_axis(index='datetime',columns='instrument').stack(future_stack=True)
                features,labels=matched_features(raw,panels,labels)
                features.to_parquet(output/'features.parquet');labels.to_frame('label').to_parquet(output/'labels.parquet')
                result=evaluate(features,labels,market.membership.index,c,baseline,provider,output)
            checked_stage(inputs);checked_stage(inputs/'screen')
            if any(sha(root/n)!=h for n,h in read(output/'source_hashes.json').items()):raise ValueError('source changed before R1 registration')
            registry=FactorRegistry(root/'data/factor_registry.sqlite')
            if (output/'comparisons.json').exists():
                for name,row in read(output/'comparisons.json').items():
                    definition={'name':'R1_'+name,'family':'mechanism_combination','expression':'Alpha158 + '+', '.join(c['variants'][name]),
                        'hypothesis':'Fixed subset model increment on a common universe','direction':1,'source':'R1 frozen subset experiment',
                        'paper':None,'generator':'human','version':1,'r1_protocol_sha256':PROTOCOL_SHA}
                    fid='F_'+identity(definition)[:16];registry.register(fid,definition)
                    registry.record(inputs.name+'_MODEL',fid,{'status':'FORWARD' if row['decision']=='GO' else 'REJECT',
                        'model_increment':row,'screen_run':inputs.name+'_SCREEN','independent_alpha':False,'qualification':'SEALED','lockbox':'SEALED'})
            finish(root,output,{'status':'PASS','stage':'model',**result,'qualification':'SEALED','lockbox':'SEALED','independent_alpha':False})
            return output
        except BaseException as exc:
            write(output/'status.json',{'status':'FAIL','stage':'model','error':str(exc)});raise
