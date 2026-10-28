# -*- coding: utf-8 -*-
"""生成 README 用的对比图。

数据来源不是原始榜单，而是 market_structure_analysis.py 的产出表——
所以图上的每个点都能在「五年趋势」sheet 里查到，不重新计算任何指标。

用法：
  1) 先用 market_structure_analysis.py 分别跑收入榜导出与下载榜导出，各得一份 xlsx；
  2) 把下面两个路径指向这两份产出；
  3) python make_readme_figures.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------- Config
REVENUE_XLSX = Path("data/市场结构分析_sub_genre_revenue_xxx.xlsx")    # 收入榜导出的产出
DOWNLOAD_XLSX = Path("data/市场结构分析_sub_genre_downloads_xxx.xlsx")  # 下载榜导出的产出
OUT_PNG = Path(__file__).parent / "docs" / "figures" / "concentration_vs_churn.png"

SHEET = "五年趋势"
CR5_HIGH = 75.0     # 与 market_structure_analysis.Config.JUDGE_CR5_HIGH 一致
CHURN_MIN = 15.0    # 与 market_structure_analysis.Config.JUDGE_CHURN_MIN 一致
# -----------------------------------------------------------------------


def load(path: Path) -> pd.DataFrame:
    """取「五年趋势」里的排序轴 CR5 与头部换血率，只保留画图需要的列。"""
    df = pd.read_excel(path, sheet_name=SHEET)
    cr5col = [c for c in df.columns if c.startswith("CR5_") and "样本" not in c][0]
    out = df[["维度", "年份", cr5col, "头部换血率%"]].rename(columns={cr5col: "CR5"})
    return out.sort_values(["维度", "年份"])


def band(ax, df: pd.DataFrame, col: str, color: str, label: str) -> None:
    """组内区间带：每个年份取该组各维度的 min–max。"""
    g = df.dropna(subset=[col]).groupby("年份")[col].agg(["min", "max"])
    ax.fill_between(g.index, g["min"], g["max"], color=color, alpha=.30, lw=0)
    ax.plot(g.index, g["max"], color=color, lw=1.5, label=label)
    ax.plot(g.index, g["min"], color=color, lw=1.5)


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    groups = [
        ("收入榜样本（3 个品类）", REVENUE_XLSX, "#C0504D"),
        ("下载榜样本（3 个品类）", DOWNLOAD_XLSX, "#4F81BD"),
    ]

    fig, (ax_cr5, ax_churn) = plt.subplots(1, 2, figsize=(11.2, 4.3), dpi=165)

    for name, path, color in groups:
        df = load(path)
        band(ax_cr5, df, "CR5", color, name)
        band(ax_churn, df, "头部换血率%", color, name)

    # 判定层参考线：标在坐标区外侧，避免压住区间带
    for ax, y, txt, lim in ((ax_cr5, CR5_HIGH, f"{CR5_HIGH:.0f}%", (10, 96)),
                            (ax_churn, CHURN_MIN, f"{CHURN_MIN:.0f}%", (8, 72))):
        ax.axhline(y, ls="--", lw=1, color="#8C8C8C", zorder=0)
        ax.text(1.008, y, txt, transform=ax.get_yaxis_transform(),
                fontsize=8, color="#8C8C8C", va="center")
        ax.set_ylim(*lim)
        ax.set_xlabel("年份", fontsize=9.5)
        ax.set_xticks(range(2021, 2026))
        ax.grid(alpha=.20, lw=.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

    ax_cr5.set_title("头部集中度 CR5：两组五年从未交叉\n最窄的一年仍差 13 个百分点",
                     fontsize=11, pad=9, linespacing=1.5)
    ax_cr5.set_ylabel("CR5（按各自排序轴，%）", fontsize=9.5)

    ax_churn.set_title("头部换血率：两组互相穿插\n区间带高度重合，分不出两类结构",
                       fontsize=11, pad=9, linespacing=1.5)
    ax_churn.set_ylabel("Top20 换血率（%）", fontsize=9.5)

    handles = [plt.Line2D([], [], color=c, lw=2, marker="s", ms=6, alpha=.55, label=n)
               for n, _, c in groups]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False,
               fontsize=9, bbox_to_anchor=(.5, .002), handlelength=1.8)

    fig.text(.005, -.075,
             "口径：CR5 与换血率均按各自数据集的排序轴计算（收入榜样本用收入、下载榜样本用下载），"
             "两组不做跨组排名。阴影为该组三个品类的 min–max 区间。\n"
             "数据：美国市场 2021–2025 逐年榜单导出（Sensor Tower），已过滤非游戏产品；"
             "换血率首年无上年可比，从 2022 年起。",
             fontsize=7.6, color="#888888", linespacing=1.5)

    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, bbox_inches="tight")
    print(f"saved -> {OUT_PNG}")


if __name__ == "__main__":
    main()
