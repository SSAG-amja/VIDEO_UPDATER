from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.config import DATABASE_URL

# asyncpg 드라이버를 사용하도록 URL 스키마를 변환합니다.
if DATABASE_URL.startswith("postgresql+psycopg2://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = DATABASE_URL

# SQLAlchemy Async Engine 생성
# pool_pre_ping=True: 연결이 끊어졌는지 확인 후 재연결 (안정성 확보)
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True, 
    echo=False  # 개발 중 쿼리 로그를 보고 싶다면 True로 변경
)

# Async Session 객체 생성기
# autocommit, autoflush는 False로 두어 트랜잭션을 수동으로 완벽히 통제합니다.
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def get_db():
    """
    DB 세션을 생성하고 반환하는 제너레이터 함수입니다.
    작업이 끝나면 반드시 세션을 닫도록 보장합니다.
    """
    async with SessionLocal() as db:
        yield db