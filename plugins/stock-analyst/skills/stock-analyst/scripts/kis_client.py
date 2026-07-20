"""
kis_client.py — 한국투자증권 KIS Open API 클라이언트

확인된 스펙 (2026 기준, apiportal.koreainvestment.com):
  - 토큰 발급   POST /oauth2/tokenP   {grant_type:client_credentials, appkey, appsecret}
                 access_token 유효 1일. 자주 재발급하면 차단되므로 파일 캐싱 필수.
  - 현재가      GET  /uapi/domestic-stock/v1/quotations/inquire-price       tr_id FHKST01010100
  - 기간별시세  GET  /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice  tr_id FHKST03010100
                 FID_PERIOD_DIV_CODE = D(일)/W(주)/M(월)/Y(년), output2 = 캔들배열(최대 ~100봉)
  - 주식잔고    GET  /uapi/domestic-stock/v1/trading/inquire-balance        tr_id TTTC8434R(실전)/VTTC8434R(모의)

실전 base: https://openapi.koreainvestment.com:9443
모의 base: https://openapivts.koreainvestment.com:29443

주의: 이 파일은 실제 인증정보로 네 환경에서 실행된다. 인증정보는 config/credentials.yaml
      (git 제외) 또는 환경변수로만 주입한다. 코드에 하드코딩 금지.
"""
from __future__ import annotations
import os
import json
import time
import datetime as dt
from pathlib import Path

import requests
import pandas as pd
import yaml

REAL_BASE = "https://openapi.koreainvestment.com:9443"
MOCK_BASE = "https://openapivts.koreainvestment.com:29443"
TOKEN_CACHE = Path.home() / ".kis_token.json"


