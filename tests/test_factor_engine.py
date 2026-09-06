import json
import hashlib
import sqlite3
import sys
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest

from quant_research.factors.engine import audit_causality, strict_write_json, validate_config
from quant_research.factors.expressions import Expression


def test_runtime_causality_probe_rejects_future_dependent_calculation():
    close=pd.DataFrame({'A':[1.,2.,4.,8.,16.]},index=pd.bdate_range('2020-01-01',periods=5))
    assert audit_causality(Expression('Mean(close,2)'),{'close':close},close.notna(),close.index[2])['status']=='PASS'
    class FutureExpression:
        lookback=0
        def evaluate(self, fields, membership=None):
            return fields['close'].shift(-1)
    with pytest.raises(ValueError,match='causality'):
        audit_causality(FutureExpression(),{'close':close},close.notna(),close.index[2])


def test_report_json_has_real_nulls_for_unavailable_statistics(tmp_path):
    path=tmp_path/'report.json'
    strict_write_json(path,{'x':np.nan,'n':np.int64(10),'stat':None})
    assert json.loads(path.read_text())=={'x':None,'n':10,'stat':None}
    assert 'NaN' not in path.read_text()


def test_run_config_rejects_unsupported_universe_and_incomplete_decay():
    config={'name':'demo','universe':'csi300','horizon':5,'decay_horizons':[1,2,5,10,20], 'min_pairs':30}
    validate_config(config)
    with pytest.raises(ValueError):validate_config({**config,'universe':'current_csi300'})
    with pytest.raises(ValueError):validate_config({**config,'horizon':3})


def failure_probe_engine(tmp_path, monkeypatch, init_error=None):
    """Keep causal calculations and SQLite real; isolate external data and Qlib."""
    from quant_research.factors import engine as engine_module
    from quant_research.factors.data import FactorData

    dates = pd.bdate_range('2020-01-01', periods=90)
    t = np.arange(len(dates), dtype=float)
    close = pd.DataFrame({
        'A': 10 + .1 * t, 'B': 20 + .01 * t ** 2,
        'C': 30 + np.sin(t / 5) + .05 * t,
    }, index=dates)
    data = FactorData(
        {'close': close, 'returns': close.pct_change(fill_method=None),
         'turnover': close / 1000},
        close.notna(), close.notna(), close.mean(axis=1),
    )
    segments = {
        name: [str(dates[start].date()), str(dates[end].date())]
        for name, start, end in [('train', 0, 29), ('valid', 30, 59), ('test', 60, 89)]
    }
    (tmp_path / 'baseline.json').write_text(json.dumps({
        'name': 'local_fixture', 'segments': segments, 'backtest': {},
    }), encoding='utf-8')
    config = {
        'name': 'failure_probe', 'universe': 'csi300', 'horizon': 5,
        'decay_horizons': [1, 2, 5, 10, 20], 'min_pairs': 3,
        'baseline_id': 'frozen_fixture', 'baseline_config': 'baseline.json',
        'rules': {'min_coverage': .7, 'min_days': 100, 'min_rank_ic': .01,
                  'min_positive_ratio': .5, 'max_pool_corr': .9},
    }
    monkeypatch.setattr(engine_module, 'load_factor_data', lambda root, baseline: data)
    manifest=tmp_path/'data/canonical/local_fixture/manifest.json'
    manifest.parent.mkdir(parents=True);manifest.write_text('{"fixture":true}',encoding='utf-8')
    source_hash=hashlib.sha256(manifest.read_bytes()).hexdigest()
    for name in ['scripts/run_factors.py','run-factors.ps1']:
        source=tmp_path/name;source.parent.mkdir(parents=True,exist_ok=True);source.write_text('fixture')
    monkeypatch.setattr(engine_module, 'verify_baseline', lambda root, baseline_id: {
        'original_provenance': {'qlib_files_sha256': {}, 'source_manifest_sha256': source_hash},
    })

    def init(**kwargs):
        if init_error is not None:
            raise RuntimeError(init_error)

    monkeypatch.setitem(sys.modules, 'qlib', SimpleNamespace(init=init))
    return engine_module.FactorEngine(tmp_path, config)


def probe_definitions():
    return [
        {'name': 'FIRST', 'family': 'fixture', 'expression': 'close',
         'hypothesis': 'Synthetic persistence fixture'},
        {'name': 'SECOND', 'family': 'fixture', 'expression': '-close',
         'hypothesis': 'Synthetic persistence fixture'},
    ]


def saved_trials(tmp_path):
    with sqlite3.connect(tmp_path / 'data/factor_registry.sqlite') as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute('''
            SELECT f.name, e.factor_id, e.status, e.error, e.report_json
            FROM evaluations AS e JOIN factors AS f ON f.factor_id = e.factor_id
            ORDER BY e.evaluation_id
        ''')]


def failed_run_state(tmp_path):
    status = next((tmp_path / 'experiments/factor_engine/failure_probe').glob('*/status.json'))
    return json.loads(status.read_text(encoding='utf-8'))


