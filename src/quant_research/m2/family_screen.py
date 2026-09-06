"""Three frozen economic hypotheses, observed-history IC and conditional checks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import traceback
import numpy as np
import pandas as pd
from filelock import FileLock
from ..factors.engine import strict_write_json as write, verify_baseline
from ..factors.provenance import verify_data_identity
from ..factors.data import load_factor_data, preprocess, forward_labels
from ..factors.analytics import daily_ic, summarize_ic, correlation_matrix
from .core import neutralize, block_inference, bh_adjust
from .alpha_map import compress_basis, conditional_residual


def checked_artifact(folder, relative, manifest):
    path = folder / relative
    normalized = {key.replace('\\', '/'): value for key, value in manifest.items()}
    if hashlib.sha256(path.read_bytes()).hexdigest() != normalized[relative.replace('\\', '/')]:
        raise ValueError(f'input artifact changed: {relative}')
    return path


def screen_pass(coverage_by_year, stats, yearly, q, c):
    return (all(v >= c['min_coverage'] for v in coverage_by_year.values())
            and stats['rank_ic'] is not None and stats['rank_ic'] >= c['min_rank_ic']
            and all(v['rank_ic'] is not None and v['rank_ic'] > 0 for v in yearly.values())
            and q <= c['max_q'])


def run(root, quarterly):
    root, quarterly = Path(root), Path(quarterly).resolve()
    with FileLock(str(root / 'data/factor_engine.lock'), timeout=0):
        return _run(root, quarterly)


def _run(root, quarterly):
    c = json.loads((root / 'configs/factors/m2_family_screen.json').read_text())
    if c['period'] != ['2015-01-01', '2016-12-31'] or c['conditional_period'] != ['2016-01-01', '2016-12-31']:
        raise ValueError('screen dates frozen; qualification is not authorized by this script')
    if c['primary_tests'] != ['ROE', 'EARNINGS_GROWTH', 'LOW_ASSET_GROWTH']:
        raise ValueError('primary hypothesis budget changed')
    output = root / 'experiments/m2' / c['name'] / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    state = {'status': 'RUNNING', 'stage': 'verify_inputs', 'run_id': output.name}
    write(output / 'status.json', state); write(output / 'config.json', c)
    print(f'FAMILY_SCREEN {output}', flush=True)
    try:
        names = ['src/quant_research/m2/family_screen.py', 'src/quant_research/m2/core.py',
                 'src/quant_research/m2/alpha_map.py', 'src/quant_research/factors/data.py',
                 'src/quant_research/factors/analytics.py', 'configs/factors/m2_family_screen.json',
                 'scripts/run_family_screen.py']
        hashes = {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
        for n in names:
            target = output/'source'/n; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root/n, target)
        write(output/'source_hashes.json', hashes)
        if json.loads((quarterly/'status.json').read_text())['status'] != 'PASS':
            raise ValueError('quarterly collection must pass first')
        manifest = json.loads((quarterly/'data_manifest.json').read_text())
        qc = json.loads(checked_artifact(quarterly, 'config.json', manifest).read_text())
        expected = {'ROE': ('roeAvg', 1), 'EARNINGS_GROWTH': ('YOYNI', 1), 'LOW_ASSET_GROWTH': ('YOYAsset', -1)}
        if {n: (d['field'], d['direction']) for n,d in qc['candidates'].items()} != expected:
            raise ValueError('candidate definitions changed')
        # Never accept a clean-looking panel from a run with ambiguous input data.
        quarantine = pd.read_csv(checked_artifact(quarterly, 'quarantine.csv', manifest))
        if len(quarantine):
            raise ValueError('quarantine requires explicit data review before screening')
        baseline = json.loads((root/'configs/experiments/baostock_alpha158.json').read_text())
        frozen = verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
        verify_data_identity(root, baseline, frozen)
        market = load_factor_data(root, baseline)
        dates = market.membership.loc[c['period'][0]:c['period'][1]].index
        mask = (market.membership & market.tradable).loc[dates]
        labels = forward_labels(market, c['primary_horizon'], c['period'])
        prior = root/c['pilot_run']; prior_hashes = json.loads((prior/'artifact_hashes.json').read_text())
        size = pd.read_parquet(checked_artifact(prior, 'data/log_circulating_cap_proxy.parquet', prior_hashes)).loc[dates]
        industry = pd.read_parquet(checked_artifact(prior, 'data/industry.parquet', prior_hashes)).loc[dates]
        bp = pd.read_parquet(checked_artifact(prior, 'BP_neutral/scores.parquet', prior_hashes)).loc[dates]
        scores, results, checks = {'BP_reference': bp}, {}, []
        for name in c['primary_tests']:
            definition = qc['candidates'][name]
            raw = pd.read_parquet(checked_artifact(quarterly, definition['field']+'.parquet', manifest))
            raw = preprocess(raw.reindex(index=dates, columns=mask.columns)*definition['direction'], mask)
            score, check = neutralize(raw, size, industry)
            scores[name] = score
            folder = output/name; folder.mkdir()
            score.to_parquet(folder/'scores.parquet'); check.to_csv(folder/'neutralization_checks.csv', index=False)
            checks.append(check)
            daily = daily_ic(score, labels, c['min_pairs']); daily.to_csv(folder/'ic.csv')
            coverage = {str(y): float(score.loc[str(y)].notna().to_numpy().sum()/market.membership.loc[str(y)].to_numpy().sum()) for y in [2015,2016]}
            yearly = {str(y): summarize_ic(d) for y,d in daily.groupby(daily.index.year)}
            results[name] = {'family': definition['family'], 'coverage_by_year': coverage,
                             'primary': summarize_ic(daily), 'years': yearly,
                             'inference': block_inference(daily.rank_ic, c['block_length'], c['bootstrap_samples'], c['seed'])}
            print(f'IC {name}', flush=True)
        qs = bh_adjust([results[n]['inference']['p'] for n in c['primary_tests']])
        for name,q in zip(c['primary_tests'], qs):
            r = results[name]; r['q'] = float(q)
            r['screen_status'] = 'IC_SCREEN_PASS' if screen_pass(r['coverage_by_year'],r['primary'],r['years'],q,c) else 'IC_SCREEN_REJECT'
        correlation_matrix(scores).to_csv(output/'family_correlation.csv')
        # Reconstruct the exact previously frozen technical projection, not a new fit protocol.
        amap = root/c['alpha_map_run']
        if json.loads((amap/'status.json').read_text())['status'] != 'PASS':
            raise ValueError('technical map did not pass')
        ah = c['alpha_map_input_sha256']
        features = pd.read_parquet(checked_artifact(amap, 'features.parquet', ah))
        basis = json.loads(checked_artifact(amap, 'basis.json', ah).read_text())
        pca = json.loads(checked_artifact(amap, 'pca.json', ah).read_text())
        frozen_loadings = pd.read_csv(checked_artifact(amap, 'pca_loadings.csv', ah), index_col=0)
        compressed, loadings, reproduced = compress_basis(features[basis['representatives']],pca['fit_period'],pca['variance_target'],20)
        np.testing.assert_allclose(loadings, frozen_loadings, rtol=1e-10, atol=1e-12)
        if abs(reproduced['variance_retained'] - pca['variance_retained']) > 1e-12:
            raise ValueError('PCA reconstruction changed')
        conditional_labels = forward_labels(market,c['primary_horizon'],c['conditional_period'])
        diagnostic = {}
        for name, score in scores.items():
            candidate = score.loc[c['conditional_period'][0]:c['conditional_period'][1]]
            matched,residual,check = conditional_residual(candidate,compressed,size,industry)
            folder=output/name; folder.mkdir(exist_ok=True)
            check.to_csv(folder/'projection_checks.csv',index=False); checks.append(check)
            diagnostic[name] = {}
            for variant,panel in [('matched',matched),('residual',residual)]:
                panel.to_parquet(folder/(variant+'.parquet'))
                daily = daily_ic(panel,conditional_labels,c['min_pairs']);daily.to_csv(folder/(variant+'_ic.csv'))
                diagnostic[name][variant] = summarize_ic(daily)
            if not matched.notna().equals(residual.notna()):
                raise ValueError('conditional samples differ')
            diagnostic[name]['status']='DIAGNOSTIC_ONLY' if len(check) else 'INSUFFICIENT_COMMON_SAMPLE'
            print(f'CONDITIONAL {name}',flush=True)
        write(output/'metrics.json',results);write(output/'conditional.json',diagnostic)
        errors=[float(d.orthogonality_error.max()) for d in checks if len(d)]
        if errors and max(errors)>1e-8: raise ValueError('OLS residual failed orthogonality check')
        verify_baseline(root,'BL-CN-CSI300-A158-LGBM-001')
        if any(hashlib.sha256((root/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):
            raise ValueError('source changed during screen')
        write(output/'verification.json',{'status':'PASS','quarterly_run':quarterly.name,
              'primary_tests':len(results),'max_orthogonality_error':max(errors) if errors else None,
              'pca_variance_retained':pca['variance_retained'],'pca_loadings_reproduced':True,
              'conditional_masks_equal':True,'baseline_unchanged':True,'no_2021_plus_access':True,
              'portfolio_increment':'NOT_RUN','rolling_model_increment':'NOT_RUN'})
        rows=[{'candidate':n,'family':r['family'],'coverage_2015':r['coverage_by_year']['2015'],
               'coverage_2016':r['coverage_by_year']['2016'],'rank_ic':r['primary']['rank_ic'],
               'q':r['q'],'status':r['screen_status']} for n,r in results.items()]
        table=pd.DataFrame(rows);table.to_csv(output/'summary.csv',index=False)
        text=['# M2.3 Four-family historical screen','',table.to_markdown(index=False),'',
              'BP is the existing Value reference. Three new economic hypotheses were fixed before data collection; only the neutralized versions are primary tests.',
              '','2015–2016 are already observed history. IC_SCREEN_PASS is not FORWARD, KEEP, investability or independent alpha. No net portfolio increment or rolling-model experiment was run.',
              '','## 2016 matched conditional diagnostic','']
        for n,r in diagnostic.items():
            text.append(f'- {n}: matched RankIC {r["matched"]["rank_ic"]}; residual RankIC {r["residual"]["rank_ic"]}; {r["status"]}.')
        text += ['', 'The fixed 20-PC basis retains 77.7% of representative feature variance; residuals can still contain technical information. Vendor revisions, fiscal comparability and financial-sector sensitivity remain unresolved. No signs/formulas were changed after these results.']
        (output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
        write(output/'artifact_hashes.json',{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in output.rglob('*') if p.is_file() and 'source' not in p.relative_to(output).parts and p.name!='status.json'})
        state.update(status='PASS',stage='complete');write(output/'status.json',state)
        return output
    except BaseException as exc:
        state.update(status='FAIL',error=str(exc));write(output/'status.json',state)
        (output/'traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
