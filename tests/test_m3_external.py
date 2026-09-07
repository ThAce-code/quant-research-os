import json

import pytest

from quant_research.m3.external import UPSTREAMS,translate,read_export,import_export
from quant_research.m3.pipeline import sha
from quant_research.m3.campaign import CampaignLedger
from test_m3_campaign import spec,candidate


def asset(tmp_path,source,expressions):
    path=tmp_path/('pool.json' if source=='alphasage' else 'pool.csv')
    if source=='alphasage':path.write_text(json.dumps({'exprs':expressions,'weights':[1]*len(expressions)}))
    else:
        import csv
        with path.open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['','exprs','scores'])
            for i,expr in enumerate(expressions):writer.writerow([i,expr,0.5])
    return path,{'source':source,'revision':UPSTREAMS[source]['revision'],'asset_sha256':sha(path),
                 'periods':{'train':['2010-01-01','2014-12-31']},'protected_accessed':False}


@pytest.mark.parametrize('source,expression',[('alphaforge','ts_mean(Div($close,$open),5)'),('alphasage','TsMean(Div($close,$open),5)')])
def test_native_syntax_maps_only_checked_operations(source,expression):
    result,fields,semantics=translate(source,expression)
    assert result=='Mean(Div(close, open), 5)' and fields=={'close','open'} and semantics


@pytest.mark.parametrize('source,text',[('alphasage','Rank($close)'),('alphasage','TsRank($close,20)'),
                                      ('alphaforge','CSRank($close)'),('alphaforge','ts_rank($close,20)'),
                                      ('alphaforge','Ref($close,-1)'),('alphasage','$unknown'),
                                      ('alphasage','Div(1,Log($close))'),('alphaforge','ts_delta(close,0)'),
                                      ('alphasage','Abs(-1)'),
                                      ('alphasage','__import__("os").system("echo bad")')])
def test_unaligned_unknown_and_future_expressions_fail(source,text):
    with pytest.raises(ValueError):translate(source,text)


def test_protected_training_period_and_wrong_revision_rejected(tmp_path):
    path,manifest=asset(tmp_path,'alphasage',['$close'])
    for change in [{'revision':'unknown'},{'periods':{'train':['2021-01-01','2022-01-01']}},{'protected_accessed':True}]:
        with pytest.raises(ValueError):read_export('alphasage',path,{**manifest,**change})


@pytest.mark.parametrize('source',['alphaforge','alphasage'])
def test_export_import_does_not_promote_scores_and_records_unsupported_attempt(tmp_path,source):
    path,manifest=asset(tmp_path,source,['Div($close,$open)','Pow($close,2)'])
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec())
    annotations=[{'row':0,**candidate('ignored','SEARCH_ONE')},{'row':1,**candidate('ignored','SEARCH_TWO')}]
    result=import_export(ledger,'study',0,source,path,manifest,annotations)
    assert [r['status'] for r in result['proposals']]==['ACCEPTED','INVALID']
    snap=ledger.snapshot('study')
    imported=json.loads(snap['proposals'][0]['payload'])
    assert imported['expression']=='Div(close, open)' and imported['source_type']=='SEARCH_GENERATED'
    assert 'scores' not in imported and imported['direction']==1
    assert not snap['evaluations']


def test_export_asset_identity_checked_before_proposals(tmp_path):
    path,manifest=asset(tmp_path,'alphasage',['$close']);path.write_text('{}')
    ledger=CampaignLedger(tmp_path/'ledger.sqlite');ledger.create(spec())
    with pytest.raises(ValueError,match='identity'):import_export(ledger,'study',0,'alphasage',path,manifest,[{'row':0,**candidate()}])
    assert ledger.snapshot('study')['proposals']==[]


def test_actual_forge_export_spelling_and_inverse():
    expression,fields,_=translate('alphaforge','Inv((-0.01*vwap))')
    assert expression=='Div(1, Mul(-(0.01), vwap))' and fields=={'vwap'}
    expression,fields,_=translate('alphaforge','(2.0-((vwap--10.0)-30.0))')
    assert fields=={'vwap'} and 'Sub(vwap, -(10.0))' in expression
