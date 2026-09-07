"""Run one predeclared paper batch through the existing historical screen."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from quant_research.m3.pipeline import run
from quant_research.m3.increment import run as run_increment

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=ROOT/'configs/m3/paper_pilot.json')
    parser.add_argument('--resume-screen', type=Path, help='Route an existing completed screen without rescreening')
    parser.add_argument('--screen-only', action='store_true', help='Stop after historical screening')
    args = parser.parse_args()
    screen = args.resume_screen or run(ROOT, args.batch)
    print(screen)
    if not args.screen_only:
        print(run_increment(ROOT, screen))
