"""获取官方数据，并按固定商品范围保留完整 5-core 交互历史。"""
import csv
import gzip
import hashlib
import json
import subprocess
from datetime import datetime, timezone

from src.config import (
    RAW_DIR, INTERIM_DIR, REVIEW_URL, META_URL, REVIEW_FILE, META_FILE,
    COHORT_FILE, MANIFEST_FILE, META_RECORD_LIMIT, META_BYTE_LIMIT,
    MAX_REVIEW_BYTES, MAX_META_SOURCE_BYTES,
)


def curl(*arguments):
    return subprocess.run(
        ['curl', '-f', '-s', '-S', '-L', '--connect-timeout', '15',
         '--max-time', '600', *arguments], check=True, capture_output=True,
    )


def source_info(url):
    """先 HEAD 核对文件规模；没有可靠长度时停止，不盲目下载。"""
    headers = curl('-I', url).stdout.decode()
    lengths = [int(line.split(':', 1)[1].strip()) for line in headers.splitlines()
               if line.lower().startswith('content-length:')]
    if not lengths:
        raise RuntimeError(f'无法确认文件大小: {url}\n{headers}')
    etags = [line.split(':', 1)[1].strip() for line in headers.splitlines()
             if line.lower().startswith('etag:')]
    return {'url': url, 'source_bytes': lengths[-1],
            'etag': etags[-1] if etags else None}


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(block)
    return {'file': str(path.relative_to(RAW_DIR.parent.parent)),
            'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def get_reviews(info):
    if info['source_bytes'] > MAX_REVIEW_BYTES:
        raise RuntimeError('5-core 文件超过 100 MiB 预算，请重新审查下载策略。')
    if not REVIEW_FILE.exists():
        partial = REVIEW_FILE.with_suffix('.gz.part')
        curl('-o', str(partial), REVIEW_URL)
        if partial.stat().st_size != info['source_bytes']:
            raise RuntimeError('评论下载长度不完整，保留 .part 供排查。')
        partial.replace(REVIEW_FILE)
    if REVIEW_FILE.stat().st_size != info['source_bytes']:
        raise RuntimeError('本地评论文件长度与官方 HEAD 不一致。')


def get_metadata(info):
    if info['source_bytes'] > MAX_META_SOURCE_BYTES:
        raise RuntimeError('metadata 源文件超过 1 GiB，需重新检查策略。')
    prefix = RAW_DIR / 'metadata_prefix.gz.part'
    headers = RAW_DIR / 'metadata_range_headers.txt'
    # 只请求前 16 MiB 压缩字节；严格核对 Range，避免下载完整大文件。
    curl('--range', f'0-{META_BYTE_LIMIT - 1}', '--max-filesize',
         str(META_BYTE_LIMIT), '-D', str(headers), '-o', str(prefix), META_URL)
    header_text = headers.read_text().lower()
    expected = f'content-range: bytes 0-{META_BYTE_LIMIT - 1}/{info["source_bytes"]}'
    if expected not in header_text or prefix.stat().st_size != META_BYTE_LIMIT:
        raise RuntimeError('服务器未按预期提供指定字节范围。')
    partial = META_FILE.with_suffix('.jsonl.part')
    with gzip.open(prefix, 'rt', encoding='utf-8') as source, partial.open('w') as target:
        for index in range(META_RECORD_LIMIT):
            line = source.readline()
            if not line:
                raise RuntimeError(f'metadata 不足 {META_RECORD_LIMIT} 行。')
            json.loads(line)  # 只校验，不修改原始字段。
            target.write(line)
    partial.replace(META_FILE)
    info['transferred_bytes'] = prefix.stat().st_size
    prefix.unlink()  # 成功解析后删除临时传输片段，保留真实 JSONL 与响应头。


def build_cohort():
    with META_FILE.open() as file:
        parents = {json.loads(line).get('parent_asin') for line in file}
    parents.discard(None)
    parents.discard('')
    scanned = selected = 0
    partial = COHORT_FILE.with_suffix('.csv.part')
    with gzip.open(REVIEW_FILE, 'rt') as source, partial.open('w', newline='') as target:
        reader = csv.DictReader(source)
        if 'parent_asin' not in (reader.fieldnames or []):
            raise RuntimeError('真实 5-core 文件没有 parent_asin，无法建立商品范围。')
        writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            scanned += 1
            if row['parent_asin'] in parents:
                writer.writerow(row)
                selected += 1
    partial.replace(COHORT_FILE)
    if not selected:
        raise RuntimeError('固定 metadata 范围与 5-core 没有交集，不可继续分析。')
    return {'source_interactions': scanned, 'cohort_interactions': selected,
            'metadata_parent_ids': len(parents)}


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {'status': 'started', 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                'selection': 'metadata source records 1..10000; all matching 5-core interactions'}
    try:
        review_info, meta_info = source_info(REVIEW_URL), source_info(META_URL)
        manifest['sources'] = {'reviews': review_info, 'metadata': meta_info}
        print(json.dumps(manifest['sources'], indent=2), flush=True)
        get_reviews(review_info)
        get_metadata(meta_info)
        manifest.update(build_cohort())
        manifest['files'] = [fingerprint(REVIEW_FILE), fingerprint(META_FILE), fingerprint(COHORT_FILE)]
        manifest['status'] = 'complete'
    except Exception as error:
        manifest['status'] = 'failed'
        manifest['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            manifest['stderr'] = error.stderr.decode(errors='replace')
        raise
    finally:
        MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
