"""Immutable factor definitions and append-only research trials in SQLite.

The complete strict-JSON report is authoritative. Validation scalar columns
are only query conveniences and never determine a factor's disposition here.
"""
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3


_STATUSES = {'KEEP', 'REJECT', 'FORWARD', 'FAILED'}
_DEFINITION_FIELDS = (
    'name', 'family', 'expression', 'hypothesis', 'direction',
    'source', 'paper', 'generator', 'version',
)
_VALID_METRICS = {
    'valid_ic': ('primary', 'ic'),
    'valid_rank_ic': ('primary', 'rank_ic'),
    'valid_icir': ('primary', 'icir'),
    'valid_rank_icir': ('primary', 'rank_icir'),
    'valid_mean_turnover': ('portfolio', 'top20', 'mean_turnover'),
    'valid_net_excess_annual': ('portfolio', 'top20', 'net_excess_annual'),
    'valid_net_excess_ir': ('portfolio', 'top20', 'net_excess_ir'),
    'valid_net_mdd': ('portfolio', 'top20', 'net_mdd'),
    'valid_decay_5': ('decay', '5', 'ic'),
    'valid_decay_10': ('decay', '10', 'ic'),
    'valid_decay_20': ('decay', '20', 'ic'),
    'valid_corr_max': ('corr_max',),
    'valid_corr_existing_pool': ('corr_existing_pool',),
}


def _json_object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be a JSON object')
    try:
        return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f'{label} must contain only strict JSON values: {error}') from error


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')
    return value


def _nested(mapping, *keys):
    value = mapping
    for key in keys:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError(f'report section containing {key} must be an object or null')
        value = value.get(key)
    return value


def _number(value, label):
    if value is None:
        return None
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f'{label} must be a finite number or null')
    return value


