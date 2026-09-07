"""Replay full-size M3 survivor evidence without fitting or changing admissions."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

import lightgbm as lgb
import numpy as np
import pandas as pd


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(root,run):
    root=Path(root).resolve();run=Path(run).resolve()
    read=lambda name:json.loads((run/name).read_text())
    state=read('status.json');assert state['status']=='PASS'
    assert state['qualification']==state['lockbox']=='SEALED'
    manifest=read('artifact_hashes.json')
    for name,expected in manifest.items():assert digest(run/name)==expected,name
    sources=read('source_hashes.json')
    for name,expected in sources.items():assert digest(run/'source'/name)==expected,name
    c=read('config.json')['numeric_protocol'];admission=read('admission.json')
    variants=c['variants'];n=len(admission['candidates'])
    assert n>0 and c['fold_years']==list(range(2015,2021))
    assert state['fits']==6*(1+n) and state['portfolios']==1+2*n
    folds=pd.read_csv(run/'folds.csv')
    assert len(folds)==state['fits']
    assert set(zip(folds.year,folds.variant))=={(y,v) for y in c['fold_years'] for v in variants}
    for year,rows in folds.groupby('year'):
        assert rows.train_rows.nunique()==rows.valid_rows.nunique()==rows.prediction_rows.nunique()==1
        assert (pd.to_datetime(rows.train_end).dt.year==year-2).all()
        assert (pd.to_datetime(rows.valid_end).dt.year==year-1).all()
        assert (rows.seed==c['seed']).all()
        assert (rows.train_rows>=c['min_train_rows']).all() and (rows.valid_rows>=c['min_valid_rows']).all()
    features=pd.read_parquet(run/'features.parquet')
    predictions=pd.read_parquet(run/'predictions.parquet')
    labels=pd.read_parquet(run/'labels.parquet').label
    assert features.index.equals(labels.index) and not predictions.index.has_duplicates
    assert np.isfinite(predictions).all().all() and predictions.index.isin(features.index).all()
    assert list(predictions.columns)==list(variants)
    assert predictions.index.get_level_values('datetime').max()<pd.Timestamp('2021-01-01')
    replayed=0
    for row in folds.itertuples():
        available=predictions.index[predictions.index.get_level_values('datetime').year==row.year]
        selected=available[np.linspace(0,len(available)-1,min(30,len(available)),dtype=int)]
        columns=list(features.columns[:158])+variants[row.variant]
        assert len(columns)==row.features
        model=lgb.Booster(model_file=str(run/'models'/f'{row.year}_{row.variant}.txt'))
        actual=model.predict(features.loc[selected,columns])
        np.testing.assert_allclose(actual,predictions.loc[selected,row.variant],rtol=1e-10,atol=1e-12)
        replayed+=len(selected)
    daily={}
    pair_counts={}
    for name in variants:
        frame=pd.concat([predictions[name].rename('score'),labels.rename('label')],axis=1).dropna()
        frame=frame.loc[frame.index.get_level_values('datetime')>=pd.Timestamp(c['evaluation_period'][0])]
        ranks=frame.groupby(level='datetime').rank()
        counts=frame.groupby(level='datetime').size()
        ric=ranks.groupby(level='datetime').apply(lambda d:d.score.corr(d.label))
        ric=ric.where(counts>=c['min_prediction_daily_pairs'])
        stored=pd.read_csv(run/f'{name}_ic.csv',index_col=0,parse_dates=True)
        np.testing.assert_allclose(ric.reindex(stored.index),stored.rank_ic,atol=1e-12,rtol=1e-10,equal_nan=True)
        daily[name]=stored.rank_ic;pair_counts[name]=int(ric.notna().sum())
    reports={name:pd.read_csv(run/f'{name}_daily.csv',index_col=0,parse_dates=True)
             for name in [*variants,*c['blend_diagnostics']]}
    base=reports['BASE']['return']-reports['BASE'].cost
    for report in reports.values():
        assert report.index.equals(base.index)
        assert np.isfinite(report[['return','cost']]).all().all()
        assert report.cost.ge(0).all() and report.cost.sum()>0
        assert report.index.max()<pd.Timestamp('2021-01-01')
    comparisons=read('comparisons.json');g=c['gate']
    for name,result in comparisons.items():
        delta=reports[name]['return']-reports[name].cost-base
        np.testing.assert_allclose(delta.mean(),result['net_increment']['mean'],atol=1e-14)
        np.testing.assert_allclose((daily[name]-daily['BASE']).mean(),result['rank_ic_increment']['mean'],atol=1e-14)
        for year,group in delta.groupby(delta.index.year):
            np.testing.assert_allclose(group.mean()*238,result['annual_net_increment'][str(year)],atol=1e-12)
        positive=sum(result['annual_net_increment'].get(str(y),0)>0 for y in g['full_years'])
        passed=(result['rank_ic_increment']['mean']>=g['min_rank_ic_increment']
                and result['q']<=g['max_increment_q'] and delta.mean()*238>=g['min_net_annual_increment']
                and result['net_increment']['low']>0 and positive>=g['min_positive_full_years'])
        assert result['decision']==('GO' if passed else 'NO_GO')
        assert result['positive_full_years']==positive
    path=root/'data/factor_registry.sqlite'
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        records=db.execute('SELECT report_json FROM evaluations WHERE run_id=?',(run.name,)).fetchall()
    assert len(records)==n
    for (encoded,) in records:
        result=json.loads(encoded)
        assert result['screen_run']==admission['screen_run'] and result['independent_alpha'] is False
        assert result['model_increment'] in comparisons.values()
    report={'status':'PASS','run_id':run.name,'screen_run':admission['screen_run'],
            'source_files_checked':len(sources),'artifacts_checked':len(manifest),
            'fits':len(folds),'predictions_replayed':replayed,'prediction_rows':len(predictions),
            'rank_ic_days_replayed':pair_counts,'portfolio_days':len(base),'portfolios':len(reports),
            'numerical_registry_records':len(records),'qualification_executed':False,'lockbox_executed':False,
            'limits':'Historical research only. Stored bootstrap intervals/q reused, not independently resampled. No fill-level order replay or live capacity claim.'}
    # Keep verifier output outside the immutable run's original artifact manifest.
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(Path(__file__).resolve().parents[1],args.run)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
