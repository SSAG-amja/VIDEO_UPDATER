FROM python:3.11

# 작업 디렉토리 설정 (기존 /back에서 /app으로 변경하여 구조 통일)
WORKDIR /app

# 필수 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 서버가 아닌 데이터 최신화 스크립트(main.py)를 실행
# 만약 이 백엔드도 API 형태를 띠게 된다면 uvicorn으로 변경 가능합니다.
CMD ["python", "main.py"]