import os
import aiohttp
import aiofiles
from core.logger import get_logger

logger = get_logger("FILE_MANAGER")

class FileManager:
    DOWNLOAD_DIR = "downloads"

    @classmethod
    async def download_dump_file(cls, url: str, filename: str) -> str | None:
        """대용량 파일을 청크 단위로 안전하게 다운로드합니다."""
        if not os.path.exists(cls.DOWNLOAD_DIR):
            os.makedirs(cls.DOWNLOAD_DIR)

        file_path = os.path.join(cls.DOWNLOAD_DIR, filename)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"다운로드 실패: {url} (Status: {response.status})")
                        return None

                    # 1MB 단위로 쪼개서 디스크에 작성 (메모리 폭발 방지)
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            await f.write(chunk)
            
            logger.info(f"덤프 파일 다운로드 완료: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"파일 다운로드 중 에러 발생: {e}")
            return None

    @classmethod
    def delete_file(cls, file_path: str):
        """사용이 끝난 덤프 파일을 삭제하여 디스크 용량을 확보합니다."""
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"임시 파일 삭제 완료: {file_path}")