"""按照明确预算读取真实原始评论，仅用于确认 schema。"""
import gzip
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone

from src.config import (
    RAW_DIR, OUTPUT_DIR, RAW_REVIEW_URL, RAW_REVIEW_DOWNLOAD_LIMIT,
    RAW_SCHEMA_BYTE_LIMIT, RAW_SCHEMA_RECORD_LIMIT, RAW_SCHEMA_FILE,
)
from src.download_data import curl, source_info, fingerprint
from src.profiling import parse_time


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    info = source_info(RAW_REVIEW_URL)
    info['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
    info['download_limit_bytes'] = RAW_REVIEW_DOWNLOAD_LIMIT
    print(json.dumps(info, indent=2), flush=True)
    if info['source_bytes'] <= RAW_REVIEW_DOWNLOAD_LIMIT:
        compressed = RAW_DIR / 'Patio_Lawn_and_Garden_raw.jsonl.gz'
        curl('--max-filesize', str(RAW_REVIEW_DOWNLOAD_LIMIT), '-o', str(compressed), RAW_REVIEW_URL)
        if compressed.stat().st_size != info['source_bytes']:
            raise RuntimeError('原始文件下载长度不一致。')
        info['mode'] = 'complete_download_schema_probe'
    else:
        compressed = RAW_DIR / 'raw_review_schema_prefix.gz.part'
        headers = RAW_DIR / 'raw_review_schema_range_headers.txt'
        curl('--range', f'0-{RAW_SCHEMA_BYTE_LIMIT-1}', '--max-filesize',
             str(RAW_SCHEMA_BYTE_LIMIT), '-D', str(headers), '-o', str(compressed), RAW_REVIEW_URL)
        expected = f'content-range: bytes 0-{RAW_SCHEMA_BYTE_LIMIT-1}/{info["source_bytes"]}'
        if expected not in headers.read_text().lower():
            raise RuntimeError('Range 响应范围不符合预期，停止解析。')
        if compressed.stat().st_size != RAW_SCHEMA_BYTE_LIMIT:
            raise RuntimeError('Range 响应长度不符合预期。')
        info['mode'] = 'range_schema_probe_only'
    info['transferred_bytes'] = compressed.stat().st_size
    types, present, years = {}, Counter(), Counter()
    active_parents, active_users = {}, {}
    verified_true = 0
    with gzip.open(compressed, 'rt', encoding='utf-8') as source, RAW_SCHEMA_FILE.open('w') as target:
        for index in range(RAW_SCHEMA_RECORD_LIMIT):
            line = source.readline()
            if not line:
                raise RuntimeError('样本记录数不足。')
            row = json.loads(line)
            target.write(line)
            for field, value in row.items():
                present[field] += 1
                types.setdefault(field, Counter())[type(value).__name__] += 1
            verified_true += int(row.get('verified_purchase') is True)
            time = parse_time(row.get('timestamp'))
            if time and 2018 <= time.year <= 2023:
                year = str(time.year)
                years[year] += 1
                active_parents.setdefault(year, set()).add(row.get('parent_asin'))
                active_users.setdefault(year, set()).add(row.get('user_id'))
    info['sample_records'] = RAW_SCHEMA_RECORD_LIMIT
    info['field_types'] = {k: dict(v) for k, v in types.items()}
    info['field_present_counts'] = dict(present)
    info['verified_true_sample_records'] = verified_true
    info['recent_years_sample_only'] = [
        {'year': year, 'interactions': years[str(year)],
         'active_parent_asin': len(active_parents.get(str(year), set()) - {None, ''}),
         'active_users': len(active_users.get(str(year), set()) - {None, ''})}
        for year in range(2018, 2024)
    ]
    info['sample_file'] = fingerprint(RAW_SCHEMA_FILE)
    info['limitations'] = 'Source-order prefix; schema verification only; no full-product histories; not category totals.'
    (OUTPUT_DIR / 'raw_review_probe.json').write_text(json.dumps(info, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr.decode(errors='replace'))
        raise
