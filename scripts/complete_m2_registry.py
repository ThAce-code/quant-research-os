"""Append previously unarchived M2 failures using the existing registry schema."""
from pathlib import Path
import sys,json,hashlib
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from quant_research.factors.registry import FactorRegistry


def main(root,rolling):
    assert json.loads((rolling/'status.json').read_text())['status']=='PASS'
    assert json.loads((rolling/'independent_verification.json').read_text())['status']=='PASS'
    decision=json.loads((rolling/'research_decision.json').read_text())
    if decision['decision']!='NO_GO':raise ValueError('a GO candidate needs subsequent admission evidence')
    registry=FactorRegistry(root/'data/m2_factor_registry.sqlite')
    before=registry.evaluations();previous={(r['run_id'],r['factor_id']):r['report'] for r in before};written=[]
    def save(run_id,key,report):
        if (run_id,key) in previous:assert previous[(run_id,key)]==report
        else:registry.record(run_id,key,report)
        written.append({'run_id':run_id,'factor_id':key,'report':report})
    def definition(name,family,expression,direction):
        return {'name':name,'family':family,'expression':expression,'direction':direction,
                'hypothesis':'Fixed preregistered economic hypothesis; see linked immutable trial configuration',
                'source':'baostock_revision_unknown','paper':None,'generator':'human_preregistered','version':1}
    family=root/'experiments/m2/m2_four_family_screen_v1/20260906T063503769408Z'
    published=json.loads((root/'docs/results/sources.json').read_text())
    assert hashlib.sha256((family/'metrics.json').read_bytes()).hexdigest()==published['docs/results/m2_family_screen/metrics.json']['sha256']
    metrics=json.loads((family/'metrics.json').read_text())
    c=json.loads((root/'configs/factors/m2_quarterly.json').read_text())
    for name,d in c['candidates'].items():
        key='M2_'+name;registry.register(key,definition(key,d['family'],f"{d['direction']} * {d['field']}; publication-aligned, industry/size neutral",d['direction']))
        assert metrics[name]['screen_status']=='IC_SCREEN_REJECT'
        save(family.name,key,{'status':'REJECT','trial_kind':'historical_factor_screen','source_run':family.name,
              'source_sha256':hashlib.sha256((family/'metrics.json').read_bytes()).hexdigest(),'original_result':metrics[name],
              'scope':'2015-2016 observed history; no independent confirmation'})
    supplement=root/'experiments/m2/m2_supplementary_screen_v1/20260906T084009964682Z'
    assert hashlib.sha256((supplement/'ic_metrics.json').read_bytes()).hexdigest()==published['docs/results/m2_supplementary_screen/ic_metrics.json']['sha256']
    metrics=json.loads((supplement/'ic_metrics.json').read_text())
    c=json.loads((supplement/'config.json').read_text())
    for name,d in c['hypotheses'].items():
        key='M2_'+name;registry.register(key,definition(key,d['family'],d['expression']+'; industry/size neutral',d['direction']))
        assert metrics[name]['screen_status']=='IC_SCREEN_REJECT'
        save(supplement.name,key,{'status':'REJECT','trial_kind':'historical_factor_screen','source_run':supplement.name,
              'source_sha256':hashlib.sha256((supplement/'ic_metrics.json').read_bytes()).hexdigest(),'original_result':metrics[name],
              'scope':'2015-2020 observed/burned history; no independent confirmation'})
    comparisons=json.loads((rolling/'comparisons.json').read_text())
    assert hashlib.sha256((rolling/'comparisons.json').read_bytes()).hexdigest()==json.loads((rolling/'artifact_hashes.json').read_text())['comparisons.json']
    for key,variant in [('M2_BP_neutral','ADD_BP'),('M2_CASHFLOW_MARGIN_YTD','ADD_CASHFLOW')]:
        assert comparisons[variant]['decision']=='NO_GO'
        save(rolling.name,key,{'status':'REJECT','trial_kind':'model_increment_admission','source_run':rolling.name,
              'source_sha256':hashlib.sha256((rolling/'comparisons.json').read_bytes()).hexdigest(),'variant':variant,
              'original_result':comparisons[variant],'joint_variant':comparisons['ADD_BOTH'],
              'scope':'Final rejection for this fixed M2 research budget; preserve earlier historical FORWARD/REJECT trials'})
    after=registry.evaluations();lookup={(r['run_id'],r['factor_id']):r['report'] for r in after}
    for row in written:assert lookup[(row['run_id'],row['factor_id'])]==row['report']
    for row in before:assert lookup[(row['run_id'],row['factor_id'])]==row['report']
    assert not registry.existing_pool()
    out=root/'experiments/m2/m2_registry_closure_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    def write(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write('trials.json',written)
    write('verification.json',{'status':'PASS','archived_trials_checked':len(written),'prior_trials_preserved':len(before),
          'total_trials':len(after),'keep_pool_size':0,'registry_schema_unchanged':True,'readback_report_parity':True})
    write('source_hashes.json',{'scripts/complete_m2_registry.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    write('artifact_hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    write('status.json',{'status':'PASS'});print('REGISTRY '+str(out),flush=True)


if __name__=='__main__':main(Path(__file__).resolve().parents[1],Path(sys.argv[1]))
