"""Read-only R1 numerical replay, independent of its financial and model adapters."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.r1.workflow import market_data


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def check(folder):
    assert read(folder/'status.json')['status']=='PASS'
    for name,h in read(folder/'artifact_hashes.json').items():assert sha(folder/name)==h,name
    for name,h in read(folder/'source_hashes.json').items():assert sha(folder/'source'/name)==h,name


def bootstrap(series,c):
    values=np.asarray(series,dtype=float);n=len(values);block=c['block_length']
    if np.isfinite(values).sum()<max(40,2*block):return {'mean':None,'low':None,'high':None,'p':1.}
    starts=np.random.default_rng(c['seed']).integers(n,size=(c['bootstrap_samples'],int(np.ceil(n/block))))
    draws=np.array([np.nanmean(values[np.concatenate([np.arange(s,s+block)%n for s in row])[:n]]) for row in starts])
    mu=np.nanmean(values)
    return {'mean':float(mu),'low':float(np.quantile(draws,.025)),'high':float(np.quantile(draws,.975)),
            'p':float((1+(draws-mu>=mu).sum())/(len(draws)+1))}


def bh(p):
    return [min(1.,min(len(p)*z/(np.asarray(p)<=z).sum() for z in p if z>=v)) for v in p]


def compare(a,b):
    for k,v in a.items():
        if v is None:assert b[k] is None
        else:np.testing.assert_allclose(v,b[k],rtol=1e-10,atol=1e-12)


def rank_ic(scores,labels,min_pairs):
    out=[];labels=labels.reindex_like(scores)
    for date in scores.index:
        frame=pd.concat([scores.loc[date].rename('s'),labels.loc[date].rename('y')],axis=1).dropna()
        out.append(frame.s.rank().corr(frame.y.rank()) if len(frame)>=min_pairs else np.nan)
    return pd.Series(out,index=scores.index)


def label_panel(market,c,segment):
    prices=market.fields['close'];out=prices*float('nan');reach=c['horizon']+1
    eligible=market.execution_eligible
    for pos,date in enumerate(prices.index[:-reach]):
        if not pd.Timestamp(segment[0])<=date<=pd.Timestamp(segment[1]):continue
        if prices.index[pos+reach]>pd.Timestamp(segment[1]):continue
        valid=market.membership.loc[date]&eligible.iloc[pos+1]&eligible.iloc[pos+reach]
        out.loc[date]=((prices.iloc[pos+reach]/prices.iloc[pos+1])-1).where(valid)
    return out.loc[segment[0]:segment[1]]


def verify_inputs(inputs,market,c):
    check(inputs);audit=ROOT/c['financial_audit']
    for name,h in c['financial_inputs'].items():assert sha(audit/name)==h
    p=pd.read_parquet(audit/'profit.parquet');cash=pd.read_parquet(audit/'cash.parquet')
    lookup=lambda frame:{(r['code'],pd.Timestamp(r['statDate'])):r for r in frame.to_dict('records')}
    p,cf=lookup(p),lookup(cash)
    events=pd.read_parquet(inputs/'financial_events.parquet');events_checked=0;cells=0
    for r in events.itertuples():
        period=pd.Timestamp(r.statDate);prior=period-pd.DateOffset(years=1)
        pp=p.get((r.code,period));cc=cf.get((r.code,period));prevp=p.get((r.code,prior));prevc=cf.get((r.code,prior))
        if r.candidate=='R1_CASH_SURPLUS':deps=[pp,cc]
        elif r.candidate=='R1_CASH_IMPROVEMENT':deps=[pp,cc,prevp,prevc]
        else:deps=[pp,prevp]
        expected=np.nan
        if all(d is not None for d in deps) and max(pd.Timestamp(d['pubDate']) for d in deps)<=r.pubDate:
            def gap(profit,flow):
                margin=profit['npMargin'];observed=flow['CFOToOR'];implied=flow['CFOToNP']*margin
                return observed-margin if np.isfinite(implied) and np.isfinite(observed) and abs(implied-observed)<=2e-5+2e-5*abs(observed) else np.nan
            if r.candidate=='R1_CASH_SURPLUS':expected=gap(pp,cc)
            elif r.candidate=='R1_CASH_IMPROVEMENT':expected=gap(pp,cc)-gap(prevp,prevc)
            else:
                field='gpMargin' if r.candidate=='R1_GROSS_MARGIN_CHANGE' else 'npMargin'
                expected=pp[field]-prevp[field]
        np.testing.assert_allclose(expected,r.value,equal_nan=True,atol=1e-12)
        assert r.pubDate<=pd.Timestamp(c['data_period'][1]);events_checked+=1
    for name,group in events.groupby('candidate'):
        raw=pd.read_parquet(inputs/name/'raw.parquet')
        for symbol,part in group.groupby('symbol'):
            sampled=raw.index[np.linspace(0,len(raw)-1,12,dtype=int)]
            for date in sampled:
                known=part[part.pubDate<date]
                expected=np.nan
                if len(known):
                    last=known.sort_values(['statDate','pubDate']).iloc[-1]
                    if (date-last.pubDate).days<=400 and (date-last.statDate).days<=550:expected=last.value
                np.testing.assert_allclose(raw.loc[date,symbol],expected,equal_nan=True,atol=1e-12);cells+=1
    close=market.fields['close'];turn=market.fields['turnover']
    expected={'R1_QUIET_REVERSAL':-(close/close.shift(5)-1)/(1+turn/turn.rolling(20).mean().where(lambda x:x>0)),
              'R1_ACTIVE_CONTINUATION':(close/close.shift(20)-1)*turn/(turn.rolling(60).mean().where(lambda x:x>0)+turn)}
    for name,raw in expected.items():
        saved=pd.read_parquet(inputs/name/'raw.parquet')
        np.testing.assert_allclose(raw.reindex_like(saved),saved,rtol=1e-10,atol=1e-12,equal_nan=True);cells+=saved.size
    return {'financial_events_recomputed':events_checked,'raw_cells_replayed':cells}


def verify(inputs,full):
    c=read(inputs/'protocol.json');items=read(inputs/'candidates.json');_,market=market_data(ROOT)
    evidence=verify_inputs(inputs,market,c)
    if not full:return {'status':'PASS','stage':'inputs',**evidence}
    screen=inputs/'screen';model=inputs/'model';check(screen);check(model)
    results=read(screen/'results.json');labels=label_panel(market,c,c['screen_period']);daily={};ps=[]
    for item in items:
        name=item['name'];score=pd.read_parquet(inputs/name/'scores.parquet').loc[c['screen_period'][0]:c['screen_period'][1]]
        stored=pd.read_csv(screen/f'{name}_ic.csv',index_col=0,parse_dates=True)
        ric=rank_ic(score,labels,c['screen']['min_pairs']);daily[name]=ric
        np.testing.assert_allclose(ric,stored.rank_ic,equal_nan=True,atol=1e-12)
        b=bootstrap(ric,c);compare(b,results[name]['inference']);ps.append(b['p'])
        compare({'rank_ic':float(ric.mean())},results[name]['primary'])
        for year,part in ric.groupby(ric.index.year):compare({'rank_ic':float(part.mean())},results[name]['years'][str(year)])
    qs=bh(ps+[1.]*(12-len(ps)));chosen=[]
    coverage=pd.read_csv(inputs/'coverage.csv');mask=pd.read_parquet(inputs/'universe.parquet')
    for item,q in zip(items,qs):
        row=results[item['name']];np.testing.assert_allclose(q,row['q'])
        panel=pd.read_parquet(inputs/item['name']/'scores.parquet')
        for y in [2015,2016]:
            actual=panel.loc[str(y)].notna().to_numpy().sum()/mask.loc[str(y)].to_numpy().sum()
            np.testing.assert_allclose(actual,row['coverage'][str(y)])
        positive=all(row['years'][str(y)]['rank_ic']>0 for y in [2015,2016])
        enough=min(row['coverage'].values())>=.7
        assert row['status']==('FORWARD' if positive and enough and row['primary']['rank_ic']>=.01 and q<=.1 else 'REJECT')
    for family in c['family_order']:
        for item in items:
            row=results[item['name']]
            if item['family']==family and min(row['coverage'].values())>=.7 and all(row['years'][str(y)]['rank_ic']>0 for y in [2015,2016]):
                chosen.append(item['name']);break
    assert chosen==read(screen/'selection.json')['selected']
    state=read(model/'status.json');evidence.update(screen_rank_ic_days=sum(len(v) for v in daily.values()),screen_bootstrap_replayed=True,selected=chosen)
    if not chosen:
        assert state['decision']=='NO_ENTRY' and state['fits']==state['portfolios']==0
    elif state['decision']=='DATA_GATE_FAIL':
        counts=read(model/'sample_gate.json')
        assert any(r['train_rows']<c['min_train_rows'] or r['valid_rows']<c['min_valid_rows'] for r in counts)
    else:
        import lightgbm as lgb
        cfg=read(model/'config.json');variants=cfg['variants'];folds=pd.read_csv(model/'folds.csv')
        x=pd.read_parquet(model/'features.parquet');y=pd.read_parquet(model/'labels.parquet').label
        pred=pd.read_parquet(model/'predictions.parquet');calendar=market.membership.index
        expected=label_panel(market,c,c['data_period']).rename_axis(index='datetime',columns='instrument').stack(future_stack=True).reindex(y.index)
        np.testing.assert_allclose(y,expected,equal_nan=True,atol=1e-12)
        source=pd.read_parquet(ROOT/c['controls_run']/'alpha158.parquet')
        valid=pd.Series(True,index=source.index)
        for name in chosen:
            panel=pd.read_parquet(inputs/name/'scores.parquet').rename_axis(index='datetime',columns='instrument').stack(future_stack=True).reindex(source.index)
            valid &= panel.notna()
        pd.testing.assert_index_equal(x.index,source.index[valid])
        replayed=0
        for f in folds.itertuples():
            for part in ['train','valid']:
                end=pd.Timestamp(getattr(f,part+'_end'));exit_date=pd.Timestamp(getattr(f,part+'_label_exit'))
                assert calendar.get_loc(exit_date)-calendar.get_loc(end)==21
                assert exit_date<pd.Timestamp(f.year-(part=='train'),1,1)
            available=pred.index[pred.index.get_level_values('datetime').year==f.year]
            sample=available[np.linspace(0,len(available)-1,30,dtype=int)]
            booster=lgb.Booster(model_file=str(model/'models'/f'{f.year}_{f.variant}.txt'))
            np.testing.assert_allclose(booster.predict(x.loc[sample,list(x.columns[:158])+variants[f.variant]]),pred.loc[sample,f.variant],rtol=1e-10,atol=1e-12)
            replayed+=len(sample)
        rics={};reports={}
        dates=calendar[(calendar>=c['evaluation_period'][0])&(calendar<=c['evaluation_period'][1])]
        for name in variants:
            scores=pred[name].unstack('instrument').loc[c['evaluation_period'][0]:]
            actual=rank_ic(scores,y.unstack('instrument'),c['min_prediction_daily_pairs'])
            stored=pd.read_csv(model/f'{name}_ic.csv',index_col=0,parse_dates=True)
            np.testing.assert_allclose(actual,stored.rank_ic,equal_nan=True,atol=1e-12);rics[name]=actual
            report=pd.read_csv(model/f'{name}_daily.csv',index_col=0,parse_dates=True)
            assert report.index.equals(dates)
            assert (report.loc[~report.index.isin(dates[::5]),'cost'].abs()<1e-12).all()
            reports[name]=report['return']-report.cost
        comparisons=read(model/'comparisons.json');ps=[];rankstats={}
        for name,row in comparisons.items():
            b=bootstrap(rics[name]-rics['BASE'],c);compare(b,row['rank_ic_increment']);ps.append(b['p']);rankstats[name]=b
            net=reports[name]-reports['BASE'];compare(bootstrap(net,c),row['net_increment'])
            np.testing.assert_allclose(net.mean()*238,row['annual_net_increment'])
            for year,part in net.groupby(net.index.year):np.testing.assert_allclose(part.mean()*238,row['by_year'][str(year)])
        qs=bh(ps+[1.]*(7-len(ps)))
        for (name,row),q in zip(comparisons.items(),qs):
            np.testing.assert_allclose(q,row['q']);g=c['gate'];positive=sum(row['by_year'][str(y)]>0 for y in g['full_years'])
            passed=row['rank_ic_increment']['mean']>=g['min_rank_ic_increment'] and q<=g['max_increment_q'] and row['annual_net_increment']>=g['min_net_annual_increment'] and row['net_increment']['low']>0 and positive>=g['min_positive_full_years']
            assert row['decision']==('GO' if passed else 'NO_GO')
        assert state['fits']==len(folds)==6*len(variants) and state['portfolios']==len(variants)
        evidence.update(predictions_replayed=replayed,prediction_rows=len(pred),model_bootstrap_replayed=True,model_variants=len(variants))
    with sqlite3.connect((ROOT/'data/factor_registry.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        screens=db.execute('select report_json from evaluations where run_id=?',(inputs.name+'_SCREEN',)).fetchall()
        models=db.execute('select report_json from evaluations where run_id=?',(inputs.name+'_MODEL',)).fetchall()
    assert len(screens)==6
    for (text,) in screens:
        row=json.loads(text);assert row['independent_alpha'] is False
        assert any(all(row.get(k)==v for k,v in result.items()) for result in results.values())
    if (model/'comparisons.json').exists():
        comparisons=read(model/'comparisons.json');assert len(models)==len(comparisons)
        for (text,) in models:assert json.loads(text)['model_increment'] in comparisons.values()
    else:assert not models
    assert state['qualification']==state['lockbox']=='SEALED'
    return {'status':'PASS','decision':state['decision'],**evidence,'registry_screen_records':len(screens),'registry_model_records':len(models),
            'limits':'Historical exploratory evidence. Financial vintages remain unknown; sampled panel transfer, full event/formula checks; no fill-level or capacity verification.',
            'verifier_sha256':sha(Path(__file__))}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('inputs',type=Path);p.add_argument('--full',action='store_true');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=verify(args.inputs,args.full);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
