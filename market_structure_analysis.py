# -*- coding: utf-8 -*-
"""
市场结构分析 · 主脚本
=====================

在原有「集中度 / 吸量效率 / 新品 / 存量 / Top10」五张底表之外，补四块此前没做的分析：

1. **产品模型交叉** —— 品类（或题材）内按 Sensor Tower 官方标签 `Game Product Model`
   （超休闲 / 混合休闲 / 休闲 / 中重度）拆开，看哪条商业化路径在增长。
   这是「细分赛道识别」的替代方案：官方标签比自建词族簇可辩护得多。
2. **五年趋势** —— 把逐年算的指标连成曲线，并给两个基准列（相对首年、相对同组中位），
   让「在恶化 / 在好转」这句话可判定。
3. **发行商与出海** —— 品类内发行商集中度、新进入者构成，以及
   `Most Popular Country by Downloads` 的分布（美国榜单上到底有多少产品真靠美国市场）。
4. **进入判断** —— 每个维度按五个固定问题（规模 / 增长 / 集中度 / 新品空间 / 变现路径）
   各给一行结论 + 证据 + 边界，合成「进 / 不进 / 有条件进」。

---------------------------------------------------------------------------
口径红线（写死在代码里，不靠人记）
---------------------------------------------------------------------------
1. **只在该数据集的排序轴上做总量与份额结论。** 收入榜样本（按收入筛）里
   「高下载低收入」的纯广告产品被截断，所以它的下载量是**系统性低估**；
   下载榜样本反之。另一轴的总量类指标一律标 `sample_only`，只能当样本内结构看。
2. **过滤 `Category != 'Games'`** —— 实测下载榜样本里有 3.6% 的非游戏产品，
   而它们同样带着品类 / 题材标签，不滤会污染分母。
3. **跨年在榜一律用固定 Top N 排名口径**，不用「是否出现在导出文件里」——
   各年榜单深度逐年变化（实测某品类每年 1,641 → 629 行）。
4. **DAU 只用于头部子样本**（覆盖率按下载五分位：最低档 8.9%、最高档 70%），
   不做主指标。
5. **不跨数据集拼接**。每个数据集各自跑，结论不跨集合并。
"""

import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

# ======================== 配置 ========================
class Config:
    # ---- 路径（跑之前改这两行）----
    DATA_FOLDER = r"C:\Users\yourname\Downloads\game-ranking-export"   # 榜单导出 CSV 所在目录
    OUTPUT_FOLDER = r"C:\Users\yourname\Downloads\game-ranking-export"  # 分析结果输出路径

    # ---- 分析设定 ----
    ANALYSIS_YEARS = [2021, 2022, 2023, 2024, 2025]
    DIMENSION = "sub_genre"          # sub_genre=品类（读源列 Game Sub-genre）/ game_theme=题材（读源列 Game Theme）
    RANK_AXIS = "revenue"            # 该数据集的排序轴：revenue / downloads —— 决定哪个轴可以做总量结论
    HEAD_RATIO = 0.4                 # 头部占比阈值（40%）
    MID_RATIO = 0.7                  # 中腰部占比阈值（70%）
    CR_LEVELS = [3, 5, 10]           # 集中度档位
    TOP_N_INRANK = 100               # 跨年在榜口径：固定取每个维度内 Top N
    TOP_N_HEAD = 20                  # 头部换血率用的 Top N

    # ---- 进入判断的阈值 ----
    # 每个阈值都写清「为什么是这个值」。阈值可调，但调完要回来改这里的说明，
    # 否则文档与代码会各说各话；输出表的「判定规则」列会自动带上这里的实际取值。
    JUDGE_SCALE_RATIO = 1.0          # 规模：排序轴总量 ≥ 同组中位 × 该值。
                                      # 取 1.0 = 不要求比同组中位大，只要不在中位以下；
                                      # 跨口径的维度不能比规模，所以基准限定在同一次运行内。
    JUDGE_GROWTH_MIN = 0.0           # 增长：首尾年 CAGR 下限，取 0 = 不要求增长，只要求不萎缩。
                                      # 用 CAGR 而不是最近一年同比，因为单年同比会被基数效应带偏。
    JUDGE_CR5_HIGH = 75.0            # 集中度：CR5 高于此值算「头部固化」。
                                      # 取 75 是因为 Top5 拿走四分之三份额时，
                                      # 中小玩家已很难靠单点突破进入。
    JUDGE_CR5_VERY_HIGH = 85.0       # CR5 高于此值触发否决项，综合判断封顶「有条件进入」。
                                      # 与上一档拉开 10 个点，用来区分「头部偏固」与「头部锁死」。
    JUDGE_CHURN_MIN = 15.0           # 新品空间：头部换血率下限（%）。
                                      # 用换血率而不是新品占比——新品占比高但头部固化时，
                                      # 新品其实挤不进去；换血率直接测「头部位置是否对新进入者开放」。
    JUDGE_PATH_MIN_SHARE = 50.0      # 变现路径：最大产品模型档占比下限（%），低于此值判「路径不清」。
                                      # 过半才算「说得清靠什么赚钱」；占比过半同时说明可选项变少，
                                      # 这一层含义写在输出表的「变现依据」列里。

    # ---- 输出 ----
    EXPORT_NAME = "市场结构分析"


