"""
scoring.py — 결정론적 방향성 점수 / 시나리오 확률 산출기

역할 분리 원칙(기존 indicators.py/targets.py와 동일): 이 파일은 "숫자만" 계산한다.
서술·해석은 Claude가 한다. 외부 API 호출, 난수, 시간 의존성 없음 — 같은 입력이면
항상 같은 출력(재현 가능성 = 검증 가능성).

방법론 요약 (자세한 근거는 reference/scoring_method.md):
  1) 타임프레임(D/W/M/Y)별로 6개 지표 신호를 -1~+1로 정규화해 가중합 → TF별 signal.
  2) 지평(horizon: short=1~4주 / mid=1~3개월)에 따라 TF 가중치를 다르게 적용해 종합.
  3) RSI/스토캐스틱/볼린저%b는 "과매수=하락신호"로 쓰지 않는다. 값이 높을수록
     상방 모멘텀이 강하다는 신호로만 쓴다 — reading_indicators.md의 경고
     ("강한 추세에서는 RSI가 오래 과매수에 머문다")를 스코어링에도 동일 적용.
  4) 신뢰도(confidence) = 타임프레임 간 신호 일치도 + 데이터 충분성 + 변동성(ATR%).
  5) 시나리오 확률은 방향성 점수를 신뢰도로 감쇠(damping)한 뒤 중립분포(33/34/33)에서
     이동시켜 산출 — 신뢰도가 낮으면 점수가 커도 확률은 중립에 가깝게 유지된다
     (과신 방지).

주의: 이 점수는 과거 데이터 백테스트로 보정되지 않았다(v1). 통계적으로 검증된
"승률"이 아니라 지표 종합의 정량적 요약이며, 확정된 미래를 보장하지 않는다.
"""
from __future__ import annotations

SUB_WEIGHTS = {
    "trend": 0.30,          # ma_alignment
    "macd": 0.25,           # macd.state / hist
    "rsi": 0.15,
    "stochastic": 0.10,
    "bollinger": 0.10,      # bollinger.pct_b
    "range_position": 0.10, # range_252.position_pct
}

HORIZON_WEIGHTS = {
    # 단기(1~4주): 일봉 비중 최대, 연봉은 참고 수준
    "short": {"D": 0.40, "W": 0.30, "M": 0.20, "Y": 0.10},
    # 중기(1~3개월): 월봉 비중 최대, 큰 그림(연봉)도 상당 반영
    "mid":   {"M": 0.35, "W": 0.30, "D": 0.20, "Y": 0.15},
}

COMP_LABEL = {
    "trend": "이동평균 배열",
    "macd": "MACD",
    "rsi": "RSI",
    "stochastic": "스토캐스틱",
    "bollinger": "볼린저 %b",
    "range_position": "기간 내 위치",
}
TF_LABEL = {"D": "일봉", "W": "주봉", "M": "월봉", "Y": "연봉"}


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _tf_components(summ: dict) -> dict:
    """summarize() 출력 하나(단일 타임프레임)에서 -1~+1 신호 컴포넌트를 뽑는다.
    데이터가 없는(None) 지표는 딕셔너리에서 아예 생략한다 — 0(중립)과 결측은 다르다."""
    comps = {}

    ma = summ.get("ma_alignment")
    if ma == "정배열(단기>장기)":
        comps["trend"] = 1.0
    elif ma == "역배열(단기<장기)":
        comps["trend"] = -1.0
    elif ma == "혼조":
        comps["trend"] = 0.0
    # None → 유효 MA 3개 미만, 생략

    state = (summ.get("macd") or {}).get("state")
    if state == "직전봉 골든크로스(히스토그램 음->양 전환)":
        comps["macd"] = 1.0
    elif state == "직전봉 데드크로스(히스토그램 양->음 전환)":
        comps["macd"] = -1.0
    elif state == "양(+)":
        comps["macd"] = 0.5
    elif state == "음(-)":
        comps["macd"] = -0.5

    rsi_v = (summ.get("rsi14") or {}).get("value")
    if rsi_v is not None:
        # 50=중립. 과매수(고RSI)를 하락신호로 쓰지 않고 상방 모멘텀 신호로만 사용.
        comps["rsi"] = _clip((rsi_v - 50) / 50, -1, 1)

    k = (summ.get("stochastic") or {}).get("k")
    d = (summ.get("stochastic") or {}).get("d")
    vals = [v for v in (k, d) if v is not None]
    if vals:
        avg = sum(vals) / len(vals)
        comps["stochastic"] = _clip((avg - 50) / 50, -1, 1)

    pb = (summ.get("bollinger") or {}).get("pct_b")
    if pb is not None:
        comps["bollinger"] = _clip((pb - 0.5) * 2, -1, 1)

    pos = (summ.get("range_252") or {}).get("position_pct")
    if pos is not None:
        comps["range_position"] = _clip((pos - 50) / 50, -1, 1)

    return comps


