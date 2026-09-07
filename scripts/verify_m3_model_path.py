"""Real model/backtest integration on observed history; isolated synthetic candidate.

Engineering only: does not fabricate admission or modify the production registry.
The candidate is random noise, not a paper/human alpha research hypothesis.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from quant_research.m3.increment import matched_features, evaluate_models
from quant_research.m3.pipeline import sha
from quant_research.factors.engine import strict_write_json as write, verify_baseline
from quant_research.factors.provenance import verify_data_identity
from quant_research.factors.expressions import FactorDefinition
from quant_research.factors.registry import FactorRegistry
from quant_research.integrity import file_hashes
from quant_research.m2.family_screen import checked_artifact
from quant_research.m2.core import neutralize


def main():
    with FileLock(str(ROOT/'data/factor_engine.lock'), timeout=0):
        return execute()


def execute():
    out = ROOT/'experiments/m3_engineering'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    write(out/'status.json', {'status':'RUNNING','scope':'ENGINEERING_ONLY'})
    production = ROOT/'data/factor_registry.sqlite'
    before = FactorRegistry(production).evaluations()
    try:
        baseline = json.loads((ROOT/'configs/experiments/baostock_alpha158.json').read_text())
        frozen = verify_baseline(ROOT, 'BL-CN-CSI300-A158-LGBM-001')
        verify_data_identity(ROOT, baseline, frozen)
        provider = ROOT/'data/qlib'/baseline['name']
        if file_hashes(provider, '**/*') != frozen['original_provenance']['qlib_files_sha256']:
            raise ValueError('provider identity changed')
        adapter = json.loads((ROOT/'configs/m3/increment.json').read_text())
        cache = ROOT/adapter['input_run']
        if sha(cache/'artifact_hashes.json') != adapter['input_manifest_sha256']:
            raise ValueError('input manifest changed')
        manifest = json.loads((cache/'artifact_hashes.json').read_text())
        baseline['model'] = {'num_threads':1, 'num_leaves':8, 'learning_rate':.1,
                             'deterministic':True, 'force_col_wise':True, 'seed':42}
        c = json.loads((ROOT/'configs/factors/m2_rolling.json').read_text())
        name = 'ENGINEERING_NOISE'
        c.update(fold_years=[2015], train_start='2013-01-01',
            evaluation_period=['2015-01-01','2015-03-31'],
            variants={'BASE':[], 'ADD_ENGINEERING_NOISE':[name]},
            primary_comparisons=['ADD_ENGINEERING_NOISE'],
            num_boost_round=5, early_stopping_rounds=2, min_train_rows=100,
            min_valid_rows=100, strategy={'topk':10, 'n_drop':2})
        # Deliberately retain strict original GO gate: an engineering result is not admission.
        write(out/'fixture.json', {'scope':'ENGINEERING_ONLY', 'seed':9281,
            'candidate':'independent Gaussian noise, daily neutralized; full historical symbol coverage', 'config':c,
            'baseline':baseline,'input_run':str(cache.relative_to(ROOT)),
            'input_manifest_sha256':adapter['input_manifest_sha256'],
            'research_registry_writes':False, 'screen_bypassed':'not a research run; shared numerical core only'})
        paths = list((ROOT/'src/quant_research').rglob('*.py'))+[Path(__file__)]
        sources = {str(p.relative_to(ROOT)):sha(p) for p in paths}
        for n in sources:
            target=out/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,target)
        write(out/'source_hashes.json',sources)
        features = pd.read_parquet(checked_artifact(cache,'alpha158.parquet',manifest))
        dates=features.index.get_level_values('datetime')
        symbols=sorted(features.index.get_level_values('instrument').unique())
        keep=(dates>='2013-01-01')&(dates<='2015-03-31')&features.index.get_level_values('instrument').isin(symbols)
        features=features.loc[keep]
        labels=pd.read_parquet(checked_artifact(cache,'labels.parquet',manifest)).label
        size=pd.read_parquet(checked_artifact(cache,'log_size.parquet',manifest)).loc['2013-01-01':'2015-03-31',symbols]
        industry=pd.read_parquet(checked_artifact(cache,'industry.parquet',manifest)).reindex_like(size)
        universe=pd.read_parquet(checked_artifact(cache,'universe.parquet',manifest)).reindex_like(size)
        random=pd.DataFrame(np.random.default_rng(9281).normal(size=size.shape),index=size.index,columns=size.columns)
        score,_=neutralize(random.where(universe),size,industry)
        x,y=matched_features(features,{name:score},labels)
        x.to_parquet(out/'features.parquet');y.to_frame('label').to_parquet(out/'labels.parquet')
        calendar=pd.DatetimeIndex(pd.read_parquet(ROOT/'data/canonical'/baseline['name']/'calendar.parquet').datetime)
        factor=FactorDefinition(name,'engineering_fixture','close','Synthetic transport fixture; not alpha research',
                                source='ENGINEERING_ONLY',generator='seeded_test')
        comparisons=evaluate_models(x,y,calendar,c,baseline,provider,[factor],out)
        # A separate SQLite exercises serialization/read-back; production admission is untouched.
        isolated=FactorRegistry(out/'engineering_registry.sqlite')
        isolated.register(factor.factor_id,asdict(factor))
        isolated.record(out.name,factor.factor_id,{'status':'REJECT','reasons':['ENGINEERING_ONLY_NOT_ADMISSIBLE'],
            'model_increment':comparisons,'independent_alpha':False})
        assert isolated.evaluations()[0]['report']['model_increment']==comparisons
        predictions=pd.read_parquet(out/'predictions.parquet')
        assert predictions.notna().all().all() and predictions.index.is_unique
        reports={n:pd.read_csv(out/f'{n}_daily.csv',index_col=0) for n in ['BASE','ADD_ENGINEERING_NOISE','BLEND_ENGINEERING_NOISE']}
        for report in reports.values():
            assert report.index.equals(reports['BASE'].index)
            assert report.cost.ge(0).all() and report.cost.sum()>0
        delta=reports['ADD_ENGINEERING_NOISE']['return']-reports['ADD_ENGINEERING_NOISE'].cost-(reports['BASE']['return']-reports['BASE'].cost)
        np.testing.assert_allclose(delta.mean(),comparisons['ADD_ENGINEERING_NOISE']['net_increment']['mean'])
        assert FactorRegistry(production).evaluations()==before
        assert all(sha(ROOT/n)==v for n,v in sources.items())
        verify_baseline(ROOT,'BL-CN-CSI300-A158-LGBM-001')
        status={'status':'PASS','scope':'ENGINEERING_ONLY','run_id':out.name,
            'fits':2,'portfolios':3,'prediction_rows':len(predictions),'backtest_days':len(delta),
            'positive_cost_all_portfolios':True,'net_delta_replayed':True,
            'isolated_registry_roundtrip':True,'production_registry_unchanged':True,
            'production_trials':len(before),'qualification_accessed':False,'lockbox_accessed':False,
            'limits':'one short fold and random candidate; no research admission or full six-fold validation'}
        write(out/'status.json',status)
        write(out/'artifact_hashes.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*')
              if p.is_file() and 'source' not in p.relative_to(out).parts and p.suffix!='.sqlite'})
        print(json.dumps(status),flush=True)
        return out
    except BaseException as exc:
        write(out/'status.json',{'status':'FAIL','scope':'ENGINEERING_ONLY','error':str(exc)})
        raise


if __name__=='__main__':
    print(main())