# ======================== 工具 ========================
def safe_div(num, den, default=0.0):
    if den is None or (isinstance(den, float) and den == 0):
        return default
    try:
        if den == 0:
            return default
    except Exception:
        return default
    return num / den


def read_csv_any(path):
    """三种编码回退读取（源文件是 utf-16，但导出过的人可能转过码）。"""
    last_err = None
    for enc in ("utf-16", "utf-8-sig", "gbk"):
        try:
            return pd.read_csv(path, sep="\t", encoding=enc, on_bad_lines="skip")
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"无法读取 {path}: {last_err}")


COLUMN_MAP = {
    "unified name": "product_name",
    "unified id": "product_id",
    "unified publisher name": "publisher_name",
    "unified publisher id": "publisher_id",
    "date": "date",
    "platform": "platform",
    "category": "category",
    "game sub-genre": "sub_genre",
    "game theme": "game_theme",
    "game product model": "product_model",
    "earliest release date": "release_date",
    "most popular country by downloads": "core_market",
    "downloads (absolute)": "downloads_abs",
    "downloads (pop growth)": "downloads_growth",
    "downloads (pop growth %)": "downloads_growth_pct",
    "revenue (absolute)": "revenue_abs",
    "revenue (pop growth)": "revenue_growth",
    "revenue (pop growth %)": "revenue_growth_pct",
    "dau (absolute)": "dau_abs",
    "rpd (all time, ww)": "rpd",
    "arpdau (last month, us)": "arpdau",
    "publisher country": "publisher_country",
}


def load_panel(folder):
    """读入目录下所有榜单 CSV，统一字段、过滤非游戏、算出年份与新品标记。"""
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".csv"))
    if not files:
        raise SystemExit(f"目录下没有 csv：{folder}")

    frames = []
    for fname in files:
        df = read_csv_any(os.path.join(folder, fname))
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})

        # 年份：优先用 Date 列；取不到就从文件名里找 4 位年份
        year = None
        if "date" in df.columns:
            d = pd.to_datetime(df["date"], errors="coerce")
            yrs = d.dt.year.dropna().unique()
            if len(yrs):
                year = int(yrs[0])
        if year is None:
            m = re.search(r"(20\d\d)", fname)
            if m:
                year = int(m.group(1))
        if year is None:
            print(f"  [跳过] 无法确定年份：{fname}")
            continue

        df["analysis_year"] = year
        frames.append(df)
        print(f"  {year}: {len(df)} 行  ({fname[:46]})")

    if not frames:
        raise SystemExit("没有可用数据")
    panel = pd.concat(frames, ignore_index=True)

    # ---- 口径红线 2：过滤非游戏 ----
    before = len(panel)
    if "category" in panel.columns:
        panel = panel[panel["category"].astype(str).str.strip().eq("Games")]
    print(f"  过滤非游戏产品：{before} -> {len(panel)} 行")

    # ---- 数值化 ----
    for col in ("downloads_abs", "revenue_abs", "dau_abs", "rpd", "arpdau",
                "downloads_growth", "revenue_growth", "dau_growth"):
        if col in panel.columns:
            panel[col] = pd.to_numeric(panel[col], errors="coerce").fillna(0)
    for col in ("downloads_growth_pct", "revenue_growth_pct"):
        if col in panel.columns:
            panel[col] = pd.to_numeric(panel[col].astype(str).str.replace("%", ""),
                                       errors="coerce").fillna(0) / 100
    if "release_date" in panel.columns:
        panel["release_date"] = pd.to_datetime(panel["release_date"], errors="coerce")
        panel["release_year"] = panel["release_date"].dt.year
    else:
        panel["release_year"] = np.nan

    panel["is_new"] = panel["release_year"] == panel["analysis_year"]
    return panel