def _weighted_signal(comps: dict) -> float | None:
    total_w = sum(SUB_WEIGHTS[c] for c in comps)
    if total_w <= 0:
        return None
    return sum(comps[c] * SUB_WEIGHTS[c] for c in comps) / total_w


def _confidence(per_tf: dict, norm_weights: dict, total_w: float, tfs_raw: dict) -> tuple[str, float]:
    """신뢰도 = 이 horizon의 가중치 기준 타임프레임 간 일치도 + 가중 데이터 커버리지
    + 변동성(ATR%) 종합. agreement/availability는 horizon마다 다르게 나온다 — 예를 들어
    단기는 일봉 비중이 커서 일봉이 상위 타임프레임과 어긋나면 더 크게 감점되고,
    중기는 월봉 비중이 커서 월봉 기준 일치도가 더 크게 반영된다."""
    if not per_tf or total_w <= 0:
        return "low", 0.0

    if len(per_tf) < 2:
        # 타임프레임 1개로는 교차검증(다른 프레임과 일치하는지)이 불가능하므로
        # 분산=0(=완전 일치로 오해)이 되지 않게 고정 페널티를 준다.
        agreement = 0.5
    else:
        w_mean = sum(per_tf[tf]["signal"] * norm_weights[tf] for tf in norm_weights)
        w_var = sum(norm_weights[tf] * (per_tf[tf]["signal"] - w_mean) ** 2 for tf in norm_weights)
        spread = w_var ** 0.5
        agreement = _clip(1 - spread, 0, 1)

    # 이 horizon이 원래 요구하는 가중치 중 실제로 데이터가 있었던 비율(=total_w, 정규화 전 합)
    availability = _clip(total_w, 0, 1)

    # 변동성은 항상 일봉 ATR% 기준(타임프레임마다 ATR%의 절대 스케일이 달라 horizon에 맞춰
    # 바꾸면 "월봉이라 변동성 커 보임" 같은 착시가 생김 — 일봉을 공통 척도로 고정).
    atr_pct = None
    for tf in ("D", "W", "M", "Y"):
        v = (tfs_raw.get(tf) or {}).get("atr14", {}).get("pct_of_price")
        if v is not None:
            atr_pct = v
            break
    # ATR%가 낮을수록(변동성 작을수록) 신뢰도에 유리. 5%를 중간 기준점으로 정규화.
    vol_factor = 0.5 if atr_pct is None else _clip(1 - (atr_pct - 5) / 15, 0, 1)

    score = 0.45 * agreement + 0.30 * availability + 0.25 * vol_factor
    if score >= 0.65:
        label = "high"
    elif score >= 0.40:
        label = "mid"
    else:
        label = "low"
    return label, score


def _scenarios(bias_score: int, conf_score: float) -> dict:
    """방향성 점수를 신뢰도로 감쇠시켜 중립분포(33/34/33)에서 이동. 합은 항상 100."""
    strength = _clip(bias_score / 100.0, -1, 1)
    damped = strength * _clip(conf_score, 0.15, 1.0)
    shift = damped * 33.0

    vals = {
        "up": max(33.34 + shift, 1.0),
        "sideways": max(33.33, 1.0),
        "down": max(33.33 - shift, 1.0),
    }
    total = sum(vals.values())
    pct = {k: v / total * 100 for k, v in vals.items()}
    rounded = {k: int(round(v)) for k, v in pct.items()}
    diff = 100 - sum(rounded.values())
    if diff:
        biggest = max(rounded, key=lambda k: rounded[k])
        rounded[biggest] += diff
    return rounded


