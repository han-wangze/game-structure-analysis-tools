# -*- coding: utf-8 -*-
"""
产品轨迹分析 · 队列存活与头部换血
================================

用产品 ID 跨年连接，回答三个此前没被回答过的问题：

1. **进来之后能活几年** —— 按首发年份分队列，看第 k 年仍在榜的比例。
2. **头部在固化还是在轮换** —— 每年 Top N 里有多少是上一年不在的。
3. **什么样的新品能活下来** —— 存活者与退出者在进入年的特征差在哪。

---------------------------------------------------------------------------
口径（写死在代码里）
---------------------------------------------------------------------------
1. **在榜口径 = 固定 Top N 排名**，不是「是否出现在导出文件里」。
   各年榜单深度逐年变化（实测某品类每年 1,641 → 629 行），用文件出现与否会把
   「榜单变浅」误判成「产品掉榜」。
2. **队列分母 = 当年进榜的新品**，不是「当年全部新品」。
   只有进了榜的产品才在样本内，所以测出的存活率偏向「当年已变现的新品」，
   偏乐观；这个偏误在输出表的列名里写明。
3. **只在该数据集的排序轴上排名**；另一轴只作样本内参考。
4. **过滤 `Category != 'Games'`**（实测下载榜样本有 3.6% 非游戏产品带着题材标签）。
"""

import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

# ======================== 配置 ========================
class Config:
    DATA_FOLDER = r"C:\Users\yourname\Downloads\game-ranking-export"   # 榜单导出 CSV 所在目录
    OUTPUT_FOLDER = r"C:\Users\yourname\Downloads\game-ranking-export"  # 分析结果输出路径

    ANALYSIS_YEARS = [2021, 2022, 2023, 2024, 2025]
    DIMENSION = "sub_genre"      # sub_genre / game_theme
    RANK_AXIS = "revenue"        # 该数据集的排序轴
    TOP_N_SURVIVAL = 100         # 存活判定的固定 Top N
    TOP_N_CHURN = 20             # 头部换血率的 Top N
    EXPORT_NAME = "产品轨迹分析"


COLUMN_MAP = {
    "unified name": "product_name",
    "unified id": "product_id",
    "unified publisher name": "publisher_name",
    "date": "date",
    "category": "category",
    "game sub-genre": "sub_genre",
    "game theme": "game_theme",
    "game product model": "product_model",
    "earliest release date": "release_date",
    "most popular country by downloads": "core_market",
    "downloads (absolute)": "downloads_abs",
    "revenue (absolute)": "revenue_abs",
    "rpd (all time, ww)": "rpd",
    "publisher country": "publisher_country",
}


def safe_div(num, den, default=0.0):
    try:
        return num / den if den else default
    except Exception:
        return default


def read_csv_any(path):
    last = None
    for enc in ("utf-16", "utf-8-sig", "gbk"):
        try:
            return pd.read_csv(path, sep="\t", encoding=enc, on_bad_lines="skip")
        except Exception as exc:
            last = exc
    raise RuntimeError(f"无法读取 {path}: {last}")


def load_panel(folder):
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".csv"))
    frames = []
    for fname in files:
        df = read_csv_any(os.path.join(folder, fname))
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
        year = None
        if "date" in df.columns:
            yrs = pd.to_datetime(df["date"], errors="coerce").dt.year.dropna().unique()
            if len(yrs):
                year = int(yrs[0])
        if year is None:
            m = re.search(r"(20\d\d)", fname)
            if m:
                year = int(m.group(1))
        if year is None:
            continue
        df["analysis_year"] = year
        frames.append(df)
        print(f"  {year}: {len(df)} 行  ({fname[:46]})")
    if not frames:
        raise SystemExit("没有可用数据")
    panel = pd.concat(frames, ignore_index=True)

    before = len(panel)
    if "category" in panel.columns:
        panel = panel[panel["category"].astype(str).str.strip().eq("Games")]
    print(f"  过滤非游戏：{before} -> {len(panel)} 行")

    for col in ("downloads_abs", "revenue_abs", "rpd"):
        if col in panel.columns:
            panel[col] = pd.to_numeric(panel[col], errors="coerce").fillna(0)
    if "release_date" in panel.columns:
        panel["release_date"] = pd.to_datetime(panel["release_date"], errors="coerce")
        panel["release_year"] = panel["release_date"].dt.year
    else:
        panel["release_year"] = np.nan
    panel["is_new"] = panel["release_year"] == panel["analysis_year"]
    return panel


def rank_col(axis):
    return "revenue_abs" if axis == "revenue" else "downloads_abs"


