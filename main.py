import asyncio
import aiohttp
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.database import SessionLocal  # DB 세션 팩토리 (설정해둔 경로에 맞게 임포트)
from synchronizers.meta_sync import MetaSynchronizer
from synchronizers.keyword_sync import KeywordSynchronizer
from synchronizers.person_sync import PersonSynchronizer
from synchronizers.movie_sync import MovieSynchronizer

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("VIDEO_UPDATER_MAIN")


def get_scheduler_config():
    """스케줄러 실행 시각/타임존 설정을 환경변수에서 읽습니다."""
    timezone = os.getenv("SCHEDULER_TIMEZONE", "Asia/Seoul")
    hour = int(os.getenv("SCHEDULER_HOUR", "23"))
    minute = int(os.getenv("SCHEDULER_MINUTE", "0"))
    run_on_startup = os.getenv("RUN_ON_STARTUP", "false").lower() == "true"
    return timezone, hour, minute, run_on_startup

def get_target_dates():
    """TMDB 기준(UTC)으로 Dump/Change API 날짜를 계산합니다."""
    now_utc = datetime.now(timezone.utc)
    
    # 덤프 파일용 포맷 (MM_DD_YYYY) ex: 04_23_2026
    dump_date_str = now_utc.strftime("%m_%d_%Y")
    
    # Change API용 포맷 (YYYY-MM-DD)
    start_date = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = now_utc.strftime("%Y-%m-%d")
    
    return dump_date_str, start_date, end_date

async def run_pipeline():
    logger.info("🚀 Pinlm VIDEO_UPDATER 파이프라인 가동 시작")
    
    dump_date_str, start_date, end_date = get_target_dates()
    logger.info(f"타겟 날짜 | Dump: {dump_date_str}, Change API: {start_date} ~ {end_date}")

    # 1. 단일 HTTP 세션 열기 (전체 파이프라인에서 공유)
    async with aiohttp.ClientSession() as aio_session:
        
        # 2. 단일 DB 트랜잭션 세션 열기
        async with SessionLocal() as db_session:
            try:
                # ========================================================
                # [Step 1] 기초 공사 (Meta: Genre, OTT)
                # ========================================================
                meta_sync = MetaSynchronizer(db_session)
                await meta_sync.sync_genres(aio_session)
                await meta_sync.sync_otts(aio_session)

                # ========================================================
                # [Step 2] 보조 데이터 동기화 (Keyword, Person)
                # ========================================================
                keyword_sync = KeywordSynchronizer(db_session)
                await keyword_sync.sync_keywords(dump_date_str)

                person_sync = PersonSynchronizer(db_session)
                await person_sync.sync_people(aio_session, dump_date_str, start_date, end_date)

                # ========================================================
                # [Step 3] 메인 데이터 동기화 (Movie & Mappings)
                # ========================================================
                movie_sync = MovieSynchronizer(db_session)
                await movie_sync.sync_movies(aio_session, dump_date_str, start_date, end_date)

                # 모든 단계 성공 시에만 최종 커밋 (원자성 보장)
                await db_session.commit()
                
            except Exception as e:
                logger.error(f"❌ 파이프라인 실행 중 치명적 오류 발생: {str(e)}", exc_info=True)
                await db_session.rollback()  # 오류 시 롤백
                raise

    logger.info("✅ Pinlm VIDEO_UPDATER 파이프라인이 안전하게 종료되었습니다.")


async def run_pipeline_job():
    """APScheduler에서 호출하는 안전 실행 래퍼"""
    try:
        await run_pipeline()
    except Exception:
        logger.exception("❌ 스케줄 작업 실행 실패")


async def run_scheduler_forever():
    """하루 1회 파이프라인 실행을 위한 스케줄러 루프"""
    timezone, hour, minute, run_on_startup = get_scheduler_config()
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(timezone))

    scheduler.add_job(
        run_pipeline_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_video_updater",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "🕒 APScheduler 시작 | timezone=%s, daily=%02d:%02d, run_on_startup=%s",
        timezone,
        hour,
        minute,
        run_on_startup,
    )

    if run_on_startup:
        await run_pipeline_job()

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)

if __name__ == "__main__":
    # Windows 환경 등에서의 asyncio 에러 방지
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        asyncio.run(run_scheduler_forever())
    except KeyboardInterrupt:
        logger.info("스케줄러 종료 신호를 받았습니다.")
    except Exception:
        raise SystemExit(1)