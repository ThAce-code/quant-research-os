"""Finite R1 data/screen stages; reuse M1/M2 kernels under a new frozen protocol."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from filelock import FileLock

from .financial import FINANCIAL,events_for_symbol,transfer
from ..factors.data import load_factor_data,preprocess,forward_labels
from ..factors.engine import strict_write_json as write,verify_baseline
from ..factors.provenance import verify_data_identity
from ..factors.analytics import daily_ic,summarize_ic,correlation_matrix
from ..factors.registry import FactorRegistry
from ..m2.core import neutralize,block_inference,bh_adjust
from ..m2.family_screen import checked_artifact
from ..m2.alpha_map import compress_basis,conditional_residual
from ..m3.candidates import identity

PROTOCOL_SHA='616af7d4e4041db6908ac08cd376fa288c436bf4a454f27d809ffee6457a46f0'
CANDIDATES_SHA='27b9609dcb34257ba9d27ffa6092b550782c59c1b43b8d196e99f4c8024a8da4'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def reserve(root,c,stage,output):
    """One numerical execution per frozen campaign; interrupted tickets stay spent."""
    folder=root/'experiments/r1'/c['name'];folder.mkdir(parents=True,exist_ok=True)
    ticket=folder/(stage+'_reservation.json')
    with ticket.open('x',encoding='utf-8') as f:
        json.dump({'protocol_sha256':PROTOCOL_SHA,'output':str(output),'stage':stage},f)


def protocol(root):
    root=Path(root)
    for name,expected in [('protocol.json',PROTOCOL_SHA),('candidates.json',CANDIDATES_SHA)]:
        if sha(root/'configs/r1'/name)!=expected:raise ValueError('R1 protocol/candidates changed')
    return read(root/'configs/r1/protocol.json'),read(root/'configs/r1/candidates.json')


def snapshot(root,folder):
    paths=[*root.glob('src/quant_research/**/*.py'),*root.glob('configs/r1/*.json')]
    hashes={str(p.relative_to(root)):sha(p) for p in paths}
    for name in hashes:
        dest=folder/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,dest)
    write(folder/'source_hashes.json',hashes)


def finish(root,folder,state):
    if any(sha(root/name)!=h for name,h in read(folder/'source_hashes.json').items()):raise ValueError('source changed during R1 stage')
    verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
    write(folder/'status.json',state)
    write(folder/'artifact_hashes.json',{str(p.relative_to(folder)):sha(p) for p in folder.rglob('*')
        if p.is_file() and 'source' not in p.relative_to(folder).parts and p.name!='artifact_hashes.json'})


def checked_stage(folder):
    if read(folder/'status.json')['status']!='PASS':raise ValueError('incomplete R1 input stage')
    manifest=read(folder/'artifact_hashes.json')
    for name,h in manifest.items():
        if sha(folder/name)!=h:raise ValueError('R1 artifact changed: '+name)
    return manifest


def controls(root,c):
    folder=root/c['controls_run']
    if sha(folder/'artifact_hashes.json')!=c['controls_manifest_sha256']:raise ValueError('controls identity changed')
    manifest=read(folder/'artifact_hashes.json')
    return folder,manifest


def market_data(root):
    baseline=read(root/'configs/experiments/baostock_alpha158.json')
    if baseline['data_end']>='2021-01-01':raise ValueError('protected market data')
    frozen=verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001');verify_data_identity(root,baseline,frozen)
    return baseline,load_factor_data(root,baseline)


def technical_fields(fields):
    t=fields['turnover'];close=fields['close']
    relative20=t/t.rolling(20,min_periods=20).mean().where(lambda x:x>0)
    relative60=t/t.rolling(60,min_periods=60).mean().where(lambda x:x>0)
    return {'R1_QUIET_REVERSAL':-(close/close.shift(5)-1)/(1+relative20),
            'R1_ACTIVE_CONTINUATION':(close/close.shift(20)-1)*relative60/(1+relative60)}


def prepare(root):
    root=Path(root).resolve();c,candidates=protocol(root)
    with FileLock(str(root/'data/factor_engine.lock'),timeout=0):
        output=root/'experiments/r1'/c['name']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output.mkdir(parents=True);snapshot(root,output);write(output/'protocol.json',c);write(output/'candidates.json',candidates)
        write(output/'status.json',{'status':'RUNNING','stage':'inputs'})
        print('R1_INPUTS '+str(output),flush=True)
        try:
            audit=root/c['financial_audit']
            for name,h in c['financial_inputs'].items():
                if sha(audit/name)!=h:raise ValueError('financial audit output changed')
            profit=pd.read_parquet(audit/'profit.parquet');cash=pd.read_parquet(audit/'cash.parquet')
            _,market=market_data(root);cache,manifest=controls(root,c)
            exposures={n:pd.read_parquet(checked_artifact(cache,n+'.parquet',manifest)) for n in ['industry','log_size','universe']}
            dates=market.membership.loc[c['data_period'][0]:c['data_period'][1]].index
            mask=exposures['universe'].reindex(index=dates,columns=market.membership.columns).fillna(False)&market.tradable.loc[dates]
            mask &= exposures['log_size'].reindex_like(mask).notna()
            raw={name:pd.DataFrame(np.nan,index=dates,columns=mask.columns) for name in FINANCIAL}
            provenance=[];event_frames=[]
            for i,symbol in enumerate(mask.columns):
                code=symbol[:2].lower()+'.'+symbol[2:]
                events=events_for_symbol(profit[profit.code.eq(code)],cash[cash.code.eq(code)],code,c['data_period'][1])
                for name,e in events.items():
                    values,joined=transfer(e,dates);raw[name][symbol]=values
                    event_frames.append(e.assign(candidate=name,symbol=symbol))
                    provenance.append({'symbol':symbol,'candidate':name,'events':len(e),'finite_panel_cells':int(values.notna().sum()),
                        'max_age_of_finite':float(joined.loc[values.notna(),'age_days'].max()) if values.notna().any() else None})
                if i%50==0:print(f'R1_FINANCIAL {i+1}/{len(mask.columns)}',flush=True)
            pd.concat(event_frames,ignore_index=True).to_parquet(output/'financial_events.parquet',index=False)
            pd.DataFrame(provenance).to_csv(output/'financial_transfer_audit.csv',index=False)
            raw.update({n:p.reindex_like(mask) for n,p in technical_fields(market.fields).items()})
            mask.to_parquet(output/'universe.parquet');coverage=[]
            for item in candidates:
                name=item['name'];folder=output/name;folder.mkdir()
                panel=raw[name].replace([np.inf,-np.inf],np.nan);panel.to_parquet(folder/'raw.parquet')
                score,checks=neutralize(preprocess(panel,mask),exposures['log_size'].reindex_like(mask),exposures['industry'].reindex_like(mask))
                if len(checks) and checks.orthogonality_error.max()>1e-8:raise ValueError('R1 neutralization failed')
                score.to_parquet(folder/'scores.parquet');checks.to_csv(folder/'neutralization.csv',index=False)
                for year in sorted(dates.year.unique()):
                    denominator=int(mask.loc[str(year)].to_numpy().sum())
                    coverage.append({'candidate':name,'year':int(year),'eligible':denominator,
                        'available':int(score.loc[str(year)].notna().to_numpy().sum()),
                        'coverage':float(score.loc[str(year)].notna().to_numpy().sum()/denominator) if denominator else 0.})
                print('R1_SCORES '+name,flush=True)
            pd.DataFrame(coverage).to_csv(output/'coverage.csv',index=False)
            finish(root,output,{'status':'PASS','stage':'inputs','candidate_count':len(candidates),'returns_evaluated':False,
                'protocol_sha256':PROTOCOL_SHA,'financial_revision':'unknown','same_fiscal_dependencies':True,'protected':'SEALED'})
            return output
        except BaseException as exc:
            write(output/'status.json',{'status':'FAIL','stage':'inputs','error':str(exc)});raise


def select_representatives(results,c,candidates):
    selected=[]
    for family in c['family_order']:
        for item in candidates:
            if item['family']!=family:continue
            row=results[item['name']]
            if all(row['coverage'][str(y)]>=c['screen']['min_coverage'] and
                   row['years'][str(y)]['rank_ic'] is not None and row['years'][str(y)]['rank_ic']>0 for y in [2015,2016]):
                selected.append(item['name']);break
    return selected


def screen(root,inputs):
    root=Path(root).resolve();inputs=Path(inputs).resolve();c,candidates=protocol(root)
    with FileLock(str(root/'data/factor_engine.lock'),timeout=0):
        checked_stage(inputs);output=inputs/'screen';reserve(root,c,'screen',output);output.mkdir();snapshot(root,output)
        write(output/'status.json',{'status':'RUNNING','stage':'screen'})
        try:
            _,market=market_data(root);labels=forward_labels(market,c['horizon'],c['screen_period'])
            coverage=pd.read_csv(inputs/'coverage.csv');results={};panels={}
            for item in candidates:
                name=item['name'];score=pd.read_parquet(inputs/name/'scores.parquet').loc[c['screen_period'][0]:c['screen_period'][1]]
                panels[name]=score;ic=daily_ic(score,labels,c['screen']['min_pairs']);ic.to_csv(output/(name+'_ic.csv'))
                results[name]={'primary':summarize_ic(ic),'years':{str(y):summarize_ic(v) for y,v in ic.groupby(ic.index.year)},
                    'coverage':{str(y):float(coverage.loc[coverage.candidate.eq(name)&coverage.year.eq(y),'coverage'].iloc[0]) for y in [2015,2016]},
                    'inference':block_inference(ic.rank_ic,c['block_length'],c['bootstrap_samples'],c['seed'])}
                print('R1_SCREEN '+name+' '+str(results[name]['primary']['rank_ic']),flush=True)
            p=[results[n]['inference']['p'] if results[n]['inference']['p'] is not None else 1. for n in c['candidate_order']]
            q=bh_adjust(p+[1.]*(c['screen']['bh_family_size']-len(p)))
            selected=select_representatives(results,c,candidates)
            for name,value in zip(c['candidate_order'],q):
                row=results[name];row['q']=float(value)
                positive=all(row['years'][str(y)]['rank_ic'] is not None and row['years'][str(y)]['rank_ic']>0 for y in [2015,2016])
                passed=(min(row['coverage'].values())>=c['screen']['min_coverage'] and positive and
                        row['primary']['rank_ic'] is not None and row['primary']['rank_ic']>=c['screen']['min_rank_ic'] and value<=c['screen']['max_q'])
                row.update(status='FORWARD' if passed else 'REJECT',model_representative=name in selected,
                           interpretation='Historical exploratory screen; weak-positive combination route is separate from standalone significance.')
            # Fixed-map conditional diagnostics, without choosing another projection.
            fc=read(root/'configs/factors/m2_family_screen.json');amap=root/fc['alpha_map_run'];ah=fc['alpha_map_input_sha256']
            feat=pd.read_parquet(checked_artifact(amap,'features.parquet',ah));basis=read(checked_artifact(amap,'basis.json',ah));pc=read(checked_artifact(amap,'pca.json',ah))
            compressed,loadings,stats=compress_basis(feat[basis['representatives']],pc['fit_period'],pc['variance_target'],20)
            expected=pd.read_csv(checked_artifact(amap,'pca_loadings.csv',ah),index_col=0)
            np.testing.assert_allclose(loadings,expected,rtol=1e-10,atol=1e-12)
            cache,manifest=controls(root,c);size=pd.read_parquet(checked_artifact(cache,'log_size.parquet',manifest));industry=pd.read_parquet(checked_artifact(cache,'industry.parquet',manifest))
            diag={};conditional_labels=forward_labels(market,c['horizon'],['2016-01-01','2016-12-31'])
            for name,score in panels.items():
                matched,residual,checks=conditional_residual(score.loc['2016'],compressed,size,industry)
                if not matched.notna().equals(residual.notna()):raise ValueError('conditional universe mismatch')
                matched.to_parquet(output/(name+'_matched.parquet'));residual.to_parquet(output/(name+'_residual.parquet'))
                diag[name]={}
                for variant,panel in [('matched',matched),('residual',residual)]:
                    ic=daily_ic(panel,conditional_labels,c['screen']['min_pairs']);ic.to_csv(output/(name+'_'+variant+'_ic.csv'))
                    diag[name][variant]=summarize_ic(ic)
                diag[name]['variance_retained']=stats['variance_retained'];diag[name]['decision']='DIAGNOSTIC_ONLY'
            correlation_matrix(panels,c['screen']['min_pairs']).to_csv(output/'daily_rank_correlation.csv')
            write(output/'results.json',results);write(output/'conditional.json',diag)
            write(output/'selection.json',{'selected':selected,'rule':c['representative_selection'],'protocol_sha256':PROTOCOL_SHA,
                'model_variants_max':2**len(selected),'scope':'EXPLORATORY; not standalone promotion or protected admission'})
            if any(sha(root/n)!=h for n,h in read(output/'source_hashes.json').items()):raise ValueError('source changed before R1 screen registry')
            checked_stage(inputs)
            registry=FactorRegistry(root/'data/factor_registry.sqlite')
            for item in candidates:
                fid='F_'+identity({'candidate':item,'r1_protocol':PROTOCOL_SHA})[:16]
                definition={**item,'r1_protocol_sha256':PROTOCOL_SHA};registry.register(fid,definition)
                registry.record(inputs.name+'_SCREEN',fid,{**results[item['name']],'r1_protocol_sha256':PROTOCOL_SHA,
                    'input_run':inputs.name,'independent_alpha':False,'qualification':'SEALED','lockbox':'SEALED'})
            finish(root,output,{'status':'PASS','stage':'screen','candidates':len(candidates),'selected':selected,'protected':'SEALED'})
            return output
        except BaseException as exc:
            write(output/'status.json',{'status':'FAIL','stage':'screen','error':str(exc)});raise