def dim_series(panel, dim):
    """取维度列（品类或题材）。"""
    if dim not in panel.columns:
        raise SystemExit(f"数据里没有维度列 {dim}；现有列：{list(panel.columns)[:30]}")
    return panel[dim].astype(str).str.strip()


# ======================== 1. 产品模型交叉 ========================
def product_model_analysis(panel, dim):
    """
    维度 × 年份 × 产品模型档：产品数、占比、样本内量价、新品占比、RPD。

    这是撤掉命名聚类之后的「细分识别」替代方案——用 ST 官方标签而不是自建词族。
    """
    rows = []
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        total_products = len(sub)
        for model, g in sub.groupby("product_model"):
            if not model or model == "nan":
                model = "Unknown"
            n = len(g)
            new_n = int(g["is_new"].sum())
            rows.append({
                "维度": d,
                "年份": int(year),
                "产品模型": model,
                "产品数": n,
                "产品数占比%": round(safe_div(n, total_products) * 100, 2),
                "样本内下载占比%": round(safe_div(g["downloads_abs"].sum(),
                                             sub["downloads_abs"].sum()) * 100, 2),
                "样本内收入占比%": round(safe_div(g["revenue_abs"].sum(),
                                             sub["revenue_abs"].sum()) * 100, 2),
                "新品数": new_n,
                "新品数占比%": round(safe_div(new_n, total_products) * 100, 2),
                "平均下载": round(g["downloads_abs"].mean(), 1),
                "平均收入": round(g["revenue_abs"].mean(), 1),
                "平均RPD": round(g["rpd"].mean(), 2),
            })
    df = pd.DataFrame(rows)
    # 加上维度当年总量，方便看该档位在整体里的位置
    if not df.empty:
        tot = df.groupby(["维度", "年份"]).agg(
            _products=("产品数", "sum"),
            _downloads=("样本内下载占比%", "sum"),
            _revenue=("样本内收入占比%", "sum")).reset_index()
        df = df.merge(tot, on=["维度", "年份"], how="left")
    return df


# ======================== 2. 五年趋势 ========================
def _cr(series, n):
    s = series.sort_values(ascending=False)
    total = s.sum()
    if not total:
        return None
    return round(s.head(n).sum() / total * 100, 2)


def _layers(sub, axis):
    """按排序轴做头部/中腰部/尾部分层。"""
    col = "revenue_abs" if axis == "revenue" else "downloads_abs"
    s = sub[col].sort_values(ascending=False)
    total = s.sum()
    if not total:
        return s.iloc[:0], s.iloc[:0], s.iloc[:0]
    head = s.cumsum() / total
    n_head = int((head <= Config.HEAD_RATIO).sum()) or 1
    n_mid = int((head <= Config.MID_RATIO).sum()) or n_head + 1
    return s.iloc[:n_head], s.iloc[n_head:n_mid], s.iloc[n_mid:]


