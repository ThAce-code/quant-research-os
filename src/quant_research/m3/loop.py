"""Bounded generation/evaluation/refinement, replaying persisted work on restart."""
from dataclasses import asdict
import json
from filelock import FileLock
from .candidates import identity

from .controller import evaluate
from .generation import generate
from .trajectory import refine


def run_loop(root,ledger,campaign,endpoint,brief,example):
    lock=ledger.path.parent/('m3_loop_'+identity(campaign)[:16]+'.lock')
    with FileLock(str(lock),timeout=0):
        return _run_loop(root,ledger,campaign,endpoint,brief,example)


def _run_loop(root,ledger,campaign,endpoint,brief,example):
    """One deterministic campaign; never auto-retry unknown or failed executions.

    Up to two parents from the immediately preceding round are selected by lowest
    proposal ID, not by a performance ranking. Freeze/model admission are separate
    explicit stages after this finite search. No protected-period input is loaded.
    """
    ledger.bind_loop(campaign,{'endpoint':asdict(endpoint),'brief':brief,'example':example,
                               'policy':'previous_round_first_two_evaluated_ids_v1'})
    spec=json.loads(ledger.snapshot(campaign)['campaign']['spec'])
    for round_number in range(spec['max_rounds']):
        snapshot=ledger.snapshot(campaign)
        if snapshot['campaign']['state']!='OPEN':return {'state':'CAMPAIGN_CLOSED','campaign':campaign}
        if any(c['state']=='RESERVED' for c in snapshot['calls']):
            return {'state':'NEEDS_CALL_RECOVERY','campaign':campaign}
        if any(e['state']=='RESERVED' for e in snapshot['evaluations']):
            return {'state':'NEEDS_SCREEN_RECOVERY','campaign':campaign}
        if any(c['state'] in {'FAILED','OVERRUN'} for c in snapshot['calls']) or any(e['state']=='FAILED' for e in snapshot['evaluations']):
            return {'state':'STOPPED_EXECUTION_FAILURE','campaign':campaign}
        calls=[c for c in snapshot['calls'] if c['round']==round_number]
        for call in calls:ledger.materialize_call(campaign,call['id'])
        current=[p for p in ledger.snapshot(campaign)['proposals'] if p['round']==round_number]
        if not current and not calls:
            snapshot=ledger.snapshot(campaign)
            if len(snapshot['proposals'])>=spec['max_proposals'] or len(snapshot['calls'])>=spec['max_calls']:
                return {'state':'SEARCH_BUDGET_EXHAUSTED','campaign':campaign}
            if round_number==0:
                generate(ledger,campaign,round_number,endpoint,brief,example)
            else:
                completed=ledger.feedback(campaign)
                parents=[p['id'] for p in snapshot['proposals'] if p['round']==round_number-1 and p['id'] in completed][:2]
                if not parents:return {'state':'NO_EVALUATED_PARENTS','round':round_number,'campaign':campaign}
                refine(ledger,campaign,parents,endpoint,brief)
            current=[p for p in ledger.snapshot(campaign)['proposals'] if p['round']==round_number]
        snapshot=ledger.snapshot(campaign);reserved={e['proposal'] for e in snapshot['evaluations']}
        pending=[p['id'] for p in current if p['status']=='ACCEPTED' and p['id'] not in reserved]
        available=spec['max_evaluations']-len(reserved)
        if len(pending)>available:return {'state':'EVALUATION_BUDGET_EXHAUSTED','campaign':campaign,'pending':pending}
        for start in range(0,len(pending),3):evaluate(root,ledger,campaign,pending[start:start+3])
    return {'state':'SEARCH_COMPLETE','campaign':campaign,'rounds':spec['max_rounds'],
            'next':'freeze final selection before the separately budgeted model stage'}