def compute_forecast(result: dict, horizon: str = "mid") -> dict:
    """analyze_ticker() 결과(result)를 받아 해당 horizon의 예측 요약을 반환.

    horizon: "short"(1~4주) | "mid"(1~3개월)
    """
    if horizon not in HORIZON_WEIGHTS:
        raise ValueError(f"horizon은 {list(HORIZON_WEIGHTS)} 중 하나여야 함: {horizon}")

    tfs_raw = result.get("timeframes") or {}
    per_tf = {}
    for tf in ("D", "W", "M", "Y"):
        summ = tfs_raw.get(tf)
        if not summ or summ.get("error"):
            continue
        comps = _tf_components(summ)
        if not comps:
            continue
        sig = _weighted_signal(comps)
        if sig is None:
            continue
        per_tf[tf] = {"signal": sig, "components": comps}

    notes = []
    base_weights = HORIZON_WEIGHTS[horizon]
    avail = {tf: w for tf, w in base_weights.items() if tf in per_tf}
    missing = [tf for tf in base_weights if tf not in per_tf]
    if missing:
        notes.append(f"{'/'.join(TF_LABEL[m] for m in missing)} 데이터 부족/결측으로 나머지 타임프레임에 가중 재분배")

    total_w = sum(avail.values())
    if total_w <= 0:
        return {
            "horizon": horizon, "bias_score": 0, "confidence": "low",
            "scenarios": {"up": 33, "sideways": 34, "down": 33},
            "drivers": [], "notes": ["사용 가능한 타임프레임 데이터 없음"],
        }
    norm_weights = {tf: w / total_w for tf, w in avail.items()}

    overall = sum(per_tf[tf]["signal"] * norm_weights[tf] for tf in norm_weights)
    bias_score = int(round(_clip(overall, -1, 1) * 100))

    confidence, conf_score = _confidence(per_tf, norm_weights, total_w, tfs_raw)
    scenarios = _scenarios(bias_score, conf_score)

    drivers = []
    for tf, tf_w in norm_weights.items():
        comps = per_tf[tf]["components"]
        sub_total = sum(SUB_WEIGHTS[c] for c in comps)
        for comp_name, comp_val in comps.items():
            contribution = comp_val * (SUB_WEIGHTS[comp_name] / sub_total) * tf_w
            drivers.append({
                "tf": tf, "tf_label": TF_LABEL[tf],
                "signal": comp_name, "signal_label": COMP_LABEL[comp_name],
                "value": round(comp_val, 2),
                "contribution": round(contribution, 3),
            })
    drivers.sort(key=lambda d: -abs(d["contribution"]))

    return {
        "horizon": horizon,
        "bias_score": bias_score,
        "confidence": confidence,
        "confidence_score": round(conf_score, 3),
        "scenarios": scenarios,
        "drivers": drivers[:6],
        "notes": notes,
    }


def compute_all_horizons(result: dict) -> dict:
    return {h: compute_forecast(result, h) for h in HORIZON_WEIGHTS}


if __name__ == "__main__":
    import json
    demo = {
        "timeframes": {
            "D": {"ma_alignment": "혼조",
                  "macd": {"state": "음(-)"}, "rsi14": {"value": 38.68},
                  "stochastic": {"k": 6.8, "d": 14.94},
                  "bollinger": {"pct_b": 0.092},
                  "range_252": {"position_pct": 59.4},
                  "atr14": {"pct_of_price": 10.22}},
            "W": {"ma_alignment": "정배열(단기>장기)",
                  "macd": {"state": "음(-)"}, "rsi14": {"value": 51.19},
                  "stochastic": {"k": 21.36, "d": 35.01},
                  "bollinger": {"pct_b": 0.443},
                  "range_252": {"position_pct": 60.9},
                  "atr14": {"pct_of_price": 13.98}},
            "M": {"ma_alignment": "정배열(단기>장기)",
                  "macd": {"state": "양(+)"}, "rsi14": {"value": 64.4},
                  "stochastic": {"k": 60.1, "d": 81.75},
                  "bollinger": {"pct_b": 0.83},
                  "range_252": {"position_pct": 63.2},
                  "atr14": {"pct_of_price": 15.21}},
            "Y": {"ma_alignment": None,
                  "macd": {"state": "양(+)"}, "rsi14": {"value": 83.39},
                  "stochastic": {"k": 64.11, "d": 70.17},
                  "bollinger": {"pct_b": 1.424},
                  "range_252": {"position_pct": 66.1},
                  "atr14": {"pct_of_price": 14.66}},
        }
    }
    print(json.dumps(compute_all_horizons(demo), ensure_ascii=False, indent=2))