def trend_analysis(panel, dim, axis):
    """
    维度 × 年份 × 指标的长表，外加两个基准列：
      - 相对首年变化（同一维度内，指标自身）
      - 相对同组中位（同年、同组内其他维度的中位数）
    没有基准，趋势表只是一堆数；有了基准才能说「在恶化还是在好转」。
    """
    rows = []
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        r = {"维度": d, "年份": int(year)}
        r["产品数"] = len(sub)
        r["发行商数"] = sub["publisher_name"].nunique() if "publisher_name" in sub.columns else None

        # 排序轴总量（唯一允许做「总量结论」的一侧）
        r["排序轴总量"] = round(sub["revenue_abs"].sum(), 0) if axis == "revenue" \
            else round(sub["downloads_abs"].sum(), 0)
        r["排序轴"] = "收入" if axis == "revenue" else "下载"
        # 另一轴：样本内值，标注只能当结构看
        other = "downloads_abs" if axis == "revenue" else "revenue_abs"
        r["另轴总量(样本内)"] = round(sub[other].sum(), 0)
        r["另轴口径"] = "sample_only"

        # 集中度：排序轴一侧是可信的集中度，另一侧标注
        for n in Config.CR_LEVELS:
            r[f"CR{n}_{axis}"] = _cr(sub["revenue_abs" if axis == 'revenue' else 'downloads_abs'], n)
        other_col = "downloads_abs" if axis == "revenue" else "revenue_abs"
        r[f"CR5_{other_col.split('_')[0]}(样本内)"] = _cr(sub[other_col], 5)

        # 分层增长贡献（按排序轴分层）
        head, mid, tail = _layers(sub, axis)
        growth_col = "revenue_growth" if axis == "revenue" else "downloads_growth"
        total_growth = sub[growth_col].sum()
        r["头部增长贡献%"] = round(safe_div(sub.loc[head.index, growth_col].sum(), total_growth) * 100, 2)
        r["中腰部增长贡献%"] = round(safe_div(sub.loc[mid.index, growth_col].sum(), total_growth) * 100, 2)
        r["尾部增长贡献%"] = round(safe_div(sub.loc[tail.index, growth_col].sum(), total_growth) * 100, 2)

        # 新品
        new = sub[sub["is_new"]]
        r["新品数"] = len(new)
        r["新品数占比%"] = round(safe_div(len(new), len(sub)) * 100, 2)
        r["新品排序轴占比%"] = round(safe_div(
            new["revenue_abs"].sum() if axis == "revenue" else new["downloads_abs"].sum(),
            sub["revenue_abs"].sum() if axis == "revenue" else sub["downloads_abs"].sum()) * 100, 2)

        # 头部换血率（口径：固定 Top N，与上年比）
        rank_col = "revenue_abs" if axis == "revenue" else "downloads_abs"
        top_rows = sub.nlargest(Config.TOP_N_HEAD, rank_col)
        top_ids = set(top_rows["product_id"])
        r[f"Top{Config.TOP_N_HEAD}占比%"] = round(safe_div(
            top_rows[rank_col].sum(), sub[rank_col].sum()) * 100, 2)
        if int(year) - 1 in set(panel["analysis_year"]):
            prev = panel[(panel[dim] == d) & (panel["analysis_year"] == int(year) - 1)]
            prev_top = set(prev.nlargest(Config.TOP_N_HEAD, rank_col)["product_id"])
            r["头部换血率%"] = round(safe_div(len(top_ids - prev_top), len(top_ids)) * 100, 2)
        else:
            r["头部换血率%"] = None

        # 变现
        r["平均RPD"] = round(sub["rpd"].mean(), 2)
        r["RPD中位数"] = round(sub["rpd"].median(), 2)
        r["平均下载"] = round(sub["downloads_abs"].mean(), 1)
        r["平均收入"] = round(sub["revenue_abs"].mean(), 1)

        # 产品模型集中度（变现路径是否单一）
        pm = sub["product_model"].value_counts(normalize=True)
        r["最大产品模型档"] = pm.index[0] if len(pm) else None
        r["最大档占比%"] = round(pm.iloc[0] * 100, 2) if len(pm) else None

        rows.append(r)

    df = pd.DataFrame(rows)

    # 基准 1：相对首年
    if not df.empty:
        first_year = df.groupby("维度")["年份"].transform("min")
        base = df[first_year == df["年份"]].set_index("维度")
        for metric in ("CR5_revenue", "CR5_downloads", "新品数占比%", "平均RPD", "排序轴总量"):
            if metric in df.columns and metric in base.columns:
                ref = df["维度"].map(base[metric])
                df[f"{metric}_相对首年"] = np.where(
                    (ref > 0), ((df[metric] - ref) / ref * 100).round(2), None)
    # 基准 2：相对同组中位（同年、同组内其他维度）
    if not df.empty:
        for metric in ("CR5_revenue", "CR5_downloads", "新品数占比%", "平均RPD", "排序轴总量"):
            if metric in df.columns:
                med = df.groupby("年份")[metric].transform("median")
                df[f"{metric}_同组中位"] = med.round(2)
    return df


