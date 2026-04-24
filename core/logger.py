import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """통일된 포맷의 로거를 반환합니다."""
    logger = logging.getLogger(name)
    
    # 중복 핸들러 부착 방지
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        
        # 도커 환경에 맞게 표준 출력(stdout)으로 전송
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger