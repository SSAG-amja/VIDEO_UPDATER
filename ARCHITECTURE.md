# VIDEO_UPDATER 프로젝트 아키텍처

## 📌 프로젝트 목적
**TMDB(The Movie Database) API와 덤프 파일을 이용해 로컬 PostgreSQL DB의 영화, 배우, 키워드 데이터를 주기적으로 동기화하는 시스템**

---

## 🏗️ 전체 레이어 구조

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py (진입점)                      │
│                       [현재 비어있음]                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              SYNCHRONIZERS (동기화 계층)                     │
│  ┌──────────────┬──────────────┬──────────────┐              │
│  │ meta_sync.py │movie_sync.py │person_sync.py│keyword_sync │
│  │(장르, OTT)   │(영화+매핑)    │(배우 정보)   │.py(키워드)  │
│  └──────────────┴──────────────┴──────────────┘              │
│                                                               │
│ 책임: DB와 비교 → 신규/수정/삭제 판단 → Upsert/Delete 실행  │
└─────────────────────────────────────────────────────────────┘
                              ↑
                              │ 원천 데이터 요청
┌─────────────────────────────────────────────────────────────┐
│               FETCHERS (데이터 수집 계층)                    │
│  ┌──────────────────────┬──────────────────────┐             │
│  │  api_fetcher.py      │  dump_fetcher.py     │             │
│  │ (TMDB API 호출)      │ (gzip 덤프 다운)     │             │
│  │ - 장르 조회          │ - 영화 ID 덤프       │             │
│  │ - OTT 조회           │ - 배우 ID 덤프       │             │
│  │ - 영화 상세 조회     │ - 키워드 ID 덤프     │             │
│  │ - 변경분 조회        │ - 스트림 파싱        │             │
│  └──────────────────────┴──────────────────────┘             │
│                                                               │
│ 책임: TMDB → 로컬로 데이터 가져오기만 (DB 로직 없음)        │
└─────────────────────────────────────────────────────────────┘
                              ↑
                    TMDB API 호출 / 덤프 다운로드
```

---

## 📊 데이터 모델 구조 (models/ 디렉토리)

### 핵심 테이블
```
movies (영화 본체)
├─ id (PK, 자동증가)
├─ tmdb_id (TMDB 기준 ID, UNIQUE)
├─ title, original_title
├─ overview, popularity, vote_average
├─ release_date, runtime, budget, revenue
└─ poster_path, backdrop_path

metadata 테이블들
├─ genres (장르 마스터) → id, tmdb_id, name, name_ko
├─ otts (OTT 제공사) → id, tmdb_id, name, name_ko
├─ keywords (키워드) → id, tmdb_id, name
└─ people (배우/감독) → id, tmdb_id, name, name_ko

매핑 테이블들 (many-to-many)
├─ movie_genres → (movie_id FK, genre_id FK)
├─ movie_otts → (movie_id FK, ott_id FK, is_streaming, is_rent, is_buy)
├─ movie_keywords → (movie_id FK, keyword_id FK)
├─ movie_actors → (movie_id FK, actor_id FK, cast_name)
└─ movie_directors → (movie_id FK, director_id FK)
```

---

## 🔄 권장 실행 순서 (왜 이 순서인가)

### ⚠️ 핵심 원칙: 종속성 관계 준수
- 메타데이터(장르, OTT)는 영화와 무관하게 독립 동기화
- 키워드도 영화와 무관하게 독립 동기화
- **배우(Person)는 영화보다 먼저 동기화되어야 함** (영화 동기화 시 신규 배우 발굴하므로)
- 영화는 메타데이터 + 배우 + 키워드 데이터가 먼저 있어야 매핑 테이블 구축 가능

### 📍 최적 실행 순서

#### [1단계] 메타데이터 초기화 (병렬 가능)
```
meta_sync.py → sync_genres()     // TMDB API 호출, 신규 장르만 INSERT
meta_sync.py → sync_otts()       // TMDB API 호출, 신규 OTT만 INSERT
```
- 소요 시간: 1~2초 (API 호출 2회)
- 이유: 이들은 마스터 데이터로 변경 빈도가 낮고 매번 신규만 추가

#### [2단계] 키워드 동기화
```
keyword_sync.py → sync_keywords()  // 덤프 다운로드, 신규/삭제 처리
```
- 소요 시간: 30~60초 (대용량 덤프 스트림 처리)
- 이유: 영화와 무관 독립 동기화, 그러나 매번 대규모 Upsert이므로 시간 소요

#### [3단계] 기존 배우 기준 삭제 처리 (선택사항)
```
person_sync.py → sync_people()  // 덤프로 삭제 + Change API로 갱신
```
- 소요 시간: 60~90초
- 이유: 영화 동기화 전에 신규 배우 발굴 전에 기존 배우 현황 정리

#### [4단계] 영화 메인 동기화 (가장 오래 걸림)
```
movie_sync.py → sync_movies()
  Phase 1: DB 스캔 (기존 영화 목록 메모리 맵)
  Phase 2: 덤프 대조 (신규/삭제/제목변경 식별)
  Phase 3: Change API 호출 (정보 변경된 영화 ID 수집)
  Phase 4: 1,000건씩 청크로 API 호출 & DB Upsert
           → 신규 배우 발굴 → 배우 INSERT
           → 매핑 테이블 5개 갱신 (삭제 후 재삽입)
