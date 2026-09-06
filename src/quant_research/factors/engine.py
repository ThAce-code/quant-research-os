"""Unified single-factor evaluation; validation decides, test only diagnoses."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import traceback

import numpy as np
import pandas as pd
from filelock import FileLock

from ..integrity import file_hashes
from .analytics import (correlation_matrix, daily_ic, decide_factor, exposure_report,
                        number, quantile_spread, summarize_ic)
from .data import forward_labels, load_factor_data, preprocess
from .expressions import Expression, FactorDefinition
from .provenance import freeze_sources, verify_data_identity, verify_sources


ROOT = Path(__file__).resolve().parents[3]


def clean_json(value):
    if isinstance(value, dict): return {str(k): clean_json(v) for k,v in value.items()}
    if isinstance(value, (tuple, list)): return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (float, np.floating)): return number(value)
    if isinstance(value, (Path, pd.Timestamp)): return str(value)
    return value


def strict_write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(clean_json(value), ensure_ascii=False, indent=2, allow_nan=False)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(payload + '\n', encoding='utf-8')
    temp.replace(path)


def validate_config(config):
    if config['universe'] != 'csi300' or not re.fullmatch(r'[A-Za-z0-9_-]+', config['name']):
        raise ValueError('unsupported universe or experiment name')
    if config['decay_horizons'] != [1,2,5,10,20] or config['horizon'] not in config['decay_horizons']:
        raise ValueError('primary horizon must be one of the five complete decay horizons')
    if type(config['min_pairs']) is not int or not 3 <= config['min_pairs'] <= 300:
        raise ValueError('min_pairs must be 3..300')


def audit_causality(expression, fields, membership, cutoff):
    full = expression.evaluate(fields, membership=membership)
    prefix = expression.evaluate({k:v.loc[:cutoff] for k,v in fields.items()}, membership=membership.loc[:cutoff])
    try:
        pd.testing.assert_frame_equal(full.loc[:cutoff], prefix, check_exact=False, rtol=1e-12, atol=1e-12)
    except AssertionError as error:
        raise ValueError('causality prefix-invariance check failed') from error
    return {'status':'PASS', 'method':'whitelisted historical AST + prefix invariance',
            'cutoff':str(cutoff), 'lookback':expression.lookback,
            'signal_available':'after close t', 'earliest_execution':'close t+1'}


def verify_baseline(root, baseline_id):
    frozen = Path(root) / 'baselines' / baseline_id
    manifest = json.loads((frozen / 'manifest.json').read_text(encoding='utf-8'))
    for source in (frozen / 'source').rglob('*'):
        if source.is_file():
            current = Path(root) / source.relative_to(frozen / 'source')
            if hashlib.sha256(current.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
                raise ValueError(f'frozen M0 source changed: {current}')
    original = Path(manifest['run_directory'])
    for name, want in manifest['artifact_sha256'].items():
        if hashlib.sha256((original / name).read_bytes()).hexdigest() != want:
            raise ValueError(f'frozen M0 artifact changed: {name}')
    return manifest


@dataclass
class FactorReport:
    factor: dict
    run_id: str
    config: dict
    splits: dict
    causality: dict
    status: str
    reasons: list
    artifact_directory: str
    schema_version: int = 1

    def to_dict(self):
        return clean_json(asdict(self))


class FactorEngine:
    def __init__(self, root=ROOT, config=None):
        self.root = Path(root).resolve()
        config = config or self.root / 'configs/factors/m1.json'
        self.config = json.loads(Path(config).read_text(encoding='utf-8')) if not isinstance(config,dict) else dict(config)
        validate_config(self.config)
        self.baseline_config = json.loads((self.root / self.config['baseline_config']).read_text(encoding='utf-8'))
        self.segments = self.baseline_config['segments']

    def run(self, definitions=None):
        # A shared registry and Qlib provider are protected for the whole run.
        lock = self.root / 'data/factor_engine.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(lock), timeout=0):
            return self._run(definitions or self.config['factors'])

    def _run(self, definitions):
        from .registry import FactorRegistry
        from .report import write_factor_report, write_run_report
        from .portfolio import run_portfolios
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output = self.root / 'experiments/factor_engine' / self.config['name'] / run_id
        output.mkdir(parents=True)
        state = {'run_id':run_id, 'status':'RUNNING', 'stage':'data_verification', 'started_at':datetime.now(timezone.utc).isoformat()}
        strict_write_json(output / 'status.json', state)
        print(f'FACTOR_RUN {output}', flush=True)
        reports, errors = [], []
        registry = None
        registered, recorded = set(), set()
        registry_errors = []

        def record_failure(factor_id, error):
            if factor_id in recorded:
                return True
            try:
                registry.record_failure(run_id, factor_id, f'{type(error).__name__}: {error}')
            except Exception as write_error:
                registry_errors.append({'factor_id':factor_id,
                                        'error':f'{type(write_error).__name__}: {write_error}'})
                return False
            recorded.add(factor_id)
            return True

        try:
            executing_sources = freeze_sources(self.root, output)
            frozen = verify_baseline(self.root, self.config['baseline_id'])
            data_identity = verify_data_identity(self.root, self.baseline_config, frozen)
            self.data = load_factor_data(self.root, self.baseline_config)
            print('PANELS_LOADED canonical snapshot verified',flush=True)
            provider = self.root / 'data/qlib' / self.baseline_config['name']
            if file_hashes(provider, '**/*') != frozen['original_provenance']['qlib_files_sha256']:
                raise ValueError('Qlib provider differs from frozen M0 snapshot')
            registry = FactorRegistry(self.root / 'data/factor_registry.sqlite')
            existing = registry.existing_pool()  # frozen before adding this batch
            candidates, self.scores, self.raw, audits = [], {}, {}, {}
            strict_write_json(output / 'config.json', {**self.config,'factors':definitions,'segments':self.segments})
            for definition in definitions:
                # Persist candidate identity before validation so rejected syntax is not lost.
                raw = {'direction':1,'source':'human_baseline','paper':None,'generator':'human','version':1,**definition}
                key = 'F_' + hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
                registry.register(key, raw)
                registered.add(key)
                try:
                    factor = FactorDefinition(**raw)
                    print(f'CALCULATE {factor.name}',flush=True)
                    if factor.name in self.scores:
                        raise ValueError('duplicate factor name in one batch')
                    expression = Expression(factor.expression)
                    audits[factor.name] = audit_causality(expression,self.data.fields,self.data.membership,self.segments['train'][1])
                    self.raw[factor.name] = expression.evaluate(self.data.fields, membership=self.data.membership)
                    self.scores[factor.name] = preprocess(self.raw[factor.name] * factor.direction,
                                                         self.data.membership & self.data.tradable)
                    candidates.append(factor)
                except Exception as error:
                    if not record_failure(key, error):
                        raise
                    errors.append({'factor':raw['name'],'error':str(error)})
            if not candidates:
                raise ValueError('no calculable factors')
            state['stage'] = 'diagnostics_and_backtests'; strict_write_json(output/'status.json',state)
            labels, matrices = {}, {}
            for split, segment in self.segments.items():
                print(f'CORRELATION_AND_LABELS {split}',flush=True)
                matrices[split] = correlation_matrix({name:frame.loc[segment[0]:segment[1]] for name,frame in self.scores.items()},self.config['min_pairs'])
                matrices[split].to_csv(output / f'{split}_correlation.csv')
                for horizon in self.config['decay_horizons']:
                    labels[split,horizon] = forward_labels(self.data,horizon,segment)
                    target = output / 'labels' / f'{split}_h{horizon}.parquet'; target.parent.mkdir(exist_ok=True)
                    labels[split,horizon].to_parquet(target)
            exposures = {'volatility': self.data.fields['returns'].rolling(20,min_periods=20).std(),
                         'turnover':self.data.fields['turnover'].rolling(20,min_periods=20).mean()}
            trailing = self.data.benchmark / self.data.benchmark.shift(60) - 1
            regimes = pd.Series('sideways',index=trailing.index).where(trailing.notna())
            regimes.loc[trailing.gt(.05)]='bull'; regimes.loc[trailing.lt(-.05)]='bear'
            regimes.rename('regime').to_csv(output / 'regimes.csv')
            pool = {entry['factor_id']: preprocess(Expression(entry['expression']).evaluate(self.data.fields,membership=self.data.membership)*entry['direction'], self.data.membership & self.data.tradable)
                    for entry in existing}
            import qlib
            # Serial loading avoids Windows worker CPU-feature initialization failures.
            qlib.init(provider_uri=str(provider),region='cn',kernels=1,expression_cache=None,dataset_cache=None)
            for factor in candidates:
                directory = output / factor.name; directory.mkdir()
                try:
                    print(f'EVALUATE {factor.name}',flush=True)
                    score = self.scores[factor.name]
                    score.to_parquet(directory / 'scores.parquet')
                    self.raw[factor.name].where(self.data.membership & self.data.tradable).to_parquet(directory / 'raw_values.parquet')
                    splits = {}
                    for split,segment in self.segments.items():
                        subdir = directory / split; subdir.mkdir()
                        sc = score.loc[segment[0]:segment[1]]
                        expected = self.data.membership.loc[sc.index].to_numpy().sum()
                        stats = {'coverage':float(sc.notna().to_numpy().sum()/expected), 'decay':{}}
                        for horizon in self.config['decay_horizons']:
                            daily = daily_ic(sc,labels[split,horizon],self.config['min_pairs'])
                            daily.to_csv(subdir/f'ic_h{horizon}.csv')
                            decay = summarize_ic(daily)
                            decay['last_usable_signal_date'] = str(daily.ic.last_valid_index()) if daily.ic.notna().any() else None
                            stats['decay'][str(horizon)] = decay
                            if horizon == self.config['horizon']:
                                primary = daily
                        stats['primary'] = summarize_ic(primary)
                        stats['stability_year'] = {str(year):summarize_ic(frame) for year,frame in primary.groupby(primary.index.year)}
                        stats['stability_regime'] = {regime:summarize_ic(primary.loc[regimes.reindex(primary.index).eq(regime)]) for regime in ['bull','bear','sideways']}
                        stats['exposure'] = exposure_report(sc,exposures,self.config['min_pairs'])
                        others = matrices[split].loc[factor.name].drop(factor.name).abs()
                        stats['corr_max'] = number(others.max())
                        pool_corr = [daily_ic(sc,v.loc[segment[0]:segment[1]],self.config['min_pairs']).rank_ic.mean()
                                     for key,v in pool.items() if key != factor.factor_id]
                        stats['corr_existing_pool'] = number(max([abs(v) for v in pool_corr if np.isfinite(v)],default=np.nan))
                        spread = quantile_spread(sc,labels[split,self.config['horizon']],.2,self.config['min_pairs'])
                        spread.to_csv(subdir/'hypothetical_spread.csv')
                        stats['long_short'] = {'mean_horizon_spread':number(spread.long_short.mean()),
                                              'horizon':self.config['horizon'], 'days':int(spread.long_short.notna().sum()),
                                              'execution':'hypothetical gross top20-minus-bottom20 label spread; overlapping; no short availability or costs modeled'}
                        if split in {'valid','test'}:
                            print(f'BACKTEST {factor.name} {split}',flush=True)
                            stats['portfolio'] = run_portfolios(score,segment[0],segment[1],self.baseline_config['backtest'],subdir,sc.index)
                        else:
                            stats['portfolio'] = None
                        splits[split]=stats
                    valid = splits['valid']
                    decision = {**valid['primary'],'coverage':valid['coverage'], 'net_excess_annual':valid['portfolio']['top20']['net_excess_annual']}
                    missing = [name for name,value in valid['exposure'].items() if value['status'] != 'AVAILABLE']
                    status,reasons = decide_factor(decision,self.config['rules'],missing,valid['corr_existing_pool'])
                    report = FactorReport({**asdict(factor),'factor_id':factor.factor_id},run_id,
                                          {**self.config,'segments':self.segments,'annualization_days':238},splits,
                                          audits[factor.name],status,reasons,str(directory))
                    write_factor_report(directory,report.to_dict())
                    strict_write_json(directory/'report.json',report.to_dict())
                    registry.record(run_id,factor.factor_id,report.to_dict())
                    recorded.add(factor.factor_id)
                    reports.append(report)
                    print(f'RESULT {factor.name} {status} valid_rank_ic={valid["primary"]["rank_ic"]} test_net={splits["test"]["portfolio"]["top20"]["net_excess_annual"]}',flush=True)
                except Exception as error:
                    if not record_failure(factor.factor_id, error):
                        raise
                    (directory/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
                    errors.append({'factor':factor.name,'error':str(error)})
            write_run_report(output,[r.to_dict() for r in reports],errors,matrices['valid'])
            verify_baseline(self.root,self.config['baseline_id'])
            verify_sources(self.root,executing_sources)
            verify_data_identity(self.root,self.baseline_config,frozen)
            strict_write_json(output/'provenance.json',{'baseline_id':self.config['baseline_id'],
                'baseline_manifest_sha256':hashlib.sha256((self.root/'baselines'/self.config['baseline_id']/'manifest.json').read_bytes()).hexdigest(),
                'data_manifest_sha256':data_identity,
                'source_sha256':executing_sources,
                'versions':{name:importlib.metadata.version(name) for name in ['pandas','numpy','pyqlib','pyarrow','matplotlib']},
                'existing_pool_at_start':existing,'baseline_unchanged':True,'qlib_data_kernels':1})
            if errors:
                strict_write_json(output/'factor_errors.json',errors)
                raise RuntimeError(f'{len(errors)} factors failed; see factor_errors.json')
            state.update(status='PASS',stage='complete',factors=len(reports),ended_at=datetime.now(timezone.utc).isoformat())
            strict_write_json(output/'status.json',state)
            strict_write_json(output.parent/'latest.json',{'run_directory':str(output),**state})
            return reports
        except Exception as error:
            primary_traceback = traceback.format_exc()
            for factor_id in sorted(registered - recorded):
                record_failure(factor_id, error)
            state.update(status='FAILED',error=f'{type(error).__name__}: {error}',ended_at=datetime.now(timezone.utc).isoformat())
            if registry_errors:
                state['registry_errors'] = registry_errors
            strict_write_json(output/'status.json',state)
            (output/'error.txt').write_text(primary_traceback,encoding='utf-8')
            raise


def evaluate_factor(factor, universe='csi300', horizon=5, experiment=None, root=ROOT):
    """Return one FactorReport; experiment is a config path or config dictionary."""
    engine = FactorEngine(root,experiment)
    engine.config.update(universe=universe,horizon=horizon)
    validate_config(engine.config)
    if isinstance(factor,str):
        factor = next((f for f in engine.config['factors'] if f['name']==factor),None)
        if factor is None: raise ValueError('unknown registered seed factor')
    if isinstance(factor,FactorDefinition): factor=asdict(factor)
    return engine.run([factor])[0]
