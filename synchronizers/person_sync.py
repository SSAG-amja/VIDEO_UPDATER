import asyncio
import logging
from sqlalchemy.future import select
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from models.metadata import Person
from fetchers.api_fetcher import TMDBApiFetcher
from fetchers.dump_fetcher import TMDBDumpFetcher
from utils.compare_utils import build_normalized_lookup, normalize_compare_text

logger = logging.getLogger("PERSON_SYNC")

class PersonSynchronizer:
    def __init__(self, db_session):
        self.db = db_session
        self.api_fetcher = TMDBApiFetcher()
        self.dump_fetcher = TMDBDumpFetcher()  # Dump Fetcher 추가!

    async def sync_people(self, aio_session, date_str: str, start_date: str, end_date: str):
        """인물 데이터 동기화 (Dump로 삭제, Change API로 갱신)"""
        logger.info("인물 하이브리드 동기화 시작...")

        # ---------------------------------------------------------
        # [Step 1] DB 기준 인물 목록 로드
        # ---------------------------------------------------------
        result = await self.db.execute(select(Person.id, Person.tmdb_id, Person.name))
        rows = result.all()
        db_ids = {r.tmdb_id for r in rows}
        db_name_lookup = build_normalized_lookup(rows, "name")
        
        if not db_ids:
            logger.info("people 테이블이 비어 있어 dump 기반 초기 적재를 수행합니다.")
            dump_file = await self.dump_fetcher.download_dump("person_ids", date_str)
            if not dump_file:
                logger.error("person dump 파일이 없어 초기 적재를 수행할 수 없습니다.")
                return

            pending_people = []
            chunk_size = 5000
            for item in self.dump_fetcher.get_dump_iterator(dump_file):
                pending_people.append({
                    "tmdb_id": item['id'],
                    "name": item.get('name') or f"person_{item['id']}",
                })

                if len(pending_people) >= chunk_size:
                    stmt = insert(Person).values(pending_people).on_conflict_do_nothing(index_elements=['tmdb_id'])
                    await self.db.execute(stmt)
                    pending_people = []

            if pending_people:
                stmt = insert(Person).values(pending_people).on_conflict_do_nothing(index_elements=['tmdb_id'])
                await self.db.execute(stmt)

            logger.info("people 테이블 초기 적재 완료.")

            result = await self.db.execute(select(Person.id, Person.tmdb_id, Person.name))
            rows = result.all()
            db_ids = {r.tmdb_id for r in rows}
            db_name_lookup = build_normalized_lookup(rows, "name")

        # ---------------------------------------------------------
        # [Step 2] Dump 대조를 통한 삭제 (TMDB에서 지워진 인물 처리)
        # ---------------------------------------------------------
        dump_file = await self.dump_fetcher.download_dump("person_ids", date_str)
        if dump_file:
            dump_ids = set()
            for item in self.dump_fetcher.get_dump_iterator(dump_file):
                dump_id = item['id']
                dump_ids.add(dump_id)

                if dump_id in db_ids:
                    continue

                matched_row = db_name_lookup.get(normalize_compare_text(item.get('name')))
                if matched_row:
                    detail = await self.api_fetcher.fetch_with_retry(
                        aio_session,
                        f"{self.api_fetcher.base_url}/person/{dump_id}",
                        failure_context={"entity_type": "person", "entity_id": dump_id},
                    )

                    if not detail or normalize_compare_text(detail.get('name')) != normalize_compare_text(matched_row.name):
                        continue

                    await self.db.execute(
                        update(Person)
                        .where(Person.id == matched_row.id)
                        .values(tmdb_id=dump_id)
                    )
                    db_ids.discard(matched_row.tmdb_id)
                    db_ids.add(dump_id)
                    continue
            
            # DB에는 있는데 최신 덤프에는 없는 ID 추출
            delete_ids = db_ids - dump_ids
            if delete_ids:
                await self.db.execute(
                    delete(Person).where(Person.tmdb_id.in_(list(delete_ids)))
                )
                logger.info(f"{len(delete_ids)}명의 삭제된 인물 정리 완료.")
                
                # 업데이트 대상에서 제외하기 위해 db_ids 최신화
                db_ids = db_ids - delete_ids 

        # ---------------------------------------------------------
        # [Step 3] Change API 대조를 통한 갱신 (정보가 변경된 인물 처리)
        # ---------------------------------------------------------
        changed_ids_from_api = set()
        page = 1

        while True:
            change_data = await self.api_fetcher.fetch_changes(
                aio_session,
                start_date,
                end_date,
                page=page,
                endpoint="/person/changes",
            )

            if not change_data:
                break

            changed_ids_from_api.update(item['id'] for item in change_data.get('results', []))

            total_pages = change_data.get('total_pages', 1)
            if page >= total_pages:
                break

            page += 1

        # 우리 DB에 남아있는 사람 중 변경된 사람만 필터링
        target_ids = list(db_ids.intersection(changed_ids_from_api))

        if target_ids:
            logger.info(f"총 {len(target_ids)}명의 인물 정보 비동기 업데이트 시작...")

            # API로 상세 정보 비동기 호출 (Semaphore 40 적용)
            tasks = [
                self.api_fetcher.fetch_with_retry(
                    aio_session,
                    f"{self.api_fetcher.base_url}/person/{pid}",
                    failure_context={"entity_type": "person", "entity_id": pid},
                )
                for pid in target_ids
            ]
            results = await asyncio.gather(*tasks)

            updated_count = 0
            for p_data in results:
                if p_data:
                    stmt = (
                        update(Person)
                        .where(Person.tmdb_id == p_data['id'])
                        .values(
                            name=p_data.get('name'),
                        )
                    )
                    await self.db.execute(stmt)
                    updated_count += 1

            logger.info(f"{updated_count}명의 인물 정보 업데이트 완료.")
        else:
            logger.info("업데이트 대상 인물이 없습니다.")