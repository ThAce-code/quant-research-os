"""Reproducible first M2 research run using the frozen M0 market snapshot."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import traceback

import numpy as np
import pandas as pd
from filelock import FileLock

from ..baostock_data import BaoStockCache
from ..factors.engine import strict_write_json as write, verify_baseline, clean_json
from ..factors.provenance import verify_data_identity
from ..factors.data import load_factor_data, preprocess, forward_labels
from ..factors.analytics import daily_ic, summarize_ic, correlation_matrix
from ..factors.portfolio import run_portfolios, portfolio_metrics
from ..factors.registry import FactorRegistry
from ..integrity import file_hashes
from .core import asof_events, circulating_cap, neutralize, block_inference, bh_adjust


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root, config, market, baseline, output):
    dates = market.membership.loc[config['start']:config['end']].index
    symbols = market.membership.loc[dates].any()[lambda s: s].index.tolist()
    fields = list(config['factors'].values())
    panels = {f: pd.DataFrame(np.nan, index=dates, columns=market.membership.columns) for f in fields}
    industry = pd.DataFrame(index=dates, columns=market.membership.columns, dtype=object)
    size = panels[fields[0]].copy()
    canonical = root / 'data/canonical' / baseline['name']
    snapshots, audits, samples = [], [], []
    with BaoStockCache(root / 'data/raw/baostock') as source:
        # Month-end snapshots are only available after their query date. Never
        # backdate an observed snapshot to the earlier vendor updateDate.
        for date in pd.date_range(pd.Timestamp(config['start']) - pd.offsets.MonthEnd(1), config['end'], freq='ME'):
            text = str(date.date())
            frame = source.query('query_stock_industry', date=text)
            if pd.to_datetime(frame.updateDate).gt(date).any() or frame.code.duplicated().any():
                raise ValueError('invalid historical industry snapshot')
            frame['snapshot_date'] = date
            snapshots.append(frame)
        events = pd.concat(snapshots, ignore_index=True)
        events.to_parquet(output / 'industry_events.parquet', index=False)
        for i, symbol in enumerate(symbols):
            code = symbol[:2].lower() + '.' + symbol[2:]
            frame = source.query('query_history_k_data_plus', allow_empty=True, code=code,
                                 fields='date,code,' + ','.join(fields), start_date=config['start'],
                                 end_date=config['end'], frequency='d', adjustflag='3')
            if not frame.empty:
                frame['date'] = pd.to_datetime(frame.date)
                if frame.date.duplicated().any() or not frame.date.isin(dates).all():
                    raise ValueError('invalid valuation dates')
                for field in fields:
                    # Empty vendor fields are missing; malformed nonempty values fail.
                    val = pd.to_numeric(frame.set_index('date')[field].replace('', np.nan), errors='raise')
                    panels[field][symbol] = val.reindex(dates).shift(1)
            bars = pd.read_parquet(canonical / f'{symbol}.parquet').set_index('datetime').reindex(dates)
            bars['is_suspended'] = bars.is_suspended.fillna(True).astype(bool)
            cap = circulating_cap(bars)
            size[symbol] = np.log(cap.where(cap.gt(0)))
            e = events.loc[events.code.eq(code), ['snapshot_date', 'industry']].copy()
            e['industry'] = e.industry.replace('', np.nan)
            joined = asof_events(e, dates, 'snapshot_date', ['industry'], max_age=62)
            industry[symbol] = joined.industry
            audits.append({'symbol': symbol, 'valuation_rows': len(frame),
                           'size_days': int(cap.notna().sum()),
                           'industry_days': int(joined.industry.notna().sum())})
            if i % 25 == 0 or i == len(symbols)-1:
                print(f'DATA {i+1}/{len(symbols)} {symbol}', flush=True)
        # Real publication join and share-unit crosschecks, not a claim of full
        # quarterly coverage. Broad quarterly factor extraction is a later batch.
        for code in ['sh.600000', 'sz.000001', 'sh.600519']:
            frames = [source.query('query_profit_data', allow_empty=True, code=code, year=year, quarter=q)
                      for year in [2014, 2015, 2016] for q in [1, 2, 3, 4]]
            records = pd.concat(frames, ignore_index=True)
            for col in ['roeAvg', 'totalShare', 'liqaShare']:
                records[col] = pd.to_numeric(records[col].replace('', np.nan), errors='raise')
            joined = asof_events(records, dates, 'pubDate', ['roeAvg', 'totalShare', 'liqaShare'])
            records.to_parquet(output / f'{code}_financial_events.parquet', index=False)
            joined.to_parquet(output / f'{code}_financial_daily.parquet')
            symbol = code.replace('.', '').upper()
            bars = pd.read_parquet(canonical / f'{symbol}.parquet').set_index('datetime').reindex(dates)
            shares = np.exp(size[symbol]) / bars.close
            ratio = shares / joined.liqaShare
            samples.append({'code': code, 'reports': len(records),
                            'median_inferred_to_reported_circulating_shares': ratio.median(),
                            'financial_daily_coverage': joined.roeAvg.notna().mean()})
        write(output / 'requests.json', source.manifest)
    for field, panel in panels.items():
        panel.to_parquet(output / f'{field}.parquet')
    size.to_parquet(output / 'log_circulating_cap_proxy.parquet')
    industry.to_parquet(output / 'industry.parquet')
    membership = market.membership.loc[dates]
    coverage = {field: float((panel.notna() & membership).to_numpy().sum() / membership.to_numpy().sum())
                for field, panel in {**panels, 'size': size, 'industry': industry}.items()}
    write(output / 'quality.json', {'coverage': coverage, 'instruments': audits, 'financial_samples': samples,
           'pit_level': config['pit_level'], 'quarterly_scope': 'three stock infrastructure audit only',
           'size_definition': 'raw close * raw volume / (turn_percent / 100); excludes turn < 0.01 percent',
           'industry': config['industry_sampling'], 'valuation_lag': 'one trading day; no fill',
           'limitations': ['vendor revisions unknown', 'monthly industry changes detected with delay',
                          'quarterly share comparison can differ due to intervening corporate actions']})
    return panels, size, industry


def run(root):
    root = Path(root)
    with FileLock(str(root / 'data/factor_engine.lock'), timeout=0):
        return _run(root)


def _run(root):
    config = json.loads((root / 'configs/factors/m2_first.json').read_text(encoding='utf-8'))
    baseline = json.loads((root / 'configs/experiments/baostock_alpha158.json').read_text(encoding='utf-8'))
    # This pilot cannot silently become a lockbox evaluation by editing dates.
    if config['start'] != '2014-12-01' or config['end'] != '2016-12-31':
        raise ValueError('pilot dates fixed; register a new experiment for other periods')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = root / 'experiments/m2' / config['name'] / run_id
    output.mkdir(parents=True)
    print(f'M2_RUN {output}', flush=True)
    state = {'status': 'RUNNING', 'stage': 'source_freeze', 'run_id': run_id}
    registry = FactorRegistry(root / 'data/m2_factor_registry.sqlite')
    registered, recorded = [], []
    try:
        write(output / 'status.json', state)
        write(output / 'config.json', config)
        sources = list((root / 'src/quant_research').rglob('*.py')) + [root / 'configs/factors/m2_first.json', root / 'scripts/run_m2.py', root / 'run-m2.ps1']
        hashes = {str(p.relative_to(root)): digest(p) for p in sources}
        for name in hashes:
            target = output / 'source' / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, target)
        write(output / 'source_hashes.json', hashes)
        frozen = verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
        identity = verify_data_identity(root, baseline, frozen)
        market = load_factor_data(root, baseline)
        provider = root / 'data/qlib' / baseline['name']
        if file_hashes(provider, '**/*') != frozen['original_provenance']['qlib_files_sha256']:
            raise ValueError('Qlib data identity changed')
        data_dir = output / 'data'; data_dir.mkdir()
        state['stage'] = 'data_preparation'; write(output / 'status.json', state)
        panels, size, industry = prepare(root, config, market, baseline, data_dir)
        data_hashes = {p.name: digest(p) for p in data_dir.iterdir() if p.is_file()}
        write(output / 'data_manifest.json', {'baseline_identity': identity, 'files': data_hashes})
        dates = size.index
        mask = market.membership.loc[dates] & market.tradable.loc[dates]
        scores, checks = {}, {}
        for name, field in config['factors'].items():
            raw = preprocess(1 / panels[field].where(panels[field].gt(0)), mask)
            scores[name + '_raw'] = raw
            scores[name + '_neutral'], checks[name] = neutralize(raw, size, industry)
            checks[name].to_csv(output / f'{name}_neutralization_checks.csv', index=False)
        reference = preprocess(-market.fields['returns'].rolling(20, min_periods=20).std().loc[dates], mask)
        reference, checks['reference'] = neutralize(reference, size, industry)
        scores['LOWVOL_reference'] = reference
        # Compare blends to matched-reference portfolios so missing candidates
        # cannot masquerade as incremental alpha via a different universe.
        for name in config['factors']:
            candidate = scores[name + '_neutral']
            common = candidate.notna() & reference.notna()
            matched = preprocess(reference, common)
            scores[name + '_matched_reference'] = matched
            scores[name + '_blend'] = ((1-config['blend_candidate_weight']) * matched
                                     + config['blend_candidate_weight'] * preprocess(candidate, common))
        state['stage'] = 'factor_evaluation'; write(output / 'status.json', state)
        import qlib
        qlib.init(provider_uri=str(provider), region='cn', kernels=1, expression_cache=None, dataset_cache=None)
        segment = [config['evaluation_start'], config['end']]
        expected = dates[(dates >= segment[0]) & (dates <= segment[1])]
        labels = {h: forward_labels(market, h, segment) for h in config['horizons']}
        for h, label in labels.items(): label.to_parquet(output / f'labels_h{h}.parquet')
        results, daily_primary = {}, {}
        for name, score in scores.items():
            key = 'M2_' + name
            definition = {'name': key, 'family': 'value' if not name.startswith('LOWVOL') else 'volatility',
                          'expression': name + ': see frozen config and source',
                          'hypothesis': 'Higher value yield predicts higher returns; fixed positive orientation',
                          'direction': 1, 'source': 'baostock_revision_unknown', 'paper': None,
                          'generator': 'human_preregistered', 'version': 1}
            registry.register(key, definition); registered.append(key)
            folder = output / name; folder.mkdir()
            score.to_parquet(folder / 'scores.parquet')
            result = {'coverage': float((score.loc[expected].notna() & mask.loc[expected]).to_numpy().sum()
                                       / market.membership.loc[expected].to_numpy().sum()), 'decay': {}}
            for horizon, label in labels.items():
                daily = daily_ic(score, label)
                daily.to_csv(folder / f'ic_h{horizon}.csv')
                result['decay'][str(horizon)] = summarize_ic(daily)
                if horizon == config['primary_horizon']:
                    daily_primary[name] = daily
                    result['primary'] = summarize_ic(daily)
                    result['years'] = {str(year): summarize_ic(group) for year, group in daily.groupby(daily.index.year)}
                    result['inference'] = block_inference(daily.rank_ic, config['block_length'], config['bootstrap_samples'], config['seed'])
            print(f'BACKTEST {name}', flush=True)
            result['portfolio'] = run_portfolios(score, *segment, baseline['backtest'], folder, expected)
            # Stress doubles explicit historical fees; no assertion of calibrated impact.
            report = pd.read_csv(folder / 'top20_daily.csv', index_col=0, parse_dates=True)
            result['double_fee_net_excess_annual'] = float((report['return'] - 2*report.cost - report.bench).mean()*238)
            result['size_rank_corr'] = daily_ic(score, size).rank_ic.mean()
            write(folder / 'metrics.json', result)
            results[name] = result
        tested = [name + suffix for name in config['factors'] for suffix in ['_raw', '_neutral']]
        qs = bh_adjust([results[name]['inference']['p'] for name in tested])
        incremental = {}
        for name in config['factors']:
            blend = pd.read_csv(output / (name+'_blend') / 'top20_daily.csv', index_col=0, parse_dates=True)
            ref = pd.read_csv(output / (name+'_matched_reference') / 'top20_daily.csv', index_col=0, parse_dates=True)
            delta = (blend['return']-blend.cost) - (ref['return']-ref.cost)
            delta.to_csv(output / f'{name}_paired_increment.csv')
            incremental[name] = block_inference(delta, config['block_length'], config['bootstrap_samples'], config['seed'])
            incremental[name]['annual_delta'] = float(delta.mean()*238)
        delta_q = bh_adjust([incremental[n]['p'] for n in config['factors']])
        for name, q in zip(config['factors'], delta_q): incremental[name]['q'] = q
        write(output / 'incremental.json', incremental)
        correlation_matrix({name:scores[name].loc[expected] for name in tested}).to_csv(output / 'correlation.csv')
        rows = []
        for name, q in zip(tested, qs):
            r = results[name]; r['q'] = float(q)
            base = name.split('_')[0]; inc = incremental[base]
            positive_years = all(v['rank_ic'] is not None and v['rank_ic'] > 0 for v in r['years'].values())
            passes = (r['coverage'] >= config['min_coverage'] and r['primary']['rank_ic'] is not None
                      and r['primary']['rank_ic'] >= config['min_rank_ic'] and q <= config['max_q']
                      and r['portfolio']['top20']['net_excess_annual'] > 0 and positive_years)
            status = 'FORWARD' if passes else 'REJECT'
            r['status'] = status
            r['reason'] = 'historical screening passed; revision and independent confirmation pending' if passes else 'historical screening gates failed'
            rows.append({'factor': name, 'coverage': r['coverage'], 'rank_ic': r['primary']['rank_ic'],
                         'q': q, 'net_excess_annual': r['portfolio']['top20']['net_excess_annual'],
                         'net_mdd': r['portfolio']['top20']['net_mdd'], 'status': status,
                         'neutral_blend_delta_annual': inc['annual_delta'] if name.endswith('_neutral') else None,
                         'increment_supported': bool(name.endswith('_neutral') and inc['low'] is not None and inc['low'] > 0
                                                     and inc['q'] <= config['max_q'] and inc['annual_delta'] >= config['min_increment_annual'])})
        for name, r in results.items():
            report = {'status': r.get('status', 'FORWARD'), 'reasons': [r.get('reason', 'reference/control only, not candidate admission')],
                      'config': {**config, 'segments': {'valid': segment}}, 'splits': {'valid': clean_json(r)},
                      'artifact_directory': str(output/name), 'holdout_status': 'NOT_RUN'}
            write(output / name / 'report.json', report)
            registry.record(run_id, 'M2_'+name, clean_json(report)); recorded.append('M2_'+name)
        summary = pd.DataFrame(rows); summary.to_csv(output / 'summary.csv', index=False)
        lines = ['# M2 首批价值因子探索', '', '样本：2015–2016，历史沪深300；已触碰开发数据，不能作为独立样本外证明。',
                 '三项预注册假设 BP / EP / SP，原始与中性化共六项主检验；主期限5日，20日仅诊断。',
                 '日频估值延迟一个交易日，行业月末快照次交易日可用；供应商历史修订未知。',
                 '市值为流通市值代理；季度财务只完成三只股票的时点与股本核验。', '',
                 '|因子|覆盖率|RankIC|FDR q|含成本超额年化|净值最大回撤|状态|', '|---|---:|---:|---:|---:|---:|---|']
        for row in rows:
            ric = f"{row['rank_ic']:.4f}" if row['rank_ic'] is not None else 'null'
            lines.append(f"|{row['factor']}|{row['coverage']:.1%}|{ric}|{row['q']:.4f}|{row['net_excess_annual']:.2%}|{row['net_mdd']:.2%}|{row['status']}|")
        lines += ['', '## 加入低波参考的边际贡献', '固定25%候选+75%低波，参考与混合组合使用相同可用股票。置信区间按20日块自助法，单位为日收益。']
        for name, inc in incremental.items():
            lines.append(f"- {name}: 超额年化增量 {inc['annual_delta']:.2%}；日增量95%区间 [{inc['low']}, {inc['high']}]；q={inc['q']:.4f}。")
        lines += ['', '运行PASS仅表示产物完成；没有KEEP或独立alpha确认。',
                  '实际费用沿用M0；双倍费用诊断在metrics.json。未校准冲击/容量，行业与市值残差化不保证投资组合行业中性。',
                  '尚待：全量季度财务、Alpha158解剖、完整聚类、滚动模型增量、新时期资格验证及锁箱。']
        (output / 'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
        state['stage'] = 'verification'; write(output / 'status.json', state)
        if any(digest(root/name) != want for name, want in hashes.items()): raise ValueError('source changed during run')
        if any(digest(data_dir/name) != want for name, want in data_hashes.items()): raise ValueError('data changed during run')
        verify_baseline(root, 'BL-CN-CSI300-A158-LGBM-001')
        verification = {'status': 'PASS', 'candidate_variants': len(rows), 'portfolio_variants': len(scores),
                        'baseline_unchanged': True, 'source_unchanged': True, 'data_hashes_verified': True,
                        'max_ols_orthogonality_error': max(float(c.orthogonality_error.max()) for c in checks.values() if not c.empty)}
        if verification['max_ols_orthogonality_error'] > 1e-8: raise ValueError('OLS check failed')
        # Reconcile every saved top20 return path with reported portfolio metrics.
        for name, result in results.items():
            # Qlib benchmark returns are float32; CSV decimal text must be
            # restored to that dtype before promotion in portfolio_metrics.
            saved = pd.read_csv(output/name/'top20_daily.csv', index_col=0, parse_dates=True, dtype={'bench': np.float32})
            recomputed = portfolio_metrics(saved)
            if abs(recomputed['net_excess_annual'] - result['portfolio']['top20']['net_excess_annual']) > 1e-10:
                raise ValueError('portfolio readback mismatch')
        write(output / 'verification.json', verification)
        write(output / 'artifact_hashes.json', {str(p.relative_to(output)):digest(p) for p in output.rglob('*') if p.is_file() and p.name != 'status.json'})
        state.update(status='PASS', stage='complete'); write(output / 'status.json', state)
        write(output.parent / 'latest.json', {'run_id': run_id, 'directory': str(output)})
        print(summary.to_string(index=False), flush=True)
        print(f'PASS {output}', flush=True)
        return output
    except BaseException as exc:
        state.update(status='FAILED', error=str(exc)); write(output / 'status.json', state)
        (output / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        for key in registered:
            if key not in recorded: registry.record_failure(run_id, key, str(exc))
        raise
