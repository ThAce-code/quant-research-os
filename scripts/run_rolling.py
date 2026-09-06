from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from quant_research.m2.rolling import run
if __name__=='__main__':run(Path(__file__).resolve().parents[1],Path(sys.argv[1]).resolve())
