"""
indicators.py — 기술적 지표 계산 (pandas/numpy 순수 구현, TA-Lib 불필요)

입력: OHLCV DataFrame
    columns: ['date','open','high','low','close','volume']
    date 오름차순 정렬 (과거 -> 최신)

모든 함수는 계산만 한다. "사라/팔라"는 판단을 내리지 않는다.
summarize()가 붙이는 label은 '지표의 통상적 의미'일 뿐 매매 신호가 아니다.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ------------------------- 기본 이동평균 -------------------------
def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(window=n, min_periods=n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


# ------------------------- RSI (Wilder) -------------------------
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder 평활 (alpha = 1/n)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # loss가 0이면 RSI=100
    out = out.where(avg_loss != 0, 100.0)
    return out


# ------------------------- MACD -------------------------
def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


# ------------------------- Bollinger Bands -------------------------
def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    std = close.rolling(window=n, min_periods=n).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    pct_b = (close - lower) / (upper - lower)          # 0~1, 밴드 내 위치
    bandwidth = (upper - lower) / mid                    # 변동성 (밴드폭)
    return mid, upper, lower, pct_b, bandwidth


# ------------------------- Stochastic -------------------------
def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k: int = 14, d: int = 3):
    ll = low.rolling(window=k, min_periods=k).min()
    hh = high.rolling(window=k, min_periods=k).max()
    fast_k = 100 * (close - ll) / (hh - ll)
    slow_d = fast_k.rolling(window=d, min_periods=d).mean()
    return fast_k, slow_d


# ------------------------- ATR (Wilder) -------------------------
def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


# ------------------------- OBV -------------------------
def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


# ------------------------- 지지/저항 (스윙 고저 + 기간 고저) -------------------------
def swing_levels(df: pd.DataFrame, window: int = 5, lookback: int = 120):
    """
    최근 lookback봉 내에서 국소 고점(저항)/저점(지지) 후보를 추출.
    window: 좌우 window봉보다 높으면 스윙 고점(낮으면 저점)으로 판정.
    """
    sub = df.tail(lookback).reset_index(drop=True)
    highs, lows = [], []
    h, l = sub["high"].values, sub["low"].values
    for i in range(window, len(sub) - window):
        seg_h = h[i - window:i + window + 1]
        seg_l = l[i - window:i + window + 1]
        if h[i] == seg_h.max() and (seg_h.argmax() == window):
            highs.append(float(h[i]))
        if l[i] == seg_l.min() and (seg_l.argmin() == window):
            lows.append(float(l[i]))
    return sorted(set(highs)), sorted(set(lows))


def nearest_levels(price: float, resistances, supports):
    """현재가 기준 가장 가까운 위 저항 / 아래 지지."""
    above = sorted([r for r in resistances if r > price])
    below = sorted([s for s in supports if s < price], reverse=True)
    return {
        "nearest_resistance": above[0] if above else None,
        "nearest_support": below[0] if below else None,
    }


# ------------------------- 종합 요약 -------------------------
def _round(x, nd=2):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), nd)


def summarize(df: pd.DataFrame, timeframe: str = "D") -> dict:
    """
    한 타임프레임(일/주/월/년)에 대한 지표 스냅샷을 dict로 반환.
    label은 '지표의 통상적 의미'일 뿐, 매매 신호가 아님.
    """
    df = df.copy().reset_index(drop=True)
    if len(df) < 15:
        return {"timeframe": timeframe, "bars": len(df),
                "error": "데이터 부족 (최소 15봉 필요)"}

    close = df["close"]
    high, low, vol = df["high"], df["low"], df["volume"]
    last = float(close.iloc[-1])

    # 이동평균
    mas = {}
    for n in (5, 20, 60, 120, 200):
        if len(df) >= n:
            mas[f"ma{n}"] = _round(sma(close, n).iloc[-1])
        else:
            mas[f"ma{n}"] = None

    # MA 배열 상태
    ma_order_labels = []
    ordered = [mas.get("ma5"), mas.get("ma20"), mas.get("ma60"), mas.get("ma120")]
    ordered_valid = [m for m in ordered if m is not None]
    if len(ordered_valid) >= 3:
        if all(ordered_valid[i] > ordered_valid[i + 1] for i in range(len(ordered_valid) - 1)):
            ma_order_labels.append("정배열(단기>장기)")
        elif all(ordered_valid[i] < ordered_valid[i + 1] for i in range(len(ordered_valid) - 1)):
            ma_order_labels.append("역배열(단기<장기)")
        else:
            ma_order_labels.append("혼조")

    # RSI
    rsi_val = _round(rsi(close, 14).iloc[-1])
    if rsi_val is None:
        rsi_label = None
    elif rsi_val >= 70:
        rsi_label = "과매수권(>=70)"
    elif rsi_val <= 30:
        rsi_label = "과매도권(<=30)"
    else:
        rsi_label = "중립대(30~70)"

    # MACD
    macd_line, signal_line, hist = macd(close)
    macd_v = _round(macd_line.iloc[-1], 3)
    sig_v = _round(signal_line.iloc[-1], 3)
    hist_v = _round(hist.iloc[-1], 3)
    macd_cross = None
    if len(hist.dropna()) >= 2:
        prev, cur = hist.iloc[-2], hist.iloc[-1]
        if prev <= 0 < cur:
            macd_cross = "직전봉 골든크로스(히스토그램 음->양 전환)"
        elif prev >= 0 > cur:
            macd_cross = "직전봉 데드크로스(히스토그램 양->음 전환)"
        else:
            macd_cross = "양(+)" if cur > 0 else "음(-)"

    # Bollinger
    mid, upper, lower, pct_b, bw = bollinger(close)
    pctb_v = _round(pct_b.iloc[-1], 3)
    if pctb_v is None:
        bb_label = None
    elif pctb_v >= 1.0:
        bb_label = "상단 돌파(%b>=1)"
    elif pctb_v <= 0.0:
        bb_label = "하단 이탈(%b<=0)"
    elif pctb_v >= 0.8:
        bb_label = "상단 근접"
    elif pctb_v <= 0.2:
        bb_label = "하단 근접"
    else:
        bb_label = "밴드 중앙권"

    # Stochastic
    fast_k, slow_d = stochastic(high, low, close)
    k_v, d_v = _round(fast_k.iloc[-1]), _round(slow_d.iloc[-1])

    # ATR (변동성, 손절폭 계산에 사용)
    atr_v = _round(atr(high, low, close, 14).iloc[-1])
    atr_pct = _round((atr_v / last) * 100, 2) if atr_v else None

    # 거래량
    vol_v = float(vol.iloc[-1])
    vol_ma20 = sma(vol, 20).iloc[-1] if len(df) >= 20 else np.nan
    vol_ratio = _round(vol_v / vol_ma20, 2) if vol_ma20 and vol_ma20 > 0 else None

    # 기간 고저 (52주 성격 - 타임프레임에 따라 의미 다름)
    hi_252 = _round(high.tail(252).max()) if len(df) >= 60 else _round(high.max())
    lo_252 = _round(low.tail(252).min()) if len(df) >= 60 else _round(low.min())
    pos_in_range = None
    if hi_252 and lo_252 and hi_252 > lo_252:
        pos_in_range = _round((last - lo_252) / (hi_252 - lo_252) * 100, 1)

    # 지지/저항
    res, sup = swing_levels(df)
    near = nearest_levels(last, res, sup)

    # 가격 vs 이동평균
    price_vs_ma = {}
    for n in (20, 60, 120, 200):
        m = mas.get(f"ma{n}")
        if m:
            price_vs_ma[f"vs_ma{n}"] = f"{'위' if last >= m else '아래'} ({_round((last/m-1)*100,1)}%)"

    return {
        "timeframe": timeframe,
        "bars": len(df),
        "last_date": str(df["date"].iloc[-1]),
        "last_close": _round(last),
        "moving_averages": mas,
        "ma_alignment": ma_order_labels[0] if ma_order_labels else None,
        "price_vs_ma": price_vs_ma,
        "rsi14": {"value": rsi_val, "label": rsi_label},
        "macd": {"macd": macd_v, "signal": sig_v, "hist": hist_v, "state": macd_cross},
        "bollinger": {"pct_b": pctb_v, "bandwidth": _round(bw.iloc[-1], 4),
                      "upper": _round(upper.iloc[-1]), "mid": _round(mid.iloc[-1]),
                      "lower": _round(lower.iloc[-1]), "label": bb_label},
        "stochastic": {"k": k_v, "d": d_v},
        "atr14": {"value": atr_v, "pct_of_price": atr_pct},
        "volume": {"last": _round(vol_v), "vs_ma20_ratio": vol_ratio},
        "range_252": {"high": hi_252, "low": lo_252, "position_pct": pos_in_range},
        "levels": {
            "nearest_resistance": _round(near["nearest_resistance"]) if near["nearest_resistance"] else None,
            "nearest_support": _round(near["nearest_support"]) if near["nearest_support"] else None,
            "resistances": [_round(r) for r in res[-5:]],
            "supports": [_round(s) for s in sup[-5:]],
        },
    }
