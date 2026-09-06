"""Standalone resumable data preparation; run_baseline.py also calls this."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from quant_research.baostock_data import prepare_data
from quant_research.qlib_export import export_dataset

if __name__ == '__main__':
    config = json.loads((ROOT / 'configs/experiments/baostock_alpha158.json').read_text())
    canonical = prepare_data(ROOT, config)
    output = export_dataset(canonical, ROOT / 'data/qlib' / config['name'])
    print(f'DATA_READY {output}', flush=True)
