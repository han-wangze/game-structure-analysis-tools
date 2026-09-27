# genre_analysis.py 输出字段说明

输出文件：`game_category_analysis_report_5years.xlsx`，共 6 张底表。除「TOP10产品详情」外，每行 = 一个品类 × 一个年份。

## 通用口径

- **分析粒度**：维度（品类或题材）× 年份，由 `Config.DIMENSION` 决定——`"sub_genre"` 按品类（源列 `Game Sub-genre`），`"game_theme"` 按题材（源列 `Game Theme`）。
- **维度列名**：输出的维度列名随配置而变——跑品类时为 `sub_genre`，跑题材时为 `game_theme`（本文统一称「维度列」）。
- **分层**：按下载量降序累计占比划分——头部 ≤40%、中腰部 40%–70%、尾部 >70%。
- **新品 / 存量**：首发日期落在当年 1/1–12/31 的为新品，其余为存量产品。
- **成熟 / 衰退**：上线 1–3 年为成熟产品，3 年以上为衰退产品。
- **指标来源列**：下载 = `Downloads (Absolute)`；收入 = `Revenue (Absolute)`；DAU = `DAU (Absolute)`；RPD = `RPD (All Time, WW)`（每下载收入）；ARPDAU = `ARPDAU (Last Month, US)`（每 DAU 平均收入）。
- **增长**：`Downloads / Revenue (PoP Growth)`，即年同比增量。

| 页签 | 内容 |
|---|---|
| 1 | 集中度分析：CR 集中度、分层增长贡献、头部稳定性、吸量与变现差异 |
| 2 | 吸量效率分析：分层吸量效率与三个效率维度 |
| 3 | 新品表现分析：新品数量、渗透率、增长贡献、变现溢价 |
| 4 | 存量产品分析：成熟 / 衰退分层的规模与贡献 |
| 5 | 聚类分析汇总：命名聚类的关键词与各簇表现 |
| 6 | TOP10产品详情：下载、收入两个维度各取 Top10 的产品明细 |

## 1. 集中度分析

**标识**

| 字段 | 类型 | 含义 |
|---|---|---|
| `sub_genre` / `game_theme` | 字符串 | 维度名称（品类名或题材名，取决于 `Config.DIMENSION`） |
| `year` | 整数 | 分析年份（2021–2025） |
| `total_products` | 整数 | 该品类当年有效产品数 |

**CR 集中度**（下载、收入各自按自己的排名取前 N）

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `CR3_download_pct` / `CR3_revenue_pct` | 浮点 | 前 3 名产品的下载 / 收入占比（%） | 前 3 名之和 ÷ 品类合计 |
| `CR3_monopoly_level` | 字符串 | 垄断程度 | ≥80% 高垄断；40%–80% 中垄断；<40% 低垄断 |
| `CR5_*` / `CR10_*` | — | 同上，取前 5 / 前 10 名 | 同上 |

**分层增长贡献**

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `head_download_contribution_pct` | 浮点 | 头部（≤40%）产品占品类下载增长的比重（%） | 头部增长之和 ÷ 品类增长合计 |
| `mid_download_contribution_pct` | 浮点 | 中腰部（40%–70%）下载增长贡献 | 同上 |
| `tail_download_contribution_pct` | 浮点 | 尾部（>70%）下载增长贡献 | 同上 |
| `head_revenue_contribution_pct` 等 | 浮点 | 收入侧的三层贡献 | 同上 |

**头部结构稳定性**

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `head3_download_growth_variance` | 浮点 | 前 3 名下载增长的方差，越小越稳定 | 前 3 名增长值的方差 |
| `top1_vs_top2_download_gap_ratio` | 浮点 | 第一名相对第二名的领先幅度（%） | (第1名 − 第2名) ÷ 第2名 |
| `head3_maturity_ratio` | 浮点 | 前 3 名中上线 1–3 年产品的占比（%） | 成熟产品数 ÷ 3 |

