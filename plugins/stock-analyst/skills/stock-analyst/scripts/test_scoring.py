"""scoring.py 최소 self-check. 실행: python3 scripts/test_scoring.py"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scoring as sc

BULLISH_TF = {
    "ma_alignment": "정배열(단기>장기)",
    "macd": {"state": "직전봉 골든크로스(히스토그램 음->양 전환)"},
    "rsi14": {"value": 75.0},
    "stochastic": {"k": 85.0, "d": 80.0},
    "bollinger": {"pct_b": 0.9},
    "range_252": {"position_pct": 90.0},
    "atr14": {"pct_of_price": 3.0},
}
BEARISH_TF = {
    "ma_alignment": "역배열(단기<장기)",
    "macd": {"state": "직전봉 데드크로스(히스토그램 양->음 전환)"},
    "rsi14": {"value": 25.0},
    "stochastic": {"k": 15.0, "d": 20.0},
    "bollinger": {"pct_b": 0.1},
    "range_252": {"position_pct": 10.0},
    "atr14": {"pct_of_price": 3.0},
}


def _result(tf_map):
    return {"timeframes": {tf: dict(v) for tf, v in tf_map.items()}}


def test_all_bullish_gives_positive_bias_and_up_gt_down():
    result = _result({tf: BULLISH_TF for tf in ("D", "W", "M", "Y")})
    for horizon in ("short", "mid"):
        f = sc.compute_forecast(result, horizon)
        assert f["bias_score"] > 50, f["bias_score"]
        assert f["scenarios"]["up"] > f["scenarios"]["down"], f["scenarios"]
        assert sum(f["scenarios"].values()) == 100


def test_all_bearish_gives_negative_bias_and_down_gt_up():
    result = _result({tf: BEARISH_TF for tf in ("D", "W", "M", "Y")})
    for horizon in ("short", "mid"):
        f = sc.compute_forecast(result, horizon)
        assert f["bias_score"] < -50, f["bias_score"]
        assert f["scenarios"]["down"] > f["scenarios"]["up"], f["scenarios"]
        assert sum(f["scenarios"].values()) == 100


def test_neutral_mixed_signals_near_zero_and_probabilities_sum_100():
    result = _result({"D": BULLISH_TF, "W": BEARISH_TF, "M": BULLISH_TF, "Y": BEARISH_TF})
    for horizon in ("short", "mid"):
        f = sc.compute_forecast(result, horizon)
        assert -100 <= f["bias_score"] <= 100
        assert sum(f["scenarios"].values()) == 100


def test_missing_timeframes_no_exception_and_notes_present():
    # 연봉/월봉 결측(상장 이력 짧은 종목 등) — 예외 없이 동작해야 함
    result = _result({"D": BULLISH_TF, "W": BULLISH_TF})
    for horizon in ("short", "mid"):
        f = sc.compute_forecast(result, horizon)
        assert sum(f["scenarios"].values()) == 100
        assert f["notes"], "결측 타임프레임이 있으면 notes에 남겨야 함"


def test_error_timeframe_dict_is_skipped_not_crashed():
    result = _result({"D": BULLISH_TF, "W": BULLISH_TF, "M": BULLISH_TF})
    result["timeframes"]["Y"] = {"timeframe": "Y", "bars": 3, "error": "데이터 부족 (최소 15봉 필요)"}
    for horizon in ("short", "mid"):
        f = sc.compute_forecast(result, horizon)
        assert sum(f["scenarios"].values()) == 100


def test_no_data_at_all_returns_neutral_low_confidence():
    result = {"timeframes": {}}
    f = sc.compute_forecast(result, "mid")
    assert f["bias_score"] == 0
    assert f["confidence"] == "low"
    assert sum(f["scenarios"].values()) == 100


def test_single_timeframe_confidence_penalized_vs_full_coverage():
    full = _result({tf: BULLISH_TF for tf in ("D", "W", "M", "Y")})
    single = _result({"D": BULLISH_TF})
    f_full = sc.compute_forecast(full, "short")
    f_single = sc.compute_forecast(single, "short")
    assert f_single["confidence_score"] < f_full["confidence_score"], (
        f_single["confidence_score"], f_full["confidence_score"])


def test_horizon_differs_when_daily_diverges_from_higher_frames():
    # 일봉만 약세, 나머지는 강세 -> 일봉 비중이 큰 short가 mid보다 점수가 낮아야 함
    result = _result({"D": BEARISH_TF, "W": BULLISH_TF, "M": BULLISH_TF, "Y": BULLISH_TF})
    f_short = sc.compute_forecast(result, "short")
    f_mid = sc.compute_forecast(result, "mid")
    assert f_short["bias_score"] < f_mid["bias_score"], (f_short["bias_score"], f_mid["bias_score"])


def test_deterministic_same_input_same_output():
    result = _result({tf: BULLISH_TF for tf in ("D", "W", "M", "Y")})
    a = sc.compute_forecast(result, "mid")
    b = sc.compute_forecast(result, "mid")
    assert a == b


def test_invalid_horizon_raises():
    try:
        sc.compute_forecast({"timeframes": {}}, "yearly")
    except ValueError:
        return
    raise AssertionError("잘못된 horizon이면 ValueError가 나야 함")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK ({len(tests)} tests)")