# ======================== 1. 队列进入率 ========================
def cohort_entry_rate(panel, dim, axis):
    """
    按首发年份分队列，看第 k 年有多少成员进入头部 Top N。

    ⚠ 指标命名说明：这个量测的是「新品进入头部的比例」，不是「存活率」——
    队列成员从未被要求先进过 Top N，所以不是从某个状态往下掉的存活。
    真正意义的存活（进了头部之后能否保住位置）见「头部留存」。

    两个必须知道的偏误：
    - **分母是「当年进榜的新品」**，不是当年全部新品 → 结果偏乐观。
    - **上线当年（k=0）在收入轴下结构性吃亏**：新游当年几乎没有收入，
      不可能进当年收入 Top N；到第二年才有完整年度数据。所以 k=0 那一列
      与 k≥1 不可直接比较，脚本会单独标注。
    """
    rcol = rank_col(axis)
    years = sorted(panel["analysis_year"].unique())
    max_year = max(years)

    top_sets = {}
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        ids = sub.nlargest(Config.TOP_N_SURVIVAL, rcol)["product_id"]
        top_sets[(d, int(year))] = set(ids)

    rows = []
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        year = int(year)
        cohort = sub[sub["release_year"] == year]      # 当年进榜的新品
        if cohort.empty:
            continue
        cohort_ids = set(cohort["product_id"])
        base_size = len(cohort_ids)

        for k in range(0, len(years)):
            target_year = year + k
            if target_year > max_year:
                break
            alive = cohort_ids & top_sets.get((d, target_year), set())
            note = f"Top{Config.TOP_N_SURVIVAL}（{axis}排名）；分母为当年进榜新品，非当年全部新品"
            if k == 0:
                note += "；k=0 为上线当年（收入轴下新游当年无收入，不可与后续年份直接比较）"
            rows.append({
                "维度": d,
                "队列年(首发年)": year,
                "经过年数k": k,
                "观察年": target_year,
                "队列规模(当年进榜新品数)": base_size,
                "进入头部数": len(alive),
                "头部进入率%": round(safe_div(len(alive), base_size) * 100, 2),
                "口径说明": note,
            })
    return pd.DataFrame(rows)


# ======================== 1b. 头部留存 ========================
def head_retention(panel, dim, axis):
    """
    真正的存活口径：**在首个完整经营年进入 Top N 的新品，次年还能不能保住位置**。

    队列 = 首发于 Y-1 年、且在 Y 年（首个完整年）进入 Top N 的产品。
    留存 = 次年仍在 Top N。
    这个口径避开了「上线当年进不了榜」的干扰，是业务真正关心的
    「新品挤进头部后守不守得住」。
    """
    rcol = rank_col(axis)
    years = sorted(panel["analysis_year"].unique())
    max_year = max(years)

    top_sets = {}
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        ids = sub.nlargest(Config.TOP_N_SURVIVAL, rcol)["product_id"]
        top_sets[(d, int(year))] = set(ids)

    rows = []
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        year = int(year)
        if year - 1 not in years:
            continue
        first_full = sub[(sub["release_year"] == year - 1)]
        if first_full.empty:
            continue
        entered = set(first_full["product_id"]) & top_sets.get((d, year), set())
        if not entered:
            continue
        if year + 1 > max_year:
            continue
        next_top = top_sets.get((d, year + 1), set())
        kept = entered & next_top
        rows.append({
            "维度": d,
            "观察年": year,
            "队列(上年新品且本年进入TopN)数": len(entered),
            "次年仍在TopN数": len(kept),
            "头部留存率%": round(safe_div(len(kept), len(entered)) * 100, 2),
            "口径": f"Top{Config.TOP_N_SURVIVAL}（{axis}排名）；队列为首发于{year-1}年、{year}年进入头部的新品",
        })
    return pd.DataFrame(rows)


# ======================== 2. 头部换血 ========================
def head_churn(panel, dim, axis):
    """每年 Top N 里有多少是上一年不在的；新进榜产品里有多少是当年新品。"""
    rcol = rank_col(axis)
    rows = []
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        year = int(year)
        top = sub.nlargest(Config.TOP_N_CHURN, rcol)
        cur = set(top["product_id"])
        prev_year = year - 1
        prev = panel[(panel[dim] == d) & (panel["analysis_year"] == prev_year)]
        has_prev = len(prev) > 0
        prev_ids = set(prev["product_id"]) if has_prev else set()
        prev_top = set(prev.nlargest(Config.TOP_N_CHURN, rcol)["product_id"]) if has_prev else set()

        newcomers = cur - prev_ids
        new_in_top = cur - prev_top
        rows.append({
            "维度": d, "年份": year,
            f"Top{Config.TOP_N_CHURN}产品数": len(cur),
            "其中上一年未进榜的新产品数": len(newcomers) if has_prev else None,
            "新产品占比%": round(safe_div(len(newcomers), len(cur)) * 100, 2) if has_prev else None,
            "头部换血率%": round(safe_div(len(new_in_top), len(cur)) * 100, 2) if has_prev else None,
            "换血产品中当年新品数": (int(top[top["product_id"].isin(new_in_top) & top["is_new"]].shape[0])
                                 if has_prev else None),
            "换血产品中当年新品占比%": (round(safe_div(
                top[top["product_id"].isin(new_in_top) & top["is_new"]].shape[0],
                len(new_in_top)) * 100, 2) if has_prev else None),
            "口径": (f"Top{Config.TOP_N_CHURN}（{axis}排名）；换血=今年在榜且去年不在"
                   + ("；首年无上年数据，留空" if not has_prev else "")),
        })
    return pd.DataFrame(rows)


