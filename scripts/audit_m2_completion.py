"""Audit the finite M2 decision tree; NO_GO is not independent alpha confirmation."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.factors.engine import verify_baseline
from quant_research.factors.provenance import verify_data_identity


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(history):
    history=Path(history);c=read(history/'config.json')
    frozen=verify_baseline(ROOT,'BL-CN-CSI300-A158-LGBM-001')
    baseline_identity=verify_data_identity(ROOT,read(ROOT/'configs/experiments/baostock_alpha158.json'),frozen)
    independent=read(history/'independent_verification.json')
    assert independent['status']=='PASS'
    assert independent['accounted_symbol_method_quarters']==40520
    member=pd.read_parquet(history/'membership.parquet')
    assert independent['panel_cells_checked']==member.size*5 and len(member.columns)==726
    assert c==read(ROOT/'configs/factors/m2_alternate_history.json')
    sources=read(ROOT/'docs/results/sources.json')
    for path,entry in sources.items():assert sha(ROOT/path)==entry['sha256'],path
    paths={
        'M2.0':'docs/results/m2/verification.json',
        'M2.1':'docs/results/m2/verification.json',
        'M2.2':'docs/results/m2_alpha_map/verification.json',
        'families':'docs/results/m2_family_screen/verification.json',
        'supplementary':'docs/results/m2_supplementary_screen/verification.json',
        'cashflow':'docs/results/m2_supplementary_data/independent_verification.json',
        'M2.4':'docs/results/m2_conditional_completion/verification.json',
        'M2.5':'docs/results/m2_rolling/independent_verification.json',
        'registry':'docs/results/m2_registry_closure/verification.json'}
    evidence={}
    for key,name in paths.items():
        value=read(ROOT/name);assert value['status']=='PASS'
        evidence[key]={'path':name,'sha256':sha(ROOT/name)}
    assert read(ROOT/paths['M2.1'])['candidate_variants']==6
    assert read(ROOT/paths['M2.2'])['features']==158
    assert read(ROOT/paths['families'])['primary_tests']==3
    assert read(ROOT/paths['M2.5'])['folds_checked']==24
    rolling=ROOT/'experiments/m2/m2_rolling_v1/20260906T092732142566Z'
    decision=read(rolling/'research_decision.json');assert decision['decision']=='NO_GO'
    table=pd.read_csv(rolling/'summary.csv');assert len(table)==3 and table.decision.eq('NO_GO').all()
    for phase in ['qualification','lockbox']:
        gate=read(ROOT/f'docs/results/m2_protected_gate/{phase}.json')
        assert gate['status']=='NOT_OPENED_NO_ELIGIBLE_CANDIDATE'
        assert not gate['executed'] and not gate['passed'] and gate['data_requests_issued']==0 and gate['protected_observations_read']==0
        assert gate['protocol_sha256']==sha(ROOT/'configs/factors/m2_rolling.json')
        for name,digest in gate['upstream_hashes'].items():assert sha(rolling/name)==digest
    with sqlite3.connect('file:'+str(ROOT/'data/m2_factor_registry.sqlite').replace('\\','/')+'?mode=ro',uri=True) as con:
        keep=con.execute("SELECT count(*) FROM evaluations WHERE status='KEEP'").fetchone()[0]
        trials=con.execute('SELECT count(*) FROM evaluations').fetchone()[0]
    assert keep==0 and trials==33
    tests=(ROOT/'experiments/m2_alternate_final_regression.log').read_text(encoding='utf-8',errors='replace')
    match=re.search(r'(\d+) passed, (\d+) warnings in ([\d.]+)s',tests)
    assert match and int(match[1])>=158 and ' FAILED ' not in tests
    accounting=pd.read_csv(history/'quarter_accounting.csv')
    assignment=pd.read_csv(history/'source_assignment.csv')
    assert len(accounting)==40520 and len(assignment)==1452
    assert assignment.source.value_counts().to_dict()=={'baostock':987,'eastmoney_reconstructed':465}
    result={'status':'COMPLETE_NO_GO','goal_achieved':True,'audit_time':datetime.now(timezone.utc).isoformat(),
            'scope':'Frozen finite M2 research over historical CSI300, 2008 through July 2020. Original symbol/quarter/field data delivery completed using authorized alternate source; not full A-share market or historical-version PIT.',
            'M2.0':'COMPLETE','M2.1':'COMPLETE','M2.2':'COMPLETE',
            'M2.3':'COMPLETE_FINITE_FAMILY_STUDY_AND_SOURCE_LABELLED_DATA_DELIVERY',
            'M2.4':'COMPLETE_DIAGNOSTICS_NO_CONFIRMED_INCREMENT','M2.5':'COMPLETE_NO_GO',
            'M2.6':'CLOSED_NO_ENTRY_NOT_EXECUTED','M2.7':'CLOSED_NO_ENTRY_NOT_EXECUTED',
            'independent_alpha_found':False,'keep_pool_size':keep,'registry_trials':trials,
            'baseline_source_and_artifacts_unchanged':True,'baseline_data_identity':baseline_identity,
            'history_run':history.name,'history_independent_verification':independent,
            'history_verification_sha256':sha(history/'independent_verification.json'),
            'research_evidence':evidence,'regression':match[0],'public_source_hashes_checked':len(sources),
            'remaining_required_tasks':[],
            'limitations':['Conservative alternate-source update-time guard reduces usable coverage; missing values retained',
                           'Original historical financial versions not reconstructed; BaoStock source retains legacy revision uncertainty',
                           '8,354 original BaoStock responses remain unavailable; alternate data is not labelled as BaoStock',
                           'Qualification and lockbox not executed because upstream joint admission failed',
                           'No full-market, independent alpha, capacity or live-trading claim']}
    (ROOT/'docs/M2_COMPLETION_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)


if __name__=='__main__':main(sys.argv[1])