```
- 소요 시간: 5~30분 (영화 수, API 호출 빈도에 따라 가변)
- 이유: 가장 복잡하고 시간 소요, 다른 모든 메타데이터에 종속

---

## 🔍 각 SYNCHRONIZER 상세 역할

### 1️⃣ meta_sync.py (MetaSynchronizer)
```python
sync_genres(session)
  1. fetch_genres() → TMDB API 호출
  2. DB에서 기존 tmdb_id 목록 조회
  3. 신규 장르만 필터링
  4. INSERT (Conflict 무시)
  
sync_otts(session)
  1. fetch_otts(session, "KR") → TMDB API 호출 (한국 지역만)
  2. DB에서 기존 tmdb_id 목록 조회
  3. 신규 OTT만 필터링
  4. INSERT (Conflict 무시)
```
**결과**: 최대 100~200개 장르/OTT 추가 (변동 거의 없음)

### 2️⃣ keyword_sync.py (KeywordSynchronizer)
```python
sync_keywords(date_str)
  Phase 1: download_dump("keyword_ids", date_str) → 대용량 gzip 다운
  Phase 2: DB에서 기존 키워드 tmdb_id 풀 로드
  Phase 3: 덤프 스트림 파싱
           - 신규 키워드 수집
           - 덤프에서 삭제된 키워드 식별
  Phase 4: 신규 5,000건씩 청크로 INSERT
  Phase 5: 삭제 대상 DELETE
```
**결과**: 보통 10,000~50,000개 키워드 신규 추가/삭제

### 3️⃣ person_sync.py (PersonSynchronizer)
```python
sync_people(aio_session, date_str, start_date, end_date)
  Step 1: DB에서 기존 배우 tmdb_id 목록 로드
  Step 2: download_dump("person_ids", date_str) → 덤프 다운
  Step 3: 덤프 스트림 파싱, 삭제 대상 식별 및 DELETE
  Step 4: fetch_changes("/person/changes") → 정보 변경된 배우 ID 수집
  Step 5: 변경 대상 비동기 API 호출 (Semaphore 40)
  Step 6: 배우 정보 UPDATE (이름, 한글 이름 등)
```
**결과**: 대개 수천~수만 명 배우 정보 업데이트

### 4️⃣ movie_sync.py (MovieSynchronizer) - 핵심 로직
```python
sync_movies(aio_session, date_str, start_date, end_date)

Phase 1: DB 스캔
  → 기존 영화 {tmdb_id: title} 메모리 맵 구축
  → genre_map, ott_map, keyword_map, person_map 구축

Phase 2: 덤프 대조
  → download_dump("movie_ids", date_str)
  → 신규 영화 식별 (DB에 없는 ID)
  → 삭제 대상 식별 (DB에는 있는데 덤프에 없는 ID)
  → 제목 변경 영화 식별 (tmdb_id 동일하나 title 다른 경우)
  → 삭제 대상 DELETE

Phase 3: Change API 호출
  → fetch_changes(start_date, end_date)
  → 정보 변경된 영화 ID 수집

Phase 4: 비동기 상세 조회 & DB Upsert (1,000건씩 청크)
  For each chunk:
    1. fetch_movie_details(mid) × N건 병렬 호출 (Semaphore 40)
    2. 신규 배우 발굴 → people INSERT
    3. 영화 본체 Upsert
    4. 매핑 테이블 5개:
       - movie_genres: 기존 DELETE 후 재INSERT
       - movie_otts: 기존 DELETE 후 재INSERT
       - movie_keywords: 기존 DELETE 후 재INSERT
       - movie_actors: 기존 DELETE 후 재INSERT (배우 최대 10명 제한 가능)
       - movie_directors: 기존 DELETE 후 재INSERT
    5. COMMIT (청크 단위 트랜잭션)
