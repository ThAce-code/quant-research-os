"""One-command real-data reproduction. All paths are relative to project root."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from quant_research.baostock_data import prepare_data, write_json
from quant_research.qlib_export import export_dataset
from quant_research.baseline import run_experiment
from quant_research.integrity import verify_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiments/baostock_alpha158.json')
    parser.add_argument('--skip-download', action='store_true', help='Require already prepared canonical data and export it again')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = ROOT / 'experiments' / config['name'] / run_id
    output.mkdir(parents=True)
    state = {'run_id': run_id, 'status': 'RUNNING', 'stage': 'data', 'started_at': datetime.now(timezone.utc).isoformat()}
    write_json(output / 'status.json', state)
    print(f'RUN_DIRECTORY {output}', flush=True)
    try:
        canonical = ROOT / 'data/canonical' / config['name']
        if args.skip_download:
            if not (canonical / 'manifest.json').exists():
                raise ValueError('No completed canonical dataset; run without --skip-download first')
        else:
            canonical = prepare_data(ROOT, config)
        manifest = verify_dataset(canonical, config)
        if manifest.get('raw_to_canonical_audit', {}).get('status') != 'PASS':
            raise ValueError('Raw to canonical audit is required before training')
        export_dataset(canonical, ROOT / 'data/qlib' / config['name'])
        state['stage'] = 'experiment'
        write_json(output / 'status.json', state)
        metrics = run_experiment(ROOT, config, output)
        state.update(status='PASS', stage='complete', ended_at=datetime.now(timezone.utc).isoformat())
        write_json(output / 'status.json', state)
        write_json(ROOT / 'experiments' / config['name'] / 'latest.json', {'run_directory': str(output), **state})
        print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
        print(f'REPORT {output / "report.md"}', flush=True)
    except Exception as exc:
        state.update(status='FAILED', error=f'{type(exc).__name__}: {exc}', ended_at=datetime.now(timezone.utc).isoformat())
        write_json(output / 'status.json', state)
        (output / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
