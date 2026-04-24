# VIDEO_UPDATER

VIDEO_UPDATER/
├── .env                        # 환경 변수 (DB 접속 정보, TMDB API 키 등)
├── .dockerignore               # 도커 빌드 시 제외할 파일들
├── Dockerfile                  # VIDEO_UPDATER 단독 빌드용
├── docker-compose.yml          # 이 폴더 안에서 워커 + DB(PostgreSQL)를 단독으로 띄우기 위한 설정
├── requirements.txt            # 파이썬 패키지 의존성 (SQLAlchemy, pandas, aiohttp 등)
├── main.py                     # 파이프라인 실행 진입점
│
├── core/                       # 공통 설정 및 기반 코드
│   ├── __init__.py
│   ├── config.py               # .env 로드 및 전역 설정
│   ├── database.py             # DB 연결 (Engine, Session)
│   └── logger.py               # 로깅 설정
│
├── models/                     # DB 스키마 (SQLAlchemy)
│   ├── __init__.py
│   ├── base.py                 # Declarative Base
│   ├── movie.py                # movies 테이블
│   ├── metadata.py             # otts, genres, people, keywords 테이블
│   └── mappings.py             # 매핑 테이블 5개
│
├── fetchers/                   # 외부 데이터 수집
│   ├── __init__.py
│   ├── api_fetcher.py          # TMDB API 호출 (장르, OTT 등)
│   └── dump_fetcher.py         # TMDB JSON Dump 다운로드
│
├── synchronizers/              # DB 대조 및 업데이트 로직
│   ├── __init__.py
│   ├── meta_sync.py            # 장르, OTT 동기화
│   ├── dump_sync.py            # 영화, 사람, 키워드 동기화
│   └── mapping_sync.py         # 매핑 테이블 동기화
│
└── utils/                      # 보조 도구
    ├── __init__.py
    ├── file_manager.py         # 대용량 파일 다운로드/압축해제/삭제
    └── diff_calculator.py      # 변경점 비교 로직
