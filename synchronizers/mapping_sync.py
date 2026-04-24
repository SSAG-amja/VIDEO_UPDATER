import logging
from sqlalchemy.future import select
from sqlalchemy import delete, tuple_
from sqlalchemy.dialects.postgresql import insert
from models.mappings import MovieGenre, MovieOtt, MovieKeyword, MovieActor, MovieDirector
from utils.diff_calculator import DiffCalculator

logger = logging.getLogger("MAPPING_SYNC")

class MappingSynchronizer:
    def __init__(self, db_session):
        self.db = db_session

    async def sync_mappings(self, internal_movie_ids: list, parsed_api_mappings: dict):
        """
        영화 청크 단위의 매핑 데이터를 Diff 계산하여 DB에 반영합니다.
        parsed_api_mappings 구조: 
        {
            "genres": set((movie_id, genre_id), ...),
            "otts": set((movie_id, ott_id, is_st, is_rt, is_by), ...),
            "keywords": set((movie_id, keyword_id), ...),
            "actors": set((movie_id, actor_id, cast_name), ...),
            "directors": set((movie_id, director_id), ...)
        }
        """
        if not internal_movie_ids:
            return

        # 1. 대상 영화들의 기존 매핑 데이터 한 번에 가져오기
        db_genres = set((r.movie_id, r.genre_id) for r in (await self.db.execute(select(MovieGenre.movie_id, MovieGenre.genre_id).where(MovieGenre.movie_id.in_(internal_movie_ids)))).all())
        db_keywords = set((r.movie_id, r.keyword_id) for r in (await self.db.execute(select(MovieKeyword.movie_id, MovieKeyword.keyword_id).where(MovieKeyword.movie_id.in_(internal_movie_ids)))).all())
        db_directors = set((r.movie_id, r.director_id) for r in (await self.db.execute(select(MovieDirector.movie_id, MovieDirector.director_id).where(MovieDirector.movie_id.in_(internal_movie_ids)))).all())
        # 배우와 OTT는 속성값이 포함되어 있으므로 튜플 구성에 포함 (비교를 위해)
        db_actors = set((r.movie_id, r.actor_id, r.cast_name) for r in (await self.db.execute(select(MovieActor.movie_id, MovieActor.actor_id, MovieActor.cast_name).where(MovieActor.movie_id.in_(internal_movie_ids)))).all())
        db_otts = set((r.movie_id, r.ott_id, r.is_streaming, r.is_rent, r.is_buy) for r in (await self.db.execute(select(MovieOtt.movie_id, MovieOtt.ott_id, MovieOtt.is_streaming, MovieOtt.is_rent, MovieOtt.is_buy).where(MovieOtt.movie_id.in_(internal_movie_ids)))).all())

        # 2. Diff 연산 (추가할 것과 삭제할 것 분리)
        add_g, del_g = DiffCalculator.get_delta(db_genres, parsed_api_mappings["genres"])
        add_k, del_k = DiffCalculator.get_delta(db_keywords, parsed_api_mappings["keywords"])
        add_d, del_d = DiffCalculator.get_delta(db_directors, parsed_api_mappings["directors"])
        add_a, del_a = DiffCalculator.get_delta(db_actors, parsed_api_mappings["actors"])
        add_o, del_o = DiffCalculator.get_delta(db_otts, parsed_api_mappings["otts"])

        # 3. DELETE 실행 (불필요해진 매핑 제거)
        if del_g: await self._execute_delete(MovieGenre, "genre_id", del_g)
        if del_k: await self._execute_delete(MovieKeyword, "keyword_id", del_k)
        if del_d: await self._execute_delete(MovieDirector, "director_id", del_d)
        if del_a: await self._execute_delete(MovieActor, "actor_id", del_a) # 삭제 조건은 id 2개로 충분
        if del_o: await self._execute_delete(MovieOtt, "ott_id", del_o)

        # 4. INSERT 실행 (새로운 매핑 추가)
        if add_g: await self.db.execute(insert(MovieGenre).values([{"movie_id": m, "genre_id": t} for m, t in add_g]))
        if add_k: await self.db.execute(insert(MovieKeyword).values([{"movie_id": m, "keyword_id": t} for m, t in add_k]))
        if add_d: await self.db.execute(insert(MovieDirector).values([{"movie_id": m, "director_id": t} for m, t in add_d]))
        if add_a: await self.db.execute(insert(MovieActor).values([{"movie_id": m, "actor_id": a, "cast_name": c} for m, a, c in add_a]))
        if add_o: await self.db.execute(insert(MovieOtt).values([{"movie_id": m, "ott_id": o, "is_streaming": s, "is_rent": r, "is_buy": b} for m, o, s, r, b in add_o]))

    async def _execute_delete(self, model, target_id_col: str, del_list: list):
        """복합키 삭제를 위한 헬퍼 메서드"""
        # IN 절 하나로 처리하기 위해 OR 조건 묶음 사용 (혹은 복합키 in_ 연산 지원 여부에 따라 작성)
        # SQLAlchemy에서 복합키(tuple) in_ 연산을 지원하므로 깔끔하게 처리 가능
        target_tuples = [(m_id, t_id) for m_id, t_id, *_ in del_list]
        stmt = delete(model).where(
            tuple_(model.movie_id, getattr(model, target_id_col)).in_(target_tuples)
        )
        await self.db.execute(stmt)