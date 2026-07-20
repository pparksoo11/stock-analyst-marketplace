"""
analyze.py — 스킬의 메인 진입점

사용법:
    python scripts/analyze.py <종목코드> [--name 이름] [--tf D,W,M,Y] [--count 300]
    python scripts/analyze.py --portfolio            # config/holdings.yaml 기반 목표가 계산
    python scripts/analyze.py --balance              # KIS 잔고 자동조회 후 목표가 계산

출력: 구조화된 JSON (stdout). Claude가 이 JSON을 읽고 자연어 분석/뉴스와 결합한다.
      스크립트는 숫자만 책임진다(결정론적). 해석·서술은 Claude가 한다.
"""
from __future__ import annotations
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import indicators as ind
import targets as tg
from kis_client import KISClient

TF_LABEL = {"D": "일봉", "W": "주봉", "M": "월봉", "Y": "연봉"}


def analyze_ticker(client: KISClient, code: str, name: str | None = None,
                   timeframes=("D", "W", "M", "Y"), count: int = 300) -> dict:
    quote = client.get_current_price(code)
    result = {
        "code": code,
        "name": name or quote.get("name"),
        "quote": quote,
        "timeframes": {},
        "disclaimer": "지표 계산 결과이며 매매 권유가 아님. 예측이 아니라 현재 상태의 정량 요약임.",
    }
    day_atr = None
    day_levels = None
    for tf in timeframes:
        need = count if tf == "D" else 120
        df = client.get_ohlcv(code, tf, count=need)
        if len(df) == 0:
            result["timeframes"][tf] = {"timeframe": tf, "error": "데이터 없음"}
            continue
        summ = ind.summarize(df, tf)
        summ["label"] = TF_LABEL.get(tf, tf)
        result["timeframes"][tf] = summ
        if tf == "D":
            day_atr = summ.get("atr14", {}).get("value")
            day_levels = summ.get("levels")
    # 목표가 계산에 쓸 부가정보
    result["_enrich"] = {"atr": day_atr, "levels": day_levels}
    return result


def analyze_portfolio(client: KISClient, holdings: list, rules: dict | None = None,
                      fetch_levels: bool = True) -> list:
    enrich = {}
    for h in holdings:
        code = h.get("code")
        if not code:
            continue
        try:
            q = client.get_current_price(code)
            if not h.get("current_price"):
                h["current_price"] = q["price"]
            if not h.get("name"):
                h["name"] = q.get("name")
            if fetch_levels:
                df = client.get_ohlcv(code, "D", count=200)
                if len(df):
                    s = ind.summarize(df, "D")
                    enrich[code] = {"atr": s["atr14"]["value"], "levels": s["levels"]}
        except Exception as e:
            enrich[code] = {"error": str(e)}
    return tg.compute_portfolio(holdings, enrich=enrich, rules=rules)


def _load_yaml(path: str):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", help="종목코드 6자리 (예: 005930)")
    ap.add_argument("--name")
    ap.add_argument("--tf", default="D,W,M,Y", help="타임프레임 (예: D,W,M,Y)")
    ap.add_argument("--count", type=int, default=300)
    ap.add_argument("--portfolio", action="store_true", help="config/holdings.yaml 목표가 계산")
    ap.add_argument("--balance", action="store_true", help="KIS 잔고 자동조회")
    ap.add_argument("--config")
    args = ap.parse_args()

    client = KISClient(args.config)
    base = Path(__file__).parent.parent

    if args.balance:
        df = client.get_balance()
        holdings = df.to_dict("records")
        rules = None
        rp = base / "config" / "holdings.yaml"
        if rp.exists():
            rules = (_load_yaml(str(rp)) or {}).get("rules")
        out = analyze_portfolio(client, holdings, rules=rules)
        print(json.dumps({"portfolio": out}, ensure_ascii=False, indent=2, default=str))
        return

    if args.portfolio:
        cfg = _load_yaml(str(base / "config" / "holdings.yaml"))
        out = analyze_portfolio(client, cfg.get("holdings", []), rules=cfg.get("rules"))
        print(json.dumps({"portfolio": out}, ensure_ascii=False, indent=2, default=str))
        return

    if not args.code:
        ap.error("종목코드가 필요합니다. 또는 --portfolio / --balance 사용")

    tfs = tuple(t.strip() for t in args.tf.split(",") if t.strip())
    out = analyze_ticker(client, args.code, args.name, tfs, args.count)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
