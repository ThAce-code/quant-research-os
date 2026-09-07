"""Finish this finite long-running data job: audit, document, and publish if Git is clean."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'experiments/r2/r2_baostock_event_bulk_v1'


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').rstrip('\r\n')
def write(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def replace_block(path,body):
    text=path.read_text(encoding='utf-8')
    start='<!-- BAOSTOCK_BULK_CURRENT_START -->';end='<!-- BAOSTOCK_BULK_CURRENT_END -->'
    assert text.count(start)==text.count(end)==1
    before,rest=text.split(start);_,after=rest.split(end)
    path.write_text(before+start+'\n'+body+'\n'+end+after,encoding='utf-8')


def main():
    deadline=time.monotonic()+10800
    while time.monotonic()<deadline:
        state=read(RUN/'status.json')
        if state['status'] in ['PASS','STOPPED']:break
        time.sleep(10)
    else:raise TimeoutError('Finite collection deadline exceeded; no completion claimed')
    # The collector writes the archive manifest just after its final status.
    for _ in range(10):
        if (RUN/'artifact_hashes.json').exists():break
        time.sleep(1)
    subprocess.run([sys.executable,str(ROOT/'scripts/audit_r2_baostock_events.py')],cwd=ROOT,check=True)
    result=read(RUN/'audit/summary.json')
    # Concurrent user changes never get staged or committed by the background job.
    if git('status','--porcelain'):
        write(RUN/'finalization.json',{'status':'AUDITED_LOCAL_RESULTS_READY','published':False,
             'reason':'Workspace has other changes; Git and context left untouched','summary':'audit/summary.json'})
        return
    directory=ROOT/'docs/results/r2_baostock_event_bulk';directory.mkdir(exist_ok=False)
    for name in ['summary','requests','missing_requests','source_hashes','case_comparison','eastmoney_comparison']:
        (directory/f'{name}.json').write_bytes((RUN/f'audit/{name}.json').read_bytes())
    collection=result['collection'];done=collection['status']=='PASS'
    outcome='采集完成' if done else '采集停止，部分完成'
    rows=['| 期间 | 类型 | 目标期原始行 | 窗口内历史成员事件行 | 公司数 |',
          '|---|---|---:|---:|---:|']
    for r in result['coverage']:
        rows.append(f"| {r['period']} | {r['kind']} | {r['raw_target_rows']} | {r['eligible_member_notice_rows']} | {r['eligible_companies']} |")
    report=f'''# BaoStock R2 批量事件数据：{outcome}

用户在单次财务恢复探测成功后明确要求批量采集。配置冻结于a9369ad；run为r2_baostock_event_bulk_v1。计划345只股票、预告和快报两个接口，共690项；股票来自2015/2016年1–4月历史CSI300成员并集及三个审计案例。

实际成功完成{collection['completed']}/{collection['planned_queries']}项，非空响应{collection['nonempty']}项，共{collection['rows']}行原始记录。状态{collection['status']}，结束时间{collection.get('finished_at','')}。错误：{collection.get('error','无')}。

串行请求、每项结束后间隔至少1秒，无自动重试；访问拒绝、通信错误或分页歧义停止整个批次，成功/失败/未请求项分别保留。不改写旧BaoStock失败记录、巨潮原件或东方财富面板。

合并查询区间2015-01-01至2016-04-30以减少请求，接口按公告/统计或更新日期筛选，返回的其他季度均保留在原始归档。以下才是针对2015/2016Q1的筛选统计；公司数不是每日因子覆盖率。

{chr(10).join(rows)}

源核验检查全部响应哈希、请求身份、返回代码、字段宽度、股票代码及逐项核销。四项针对性测试通过，验证报告期与公告时间、其他季度排除和历史成员边界；没有执行模型回归。注册库数量详见summary.json，本批没有写入因子评价、读取价格/收益或打开2021–2025。

原件案例对照：{json.dumps(result['case_status_counts'],ensure_ascii=False)}。东方财富ADD_AMP上下界对照：{json.dumps(result['eastmoney_comparison_counts'],ensure_ascii=False)}。仅比对同日预告及同比上下界，不等于净利润金额/全文验证，也不证明两个供应商来源独立。未返回同日版本时不能把修正值回填首次公告日。

数据准入仍为NOT_READY_PENDING_ORIGINAL_VERSION_AND_CONTENT_VALIDATION。下一步把本批结构化结果和211份已归档巨潮文书逐事件核对，保留缺失及源冲突，再冻结有限事件因子的研究假设与预算。采集成功不等于完整历史版本PIT或独立Alpha。

[汇总](summary.json)、[成功请求](requests.json)、[未完成请求](missing_requests.json)、[原件案例对照](case_comparison.json)、[跨源对照](eastmoney_comparison.json)、[原始响应哈希](source_hashes.json)。原始响应与classified_rows.json留在本地实验目录。
'''
    (directory/'report.md').write_text(report,encoding='utf-8')
    body=f"**BaoStock批量事件数据最新状态：{outcome}。** 预告/快报实际完成{collection['completed']}/{collection['planned_queries']}项请求，取得{collection['rows']}行原始记录；结束时间{collection.get('finished_at','')}。采集后的逐项核销、哈希与范围审计已完成，研究数值准入仍未通过；2021–2025封存。详见[批量报告](results/r2_baostock_event_bulk/report.md)。此段取代旧的‘仅单次财务探测成功’作为当前采集状态。"
    for name in ['docs/PROJECT_CONTEXT.md','docs/M2_ROADMAP.md']:replace_block(ROOT/name,body)
    sources_path=ROOT/'docs/results/sources.json';sources=read(sources_path)
    for name,meta in sources.items():assert sha(ROOT/name)==meta['sha256'],name
    for path in directory.iterdir():sources[path.relative_to(ROOT).as_posix()]={'source_run':RUN.name,'sha256':sha(path)}
    write(sources_path,sources)
    allowed=['docs/PROJECT_CONTEXT.md','docs/M2_ROADMAP.md','docs/results/sources.json','docs/results/r2_baostock_event_bulk/']
    changed=git('status','--porcelain').splitlines()
    if any(not any(line[3:]==p or (p.endswith('/') and line[3:].startswith(p)) for p in allowed) for line in changed):
        write(RUN/'finalization.json',{'status':'AUDITED_DOCUMENTED','published':False,'reason':'Concurrent Git changes; nothing staged'})
        return
    if git('diff','--cached','--name-only'):raise RuntimeError('Concurrent staged changes; no commit')
    git('add',*allowed)
    git('-c','core.whitespace=cr-at-eol','diff','--cached','--check')
    git('commit','-m','docs(r2): publish completed BaoStock batch outcome and audit')
    git('push','origin','main')
    write(RUN/'finalization.json',{'status':'AUDITED_DOCUMENTED_PUBLISHED','published':True,
         'commit':git('rev-parse','HEAD'),'at':datetime.now(timezone.utc).isoformat()})


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        write(RUN/'finalization.json',{'status':'FINALIZATION_FAILED','error':repr(exc),'published':False})
        raise
