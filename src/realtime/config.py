"""实时采集配置；不修改历史建模配置。"""
from src.config import PROJECT_ROOT

KEYWORD = 'garden hose'
SEARCH_URL = 'https://www.amazon.com/s?k=garden+hose'
MAX_PRODUCTS = 20
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
REQUEST_TIMEOUT = (15, 30)
REALTIME_DIR = PROJECT_ROOT / 'data' / 'realtime'
RAW_DIR = REALTIME_DIR / 'raw'
DATABASE_FILE = REALTIME_DIR / 'amazon_garden_realtime.db'
LOG_FILE = PROJECT_ROOT / 'outputs' / 'realtime_collection.log'
RESULT_DIR = PROJECT_ROOT / 'outputs' / 'realtime'
REPORT_DIR = PROJECT_ROOT / 'reports'
FIELDS = ('crawl_time', 'keyword', 'search_position', 'asin', 'title',
          'price', 'rating', 'review_count', 'product_url')