**吸量效率**

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `category_avg_acquisition` | 浮点 | 品类平均吸量（每产品下载量） | 品类下载合计 ÷ 产品数 |
| `new_product_avg_acquisition` | 浮点 | 新品平均吸量 | 新品下载合计 ÷ 新品数 |
| `head_avg_acquisition` / `mid_avg_acquisition` / `tail_avg_acquisition` | 浮点 | 各层平均吸量 | 该层下载合计 ÷ 该层产品数 |
| `avg_acquisition_growth_efficiency` | 浮点 | 单位上线时长的下载增长 | 下载增长 ÷ 上线天数，取均值 |
| `avg_acquisition_retention_efficiency` | 浮点 | 留存效率（%） | DAU ÷ 下载量，取均值 |
| `avg_acquisition_monetization_efficiency` | 浮点 | 变现效率 | 品类 RPD 均值 |

**变现差异**

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `head_download_revenue_conversion_ratio` | 浮点 | 头部单位下载收入相对全品类的倍数（%） | 头部单位下载收入 ÷ 品类单位下载收入 |
| `mid_tail_rpd_gap` | 浮点 | 中腰部与尾部的 RPD 差距 | 中腰部 RPD 均值 − 尾部 RPD 均值 |

## 2. 吸量效率分析

`sub_genre`、`year` 同上，其余为第 1 张表「吸量效率」部分的 9 个字段：`category_avg_acquisition`、`new_product_avg_acquisition`、`head_avg_acquisition`、`mid_avg_acquisition`、`tail_avg_acquisition`、`avg_acquisition_growth_efficiency`、`avg_acquisition_retention_efficiency`、`avg_acquisition_monetization_efficiency`。口径见上表。

## 3. 新品表现分析

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `new_product_count` | 整数 | 当年新品数量 | 首发日期在当年 |
| `total_product_count` | 整数 | 品类产品总数 | — |
| `new_product_ratio` | 浮点 | 新品占比（%） | 新品数 ÷ 产品总数 |
| `new_product_download_penetration` | 浮点 | 新品下载渗透率（%） | 新品下载合计 ÷ 品类下载合计 |
| `new_product_revenue_penetration` | 浮点 | 新品收入渗透率（%） | 同上，收入口径 |
| `new_product_download_contribution` | 浮点 | 新品对品类下载增长的贡献（%） | 新品下载增长 ÷ 品类下载增长 |
| `new_product_revenue_contribution` | 浮点 | 新品对品类收入增长的贡献（%） | 同上，收入口径 |
| `new_product_avg_rpd` | 浮点 | 新品 RPD 均值 | — |
| `new_product_avg_arpdau` | 浮点 | 新品 ARPDAU 均值 | — |
| `category_avg_rpd` / `category_avg_arpdau` | 浮点 | 全品类 RPD / ARPDAU 均值 | — |
| `new_product_rpd_premium_ratio` | 浮点 | 新品 RPD 溢价（%） | 新品 RPD 均值 ÷ 品类 RPD 均值 |

## 4. 存量产品分析

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `existing_product_count` | 整数 | 存量产品数（当年之前上线） | — |
| `mature_product_count` | 整数 | 成熟产品数（上线 1–3 年） | — |
| `decline_product_count` | 整数 | 衰退产品数（上线 3 年以上） | — |
| `existing_download_contribution` | 浮点 | 存量产品对下载增长的贡献（%） | 存量下载增长 ÷ 品类下载增长 |
| `existing_revenue_contribution` | 浮点 | 存量产品对收入增长的贡献（%） | 同上，收入口径 |
| `mature_avg_dl` / `mature_avg_rev` | 浮点 | 成熟产品平均下载 / 收入 | — |
| `mature_avg_dau_ratio` | 浮点 | 成熟产品 DAU / 下载量（%） | — |
| `decline_avg_dl` / `decline_avg_rev` | 浮点 | 衰退产品平均下载 / 收入 | — |
| `decline_avg_dau_ratio` | 浮点 | 衰退产品 DAU / 下载量（%） | — |
| `mature_product_growth_contribution_pct` | 浮点 | 成熟产品在存量增长中的占比（%） | 成熟产品下载增长 ÷ 存量下载增长 |
| `decline_product_dau_retention_ratio` | 浮点 | 衰退产品 DAU 留存（%） | 衰退产品 DAU ÷ 平均下载量 |
| `existing_product_age_growth_correlation` | 浮点 | 上线时长与下载增长的相关性 | Pearson 相关系数（−1 ~ 1） |