# ======================== 3. 发行商与出海 ========================
def publisher_analysis(panel, dim, axis):
    """发行商集中度 + 新进入者构成 + 产品真正依赖的市场分布。"""
    rows = []
    rank_col = "revenue_abs" if axis == "revenue" else "downloads_abs"
    for (d, year), sub in panel.groupby([dim, "analysis_year"]):
        r = {"维度": d, "年份": int(year)}
        r["产品数"] = len(sub)
        r["发行商数"] = sub["publisher_name"].nunique() if "publisher_name" in sub.columns else None
        r["平均每发行商产品数"] = round(safe_div(len(sub), r["发行商数"]), 2)

        # 发行商集中度：按发行商聚合排序轴，再算份额
        if "publisher_name" in sub.columns:
            pub = sub.groupby("publisher_name")[rank_col].sum().sort_values(ascending=False)
            total = pub.sum()
            for n in (3, 5):
                r[f"发行商CR{n}%"] = round(safe_div(pub.head(n).sum(), total) * 100, 2)
            r["发行商CR3产品数"] = int((pub.head(3) > 0).sum())

        # 新进入者构成：当年首次出现的产品，其发行商此前是否已在榜
        if int(year) - 1 in set(panel["analysis_year"]):
            prev = panel[(panel[dim] == d) & (panel["analysis_year"] == int(year) - 1)]
            prev_pubs = set(prev["publisher_name"].dropna()) if "publisher_name" in prev.columns else set()
            prev_ids = set(prev["product_id"])
            fresh = sub[~sub["product_id"].isin(prev_ids)]
            fresh_pubs = set(fresh["publisher_name"].dropna()) if "publisher_name" in fresh.columns else set()
            r["新增产品数"] = len(fresh)
            r["新增产品占比%"] = round(safe_div(len(fresh), len(sub)) * 100, 2)
            r["新进入发行商数"] = len(fresh_pubs - prev_pubs)
            r["新进入发行商占比%"] = round(safe_div(len(fresh_pubs - prev_pubs), len(fresh_pubs)) * 100, 2)
            r["老发行商带新产品数"] = len(fresh_pubs & prev_pubs)

        # 真正依赖的市场：Most Popular Country by Downloads
        if "core_market" in sub.columns:
            mkt = sub["core_market"].dropna()
            mkt = mkt[mkt.astype(str).str.strip() != ""]
            r["有市场信息产品数"] = len(mkt)
            r["非美国市场产品占比%"] = round(
                safe_div((mkt.astype(str) != "US").sum(), len(mkt)) * 100, 2)
            top = mkt.value_counts().head(3)
            r["主要市场TOP3"] = "; ".join(f"{k} {v}" for k, v in top.items())
        rows.append(r)
    return pd.DataFrame(rows)


def market_mix_table(panel, dim):
    """维度 × 主要市场的产品数矩阵（出海视角）。"""
    if "core_market" not in panel.columns:
        return pd.DataFrame()
    rows = []
    for (d, year, mkt), g in panel.groupby([dim, "analysis_year", "core_market"]):
        rows.append({"维度": d, "年份": int(year), "主要市场": mkt,
                     "产品数": len(g),
                     "样本内下载占比%": round(safe_div(
                         g["downloads_abs"].sum(),
                         panel[(panel[dim] == d) & (panel["analysis_year"] == year)]["downloads_abs"].sum()) * 100, 2),
                     "样本内收入占比%": round(safe_div(
                         g["revenue_abs"].sum(),
                         panel[(panel[dim] == d) & (panel["analysis_year"] == year)]["revenue_abs"].sum()) * 100, 2)})
    return pd.DataFrame(rows)


def judgement_rule_text():
    """
    把当前 Config 的实际取值格式化成一段规则说明，写进输出表的「判定规则」列。
    这样阈值一旦调整，表里的说明自动跟着变，不会出现「文档写一套、代码跑另一套」。
    """
    return (
        f"规模：排序轴总量 ≥ 同组中位 × {Config.JUDGE_SCALE_RATIO:g}；"
        f"增长：首尾年 CAGR ≥ {Config.JUDGE_GROWTH_MIN:g}%；"
        f"集中度：CR5 < {Config.JUDGE_CR5_HIGH:g}% 为可接受；"
        f"新品空间：头部换血率 ≥ {Config.JUDGE_CHURN_MIN:g}%；"
        f"变现路径：最大产品模型档占比 ≥ {Config.JUDGE_PATH_MIN_SHARE:g}%。"
        f"合成：通过 ≥4 项且无否决 → 可进入；≥3 项 → 有条件进入；≤2 项 → 不建议进入。"
        f"否决：CR5 ≥ {Config.JUDGE_CR5_VERY_HIGH:g}% → 封顶「有条件进入」。"
    )


