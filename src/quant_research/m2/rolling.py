"""Fixed-budget full Alpha158 add/drop, paired portfolios and research exit."""
from datetime import datetime,timezone
from copy import deepcopy
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
from ..factors.analytics import daily_ic,summarize_ic
from ..factors.portfolio import portfolio_metrics
from .core import block_inference,bh_adjust


def folds(calendar,c):
    """Purge label reach using the exchange calendar, not calendar-day arithmetic."""
    for year in c['fold_years']:
        train=calendar[(calendar>=c['train_start'])&(calendar<pd.Timestamp(year-1,1,1))]
        valid=calendar[(calendar>=pd.Timestamp(year-1,1,1))&(calendar<pd.Timestamp(year,1,1))]
        test=calendar[(calendar>=pd.Timestamp(year,1,1))&(calendar<=c['evaluation_period'][1])&(calendar.year==year)]
        if len(train)<3 or len(valid)<3 or not len(test):raise ValueError('incomplete fold calendar')
        yield {'year':year,'train':[train[0],train[-3]],'valid':[valid[0],valid[-3]],'test':[test[0],test[-1]]}


def gate(rank_increment,q,net_increment,annual,c):
    g=c['gate'];positive=sum(annual.get(str(y),0)>0 for y in g['full_years'])
    passed=(rank_increment['mean'] is not None and rank_increment['mean']>=g['min_rank_ic_increment']
            and q<=g['max_increment_q'] and net_increment['mean'] is not None
            and net_increment['mean']*238>=g['min_net_annual_increment']
            and net_increment['low']>0 and positive>=g['min_positive_full_years'])
    return {'decision':'GO' if passed else 'NO_GO','positive_full_years':positive}


def paired_backtest(signal,c,baseline,dates):
    from qlib.backtest import backtest
    portfolio,_=backtest(start_time=c['evaluation_period'][0],end_time=c['evaluation_period'][1],
        strategy={'class':'TopkDropoutStrategy','module_path':'qlib.contrib.strategy','kwargs':{'signal':signal,**c['strategy']}},
        executor={'class':'SimulatorExecutor','module_path':'qlib.backtest.executor',
                  'kwargs':{'time_per_step':'day','generate_portfolio_metrics':True}},**deepcopy(baseline['backtest']))
    report,_=portfolio['1day']
    pd.testing.assert_index_equal(pd.DatetimeIndex(report.index),pd.DatetimeIndex(dates),check_names=False)
    return report,portfolio_metrics(report)


def run(root,inputs):
    with FileLock(str(root/'data/factor_engine.lock'),timeout=0):return _run(root,inputs)


