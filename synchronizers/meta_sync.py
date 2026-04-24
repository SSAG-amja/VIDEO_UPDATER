import asyncio
import logging
from sqlalchemy.future import select
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from models.metadata import Genre, Ott
from fetchers.api_fetcher import TMDBApiFetcher
from utils.compare_utils import build_normalized_lookup, normalize_compare_text

logger = logging.getLogger("META_SYNC")

class MetaSynchronizer:
    def __init__(self, db_session):
        self.db = db_session
        self.fetcher = TMDBApiFetcher()

    async def sync_genres(self, session):
        """장르 데이터 동기화"""
        logger.info("장르 동기화 시작...")
        
        # 1. API에서 최신 장르 목록 가져오기
        data_us = await self.fetcher.fetch_genres(session, language="en-US")
        data_ko = await self.fetcher.fetch_genres(session, language="ko-KR")
        if not data_us:
            logger.error("장르 데이터를 가져오는데 실패했습니다.")
            return

        genre_ko_map = {item["id"]: item.get("name") for item in data_ko}

        # 2. DB에 이미 존재하는 tmdb_id 목록 가져오기 (비교용)
        result = await self.db.execute(select(Genre.id, Genre.tmdb_id, Genre.name, Genre.name_ko))
        rows = result.all()
        existing_ids = {r.tmdb_id for r in rows}
        existing_names = build_normalized_lookup(rows, "name")

        new_genres = []
        for item in data_us:
            if item['id'] in existing_ids:
                continue

            matched_row = existing_names.get(normalize_compare_text(item['name']))
            if matched_row:
                await self.db.execute(
                    update(Genre)
                    .where(Genre.id == matched_row.id)
                    .values(tmdb_id=item['id'])
                )
                existing_ids.discard(matched_row.tmdb_id)
                existing_ids.add(item['id'])
                continue

            if item['id'] not in existing_ids:
                new_genres.append({
                    "tmdb_id": item['id'],
                    "name": item['name'],
                    "name_ko": genre_ko_map.get(item['id']) or item['name']
                })

        # 3. 신규 데이터가 있다면 일괄 삽입
        if new_genres:
            stmt = insert(Genre).values(new_genres)
            # 중복 방지를 위한 안전장치 (Conflict 발생 시 무시)
            stmt = stmt.on_conflict_do_nothing(index_elements=['tmdb_id'])
            await self.db.execute(stmt)
            logger.info(f"{len(new_genres)}개의 새로운 장르가 추가되었습니다.")
        else:
            logger.info("업데이트할 새로운 장르가 없습니다.")

    async def sync_otts(self, session):
        """OTT(Watch Providers) 데이터 동기화"""
        logger.info("OTT 목록 동기화 시작...")

        # 1. API에서 한국 지역 OTT 목록 가져오기
        data_us = await self.fetcher.fetch_otts(session, language="en-US")
        data_ko = await self.fetcher.fetch_otts(session, language="ko-KR")
        if not data_us:
            logger.error("OTT 데이터를 가져오는데 실패했습니다.")
            return

        ott_ko_map = {item["provider_id"]: item.get("provider_name") for item in data_ko}

        # 2. DB에 존재하는 OTT tmdb_id 목록 확인
        result = await self.db.execute(select(Ott.id, Ott.tmdb_id, Ott.name, Ott.name_ko))
        rows = result.all()
        existing_ids = {r.tmdb_id for r in rows}
        existing_names = build_normalized_lookup(rows, "name")

        new_otts = []
        for item in data_us:
            if item['provider_id'] in existing_ids:
                continue

            matched_row = existing_names.get(normalize_compare_text(item['provider_name']))
            if matched_row:
                await self.db.execute(
                    update(Ott)
                    .where(Ott.id == matched_row.id)
                    .values(tmdb_id=item['provider_id'])
                )
                existing_ids.discard(matched_row.tmdb_id)
                existing_ids.add(item['provider_id'])
                continue

            if item['provider_id'] not in existing_ids:
                new_otts.append({
                    "tmdb_id": item['provider_id'],
                    "name": item['provider_name'],
                    "name_ko": ott_ko_map.get(item['provider_id']) or item['provider_name']
                })

        # 3. 신규 데이터 일괄 삽입
        if new_otts:
            stmt = insert(Ott).values(new_otts)
            stmt = stmt.on_conflict_do_nothing(index_elements=['tmdb_id'])
            await self.db.execute(stmt)
            logger.info(f"{len(new_otts)}개의 새로운 OTT가 추가되었습니다.")
        else:
            logger.info("업데이트할 새로운 OTT가 없습니다.")