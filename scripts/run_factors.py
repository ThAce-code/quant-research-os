"""Evaluate M1 factors with sealed BaoStock data and append research trials."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_research.factors.engine import FactorEngine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/factors/m1.json')
    parser.add_argument('--factor',help='One configured factor name; omit to run all')
    args=parser.parse_args()
    engine=FactorEngine(ROOT,args.config)
    definitions=None
    if args.factor:
        definitions=[f for f in engine.config['factors'] if f['name']==args.factor]
        if not definitions: parser.error('unknown factor name')
    reports=engine.run(definitions)
    for report in reports:
        print(f'{report.factor["name"]}: {report.status} {report.artifact_directory}',flush=True)


if __name__=='__main__':
    main()
