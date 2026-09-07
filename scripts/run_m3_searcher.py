"""Run pinned upstream neural generators in a separate bounded CPU environment.

The algorithms, networks, rewards and optimizers come from the official MIT
repositories. This driver bounds execution and supplies sealed canonical tensors;
it does not replace GFlowNets or AlphaForge with a different search algorithm.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.m3.external import UPSTREAMS
from quant_research.factors.data import load_factor_data
from quant_research.factors.engine import verify_baseline


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def input_tensors(config,output):
    import numpy as np
    import pandas as pd
    import torch
    from alphagen_qlib.stock_data import StockData,FeatureType
    baseline=json.loads((ROOT/'configs/experiments/baostock_alpha158.json').read_text())
    verify_baseline(ROOT,'BL-CN-CSI300-A158-LGBM-001')
    if baseline['data_end']>='2021-01-01':raise ValueError('protected data configuration')
    market=load_factor_data(ROOT,baseline)
    calendar=market.membership.index
    if calendar.max()>=pd.Timestamp('2021-01-01'):raise ValueError('protected observations')
    canonical=ROOT/'data/canonical'/baseline['name']
    vwap={}
    for symbol in market.membership.columns:
        frame=pd.read_parquet(canonical/f'{symbol}.parquet').set_index('datetime')
        vwap[symbol]=(frame.amount/frame.volume*frame.factor).where(frame.volume.gt(0)&~frame.is_suspended)
    fields={**market.fields,'vwap':pd.DataFrame(vwap).reindex_like(market.membership)}
    periods={};sets=[]
    for name in ['train','diagnostic']:
        start,end=map(pd.Timestamp,config[name]);lo=calendar.searchsorted(start);hi=calendar.searchsorted(end,side='right')
        a=lo-config['lookback_days'];b=hi+config['future_label_days']
        if a<0 or b>len(calendar) or calendar[b-1]>=pd.Timestamp('2021-01-01'):raise ValueError('data padding out of research bounds')
        dates=calendar[a:b]
        tensor=np.stack([fields[f.name.lower()].loc[dates].where(market.membership.loc[dates]).values for f in FeatureType],axis=1)
        data=StockData.__new__(StockData)
        data.data=torch.tensor(tensor,dtype=torch.float32,device='cpu')
        data.device=torch.device('cpu');data.max_backtrack_days=config['lookback_days'];data.max_future_days=config['future_label_days']
        data._dates=dates;data._stock_ids=market.membership.columns;data._features=list(FeatureType)
        data._start_time=str(start.date());data._end_time=str(end.date());data._instrument='historical_csi300';data.freq='day';data.raw=False
        sets.append(data);periods[name]=[str(dates.min().date()),str(dates.max().date())]
    write(output/'input_contract.json',{'canonical_manifest_sha256':sha(canonical/'manifest.json'),
        'periods_with_padding':periods,'training_dates':config['train'],'diagnostic_dates':config['diagnostic'],
        'historical_membership_mask':True,'shape':[list(d.data.shape) for d in sets],
        'fields':{'ohlc':'canonical raw price * factor','volume':'canonical raw shares / factor',
                  'vwap':'canonical amount / raw volume * factor; zero volume missing'},
        'protected_accessed':False,'data_backend':'sealed canonical tensors; upstream StockData network loaders not invoked'})
    return sets,periods


def sage(config,output,data,test):
    import torch
    from torch import nn
    from torch.optim import Adam
    from alpha_gfn.config import FEATURES,OPERATORS,DELTA_TIMES,CONSTANTS,HIDDEN_DIM,LEARNING_RATE
    from alpha_gfn.modules import SequenceEncoder
    from alpha_gfn.env.core import GFNEnvCore
    from alpha_gfn.alpha_pool import AlphaPoolGFN
    from alpha_gfn.gflownet import EntropyTBGFlowNet
    from alphagen.data.expression import Feature,Ref
    from alphagen_qlib.stock_data import FeatureType
    from gfn.samplers import Sampler
    from gfn.modules import DiscretePolicyEstimator
    from gfn.utils.modules import NeuralNet
    # Helpers are imported from the pinned upstream driver, not reimplemented.
    native=importlib.import_module('train_gfn')
    c=config['alphasage'];close=Feature(FeatureType.CLOSE);target=Ref(close,-20)/close-1
    pool=AlphaPoolGFN(c['pool_capacity'],data,target)
    backbone=SequenceEncoder(len(FEATURES)+len(OPERATORS)+len(DELTA_TIMES)+len(CONSTANTS),c['encoder_type'])
    env=GFNEnvCore(pool,backbone,torch.device('cpu'),c['mask_dropout_prob'],c['ssl_weight'],c['nov_weight'])
    pf_head=NeuralNet(input_dim=HIDDEN_DIM,output_dim=env.n_actions,n_hidden_layers=0)
    pb_head=NeuralNet(input_dim=HIDDEN_DIM,output_dim=env.n_actions-1,n_hidden_layers=0)
    pf=DiscretePolicyEstimator(nn.Sequential(backbone,pf_head),n_actions=env.n_actions,preprocessor=env.preprocessor)
    pb=DiscretePolicyEstimator(nn.Sequential(backbone,pb_head),n_actions=env.n_actions,preprocessor=env.preprocessor,is_backward=True)
    loss_fn=EntropyTBGFlowNet(pf=pf,pb=pb,entropy_coef=c['entropy_coef'],entropy_temperature=c['entropy_temperature'])
    optimizer=Adam(list(backbone.parameters())+list(pf_head.parameters())+list(pb_head.parameters())+[loss_fn.logZ],lr=LEARNING_RATE)
    sampler=Sampler(estimator=pf)
    scheduler=native.WeightScheduler(c['ssl_weight'],c['nov_weight'],c['final_weight_ratio'],c['episodes'],c['weight_decay_type'])
    logger=native.GFNLogger(pf,pool,str(output/'native'),test,target)
    total=0;updates=0;losses=[]
    for episode in range(c['episodes']):
        env.ssl_weight,env.nov_weight=scheduler.get_current_weights()
        trajectories=sampler.sample_trajectories(env=env,n_trajectories=1,save_estimator_outputs=c['entropy_coef']>0)
        loss=loss_fn.loss(env=env,trajectories=trajectories)
        if loss is not None and torch.isfinite(loss):total+=loss
        if episode>0 and (episode+1)%c['update_freq']==0 and isinstance(total,torch.Tensor):
            losses.append(float(total.detach()));total.backward();optimizer.step();optimizer.zero_grad();updates+=1;total=0
        scheduler.step()
        if (episode+1)%16==0:print(f'SAGE episode={episode+1} updates={updates} pool={pool.size}',flush=True)
    logger.log_metrics(c['episodes']);logger.save_checkpoint(c['episodes']);logger.close()
    write(output/'training.json',{'algorithm':'upstream structure-aware GFlowNet','episodes':c['episodes'],'optimizer_updates':updates,
                                  'losses':losses,'pool_size':pool.size,'full_paper_replication':False})
    return output/'native'/f'pool_{c["episodes"]}.json'


def forge(config,output,data,test):
    import torch
    from gan.dataset import Collector
    from gan.network.masker import NetM
    from gan.network.predictor import NetP
    from gan.network.generater import NetG_DCGAN,train_network_generator
    from gan.utils import Builders,save_blds_csv
    from alphagen.rl.env.wrapper import SIZE_ACTION
    from alphagen_generic.features import target
    native=importlib.import_module('train_AFF');c=config['alphaforge']
    cfg=SimpleNamespace(max_len=20,batch_size=c['batch_size'],potential_size=100,g_hidden=128,p_hidden=128,device='cpu',
        batch_size_p=64,num_epochs_p=c['predictor_epochs'],num_epochs_g=c['generator_epochs'],es_p=10,g_es=10,g_es_score='max',
        l_pred=1.,l_simi=10.,l_simi_thresh=.4,l_potential=10.,l_potential_thresh=.4,l_potential_epsilon=1e-7,l_entropy=0)
    generator=NetG_DCGAN(SIZE_ACTION,cfg.potential_size,20,128);masker=NetM(20,SIZE_ACTION);predictor=NetP(SIZE_ACTION,128,20)
    empty=Builders(0,max_len=20,n_actions=SIZE_ACTION)
    metric=native.get_metric(empty,device='cpu',corr_thresh=c['correlation_threshold'])
    collect=Collector(20,SIZE_ACTION);z=torch.zeros(c['batch_size'],100)
    collect.collect_target_num(generator,masker,z,data,target,metric,target_num=c['collection_target'],reset_net=True,
                               drop_invalid=False,randomly=False,random_method=lambda x:x.normal_(),max_iter=c['collection_max_iter'])
    collect.blds.evaluate(data,target,metric)
    x,y,weights=native.blds_list_to_tensor([collect.blds],[1.]);y=native.pre_process_y(y)
    predictor.initialize_parameters();native.train_net_p_with_weight(cfg,predictor,x,y,weights,lr=1e-3)
    generator.initialize_parameters()
    trained=train_network_generator(generator,masker,predictor,cfg,data,target,0,lambda x:x.normal_(),metric,1e-3,SIZE_ACTION)
    generated=collect.collect(generator,masker,z,reset_net=False,random_method=lambda x:x.normal_())
    generated.drop_invalid();generated.evaluate(data,target,metric)
    save_blds_csv(generated,str(output/'generated.csv'));save_blds_csv(trained,str(output/'during_training.csv'))
    torch.save(generator.state_dict(),output/'generator.pt');torch.save(predictor.state_dict(),output/'predictor.pt')
    write(output/'training.json',{'algorithm':'upstream AlphaForge predictor and DCGAN generator losses',
          'predictor_epochs':c['predictor_epochs'],'generator_epochs':c['generator_epochs'],
          'collected':len(collect.blds),'generated':len(generated),'during_training':len(trained),'full_paper_replication':False,
          'scope':'One bounded native training round; exports are candidates, not a completed threshold-filled alpha zoo or dynamic portfolio.'})
    return output/'generated.csv'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',choices=list(UPSTREAMS))
    parser.add_argument('--config',type=Path,default=ROOT/'configs/m3/searcher_integration.json');args=parser.parse_args()
    source=args.source;vendor=ROOT/'vendor'/source
    revision=subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()
    if revision!=UPSTREAMS[source]['revision'] or subprocess.check_output(['git','-C',str(vendor),'status','--porcelain'],text=True).strip():
        raise ValueError('upstream checkout is not the pinned clean revision')
    sys.path[:0]=[str(vendor/'src'),str(vendor)] if source=='alphasage' else [str(vendor)]
    config=json.loads(args.config.read_text());output=ROOT/'experiments/m3_searchers'/source/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True);write(output/'status.json',{'status':'RUNNING'});write(output/'config.json',config)
    print('SEARCHER_RUN '+str(output),flush=True)
    try:
        import numpy as np
        import torch
        torch.set_num_threads(config['threads']);torch.manual_seed(config['seed']);random.seed(config['seed']);np.random.seed(config['seed'])
        source_hashes={str(p.relative_to(vendor)):sha(p) for p in vendor.rglob('*.py')}
        write(output/'source_hashes.json',source_hashes)
        write(output/'runtime.json',{'python':sys.version,'torch':torch.__version__,'device':'cpu','revision':revision,'runner_sha256':sha(__file__)})
        sets,periods=input_tensors(config,output)
        asset=(sage if source=='alphasage' else forge)(config,output,*sets)
        if any(sha(vendor/name)!=expected for name,expected in source_hashes.items()):raise ValueError('upstream changed during execution')
        write(output/'export_manifest.json',{'source':source,'revision':revision,'asset_sha256':sha(asset),
              'periods':periods,'protected_accessed':False,'asset':str(asset.relative_to(output)),
              'generation_evidence':'Local pinned upstream execution; see runtime/training/input contract'})
        write(output/'status.json',{'status':'PASS','asset':str(asset.relative_to(output)),'full_paper_replication':False})
    except BaseException as exc:
        write(output/'status.json',{'status':'FAIL','error':str(exc)});raise


if __name__=='__main__':main()
