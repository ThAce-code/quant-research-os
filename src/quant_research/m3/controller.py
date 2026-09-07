"""Common campaign entry for imports, generated candidates and research feedback."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from .campaign import CampaignLedger, CampaignSpec
from .candidates import ResearchHypothesis
from .pipeline import sha, run as screen_run
from ..factors.engine import strict_write_json as write
from ..factors.registry import FactorRegistry
from ..m2.family_screen import checked_artifact


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
    if batch.get('screen_protocol_sha256')!=sha(screen/'screen_protocol.json'):
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
    output=screen_run(root,batch)
    attach_screen(root,ledger,campaign,output,proposal_ids)
    return output
