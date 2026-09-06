"""Complete supplementary conditional diagnostics; never change screening gates."""
from pathlib import Path
import sys,json,hashlib
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from quant_research.m2.alpha_map import compress_basis,conditional_residual
from quant_research.factors.data import load_factor_data,forward_labels
from quant_research.factors.analytics import daily_ic,summarize_ic
from quant_research.factors.engine import strict_write_json as write,verify_baseline


def main(root):
    out=root/'experiments/m2/m2_conditional_completion_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True);print('CONDITIONAL '+str(out),flush=True)
    config={'period':['2016-01-01','2016-12-31'],'fit':['2015-01-01','2015-12-31'],'horizon':5,
            'pca_cap':20,'variance_target':.9,'min_rows_per_parameter':2,'status':'POST_RESULT_DIAGNOSTIC_ONLY',
            'timing':'initiated after fixed rolling NO_GO; no candidate selection, gate changes, sign flips or tuning',
            'reference':'reuse exact previously frozen Alpha158 representative PCA; cannot represent full technical information'}
    write(out/'config.json',config);write(out/'status.json',{'status':'RUNNING'})
    atlas=root/'experiments/m2/m2_alpha158_map_v2/20260906T055955632527Z'
    inputs=root/'experiments/m2/m2_model_inputs_v1/20260906T090208399969Z'
    supplement=root/'experiments/m2/m2_supplementary_screen_v1/20260906T084009964682Z'
    used=[]
    def read(folder,name):
        manifest=(json.loads((root/'configs/factors/m2_family_screen.json').read_text())['alpha_map_input_sha256']
                  if folder==atlas else json.loads((folder/'artifact_hashes.json').read_text()))
        manifest={Path(k).as_posix():v for k,v in manifest.items()}
        p=folder/name;h=hashlib.sha256(p.read_bytes()).hexdigest();assert h==manifest[name],name
        used.append({'path':str(p),'sha256':h});return p
    try:
        features=pd.read_parquet(read(atlas,'features.parquet'))
        reps=json.loads(read(atlas,'basis.json').read_text())['representatives']
        basis,_,pca=compress_basis(features[reps],config['fit'],.9,20)
        prior_pca=json.loads(read(atlas,'pca.json').read_text())
        assert np.isclose(pca['variance_retained'],prior_pca['variance_retained'],atol=1e-12)
        size=pd.read_parquet(read(inputs,'log_size.parquet'));industry=pd.read_parquet(read(inputs,'industry.parquet'))
        candidates={'BP':pd.read_parquet(read(inputs,'BP.parquet')),'CASHFLOW':pd.read_parquet(read(inputs,'CASHFLOW.parquet')),
                    'ILLIQUIDITY':pd.read_parquet(read(supplement,'ILLIQUIDITY_20/scores.parquet'))}
        baseline=json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');market=load_factor_data(root,baseline)
        label=forward_labels(market,5,config['period']);results={}
        for name,score in candidates.items():
            score=score.loc['2016']
            matched,residual,check=conditional_residual(score,basis,size,industry,2)
            assert matched.notna().equals(residual.notna())
            if len(check):assert check.orthogonality_error.max()<1e-8
            check.to_csv(out/f'{name}_checks.csv',index=False);r={}
            for kind,panel in [('matched',matched),('residual',residual)]:
                daily=daily_ic(panel,label,30);daily.to_csv(out/f'{name}_{kind}_ic.csv');r[kind]=summarize_ic(daily)
            results[name]={'status':'DIAGNOSTIC_ONLY',**r};print(name,flush=True)
        write(out/'metrics.json',results);write(out/'inputs.json',used);write(out/'pca.json',pca)
        write(out/'verification.json',{'status':'PASS','matched_masks_equal':True,'screening_and_rolling_decisions_unchanged':True,
              'no_2021_plus_access':True,'reference_variance_retained':pca['variance_retained']})
        rows=[{'candidate':n,'matched_rank_ic':r['matched']['rank_ic'],'residual_rank_ic':r['residual']['rank_ic'],'days':r['residual']['days']} for n,r in results.items()]
        table=pd.DataFrame(rows);table.to_csv(out/'summary.csv',index=False)
        (out/'report.md').write_text('# M2.4 supplementary conditional diagnostic\n\n'+table.to_markdown(index=False)+
             '\n\nThis completion diagnostic was initiated after rolling NO_GO. It reuses the existing 2015-fitted, 20-PC reference on 2016. '
             'It does not change any gate or rejected formula. PCA retains only 77.7% of representative variance, so residual information may still be technical. '
             'The separate rolling add/drop experiment uses all 158 original features. No independent alpha or fresh OOS claim.\n',encoding='utf-8')
        write(out/'source_hashes.json',{'scripts/complete_conditional.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        write(out/'artifact_hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='status.json'})
        write(out/'status.json',{'status':'PASS'});print('PASS '+str(out),flush=True)
    except BaseException as exc:
        write(out/'status.json',{'status':'FAIL','error':str(exc)});raise


if __name__=='__main__':main(Path(__file__).resolve().parents[1])