def _run(root,inputs):
    config_path=root/'configs/factors/m2_rolling.json';c=json.loads(config_path.read_text(encoding='utf-8'))
    output=root/'experiments/m2'/c['name']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True);print('ROLLING '+str(output),flush=True)
    state={'status':'RUNNING','run_id':output.name};write(output/'status.json',state);write(output/'config.json',c)
    names=['src/quant_research/m2/rolling.py','configs/factors/m2_rolling.json','src/quant_research/factors/analytics.py',
           'src/quant_research/factors/portfolio.py','src/quant_research/m2/core.py']
    sources={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
    for n in names:
        dest=output/'source'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/n,dest)
    write(output/'source_hashes.json',sources)
    try:
        assert json.loads((inputs/'status.json').read_text())['status']=='PASS'
        manifest=json.loads((inputs/'artifact_hashes.json').read_text())
        for n,h in manifest.items():assert hashlib.sha256((inputs/n).read_bytes()).hexdigest()==h,n
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');identity=verify_data_identity(root,baseline,frozen)
        canonical=root/'data/canonical'/baseline['name']
        calendar=pd.DatetimeIndex(pd.read_parquet(canonical/'calendar.parquet').datetime)
        common=pd.read_parquet(inputs/'common.parquet')
        index=common.rename_axis(index='datetime',columns='instrument').stack(future_stack=True)
        features=pd.read_parquet(inputs/'alpha158.parquet')
        features=features.loc[index.reindex(features.index).fillna(False)].copy()
        alpha_names=list(features.columns);assert len(alpha_names)==158
        for name in ['BP','CASHFLOW']:
            features[name]=pd.read_parquet(inputs/f'{name}.parquet').rename_axis(index='datetime',columns='instrument').stack(future_stack=True).reindex(features.index).astype('float32')
        assert features[['BP','CASHFLOW']].notna().all().all()
        raw_labels=pd.read_parquet(inputs/'labels.parquet').label.reindex(features.index)
        learned=(raw_labels.groupby(level='datetime').rank(pct=True)-.5)*3.46
        dates=features.index.get_level_values('datetime')
        import lightgbm as lgb
        params={k:v for k,v in baseline['model'].items() if k!='loss'}
        params.update(objective='regression',metric='l2',verbosity=-1,seed=c['seed'])
        predictions={name:[] for name in c['variants']};audits=[]
        model_dir=output/'models';model_dir.mkdir()
        for fold in folds(calendar,c):
            a,b=fold['train'];va,vb=fold['valid'];ta,tb=fold['test']
            train=(dates>=a)&(dates<=b)&learned.notna().to_numpy()
            valid=(dates>=va)&(dates<=vb)&learned.notna().to_numpy()
            infer_start=calendar[calendar<ta][-1] if fold['year']==c['fold_years'][0] else ta
            infer=(dates>=infer_start)&(dates<=tb)
            if train.sum()<c['min_train_rows'] or valid.sum()<c['min_valid_rows']:raise ValueError('fold data gate failed')
            for name,extra in c['variants'].items():
                columns=alpha_names+extra
                train_set=lgb.Dataset(features.loc[train,columns],label=learned.loc[train])
                valid_set=lgb.Dataset(features.loc[valid,columns],label=learned.loc[valid],reference=train_set)
                model=lgb.train(params,train_set,num_boost_round=c['num_boost_round'],valid_sets=[valid_set],
                    callbacks=[lgb.early_stopping(c['early_stopping_rounds'],verbose=False),lgb.log_evaluation(0)])
                pred=pd.Series(model.predict(features.loc[infer,columns]),index=features.index[infer],name=name)
                assert np.isfinite(pred.to_numpy()).all()
                predictions[name].append(pred);model.save_model(str(model_dir/f'{fold["year"]}_{name}.txt'))
                audits.append({'year':fold['year'],'variant':name,'train_start':str(a.date()),'train_end':str(b.date()),
                    'valid_start':str(va.date()),'valid_end':str(vb.date()),'test_start':str(ta.date()),'test_end':str(tb.date()),
                    'train_rows':int(train.sum()),'valid_rows':int(valid.sum()),'prediction_rows':len(pred),
                    'features':len(columns),'best_iteration':model.best_iteration,'seed':c['seed']})
                pd.DataFrame(audits).to_csv(output/'folds.csv',index=False)
                state.update(stage='training',fits_completed=len(audits),fits_total=24);write(output/'status.json',state)
                print(f'FIT {len(audits)}/24 {fold["year"]} {name} iteration={model.best_iteration}',flush=True)
        predicted=pd.DataFrame({n:pd.concat(parts).sort_index() for n,parts in predictions.items()})
        assert not predicted.index.has_duplicates and predicted.notna().all().all()
        predicted.to_parquet(output/'predictions.parquet')
        pd.DataFrame({'label':raw_labels.reindex(predicted.index)}).to_parquet(output/'labels.parquet')
        evaluation=(predicted.index.get_level_values('datetime')>=c['evaluation_period'][0])
        labels=raw_labels.reindex(predicted.index[evaluation]).unstack('instrument')
        ic={};stats={}
        for name in c['variants']:
            daily=daily_ic(predicted.loc[evaluation,name].unstack('instrument'),labels,c['min_prediction_daily_pairs'])
            daily.to_csv(output/f'{name}_ic.csv');ic[name]=daily
            stats[name]=summarize_ic(daily)
        write(output/'signal_metrics.json',stats)
        ranked=predicted.groupby(level='datetime').rank(pct=True)
        signals={n:predicted[n] for n in c['variants']}
        for name,weights in c['blend_diagnostics'].items():
            candidate=next(k for k in weights if k!='BASE')
            candidate_rank=features.loc[predicted.index,candidate].groupby(level='datetime').rank(pct=True)
            signals[name]=ranked.BASE*weights['BASE']+candidate_rank*weights[candidate]
        import qlib
        qlib.init(provider_uri=str(root/'data/qlib'/baseline['name']),region='cn',kernels=1,expression_cache=None,dataset_cache=None)
        expected=calendar[(calendar>=c['evaluation_period'][0])&(calendar<=c['evaluation_period'][1])]
        reports={};portfolio={}
        for name,signal in signals.items():
            assert signal.index.equals(predicted.index)
            print('BACKTEST '+name,flush=True)
            report,metrics=paired_backtest(signal,c,baseline,expected)
            report.to_csv(output/f'{name}_daily.csv');reports[name]=report;portfolio[name]=metrics
            state.update(stage='backtest',portfolios_completed=len(reports));write(output/'status.json',state)
        write(output/'portfolio.json',portfolio)
        rank_deltas={n:block_inference(ic[n].rank_ic-ic['BASE'].rank_ic,c['block_length'],c['bootstrap_samples'],c['seed']) for n in c['primary_comparisons']}
        qs=bh_adjust([rank_deltas[n]['p'] for n in c['primary_comparisons']]);comparisons={}
        base=reports['BASE'];base_net=base['return']-base.cost
        for name,q in zip(c['primary_comparisons'],qs):
            delta=reports[name]['return']-reports[name].cost-base_net
            net=block_inference(delta,c['block_length'],c['bootstrap_samples'],c['seed'])
            annual={str(y):float(g.mean()*238) for y,g in delta.groupby(delta.index.year)}
            comparisons[name]={'rank_ic_increment':rank_deltas[name],'q':float(q),'net_increment':net,
                'annual_net_increment':float(delta.mean()*238),'by_year':annual,**gate(rank_deltas[name],q,net,annual,c)}
            delta.to_csv(output/f'{name}_minus_BASE.csv')
        diagnostics={}
        for name,(left,right) in c['drop_diagnostics'].items():
            delta=reports[left]['return']-reports[left].cost-(reports[right]['return']-reports[right].cost)
            diagnostics[name]={'interpretation':f'effect retained by {left} versus {right}',
                'net_increment':block_inference(delta,c['block_length'],c['bootstrap_samples'],c['seed'])}
        for name in c['blend_diagnostics']:
            delta=reports[name]['return']-reports[name].cost-base_net
            diagnostics[name]={'net_increment':block_inference(delta,c['block_length'],c['bootstrap_samples'],c['seed']),
                'annual_net_increment':float(delta.mean()*238),'status':'DIAGNOSTIC_ONLY'}
        write(output/'comparisons.json',comparisons);write(output/'diagnostics.json',diagnostics)
        passing=[n for n in c['primary_comparisons'] if comparisons[n]['decision']=='GO']
        passing.sort(key=lambda n:(-comparisons[n]['annual_net_increment'],c['primary_comparisons'].index(n)))
        winner=passing[0] if passing else None
        write(output/'research_decision.json',{'decision':'GO' if winner else 'NO_GO','winner':winner,
            'qualification':'PENDING_EXECUTION' if winner else 'NOT_OPENED_NO_HISTORICAL_GO',
            'lockbox':'SEALED','no_2021_plus_access':True,'single_factor_REJECT_statuses_unchanged':True,
            'independent_alpha':'NOT_CONFIRMED'})
        assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in sources.items())
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        write(output/'verification.json',{'status':'PASS','baseline_identity':identity,'fits':len(audits),'portfolios':len(reports),
              'same_prediction_rows':True,'input_run':inputs.name,'features':158,'no_2021_plus_access':True,'frozen_protocol_sha256':sources['configs/factors/m2_rolling.json']})
        table=pd.DataFrame([{'variant':n,'rank_ic_increment':d['rank_ic_increment']['mean'],'q':d['q'],
            'net_annual_increment':d['annual_net_increment'],'positive_full_years':d['positive_full_years'],'decision':d['decision']} for n,d in comparisons.items()])
        table.to_csv(output/'summary.csv',index=False)
        (output/'report.md').write_text('# M2 full Alpha158 rolling increment\n\n'+table.to_markdown(index=False)+
            '\n\n24 fixed fits; expanding annual train/validation; identical nonfinancial historical universe. Six continuous costed portfolios. '
            '2015–2020 is burned diagnostic history, not fresh OOS. Labels and strategy follow the separately frozen rolling protocol. '
            'Three primary comparisons use BH; drop/blend outputs are diagnostics. No hyperparameter search or formula repair.\n\n'
            'Research decision: '+('GO '+winner if winner else 'NO_GO; qualification and lockbox remain unopened under the frozen entry gates.')+
            '\n\nVendor revisions, historical industry vintages and market-impact capacity remain limitations. No independent alpha claim.\n',encoding='utf-8')
        write(output/'artifact_hashes.json',{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*')
            if p.is_file() and 'source' not in p.relative_to(output).parts and p.name!='status.json'})
        state.update(status='PASS',stage='complete');write(output/'status.json',state);print('PASS '+str(output),flush=True)
        return output
    except BaseException as exc:
        state.update(status='FAIL',error=str(exc));write(output/'status.json',state)
        (output/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
