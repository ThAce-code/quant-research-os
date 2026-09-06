"""Record the frozen NO_GO branch without opening qualification or lockbox."""
from pathlib import Path
import sys,json,hashlib
from datetime import datetime,timezone
import pandas as pd


def validate_no_go(decision,comparisons):
    if decision['decision']!='NO_GO' or decision['winner'] is not None:
        raise ValueError('a winner requires qualification execution, not a no-entry record')
    if not comparisons or any(v['decision']!='NO_GO' for v in comparisons.values()):
        raise ValueError('upstream decisions do not support no-entry closure')


def main(root,run):
    assert json.loads((run/'status.json').read_text())['status']=='PASS'
    assert json.loads((run/'independent_verification.json').read_text())['status']=='PASS'
    decision=json.loads((run/'research_decision.json').read_text())
    comparisons=json.loads((run/'comparisons.json').read_text());validate_no_go(decision,comparisons)
    c=json.loads((run/'config.json').read_text())
    frozen_hash=json.loads((run/'verification.json').read_text())['frozen_protocol_sha256']
    assert hashlib.sha256((root/'configs/factors/m2_rolling.json').read_bytes()).hexdigest()==frozen_hash
    calendar=pd.read_parquet(root/'data/canonical/baostock_alpha158_csi300_2008_2020/calendar.parquet').datetime
    assert calendar.max()<pd.Timestamp('2021-01-01')
    out=root/'experiments/m2/m2_protected_gate_v1'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    def write(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    evidence={n:hashlib.sha256((run/n).read_bytes()).hexdigest() for n in ['research_decision.json','comparisons.json','independent_verification.json','verification.json']}
    for phase in ['qualification','lockbox']:
        write(phase+'.json',{'status':'NOT_OPENED_NO_ELIGIBLE_CANDIDATE','phase':phase,'period':c[phase]['period'],
            'executed':False,'passed':False,'upstream_decision':'NO_GO','upstream_run':run.name,'upstream_hashes':evidence,
            'protocol_sha256':frozen_hash,'data_requests_issued':0,'protected_observations_read':0,
            'reason':'No historical model variant satisfies the frozen joint entry gate; no retry or retuning allowed',
            'interpretation':'conditional research branch closed; this is not an executed or passed holdout test'})
    write('verification.json',{'status':'PASS','parent_decision_checked':True,'independent_parent_verification':'PASS',
          'canonical_calendar_max':str(calendar.max().date()),'no_network_or_data_collection_called':True,
          'no_independent_alpha_claim':True,'no_holdout_test_claim':True})
    (out/'report.md').write_text('# M2.6 / M2.7 entry decisions\n\nHistorical rolling run `'+run.name+
        '` has no GO candidate. Under the protocol frozen before those model results, qualification 2021–2023 and lockbox 2024–2025 remain unopened. '
        'Both records explicitly state executed=false and passed=false. This closes the conditional no-entry branch; it does not claim independent validation occurred. '
        'There is no candidate to qualify or confirm, and no formula/threshold retry is authorized by this batch.\n',encoding='utf-8')
    write('source_hashes.json',{'scripts/close_protected_gates.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    write('artifact_hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    write('status.json',{'status':'PASS','research_branch':'CLOSED_NO_ENTRY','qualification_executed':False,'lockbox_executed':False})
    print('PROTECTED_GATE '+str(out),flush=True)


if __name__=='__main__':main(Path(__file__).resolve().parents[1],Path(sys.argv[1]))
