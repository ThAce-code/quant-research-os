"""The first Qlib experiment, with train/validation labels purged at boundaries."""
from copy import deepcopy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

from .baostock_data import write_json


def purged_segments(segments, calendar):
    result = {key: list(value) for key, value in segments.items()}
    for key in ['train', 'valid']:
        dates = calendar[(calendar >= pd.Timestamp(segments[key][0])) & (calendar <= pd.Timestamp(segments[key][1]))]
        if len(dates) < 3:
            raise ValueError(f'{key} must have at least 3 trading dates')
        result[key][1] = dates[-3].strftime('%Y-%m-%d')
    return result


def validate_outputs(predictions, labels, report, expected_dates):
    if predictions.empty or predictions.index.has_duplicates or labels.empty:
        raise ValueError('empty or duplicated predictions/labels')
    if not np.isfinite(predictions.to_numpy()).all():
        raise ValueError('nonfinite predictions')
    if not predictions.index.equals(labels.index):
        raise ValueError('prediction/label index alignment mismatch')
    pred_dates = pd.DatetimeIndex(predictions.index.get_level_values('datetime').unique()).sort_values()
    if not pred_dates.equals(pd.DatetimeIndex(expected_dates)):
        raise ValueError('prediction date coverage mismatch')
    if not pd.DatetimeIndex(report.index).equals(pd.DatetimeIndex(expected_dates)):
        raise ValueError('backtest date coverage mismatch')
    values = report[['return', 'bench', 'cost', 'turnover']]
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError('nonfinite backtest values')
    if report.cost.lt(0).any() or not report.turnover.gt(0).any():
        raise ValueError('invalid costs or no trades')
    if not report.loc[report.turnover.gt(0), 'cost'].gt(0).all():
        raise ValueError('trading days must incur positive costs')
    valid_labels = labels.dropna()
    label_dates = pd.DatetimeIndex(valid_labels.index.get_level_values('datetime').unique()).sort_values()
    if not label_dates.equals(pd.DatetimeIndex(expected_dates)) or not np.isfinite(valid_labels.to_numpy()).all():
        raise ValueError('usable label coverage mismatch')


