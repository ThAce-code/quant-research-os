"""Derive legacy-aware controls and exact Alpha158 inputs from sealed history."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import hashlib
import json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from quant_research.m2.history_completion import industry_key,financial_key
from quant_research.m2.core import asof_events,neutralize
from quant_research.factors.data import preprocess,load_factor_data
from quant_research.factors.engine import verify_baseline,strict_write_json as write
from quant_research.factors.provenance import verify_data_identity


def main(root):
    prior=root/'experiments/m2/m2_supplementary_data_v1/20260906T072711741731Z'
    output=root/'experiments/m2/m2_model_inputs_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True);print('MODEL_INPUTS '+str(output),flush=True)
    state={'status':'RUNNING','run_id':output.name};write(output/'status.json',state)
    try:
        manifest=json.loads((prior/'artifact_hashes.json').read_text())
        names=['membership.parquet','CFOToOR.parquet','BP.parquet','log_size.parquet','industry_events.parquet']
        for name in names:assert hashlib.sha256((prior/name).read_bytes()).hexdigest()==manifest[name]
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');identity=verify_data_identity(root,baseline,frozen)
        market=load_factor_data(root,baseline)
        member=pd.read_parquet(prior/'membership.parquet');size=pd.read_parquet(prior/'log_size.parquet')
        e=pd.read_parquet(prior/'industry_events.parquet');e['industry']=e.industry.map(industry_key)
        industry=pd.DataFrame(index=member.index,columns=member.columns,dtype=object)
        for symbol in member:
            code=symbol[:2].lower()+'.'+symbol[2:]
            own=e[e.code.eq(code)]
            industry[symbol]=asof_events(own,member.index,'snapshot_date',['industry'],62).industry
        financial=industry.map(financial_key);universe=member&industry.notna()&~financial
        industry.to_parquet(output/'industry.parquet');universe.to_parquet(output/'universe.parquet')
        size.to_parquet(output/'log_size.parquet')
        active=market.tradable.reindex_like(member);scores={};rows=[]
        for name,field in [('BP','BP'),('CASHFLOW','CFOToOR')]:
            score,checks=neutralize(preprocess(pd.read_parquet(prior/f'{field}.parquet'),universe&active),size,industry)
            score.to_parquet(output/f'{name}.parquet');checks.to_csv(output/f'{name}_neutralization.csv',index=False);scores[name]=score
            previous=root/'experiments/m2/m2_supplementary_screen_v1/20260906T084009964682Z'/('BP_reference' if name=='BP' else 'CASHFLOW_MARGIN_YTD')/'scores.parquet'
            pd.testing.assert_frame_equal(score.loc['2015':],pd.read_parquet(previous).loc['2015':])
            print('SCORE '+name,flush=True)
        common=scores['BP'].notna()&scores['CASHFLOW'].notna()
        common.to_parquet(output/'common.parquet')
        for year in sorted(member.index.year.unique()):
            m=member.loc[str(year)];u=universe.loc[str(year)];n=common.loc[str(year)].sum(axis=1)
            rows.append({'year':int(year),'industry_coverage':float((industry.loc[str(year)].notna()&m).to_numpy().sum()/m.to_numpy().sum()),
                         'common_coverage':float(n.sum()/u.to_numpy().sum()),'median_daily_pairs':float(n.median()),'min_daily_pairs':int(n.min())})
        pd.DataFrame(rows).to_csv(output/'coverage.csv',index=False)
        import qlib
        from qlib.data import D
        from qlib.contrib.data.handler import Alpha158
        qlib.init(provider_uri=str(root/'data/qlib'/baseline['name']),region='cn',kernels=1,expression_cache=None,dataset_cache=None)
        expressions,names=Alpha158.get_feature_config(None);assert len(names)==158
        # Chunk extraction bounds memory. All chunks use only original sealed history.
        parts=[]
        for i in range(0,len(member.columns),50):
            f=D.features(list(member.columns[i:i+50]),expressions,start_time='2008-01-01',end_time='2020-07-31')
            f.columns=names;f=f.reorder_levels(['datetime','instrument']).sort_index()
            eligible=member.iloc[:,i:i+50].rename_axis(index='datetime',columns='instrument').stack(future_stack=True)
            f=f.loc[eligible.reindex(f.index).fillna(False)].replace([np.inf,-np.inf],np.nan).astype('float32')
            parts.append(f);print(f'ALPHA158 {min(i+50,len(member.columns))}/{len(member.columns)}',flush=True)
        features=pd.concat(parts).sort_index();features.to_parquet(output/'alpha158.parquet')
        # Use the same t+1-close -> t+2-close label as frozen M0.
        label=D.features(list(member.columns),['Ref($close,-2)/Ref($close,-1)-1'],start_time='2008-01-01',end_time='2020-07-31')
        label.columns=['label'];label=label.reorder_levels(['datetime','instrument']).sort_index()
        label.reindex(features.index).to_parquet(output/'labels.parquet')
        write(output/'verification.json',{'status':'PASS','baseline_identity':identity,'legacy_mapping':'none; contemporaneous full-string categories',
              '2015_plus_scores_identical':True,'features':158,'rows':len(features),'no_2021_plus_access':True,
              'source_run':prior.name,'industry_source':'https://www.csrc.gov.cn/csrc/c101864/c1024632/content.shtml'})
        write(output/'source_hashes.json',{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['scripts/prepare_model_inputs.py','src/quant_research/m2/history_completion.py']})
        write(output/'artifact_hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name!='status.json'})
        state.update(status='PASS');write(output/'status.json',state);print('PASS '+str(output),flush=True)
    except BaseException as exc:
        state.update(status='FAIL',error=str(exc));write(output/'status.json',state);raise


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
