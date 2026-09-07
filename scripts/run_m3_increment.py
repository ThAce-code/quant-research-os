"""Route a completed screen into survivor-only matched model/cost evaluation."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from quant_research.m3.increment import run
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('screen', type=Path)
    print(run(ROOT, parser.parse_args().screen))
