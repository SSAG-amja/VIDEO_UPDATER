import asyncio
import aiohttp
import json
import logging
from datetime import datetime
from core.config import TMDB_API_KEY

# 에러 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API_FETCHER")

class TMDBApiFetcher:
    def __init__(self):
        self.api_key = TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.params = {"api_key": self.api_key, "language": "en-US"}
        self.semaphore = asyncio.Semaphore(40)  # 초당 40회 제한
        self.error_log_path = "failed_sync_ids.jsonl"

    async def _fetch_with_retry(self, session, url, params=None, retries=3, failure_context=None):
        """3회 재시도 로직이 포함된 공통 fetch 메서드"""
        current_params = self.params.copy()
        if params:
            current_params.update(params)

        for attempt in range(1, retries + 1):
            async with self.semaphore:
                try:
                    async with session.get(url, params=current_params, timeout=10) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429: # Rate Limit
                            wait_time = int(response.headers.get("Retry-After", 1))
                            await asyncio.sleep(wait_time)
                        else:
                            logger.warning(f"[Attempt {attempt}] HTTP {response.status} for {url}")
                except Exception as e:
                    logger.error(f"[Attempt {attempt}] Error fetching {url}: {str(e)}")
            
            if attempt < retries:
                await asyncio.sleep(2 ** attempt) # 지수 백오프 (2, 4, 8초)
        
        # 3회 모두 실패 시 로그 남기기
        self._log_error(url, failure_context=failure_context)
        return None

    async def fetch_with_retry(self, session, url, params=None, retries=3, failure_context=None):
        """외부 호출용 공용 래퍼 메서드"""
        return await self._fetch_with_retry(
            session,
            url,
            params=params,
            retries=retries,
            failure_context=failure_context,
        )

    def _log_error(self, url, failure_context=None):
        payload = {
            "timestamp": datetime.now().isoformat(),
            "url": url,
        }
        if failure_context:
            payload.update(failure_context)

        with open(self.error_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    async def fetch_genres(self, session, language=None):
        """장르 목록 가져오기"""
        url = f"{self.base_url}/genre/movie/list"
        params = {"language": language} if language else None
        data = await self._fetch_with_retry(session, url, params=params)
        return data.get("genres", []) if data else []

    async def fetch_otts(self, session, language=None):
        """OTT(Watch Providers) 목록 가져오기"""
        url = f"{self.base_url}/watch/providers/movie"
        params = {"watch_region": "KR"}
        if language:
            params["language"] = language
        data = await self._fetch_with_retry(session, url, params=params)
        return data.get("results", []) if data else []

    async def fetch_movie_details(self, session, movie_id, language=None):
        """영화 상세 정보 가져오기 (Phase 4용)"""
        url = f"{self.base_url}/movie/{movie_id}"
        # append_to_response로 출연진(credits), 키워드(keywords)를 한 번에 가져와서 API 호출 횟수 절약
        params = {"append_to_response": "credits,keywords,watch/providers,release_dates"}
        if language:
            params["language"] = language
        return await self._fetch_with_retry(
            session,
            url,
            params=params,
            failure_context={"entity_type": "movie", "entity_id": movie_id},
        )

    async def fetch_changes(self, session, start_date, end_date, page=1, endpoint="/movie/changes"):
        """변경 내역 ID 목록 가져오기 (Phase 3용)"""
        url = f"{self.base_url}{endpoint}"
        params = {"start_date": start_date, "end_date": end_date, "page": page}
        return await self._fetch_with_retry(session, url, params=params)