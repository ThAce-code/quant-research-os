"""Run one predeclared paper batch through the existing historical screen."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from quant_research.m3.pipeline import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=ROOT/'configs/m3/paper_pilot.json')
    args = parser.parse_args()
    print(run(ROOT, args.batch))
