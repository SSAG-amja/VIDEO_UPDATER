# 📋 코드 검사 가이드 (검사 순서)

## 🎯 검사 방향: 진입점 → 메서드 시그니처 → 각 synchronizer → 모델

---

## ✅ 검사 순서 (우선순위순)

### [1단계] 진입점 확인 - main.py
**왜**: 전체 프로젝트가 어떻게 실행되는지 파악하기 위함

```
파일: main.py
확인사항:
  □ 현재 비어있나?
  □ 만약 있다면, synchronizer 호출 순서가 메타→키→배우→영화인가?
  □ 비동기 세션(aiohttp.ClientSession) 관리는?
  □ DB 세션 관리는?
  □ 예외 처리는?

기대값:
  - meta_sync.sync_genres() + meta_sync.sync_otts()
  - keyword_sync.sync_keywords()
  - person_sync.sync_people()
  - movie_sync.sync_movies()
  
참고 파일:
  ARCHITECTURE.md의 "실행 순서" 섹션
```

---

### [2단계] api_fetcher.py 메서드 시그니처 검증
**왜**: 모든 synchronizer가 이 클래스의 메서드를 호출하므로, 정의와 호출이 일치해야 함

```
파일: fetchers/api_fetcher.py
확인사항:

1️⃣ 모든 public 메서드 목록 작성:
   □ fetch_genres(session)
   □ fetch_otts(session)
   □ fetch_movie_details(session, movie_id)
   □ fetch_changes(session, start_date, end_date, page=1)
   □ _fetch_with_retry(session, url, params, retries) [private]

2️⃣ 각 메서드의 반환 타입 확인:
   □ 모두 JSON dict 반환하나?
   □ 실패 시 None 반환하나?

3️⃣ 주의할 점:
   □ _fetch_with_retry 메서드가 "_" 언더스코어로 시작 (private)
   □ fetch_changes가 endpoint 파라미터를 받지 않음 (항상 /movie/changes)
   □ Semaphore(40) 적용되나?
```

체크리스트:
```python
# api_fetcher.py에서 다음 메서드들이 정의되어 있는지 확인
□ def _fetch_with_retry(self, session, url, params=None, retries=3):
□ def fetch_genres(self, session):
□ def fetch_otts(self, session):
□ def fetch_movie_details(self, session, movie_id):
□ def fetch_changes(self, session, start_date, end_date, page=1):
```

---

### [3단계] dump_fetcher.py 메서드 시그니처 검증
**왜**: keyword_sync, person_sync, movie_sync에서 모두 호출

```
파일: fetchers/dump_fetcher.py
확인사항:

1️⃣ 모든 public 메서드:
   □ async download_dump(dump_type: str, date_str: str) → str (파일 경로)
   □ get_dump_iterator(file_path: str) → generator

2️⃣ 각 메서드 사용처:
   □ download_dump("movie_ids", date_str) in movie_sync.py
   □ download_dump("keyword_ids", date_str) in keyword_sync.py
   □ download_dump("person_ids", date_str) in person_sync.py
   □ get_dump_iterator(file_path) 모두에서

3️⃣ 잠재적 버그:
   □ date_str 포맷이 정확히 'MM_DD_YYYY'인지?
   □ 파일 이미 존재 시 다시 다운로드 안 하는가? (효율성)
```

---

### [4단계] meta_sync.py 검증
**왜**: 가장 간단한 synchronizer, 버그 가능성 낮음

```
파일: synchronizers/meta_sync.py
확인사항:

1️⃣ sync_genres(session) 메서드:
   □ fetch_genres(session) 호출 후 신규만 필터링하나?
   □ INSERT 시 on_conflict_do_nothing() 있나?
   
2️⃣ sync_otts(session) 메서드:
   □ fetch_otts(session) 호출하나?
   □ OTT도 신규만 INSERT하나?

3️⃣ 문제점:
   □ Unique 제약이 name과 name_ko 둘 다 있음
   □ API가 ko-KR만 반환하면 name ≈ name_ko (중복 가능)
```

---

### [5단계] keyword_sync.py 검증
**왜**: 덤프 처리 로직 포함, TODO 주석 있음

```
파일: synchronizers/keyword_sync.py
확인사항:

1️⃣ sync_keywords(date_str) 메서드:
   Phase 1: □ download_dump("keyword_ids", date_str) 호출
   Phase 2: □ DB에서 기존 tmdb_id 목록 로드
   Phase 3: □ get_dump_iterator() 스트림 처리
   Phase 4: □ 신규 키워드 5,000건씩 청크 INSERT
   Phase 5: □ 삭제 대상 DELETE

2️⃣ 주의사항:
   □ Line 49의 TODO 주석: Keyword name이 UNIQUE인데 TMDB 불량 데이터 가능
   □ on_conflict_do_nothing() 있는지 확인
   □ 삭제 로직도 있는지 확인
```

