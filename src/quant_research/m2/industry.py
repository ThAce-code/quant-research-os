"""Contemporaneous taxonomy parsing, including the 2012 text-only transition."""
import re
import pandas as pd


def industry_key(value):
    if pd.isna(value) or not str(value).strip():return None
    value=str(value).strip();match=re.match(r'^([A-S]\d{2})',value)
    if match:return match.group(1)
    if '\ufffd' in value or not re.search(r'[\u4e00-\u9fff]',value):raise ValueError('unrecognized industry encoding')
    return 'LEGACY:'+value


def financial_key(value):
    if value in {'J66','J67','J68','J69'}:return True
    if not isinstance(value,str) or not value.startswith('LEGACY:'):return False
    return value[len('LEGACY:'):].split('-',1)[0] in {'金融保险业','金融业'}