## 5. 聚类分析汇总

每行 = 一个品类 × 年份 × 一个命名簇。

| 字段 | 类型 | 含义 | 计算 |
|---|---|---|---|
| `sub_genre` / `game_theme`、`year` | — | 维度与年份 | — |
| `optimal_cluster_num` | 整数 | 本次聚类选定的簇数 | 由轮廓系数自动选取 |
| `silhouette_scores` | 字符串 | 各候选 K 值（2–8）对应的轮廓系数 | 形如 `[(2, 0.08), (3, 0.09), ...]`，用于查看选 K 依据 |
| `cluster_label` | 字符串 | 簇标签 | `cluster_1`、`cluster_2` … |
| `core_keywords` | 字符串 | 该簇的核心关键词（逗号分隔） | 按「簇内相对全局的对比度」提取，簇间不重复 |
| `cr3_revenue_pct` | 浮点 | 该品类当年收入 CR3（%） | 前 3 名收入 ÷ 品类收入 |
| `top3_same_cluster_count` | 整数 | 收入前 3 名中落在同一簇的产品数（1–3） | 仅在 CR3≥80% 的高垄断品类给出，其余留空 |
| `new_product_top_cluster_lift` | 浮点 | 新品向最大簇的聚集倍数 | 新品落入最大簇的比例 ÷ 全体落入该簇的比例；>1 表示新品相对更集中 |
| `product_count` | 整数 | 该簇产品数 | — |
| `total_downloads` / `avg_downloads` | 浮点 | 该簇下载合计 / 均值 | — |
| `total_revenue` / `avg_revenue` | 浮点 | 该簇收入合计 / 均值 | — |
| `avg_rpd` / `avg_arpdau` | 浮点 | 该簇 RPD / ARPDAU 均值 | — |
| `download_ratio` / `revenue_ratio` | 浮点 | 该簇占品类的下载 / 收入比重（%） | 簇合计 ÷ 品类合计 |
| `download_growth_contribution_pct` | 浮点 | 该簇对品类下载增长的贡献（%） | 簇下载增长 ÷ 品类下载增长 |

## 6. TOP10产品详情

每行 = 一个产品；下载、收入两个维度各取 Top10（同一产品可能出现两次，用 `sort_type` 区分）。

| 字段 | 类型 | 含义 |
|---|---|---|
| `product_name` | 字符串 | 产品名称 |
| `publisher_name` | 字符串 | 发行商 |
| `product_model` | 字符串 | 变现模式（如 IAP、广告） |
| `downloads_abs` / `revenue_abs` | 浮点 | 当年下载 / 收入 |
| `downloads_growth` / `revenue_growth` | 浮点 | 当年下载 / 收入同比增长值 |
| `download_contribution_pct` / `revenue_contribution_pct` | 浮点 | 该产品对品类增长的贡献（%） |
| `is_new` | 布尔 | 是否当年新品 |
| `sort_type` | 字符串 | `download` = 按下载取的前 10；`revenue` = 按收入取的前 10 |
| `sub_genre` / `game_theme`、`year` | — | 维度与年份 |

## 阅读建议

- 看**头部垄断**：`CR3_revenue_pct` / `CR5_revenue_pct` 配合 `CR*_monopoly_level`；
- 看**增长由谁带动**：`head/mid/tail_*_contribution_pct` 与 `new_product_*_contribution`；
- 看**进入空间**：`new_product_download_penetration`、`new_product_rpd_premium_ratio`；
- 看**命名与结构**：聚类表的 `core_keywords` 配合 `download_ratio` / `revenue_ratio` / `avg_rpd`，判断哪类命名框架的产品表现更好。
