"""_get() 페이싱/재시도 가드 최소 점검. 실행: python3 scripts/test_kis_client_retry.py"""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from kis_client import KISClient


def _client():
    c = object.__new__(KISClient)  # 실제 credentials 없이 인스턴스만 구성
    c.appkey, c.appsecret, c.account, c.env = "k", "s", "", "real"
    c.base = "https://example.invalid"
    c._token, c._token_exp, c._last_call = "t", 9e18, 0.0
    return c


def test_retries_on_500_then_succeeds():
    c = _client()
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"rt_cd": "0", "output": {}}
    ok.raise_for_status.return_value = None
    bad = MagicMock(status_code=500)
    with patch("kis_client.requests.get", side_effect=[bad, ok]), \
         patch("kis_client.time.sleep"):
        j = c._get("/p", "tr", {})
    assert j["rt_cd"] == "0"


def test_raises_after_exhausting_retries():
    c = _client()
    bad = MagicMock(status_code=500)
    bad.raise_for_status.side_effect = RuntimeError("500")
    with patch("kis_client.requests.get", return_value=bad), \
         patch("kis_client.time.sleep"):
        try:
            c._get("/p", "tr", {})
        except RuntimeError:
            return
    raise AssertionError("500이 반복돼도 예외가 발생하지 않음")


if __name__ == "__main__":
    test_retries_on_500_then_succeeds()
    test_raises_after_exhausting_retries()
    print("OK")
