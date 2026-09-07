"""Deterministic research-memory retrieval and explicit parent-linked refinement.

Outcomes remain exploratory. Retrieval never ranks by profitability and never
consults qualification or lockbox stores. A rejected parent's record is immutable;
mutation and crossover create new attempts against the original campaign budget.
"""
import json
import re

from .generation import generate


def retrieve(ledger, campaign, query='', limit=10):
    if not isinstance(query,str) or len(query)>2000 or type(limit) is not int or not 1<=limit<=50:
        raise ValueError('invalid memory query or limit')
    snapshot=ledger.snapshot(campaign)
    stage_feedback=ledger.feedback(campaign)
    outcomes={e['proposal']:e for e in snapshot['evaluations'] if e['state']=='COMPLETE'}
    terms=set(re.findall(r'\w+',query.casefold()))
    records=[]
    for proposal in snapshot['proposals']:
        outcome=outcomes.get(proposal['id'])
        if outcome is None:continue
        evidence=stage_feedback[proposal['id']]
        if evidence.get('scope')!='research_only' or evidence.get('protected_accessed') is not False:
            raise ValueError('non-research evidence in trajectory memory')
        spec=json.loads(snapshot['campaign']['spec'])
        start,end=evidence['period']
        if not spec['research_period'][0]<=start<=end<=spec['research_period'][1] or end>='2021-01-01':
            raise ValueError('protected or out-of-campaign trajectory')
        hypothesis=json.loads(proposal['payload'])
        document=' '.join(str(hypothesis.get(k,'')) for k in ('name','family','hypothesis','economic_rationale','expression'))
        score=len(terms & set(re.findall(r'\w+',document.casefold())))
        if terms and not score:continue
        records.append({'proposal_id':proposal['id'],'round':proposal['round'],
                        'parents':json.loads(proposal['parents']),'hypothesis':hypothesis,
                        'evidence':evidence,'run_id':outcome['run_id'],'relevance':score})
    return sorted(records,key=lambda r:(-r['relevance'],r['proposal_id']))[:limit]


def refine(ledger,campaign,parents,endpoint,brief):
    if not 1<=len(parents)<=2 or len(set(parents))!=len(parents):
        raise ValueError('refinement requires one mutation parent or two crossover parents')
    # Read all admitted outcomes, not the top-N search results.
    snapshot=ledger.snapshot(campaign)
    proposals={p['id']:p for p in snapshot['proposals']}
    outcomes=ledger.feedback(campaign)
    if any(p not in proposals or p not in outcomes for p in parents):
        raise ValueError('all parents need completed research evaluations')
    round_number=1+max(proposals[p]['round'] for p in parents)
    feedback={str(p):outcomes[p] for p in parents}
    example=json.loads(proposals[parents[0]]['payload'])
    operation='mutation' if len(parents)==1 else 'crossover'
    return generate(ledger,campaign,round_number,endpoint,
        f'Research-only {operation}. Preserve parent records; explain the new economic hypothesis. '+brief,
        example,parents,feedback)