class KISClient:
    def __init__(self, config_path: str | None = None):
        cfg = self._load_config(config_path)
        self.appkey = cfg["appkey"]
        self.appsecret = cfg["appsecret"]
        self.account = str(cfg.get("account", ""))          # 8자리-2자리 (예: 12345678-01)
        self.env = cfg.get("env", "real")                    # 'real' | 'mock'
        self.base = REAL_BASE if self.env == "real" else MOCK_BASE
        self._token = None
        self._token_exp = 0

    # ---------------- config ----------------
    @staticmethod
    def _load_config(path: str | None) -> dict:
        # 1) 환경변수 우선
        if os.getenv("KIS_APPKEY") and os.getenv("KIS_APPSECRET"):
            return {
                "appkey": os.environ["KIS_APPKEY"],
                "appsecret": os.environ["KIS_APPSECRET"],
                "account": os.getenv("KIS_ACCOUNT", ""),
                "env": os.getenv("KIS_ENV", "real"),
            }
        # 2) yaml 파일
        candidates = [path] if path else []
        candidates += [
            str(Path(__file__).parent.parent / "config" / "credentials.yaml"),
            str(Path.home() / ".kis" / "credentials.yaml"),
        ]
        for c in candidates:
            if c and Path(c).exists():
                with open(c, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
        raise FileNotFoundError(
            "KIS 인증정보를 찾을 수 없습니다. 환경변수(KIS_APPKEY/KIS_APPSECRET) 또는 "
            "config/credentials.yaml 을 설정하세요. (credentials.example.yaml 참고)"
        )

    # ---------------- token ----------------
    def _read_cached_token(self):
        if not TOKEN_CACHE.exists():
            return None
        try:
            data = json.loads(TOKEN_CACHE.read_text())
            if data.get("env") != self.env or data.get("appkey") != self.appkey:
                return None
            if data.get("exp", 0) > time.time() + 300:  # 5분 여유
                return data
        except Exception:
            return None
        return None

    def get_access_token(self) -> str:
        if self._token and self._token_exp > time.time() + 300:
            return self._token
        cached = self._read_cached_token()
        if cached:
            self._token = cached["token"]
            self._token_exp = cached["exp"]
            return self._token

        url = f"{self.base}/oauth2/tokenP"
        body = {"grant_type": "client_credentials",
                "appkey": self.appkey, "appsecret": self.appsecret}
        r = requests.post(url, json=body, timeout=10)
        r.raise_for_status()
        j = r.json()
        self._token = j["access_token"]
        # expires_in(초) 제공. 안전하게 -600초.
        self._token_exp = time.time() + int(j.get("expires_in", 86400)) - 600
        TOKEN_CACHE.write_text(json.dumps(
            {"token": self._token, "exp": self._token_exp,
             "env": self.env, "appkey": self.appkey}))
        try:
            os.chmod(TOKEN_CACHE, 0o600)
        except Exception:
            pass
        return self._token

    def _headers(self, tr_id: str) -> dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.appkey,
            "appsecret": self.appsecret,
            "tr_id": tr_id,
            "custtype": "P",   # 개인
        }

    def _get(self, path: str, tr_id: str, params: dict) -> dict:
        url = f"{self.base}{path}"
        r = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        r.raise_for_status()
        j = r.json()
        if str(j.get("rt_cd", "0")) != "0":
            raise RuntimeError(f"KIS API 오류 [{j.get('msg_cd')}] {j.get('msg1')}")
        return j

    # ---------------- 현재가 ----------------
    def get_current_price(self, code: str) -> dict:
        j = self._get("/uapi/domestic-stock/v1/quotations/inquire-price",
                      "FHKST01010100",
                      {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code})
        o = j["output"]
        return {
            "code": code,
            "name": o.get("hts_kor_isnm"),
            "price": float(o["stck_prpr"]),
            "change_pct": float(o.get("prdy_ctrt", 0)),
            "high52": float(o.get("w52_hgpr", 0) or 0),
            "low52": float(o.get("w52_lwpr", 0) or 0),
            "per": o.get("per"),
            "pbr": o.get("pbr"),
            "market_cap": o.get("hts_avls"),
        }

    # ---------------- 기간별 시세 (일/주/월/년) ----------------
    def get_ohlcv(self, code: str, period: str = "D",
                  count: int = 300, adjusted: bool = True) -> pd.DataFrame:
        """
        period: 'D'(일) 'W'(주) 'M'(월) 'Y'(년)
        count : 확보하려는 최소 봉 개수. 한 호출당 ~100봉이라 부족하면 날짜 창을 뒤로 밀며 반복.
        adjusted: 수정주가 여부 (FID_ORG_ADJ_PRC: 0=수정주가, 1=원주가) -> True면 '0'
        """
        assert period in ("D", "W", "M", "Y")
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"
        end = dt.date.today()
        frames, guard = [], 0
        oldest_seen = None

        while True:
            guard += 1
            if guard > 12:
                break
            start = self._window_start(end, period)
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": period,
                "FID_ORG_ADJ_PRC": "0" if adjusted else "1",
            }
            j = self._get(path, tr_id, params)
            rows = j.get("output2") or []
            rows = [r for r in rows if r.get("stck_bsop_date")]
            if not rows:
                break
            frames.append(rows)

            dates = [r["stck_bsop_date"] for r in rows]
            batch_oldest = min(dates)
            if oldest_seen is not None and batch_oldest >= oldest_seen:
                break  # 더 이상 과거로 안 감
            oldest_seen = batch_oldest

            total = sum(len(f) for f in frames)
            if total >= count:
                break
            # 다음 창: 가장 오래된 날짜 하루 전으로 이동
            end = dt.datetime.strptime(batch_oldest, "%Y%m%d").date() - dt.timedelta(days=1)
            time.sleep(0.12)  # 유량제한 보호

        return self._rows_to_df(frames, count)

    @staticmethod
    def _window_start(end: dt.date, period: str) -> dt.date:
        # 한 호출에 ~100봉을 채우도록 넉넉한 창 설정
        if period == "D":
            return end - dt.timedelta(days=200)      # 영업일 ~130
        if period == "W":
            return end - dt.timedelta(weeks=110)
        if period == "M":
            return end - dt.timedelta(days=31 * 110)
        return end - dt.timedelta(days=366 * 100)    # Y

    @staticmethod
    def _rows_to_df(frames: list, count: int) -> pd.DataFrame:
        flat = [r for f in frames for r in f]
        if not flat:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        seen, uniq = set(), []
        for r in flat:
            d = r["stck_bsop_date"]
            if d in seen:
                continue
            seen.add(d)
            uniq.append(r)
        df = pd.DataFrame({
            "date": [pd.to_datetime(r["stck_bsop_date"], format="%Y%m%d") for r in uniq],
            "open": [float(r["stck_oprc"]) for r in uniq],
            "high": [float(r["stck_hgpr"]) for r in uniq],
            "low": [float(r["stck_lwpr"]) for r in uniq],
            "close": [float(r["stck_clpr"]) for r in uniq],
            "volume": [float(r.get("acml_vol", 0) or 0) for r in uniq],
        })
        df = df.sort_values("date").reset_index(drop=True)
        return df.tail(count).reset_index(drop=True)

    # ---------------- 잔고 (보유종목) ----------------
    def get_balance(self) -> pd.DataFrame:
        """보유 종목 목록. account 설정 필요. (실전 TTTC8434R / 모의 VTTC8434R)"""
        if "-" not in self.account:
            raise ValueError("account 형식은 '12345678-01' 이어야 합니다.")
        cano, acnt_prdt = self.account.split("-")
        tr_id = "TTTC8434R" if self.env == "real" else "VTTC8434R"
        params = {
            "CANO": cano, "ACNT_PRDT_CD": acnt_prdt,
            "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
            "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        }
        j = self._get("/uapi/domestic-stock/v1/trading/inquire-balance", tr_id, params)
        holdings = j.get("output1") or []
        recs = []
        for h in holdings:
            qty = float(h.get("hldg_qty", 0) or 0)
            if qty <= 0:
                continue
            recs.append({
                "code": h.get("pdno"),
                "name": h.get("prdt_name"),
                "quantity": qty,
                "avg_price": float(h.get("pchs_avg_pric", 0) or 0),
                "current_price": float(h.get("prpr", 0) or 0),
                "eval_pl_pct": float(h.get("evlu_pfls_rt", 0) or 0),
            })
        return pd.DataFrame(recs)


if __name__ == "__main__":
    # 간단 연결 테스트 (네 환경에서만 동작)
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "005930"
    c = KISClient()
    print("현재가:", c.get_current_price(code))
    for p in ("D", "W", "M", "Y"):
        df = c.get_ohlcv(code, p, count=250 if p == "D" else 120)
        print(f"[{p}] {len(df)}봉  최근:", df.iloc[-1].to_dict() if len(df) else "없음")
