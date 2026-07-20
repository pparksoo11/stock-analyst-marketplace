# stock-analyst (Claude Code 플러그인)

한국 주식(KOSPI/KOSDAQ)을 한국투자증권 KIS Open API로 분석하는 **읽기·분석 전용** 플러그인.
매수/매도 주문 기능은 없다.

## 기능

- **기술적 분석** — 일/주/월/연봉 4개 타임프레임 지표(이동평균·RSI·MACD·볼린저·스토캐스틱·ATR·지지저항)
- **방향성 예측** — 지표를 결정론적으로 가중 종합한 단기(1~4주)·중기(1~3개월) 시나리오 확률·신뢰도
- **뉴스 호재/악재 정리** — 종목 관련 최신 뉴스를 사실 위주로 정리
- **목표가/손절가 계산** — 사용자가 정한 규칙(예: 목표 10%·손절 8%)으로 계산 (percent / ATR / 지지저항)
- **답변 전 검증 게이트** — 결정론적 정합성 검사(`verify.py`) + 별도 검증 에이전트(LLM) 통과 후 출력

## 대화형 사용 (설치만 하면 됨)

슬래시 명령 없이 그냥 대화로:

```
삼성전자 분석해줘
005930 주봉 월봉 어때?
내 보유종목 목표가/손절가 정리해줘
카카오 뉴스 호재 악재 정리해줘
```

명시적 슬래시 명령도 가능:

```
/stock-analyst:analyze 005930
```

## 인증정보 설정 (플러그인 환경 주의)

플러그인은 설치 시 캐시 디렉토리로 **복사**되고 업데이트 때 덮어써진다.
그래서 인증정보를 플러그인 폴더 안(`config/credentials.yaml`)에 두면 업데이트 시 사라진다.
**아래 둘 중 하나를 쓸 것 (플러그인 폴더 밖):**

**방법 1 — 홈 디렉토리 파일 (권장)**
```bash
mkdir -p ~/.kis
cat > ~/.kis/credentials.yaml <<'YAML'
appkey: "발급받은_APP_KEY_36자리"
appsecret: "발급받은_APP_SECRET_180자리"
account: "12345678-01"   # 잔고조회 쓸 때만
env: "real"              # real=실전, mock=모의
YAML
chmod 600 ~/.kis/credentials.yaml
```

**방법 2 — 환경변수** (`~/.zshrc` 등에 추가)
```bash
export KIS_APPKEY="..."
export KIS_APPSECRET="..."
export KIS_ENV="real"
# export KIS_ACCOUNT="12345678-01"   # 선택
```

스킬은 ①환경변수 → ②플러그인 내 config → ③`~/.kis/credentials.yaml` 순으로 인증정보를 찾는다.

## 파이썬 의존성

스크립트 실행에 필요:
```bash
pip install -r requirements.txt   # requests, pandas, numpy, PyYAML
```

## 주의

- 방향성 예측은 결정론적 점수(`scripts/scoring.py`)를 확률·신뢰도로 표현한 참고 정보이며 확정된 미래가 아니다. 매매 권유도 아니다.
- 모든 답변은 결정론적 정합성 검사(`scripts/verify.py`)와 별도 검증 에이전트(LLM) 통과 후에만 출력된다.
- 실제 투자 판단과 결과는 본인 책임이다.