---

### [6단계] person_sync.py 검증
**왜**: 버그 가능성 높음 (메서드명 오타, 엔드포인트 불일치)

```
파일: synchronizers/person_sync.py
확인사항:

🔴 CRITICAL BUGS:
   1️⃣ Line 68: fetch_with_retry() 호출
      └─ api_fetcher에는 "_fetch_with_retry" (언더스코어 있음)
      └─ 이름이 다르거나 접근 불가 오류 발생 가능
      
   2️⃣ Line 53: fetch_changes(..., endpoint="/person/changes")
      └─ api_fetcher.fetch_changes는 endpoint 파라미터 없음
      └─ /movie/changes 만 호출 가능한데, /person/changes 필요
      └─ 메서드 수정 필요

2️⃣ sync_people() 메서드 흐름:
   Step 1: □ DB에서 기존 배우 tmdb_id 로드
   Step 2: □ dump_fetcher.download_dump("person_ids", date_str)
   Step 3: □ 덤프와 비교해서 삭제 대상 DELETE
   Step 4: □ fetch_changes() 호출 (❌ 버그: 엔드포인트 고정)
   Step 5: □ 변경 대상 비동기 API 호출
   Step 6: □ UPDATE 실행

3️⃣ 수정 필요:
   □ fetch_with_retry() → _fetch_with_retry() 또는 public 메서드로 변경
   □ fetch_changes 메서드에 endpoint 파라미터 추가 필요
```

---

### [7단계] movie_sync.py 검증
**왜**: 가장 복잡한 로직, 여러 버그 가능성

```
파일: synchronizers/movie_sync.py
확인사항:

🔴 CRITICAL BUGS:
   1️⃣ Line 81: fetch_changes(..., endpoint="/movie/changes")
      └─ api_fetcher 정의에 endpoint 파라미터 없음
      └─ 실제 메서드 시그니처 확인 필요
      
2️⃣ 신규 배우 발굴 로직 (Line 145):
   □ Credits에서 신규 배우 식별 후 즉시 INSERT
   □ 의도가 명확한가? (movie_sync vs person_sync 책임 혼동)

3️⃣ OTT 매핑 로직 (Line 185):
   □ watch/providers 응답 구조가 예상대로인지?
   □ kr_providers 경로가 맞는지? (KR vs 다른 포맷)

4️⃣ Phase 4 청크 처리:
   □ 1,000건씩 청크 처리하나?
   □ Semaphore(40) 적용되나?
   □ 매핑 테이블 5개 모두 갱신하나?
   □ 삭제 후 재삽입 전략 사용하나?

체크포인트:
   Line 43-100: Phase 1 (DB 스캔) - 메모리 맵 구축
   Line 103-150: Phase 2 (덤프 대조) - 신규/삭제/제목변경
   Line 153-165: Phase 3 (Change API) - 변경분 수집
   Line 168+: Phase 4 (청크 Upsert) - API 호출 & DB 반영
```

---

### [8단계] models/ 검증
**왜**: Unique 제약과 관련된 데이터 정합성 문제

```
파일: models/metadata.py
확인사항:

1️⃣ Genre 테이블:
   □ name = Column(String(50), unique=True) ← UNIQUE
   □ name_ko = Column(String(100), unique=True) ← UNIQUE
   └─ API가 ko-KR만 반환 시 name ≈ name_ko (중복 가능)

2️⃣ Ott 테이블:
   □ name = Column(String(50), unique=True) ← UNIQUE
   □ name_ko = Column(String(100), unique=True) ← UNIQUE
   └─ 동일 문제

3️⃣ Keyword 테이블:
   □ name = Column(String(100), unique=True) ← UNIQUE
   └─ TMDB 불량 데이터로 서로 다른 id가 같은 name 가능
   └─ TODO 주석 있음 (keyword_sync.py Line 49)

4️⃣ Person 테이블:
   □ name_ko = Column(String(100), nullable=True)
   □ 임시 처리되어 있음 (추후 보강 예정)
```

---

### [9단계] models/mappings.py 검증
**왜**: 매핑 테이블 구조 확인