```
**결과**: 보통 10만~수십만 영화 신규/수정, 매핑 테이블 수백만 행 갱신

---

## 🔌 FETCHERS 상세 역할

### api_fetcher.py (TMDBApiFetcher)
```python
__init__()
  - TMDB_API_KEY 로드
  - base_url = "https://api.themoviedb.org/3"
  - Semaphore(40) 초당 API 호출 제한
  - error_log_path = "failed_sync_ids.log"

_fetch_with_retry(session, url, params, retries=3)
  - 재시도 로직 (3회까지)
  - 지수 백오프 (2초, 4초, 8초)
  - Rate Limit 대응 (429 상태 → Retry-After 헤더 대기)
  - 3회 모두 실패 시 failed_sync_ids.log에 기록

fetch_genres(session) → GET /genre/movie/list
fetch_otts(session) → GET /watch/providers/movie?watch_region=KR
fetch_movie_details(movie_id) → GET /movie/{id}?append_to_response=credits,keywords,watch/providers
fetch_changes(start_date, end_date) → GET /movie/changes?start_date=...&end_date=...
```

### dump_fetcher.py (TMDBDumpFetcher)
```python
__init__()
  - DOWNLOAD_DIR 설정 (./downloads)
  - 폴더 자동 생성

async download_dump(dump_type, date_str)
  dump_type: 'movie_ids', 'person_ids', 'keyword_ids'
  date_str: 'MM_DD_YYYY' (예: 04_24_2026)
  
  URL 구성: http://files.tmdb.org/p/exports/{dump_type}_{date_str}.json.gz
  
  - 파일 이미 존재하면 스킵
  - 1MB씩 청크 다운로드 (메모리 보호)
  - gzip 압축 파일 저장

get_dump_iterator(file_path)
  - gzip.open() + ijson 스트리밍 파싱
  - 한 줄씩 JSON 객체 yield (메모리 효율적)
  - 예: {id: 123, name: '키워드'} 한 줄씩 반환
```

---

## 💾 core/ 구조

### config.py
```python
DB_USER, DB_PASSWORD, DB_NAME, DB_HOST, DB_PORT
  → DATABASE_URL 조립 (docker-compose 주입값 우선)

TMDB_API_KEY
  → 환경변수 로드

DOWNLOAD_DIR
  → 덤프 다운로드 경로 (기본값: ./downloads)