def run_experiment(root, config, output):
    # Optional neural model imports from Qlib are intentionally not dependencies.
    import qlib
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.contrib.evaluate import risk_analysis
    from qlib.data import D
    from qlib.data.dataset import DatasetH
    from qlib.workflow import R
    from qlib.workflow.record_temp import SignalRecord, SigAnaRecord, PortAnaRecord

    root, output = Path(root), Path(output)
    provider = root / 'data/qlib' / config['name']
    canonical = root / 'data/canonical' / config['name']
    calendar = pd.DatetimeIndex(pd.read_parquet(canonical / 'calendar.parquet').datetime)
    segments = purged_segments(config['segments'], calendar)
    mlruns = root / 'experiments/mlruns'
    mlruns.mkdir(parents=True, exist_ok=True)
    os.environ['MLFLOW_ALLOW_FILE_STORE'] = 'true'
    qlib.init(provider_uri=str(provider), region='cn', kernels=8,
              expression_cache=None, dataset_cache=None,
              exp_manager={'class': 'MLflowExpManager', 'module_path': 'qlib.workflow.expm',
                           'kwargs': {'uri': mlruns.as_uri(), 'default_exp_name': config['name']}})
    # Verify that real BaoStock prices survive the Qlib binary reader.
    check = D.features(['SH600000'], ['$close', '$factor', '$volume', '$vwap'],
                       start_time='2017-05-24', end_time='2017-05-25')
    raw = pd.read_parquet(canonical / 'SH600000.parquet').set_index('datetime')
    for (_, day), row in check.iterrows():
        if not np.isclose(row['$close'] / row['$factor'], raw.loc[day, 'close'], rtol=1e-5):
            raise ValueError('Qlib raw-price roundtrip failed')
        if not np.isclose(row['$volume'] * row['$vwap'], raw.loc[day, 'amount'], rtol=1e-5):
            raise ValueError('Qlib price-volume accounting identity failed')
    if len(check) != 2:
        raise ValueError('missing Qlib roundtrip probe dates')
    check.to_csv(output / 'qlib_roundtrip.csv')
    task_config = {**deepcopy(config), 'effective_segments': segments, 'provider_uri': str(provider),
                   'label': 'Ref($close, -2)/Ref($close, -1) - 1',
                   'qlib_annualization': {'days': 238, 'accumulation': 'sum'},
                   'purge_label_horizon': 2}
    write_json(output / 'effective_config.json', task_config)
    print('ALPHA158 loading historical CSI300 features', flush=True)
    handler = Alpha158(instruments='csi300', start_time=segments['train'][0],
                       end_time=segments['test'][1], fit_start_time=segments['train'][0],
                       fit_end_time=segments['train'][1])
    dataset = DatasetH(handler=handler, segments=segments)
    segment_stats = {}
    for name in segments:
        frame = dataset.prepare(name, col_set=['feature', 'label'], data_key='learn')
        segment_stats[name] = {'rows': len(frame), 'features': len(frame['feature'].columns),
                               'dates': frame.index.get_level_values('datetime').nunique(),
                               'feature_nan_fraction': float(frame['feature'].isna().mean().mean())}
        if not len(frame) or len(frame['feature'].columns) != 158:
            raise ValueError(f'invalid Alpha158 segment {name}: {segment_stats[name]}')
    write_json(output / 'segment_stats.json', segment_stats)
    with R.start(experiment_name=config['name'], recorder_name=output.name):
        recorder = R.get_recorder()
        recorder.log_params(data_provider='baostock', seed=config['model']['seed'], label_purge=2)
        model = LGBModel(**config['model'])
        print('LIGHTGBM training', flush=True)
        model.fit(dataset)
        model.model.save_model(str(output / 'model.txt'))
        recorder.save_objects(**{'model.pkl': model})
        SignalRecord(model=model, dataset=dataset, recorder=recorder).generate()
        SigAnaRecord(recorder=recorder, ana_long_short=False, ann_scaler=252).generate()
        portfolio_config = {
            'strategy': {'class': 'TopkDropoutStrategy', 'module_path': 'qlib.contrib.strategy',
                         'kwargs': {'signal': '<PRED>', **config['strategy']}},
            'backtest': {**deepcopy(config['backtest']), 'start_time': segments['test'][0],
                         'end_time': segments['test'][1]}}
        print('TOP50 backtest with transaction costs', flush=True)
        PortAnaRecord(recorder=recorder, config=portfolio_config).generate()
        pred = recorder.load_object('pred.pkl')
        labels = recorder.load_object('label.pkl')
        report = recorder.load_object('portfolio_analysis/report_normal_1day.pkl')
        ic = recorder.load_object('sig_analysis/ic.pkl')
        ric = recorder.load_object('sig_analysis/ric.pkl')
        expected = calendar[(calendar >= pd.Timestamp(segments['test'][0])) & (calendar <= pd.Timestamp(segments['test'][1]))]
        validate_outputs(pred, labels, report, expected)
        pred.to_parquet(output / 'predictions.parquet')
        labels.to_parquet(output / 'labels.parquet')
        report.to_csv(output / 'daily_backtest.csv')
        daily_ic = pd.DataFrame({'IC': ic, 'RankIC': ric,
                                 'valid_labels': labels.dropna().groupby(level='datetime').size()})
        daily_ic.to_csv(output / 'daily_ic.csv')
        daily_ic.groupby(daily_ic.index.year).agg(['mean', 'std', 'count']).to_csv(output / 'annual_ic.csv')
        analyses = {
            'benchmark': risk_analysis(report.bench, freq='day')['risk'].to_dict(),
            'excess_gross': risk_analysis(report['return'] - report.bench, freq='day')['risk'].to_dict(),
            'excess_net': risk_analysis(report['return'] - report.bench - report.cost, freq='day')['risk'].to_dict(),
            'strategy_net_compound': risk_analysis(report['return'] - report.cost, freq='day', mode='product')['risk'].to_dict()}
        signal_metrics = {k: float(v) for k, v in recorder.list_metrics().items()
                          if k in ['IC', 'ICIR', 'Rank IC', 'Rank ICIR']}
        metrics = {'signal': signal_metrics, 'portfolio': analyses,
                   'best_iteration': model.model.best_iteration,
                   'test_days': len(report), 'prediction_rows': len(pred),
                   'mean_daily_turnover': float(report.turnover.mean()),
                   'annualized_cost_drag': float(report.cost.mean() * 238),
                   'recorder_id': recorder.id, 'experiment_id': recorder.experiment_id}
        if len(signal_metrics) != 4 or not np.isfinite(list(signal_metrics.values())).all():
            raise ValueError('incomplete or nonfinite signal metrics')
    source_manifest = canonical / 'manifest.json'
    versions = {name: importlib.metadata.version(name) for name in ['baostock', 'pyqlib', 'lightgbm', 'pandas', 'pyarrow', 'numpy', 'mlflow', 'filelock', 'matplotlib']}
    import subprocess
    qlib_revision = subprocess.run(['git', '-C', str(root / 'vendor/qlib'), 'rev-parse', 'HEAD'],
                                   capture_output=True, text=True, check=True).stdout.strip()
    sources = list((root / 'src/quant_research').glob('*.py')) + [root / 'scripts/run_baseline.py']
    from .integrity import file_hashes
    import shutil
    shutil.copy2(source_manifest, output / 'data_manifest.json')
    write_json(output / 'provenance.json', {'versions': versions, 'qlib_revision': qlib_revision,
               'source_manifest': str(source_manifest),
               'source_manifest_sha256': hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
               'source_code_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
               'qlib_files_sha256': file_hashes(provider, '**/*')})
    from .reporting import write_report
    write_report(output, metrics, json.loads(source_manifest.read_text(encoding='utf-8')), segment_stats)
    write_json(output / 'metrics.json', metrics)
    return metrics
