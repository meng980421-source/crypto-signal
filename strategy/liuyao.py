"""
梅花易数时间起卦 —— 六爻方向过滤

公式（均以 1 起数，余 0 取最大值）：
  上卦 = (年支 + 农历月 + 农历日) % 8   (0→8)
  下卦 = (年支 + 农历月 + 农历日 + 时支) % 8  (0→8)
  动爻 = (年支 + 农历月 + 农历日 + 时支) % 6  (0→6)

先天八卦序：乾1 兑2 离3 震4 巽5 坎6 艮7 坤8
五行：乾兑=金  震巽=木  坤艮=土  离=火  坎=水
生克：木→火→土→金→水→木（生），木→土→水→火→金→木（克）

动爻1-3：下卦=用，上卦=体
动爻4-6：上卦=用，下卦=体
用生体/用比和 → 偏多；用克体 → 偏空；其余 → 观望
"""
from __future__ import annotations

import pandas as pd
from functools import lru_cache

try:
    from lunar_python import Solar
    _LUNAR_OK = True
except ImportError:
    _LUNAR_OK = False

# 先天八卦五行
_WX = {1: "金", 2: "金", 3: "火", 4: "木", 5: "木", 6: "水", 7: "土", 8: "土"}
_GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_OVERCOMES  = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def _hour_zhi(hour: int) -> int:
    """北京时小时 → 时支数（子=1 … 亥=12）。"""
    return 1 if hour == 23 else hour // 2 + 1


@lru_cache(maxsize=4096)
def _bias_cached(year: int, month: int, day: int, hour: int) -> str:
    """
    年月日时均为北京时历法数值（solar year/month/day + BJ hour）。
    返回 'bull' | 'bear' | 'neutral'
    """
    if not _LUNAR_OK:
        return "neutral"

    solar = Solar.fromYmd(year, month, day)
    lunar = solar.getLunar()

    year_zhi  = lunar.getYearZhiIndex() + 1        # 0-based → 1-based (子=1)
    lm        = abs(lunar.getMonth())               # 闰月为负，取绝对值
    ld        = lunar.getDay()
    hour_zhi  = _hour_zhi(hour)

    shang = (year_zhi + lm + ld) % 8 or 8
    xia   = (year_zhi + lm + ld + hour_zhi) % 8 or 8
    dong  = (year_zhi + lm + ld + hour_zhi) % 6 or 6

    ti, yong = (shang, xia) if dong <= 3 else (xia, shang)

    ti_wx   = _WX[ti]
    yong_wx = _WX[yong]

    if yong_wx == ti_wx or _GENERATES[yong_wx] == ti_wx:
        return "bull"
    if _OVERCOMES[yong_wx] == ti_wx:
        return "bear"
    return "neutral"


def compute_liuyao_series(df: pd.DataFrame) -> pd.Series:
    """
    预计算 df 中每根 K 线对应的六爻偏向。
    df.index 需为 UTC timezone-aware DatetimeIndex。
    """
    if not _LUNAR_OK:
        return pd.Series("neutral", index=df.index, name="liuyao")

    bj = df.index.tz_convert("Asia/Shanghai")
    biases = [
        _bias_cached(int(t.year), int(t.month), int(t.day), int(t.hour))
        for t in bj
    ]
    return pd.Series(biases, index=df.index, name="liuyao")