```

### database.py
```python
- DB 연결 설정
- SQLAlchemy 세션 관리
```

### logger.py
```python
- 프로젝트 전역 로깅 설정
```

---

## 📋 현재 코드의 버그/불일치 (⚠️ 오점 리스트)

### ❌ 1. main.py가 비어있음
- **문제**: 시스템 진입점이 없어서 synchronizer들을 언제 어떤 순서로 실행할지 불명확
- **영향**: 프로젝트 자동화 불가능
- **필요 액션**: main.py에 orchestrator 로직 작성 필요

### ❌ 2. fetch_changes 메서드명 불일치
- **파일**: [synchronizers/movie_sync.py](synchronizers/movie_sync.py#L81), [synchronizers/person_sync.py](synchronizers/person_sync.py#L53)
- **호출**: `fetch_changes(aio_session, start_date, end_date, endpoint="/movie/changes")`
- **정의**: [fetchers/api_fetcher.py](fetchers/api_fetcher.py#L70)에는 endpoint 파라미터 없음
- **실제 정의**: `fetch_changes(session, start_date, end_date, page=1)`
- **버그**: movie_sync와 person_sync에서 endpoint 파라미터 추가되어 있으나 api_fetcher에는 미정의

### ❌ 3. _fetch_with_retry vs fetch_with_retry 명명 불일치
- **파일**: [synchronizers/person_sync.py](synchronizers/person_sync.py#L68)
- **호출**: `self.api_fetcher.fetch_with_retry(...)`
- **실제 정의**: [fetchers/api_fetcher.py](fetchers/api_fetcher.py#L17) `_fetch_with_retry` (언더스코어 접두)
- **버그**: 메서드명 오타 또는 접근성 오류

### ❌ 4. synchronizers/mapping_sync.py가 비어있음
- **문제**: 향후 매핑 동기화 로직 분리 지점으로 보이나 미구현
- **현황**: movie_sync.py에서 모든 매핑 로직 처리 중
- **필요 액션**: 아직은 영향 없으나 향후 refactor 예정인 듯

### ⚠️ 5. person_sync.py에서 Change API 엔드포인트 불일치 가능성
- **파일**: [synchronizers/person_sync.py](synchronizers/person_sync.py#L53)
- **호출**: `fetch_changes(aio_session, start_date, end_date, endpoint="/person/changes")`
- **문제**: api_fetcher의 fetch_changes 메서드가 "/movie/changes" 고정 (엔드포인트 변수화 필요)

### ⚠️ 6. movie_sync의 신규 배우 lazy insert 전략
- **파일**: [synchronizers/movie_sync.py](synchronizers/movie_sync.py#L145)
- **현황**: 영화 상세 조회 시 신규 배우 발굴 → 즉시 INSERT
- **장점**: 매핑 테이블 구축 시 배우 ID 보장
- **단점**: 영화 동기화 중에 배우 동기화가 숨어있음 (의도가 명확하지 않음)

### ⚠️ 7. Keyword 모델에 Unique 제약
- **파일**: [models/metadata.py](models/metadata.py#L22)
- **현황**: `name = Column(String(100), unique=True)`
- **문제**: TMDB 데이터 불량으로 동일한 이름을 가진 서로 다른 ID가 존재 가능
- **영향**: [synchronizers/keyword_sync.py](synchronizers/keyword_sync.py#L49) TODO 주석에 명시됨
- **위험**: Unique 제약 위반으로 INSERT 실패 가능

### ⚠️ 8. Genre, Ott 모델의 name_ko Unique 제약
- **파일**: [models/metadata.py](models/metadata.py#L11), [models/metadata.py](models/metadata.py#L14)
- **현황**: `name = Column(String(50), unique=True)` + `name_ko = Column(String(100), unique=True)`
- **문제**: API가 ko-KR 언어로만 반환하면 name ≈ name_ko (중복 Unique 제약)
- **영향**: 만약 영어 이름과 한글 이름이 다르게 들어오면 나중에 문제 가능

### ⚠️ 9. fetch_movie_details의 append_to_response 파라미터
- **파일**: [fetchers/api_fetcher.py](fetchers/api_fetcher.py#L63)
- **현황**: `append_to_response=credits,keywords,watch/providers`
- **잠재적 이슈**: watch/providers 응답 구조가 movie_sync에서 기대하는 구조와 맞는지 검증 필요

### ⚠️ 10. 매핑 테이블 삭제 후 재삽입 전략
- **파일**: [synchronizers/movie_sync.py](synchronizers/movie_sync.py#L245)
- **현황**: 기존 매핑 DELETE 후 새 매핑 INSERT
- **이유**: 부분 업데이트보다 빠르고 정합성 보장
- **단점**: 삭제 쿼리 + INSERT 쿼리로 2배 트래픽 (트랜잭션 내 원자성 보장되므로 문제 없음)

---

## 🎯 실행 검증 체크리스트

```
□ main.py 구현 완료 (orchestrator)
□ api_fetcher.fetch_changes 엔드포인트 매개변수화
□ person_sync의 fetch_with_retry 호출 수정
□ movie_sync의 fetch_changes 호출 파라미터 확인
□ TMDB 덤프 날짜 형식 확인 (MM_DD_YYYY)
□ Person, Keyword 메타데이터 Unique 제약 재검토
□ 첫 실행 시 모든 메타데이터 초기 로드 검증
□ 대량 데이터 시 청크 크기 최적화 (1,000 vs 5,000)
□ Rate Limit 430 → 429 대응 로직 재확인
```

---

## 📌 요약

**이 시스템은 매주/매일 TMDB를 폴링해서 우리 DB를 최신 상태로 유지하는 동기화 엔진입니다.**

1. **fetchers**: 외부 데이터 원천 (TMDB API + 덤프)에서 데이터 수집만 담당
2. **synchronizers**: 수집한 데이터와 기존 DB를 비교해서 INSERT/UPDATE/DELETE 결정
3. **models**: DB 스키마 (영화 + 메타데이터 + 매핑)
4. **core**: 설정, DB 연결, 로깅

**핵심 실행 순서**:
```
메타(1~2초) → 키워드(30~60초) → 배우(60~90초) → 영화(5~30분)
```

**다음 단계**: 현재 코드의 **버그/불일치 10가지**를 수정하면 프로젝트가 완성됨.