# ======================== 3. 存活者 vs 退出者 ========================
def survivor_vs_exit(panel, dim, axis):
    """
    对每个队列（首发年），把队列成员按「第 2 年是否仍在榜」分成两组，
    对比它们在**进入年**的特征：下载规模、RPD、产品模型档、发行商规模。
    """
    rcol = rank_col(axis)
    years = sorted(panel["analysis_year"].unique())
    rows = []

    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        year = int(year)
        cohort = sub[sub["release_year"] == year]
        if cohort.empty:
            continue
        nxt = year + 1
        if nxt > max(years):
            continue
        nxt_sub = panel[(panel[dim] == d) & (panel["analysis_year"] == nxt)]
        if nxt_sub.empty:
            continue
        alive_ids = set(nxt_sub.nlargest(Config.TOP_N_SURVIVAL, rcol)["product_id"])

        cohort = cohort.copy()
        cohort["survived"] = cohort["product_id"].isin(alive_ids)
        for survived, g in cohort.groupby("survived"):
            label = "存活(次年仍在TopN)" if survived else "退出(次年掉出TopN)"
            pub_count = g["publisher_name"].nunique() if "publisher_name" in g.columns else None
            model_top = g["product_model"].value_counts()
            rows.append({
                "维度": d,
                "队列年(首发年)": year,
                "分组": label,
                "产品数": len(g),
                "占队列%": round(safe_div(len(g), len(cohort)) * 100, 2),
                "进入年平均下载": round(g["downloads_abs"].mean(), 1),
                "进入年下载中位数": round(g["downloads_abs"].median(), 1),
                "进入年平均收入": round(g["revenue_abs"].mean(), 1),
                "进入年平均RPD": round(g["rpd"].mean(), 2),
                "涉及发行商数": pub_count,
                "平均每发行商产品数": round(safe_div(len(g), pub_count), 2),
                "主导产品模型档": model_top.index[0] if len(model_top) else None,
                "主导档占比%": round(model_top.iloc[0] / len(g) * 100, 2) if len(model_top) else None,
            })
    return pd.DataFrame(rows)


# ======================== 主流程 ========================
def main():
    print("=" * 70)
    print("产品轨迹分析")
    print(f"数据：{Config.DATA_FOLDER}")
    print(f"维度：{Config.DIMENSION}   排序轴：{Config.RANK_AXIS}")
    print("=" * 70)

    panel = load_panel(Config.DATA_FOLDER)
    panel[Config.DIMENSION] = panel[Config.DIMENSION].astype(str).str.strip()
    panel = panel[panel[Config.DIMENSION].ne("") & panel[Config.DIMENSION].ne("nan")]
    panel = panel[panel["analysis_year"].isin(Config.ANALYSIS_YEARS)]

    print("\n1. 队列进入率")
    entry = cohort_entry_rate(panel, Config.DIMENSION, Config.RANK_AXIS)
    print(f"   {len(entry)} 行")

    print("\n1b. 头部留存（进了头部能不能保住）")
    ret = head_retention(panel, Config.DIMENSION, Config.RANK_AXIS)
    print(f"   {len(ret)} 行")

    print("\n2. 头部换血")
    churn = head_churn(panel, Config.DIMENSION, Config.RANK_AXIS)
    print(f"   {len(churn)} 行")

    print("\n3. 存活者 vs 退出者")
    svex = survivor_vs_exit(panel, Config.DIMENSION, Config.RANK_AXIS)
    print(f"   {len(svex)} 行")

    os.makedirs(Config.OUTPUT_FOLDER, exist_ok=True)
    out = os.path.join(Config.OUTPUT_FOLDER,
                        f"{Config.EXPORT_NAME}_{Config.DIMENSION}_{datetime.now():%Y%m%d_%H%M}.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        entry.to_excel(writer, sheet_name="队列进入率", index=False)
        ret.to_excel(writer, sheet_name="头部留存", index=False)
        churn.to_excel(writer, sheet_name="头部换血", index=False)
        svex.to_excel(writer, sheet_name="存活者vs退出者", index=False)
    print(f"\n已保存：{out}")

    # 控制台摘要
    if not entry.empty:
        print("\n" + "=" * 70)
        print("新品队列进入头部的比例（k=0 为上线当年，收入轴下不可与后续年份直接比较）:")
        piv = entry.pivot_table(index=["维度", "队列年(首发年)"], columns="经过年数k",
                                values="头部进入率%")
        print(piv.round(1).to_string())
    if not ret.empty:
        print("\n头部留存率（上年新品进入 Top N 后，次年仍保住位置的比例）:")
        print(ret.pivot_table(index="观察年", columns="维度",
                              values="头部留存率%").round(1).to_string())
    if not churn.empty:
        print("\n头部换血率（Top20 里今年在榜、去年不在的占比）:")
        print(churn.pivot_table(index="年份", columns="维度", values="头部换血率%").round(1).to_string())
    return out


if __name__ == "__main__":
    sys.exit(main())
