"""
verify.py — 서술(예측 포함) 출력 전 결정론적 정합성 검사.

analyze_ticker() 결과(quote/timeframes/forecast 포함)와, 선택적으로 targets.py 결과를
받아 산술·구조적 모순을 검사한다. 이 파일은 서술 "텍스트"는 보지 않는다(자연어 파싱은
오탐이 많아 여기서 하지 않음). 대신 검증 에이전트(LLM)가 초안 서술과 대조할 truth_table을
만들어 반환한다 — 숫자 자체의 진위는 여기서 결정론적으로 보증하고, "서술이 그 숫자를
정확히 인용했는지·논리적으로 과신하지 않는지"는 LLM 검증 에이전트가 담당한다(역할 분리).

검사 항목:
  1) 시나리오 확률 합 = 100
  2) bias_score 부호와 시나리오(up/down) 방향 모순 여부
  3) confidence 라벨이 confidence_score 구간과 일치하는지
  4) 같은 입력으로 forecast를 재계산해도 동일한지(결정론성)
  5) (targets 결과가 있으면) risk_reward 재계산이 보고값과 일치하는지
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scoring as sc

# scoring._confidence()의 라벨 임계값과 반드시 같이 맞춰야 함. 독립 재검증이 목적이라
# scoring 내부 구현을 그대로 불러쓰지 않고 계약값을 여기 별도로 박아둔다.
CONF_HIGH = 0.65
CONF_MID = 0.40
# bias_score가 이 값 이하로 작으면 방향-확률 불일치를 반올림 노이즈로 보고 넘어간다.
DIRECTION_MATERIALITY = 15


def _check_scenario_sum(scenarios: dict) -> list[str]:
    total = sum(scenarios.values())
    if total != 100:
        return [f"시나리오 확률 합이 100이 아님: {total} ({scenarios})"]
    return []


def _check_direction_consistency(bias_score: int, scenarios: dict) -> list[str]:
    up, down = scenarios.get("up", 0), scenarios.get("down", 0)
    issues = []
    if bias_score > DIRECTION_MATERIALITY and down > up:
        issues.append(f"bias_score={bias_score}(양)인데 하락 확률({down}%)이 상승 확률({up}%)보다 높음")
    if bias_score < -DIRECTION_MATERIALITY and up > down:
        issues.append(f"bias_score={bias_score}(음)인데 상승 확률({up}%)이 하락 확률({down}%)보다 높음")
    return issues


def _check_confidence_label(confidence: str, confidence_score: float) -> list[str]:
    expected = "high" if confidence_score >= CONF_HIGH else ("mid" if confidence_score >= CONF_MID else "low")
    if confidence != expected:
        return [f"confidence 라벨 '{confidence}'이 confidence_score {confidence_score}와 불일치(기대: {expected})"]
    return []


def _check_determinism(result: dict, forecast_by_horizon: dict) -> list[str]:
    issues = []
    for horizon, forecast in forecast_by_horizon.items():
        if horizon not in sc.HORIZON_WEIGHTS:
            continue
        recomputed = sc.compute_forecast(result, horizon)
        if (recomputed.get("bias_score") != forecast.get("bias_score")
                or recomputed.get("scenarios") != forecast.get("scenarios")):
            issues.append(f"[{horizon}] forecast 재계산 결과가 원본과 다름(결정론성 위반)")
    return issues


def _recompute_rr(entry: float, target: float, stop: float):
    risk = entry - stop
    if risk is None or risk <= 0:
        return None
    return round((target - entry) / risk, 2)


def _check_targets_rr(targets_out: dict) -> list[str]:
    issues = []
    cur = targets_out.get("current_price")
    avg = targets_out.get("avg_price")
    methods = targets_out.get("methods", {})

    pct = methods.get("percent")
    if pct and avg:
        expected = _recompute_rr(avg, pct["target_conservative"]["price"], pct["stop_loss"]["price"])
        reported = pct.get("risk_reward_conservative")
        if expected is not None and reported is not None and abs(expected - reported) > 0.02:
            issues.append(f"percent 방식 손익비 재계산({expected}) != 보고값({reported})")

    atr = methods.get("atr")
    if atr and cur:
        expected = _recompute_rr(cur, atr["target"]["price"], atr["stop_loss"]["price"])
        reported = atr.get("risk_reward")
        if expected is not None and reported is not None and abs(expected - reported) > 0.02:
            issues.append(f"ATR 방식 손익비 재계산({expected}) != 보고값({reported})")

    lv = methods.get("levels")
    if lv and cur and lv.get("stop_loss") and lv.get("target_first"):
        expected = _recompute_rr(cur, lv["target_first"]["price"], lv["stop_loss"]["price"])
        reported = lv.get("risk_reward")
        if expected is not None and reported is not None and abs(expected - reported) > 0.02:
            issues.append(f"지지/저항 방식 손익비 재계산({expected}) != 보고값({reported})")

    return issues


def _build_truth_table(result: dict, forecast_by_horizon: dict, targets_out: dict | None) -> dict:
    quote = result.get("quote", {})
    tf_summary = {}
    for tf, summ in (result.get("timeframes") or {}).items():
        if not summ or summ.get("error"):
            tf_summary[tf] = {"error": (summ or {}).get("error", "없음")}
            continue
        tf_summary[tf] = {
            "last_close": summ.get("last_close"),
            "ma_alignment": summ.get("ma_alignment"),
            "rsi14": (summ.get("rsi14") or {}).get("value"),
            "macd_state": (summ.get("macd") or {}).get("state"),
            "bollinger_pct_b": (summ.get("bollinger") or {}).get("pct_b"),
            "bollinger_label": (summ.get("bollinger") or {}).get("label"),
            "stochastic_k": (summ.get("stochastic") or {}).get("k"),
            "stochastic_d": (summ.get("stochastic") or {}).get("d"),
            "atr_pct_of_price": (summ.get("atr14") or {}).get("pct_of_price"),
            "volume_vs_ma20_ratio": (summ.get("volume") or {}).get("vs_ma20_ratio"),
            "range_position_pct": (summ.get("range_252") or {}).get("position_pct"),
            "nearest_resistance": (summ.get("levels") or {}).get("nearest_resistance"),
            "nearest_support": (summ.get("levels") or {}).get("nearest_support"),
        }
    truth = {
        "code": result.get("code"),
        "current_price": quote.get("price"),
        "change_pct": quote.get("change_pct"),
        "timeframes": tf_summary,
        "forecast": {
            h: {"bias_score": f["bias_score"], "confidence": f["confidence"], "scenarios": f["scenarios"]}
            for h, f in forecast_by_horizon.items()
        },
    }
    if targets_out:
        truth["targets"] = targets_out
    return truth


def verify(result: dict, forecast_by_horizon: dict | None = None,
           targets_out: dict | None = None) -> dict:
    """result: analyze_ticker() 출력(quote/timeframes/forecast 포함).
    forecast_by_horizon: {"short":..., "mid":...}. 없으면 result["forecast"]를 쓴다.
    targets_out: targets.compute_for_holding() 출력(선택, 있으면 R:R 재검산)."""
    forecast_by_horizon = forecast_by_horizon or result.get("forecast") or {}

    violations = []
    for horizon, forecast in forecast_by_horizon.items():
        violations += [f"[{horizon}] {m}" for m in _check_scenario_sum(forecast.get("scenarios", {}))]
        violations += [f"[{horizon}] {m}" for m in
                       _check_direction_consistency(forecast.get("bias_score", 0), forecast.get("scenarios", {}))]
        violations += [f"[{horizon}] {m}" for m in
                       _check_confidence_label(forecast.get("confidence"), forecast.get("confidence_score", 0.0))]

    if forecast_by_horizon:
        violations += _check_determinism(result, forecast_by_horizon)

    if targets_out:
        violations += _check_targets_rr(targets_out)

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "truth_table": _build_truth_table(result, forecast_by_horizon, targets_out),
    }


if __name__ == "__main__":
    import json
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    out = verify(data)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out["passed"] else 1)
