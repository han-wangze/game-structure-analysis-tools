# -*- coding: utf-8 -*-
"""生成 README 用的集中度走势图。

只画一份导出、一个口径：收入榜导出里的品类，只看收入。
不与其他数据集（下载榜、题材）并列——排序轴不同，放在一起比不出东西。

数据来源不是原始榜单，而是 market_structure_analysis.py 的产出表——
图上每个点都能在「五年趋势」sheet 里查到，不重新计算任何指标。

用法：
  1) 先用 market_structure_analysis.py 跑一遍，得到产出 xlsx；
  2) 把下面的路径指向这份产出；
  3) python make_readme_figures.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------- Config
ANALYSIS_XLSX = Path("data/市场结构分析_xxx.xlsx")   # market_structure_analysis.py 的产出
OUT_PNG = Path(__file__).parent / "docs" / "figures" / "revenue_cr5_trend.png"

SHEET = "五年趋势"
# -----------------------------------------------------------------------


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    df = pd.read_excel(ANALYSIS_XLSX, sheet_name=SHEET)
    cr5col = [c for c in df.columns if c.startswith("CR5_") and "样本" not in c][0]

    fig, ax = plt.subplots(figsize=(8.0, 4.6), dpi=165)
    for dim, g in df.groupby("维度", sort=False):
        g = g.sort_values("年份")
        ax.plot(g["年份"], g[cr5col], marker="o", ms=5, lw=1.8, label=dim)

    ax.set_title("收入榜导出三个品类的头部集中度走势（CR5，2021–2025）",
                 fontsize=11.5, pad=12)
    ax.set_ylabel("CR5（Top5 收入占样本总收入，%）", fontsize=9.5)
    ax.set_xlabel("年份", fontsize=9.5)
    ax.set_xticks(sorted(df["年份"].unique()))
    ax.grid(alpha=.20, lw=.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ax.legend(frameon=False, fontsize=9, loc="lower right")

    fig.text(.005, -.04,
             "口径：CR5 = Top5 收入占该样本总收入的比例；样本为按收入排序的榜单导出，"
             "已过滤非游戏产品。\n数据：美国市场 2021–2025 逐年榜单导出（Sensor Tower）。",
             fontsize=7.6, color="#888888", linespacing=1.5)

    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, bbox_inches="tight")
    print(f"saved -> {OUT_PNG}")


if __name__ == "__main__":
    main()
