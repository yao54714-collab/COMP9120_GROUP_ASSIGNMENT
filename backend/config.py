import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
SYDNEY = ZoneInfo('Australia/Sydney')

def database_config():
    return dict(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '55432')),
                dbname=os.getenv('DB_NAME', 'pawcare'), user=os.getenv('DB_USER', 'pawcare_app'),
                password=os.getenv('DB_PASSWORD', ''), connect_timeout=5)
