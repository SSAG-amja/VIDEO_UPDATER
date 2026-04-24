import logging
from sqlalchemy.future import select
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from models.metadata import Keyword
from fetchers.dump_fetcher import TMDBDumpFetcher
from utils.compare_utils import (
    build_normalized_lookup,
    normalize_compare_text,
)

logger = logging.getLogger("KEYWORD_SYNC")

class KeywordSynchronizer:
    def __init__(self, db_session):
        self.db = db_session
        self.dump_fetcher = TMDBDumpFetcher()

    async def sync_keywords(self, date_str: str):
        """덤프 파일을 이용한 키워드 일괄 동기화"""
        logger.info("키워드 동기화 시작 (덤프 기반)...")
        
        # 1. 덤프 파일 다운로드
        file_path = await self.dump_fetcher.download_dump("keyword_ids", date_str)
        if not file_path:
            logger.error("키워드 덤프 파일을 찾을 수 없습니다.")
            return

        # 2. Phase 1: DB에서 기존 tmdb_id 전체 로드 (메모리 맵 구축)
        result = await self.db.execute(select(Keyword.id, Keyword.tmdb_id, Keyword.name))
        rows = result.all()
        db_ids = {r.tmdb_id for r in rows}
        db_name_lookup = build_normalized_lookup(rows, "name")
        
        dump_ids = set()
        new_keywords = []

        # 3. Phase 2: 덤프 파일 스트리밍 대조
        logger.info("덤프 파일 스트리밍 대조 시작...")
        for item in self.dump_fetcher.get_dump_iterator(file_path):
            tmdb_id = item['id']
            dump_ids.add(tmdb_id)
            
            # DB에 없는 새로운 키워드 발굴
            if tmdb_id in db_ids:
                continue

            # 보수 정책: 정규화된 완전일치에서만 같은 키워드로 간주
            matched_row = db_name_lookup.get(normalize_compare_text(item['name']))

            if matched_row:
                await self.db.execute(
                    update(Keyword)
                    .where(Keyword.id == matched_row.id)
                    .values(tmdb_id=tmdb_id)
                )
                db_ids.discard(matched_row.tmdb_id)
                db_ids.add(tmdb_id)
                continue

            if tmdb_id not in db_ids:
                new_keywords.append({
                    "tmdb_id": tmdb_id,
                    "name": item['name']
                })

        # 4. 신규 키워드 일괄 삽입 (Chunk 처리로 DB Lock 최소화)
        if new_keywords:
            chunk_size = 5000
            for i in range(0, len(new_keywords), chunk_size):
                chunk = new_keywords[i:i + chunk_size]
                # TODO: TMDB 데이터 자체의 문제로 서로 다른 ID가 동일한 name을 가지는 불량 데이터가 들어올 수 있음.
                # 현재 Keyword 모델의 name 컬럼이 Unique=True이므로 충돌 에러가 날 가능성 염두할 것.
                stmt = insert(Keyword).values(chunk).on_conflict_do_nothing()
                await self.db.execute(stmt)
            logger.info(f"{len(new_keywords)}개의 신규 키워드 추가 완료.")

        # 5. 삭제된 키워드 정리 (TMDB에서 날아간 데이터)
        delete_ids = db_ids - dump_ids
        if delete_ids:
            await self.db.execute(
                delete(Keyword).where(Keyword.tmdb_id.in_(list(delete_ids)))
            )
            logger.info(f"{len(delete_ids)}개의 삭제된 키워드 정리 완료.")
        logger.info("키워드 동기화 완료.")