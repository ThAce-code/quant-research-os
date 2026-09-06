"""Registry contracts exercised against real, reopened SQLite databases."""
from dataclasses import asdict
import json
import sqlite3

import pytest

from quant_research.factors.expressions import FactorDefinition


def registry(path):
    # Import at call time so an absent implementation fails each behavior test.
    from quant_research.factors.registry import FactorRegistry
    return FactorRegistry(path)


def definition(**changes):
    fields = asdict(FactorDefinition(
        'MOM_20', 'momentum', 'close / Ref(close, 20) - 1',
        'A predeclared momentum hypothesis',
    ))
    return fields | changes


def rows(path, table):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(f'SELECT * FROM {table}')]


def complete_report():
    return {
        'status': 'REJECT',
        'reasons': ['validation_gate:net_excess_annual'],
        'config': {'segments': {
            'train': ['2008-01-01', '2014-12-31'],
            'valid': ['2015-01-01', '2016-12-31'],
            'test': ['2017-01-01', '2020-08-01'],
        }},
        'splits': {
            'valid': {
                'primary': {'ic': 0.01, 'rank_ic': 0.02,
                            'icir': 0.03, 'rank_icir': 0.04},
                'portfolio': {'top20': {
                    'mean_turnover': 0.15, 'net_excess_annual': -0.07,
                    'net_excess_ir': -0.8, 'net_mdd': -0.3,
                }},
                'decay': {'5': {'ic': 0.11}, '10': {'ic': 0.12},
                          '20': {'ic': 0.13}},
                'corr_max': 0.7, 'corr_existing_pool': None,
                'exposures': {'size': {'value': None, 'reason': 'No PIT observations'}},
            },
            'test': {'primary': {'ic': 0.9}, 'unrecognized_detail': ['保留', None]},
        },
    }


def test_registration_survives_reopen_and_exact_repeat_is_idempotent(tmp_path):
    path = tmp_path / 'nested' / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    registry(path).register('factor-1', dict(reversed(list(definition().items()))))

    saved = rows(path, 'factors')
    assert len(saved) == 1
    assert saved[0]['factor_id'] == 'factor-1'
    assert saved[0]['name'] == 'MOM_20'
    assert saved[0]['version'] == 1
    assert saved[0]['paper'] is None
    assert json.loads(saved[0]['definition_json']) == definition()


@pytest.mark.parametrize('changes', [
    {'expression': 'close / Ref(close, 21) - 1'},
    {'hypothesis': 'A different hypothesis'},
    {'direction': -1},
    {'source': 'changed_source'},
])
def test_changed_definition_cannot_reuse_id_or_name_version(tmp_path, changes):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())

    with pytest.raises(ValueError, match='immutable'):
        store.register('factor-1', definition(**changes))
    with pytest.raises(ValueError, match='version'):
        store.register('factor-2', definition(**changes))

    assert len(rows(path, 'factors')) == 1
    assert json.loads(rows(path, 'factors')[0]['definition_json']) == definition()


def test_bumped_version_preserves_both_definitions(tmp_path):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    revised = definition(version=2, expression='close / Ref(close, 21) - 1')
    with pytest.raises(ValueError, match='immutable'):
        store.register('factor-1', revised)
    store.register('factor-2', revised)

    assert [row['version'] for row in rows(path, 'factors')] == [1, 2]
    assert [json.loads(row['definition_json']) for row in rows(path, 'factors')] == [definition(), revised]


def test_rejected_and_failed_trials_survive_repeated_runs(tmp_path):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    report = complete_report()
    store.record('run-1', 'factor-1', report)
    store.record_failure('run-2', 'factor-1', 'Portfolio output was incomplete')
    store.record('run-3', 'factor-1', {'status': 'FORWARD', 'reasons': ['missing_size']})

    saved = rows(path, 'evaluations')
    assert [row['status'] for row in saved] == ['REJECT', 'FAILED', 'FORWARD']
    assert json.loads(saved[0]['report_json']) == report
    failure = json.loads(saved[1]['report_json'])
    assert failure['status'] == 'FAILED'
    assert failure['error'] == 'Portfolio output was incomplete'
    assert saved[1]['error'] == 'Portfolio output was incomplete'
    readback = registry(path).evaluations()
    assert [row['run_id'] for row in readback] == ['run-1', 'run-2', 'run-3']
    assert readback[0]['report'] == report


def test_each_run_factor_pair_is_immutable_but_batch_run_is_allowed(tmp_path):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    store.register('factor-2', definition(name='MOM_60', expression='close / Ref(close, 60) - 1'))
    original = {'status': 'REJECT', 'reasons': ['low_ic']}
    store.record('run-1', 'factor-1', original)
    store.record('run-1', 'factor-2', {'status': 'FORWARD'})

    with pytest.raises(ValueError, match='immutable'):
        store.record('run-1', 'factor-1', {'status': 'KEEP'})
    with pytest.raises(ValueError, match='immutable'):
        store.record_failure('run-1', 'factor-1', 'Later failure')

    saved = rows(path, 'evaluations')
    assert len(saved) == 2
    assert json.loads(saved[0]['report_json']) == original


