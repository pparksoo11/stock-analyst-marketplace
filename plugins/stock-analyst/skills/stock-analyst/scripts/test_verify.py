"""verify.py 최소 self-check. 실행: python3 scripts/test_verify.py"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scoring as sc
import verify as vf

BULLISH_TF = {
    "ma_alignment": "정배열(단기>장기)",
    "macd": {"state": "직전봉 골든크로스(히스토그램 음->양 전환)"},
    "rsi14": {"value": 75.0},
    "stochastic": {"k": 85.0, "d": 80.0},
    "bollinger": {"pct_b": 0.9},
    "range_252": {"position_pct": 90.0},
    "atr14": {"pct_of_price": 3.0},
}


def _result():
    return {"code": "005930", "quote": {"price": 100000.0},
            "timeframes": {tf: dict(BULLISH_TF) for tf in ("D", "W", "M", "Y")}}


def test_clean_forecast_passes():
    result = _result()
    result["forecast"] = sc.compute_all_horizons(result)
    out = vf.verify(result)
    assert out["passed"], out["violations"]
    assert out["truth_table"]["current_price"] == 100000.0


def test_scenario_sum_not_100_is_caught():
    result = _result()
    result["forecast"] = sc.compute_all_horizons(result)
    result["forecast"]["short"]["scenarios"] = {"up": 50, "sideways": 30, "down": 30}  # 합 110
    out = vf.verify(result)
    assert not out["passed"]
    assert any("합이 100" in v for v in out["violations"])


def test_direction_contradiction_is_caught():
    result = _result()
    result["forecast"] = sc.compute_all_horizons(result)
    result["forecast"]["mid"]["bias_score"] = 60
    result["forecast"]["mid"]["scenarios"] = {"up": 10, "sideways": 20, "down": 70}  # 양수인데 하락 우세
    out = vf.verify(result)
    assert not out["passed"]
    assert any("하락 확률" in v for v in out["violations"])


def test_confidence_label_mismatch_is_caught():
    result = _result()
    result["forecast"] = sc.compute_all_horizons(result)
    result["forecast"]["short"]["confidence"] = "low"
    result["forecast"]["short"]["confidence_score"] = 0.9  # high여야 함
    out = vf.verify(result)
    assert not out["passed"]
    assert any("confidence 라벨" in v for v in out["violations"])


def test_determinism_break_is_caught():
    result = _result()
    result["forecast"] = sc.compute_all_horizons(result)
    result["forecast"]["mid"]["bias_score"] = 999  # 원본 재계산과 달라짐
    out = vf.verify(result)
    assert not out["passed"]
    assert any("결정론성" in v for v in out["violations"])


def test_targets_rr_mismatch_is_caught():
    result = _result()
    result["forecast"] = sc.compute_all_horizons(result)
    targets_out = {
        "current_price": 100000.0, "avg_price": None,
        "methods": {"atr": {"target": {"price": 120000.0}, "stop_loss": {"price": 90000.0},
                            "risk_reward": 999.0}},  # 실제론 (120000-100000)/(100000-90000)=2.0
    }
    out = vf.verify(result, targets_out=targets_out)
    assert not out["passed"]
    assert any("ATR 방식 손익비" in v for v in out["violations"])


def test_targets_rr_match_passes():
    result = _result()
    result["forecast"] = sc.compute_all_horizons(result)
    targets_out = {
        "current_price": 100000.0, "avg_price": None,
        "methods": {"atr": {"target": {"price": 120000.0}, "stop_loss": {"price": 90000.0},
                            "risk_reward": 2.0}},
    }
    out = vf.verify(result, targets_out=targets_out)
    assert out["passed"], out["violations"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK ({len(tests)} tests)")
