import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    BASE_DIR = Path(__file__).parent.parent

    DATABASE_PATH = os.getenv('DATABASE_PATH', str(BASE_DIR / 'data' / 'company_users.db'))
    
    DATASET_PATH = str(BASE_DIR / 'data' / 'dataset-it-profession.csv')
    
    MODEL_PATH = str(BASE_DIR / 'gemma-3-1b-it-Q4_K_M.gguf')
    
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    LOG_LEVEL = 'INFO'
    LOG_FILE = str(BASE_DIR / 'logs' / 'bot.log')
    
    MAX_WORKERS = 4
    TIMEOUT_SECONDS = 30
    
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model file not found at {MODEL_PATH}")
    
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

config = Config()
