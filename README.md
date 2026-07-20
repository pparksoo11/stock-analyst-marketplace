# yeonsu-tools — Claude Code 플러그인 마켓플레이스

개인용 Claude Code 플러그인 모음. 현재 `stock-analyst` 하나 포함 — 한국 주식(KOSPI/KOSDAQ)을 한국투자증권 KIS Open API로 분석하는 **읽기·분석 전용** 플러그인. 매수/매도 주문 기능은 없다.

## 설치

```
/plugin marketplace add pparksoo11/stock-analyst-marketplace
/plugin install stock-analyst@yeonsu-tools
```

로컬 폴더에서 바로 테스트하려면:
```
/plugin marketplace add ./stock-analyst-marketplace
/plugin install stock-analyst@yeonsu-tools
/plugin validate ./stock-analyst-marketplace   # 검증
```

자체 GitLab 등에 올려서 쓸 때도 동일하게 `/plugin marketplace add <git-url>`. 사설 저장소면 git 자격증명(`gh auth login` 또는 credential helper)이 미리 설정돼 있어야 한다.

## 사용법

설치 후 슬래시 명령 없이 그냥 대화로:

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

**기능**: 일/주/월/연봉 4개 타임프레임 기술적 지표(이동평균·RSI·MACD·볼린저·스토캐스틱·ATR·지지저항) · 뉴스 호재/악재 정리 · 목표가/손절가 계산(percent·ATR·지지저항 3방식 동시 제공).

## 최초 1회 설정 — 인증정보 (KIS Open API)

한국투자증권 계좌 개설 → [KIS Developers](https://apiportal.koreainvestment.com)에서 App Key/Secret 발급 → 아래 중 하나로 주입 (플러그인 폴더 밖에 둘 것 — 플러그인 폴더는 업데이트 시 덮어써진다):

```bash
export KIS_APPKEY="발급받은_APP_KEY_36자리"
export KIS_APPSECRET="발급받은_APP_SECRET_180자리"
export KIS_ENV="real"          # real=실전, mock=모의
# export KIS_ACCOUNT="12345678-01"   # 잔고조회(--balance) 쓸 때만
```

또는 `~/.kis/credentials.yaml` — 자세한 설정법·우선순위는 [플러그인 README](plugins/stock-analyst/README.md) 참고.

파이썬 의존성:
```bash
pip install -r plugins/stock-analyst/skills/stock-analyst/requirements.txt
```

> **인증정보는 절대 이 저장소에 커밋하지 않는다.** `config/credentials.yaml`, `config/holdings.yaml`, `~/.kis/`는 이미 `.gitignore`로 제외되어 있다.

## 구조

```
stock-analyst-marketplace/
├── .claude-plugin/marketplace.json   # 마켓플레이스 카탈로그
└── plugins/stock-analyst/
    ├── .claude-plugin/plugin.json    # 플러그인 매니페스트
    ├── commands/analyze.md           # /stock-analyst:analyze
    ├── skills/stock-analyst/         # SKILL.md + scripts + reference
    └── README.md                     # 플러그인 상세 문서
```

## 주의

지표·목표가는 현재 상태의 정량 요약이며 주가 예측이나 매매 권유가 아니다. 투자 판단과 결과는 본인 책임이다.
