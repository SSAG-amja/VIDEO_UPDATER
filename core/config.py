import os
from dotenv import load_dotenv

# .env 파일 로드 (로컬 테스트 시 유용)
load_dotenv()

# Database Settings
DB_USER = os.getenv("DB_USER", "gookbob")
DB_PASSWORD = os.getenv("DB_PASSWORD", "gookbob")
DB_NAME = os.getenv("DB_NAME", "ssag_algo")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")

# docker-compose에서 주입한 DATABASE_URL이 있으면 우선 사용하고, 없으면 변수로 조립합니다.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# TMDB API Key
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

# 대용량 파일 다운로드 임시 경로 (필요시 사용)
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")