"""Bounded M3.0 orchestration of existing M1/M2 research kernels.

Screen rejection terminates admission. Screen survivors are pending the separate
cost/model protocol, never promoted to KEEP by this adapter.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from filelock import FileLock

from .candidates import admit_batch, identity
from ..factors.engine import strict_write_json as write, verify_baseline, audit_causality
from ..factors.expressions import Expression
from ..factors.provenance import verify_data_identity
from ..factors.data import load_factor_data, preprocess, forward_labels
from ..factors.analytics import daily_ic, summarize_ic
from ..factors.registry import FactorRegistry
from ..m2.core import neutralize, block_inference, bh_adjust
from ..m2.family_screen import checked_artifact, screen_pass
from ..m2.alpha_map import compress_basis, conditional_residual
import hashlib


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def research_firewall(baseline, screen):
    if baseline['data_end'] > '2020-12-31':
        raise ValueError('protected data cannot enter M3 research')
    for segment in baseline['segments'].values():
        if len(segment) != 2 or segment[0] > segment[1] or segment[1] > '2020-12-31':
            raise ValueError('protected or invalid baseline segment')
    if screen['period'] != ['2015-01-01', '2016-12-31']:
        raise ValueError('only the observed historical screening period is authorized')
    if screen['conditional_period'] != ['2016-01-01', '2016-12-31']:
        raise ValueError('conditional period must retain the frozen map protocol')


def run(root, batch_path):
    root, batch_path = Path(root).resolve(), Path(batch_path).resolve()
    payload = json.loads(batch_path.read_text(encoding='utf-8'))
    hypotheses = admit_batch(payload)
    baseline = json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
    c = json.loads((root/'configs/factors/m2_family_screen.json').read_text())
    research_firewall(baseline, c)  # Before loading any market observations.
    if payload['screen_protocol_sha256'] != sha(root/'configs/factors/m2_family_screen.json'):
        raise ValueError('screen protocol changed after batch freeze')
    with FileLock(str(root/'data/factor_engine.lock'), timeout=0):
        return _run(root, batch_path, payload, hypotheses, baseline, c)


def _run(root, batch_path, payload, hypotheses, baseline, c):
    output = root/'experiments/m3'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state = {'status': 'RUNNING', 'run_id': output.name, 'batch_sha256': identity(payload)}
    write(output/'status.json', state)
    write(output/'batch.json', payload)
    write(output/'screen_protocol.json', c)
    print(f'M3_RUN {output}', flush=True)
    registered, recorded = [], set()
    registry = FactorRegistry(root/'data/factor_registry.sqlite')
    try:
        sources = list((root/'src/quant_research').rglob('*.py')) + [batch_path,
                  root/'scripts/run_m3.py', root/'docs/M3_PROTOCOL.md',
                  root/'configs/factors/m2_family_screen.json']
        hashes = {str(p.relative_to(root)): sha(p) for p in sources}
        for n in hashes:
            target = output/'source'/n
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root/n, target)
        write(output/'source_hashes.json', hashes)
        frozen = verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
        data_hash = verify_data_identity(root, baseline, frozen)
        market = load_factor_data(root, baseline)
        if market.membership.index.max() >= pd.Timestamp('2021-01-01'):
            raise ValueError('canonical observations crossed research firewall')
        dates = market.membership.loc[c['period'][0]:c['period'][1]].index
        mask = (market.membership & market.tradable).loc[dates]
        labels = forward_labels(market, c['primary_horizon'], c['period'])
        prior = root/c['pilot_run']
        manifest = json.loads((prior/'artifact_hashes.json').read_text())
        size = pd.read_parquet(checked_artifact(prior, 'data/log_circulating_cap_proxy.parquet', manifest)).loc[dates]
        industry = pd.read_parquet(checked_artifact(prior, 'data/industry.parquet', manifest)).loc[dates]
        results, scores = {}, {}
        for h in hypotheses:
            factor = h.factor()
            registry.register(factor.factor_id, asdict(factor)); registered.append(factor.factor_id)
            folder = output/h.name; folder.mkdir()
            expression = Expression(h.expression)
            audit = audit_causality(expression, market.fields, market.membership, '2014-12-31')
            raw = expression.evaluate(market.fields, market.membership).loc[dates]
            raw.to_parquet(folder/'raw.parquet')
            score, check = neutralize(preprocess(raw*h.direction, mask), size, industry)
            score.to_parquet(folder/'scores.parquet'); scores[h.name] = score
            check.to_csv(folder/'neutralization.csv', index=False)
            daily = daily_ic(score, labels, c['min_pairs']); daily.to_csv(folder/'ic.csv')
            coverage = {str(y): float(score.loc[str(y)].notna().to_numpy().sum()/
                                     market.membership.loc[str(y)].to_numpy().sum()) for y in [2015, 2016]}
            results[h.name] = {'hypothesis_id': h.hypothesis_id, 'factor_id': factor.factor_id,
                'source_type': h.source_type, 'causality': audit, 'primary': summarize_ic(daily),
                'coverage_by_year': coverage,
                'years': {str(y): summarize_ic(d) for y, d in daily.groupby(daily.index.year)},
                'inference': block_inference(daily.rank_ic, c['block_length'], c['bootstrap_samples'], c['seed'])}
            print(f'SCREEN {h.name}', flush=True)
        qs = bh_adjust([results[h.name]['inference']['p'] for h in hypotheses])
        amap = root/c['alpha_map_run']; ah = c['alpha_map_input_sha256']
        features = pd.read_parquet(checked_artifact(amap, 'features.parquet', ah))
        basis = json.loads(checked_artifact(amap, 'basis.json', ah).read_text())
        pca = json.loads(checked_artifact(amap, 'pca.json', ah).read_text())
        loadings = pd.read_csv(checked_artifact(amap, 'pca_loadings.csv', ah), index_col=0)
        compressed, reproduced, info = compress_basis(features[basis['representatives']], pca['fit_period'], pca['variance_target'], 20)
        np.testing.assert_allclose(reproduced, loadings, rtol=1e-10, atol=1e-12)
        conditional_labels = forward_labels(market, c['primary_horizon'], c['conditional_period'])
        for h, q in zip(hypotheses, qs):
            r = results[h.name]; r['q'] = float(q)
            passed = screen_pass(r['coverage_by_year'], r['primary'], r['years'], q, c)
            r['status'] = 'FORWARD' if passed else 'REJECT'
            r['admission_stage'] = 'IC_SCREEN_PASS' if passed else 'IC_SCREEN_REJECT'
            r['independent_alpha'] = False
            r['downstream'] = {stage: 'PENDING_PROTOCOL' if passed else 'NOT_RUN_SCREEN_REJECT'
                               for stage in ['matched_cost_increment', 'rolling_model_increment']}
            r['protected'] = {'qualification_executed': False, 'lockbox_executed': False}
            matched, residual, check = conditional_residual(scores[h.name].loc['2016'], compressed, size, industry)
            if not matched.notna().equals(residual.notna()):
                raise ValueError('conditional masks differ')
            if len(check) and check.orthogonality_error.max() > 1e-8:
                raise ValueError('conditional projection failed')
            r['conditional'] = {'status': 'DIAGNOSTIC_ONLY', 'variance_retained': info['variance_retained']}
            for name, panel in [('matched', matched), ('residual', residual)]:
                d = daily_ic(panel, conditional_labels, c['min_pairs'])
                d.to_csv(output/h.name/f'{name}_ic.csv')
                r['conditional'][name] = summarize_ic(d)
            write(output/h.name/'hypothesis.json', asdict(h))
            print(f'RESULT {h.name} {r["status"]} rank_ic={r["primary"]["rank_ic"]}', flush=True)
        verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
        if any(sha(root/n) != v for n, v in hashes.items()):
            raise ValueError('source changed during experiment')
        for h in hypotheses:
            r = results[h.name]
            report = {**r, 'run_id': output.name, 'hypothesis': asdict(h),
                      'config': {'segments': {'valid': c['period']}},
                      'splits': {'valid': {'primary': r['primary']}},
                      'reasons': [r['admission_stage']], 'batch_sha256': identity(payload)}
            write(output/h.name/'report.json', report)
            registry.record(output.name, h.factor().factor_id, report); recorded.add(h.factor().factor_id)
        write(output/'results.json', results)
        write(output/'lineage.json', {'batch_sha256': identity(payload), 'run_id': output.name,
            'data_manifest_sha256': data_hash, 'source_sha256': hashes,
            'feedback_scope': 'research_only', 'automatic_refinement': False,
            'candidates': [{'hypothesis_id': h.hypothesis_id, 'factor_id': h.factor().factor_id,
                            'report': f'{h.name}/report.json'} for h in hypotheses]})
        state.update(status='PASS', stage='archived', candidates=len(hypotheses))
        write(output/'status.json', state)
        write(output/'artifact_hashes.json', {str(p.relative_to(output)): sha(p)
            for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts})
        return output
    except BaseException as exc:
        for factor_id in registered:
            if factor_id not in recorded:
                registry.record_failure(output.name, factor_id, str(exc))
        state.update(status='FAIL', error=str(exc)); write(output/'status.json', state)
        raise
