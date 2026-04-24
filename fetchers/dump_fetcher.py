import os
import gzip
import ijson
import aiohttp
import logging
from core.config import DOWNLOAD_DIR

logger = logging.getLogger("DUMP_FETCHER")

class TMDBDumpFetcher:
    def __init__(self):
        # 다운로드 경로 설정 및 폴더 생성
        self.download_dir = DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)

    async def download_dump(self, dump_type: str, date_str: str) -> str:
        """
        TMDB 서버에서 압축된 덤프 파일을 다운로드합니다.
        - dump_type: 'movie_ids', 'person_ids', 'keyword_ids'
        - date_str: 'MM_DD_YYYY' (예: 04_24_2026)
        """
        file_name = f"{dump_type}_{date_str}.json.gz"
        save_path = os.path.join(self.download_dir, file_name)
        url = f"http://files.tmdb.org/p/exports/{file_name}"

        # 이미 파일이 있다면 다운로드 스킵
        if os.path.exists(save_path):
            logger.info(f"이미 파일이 존재하여 스킵합니다: {file_name}")
            return save_path

        logger.info(f"덤프 파일 다운로드 시작: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"다운로드 실패 (HTTP {response.status})")
                    return None
                
                # 1MB씩 끊어서 저장 (메모리 보호)
                with open(save_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        
        logger.info(f"다운로드 완료: {save_path}")
        return save_path

    def get_dump_iterator(self, file_path: str):
        """
        압축된 JSON 파일을 스트리밍으로 한 줄씩 리턴하는 제너레이터입니다.
        Phase 2에서 DB와 대조할 때 사용됩니다.
        """
        if not file_path or not os.path.exists(file_path):
            logger.error(f"파일을 찾을 수 없습니다: {file_path}")
            return

        # gzip.open으로 압축을 실시간으로 풀면서 읽음
        with gzip.open(file_path, 'rb') as f:
            # ijson.items를 multiple_values=True로 설정하면 
            # 한 파일 내에 독립적인 JSON 객체들이 나열된 구조를 한 줄씩 파싱합니다.
            for item in ijson.items(f, '', multiple_values=True):
                # item은 {'id': 123, 'original_title': '...', ...} 형태의 딕셔너리
                yield item