# ======================== 4. 进入判断 ========================
def entry_judgement(trend, model_df):
    """
    每个维度按五个固定问题出一行结论。规则全部显式，判定依据写进表里，
    不用「感觉」下结论；阈值集中在 Config，方便按报告口径调整。
    """
    if trend.empty:
        return pd.DataFrame()

    rows = []
    for d, g in trend.groupby("维度"):
        g = g.sort_values("年份")
        first, last = g.iloc[0], g.iloc[-1]
        axis_label = first["排序轴"]

        # 规模：排序轴总量 vs 同组中位
        scale_ref = last.get(f"排序轴总量_同组中位")
        scale_val = last.get("排序轴总量")
        if scale_ref and scale_ref > 0:
            ratio = scale_val / scale_ref
            scale_ok = ratio >= Config.JUDGE_SCALE_RATIO
            scale_txt = (f"{axis_label}总量 {scale_val:,.0f}，为同组中位的 {ratio:.2f} 倍")
            scale_judge = "规模够" if scale_ok else "规模偏小"
        else:
            scale_ok, scale_txt = False, "样本内无对比基准"

        # 增长：首尾年 CAGR（仅排序轴）
        cagr = None
        if first.get("排序轴总量") and last.get("排序轴总量") and first["排序轴总量"] > 0 and \
                last["年份"] > first["年份"]:
            yrs = last["年份"] - first["年份"]
            cagr = ((last["排序轴总量"] / first["排序轴总量"]) ** (1 / yrs) - 1) * 100
            growth_ok = cagr >= Config.JUDGE_GROWTH_MIN
            growth_txt = f"{axis_label}首尾年 CAGR {cagr:+.1f}%"
        else:
            growth_ok, growth_txt = False, "首尾年数据不足"

        # 集中度：CR5 水平 + 方向
        cr5_col = "CR5_revenue" if axis_label == "收入" else "CR5_downloads"
        cr5 = last.get(cr5_col)
        cr5_first = first.get(cr5_col)
        veto = ""
        if cr5 is not None:
            if cr5_first is not None:
                direction = cr5 - cr5_first
                dir_txt = f"{'上升' if direction > 0 else '下降'} {abs(direction):.1f} pp（对比首年）"
            else:
                direction, dir_txt = 0, "无首年对比"
            conc_ok = cr5 < Config.JUDGE_CR5_HIGH
            conc_txt = f"CR5 {cr5:.1f}%（{axis_label}），{dir_txt}"
            if cr5 >= Config.JUDGE_CR5_VERY_HIGH:
                veto = (f"CR5 已达 {cr5:.1f}%，头部固化"
                        + ("且仍在上升，窗口在关闭" if direction > 0 else "，新进入者空间受限"))
        else:
            conc_ok, conc_txt = False, "缺集中度数据"

        # 新品空间：头部换血率（头部位置是否对新进入者开放）+ 当年新品占比
        churn = last.get("头部换血率%")
        np_share = last.get("新品数占比%")
        if churn is not None:
            new_ok = churn >= Config.JUDGE_CHURN_MIN
            new_txt = (f"头部换血率 {churn:.1f}%"
                       + (f"（当年新品占在榜产品 {np_share:.1f}%）" if np_share is not None else ""))
            new_txt += "，头部位置对新进入者开放" if new_ok else "，头部位置对新进入者不友好"
        else:
            new_ok, new_txt = False, "缺头部换血率"

        # 变现路径：主导档位占比（占比太低说明说不清靠什么赚钱；太高说明可选项少）
        model_conc = last.get("最大档占比%")
        model_name = last.get("最大产品模型档")
        if model_conc is not None:
            path_ok = model_conc >= Config.JUDGE_PATH_MIN_SHARE
            if model_conc >= 80:
                path_txt = f"最大档「{model_name}」占 {model_conc:.1f}%（路径清晰，但可选项少）"
            elif model_conc >= Config.JUDGE_PATH_MIN_SHARE:
                path_txt = f"最大档「{model_name}」占 {model_conc:.1f}%（路径较清晰）"
            else:
                path_txt = f"最大档「{model_name}」仅占 {model_conc:.1f}%（变现路径分散）"
        else:
            path_ok, path_txt = False, "缺产品模型数据"

        # 合成
        checks = [scale_ok, growth_ok, conc_ok, new_ok, path_ok]
        n_ok = sum(1 for x in checks if x)
        if n_ok >= 4 and not veto:
            verdict = "可进入"
        elif n_ok >= 3:
            verdict = "有条件进入"
        else:
            verdict = "不建议进入"
        if veto and verdict == "可进入":
            verdict = "有条件进入"

        boundary = (f"样本框：该维度来自{axis_label}榜样本；"
                    "总量与份额结论仅在排序轴一侧成立；"
                    "基准仅限本数据集覆盖的维度，不是全市场；"
                    "非游戏产品已剔除")

        rows.append({
            "维度": d, "年份": int(last["年份"]),
            "1_规模够不够": scale_judge, "规模依据": scale_txt,
            "2_增长正不正": "增长为正" if growth_ok else "增长非正", "增长依据": growth_txt,
            "3_集中度高不高": "集中度高" if not conc_ok else "集中度可接受", "集中度依据": conc_txt,
            "4_新品有没有空间": "新品有空间" if new_ok else "新品空间窄", "新品依据": new_txt,
            "5_变现路径清不清晰": "路径清晰" if path_ok else "路径不清", "变现依据": path_txt,
            "通过项数": f"{n_ok}/5",
            "否决项": veto or "无",
            "综合判断": verdict,
            "判定规则": judgement_rule_text(),
            "适用边界": boundary,
        })
    return pd.DataFrame(rows)


