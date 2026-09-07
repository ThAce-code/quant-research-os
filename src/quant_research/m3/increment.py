"""Survivor-only model/cost adapter. No automatic protected-period execution."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from filelock import FileLock

from .candidates import admit_batch, identity
from .pipeline import sha, research_firewall
from ..factors.engine import strict_write_json as write, verify_baseline
from ..factors.provenance import verify_data_identity
from ..factors.data import load_factor_data, preprocess
from ..factors.expressions import Expression
from ..factors.analytics import daily_ic
from ..factors.registry import FactorRegistry
from ..integrity import file_hashes
from ..m2.family_screen import checked_artifact, screen_pass
from ..m2.core import neutralize, block_inference, bh_adjust
from ..m2.rolling import folds, gate, paired_backtest


def survivors(screen, registry):
    """Recompute admission from frozen metrics; a status string alone is insufficient."""
    screen = Path(screen)
    if json.loads((screen/'status.json').read_text())['status'] != 'PASS':
        raise ValueError('screen did not complete')
    manifest = json.loads((screen/'artifact_hashes.json').read_text())
    payload = json.loads(checked_artifact(screen, 'batch.json', manifest).read_text())
    c = json.loads(checked_artifact(screen, 'screen_protocol.json', manifest).read_text())
    results = json.loads(checked_artifact(screen, 'results.json', manifest).read_text())
    if payload['screen_protocol_sha256'] != sha(screen/'screen_protocol.json'):
        # Source config was pretty-printed during archival: validate original bytes
        # against the source snapshot, then compare parsed objects.
        original = screen/'source/configs/factors/m2_family_screen.json'
        if sha(original) != payload['screen_protocol_sha256'] or json.loads(original.read_text()) != c:
            raise ValueError('screen protocol identity mismatch')
    hypotheses = admit_batch(payload)
    rows = {v['factor_id']: v for v in registry.evaluations() if v['run_id'] == screen.name}
    accepted = []
    for h in hypotheses:
        r = results[h.name]
        row = rows.get(h.factor().factor_id)
        if row is None or row['status'] != r['status'] or row['report']['batch_sha256'] != identity(payload):
            raise ValueError('screen registry lineage mismatch')
        if any(row['report'].get(k) != v for k, v in r.items()):
            raise ValueError('screen metrics differ from append-only registry')
        passed = screen_pass(r['coverage_by_year'], r['primary'], r['years'], r['q'], c)
        if passed != (r['status'] == 'FORWARD'):
            raise ValueError('screen decision inconsistent with numerical gate')
        if passed:
            accepted.append(h)
    return accepted, payload


def matched_features(features, candidate_panels, labels):
    """One common sample for every variant; labels never select prediction rows."""
    if features.index.has_duplicates or len(features.columns) != 158:
        raise ValueError('exact unique Alpha158 rows required')
    extra = {n: p.rename_axis(index='datetime', columns='instrument').stack(future_stack=True)
             .reindex(features.index) for n, p in candidate_panels.items()}
    candidates = pd.DataFrame(extra)
    common = np.isfinite(candidates).all(axis=1)
    x = features.loc[common].join(candidates.loc[common]).astype('float32')
    return x, labels.reindex(x.index)


def fit_predict(features, raw_labels, calendar, c, model_params, output):
    import lightgbm as lgb
    names = list(features.columns[:158])
    target = (raw_labels.groupby(level='datetime').rank(pct=True)-.5)*3.46
    dates = features.index.get_level_values('datetime')
    params = {k: v for k, v in model_params.items() if k != 'loss'}
    params.update(objective='regression', metric='l2', verbosity=-1, seed=c['seed'])
    predictions = {n: [] for n in c['variants']}; audit = []
    (output/'models').mkdir()
    for f in folds(calendar, c):
        train = (dates >= f['train'][0]) & (dates <= f['train'][1]) & target.notna()
        valid = (dates >= f['valid'][0]) & (dates <= f['valid'][1]) & target.notna()
        start = calendar[calendar < f['test'][0]][-1] if f['year'] == c['fold_years'][0] else f['test'][0]
        infer = (dates >= start) & (dates <= f['test'][1])
        if train.sum() < c['min_train_rows'] or valid.sum() < c['min_valid_rows']:
            raise ValueError('insufficient matched training/validation rows')
        for name, extra in c['variants'].items():
            columns = names + extra
            ds = lgb.Dataset(features.loc[train, columns], label=target.loc[train])
            validation = lgb.Dataset(features.loc[valid, columns], label=target.loc[valid], reference=ds)
            model = lgb.train(params, ds, num_boost_round=c['num_boost_round'], valid_sets=[validation],
                callbacks=[lgb.early_stopping(c['early_stopping_rounds'], verbose=False), lgb.log_evaluation(0)])
            predictions[name].append(pd.Series(model.predict(features.loc[infer, columns]),
                                               index=features.index[infer]))
            model.save_model(str(output/'models'/f'{f["year"]}_{name}.txt'))
            audit.append({'year': f['year'], 'variant': name, 'train_end': str(f['train'][1]),
                'valid_end': str(f['valid'][1]), 'train_rows': int(train.sum()),
                'valid_rows': int(valid.sum()), 'prediction_rows': int(infer.sum()),
                'features': len(columns), 'seed': c['seed'], 'best_iteration': model.best_iteration})
            pd.DataFrame(audit).to_csv(output/'folds.csv', index=False)
            print(f'M3_FIT {f["year"]} {name}', flush=True)
    predictions = pd.DataFrame({n: pd.concat(p).sort_index() for n, p in predictions.items()})
    if predictions.index.has_duplicates or not np.isfinite(predictions).all().all():
        raise ValueError('invalid predictions')
    return predictions


def run(root, screen, *, selection=None, more_screens=()):
    root, screen = Path(root).resolve(), Path(screen).resolve()
    with FileLock(str(root/'data/factor_engine.lock'), timeout=0):
        registry = FactorRegistry(root/'data/factor_registry.sqlite')
        selected, payload = survivors(screen, registry)
        screen_by_hypothesis={h.hypothesis_id:screen.name for h in selected}
        if selection is not None:
            if not 1<=len(selection)<=3 or len(set(selection))!=len(selection):
                raise ValueError('select one to three distinct screened hypotheses')
            combined={h.hypothesis_id:h for h in selected}
            origins=[{'screen_run':screen.name,'batch_sha256':identity(payload)}]
            for other in more_screens:
                other=Path(other).resolve();extra,batch=survivors(other,registry)
                if batch['screen_protocol_sha256']!=payload['screen_protocol_sha256']:
                    raise ValueError('combined screening protocols differ')
                for h in extra:
                    if h.hypothesis_id in combined:raise ValueError('duplicate screened hypothesis')
                    combined[h.hypothesis_id]=h;screen_by_hypothesis[h.hypothesis_id]=other.name
                origins.append({'screen_run':other.name,'batch_sha256':identity(batch)})
            if not set(selection)<=combined.keys():raise ValueError('selection lacks numerical screen admission')
            selected=[combined[i] for i in selection]
            if len({h.name for h in selected})!=len(selected):
                raise ValueError('selected candidate names collide across screening batches')
            payload={**payload,'candidates':[asdict(h) for h in selected],'source_screens':origins}
            screen_by_hypothesis={h.hypothesis_id:screen_by_hypothesis[h.hypothesis_id] for h in selected}
        output = root/'experiments/m3_increment'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output.mkdir(parents=True)
        tracked = list((root/'src/quant_research').rglob('*.py')) + [
            root/'configs/m3/increment.json', root/'scripts/run_m3_increment.py']
        hashes = {str(p.relative_to(root)): sha(p) for p in tracked}
        for n in hashes:
            target = output/'source'/n; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root/n, target)
        write(output/'source_hashes.json', hashes)
        write(output/'admission.json', {'screen_run': screen.name, 'batch_sha256': identity(payload),
            'candidates': [asdict(h) for h in selected], 'screen_by_hypothesis':screen_by_hypothesis,
            'qualification': 'SEALED', 'lockbox': 'SEALED'})
        if not selected:
            write(output/'status.json', {'status': 'PASS', 'decision': 'NO_ENTRY', 'screen_run': screen.name,
                'market_data_loaded': False, 'fits': 0, 'portfolios': 0, 'reason': 'ALL_SCREEN_REJECT'})
            return output
        try:
            result = _evaluate(root, screen, output, selected, registry, screen_by_hypothesis)
            if any(sha(root/n) != v for n, v in hashes.items()):
                raise ValueError('source changed during model run')
            write(output/'artifact_hashes.json', {str(p.relative_to(output)): sha(p)
                for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts})
            return result
        except BaseException as exc:
            write(output/'status.json', {'status': 'FAIL', 'error': str(exc)})
            raise


def _evaluate(root, screen, output, selected, registry, screen_by_hypothesis=None):
    config = json.loads((root/'configs/m3/increment.json').read_text())
    protocol = root/'configs/factors/m2_rolling.json'
    if sha(protocol) != config['rolling_protocol_sha256']:
        raise ValueError('rolling numerical protocol changed')
    c = json.loads(protocol.read_text())
    c['variants'] = {'BASE': [], **{'ADD_'+h.name: [h.name] for h in selected}}
    c['primary_comparisons'] = list(c['variants'])[1:]
    c['blend_diagnostics'] = {'BLEND_'+h.name: {'BASE': .75, h.name: .25} for h in selected}
    c.update(name='m3_survivor_increment_v1', universe=config['universe'],
             candidate_definitions=[asdict(h) for h in selected],
             drop_diagnostics={}, budget=config['budget'], selection='No automatic winner selection or protected admission')
    c.pop('illiquidity', None)
    c['qualification'] = c['lockbox'] = 'SEALED_REQUIRES_SEPARATE_ADMISSION'
    baseline = json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
    research_firewall(baseline, json.loads((screen/'screen_protocol.json').read_text()))
    if c['data_period'][1] > '2020-12-31' or c['evaluation_period'][1] > '2020-12-31':
        raise ValueError('protected rolling period')
    write(output/'config.json', {'numeric_protocol': c, 'adapter_protocol': config})
    frozen = verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
    verify_data_identity(root, baseline, frozen)
    provider = root/'data/qlib'/baseline['name']
    if file_hashes(provider, '**/*') != frozen['original_provenance']['qlib_files_sha256']:
        raise ValueError('Qlib provider identity mismatch')
    cache = root/config['input_run']
    if sha(cache/'artifact_hashes.json') != config['input_manifest_sha256']:
        raise ValueError('cached controls/features identity mismatch')
    manifest = json.loads((cache/'artifact_hashes.json').read_text())
    panels = {n: pd.read_parquet(checked_artifact(cache, n+'.parquet', manifest))
              for n in ['alpha158', 'labels', 'industry', 'universe', 'log_size']}
    market = load_factor_data(root, baseline)
    candidate_panels = {}
    for h in selected:
        raw = Expression(h.expression).evaluate(market.fields, market.membership)*h.direction
        mask = panels['universe'] & market.tradable.reindex_like(panels['universe'])
        scores, _ = neutralize(preprocess(raw.reindex_like(mask), mask), panels['log_size'], panels['industry'])
        candidate_panels[h.name] = scores
    features, labels = matched_features(panels['alpha158'], candidate_panels, panels['labels'].label)
    features.to_parquet(output/'features.parquet'); labels.to_frame('label').to_parquet(output/'labels.parquet')
    comparisons = evaluate_models(features, labels, market.membership.index, c,
                                  baseline, provider, selected, output)
    # Validate before any irreversible successful research record is appended.
    verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
    source_hashes = json.loads((output/'source_hashes.json').read_text())
    if any(sha(root/n) != v for n, v in source_hashes.items()):
        raise ValueError('source changed before result registration')
    for h in selected:
        decision = comparisons['ADD_'+h.name]
        registry.record(output.name, h.factor().factor_id, {'status': 'FORWARD' if decision['decision']=='GO' else 'REJECT',
            'reasons': ['HISTORICAL_MODEL_'+decision['decision']], 'model_increment': decision,
            'hypothesis_id': h.hypothesis_id, 'screen_run': (screen_by_hypothesis or {}).get(h.hypothesis_id,screen.name),
            'qualification': 'SEALED_PENDING_SEPARATE_ADMISSION', 'independent_alpha': False})
    verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
    write(output/'status.json', {'status': 'PASS', 'fits': len(c['fold_years'])*len(c['variants']),
                                'portfolios': len(c['variants'])+len(selected), 'qualification': 'SEALED', 'lockbox': 'SEALED'})
    return output


def evaluate_models(features, labels, calendar, c, baseline, provider, selected, output):
    """Shared numerical execution for admitted research and isolated engineering checks.

    This function cannot admit candidates or write to a research registry.
    """
    predictions = fit_predict(features, labels, calendar, c, baseline['model'], output)
    predictions.to_parquet(output/'predictions.parquet')
    evaluation = predictions.index.get_level_values('datetime') >= c['evaluation_period'][0]
    y = labels.reindex(predictions.index[evaluation]).unstack('instrument')
    daily = {n: daily_ic(predictions.loc[evaluation, n].unstack('instrument'), y,
                         c['min_prediction_daily_pairs']) for n in c['variants']}
    for n, frame in daily.items(): frame.to_csv(output/f'{n}_ic.csv')
    ranked = predictions.groupby(level='datetime').rank(pct=True)
    signals = {n: predictions[n] for n in predictions}
    for h in selected:
        score = features.loc[predictions.index, h.name].groupby(level='datetime').rank(pct=True)
        signals['BLEND_'+h.name] = .75*ranked.BASE + .25*score
    import qlib
    qlib.init(provider_uri=str(provider), region='cn', kernels=1, expression_cache=None, dataset_cache=None)
    dates = calendar[(calendar >= c['evaluation_period'][0]) & (calendar <= c['evaluation_period'][1])]
    reports = {}; metrics = {}
    for n, signal in signals.items():
        report, metric = paired_backtest(signal, c, baseline, dates)
        reports[n] = report; metrics[n] = metric; report.to_csv(output/f'{n}_daily.csv')
    write(output/'portfolio.json', metrics)
    deltas = {n: block_inference(daily[n].rank_ic-daily['BASE'].rank_ic,
              c['block_length'], c['bootstrap_samples'], c['seed']) for n in c['primary_comparisons']}
    qs = bh_adjust([v['p'] for v in deltas.values()]); comparisons = {}
    base = reports['BASE']['return']-reports['BASE'].cost
    for n, q in zip(c['primary_comparisons'], qs):
        delta = reports[n]['return']-reports[n].cost-base
        net = block_inference(delta, c['block_length'], c['bootstrap_samples'], c['seed'])
        annual = {str(y): float(g.mean()*238) for y, g in delta.groupby(delta.index.year)}
        comparisons[n] = {'rank_ic_increment': deltas[n], 'q': float(q), 'net_increment': net,
                          'annual_net_increment': annual, **gate(deltas[n], q, net, annual, c)}
    write(output/'comparisons.json', comparisons)
    blends = {}
    for h in selected:
        name = 'BLEND_'+h.name
        delta = reports[name]['return']-reports[name].cost-base
        blends[name] = {'status': 'DIAGNOSTIC_ONLY',
            'net_increment': block_inference(delta, c['block_length'], c['bootstrap_samples'], c['seed'])}
    write(output/'blend_diagnostics.json', blends)
    return comparisons
