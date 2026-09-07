"""Common campaign entry for imports, generated candidates and research feedback."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from .campaign import CampaignLedger, CampaignSpec
from .candidates import ResearchHypothesis
from .data_contract import freeze_binding, required_fields
from .pipeline import sha, run as screen_run
from ..factors.engine import strict_write_json as write
from ..factors.registry import FactorRegistry
from ..m2.family_screen import checked_artifact
from .increment import run as increment_run, survivors


def seed_existing(root, ledger):
    """Read existing definitions; never rewrite the empirical registries."""
    imported, unsupported = [], []
    for name in ['factor_registry.sqlite','m2_factor_registry.sqlite']:
        path=Path(root).resolve()/'data'/name
        if not path.exists():continue
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            for factor_id, expression, direction in db.execute('SELECT factor_id,expression,direction FROM factors'):
                try:
                    ledger.import_expression(expression,direction,f'{name}:{factor_id}')
                    imported.append(f'{name}:{factor_id}')
                except ValueError:
                    # Legacy M2 descriptions are not DSL expressions. Keep the gap explicit.
                    unsupported.append(f'{name}:{factor_id}')
    return {'imported':imported,'unsupported_legacy_definitions':unsupported}


def create_campaign(root, spec_path):
    root=Path(root).resolve()
    spec=CampaignSpec(**json.loads(Path(spec_path).read_text(encoding='utf-8')))
    ledger=CampaignLedger(root/'data/m3_campaigns.sqlite');ledger.create(spec)
    report=seed_existing(root,ledger)
    return ledger,spec,report


def import_candidates(ledger,campaign,round_number,path,source_type):
    """Input is a full reviewed hypothesis JSON; no formula is inferred from prose."""
    if source_type not in {'PAPER_EXACT','PAPER_RECONSTRUCTED','PAPER_INSPIRED','HUMAN_GENERATED'}:
        raise ValueError('manual imports must declare paper or human source')
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    candidates=payload.get('candidates')
    if not isinstance(candidates,list) or not 1<=len(candidates)<=3:
        raise ValueError('import one to three hypotheses per batch')
    return [ledger.propose(campaign,round_number,{**h,'source_type':source_type} if isinstance(h,dict) else h) for h in candidates]


def prepare_evaluation(root,ledger,campaign,proposal_ids):
    """Reserve before execution. Interrupted reservations require evidence-based recovery."""
    root=Path(root).resolve();snap=ledger.snapshot(campaign)
    if not 1<=len(proposal_ids)<=3 or len(set(proposal_ids))!=len(proposal_ids):
        raise ValueError('select one to three distinct proposals')
    chosen={p['id']:p for p in snap['proposals'] if p['status']=='ACCEPTED'}
    reserved={e['proposal'] for e in snap['evaluations']}
    if not set(proposal_ids)<=chosen.keys() or set(proposal_ids)&reserved:
        raise ValueError('proposal is missing, rejected or already reserved; use attach-screen for recovery')
    spec=json.loads(snap['campaign']['spec'])
    if len(reserved)+len(proposal_ids)>spec['max_evaluations']:
        raise ValueError('evaluation budget exhausted')
    protocol=root/'configs/factors/m2_family_screen.json'
    dates=json.loads(protocol.read_text())['period']
    if not spec['research_period'][0]<=dates[0]<=dates[1]<=spec['research_period'][1]:
        raise ValueError('current numerical screen outside campaign period')
    batch={'schema_version':1,'feedback_scope':'research_only','automatic_refinement':False,
           'screen_protocol_sha256':sha(protocol),
           'candidates':[json.loads(chosen[p]['payload']) for p in proposal_ids]}
    binding=freeze_binding(root,required_fields([ResearchHypothesis(**h) for h in batch['candidates']]))
    if binding is not None:batch['data_contract']=binding
    directory=root/'experiments/m3_campaigns'/campaign
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/('batch_'+'_'.join(map(str,proposal_ids))+'.json')
    if path.exists():raise ValueError('batch already frozen; inspect existing execution before recovery')
    # Persist the exact input before reserving; an orphan input is harmless, while
    # a reservation without recoverable input would be ambiguous after a crash.
    with path.open('x',encoding='utf-8') as stream:
        json.dump(batch,stream,indent=2,allow_nan=False)
    ledger.reserve_evaluations(proposal_ids)
    return path


def attach_screen(root,ledger,campaign,screen,proposal_ids):
    """Only checksummed outputs matching the existing numerical registry enter memory."""
    root=Path(root).resolve();screen=Path(screen).resolve()
    if not 1<=len(proposal_ids)<=3 or len(set(proposal_ids))!=len(proposal_ids):
        raise ValueError('select one to three distinct proposals')
    if json.loads((screen/'status.json').read_text())['status']!='PASS':
        raise ValueError('cannot attach incomplete screen')
    manifest=json.loads((screen/'artifact_hashes.json').read_text())
    batch=json.loads(checked_artifact(screen,'batch.json',manifest).read_text())
    c=json.loads(checked_artifact(screen,'screen_protocol.json',manifest).read_text())
    research=json.loads(checked_artifact(screen,'results.json',manifest).read_text())
    hypotheses={ResearchHypothesis(**h).hypothesis_id:ResearchHypothesis(**h) for h in batch['candidates']}
    snap=ledger.snapshot(campaign);proposals={p['id']:p for p in snap['proposals']}
    frozen=root/'experiments/m3_campaigns'/campaign/('batch_'+'_'.join(map(str,proposal_ids))+'.json')
    if not frozen.exists() or json.loads(frozen.read_text(encoding='utf-8'))!=batch:
        raise ValueError('screen does not match the frozen campaign batch')
    protocol_source=screen/'source/configs/factors/m2_family_screen.json'
    if (not protocol_source.exists() or batch.get('screen_protocol_sha256')!=sha(protocol_source)
            or json.loads(protocol_source.read_text())!=c):
        raise ValueError('screen protocol differs from batch freeze')
    rows={r['factor_id']:r['report'] for r in FactorRegistry(root/'data/factor_registry.sqlite').evaluations()
          if r['run_id']==screen.name}
    prepared=[]
    for proposal in proposal_ids:
        h=ResearchHypothesis(**json.loads(proposals[proposal]['payload']))
        if h.hypothesis_id not in hypotheses:raise ValueError('hypothesis not present in screen')
        result=research[h.name];registered=rows.get(h.factor().factor_id)
        if registered is None or any(registered.get(k)!=v for k,v in result.items()):
            raise ValueError('result differs from numerical registry')
        prepared.append((proposal,{'scope':'research_only','protected_accessed':False,
            'period':c['period'],'decision':result['admission_stage'],
            'primary':result['primary'],'inference':result['inference'],
            'batch_q':result['q'],'screen_run':screen.name,
            'result_sha256':sha(screen/'results.json'),
            'interpretation':'EXPLORATORY_SEARCH_FEEDBACK; batch q is not campaign-wide confirmation'}))
    for proposal,evidence in prepared:ledger.finish_evaluation(proposal,screen.name,evidence)
    return ledger.snapshot(campaign)


def evaluate(root,ledger,campaign,proposal_ids):
    batch=prepare_evaluation(root,ledger,campaign,proposal_ids)
    try:
        output=screen_run(root,batch)
    except Exception as exc:
        # This invocation is known terminal. An abrupt process death instead
        # leaves RESERVED and cannot authorize another execution on restart.
        ledger.fail_evaluations(proposal_ids,type(exc).__name__)
        raise
    attach_screen(root,ledger,campaign,output,proposal_ids)
    return output


def freeze_campaign(root,ledger,campaign,selected):
    root=Path(root).resolve()
    protocols={name:sha(root/name) for name in ['configs/m3/increment.json','configs/factors/m2_rolling.json']}
    # Recompute admission against the real registry instead of trusting ledger text.
    snapshot=ledger.snapshot(campaign);proposals={p['id']:p for p in snapshot['proposals']}
    evaluations={e['proposal']:e for e in snapshot['evaluations'] if e['state']=='COMPLETE'}
    for proposal in selected:
        if proposal not in proposals or proposal not in evaluations:raise ValueError('selected proposal lacks completed screen')
        screen=root/'experiments/m3'/evaluations[proposal]['run_id']
        accepted,_=survivors(screen,FactorRegistry(root/'data/factor_registry.sqlite'))
        h=ResearchHypothesis(**json.loads(proposals[proposal]['payload']))
        if h.hypothesis_id not in {a.hypothesis_id for a in accepted}:raise ValueError('selected proposal failed numerical screening')
    frozen=ledger.freeze(campaign,selected,protocols)
    directory=root/'experiments/m3_campaigns'/campaign;directory.mkdir(parents=True,exist_ok=True)
    write(directory/'freeze.json',frozen)
    return frozen


def attach_model(root,ledger,campaign,run,proposal_ids,legacy=False):
    """Import a checksummed numerical model outcome, never an evaluator's prose."""
    root=Path(root).resolve();run=Path(run).resolve()
    if not 1<=len(proposal_ids)<=3 or len(set(proposal_ids))!=len(proposal_ids):raise ValueError('distinct model proposals required')
    manifest=json.loads((run/'artifact_hashes.json').read_text())
    read=lambda name:json.loads(checked_artifact(run,name,manifest).read_text())
    status=read('status.json');admission=read('admission.json');config=read('config.json')
    comparisons=read('comparisons.json');numeric=config['numeric_protocol']
    if status.get('status')!='PASS' or status.get('qualification')!='SEALED' or status.get('lockbox')!='SEALED':
        raise ValueError('model result must be a completed sealed research run')
    snapshot=ledger.snapshot(campaign);proposals={p['id']:p for p in snapshot['proposals']}
    if not legacy:
        if not snapshot['freezes'] or not snapshot['model_runs']:raise ValueError('campaign model execution was not reserved')
        frozen=json.loads(snapshot['freezes'][0]['payload'])
        if set(frozen['selected'])!=set(proposal_ids):raise ValueError('model outcome must cover the frozen selection')
        for path,expected in frozen['protocols'].items():
            # The adapter is in each model snapshot; the underlying rolling protocol
            # is verified through its pinned digest in that adapter.
            if path=='configs/m3/increment.json' and sha(run/'source'/path)!=expected:
                raise ValueError('model adapter differs from campaign freeze')
            if path=='configs/factors/m2_rolling.json' and config['adapter_protocol']['rolling_protocol_sha256']!=expected:
                raise ValueError('model protocol differs from campaign freeze')
    expected_hypotheses=[ResearchHypothesis(**json.loads(proposals[p]['payload'])) for p in proposal_ids]
    if {h.hypothesis_id for h in expected_hypotheses}!={ResearchHypothesis(**h).hypothesis_id for h in admission['candidates']}:
        raise ValueError('model candidate set differs from requested proposals')
    registered={r['factor_id']:r['report'] for r in FactorRegistry(root/'data/factor_registry.sqlite').evaluations() if r['run_id']==run.name}
    rows=[]
    for proposal,h in zip(proposal_ids,expected_hypotheses):
        record=registered.get(h.factor().factor_id);result=comparisons['ADD_'+h.name]
        screen_run=admission.get('screen_by_hypothesis',{}).get(h.hypothesis_id,admission['screen_run'])
        if (record is None or record.get('model_increment')!=result or record.get('screen_run')!=screen_run
                or record.get('hypothesis_id')!=h.hypothesis_id or record.get('independent_alpha') is not False):
            raise ValueError('model result differs from numerical registry')
        rows.append((proposal,{'scope':'research_only','protected_accessed':False,'period':numeric['evaluation_period'],
                              'stage':'rolling_model','screen_run':screen_run,'model_run':run.name,
                              'decision':result['decision'],'comparison':result,'result_sha256':sha(run/'comparisons.json'),
                              'interpretation':'HISTORICAL_RESEARCH_ONLY; no independent alpha or protected-period admission'}))
    ledger.record_model_results(campaign,rows,run.name,'LEGACY_VERIFIED_IMPORT' if legacy else 'CAMPAIGN_MODEL')
    return ledger.snapshot(campaign)


def model_increment(root,ledger,campaign):
    root=Path(root).resolve();snapshot=ledger.snapshot(campaign)
    if not snapshot['freezes']:raise ValueError('freeze campaign before model execution')
    frozen=json.loads(snapshot['freezes'][0]['payload'])
    if not frozen['selected']:return {'decision':'NO_ENTRY','fits':0,'portfolios':0}
    for path,expected in frozen['protocols'].items():
        if sha(root/path)!=expected:raise ValueError('model protocol changed after campaign freeze')
    selected=frozen['selected'];proposals={p['id']:p for p in frozen['proposals']}
    evaluations={e['proposal']:e for e in frozen['evaluations']}
    screens=list(dict.fromkeys(root/'experiments/m3'/evaluations[p]['run_id'] for p in selected))
    hypotheses=[ResearchHypothesis(**json.loads(proposals[p]['payload'])).hypothesis_id for p in selected]
    ledger.reserve_model(campaign)
    try:
        result=increment_run(root,screens[0],selection=hypotheses,more_screens=screens[1:])
    except Exception as exc:
        ledger.fail_model(campaign,type(exc).__name__)
        raise
    attach_model(root,ledger,campaign,result,selected)
    return {'model_directory':str(result),'campaign':campaign}
