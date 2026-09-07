"""Audit cached event timestamps, announcement counterexamples and membership only."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def known_forecast(events,signal_date):
    """One code/period fixture; forecasts may legitimately precede fiscal period end."""
    if len({(r['code'],r['period']) for r in events})>1:raise ValueError('one company and period required')
    if len({r['notice_date'] for r in events})!=len(events):raise ValueError('ambiguous same-day versions')
    known=[r for r in events if r['notice_date']<signal_date]
    return max(known,key=lambda r:r['notice_date']) if known else None


def main():
    run=ROOT/'experiments/r2/r2_event_feasibility_v1';c=read(run/'protocol.json')
    for name,h in read(run/'artifact_hashes.json').items():assert sha(run/name)==h,name
    membership_path=ROOT/'data/canonical/baostock_alpha158_csi300_2008_2020/membership.parquet'
    members=pd.read_parquet(membership_path);members['code']=members.instrument.str[2:]
    calendar_path=membership_path.parent/'calendar.parquet';calendar=pd.DatetimeIndex(pd.read_parquet(calendar_path).datetime)
    audits=[]
    for kind in c['reports']:
        for period in c['report_dates']:
            frame=pd.DataFrame(read(run/f'{kind}_{period}_rows.json'))
            # This is event reach, not daily feature coverage. No prices or labels are read.
            codes=set();count=0
            for row in frame.itertuples():
                pos=calendar.searchsorted(pd.Timestamp(row.NOTICE_DATE),side='right')
                if pos>=len(calendar):continue
                day=calendar[pos];matches=members[members.code.eq(row.SECURITY_CODE)]
                if ((pd.to_datetime(matches.start)<=day)&(pd.to_datetime(matches.end)>=day)).any():codes.add(row.SECURITY_CODE);count+=1
            end=f'{period[:4]}-04-30';start=f'{period[:4]}-01-01'
            union=members[(pd.to_datetime(members.start)<=end)&(pd.to_datetime(members.end)>=start)].code.nunique()
            late=(pd.to_datetime(frame.NOTICE_DATE)>pd.Timestamp(end)).sum()
            row={'kind':kind,'period':period,'rows':len(frame),'unique_codes':frame.SECURITY_CODE.nunique(),
                 'historical_csi300_event_rows':count,'historical_csi300_event_codes':len(codes),
                 'jan_apr_historical_member_union':int(union),'notices_after_april':int(late),
                 'revision_history_complete':False}
            if kind=='forecast':
                finite=frame[['ADD_AMP_LOWER','ADD_AMP_UPPER','PREDICT_RATIO_LOWER','PREDICT_RATIO_UPPER']].notna().all(axis=1)
                delta=(frame.ADD_AMP_LOWER-frame.PREDICT_RATIO_LOWER).abs().gt(1e-6)|(frame.ADD_AMP_UPPER-frame.PREDICT_RATIO_UPPER).abs().gt(1e-6)
                row.update(all_is_latest=bool(frame.IS_LATEST.eq('T').all()),paired_range_rows=int(finite.sum()),different_range_rows=int((finite&delta).sum()),
                           update_timestamp_available='UPDATE_DATE' in frame.columns)
            else:
                row.update(update_after_notice=int((pd.to_datetime(frame.UPDATE_DATE)>pd.to_datetime(frame.NOTICE_DATE)).sum()),
                           eitime_after_notice=int((pd.to_datetime(frame.EITIME)>pd.to_datetime(frame.NOTICE_DATE)).sum()),
                           eitime_semantics='UNVERIFIED; not assumed to be historical public availability')
            audits.append(row)
    cases=read(ROOT/'configs/r2/document_cases.json');comparisons=[]
    for case in cases['cases']:
        rows=read(run/f"forecast_{case['period']}_rows.json")
        matching=[r for r in rows if r['SECURITY_CODE']==case['code'] and r['PREDICT_FINANCE_CODE']=='004']
        assert len(matching)==1;row=matching[0]
        amount_match=[row['PREDICT_AMT_LOWER'],row['PREDICT_AMT_UPPER']]==[case['net_profit_lower_yuan'],case['net_profit_upper_yuan']]
        amp_match=[row['ADD_AMP_LOWER'],row['ADD_AMP_UPPER']]==[case['yoy_lower_percent'],case['yoy_upper_percent']]
        ratio_match=np.allclose([row['PREDICT_RATIO_LOWER'],row['PREDICT_RATIO_UPPER']],[case['yoy_lower_percent'],case['yoy_upper_percent']],atol=1e-6)
        assert amount_match and amp_match and not ratio_match
        comparisons.append({'code':case['code'],'period':case['period'],'notice_matches':row['NOTICE_DATE'][:10]==case['notice_date'],
            'document':case['document'],'amount_matches':amount_match,'ADD_AMP_matches':amp_match,'PREDICT_RATIO_matches':bool(ratio_match),
            'document_yoy_range':[case['yoy_lower_percent'],case['yoy_upper_percent']],
            'provider_predict_ratio':[row['PREDICT_RATIO_LOWER'],row['PREDICT_RATIO_UPPER']],
            'wrapper_INCREASE_JZ':row['INCREASE_JZ'],'earlier_version_present_in_response':False if case['earlier_notice_date_mentioned'] else None})
    fixture=cases['version_fixture']
    assert known_forecast(fixture,'2015-01-24') is None
    assert known_forecast(fixture,'2015-01-26')['document_id']=='2015-011'
    assert known_forecast(fixture,'2015-04-09')['document_id']=='2015-011'
    assert known_forecast(fixture,'2015-04-10')['document_id']=='2015-019'
    timeline=[{'signal_date':d,'document_id':known_forecast(fixture,d)['document_id'] if known_forecast(fixture,d) else None} for d in ['2015-01-24','2015-01-26','2015-04-09','2015-04-10']]
    output=ROOT/'experiments/r2/event_audit_analysis.json'
    write(output,{'status':'PASS_AUDIT','data_admission':'NOT_READY_FOR_FACTOR_RESEARCH','returns_loaded':False,'api_requests':len(read(run/'requests.json')),
        'coverage':audits,'document_counterexamples':comparisons,'version_timeline_fixture':timeline,
        'limits':['Purposive examples cannot estimate vendor-wide error rates','ADD_AMP matches three source documents; global vintage correctness remains unverified',
                  'Latest-only sample lacks earlier forecasts','EITIME semantics and express announcement content require primary-source checks',
                  'Historical CSI300 reach is counted at first trading day strictly after notice; Jan-Apr union is descriptive, not daily factor coverage'],
        'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [membership_path,calendar_path,ROOT/'configs/r2/document_cases.json',Path(__file__),run/'artifact_hashes.json']}})
    print(json.dumps(read(output),indent=2,ensure_ascii=False))


if __name__=='__main__':main()