def test_global_qlib_init_failure_persists_every_registered_trial(tmp_path, monkeypatch):
    engine = failure_probe_engine(tmp_path, monkeypatch, 'controlled qlib init failure')

    with pytest.raises(RuntimeError, match='controlled qlib init failure'):
        engine._run(probe_definitions())

    saved = saved_trials(tmp_path)
    assert {row['name']: row['status'] for row in saved} == {'FIRST': 'FAILED', 'SECOND': 'FAILED'}
    assert len(saved) == 2
    assert all(row['error'] == 'RuntimeError: controlled qlib init failure' for row in saved)
    assert all(json.loads(row['report_json'])['status'] == 'FAILED' for row in saved)
    assert failed_run_state(tmp_path)['status'] == 'FAILED'
    assert len(list((tmp_path/'experiments/factor_engine/failure_probe').glob('*/source/scripts/run_factors.py')))==1


def test_frozen_manifest_is_checked_before_panel_loading(tmp_path,monkeypatch):
    from quant_research.factors import engine as module
    engine=failure_probe_engine(tmp_path,monkeypatch,'should not reach qlib')
    (tmp_path/'data/canonical/local_fixture/manifest.json').write_text('{"fixture":false}')
    def unexpected_load(*args):
        raise AssertionError('unfrozen panels loaded')
    monkeypatch.setattr(module,'load_factor_data',unexpected_load)
    with pytest.raises(ValueError,match='frozen'):
        engine._run(probe_definitions())


def test_global_failure_does_not_duplicate_precalculation_failure(tmp_path, monkeypatch):
    engine = failure_probe_engine(tmp_path, monkeypatch, 'controlled qlib init failure')
    definitions = probe_definitions()
    definitions[0]['expression'] = 'Ref(close,-1)'

    with pytest.raises(RuntimeError, match='controlled qlib init failure'):
        engine._run(definitions)

    saved = saved_trials(tmp_path)
    assert len(saved) == 2
    by_name = {row['name']: row for row in saved}
    assert by_name['FIRST']['status'] == 'FAILED'
    assert 'ValueError:' in by_name['FIRST']['error']
    assert 'qlib init' not in by_name['FIRST']['error']
    assert by_name['SECOND']['error'] == 'RuntimeError: controlled qlib init failure'


def test_global_cleanup_preserves_completed_and_failed_trials(tmp_path, monkeypatch):
    from quant_research.factors import portfolio, report

    engine = failure_probe_engine(tmp_path, monkeypatch)

    def portfolios(scores, start, end, backtest, output, expected_dates):
        if output.parent.name == 'SECOND':
            raise RuntimeError('controlled portfolio failure')
        return {'top20': {'net_excess_annual': .01}}

    def run_report(*args):
        raise RuntimeError('controlled run report failure')

    monkeypatch.setattr(portfolio, 'run_portfolios', portfolios)
    monkeypatch.setattr(report, 'write_factor_report', lambda *args: None)
    monkeypatch.setattr(report, 'write_run_report', run_report)

    with pytest.raises(RuntimeError, match='controlled run report failure'):
        engine._run(probe_definitions())

    saved = saved_trials(tmp_path)
    assert [(row['name'], row['status']) for row in saved] == [('FIRST', 'REJECT'), ('SECOND', 'FAILED')]
    assert saved[0]['error'] is None
    assert saved[1]['error'] == 'RuntimeError: controlled portfolio failure'
    assert failed_run_state(tmp_path)['error'] == 'RuntimeError: controlled run report failure'


@pytest.mark.parametrize('failure_stage', ['init', 'portfolio'])
def test_registry_failure_preserves_primary_error_and_other_pending_trials(tmp_path, monkeypatch, failure_stage):
    from quant_research.factors import portfolio
    from quant_research.factors.expressions import FactorDefinition
    from quant_research.factors.registry import FactorRegistry

    primary_error = f'controlled {failure_stage} failure'
    engine = failure_probe_engine(tmp_path, monkeypatch, primary_error if failure_stage == 'init' else None)
    definitions = probe_definitions()
    first_id = FactorDefinition(**definitions[0]).factor_id
    record_failure = FactorRegistry.record_failure

    def fail_first_write(self, run_id, factor_id, error):
        if factor_id == first_id:
            raise sqlite3.OperationalError('controlled registry write failure')
        return record_failure(self, run_id, factor_id, error)

    def fail_portfolio(*args):
        raise RuntimeError(primary_error)

    monkeypatch.setattr(FactorRegistry, 'record_failure', fail_first_write)
    monkeypatch.setattr(portfolio, 'run_portfolios', fail_portfolio)

    with pytest.raises(RuntimeError, match=primary_error):
        engine._run(definitions)

    saved = saved_trials(tmp_path)
    assert [(row['name'], row['status']) for row in saved] == [('SECOND', 'FAILED')]
    assert saved[0]['error'] == f'RuntimeError: {primary_error}'
    state = failed_run_state(tmp_path)
    assert state['error'] == f'RuntimeError: {primary_error}'
    assert any(error['factor_id'] == first_id and 'controlled registry write failure' in error['error']
               for error in state['registry_errors'])
