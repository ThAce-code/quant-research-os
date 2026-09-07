"""Unified bounded research campaigns. JSON input is data, never executable code."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.m3.campaign import CampaignLedger
from quant_research.m3.controller import (create_campaign,import_candidates,evaluate,attach_screen,
                                        freeze_campaign,model_increment,attach_model)
from quant_research.m3.generation import ModelEndpoint,generate
from quant_research.m3.trajectory import retrieve,refine
from quant_research.m3.loop import run_loop
from quant_research.m3.external import import_export
from quant_research.m3.auditor import audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    create=sub.add_parser('create');create.add_argument('spec',type=Path)
    show=sub.add_parser('status');show.add_argument('campaign')
    imp=sub.add_parser('import');imp.add_argument('campaign');imp.add_argument('file',type=Path)
    imp.add_argument('--source-type',required=True);imp.add_argument('--round',type=int,default=0)
    gen=sub.add_parser('generate');gen.add_argument('campaign');gen.add_argument('endpoint',type=Path)
    gen.add_argument('brief',type=Path);gen.add_argument('--round',type=int,default=0)
    gen.add_argument('--example',type=Path,default=ROOT/'configs/m3/paper_pilot.json')
    ev=sub.add_parser('evaluate');ev.add_argument('campaign');ev.add_argument('proposals',nargs='+',type=int)
    attach=sub.add_parser('attach-screen');attach.add_argument('campaign');attach.add_argument('screen',type=Path)
    attach.add_argument('proposals',nargs='+',type=int)
    replay=sub.add_parser('recover-call');replay.add_argument('campaign');replay.add_argument('ticket',type=int)
    memory=sub.add_parser('memory');memory.add_argument('campaign');memory.add_argument('--query',default='')
    memory.add_argument('--limit',type=int,default=10)
    improve=sub.add_parser('refine');improve.add_argument('campaign');improve.add_argument('endpoint',type=Path)
    improve.add_argument('brief',type=Path);improve.add_argument('parents',type=int,nargs='+')
    freeze=sub.add_parser('freeze');freeze.add_argument('campaign');freeze.add_argument('proposals',type=int,nargs='*')
    model=sub.add_parser('model');model.add_argument('campaign')
    model_attach=sub.add_parser('attach-model');model_attach.add_argument('campaign');model_attach.add_argument('run',type=Path)
    model_attach.add_argument('proposals',type=int,nargs='+');model_attach.add_argument('--legacy',action='store_true')
    loop=sub.add_parser('loop');loop.add_argument('campaign');loop.add_argument('endpoint',type=Path)
    loop.add_argument('brief',type=Path);loop.add_argument('--example',type=Path,default=ROOT/'configs/m3/paper_pilot.json')
    external=sub.add_parser('import-search');external.add_argument('campaign');external.add_argument('source',choices=['alphaforge','alphasage'])
    external.add_argument('asset',type=Path);external.add_argument('manifest',type=Path);external.add_argument('annotations',type=Path)
    external.add_argument('--round',type=int,default=0)
    review=sub.add_parser('audit');review.add_argument('campaign');review.add_argument('endpoint',type=Path)
    review.add_argument('--audit-id',default='review_v1')
    args=parser.parse_args()
    if args.command=='audit':
        result=audit(ROOT,args.campaign,ModelEndpoint(**json.loads(args.endpoint.read_text(encoding='utf-8'))),args.audit_id)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));return
    ledger=CampaignLedger(ROOT/'data/m3_campaigns.sqlite')
    if args.command=='create':
        _,spec,seed=create_campaign(ROOT,args.spec);result={'campaign':asdict(spec),'seed_audit':seed}
    elif args.command=='status':result=ledger.snapshot(args.campaign)
    elif args.command=='import':result=import_candidates(ledger,args.campaign,args.round,args.file,args.source_type)
    elif args.command=='evaluate':result={'screen_directory':str(evaluate(ROOT,ledger,args.campaign,args.proposals))}
    elif args.command=='attach-screen':result=attach_screen(ROOT,ledger,args.campaign,args.screen,args.proposals)
    elif args.command=='recover-call':result=ledger.materialize_call(args.campaign,args.ticket)
    elif args.command=='freeze':result=freeze_campaign(ROOT,ledger,args.campaign,args.proposals)
    elif args.command=='model':result=model_increment(ROOT,ledger,args.campaign)
    elif args.command=='attach-model':result=attach_model(ROOT,ledger,args.campaign,args.run,args.proposals,args.legacy)
    elif args.command=='import-search':result=import_export(ledger,args.campaign,args.round,args.source,args.asset,
        json.loads(args.manifest.read_text(encoding='utf-8')),json.loads(args.annotations.read_text(encoding='utf-8')))
    elif args.command=='memory':result=retrieve(ledger,args.campaign,args.query,args.limit)
    elif args.command=='refine':result=refine(ledger,args.campaign,args.parents,
        ModelEndpoint(**json.loads(args.endpoint.read_text(encoding='utf-8'))),args.brief.read_text(encoding='utf-8'))
    elif args.command=='loop':result=run_loop(ROOT,ledger,args.campaign,
        ModelEndpoint(**json.loads(args.endpoint.read_text(encoding='utf-8'))),args.brief.read_text(encoding='utf-8'),
        json.loads(args.example.read_text(encoding='utf-8'))['candidates'][0])
    else:
        endpoint=ModelEndpoint(**json.loads(args.endpoint.read_text(encoding='utf-8')))
        example=json.loads(args.example.read_text(encoding='utf-8'))['candidates'][0]
        result=generate(ledger,args.campaign,args.round,endpoint,args.brief.read_text(encoding='utf-8'),example)
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':main()
