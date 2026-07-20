"""
targets.py — 보유 종목 목표가/손절가 '계산기'

중요: 이건 조언 도구가 아니라 계산기다.
    사용자가 정한 규칙(목표수익률, 손절률, ATR배수 등)을 받아서 가격을 산출할 뿐,
    "여기서 팔아라/사라"를 결정하지 않는다. R:R(손익비)까지 계산해 판단은 사용자가 한다.

세 가지 방식을 동시에 제시한다:
    1) 퍼센트 방식  : 매입가 또는 현재가 기준 ±%
    2) ATR 방식     : 변동성(ATR) 배수 기반 (변동성 큰 종목엔 손절폭을 넓게)
    3) 지지/저항 방식: 가까운 지지 아래를 손절, 가까운 저항을 1차 목표로
"""
from __future__ import annotations


DEFAULT_RULES = {
    "target_conservative_pct": 10.0,   # 보수적 목표 수익률 %
    "target_aggressive_pct": 25.0,     # 공격적 목표 수익률 %
    "stop_loss_pct": 8.0,              # 손절 손실률 %
    "basis": "avg_price",             # 'avg_price'(매입가) 또는 'current'(현재가) 기준
    "atr_stop_mult": 2.0,             # 손절 = 현재가 - atr_stop_mult * ATR
    "atr_target_mult": 4.0,           # 목표 = 현재가 + atr_target_mult * ATR
}


def _pct(a: float, b: float) -> float:
    if not b:
        return 0.0
    return round((a / b - 1) * 100, 2)


def compute_for_holding(holding: dict, atr: float | None = None,
                        levels: dict | None = None, rules: dict | None = None) -> dict:
    """
    holding: {code, name, avg_price, quantity, current_price}
    atr    : 일봉 ATR14 값 (없으면 ATR 방식 생략)
    levels : {'nearest_support':..,'nearest_resistance':..} (없으면 지지/저항 방식 생략)
    rules  : DEFAULT_RULES 오버라이드
    """
    r = {**DEFAULT_RULES, **(rules or {})}
    avg = float(holding.get("avg_price") or 0)
    cur = float(holding.get("current_price") or 0)
    qty = float(holding.get("quantity") or 0)
    basis = avg if (r["basis"] == "avg_price" and avg > 0) else cur

    out = {
        "code": holding.get("code"),
        "name": holding.get("name"),
        "avg_price": round(avg, 2) if avg else None,
        "current_price": round(cur, 2) if cur else None,
        "quantity": qty,
        "unrealized_pl_pct": _pct(cur, avg) if avg else None,
        "unrealized_pl_amt": round((cur - avg) * qty, 0) if avg else None,
        "basis_used": r["basis"],
        "methods": {},
    }

    # 1) 퍼센트 방식
    tc = round(basis * (1 + r["target_conservative_pct"] / 100), 2)
    ta = round(basis * (1 + r["target_aggressive_pct"] / 100), 2)
    sl = round(basis * (1 - r["stop_loss_pct"] / 100), 2)
    out["methods"]["percent"] = {
        "target_conservative": {"price": tc, "from_current_pct": _pct(tc, cur)},
        "target_aggressive": {"price": ta, "from_current_pct": _pct(ta, cur)},
        "stop_loss": {"price": sl, "from_current_pct": _pct(sl, cur)},
        "risk_reward_conservative": _rr(basis, tc, sl),
    }

    # 2) ATR 방식 (현재가 기준)
    if atr and cur:
        atr_sl = round(cur - r["atr_stop_mult"] * atr, 2)
        atr_tg = round(cur + r["atr_target_mult"] * atr, 2)
        out["methods"]["atr"] = {
            "atr": round(atr, 2),
            "stop_loss": {"price": atr_sl, "from_current_pct": _pct(atr_sl, cur)},
            "target": {"price": atr_tg, "from_current_pct": _pct(atr_tg, cur)},
            "risk_reward": _rr(cur, atr_tg, atr_sl),
            "note": f"손절 {r['atr_stop_mult']}xATR / 목표 {r['atr_target_mult']}xATR",
        }

    # 3) 지지/저항 방식
    if levels and cur:
        sup = levels.get("nearest_support")
        res = levels.get("nearest_resistance")
        method = {}
        if sup:
            # 지지 살짝 아래(1%)를 손절 후보로
            s_price = round(sup * 0.99, 2)
            method["stop_loss"] = {"price": s_price, "from_current_pct": _pct(s_price, cur),
                                   "basis": f"가까운 지지 {round(sup,2)} 하단"}
        if res:
            method["target_first"] = {"price": round(res, 2), "from_current_pct": _pct(res, cur),
                                      "basis": "가까운 저항"}
        if sup and res:
            method["risk_reward"] = _rr(cur, res, round(sup * 0.99, 2))
        if method:
            out["methods"]["levels"] = method

    return out


def _rr(entry: float, target: float, stop: float):
    """손익비 = (목표-진입) / (진입-손절). 1.0이면 딴 만큼 잃을 수 있는 구조."""
    risk = entry - stop
    reward = target - entry
    if risk <= 0:
        return None
    return round(reward / risk, 2)


def compute_portfolio(holdings: list, enrich: dict | None = None,
                      rules: dict | None = None) -> list:
    """
    holdings: [{code,name,avg_price,quantity,current_price}, ...]
    enrich  : {code: {'atr':.., 'levels':{...}}}  (analyze.py 결과에서 주입)
    """
    enrich = enrich or {}
    res = []
    for h in holdings:
        e = enrich.get(h.get("code"), {})
        res.append(compute_for_holding(h, atr=e.get("atr"),
                                       levels=e.get("levels"), rules=rules))
    return res


if __name__ == "__main__":
    demo = {"code": "005930", "name": "삼성전자",
            "avg_price": 70000, "quantity": 10, "current_price": 74000}
    import json
    print(json.dumps(
        compute_for_holding(demo, atr=1500,
                            levels={"nearest_support": 71000, "nearest_resistance": 78000}),
        ensure_ascii=False, indent=2))