```
파일: models/mappings.py
확인사항:

1️⃣ 모든 매핑 테이블:
   □ MovieGenre (movie_id FK, genre_id FK)
   □ MovieOtt (movie_id FK, ott_id FK, is_streaming, is_rent, is_buy)
   □ MovieKeyword (movie_id FK, keyword_id FK)
   □ MovieActor (movie_id FK, actor_id FK, cast_name)
   □ MovieDirector (movie_id FK, director_id FK)

2️⃣ Cascade 설정:
   □ 모든 FK에 ondelete="CASCADE" 설정되어 있나?
   └─ 영화 삭제 시 매핑도 자동 삭제되는가?
```

---

### [10단계] core/ 검증
**왜**: 설정과 DB 연결 확인

```
파일: core/config.py
확인사항:

1️⃣ TMDB_API_KEY:
   □ 환경변수에서 로드되나?
   □ 로컬 테스트는 .env 파일?

2️⃣ DATABASE_URL:
   □ docker-compose 주입값 우선하나?
   □ postgresql+psycopg2 포맷 정확한가?

3️⃣ DOWNLOAD_DIR:
   □ ./downloads 경로 생성 되나?
```

---

## 🚨 발견된 10개 버그 우선순위

### 🔴 CRITICAL (지금 당장 수정 필요)

| 순위 | 버그 | 파일 | 라인 | 수정 난이도 |
|------|------|------|------|-----------|
| 1 | **main.py 비어있음** | main.py | - | ⭐⭐ (새로 작성) |
| 2 | **fetch_changes 엔드포인트 불일치** | api_fetcher.py + movie_sync.py + person_sync.py | L70, L81, L53 | ⭐⭐⭐ (메서드 수정) |
| 3 | **fetch_with_retry vs _fetch_with_retry** | person_sync.py | L68 | ⭐ (이름 수정) |
| 4 | **person_sync의 /person/changes 엔드포인트** | api_fetcher.py | L70 | ⭐⭐⭐ (메서드 수정) |

### 🟡 WARNING (곧 문제될 가능성)

| 순위 | 버그 | 파일 | 영향 |
|------|------|------|------|
| 5 | Keyword Unique 제약 중복 | models/metadata.py | INSERT 실패 가능 |
| 6 | Genre, Ott name_ko Unique | models/metadata.py | 중복 제약 위반 |
| 7 | 신규 배우 lazy insert | movie_sync.py | 책임 혼동 (경고 수준) |
| 8 | watch/providers 응답 구조 | movie_sync.py | 매핑 오류 가능 |

### 🔵 INFO (코드 리뷰)

| 순위 | 항목 | 파일 | 비고 |
|------|------|------|------|
| 9 | mapping_sync.py 비어있음 | synchronizers/ | 향후 refactor 지점 |
| 10 | 매핑 DELETE→INSERT 전략 | movie_sync.py | 성능 vs 정합성 trade-off |

---

## 📊 검사 작업 템플릿

각 파일을 검사할 때 이 템플릿을 사용하세요:

```markdown
## [파일명] 검사 결과

### ✅ 정상 항목
- [ ] 항목 1

### ⚠️ 주의 항목
- [ ] 항목 1

### ❌ 오류 항목
- [ ] 항목 1
- [ ] 항목 2
```

---

## 🎯 권장 검사 순서 (소요 시간)

```
1. main.py (5분) - 진입점 확인
2. api_fetcher.py (10분) - 메서드 시그니처 모두 확인
3. dump_fetcher.py (5분) - 간단함
4. meta_sync.py (5분) - 간단함
5. keyword_sync.py (5분) - TODO 주석 확인
6. person_sync.py (15분) - 🔴 버그 2개 있음
7. movie_sync.py (20분) - 🔴 버그 1개 + 복잡한 로직
8. models/metadata.py (10분) - Unique 제약 재검토
9. models/mappings.py (5분) - FK 구조 확인
10. core/config.py (5분) - 설정 확인

총 소요 시간: 약 85분
```

---

## 💡 검사 팁

1. **Grep 사용**: 각 메서드 호출을 grep으로 검색해서 정의와 비교
   ```bash
   grep -r "fetch_with_retry" .
   grep -r "fetch_changes" .
   ```

2. **타입 힌트 확인**: Python 타입 힌트로 예상 파라미터/반환값 파악

3. **에러 로그 확인**: failed_sync_ids.log 내용 (실패한 ID 기록)

4. **비동기 처리**: async/await 있는지 확인, 세마포어 적용 확인

5. **트랜잭션**: await db.commit() 위치 확인 (원자성 보장)

---

이제 **1번 main.py부터 차례대로** 검사하면 됩니다! 🚀