class FactorRegistry:
    """File-backed registry; each operation opens and closes its own connection."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        metric_columns = ',\n'.join(f'{name} REAL' for name in _VALID_METRICS)
        with self._connection() as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.executescript(f'''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS factors (
                    factor_id TEXT PRIMARY KEY NOT NULL,
                    name TEXT NOT NULL,
                    family TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    direction INTEGER NOT NULL CHECK (direction IN (-1, 1)),
                    source TEXT NOT NULL,
                    paper TEXT,
                    generator TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    definition_json TEXT NOT NULL CHECK (json_valid(definition_json)),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    UNIQUE (name, version)
                );
                CREATE TABLE IF NOT EXISTS evaluations (
                    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    factor_id TEXT NOT NULL REFERENCES factors(factor_id),
                    status TEXT NOT NULL CHECK (status IN ('KEEP', 'REJECT', 'FORWARD', 'FAILED')),
                    error TEXT,
                    train_start TEXT, train_end TEXT,
                    valid_start TEXT, valid_end TEXT,
                    test_start TEXT, test_end TEXT,
                    {metric_columns},
                    report_json TEXT NOT NULL CHECK (json_valid(report_json)),
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    UNIQUE (run_id, factor_id)
                );
                CREATE INDEX IF NOT EXISTS evaluations_factor_latest
                    ON evaluations (factor_id, evaluation_id DESC);
                CREATE TRIGGER IF NOT EXISTS factors_no_update
                    BEFORE UPDATE ON factors BEGIN
                        SELECT RAISE(ABORT, 'factor definitions are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS factors_no_delete
                    BEFORE DELETE ON factors BEGIN
                        SELECT RAISE(ABORT, 'factor definitions are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS evaluations_no_update
                    BEFORE UPDATE ON evaluations BEGIN
                        SELECT RAISE(ABORT, 'evaluations are immutable');
                    END;
                CREATE TRIGGER IF NOT EXISTS evaluations_no_delete
                    BEFORE DELETE ON evaluations BEGIN
                        SELECT RAISE(ABORT, 'evaluations are immutable');
                    END;
                COMMIT;
            ''')

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            with connection:
                yield connection
        finally:
            connection.close()

    def register(self, factor_id: str, definition: dict) -> None:
        """Register once; repeating an identical ID/definition is idempotent.

        Any definition change needs both a new factor ID and a new name/version
        identity. Existing factor IDs and definition versions cannot be replaced.
        """
        _identifier(factor_id, 'factor_id')
        payload = _json_object(definition, 'definition')
        missing = set(_DEFINITION_FIELDS) - definition.keys()
        if missing:
            raise ValueError(f'definition is missing fields: {sorted(missing)}')
        _identifier(definition['name'], 'definition name')
        if type(definition['version']) is not int or definition['version'] < 1:
            raise ValueError('definition version must be a positive integer')

        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute(
                'SELECT definition_json FROM factors WHERE factor_id = ?', (factor_id,),
            ).fetchone()
            if existing is not None:
                if existing['definition_json'] != payload:
                    raise ValueError('factor_id is immutable; register a new ID with a version bump')
                return
            existing = connection.execute(
                'SELECT factor_id FROM factors WHERE name = ? AND version = ?',
                (definition['name'], definition['version']),
            ).fetchone()
            if existing is not None:
                raise ValueError('factor name/version is already registered; a version bump is required')
            columns = ('factor_id', *_DEFINITION_FIELDS, 'definition_json')
            placeholders = ', '.join('?' for _ in columns)
            connection.execute(
                f'INSERT INTO factors ({", ".join(columns)}) VALUES ({placeholders})',
                (factor_id, *(definition[key] for key in _DEFINITION_FIELDS), payload),
            )

    def record(self, run_id: str, factor_id: str, report: dict) -> None:
        """Append one trial without changing or recomputing its disposition."""
        _identifier(run_id, 'run_id')
        _identifier(factor_id, 'factor_id')
        payload = _json_object(report, 'report')
        status = report.get('status')
        if not isinstance(status, str) or status not in _STATUSES:
            raise ValueError('report status must be KEEP, REJECT, FORWARD or FAILED')
        error = report.get('error')
        if error is not None and not isinstance(error, str):
            raise ValueError('report error must be a string or null')
        values = {'run_id': run_id, 'factor_id': factor_id, 'status': status, 'error': error}
        for split in ('train', 'valid', 'test'):
            segment = _nested(report, 'config', 'segments', split)
            if segment is None:
                segment = (None, None)
            if not isinstance(segment, (list, tuple)) or len(segment) != 2:
                raise ValueError(f'{split} segment must contain start and end dates')
            if any(date is not None and not isinstance(date, str) for date in segment):
                raise ValueError(f'{split} segment dates must be strings or null')
            values[f'{split}_start'], values[f'{split}_end'] = segment
        validation = _nested(report, 'splits', 'valid')
        for column, keys in _VALID_METRICS.items():
            values[column] = _number(_nested(validation, *keys), column)
        values['report_json'] = payload

        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if connection.execute(
                'SELECT 1 FROM factors WHERE factor_id = ?', (factor_id,),
            ).fetchone() is None:
                raise ValueError('factor must be registered before recording an evaluation')
            if connection.execute(
                'SELECT 1 FROM evaluations WHERE run_id = ? AND factor_id = ?',
                (run_id, factor_id),
            ).fetchone() is not None:
                raise ValueError('evaluation is immutable; use a new run_id for another trial')
            placeholders = ', '.join('?' for _ in values)
            connection.execute(
                f'INSERT INTO evaluations ({", ".join(values)}) VALUES ({placeholders})',
                tuple(values.values()),
            )

    def record_failure(self, run_id: str, factor_id: str, error: str) -> None:
        """Preserve an execution error as a new FAILED trial with null metrics."""
        if not isinstance(error, str):
            raise ValueError('error must be a string')
        self.record(run_id, factor_id, {'status': 'FAILED', 'reasons': ['execution_error'], 'error': error})

    def existing_pool(self) -> list[dict]:
        """Return definitions whose latest inserted trial has status KEEP."""
        with self._connection() as connection:
            saved = connection.execute('''
                SELECT f.factor_id, f.definition_json FROM factors AS f
                JOIN evaluations AS e ON e.factor_id = f.factor_id
                WHERE e.evaluation_id = (
                    SELECT MAX(latest.evaluation_id) FROM evaluations AS latest
                    WHERE latest.factor_id = f.factor_id
                ) AND e.status = 'KEEP'
                ORDER BY f.factor_id
            ''').fetchall()
        return [json.loads(row['definition_json']) | {'factor_id': row['factor_id']} for row in saved]

    def evaluations(self) -> list[dict]:
        """Read all scalar columns and parsed ``report`` in insertion order."""
        with self._connection() as connection:
            saved = connection.execute('SELECT * FROM evaluations ORDER BY evaluation_id').fetchall()
        return [dict(row) | {'report': json.loads(row['report_json'])} for row in saved]