def test_validation_scalars_and_split_dates_are_queryable_without_losing_json(tmp_path):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    report = complete_report()
    store.record('run-1', 'factor-1', report)

    saved = rows(path, 'evaluations')[0]
    expected = {
        'valid_ic': 0.01, 'valid_rank_ic': 0.02, 'valid_icir': 0.03,
        'valid_rank_icir': 0.04, 'valid_mean_turnover': 0.15,
        'valid_decay_5': 0.11, 'valid_decay_10': 0.12, 'valid_decay_20': 0.13,
        'valid_corr_max': 0.7, 'valid_corr_existing_pool': None,
        'valid_net_excess_annual': -0.07, 'valid_net_excess_ir': -0.8,
        'valid_net_mdd': -0.3,
        'train_start': '2008-01-01', 'train_end': '2014-12-31',
        'valid_start': '2015-01-01', 'valid_end': '2016-12-31',
        'test_start': '2017-01-01', 'test_end': '2020-08-01',
    }
    assert {key: saved[key] for key in expected} == expected
    assert json.loads(saved['report_json']) == report


def test_missing_scalars_are_sql_null_and_report_nulls_stay_null(tmp_path):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    report = {'status': 'FORWARD', 'splits': {'valid': {'primary': {'ic': None}}}}
    store.record('run-1', 'factor-1', report)
    store.record_failure('run-2', 'factor-1', 'No metrics available')

    for saved in rows(path, 'evaluations'):
        metric_keys = [key for key in saved if key.startswith(('train_', 'valid_', 'test_'))]
        assert metric_keys
        assert all(saved[key] is None for key in metric_keys)
    assert json.loads(rows(path, 'evaluations')[0]['report_json']) == report


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_numbers_anywhere_in_report_are_rejected_atomically(tmp_path, invalid):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    report = complete_report()
    report['splits']['test']['deep_detail'] = {'values': [None, invalid]}

    with pytest.raises(ValueError):
        store.record('run-1', 'factor-1', report)

    assert rows(path, 'evaluations') == []
    store.record_failure('run-1', 'factor-1', 'Nonfinite report rejected')
    assert rows(path, 'evaluations')[0]['status'] == 'FAILED'


@pytest.mark.parametrize('invalid', ['0.25', True, {'value': 0.25}])
def test_invalid_scalar_types_do_not_become_apparently_valid_numbers(tmp_path, invalid):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    report = complete_report()
    report['splits']['valid']['primary']['ic'] = invalid

    with pytest.raises(ValueError, match='valid_ic'):
        store.record('run-1', 'factor-1', report)

    assert rows(path, 'evaluations') == []


@pytest.mark.parametrize('status', [None, 'PASS', 'RUNNING', 'keep'])
def test_invalid_disposition_cannot_enter_history(tmp_path, status):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())

    with pytest.raises(ValueError, match='status'):
        store.record('run-1', 'factor-1', {'status': status})

    assert rows(path, 'evaluations') == []


def test_unregistered_factor_cannot_create_orphan_evaluation(tmp_path):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)

    with pytest.raises(ValueError, match='registered'):
        store.record('run-1', 'missing-factor', {'status': 'REJECT'})
    with pytest.raises(ValueError, match='registered'):
        store.record_failure('run-2', 'missing-factor', 'Failed before registration')

    assert rows(path, 'evaluations') == []


def test_existing_pool_uses_latest_trial_insertion_not_run_name_or_old_keep(tmp_path):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    for factor_id, name in [('first', 'MOM_20'), ('second', 'MOM_60'), ('never', 'REV_5')]:
        store.register(factor_id, definition(name=name))
    store.record('z-old', 'first', {'status': 'KEEP'})
    store.record('z-old', 'second', {'status': 'KEEP'})
    store.record('a-new', 'first', {'status': 'REJECT'})

    assert registry(path).existing_pool() == [definition(name='MOM_60') | {'factor_id': 'second'}]
    store.record_failure('a-new', 'second', 'Execution failed')
    assert store.existing_pool() == []
    store.record('b-new', 'first', {'status': 'KEEP'})
    assert store.existing_pool() == [definition() | {'factor_id': 'first'}]


@pytest.mark.parametrize('statement', [
    "UPDATE factors SET expression = 'close'",
    'DELETE FROM factors',
    "UPDATE evaluations SET status = 'KEEP'",
    'DELETE FROM evaluations',
])
def test_sql_cannot_overwrite_or_remove_registered_history(tmp_path, statement):
    path = tmp_path / 'factors.sqlite'
    store = registry(path)
    store.register('factor-1', definition())
    store.record('run-1', 'factor-1', {'status': 'REJECT'})

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            connection.execute(statement)

    assert rows(path, 'factors')[0]['expression'] == 'close / Ref(close, 20) - 1'
    assert rows(path, 'evaluations')[0]['status'] == 'REJECT'
