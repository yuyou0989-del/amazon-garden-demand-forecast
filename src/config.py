"""路径和数据获取规则集中配置。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / 'data' / 'raw'
INTERIM_DIR = PROJECT_ROOT / 'data' / 'interim'
REPORT_DIR = PROJECT_ROOT / 'reports'
OUTPUT_DIR = PROJECT_ROOT / 'outputs'
CATEGORY = 'Patio_Lawn_and_Garden'
RANDOM_SEED = 42  # 当前使用确定性商品范围，不调用随机抽样。
BASE_URL = 'https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023'
REVIEW_URL = f'{BASE_URL}/benchmark/5core/rating_only/{CATEGORY}.csv.gz'
META_URL = f'{BASE_URL}/raw/meta_categories/meta_{CATEGORY}.jsonl.gz'
REVIEW_FILE = RAW_DIR / f'{CATEGORY}_5core.csv.gz'
META_FILE = RAW_DIR / f'meta_{CATEGORY}_first10000.jsonl'
COHORT_FILE = INTERIM_DIR / 'interactions_cohort.csv'
MANIFEST_FILE = RAW_DIR / 'download_manifest.json'
META_RECORD_LIMIT = 10000
META_BYTE_LIMIT = 16 * 1024 * 1024
MAX_REVIEW_BYTES = 100 * 1024 * 1024
MAX_META_SOURCE_BYTES = 1024 * 1024 * 1024
TIME_START = '1996-01-01T00:00:00+00:00'
TIME_END = '2023-10-01T00:00:00+00:00'

# Stage 1.5 独立产物；不覆盖 Stage 1 原始数据及报告。
RAW_REVIEW_URL = f'{BASE_URL}/raw/review_categories/{CATEGORY}.jsonl.gz'
RAW_REVIEW_DOWNLOAD_LIMIT = 1_500_000_000  # GB 按十进制；实际文件也超过 1.5 GiB。
RAW_SCHEMA_BYTE_LIMIT = 4 * 1024 * 1024
RAW_SCHEMA_RECORD_LIMIT = 2000
RAW_SCHEMA_FILE = RAW_DIR / 'raw_review_schema_sample.jsonl'
STAGE15_DATABASE = OUTPUT_DIR / 'stage15_analysis.sqlite'
STAGE15_SUMMARY = OUTPUT_DIR / 'stage15_summary.json'
HISTORY_START = '2019-01-01'
COHORT_ANCHOR = '2020-01-01'
ANALYSIS_START = '2020-01-01'
# 最终截止日期在读取完整 5-core 后，由最后完整月份计算。
MIN_HISTORY_INTERACTIONS = 12
MIN_HISTORY_ACTIVE_MONTHS = 3
MAX_COHORT_PRODUCTS = 5000
FORMAL_COHORT_FILE = INTERIM_DIR / 'formal_cohort.csv'
ANALYSIS_END = '2023-01-01'  # 排除 2023 年出现明显覆盖突降的时期。
TEST_START = '2022-01-01'
