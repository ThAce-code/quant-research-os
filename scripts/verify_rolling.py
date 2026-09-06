"""Replay fixed sampled model predictions and independently recompute decisions."""
from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import spearmanr
from quant_research.m2.core import block_inference,bh_adjust


def main(root,run,inputs):
    assert json.loads((run/'status.json').read_text())['status']=='PASS'
    manifest=json.loads((run/'artifact_hashes.json').read_text())
    for n,h in manifest.items():assert hashlib.sha256((run/n).read_bytes()).hexdigest()==h,n
    c=json.loads((run/'config.json').read_text());pred=pd.read_parquet(run/'predictions.parquet')
    labels=pd.read_parquet(run/'labels.parquet').label
    input_manifest=json.loads((inputs/'artifact_hashes.json').read_text())
    for n,h in input_manifest.items():assert hashlib.sha256((inputs/n).read_bytes()).hexdigest()==h,n
    x=pd.read_parquet(inputs/'alpha158.parquet')
    for name in ['BP','CASHFLOW']:
        x[name]=pd.read_parquet(inputs/f'{name}.parquet').rename_axis(index='datetime',columns='instrument').stack(future_stack=True).reindex(x.index).astype('float32')
    features=list(x.columns[:158]);calendar=pd.DatetimeIndex(pd.read_parquet(root/'data/canonical/baostock_alpha158_csi300_2008_2020/calendar.parquet').datetime)
    common=pd.read_parquet(inputs/'common.parquet').rename_axis(index='datetime',columns='instrument').stack(future_stack=True)
    first=calendar[calendar<pd.Timestamp(c['evaluation_period'][0])][-1]
    eligible_dates=common.index.get_level_values('datetime')
    want=common[common & (eligible_dates>=first) & (eligible_dates<=c['evaluation_period'][1])].index
    pd.testing.assert_index_equal(pred.index,want,check_names=True)
    pd.testing.assert_series_equal(labels,pd.read_parquet(inputs/'labels.parquet').label.reindex(pred.index))
    rows=pd.read_csv(run/'folds.csv');replayed=0;ic_checked=0
    assert len(rows)==24 and set(rows.variant)==set(c['variants'])
    for row in rows.itertuples():
        assert calendar[calendar.get_loc(pd.Timestamp(row.train_end))+2]<pd.Timestamp(row.valid_start)
        assert calendar[calendar.get_loc(pd.Timestamp(row.valid_end))+2]<pd.Timestamp(row.test_start)
        own=pred.loc[str(row.year),row.variant]
        sample=own.iloc[np.linspace(0,len(own)-1,min(101,len(own)),dtype=int)]
        model=lgb.Booster(model_file=str(run/'models'/f'{row.year}_{row.variant}.txt'))
        columns=features+c['variants'][row.variant]
        assert model.num_feature()==len(columns)
        np.testing.assert_allclose(model.predict(x.loc[sample.index,columns]),sample,rtol=1e-12,atol=1e-12)
        replayed+=len(sample)
        stored=pd.read_csv(run/f'{row.variant}_ic.csv',index_col=0,parse_dates=True)
        days=own.index.get_level_values('datetime').unique()
        for day in days[::30]:
            pair=pd.DataFrame({'p':own.xs(day,level='datetime'),'y':labels.xs(day,level='datetime')}).dropna()
            if len(pair)<30:continue
            got=spearmanr(pair.p,pair.y).statistic
            assert np.isclose(got,stored.loc[day,'rank_ic'],atol=1e-12,equal_nan=True)
            ic_checked+=1
    comparisons=json.loads((run/'comparisons.json').read_text());base=pd.read_csv(run/'BASE_daily.csv',index_col=0,parse_dates=True)
    rank_base=pd.read_csv(run/'BASE_ic.csv',index_col=0,parse_dates=True).rank_ic
    rank_p=[]
    for name in c['primary_comparisons']:
        daily=pd.read_csv(run/f'{name}_daily.csv',index_col=0,parse_dates=True)
        pd.testing.assert_index_equal(base.index,daily.index)
        delta=daily['return']-daily.cost-(base['return']-base.cost)
        net=block_inference(delta,20,2000,42)
        annual={str(y):g.mean()*238 for y,g in delta.groupby(delta.index.year)}
        r=pd.read_csv(run/f'{name}_ic.csv',index_col=0,parse_dates=True).rank_ic
        rank=block_inference(r-rank_base,20,2000,42);rank_p.append(rank['p'])
        d=comparisons[name]
        for field in ['mean','low','high']:assert np.isclose(net[field],d['net_increment'][field],atol=1e-12)
        passed=(rank['mean']>=.002 and d['q']<=.1 and net['mean']*238>=.02 and net['low']>0
                and sum(annual.get(str(y),0)>0 for y in range(2015,2020))>=4)
        assert d['decision']==('GO' if passed else 'NO_GO')
    np.testing.assert_allclose(bh_adjust(rank_p),[comparisons[n]['q'] for n in c['primary_comparisons']],atol=1e-12)
    result={'status':'PASS','model_predictions_replayed':replayed,'independent_rank_ic_days':ic_checked,'folds_checked':len(rows),
            'primary_joint_decisions_checked':3,'artifact_hashes_checked':len(manifest),'no_2021_plus_access':True,
            'all_prediction_rows_match_causal_universe':True,'labels_match_input':True,
            'limits':'model replay and independent IC samples; inference reuses previously tested block routine'}
    (run/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main(Path(__file__).resolve().parents[1],Path(sys.argv[1]),Path(sys.argv[2]))
