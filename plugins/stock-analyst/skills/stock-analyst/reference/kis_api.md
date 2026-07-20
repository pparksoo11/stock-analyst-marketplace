# KIS Open API 레퍼런스 (이 스킬에서 쓰는 것 + 확장)

공식 문서: https://apiportal.koreainvestment.com
공식 샘플(LLM 친화적): https://github.com/koreainvestment/open-trading-api

## Base URL
- 실전: `https://openapi.koreainvestment.com:9443`
- 모의: `https://openapivts.koreainvestment.com:29443`

## 공통 헤더
```
content-type : application/json; charset=utf-8
authorization: Bearer {access_token}
appkey       : {APP_KEY}
appsecret    : {APP_SECRET}
tr_id        : (API별 상이)
custtype     : P   (개인)
```

## 1. 접근토큰 발급  (스킬에서 사용)
`POST /oauth2/tokenP`
```json
{"grant_type":"client_credentials","appkey":"...","appsecret":"..."}
```
- 응답: `access_token`, `expires_in`(초). 유효 1일.
- **잦은 재발급 차단** → 반드시 캐싱 (kis_client.py가 `~/.kis_token.json`에 처리).

## 2. 주식현재가 시세  (스킬에서 사용)
`GET /uapi/domestic-stock/v1/quotations/inquire-price` · `tr_id: FHKST01010100`
- params: `fid_cond_mrkt_div_code=J`, `fid_input_iscd=<6자리코드>`
- 주요 output: `stck_prpr`(현재가), `hts_kor_isnm`(종목명), `prdy_ctrt`(전일대비율), `w52_hgpr/w52_lwpr`(52주 고저), `per`, `pbr`, `hts_avls`(시총)

## 3. 국내주식 기간별시세 (일/주/월/년)  (스킬 핵심)
`GET /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` · `tr_id: FHKST03010100`
- params:
  - `FID_COND_MRKT_DIV_CODE=J` (주식/ETF/ETN)
  - `FID_INPUT_ISCD=<코드>`
  - `FID_INPUT_DATE_1=<시작 YYYYMMDD>`, `FID_INPUT_DATE_2=<종료 YYYYMMDD>`
  - `FID_PERIOD_DIV_CODE=D|W|M|Y`
  - `FID_ORG_ADJ_PRC=0(수정주가)|1(원주가)`
- output1: 종목 요약 / output2: 캔들 배열(최대 ~100봉, 최신순)
  - `stck_bsop_date`(일자), `stck_oprc/stck_hgpr/stck_lwpr/stck_clpr`(시고저종), `acml_vol`(거래량)
- **100봉 제한** → 더 긴 히스토리는 날짜 창을 뒤로 밀며 반복 (kis_client.get_ohlcv가 처리).

## 4. 주식잔고조회  (스킬에서 사용, account 필요)
`GET /uapi/domestic-stock/v1/trading/inquire-balance`
- tr_id: 실전 `TTTC8434R` / 모의 `VTTC8434R`
- params: `CANO`(계좌 앞8), `ACNT_PRDT_CD`(뒤2), `AFHR_FLPR_YN=N`, `INQR_DVSN=02`, `UNPR_DVSN=01`, `FUND_STTL_ICLD_YN=N`, `FNCG_AMT_AUTO_RDPT_YN=N`, `PRCS_DVSN=01`, `OFL_YN=""`, `CTX_AREA_FK100=""`, `CTX_AREA_NK100=""`
- output1(종목별): `pdno`(코드), `prdt_name`(명), `hldg_qty`(수량), `pchs_avg_pric`(매입평균), `prpr`(현재가), `evlu_pfls_rt`(평가손익률)

---

## 확장 아이디어 (필요 시 구현)

### 순위분석 (스크리닝용)
- 등락률 순위: `/uapi/domestic-stock/v1/ranking/fluctuation`
- 거래량 순위: `/uapi/domestic-stock/v1/quotations/volume-rank`
- 각 tr_id/파라미터는 공식 문서의 [국내주식] > [순위분석] 참조.

### 투자자별 매매동향
- 주식현재가 투자자: `inquire-investor` (외국인/기관 순매수 참고).

### 실시간 (WebSocket)
- 체결가 `H0STCNT0` 등. 실시간 감시가 필요할 때. 승인키 별도 발급.

### 해외주식
- `/uapi/overseas-price/...` 계열. 티커·거래소코드(NAS/NYS 등) 필요. 요청 시 별도 모듈로.

> 확장 시 원칙 유지: 스크립트는 숫자만, 해석은 Claude. 예측·조언 금지.