# ======================== 主流程 ========================
def main():
    print("=" * 70)
    print("市场结构分析")
    print(f"数据目录：{Config.DATA_FOLDER}")
    print(f"维度：{Config.DIMENSION}   排序轴：{Config.RANK_AXIS}")
    print("=" * 70)

    print("\n1. 读取数据")
    panel = load_panel(Config.DATA_FOLDER)
    panel[Config.DIMENSION] = dim_series(panel, Config.DIMENSION)
    panel = panel[panel[Config.DIMENSION].ne("") & panel[Config.DIMENSION].ne("nan")]
    print(f"   维度取值：{sorted(panel[Config.DIMENSION].unique())}")

    print("\n2. 产品模型交叉")
    model_df = product_model_analysis(panel, Config.DIMENSION)
    print(f"   {len(model_df)} 行")

    print("\n3. 五年趋势")
    trend = trend_analysis(panel, Config.DIMENSION, Config.RANK_AXIS)
    print(f"   {len(trend)} 行")

    print("\n4. 发行商与出海")
    pub_df = publisher_analysis(panel, Config.DIMENSION, Config.RANK_AXIS)
    mix_df = market_mix_table(panel, Config.DIMENSION)
    print(f"   {len(pub_df)} 行；市场矩阵 {len(mix_df)} 行")

    print("\n5. 进入判断")
    judge = entry_judgement(trend, model_df)
    print(f"   {len(judge)} 行")

    os.makedirs(Config.OUTPUT_FOLDER, exist_ok=True)
    out = os.path.join(Config.OUTPUT_FOLDER,
                        f"{Config.EXPORT_NAME}_{Config.DIMENSION}_{datetime.now():%Y%m%d_%H%M}.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        model_df.to_excel(writer, sheet_name="产品模型分析", index=False)
        trend.to_excel(writer, sheet_name="五年趋势", index=False)
        pub_df.to_excel(writer, sheet_name="发行商与出海", index=False)
        if not mix_df.empty:
            mix_df.to_excel(writer, sheet_name="市场分布", index=False)
        judge.to_excel(writer, sheet_name="进入判断", index=False)
    print(f"\n已保存：{out}")

    # 控制台把判断层打出来，方便直接读
    if not judge.empty:
        qa = [("1_规模够不够", "规模依据"), ("2_增长正不正", "增长依据"),
              ("3_集中度高不高", "集中度依据"), ("4_新品有没有空间", "新品依据"),
              ("5_变现路径清不清晰", "变现依据")]
        print("\n" + "=" * 70)
        for _, r in judge.iterrows():
            print(f"\n【{r['维度']}】{r['综合判断']}（通过 {r['通过项数']}）")
            if r.get("否决项") and r["否决项"] != "无":
                print(f"   ⚠ 否决项：{r['否决项']}")
            for qk, bk in qa:
                print(f"   {qk}: {r[qk]}  —— {r[bk]}")
    return out


if __name__ == "__main__":
    sys.exit(main())
