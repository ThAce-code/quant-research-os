"""Run the frozen R1 study in explicit resumable stages, without new search budgets."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.r1.workflow import prepare,screen


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['prepare','screen','model']);p.add_argument('--inputs',type=Path)
    args=p.parse_args()
    if args.stage!='prepare' and args.inputs is None:p.error('--inputs is required for screen/model')
    if args.stage=='prepare':out=prepare(ROOT)
    elif args.stage=='screen':out=screen(ROOT,args.inputs)
    else:
        from quant_research.r1.models import run
        out=run(ROOT,args.inputs)
    print('R1_OUTPUT '+str(out),flush=True)
