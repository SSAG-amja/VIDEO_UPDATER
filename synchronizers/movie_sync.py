import asyncio
import logging
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.future import select

from fetchers.api_fetcher import TMDBApiFetcher
from fetchers.dump_fetcher import TMDBDumpFetcher
from models.metadata import Genre, Keyword, Ott, Person
from models.movie import Movie
from utils.compare_utils import build_normalized_lookup, normalize_compare_text

logger = logging.getLogger("MOVIE_SYNC")


def get_korean_release_date(movie_data):
    """KR 개봉일만 추출한다. 우선순위: Theatrical(3) -> Limited(2) -> 가장 빠른 KR 일자."""
    release_date_groups = movie_data.get("release_dates", {}).get("results", [])

    for country in release_date_groups:
        if country.get("iso_3166_1") != "KR":
            continue

        release_items = country.get("release_dates", [])

        for preferred_type in (3, 2):
            typed_dates = [
                info.get("release_date")
                for info in release_items
                if info.get("type") == preferred_type and info.get("release_date")
            ]
            if typed_dates:
                return min(typed_dates).split("T")[0]

        all_dates = [info.get("release_date") for info in release_items if info.get("release_date")]
        if all_dates:
            return min(all_dates).split("T")[0]

    return None


def get_korean_movie_fields(movie_data):
    return {
        "title_ko": movie_data.get("title"),
        "status": movie_data.get("status"),
        "poster_path": movie_data.get("poster_path"),
        "backdrop_path": movie_data.get("backdrop_path"),
    }


