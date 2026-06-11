"""
权益曲线绘图。
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


_COLORS = ["#2196F3", "#FF5722", "#4CAF50", "#9C27B0", "#FF9800"]


def plot_equity_curve(
    curves:      dict[str, pd.Series],   # {label: equity_series}
    split_date:  pd.Timestamp,
    title:       str,
    save_path:   str,
    initial_eq:  float = 10_000.0,
) -> None:
    """
    归一化权益曲线图（起点 = 1.0）。
    灰色虚线标注调参段 / 检验段分界。
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    for (label, curve), color in zip(curves.items(), _COLORS):
        # 归一化到起点 = 1.0
        norm = curve / curve.iloc[0]
        ax.plot(curve.index, norm.values, label=label,
                color=color, linewidth=1.0, alpha=0.85)

    y_min = ax.get_ylim()[0]
    y_max = ax.get_ylim()[1]
    ax.axvline(x=split_date, color="gray", linestyle="--",
               linewidth=1.5, label=f"调参 | 检验  ({split_date.date()})")
    ax.axvspan(ax.get_xlim()[0], mdates.date2num(split_date),
               alpha=0.04, color="blue")
    ax.axvspan(mdates.date2num(split_date), ax.get_xlim()[1],
               alpha=0.04, color="orange")

    ax.axhline(y=1.0, color="black", linewidth=0.5, linestyle=":")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel("日期", fontsize=10)
    ax.set_ylabel("归一化权益（起点=1.0）", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  图已保存 → {save_path}")
