import json
import pandas as pd
import pytest
from quant_research.integrity import seal_dataset, verify_dataset


def dataset(tmp_path, config):
    pd.DataFrame({'close': [10.]}).to_parquet(tmp_path / 'SH600000.parquet')
    pd.DataFrame({'datetime': ['2020-01-02']}).to_parquet(tmp_path / 'calendar.parquet')
    pd.DataFrame({'instrument': ['SH600000']}).to_parquet(tmp_path / 'membership.parquet')
    (tmp_path / 'manifest.json').write_text(json.dumps({'data_config': config, 'bars': [{'instrument': 'SH600000'}]}))


def test_canonical_modification_and_config_mismatch_fail_closed(tmp_path):
    config = {'name': 'test', 'data_start': '2020-01-01', 'data_end': '2020-01-03',
              'segments': {'train': ['2020-01-01', '2020-01-02']}}
    dataset(tmp_path, config)
    seal_dataset(tmp_path)
    verify_dataset(tmp_path, config)
    with pytest.raises(ValueError, match='configuration'):
        verify_dataset(tmp_path, {**config, 'data_end': '2020-01-06'})
    pd.DataFrame({'close': [99.]}).to_parquet(tmp_path / 'SH600000.parquet')
    with pytest.raises(ValueError, match='checksum'):
        verify_dataset(tmp_path, config)


def test_unlisted_extra_canonical_file_is_rejected(tmp_path):
    config = {'name': 'test', 'data_start': '2020-01-01', 'data_end': '2020-01-03', 'segments': {}}
    dataset(tmp_path, config)
    seal_dataset(tmp_path)
    pd.DataFrame({'close': [20.]}).to_parquet(tmp_path / 'SZ000001.parquet')
    with pytest.raises(ValueError, match='file set'):
        verify_dataset(tmp_path, config)


def test_extra_file_cannot_be_legitimized_by_sealing(tmp_path):
    config = {'name': 'test', 'data_start': '2020-01-01', 'data_end': '2020-01-03', 'segments': {}}
    dataset(tmp_path, config)
    pd.DataFrame({'close': [20.]}).to_parquet(tmp_path / 'SZ000001.parquet')
    with pytest.raises(ValueError, match='file set'):
        seal_dataset(tmp_path)