class MovieSynchronizer:
    def __init__(self, db_session):
        self.db = db_session
        self.api_fetcher = TMDBApiFetcher()
        self.dump_fetcher = TMDBDumpFetcher()

        self.genre_map = {}
        self.ott_map = {}
        self.keyword_map = {}
        self.person_map = {}

    async def _build_memory_maps(self):
        logger.info("메타데이터 ID 메모리 맵 구축 중...")

        for model, target_map in [
            (Genre, self.genre_map),
            (Ott, self.ott_map),
            (Keyword, self.keyword_map),
            (Person, self.person_map),
        ]:
            result = await self.db.execute(select(model.tmdb_id, model.id))
            target_map.update({row.tmdb_id: row.id for row in result.all()})

    async def sync_movies(self, aio_session, date_str: str, start_date: str, end_date: str):
        logger.info("영화 메인 동기화 파이프라인 가동...")

        await self._build_memory_maps()

        result = await self.db.execute(
            select(
                Movie.id,
                Movie.tmdb_id,
                Movie.original_title,
                Movie.original_language,
                Movie.release_date,
                Movie.title_ko,
                Movie.status,
                Movie.poster_path,
                Movie.backdrop_path,
            )
        )
        movie_rows = result.all()
        db_movies = {row.tmdb_id: row.original_title for row in movie_rows}
        db_movie_lookup = {
            (normalize_compare_text(row.original_title), normalize_compare_text(row.original_language)): row
            for row in movie_rows
        }
        db_movie_title_lookup = build_normalized_lookup(movie_rows, "original_title")

        logger.info("[Phase 2] 영화 덤프 대조 시작...")
        dump_file = await self.dump_fetcher.download_dump("movie_ids", date_str)

        dump_ids = None
        new_ids = set()
        title_changed_ids = set()
        reconciled_ids = set()

        if dump_file:
            dump_ids = set()
            for item in self.dump_fetcher.get_dump_iterator(dump_file):
                tmdb_id = item["id"]
                original_title = item.get("original_title")
                original_language = item.get("original_language")
                dump_ids.add(tmdb_id)

                if tmdb_id not in db_movies:
                    matched_row = db_movie_lookup.get(
                        (normalize_compare_text(original_title), normalize_compare_text(original_language))
                    ) or db_movie_title_lookup.get(normalize_compare_text(original_title))

                    if matched_row:
                        detail = await self.api_fetcher.fetch_movie_details(aio_session, tmdb_id)
                        if not detail:
                            new_ids.add(tmdb_id)
                            continue

                        if normalize_compare_text(detail.get("original_title")) != normalize_compare_text(matched_row.original_title):
                            new_ids.add(tmdb_id)
                            continue

                        if normalize_compare_text(detail.get("original_language")) != normalize_compare_text(matched_row.original_language):
                            new_ids.add(tmdb_id)
                            continue

                        if normalize_compare_text(get_korean_release_date(detail)) != normalize_compare_text(matched_row.release_date):
                            new_ids.add(tmdb_id)
                            continue

                        await self.db.execute(
                            update(Movie).where(Movie.id == matched_row.id).values(tmdb_id=tmdb_id)
                        )

                        old_tmdb_id = matched_row.tmdb_id
                        db_movies.pop(old_tmdb_id, None)
                        db_movies[tmdb_id] = original_title

                        db_movie_lookup.pop(
                            (
                                normalize_compare_text(matched_row.original_title),
                                normalize_compare_text(matched_row.original_language),
                            ),
                            None,
                        )
                        db_movie_lookup[
                            (normalize_compare_text(original_title), normalize_compare_text(original_language))
                        ] = matched_row

                        db_movie_title_lookup.pop(normalize_compare_text(matched_row.original_title), None)
                        db_movie_title_lookup[normalize_compare_text(original_title)] = matched_row
                        reconciled_ids.add(tmdb_id)
                        continue

                    new_ids.add(tmdb_id)
                else:
                    if db_movies[tmdb_id] != original_title:
                        title_changed_ids.add(tmdb_id)

        if dump_ids is not None:
            delete_ids = set(db_movies.keys()) - dump_ids
            if delete_ids:
                await self.db.execute(delete(Movie).where(Movie.tmdb_id.in_(list(delete_ids))))
                logger.info(f"{len(delete_ids)}편의 영화 삭제 완료 (매핑 테이블 연쇄 삭제됨).")
        else:
            logger.warning("movie dump 파일을 받지 못해 삭제 단계는 건너뜁니다.")

        logger.info("[Phase 3] 영화 변경분(Change API) 수집 중...")
        changed_api_ids = set()
        page = 1

        while True:
            change_data = await self.api_fetcher.fetch_changes(
                aio_session,
                start_date,
                end_date,
                page=page,
                endpoint="/movie/changes",
            )

            if not change_data:
                break

            changed_api_ids.update(item["id"] for item in change_data.get("results", []))

            total_pages = change_data.get("total_pages", 1)
            if page >= total_pages:
                break

            page += 1

        target_ids = list(new_ids | title_changed_ids | changed_api_ids | reconciled_ids)
        if not target_ids:
            logger.info("업데이트할 영화가 없습니다. 파이프라인 종료.")
            return

        logger.info(f"총 {len(target_ids)}편의 영화 상세 업데이트를 시작합니다.")
        await self._process_movie_chunk(aio_session, target_ids)

    async def _process_movie_chunk(self, aio_session, target_ids: list):
        chunk_size = 1000
        total_chunks = (len(target_ids) - 1) // chunk_size + 1

        for i in range(0, len(target_ids), chunk_size):
            chunk_ids = target_ids[i : i + chunk_size]
            current_chunk = i // chunk_size + 1
            logger.info(f"[{current_chunk}/{total_chunks}] 영화 청크 처리 중... ({len(chunk_ids)}건)")

            us_tasks = [self.api_fetcher.fetch_movie_details(aio_session, mid) for mid in chunk_ids]
            ko_tasks = [
                self.api_fetcher.fetch_movie_details(aio_session, mid, language="ko-KR")
                for mid in chunk_ids
            ]
            us_results = await asyncio.gather(*us_tasks)
            ko_results = await asyncio.gather(*ko_tasks)

            valid_movies = [m for m in us_results if m is not None]
            if not valid_movies:
                continue

            ko_map = {
                movie["id"]: movie
                for movie in ko_results
                if movie is not None and movie.get("id") is not None
            }

            movies_to_upsert = []
            new_people_to_insert = {}

            for m_data in valid_movies:
                localized_data = ko_map.get(m_data["id"]) or m_data
                ko_fields = get_korean_movie_fields(localized_data)
                release_date = get_korean_release_date(localized_data) or localized_data.get("release_date")
                release_date = release_date if release_date else None

                movies_to_upsert.append(
                    {
                        "tmdb_id": m_data["id"],
                        "imdb_id": m_data.get("imdb_id"),
                        "title": m_data.get("title"),
                        "title_ko": ko_fields.get("title_ko"),
                        "original_title": m_data.get("original_title"),
                        "original_language": m_data.get("original_language"),
                        "overview": m_data.get("overview"),
                        "popularity": m_data.get("popularity", 0.0),
                        "vote_average": m_data.get("vote_average", 0.0),
                        "vote_count": m_data.get("vote_count", 0),
                        "release_date": release_date,
                        "runtime": m_data.get("runtime", 0),
                        "budget": m_data.get("budget", 0),
                        "revenue": m_data.get("revenue", 0),
                        "adult": m_data.get("adult", False),
                        "status": ko_fields.get("status"),
                        "poster_path": ko_fields.get("poster_path"),
                        "backdrop_path": ko_fields.get("backdrop_path"),
                    }
                )

                credits = m_data.get("credits", {})
                for cast in credits.get("cast", []):
                    if cast["id"] not in self.person_map:
                        new_people_to_insert[cast["id"]] = cast["name"]
                for crew in credits.get("crew", []):
                    if crew["job"] == "Director" and crew["id"] not in self.person_map:
                        new_people_to_insert[crew["id"]] = crew["name"]

            if new_people_to_insert:
                people_values = [{"tmdb_id": pid, "name": name} for pid, name in new_people_to_insert.items()]
                p_stmt = (
                    insert(Person)
                    .values(people_values)
                    .on_conflict_do_nothing(index_elements=["tmdb_id"])
                    .returning(Person.id, Person.tmdb_id)
                )
                p_result = await self.db.execute(p_stmt)
                for row in p_result.all():
                    self.person_map[row.tmdb_id] = row.id

            m_stmt = insert(Movie).values(movies_to_upsert)
            m_stmt = m_stmt.on_conflict_do_update(
                index_elements=["tmdb_id"],
                set_={col.name: col for col in m_stmt.excluded if col.name not in ("id", "tmdb_id")},
            ).returning(Movie.id, Movie.tmdb_id)

            m_result = await self.db.execute(m_stmt)
            movie_id_map = {row.tmdb_id: row.id for row in m_result.all()}

            api_mappings = {
                "genres": set(),
                "otts": set(),
                "keywords": set(),
                "actors": set(),
                "directors": set(),
            }

            internal_movie_ids = list(movie_id_map.values())

            for m_data in valid_movies:
                internal_m_id = movie_id_map.get(m_data["id"])
                if not internal_m_id:
                    continue

                for genre in m_data.get("genres", []):
                    if genre["id"] in self.genre_map:
                        api_mappings["genres"].add((internal_m_id, self.genre_map[genre["id"]]))

                for kw in m_data.get("keywords", {}).get("keywords", []):
                    if kw["id"] in self.keyword_map:
                        api_mappings["keywords"].add((internal_m_id, self.keyword_map[kw["id"]]))

                kr_providers = m_data.get("watch/providers", {}).get("results", {}).get("KR", {})
                ott_dict = {}
                for p_type, flag in [("flatrate", "is_streaming"), ("rent", "is_rent"), ("buy", "is_buy")]:
                    for p_data in kr_providers.get(p_type, []):
                        pid = p_data["provider_id"]
                        if pid in self.ott_map:
                            if pid not in ott_dict:
                                ott_dict[pid] = {"is_streaming": False, "is_rent": False, "is_buy": False}
                            ott_dict[pid][flag] = True

                for pid, flags in ott_dict.items():
                    api_mappings["otts"].add(
                        (
                            internal_m_id,
                            self.ott_map[pid],
                            flags["is_streaming"],
                            flags["is_rent"],
                            flags["is_buy"],
                        )
                    )

                for cast in m_data.get("credits", {}).get("cast", []):
                    if cast["id"] in self.person_map:
                        api_mappings["actors"].add(
                            (internal_m_id, self.person_map[cast["id"]], cast.get("character", "")[:100])
                        )

                for crew in m_data.get("credits", {}).get("crew", []):
                    if crew["job"] == "Director" and crew["id"] in self.person_map:
                        api_mappings["directors"].add((internal_m_id, self.person_map[crew["id"]]))

            if internal_movie_ids:
                from synchronizers.mapping_sync import MappingSynchronizer

                mapping_sync = MappingSynchronizer(self.db)
                await mapping_sync.sync_mappings(internal_movie_ids, api_mappings)

        logger.info("모든 영화 상세 동기화가 완료되었습니다.")
