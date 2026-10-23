import pandas as pd
import numpy as np
import os
import re
from datetime import datetime
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings('ignore')


# ======================== 配置参数（可根据需求调整）========================
class Config:
    # 文件路径配置
    DATA_FOLDER = "data"  # 存放CSV文件的文件夹路径
    OUTPUT_FOLDER = "data"  # 分析结果输出路径
    # 时间配置（5年分析，可根据需要调整年份）
    ANALYSIS_YEARS = [2021, 2022, 2023, 2024, 2025]  # 5年数据
    # 分析维度：sub_genre=品类（源列 Game Sub-genre）／game_theme=题材（源列 Game Theme）
    DIMENSION = "sub_genre"
    # 分层阈值配置
    HEAD_RATIO = 0.4  # 头部占比阈值（40%）
    MID_RATIO = 0.7  # 中腰部占比阈值（70%）
    CR_THRESHOLDS = [3, 5, 10]  # CR3/CR5/CR10
    FLUCTUATION_THRESHOLD = 0.5  # 大幅波动阈值（50%）
    # 内存配置（针对5年大数据量）
    CHUNK_SIZE = 10000  # 分块读取大小
    SAMPLE_RATIO = 1.0  # 采样比例（1.0为全量分析，小于1为抽样）


# ======================== 通用工具函数 =========================
def safe_division(numerator, denominator, default=0):
    """
    安全除法：避免除数为零和Series布尔判断歧义
    """
    if isinstance(numerator, pd.Series) and isinstance(denominator, pd.Series):
        return numerator.div(denominator.replace(0, 1)).fillna(default)
    elif isinstance(denominator, pd.Series):
        return numerator / denominator.replace(0, 1)
    elif isinstance(numerator, pd.Series):
        return numerator / (denominator if denominator != 0 else 1)
    else:
        return numerator / denominator if denominator != 0 else default


def calculate_top10_contribution(genre_df, year):
    """
    计算TOP10产品的下载/收入双维度贡献率
    """
    # 动态定义新品
    new_product_date = pd.to_datetime(f"{year}-01-01")
    next_year_date = pd.to_datetime(f"{year + 1}-01-01")
    genre_df['is_new'] = ((genre_df['release_date'] >= new_product_date) &
                          (genre_df['release_date'] < next_year_date)).fillna(False)

    # 计算品类总增长值（避免除0）
    total_dl_growth = genre_df['downloads_growth'].sum() or 1
    total_rev_growth = genre_df['revenue_growth'].sum() or 1

    # 按下载量排序TOP10
    df_download_sorted = genre_df.sort_values('downloads_abs', ascending=False).reset_index(drop=True)
    top10_dl = df_download_sorted.head(10).copy()
    top10_dl['download_contribution_pct'] = round(
        safe_division(top10_dl['downloads_growth'], total_dl_growth) * 100, 2
    )
    top10_dl['revenue_contribution_pct'] = round(
        safe_division(top10_dl['revenue_growth'], total_rev_growth) * 100, 2
    )
    top10_dl['sort_type'] = 'download'

    # 按收入排序TOP10
    df_revenue_sorted = genre_df.sort_values('revenue_abs', ascending=False).reset_index(drop=True)
    top10_rev = df_revenue_sorted.head(10).copy()
    top10_rev['revenue_contribution_pct'] = round(
        safe_division(top10_rev['revenue_growth'], total_rev_growth) * 100, 2
    )
    top10_rev['download_contribution_pct'] = round(
        safe_division(top10_rev['downloads_growth'], total_dl_growth) * 100, 2
    )
    top10_rev['sort_type'] = 'revenue'

    # 合并双维度TOP10，统一字段
    top10_combined = pd.concat([top10_dl, top10_rev], ignore_index=True)[
        ['product_name', 'publisher_name', 'product_model',
         'downloads_abs', 'revenue_abs',
         'downloads_growth', 'revenue_growth',
         'download_contribution_pct', 'revenue_contribution_pct',
         'is_new', 'sort_type']
    ]

    return top10_combined


# ======================== 扩展分析工具函数 =========================
def calculate_pearson_correlation(series1, series2):
    """计算两个序列的Pearson相关系数（处理空值）"""
    df = pd.DataFrame({'x': series1, 'y': series2}).dropna()
    if len(df) < 2:
        return 0
    return df['x'].corr(df['y'])


# ======================== 吸量效率分析工具函数 =========================
def calculate_acquisition_efficiency(df, year):
    """
    计算产品/品类吸量效率核心指标（适配年度颗粒度）
    """
    efficiency_results = {}

    # 1. 品类平均吸量效率
    total_products = len(df) or 1
    efficiency_results['category_avg_acquisition'] = round(safe_division(df['downloads_abs'].sum(), total_products), 2)

    # 2. 新品吸量效率
    new_product_date = pd.to_datetime(f"{year}-01-01")
    next_year_date = pd.to_datetime(f"{year + 1}-01-01")
    new_df = df[((df['release_date'] >= new_product_date) & (df['release_date'] < next_year_date))].copy()
    new_product_count = len(new_df) or 1
    efficiency_results['new_product_avg_acquisition'] = round(
        safe_division(new_df['downloads_abs'].sum(), new_product_count), 2)

    # 3. 分层吸量效率（头部/中腰部/尾部）
    df_download_sorted = df.sort_values('downloads_abs', ascending=False).reset_index(drop=True)
    total_dl = df_download_sorted['downloads_abs'].sum() or 1
    df_download_sorted['downloads_cum_pct'] = df_download_sorted['downloads_abs'].cumsum() / total_dl

    # 头部（前40%）
    head_df = df_download_sorted[df_download_sorted['downloads_cum_pct'] <= Config.HEAD_RATIO]
    head_count = len(head_df) or 1
    efficiency_results['head_avg_acquisition'] = round(safe_division(head_df['downloads_abs'].sum(), head_count), 2)

    # 中腰部（40%-70%）
    mid_df = df_download_sorted[(df_download_sorted['downloads_cum_pct'] > Config.HEAD_RATIO) &
                                (df_download_sorted['downloads_cum_pct'] <= Config.MID_RATIO)]
    mid_count = len(mid_df) or 1
    efficiency_results['mid_avg_acquisition'] = round(safe_division(mid_df['downloads_abs'].sum(), mid_count), 2)

    # 尾部（70%后）
    tail_df = df_download_sorted[df_download_sorted['downloads_cum_pct'] > Config.MID_RATIO]
    tail_count = len(tail_df) or 1
    efficiency_results['tail_avg_acquisition'] = round(safe_division(tail_df['downloads_abs'].sum(), tail_count), 2)

    # 4. 吸量增长效率（年度下载增长值/上线时长）
    df['release_days'] = df['release_date'].apply(lambda x: get_product_lifecycle_days(x, year))
    df['acquisition_growth_efficiency'] = safe_division(df['downloads_growth'], df['release_days'])
    efficiency_results['avg_acquisition_growth_efficiency'] = round(df['acquisition_growth_efficiency'].mean(), 4)

    # 5. 吸量留存效率（DAU/下载量）
    df['acquisition_retention_efficiency'] = safe_division(df['dau_abs'], df['downloads_abs']) * 100
    efficiency_results['avg_acquisition_retention_efficiency'] = round(df['acquisition_retention_efficiency'].mean(), 2)

    # 6. 吸量变现效率（RPD）
    efficiency_results['avg_acquisition_monetization_efficiency'] = round(df['rpd'].mean(), 4)

    return efficiency_results


def get_product_lifecycle_days(release_date, analysis_year):
    """计算产品上线时长（天）"""
    if pd.isna(release_date):
        return 0
    end_date = pd.to_datetime(f"{analysis_year}-12-31")
    return (end_date - release_date).days


# ======================== 数据预处理函数 =========================
def preprocess_data(file_path):
    """
    数据预处理：加载CSV文件并统一字段格式
    """
    try:
        # 分块读取大文件（适配5年大数据量）
        df_chunks = []
        for chunk in pd.read_csv(file_path, sep='\t', encoding='utf-16', on_bad_lines='skip',
                                 chunksize=Config.CHUNK_SIZE):
            df_chunks.append(chunk)
        df = pd.concat(df_chunks, ignore_index=True)
    except:
        try:
            df_chunks = []
            for chunk in pd.read_csv(file_path, sep='\t', encoding='utf-8', on_bad_lines='skip',
                                     chunksize=Config.CHUNK_SIZE):
                df_chunks.append(chunk)
            df = pd.concat(df_chunks, ignore_index=True)
        except:
            df_chunks = []
            for chunk in pd.read_csv(file_path, sep='\t', encoding='gbk', on_bad_lines='skip',
                                     chunksize=Config.CHUNK_SIZE):
                df_chunks.append(chunk)
            df = pd.concat(df_chunks, ignore_index=True)

    # 采样（可选）
    if Config.SAMPLE_RATIO < 1.0:
        df = df.sample(frac=Config.SAMPLE_RATIO, random_state=42)

    print(f"文件 {os.path.basename(file_path)} 的原始列名：{df.columns.tolist()}")

    # 统一字段名
    df.columns = df.columns.str.strip().str.lower()
    column_mapping = {
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
        "most popular country by downloads": "core_country",
        "downloads (absolute)": "downloads_abs",
        "downloads (pop growth)": "downloads_growth",
        "downloads (pop growth %)": "downloads_growth_pct",
        "revenue (absolute)": "revenue_abs",
        "revenue (pop growth)": "revenue_growth",
        "revenue (pop growth %)": "revenue_growth_pct",
        "dau (absolute)": "dau_abs",
        "dau (pop growth)": "dau_growth",
        "dau (pop growth %)": "dau_growth_pct",
        "rpd (all time, ww)": "rpd",
        "arpdau (last month, us)": "arpdau",
        "publisher country": "publisher_country"
    }
    existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
    df.rename(columns=existing_mapping, inplace=True)

    # 检查并创建缺失列
    required_cols = ['date', 'release_date', 'downloads_abs', 'revenue_abs', 'dau_abs',
                     'rpd', 'arpdau', 'sub_genre']
    for col in required_cols:
        if col not in df.columns:
            print(f"警告：文件 {os.path.basename(file_path)} 缺少 {col} 列，创建空列")
            df[col] = np.nan

    # 维度列统一：内部固定用 sub_genre 承载维度值，取值来自配置的分析维度列
    dim_col = Config.DIMENSION
    if dim_col not in df.columns:
        print(f"警告：文件 {os.path.basename(file_path)} 缺少 {dim_col} 列，创建空列")
        df[dim_col] = np.nan
    df['sub_genre'] = df[dim_col]

    # 数据类型转换
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['release_date'] = pd.to_datetime(df['release_date'], errors='coerce')

    # 处理金额和百分比字段
    for col in ['rpd', 'arpdau']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace('$', '').str.replace(',', ''),
                                    errors='coerce').fillna(0)

    pct_cols = ['downloads_growth_pct', 'revenue_growth_pct', 'dau_growth_pct']
    for col in pct_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace('%', ''), errors='coerce').fillna(0) / 100

    # 处理数值型缺失值
    numeric_cols = ['downloads_abs', 'revenue_abs', 'dau_abs', 'rpd', 'arpdau',
                    'downloads_growth', 'revenue_growth', 'dau_growth']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['core_country'] = df['core_country'].fillna('Unknown') if 'core_country' in df.columns else 'Unknown'
    df['analysis_year'] = pd.to_numeric(df['date'].dt.year.fillna(0), errors='coerce').astype(int)

    # 从文件名补充年份（适配5年数据）
    file_name = os.path.basename(file_path)
    year_pattern = r'202[0-9]'  # 匹配2020-2029年
    year_match = re.search(year_pattern, file_name)
    if year_match and df['analysis_year'].isna().all():
        df['analysis_year'] = int(year_match.group())

    return df


def load_all_data(data_folder):
    """加载并合并所有 CSV 文件"""
    all_data = []
    csv_files = [f for f in os.listdir(data_folder) if f.endswith('.csv')]

    if not csv_files:
        print(f"警告：在 {data_folder} 中未找到CSV文件")
        return pd.DataFrame()

    # 筛选包含分析年份的文件
    year_strs = [str(year) for year in Config.ANALYSIS_YEARS]
    filtered_files = []
    for filename in csv_files:
        if any(year in filename for year in year_strs):
            filtered_files.append(filename)

    if not filtered_files:
        print(f"警告：未找到包含{Config.ANALYSIS_YEARS}年份的CSV文件")
        return pd.DataFrame()

    print(f"找到 {len(filtered_files)} 个包含目标年份的CSV文件")

    for filename in filtered_files:
        file_path = os.path.join(data_folder, filename)
        try:
            df = preprocess_data(file_path)
            # 过滤只保留分析年份的数据
            df = df[df['analysis_year'].isin(Config.ANALYSIS_YEARS)]
            all_data.append(df)
            print(f"成功加载：{filename}，数据行数：{len(df)}")
        except Exception as e:
            print(f"加载文件 {filename} 失败：{str(e)}")
            continue

    if not all_data:
        print("警告：没有成功加载任何数据文件")
        return pd.DataFrame()

    merged_df = pd.concat(all_data, ignore_index=True)
    print(f"数据合并完成，总记录数：{len(merged_df)}")

    # 内存压缩
    merged_df = merged_df.drop_duplicates()
    for col in merged_df.select_dtypes(include=['float64']).columns:
        merged_df[col] = merged_df[col].astype('float32')
    for col in merged_df.select_dtypes(include=['int64']).columns:
        merged_df[col] = merged_df[col].astype('int32')

    return merged_df


# ======================== 1. 集中度分析模块 ========================
def concentration_analysis(df, sub_genre, year):
    """
    单品类单年份的集中度分析（含 TOP10 双维度贡献 + 头部增长韧性字段）
    """
    genre_df = df[(df['sub_genre'] == sub_genre) & (df['analysis_year'] == year)].copy()
    if len(genre_df) == 0:
        print(f"警告：{sub_genre} - {year}年 无数据")
        return None

    total_downloads = genre_df['downloads_abs'].sum()
    total_revenue = genre_df['revenue_abs'].sum()
    if total_downloads == 0 and total_revenue == 0:
        print(f"警告：{sub_genre} - {year}年 下载量和收入数据全部为0，跳过该品类分析")
        return None

    analysis_results = {
        "sub_genre": sub_genre,
        "year": year,
        "total_products": len(genre_df)
    }

    # 动态定义新品
    new_product_date = pd.to_datetime(f"{year}-01-01")
    next_year_date = pd.to_datetime(f"{year + 1}-01-01")
    genre_df['is_new'] = ((genre_df['release_date'] >= new_product_date) &
                          (genre_df['release_date'] < next_year_date)).fillna(False)

    # 按下载量/收入排序
    df_download_sorted = genre_df.sort_values('downloads_abs', ascending=False).reset_index(drop=True)
    total_dl = df_download_sorted['downloads_abs'].sum()
    df_download_sorted['downloads_cum_pct'] = df_download_sorted[
                                                  'downloads_abs'].cumsum() / total_dl if total_dl > 0 else 0

    df_revenue_sorted = genre_df.sort_values('revenue_abs', ascending=False).reset_index(drop=True)
    total_rev = df_revenue_sorted['revenue_abs'].sum()
    df_revenue_sorted['revenue_cum_pct'] = df_revenue_sorted['revenue_abs'].cumsum() / total_rev if total_rev > 0 else 0

    # 1. CR3/CR5/CR10 计算
    for cr in Config.CR_THRESHOLDS:
        cr_count = min(cr, len(df_download_sorted))
        cr_dl_sum = df_download_sorted.head(cr_count)['downloads_abs'].sum()
        cr_dl_pct = round(safe_division(cr_dl_sum, total_dl) * 100, 2)

        cr_rev_count = min(cr, len(df_revenue_sorted))
        cr_rev_sum = df_revenue_sorted.head(cr_rev_count)['revenue_abs'].sum()
        cr_rev_pct = round(safe_division(cr_rev_sum, total_rev) * 100, 2)

        analysis_results[f'CR{cr}_download_pct'] = cr_dl_pct
        analysis_results[f'CR{cr}_revenue_pct'] = cr_rev_pct

        # 垄断程度判断
        if cr_rev_pct >= 80:
            analysis_results[f'CR{cr}_monopoly_level'] = "高垄断"
        elif 40 <= cr_rev_pct < 80:
            analysis_results[f'CR{cr}_monopoly_level'] = "中垄断"
        else:
            analysis_results[f'CR{cr}_monopoly_level'] = "低垄断"

    # 2. 头部/中腰部/尾部 层级贡献率
    total_dl_growth = df_download_sorted['downloads_growth'].sum() or 1
    total_rev_growth = df_revenue_sorted['revenue_growth'].sum() or 1

    # 下载分层
    dl_filtered = df_download_sorted[df_download_sorted['downloads_cum_pct'] <= Config.HEAD_RATIO]
    head_dl_idx = dl_filtered.index[-1] if len(dl_filtered) > 0 else 0
    mid_dl_filtered = df_download_sorted[(df_download_sorted['downloads_cum_pct'] > Config.HEAD_RATIO) &
                                         (df_download_sorted['downloads_cum_pct'] <= Config.MID_RATIO)]
    mid_dl_idx = mid_dl_filtered.index[-1] if len(mid_dl_filtered) > 0 else head_dl_idx

    # 收入分层
    rev_filtered = df_revenue_sorted[df_revenue_sorted['revenue_cum_pct'] <= Config.HEAD_RATIO]
    head_rev_idx = rev_filtered.index[-1] if len(rev_filtered) > 0 else 0
    mid_rev_filtered = df_revenue_sorted[(df_revenue_sorted['revenue_cum_pct'] > Config.HEAD_RATIO) &
                                         (df_revenue_sorted['revenue_cum_pct'] <= Config.MID_RATIO)]
    mid_rev_idx = mid_rev_filtered.index[-1] if len(mid_rev_filtered) > 0 else head_rev_idx

    # 下载层级贡献
    head_dl_contribution = df_download_sorted.head(head_dl_idx + 1)['downloads_growth'].sum()
    analysis_results['head_download_contribution_pct'] = round(
        safe_division(head_dl_contribution, total_dl_growth) * 100, 2)
    mid_dl_contribution = df_download_sorted.iloc[head_dl_idx + 1:mid_dl_idx + 1]['downloads_growth'].sum()
    analysis_results['mid_download_contribution_pct'] = round(safe_division(mid_dl_contribution, total_dl_growth) * 100,
                                                              2)
    tail_dl_contribution = df_download_sorted.iloc[mid_dl_idx + 1:]['downloads_growth'].sum()
    analysis_results['tail_download_contribution_pct'] = round(
        safe_division(tail_dl_contribution, total_dl_growth) * 100, 2)

    # 收入层级贡献
    head_rev_contribution = df_revenue_sorted.head(head_rev_idx + 1)['revenue_growth'].sum()
    analysis_results['head_revenue_contribution_pct'] = round(
        safe_division(head_rev_contribution, total_rev_growth) * 100, 2)
    mid_rev_contribution = df_revenue_sorted.iloc[head_rev_idx + 1:mid_rev_idx + 1]['revenue_growth'].sum()
    analysis_results['mid_revenue_contribution_pct'] = round(
        safe_division(mid_rev_contribution, total_rev_growth) * 100, 2)
    tail_rev_contribution = df_revenue_sorted.iloc[mid_rev_idx + 1:]['revenue_growth'].sum()
    analysis_results['tail_revenue_contribution_pct'] = round(
        safe_division(tail_rev_contribution, total_rev_growth) * 100, 2)

    # 3. TOP10产品双维度贡献计算
    top10_products = calculate_top10_contribution(genre_df, year)
    analysis_results['top10_products'] = top10_products
    analysis_results['top10_download_products'] = top10_products[top10_products['sort_type'] == 'download']
    analysis_results['top10_revenue_products'] = top10_products[top10_products['sort_type'] == 'revenue']

    # 兼容原有字段（避免报错）
    analysis_results['top10_download_products']['single_contribution_pct'] = \
        analysis_results['top10_download_products']['download_contribution_pct']

    # ======================== 头部增长韧性分析字段 ========================
    # 1. head3_download_growth_variance：头部3产品年度下载增长值方差（适配年度颗粒度）
    head3_df = df_download_sorted.head(3)
    if len(head3_df) >= 2:
        # 改为使用年度下载增长值（而非月度增长率）
        head3_growth_values = head3_df['downloads_growth'].dropna()
        if len(head3_growth_values) >= 2:
            variance = round(head3_growth_values.var(), 4)
        else:
            variance = 0
    else:
        variance = 0
    analysis_results['head3_download_growth_variance'] = variance

    # 2. top1_vs_top2_download_gap_ratio：TOP1与TOP2年度下载量差距比（无修改，已适配年度）
    if len(df_download_sorted) >= 2:
        top1_dl = df_download_sorted.iloc[0]['downloads_abs']
        top2_dl = df_download_sorted.iloc[1]['downloads_abs']
        gap_ratio = round(safe_division((top1_dl - top2_dl), top2_dl) * 100, 2)
    else:
        gap_ratio = 0
    analysis_results['top1_vs_top2_download_gap_ratio'] = gap_ratio

    # 3. head3_maturity_ratio：头部3产品中成熟产品占比（无修改，已适配年度）
    head3_df['release_days'] = head3_df['release_date'].apply(lambda x: get_product_lifecycle_days(x, year))
    head3_mature_count = len(head3_df[head3_df['release_days'].between(365, 1095)])  # 1-3年为成熟产品
    head3_maturity_ratio = round(safe_division(head3_mature_count, 3) * 100, 2)
    analysis_results['head3_maturity_ratio'] = head3_maturity_ratio

    # ======================== 吸量效率分析字段 ========================
    # 调用吸量效率计算函数
    acquisition_efficiency = calculate_acquisition_efficiency(genre_df, year)
    # 合并吸量效率结果到分析结果中
    analysis_results.update(acquisition_efficiency)

    # ======================== 分层变现效率差异分析字段 ========================
    # 1. head_download_revenue_conversion_ratio：头部产品单位下载收入转化效率
    head_df = df_download_sorted.head(head_dl_idx + 1)
    head_rev = head_df['revenue_abs'].sum()
    head_dl = head_df['downloads_abs'].sum()
    category_rev = genre_df['revenue_abs'].sum()
    category_dl = genre_df['downloads_abs'].sum()

    head_conversion = safe_division(head_rev, head_dl)
    category_conversion = safe_division(category_rev, category_dl)
    conversion_ratio = round(safe_division(head_conversion, category_conversion) * 100, 2)
    analysis_results['head_download_revenue_conversion_ratio'] = conversion_ratio

    # 2. mid_tail_rpd_gap：中腰部与尾部产品平均RPD差距
    mid_df = df_download_sorted.iloc[head_dl_idx + 1:mid_dl_idx + 1]
    tail_df = df_download_sorted.iloc[mid_dl_idx + 1:]
    mid_avg_rpd = mid_df['rpd'].mean() if len(mid_df) > 0 else 0
    tail_avg_rpd = tail_df['rpd'].mean() if len(tail_df) > 0 else 0
    analysis_results['mid_tail_rpd_gap'] = round(mid_avg_rpd - tail_avg_rpd, 4)

    return analysis_results


# ======================== 2. 新品表现分析模块 ========================
def new_product_analysis(df, sub_genre, year):
    """新品表现分析（含变现溢价字段）"""
    genre_df = df[(df['sub_genre'] == sub_genre) & (df['analysis_year'] == year)].copy()
    if len(genre_df) == 0:
        print(f"警告：{sub_genre} - {year}年 无数据，跳过新品分析")
        return None

    total_downloads = genre_df['downloads_abs'].sum()
    total_revenue = genre_df['revenue_abs'].sum()
    if total_downloads == 0 and total_revenue == 0:
        print(f"警告：{sub_genre} - {year}年 无有效业务数据，跳过新品分析")
        return None

    new_product_date = pd.to_datetime(f"{year}-01-01")
    next_year_date = pd.to_datetime(f"{year + 1}-01-01")
    genre_df['is_new'] = ((genre_df['release_date'] >= new_product_date) &
                          (genre_df['release_date'] < next_year_date)).fillna(False)
    six_month_ago = pd.to_datetime(f"{year}-01-01") - pd.Timedelta(days=180)
    genre_df['is_super_new'] = (genre_df['release_date'] >= six_month_ago).fillna(False)
    new_df = genre_df[genre_df['is_new']].copy()
    total_df = genre_df.copy()

    results = {
        "sub_genre": sub_genre,
        "year": year,
        "new_product_count": len(new_df),
        "total_product_count": len(total_df),
        "new_product_ratio": round(safe_division(len(new_df), len(total_df)) * 100, 2)
    }

    # 新品渗透率
    new_dl = new_df['downloads_abs'].sum()
    total_dl = total_df['downloads_abs'].sum()
    new_rev = new_df['revenue_abs'].sum()
    total_rev = total_df['revenue_abs'].sum()

    results['new_product_download_penetration'] = round(safe_division(new_dl, total_dl) * 100, 2)
    results['new_product_revenue_penetration'] = round(safe_division(new_rev, total_rev) * 100, 2)

    # 新品贡献率
    new_dl_growth = new_df['downloads_growth'].sum()
    total_dl_growth = total_df['downloads_growth'].sum()
    new_rev_growth = new_df['revenue_growth'].sum()
    total_rev_growth = total_df['revenue_growth'].sum()

    results['new_product_download_contribution'] = round(safe_division(new_dl_growth, total_dl_growth) * 100, 2)
    results['new_product_revenue_contribution'] = round(safe_division(new_rev_growth, total_rev_growth) * 100, 2)

    # TOP10新品
    if len(new_df) > 0:
        top10_new = new_df.sort_values('downloads_abs', ascending=False).head(10)[
            ['product_name', 'publisher_name', 'product_model', 'downloads_abs',
             'revenue_abs', 'rpd', 'arpdau', 'core_country']
        ].copy()
        avg_rpd = total_df['rpd'].mean()
        avg_arpdau = total_df['arpdau'].mean()
        top10_new['rpd_vs_avg'] = top10_new['rpd'] - avg_rpd
        top10_new['arpdau_vs_avg'] = top10_new['arpdau'] - avg_arpdau
        results['top10_new_products'] = top10_new
        results['new_product_avg_rpd'] = round(new_df['rpd'].mean(), 2)
        results['new_product_avg_arpdau'] = round(new_df['arpdau'].mean(), 2)
        results['category_avg_rpd'] = round(avg_rpd, 2)
        results['category_avg_arpdau'] = round(avg_arpdau, 2)

        # ======================== new_product_rpd_premium_ratio 新品RPD溢价率 ========================
        new_product_rpd_premium = round(safe_division(results['new_product_avg_rpd'], avg_rpd) * 100, 2)
        results['new_product_rpd_premium_ratio'] = new_product_rpd_premium
    else:
        results['top10_new_products'] = pd.DataFrame()
        results['new_product_avg_rpd'] = 0
        results['new_product_avg_arpdau'] = 0
        results['new_product_rpd_premium_ratio'] = 0

    return results


# ======================== 3. 存量产品表现分析模块 ========================
def existing_product_analysis(df, sub_genre, year):
    """存量产品表现分析（含衰退产品 DAU 比率 + 生命周期细分字段）"""
    genre_df = df[(df['sub_genre'] == sub_genre) & (df['analysis_year'] == year)].copy()
    if len(genre_df) == 0:
        print(f"警告：{sub_genre} - {year}年 无数据，跳过量产品分析")
        return None

    total_downloads = genre_df['downloads_abs'].sum()
    total_revenue = genre_df['revenue_abs'].sum()
    if total_downloads == 0 and total_revenue == 0:
        print(f"警告：{sub_genre} - {year}年 无有效业务数据，跳过量产品分析")
        return None

    new_product_date = pd.to_datetime(f"{year}-01-01")
    genre_df['is_existing'] = (genre_df['release_date'] < new_product_date).fillna(False)
    existing_df = genre_df[genre_df['is_existing']].copy()

    # 生命周期分层
    current_date = pd.to_datetime(f"{year}-12-31")
    genre_df['release_days'] = (current_date - genre_df['release_date']).dt.days.fillna(0)

    def get_life_cycle(days):
        if pd.isna(days) or days < 0:
            return '未知'
        elif days < 365:
            return '新品'
        elif days < 1095:
            return '成熟产品'
        else:
            return '衰退产品'

    genre_df['life_cycle'] = genre_df['release_days'].apply(get_life_cycle)

    results = {
        "sub_genre": sub_genre,
        "year": year,
        "existing_product_count": len(existing_df),
        "mature_product_count": len(genre_df[genre_df['life_cycle'] == '成熟产品']),
        "decline_product_count": len(genre_df[genre_df['life_cycle'] == '衰退产品'])
    }

    # 存量贡献率
    existing_dl_growth = existing_df['downloads_growth'].sum()
    total_dl_growth = genre_df['downloads_growth'].sum()
    existing_rev_growth = existing_df['revenue_growth'].sum()
    total_rev_growth = genre_df['revenue_growth'].sum()

    results['existing_download_contribution'] = round(safe_division(existing_dl_growth, total_dl_growth) * 100, 2)
    results['existing_revenue_contribution'] = round(safe_division(existing_rev_growth, total_rev_growth) * 100, 2)

    # TOP10存量产品
    if len(existing_df) > 0:
        top10_existing = existing_df.sort_values('revenue_abs', ascending=False).head(10)[
            ['product_name', 'publisher_name', 'product_model', 'downloads_abs',
             'revenue_abs', 'dau_abs', 'dau_growth_pct', 'rpd', 'arpdau']
        ].copy()

        top10_existing['dau_download_ratio'] = round(
            safe_division(top10_existing['dau_abs'], top10_existing['downloads_abs']) * 100, 2)

        results['top10_existing_products'] = top10_existing

        # 生命周期分层表现
        mature_df = genre_df[genre_df['life_cycle'] == '成熟产品']
        decline_df = genre_df[genre_df['life_cycle'] == '衰退产品']

        results['mature_avg_dl'] = round(mature_df['downloads_abs'].mean(), 2) if len(mature_df) > 0 else 0
        results['mature_avg_rev'] = round(mature_df['revenue_abs'].mean(), 2) if len(mature_df) > 0 else 0

        if len(mature_df) > 0:
            mature_dau_ratio = safe_division(mature_df['dau_abs'], mature_df['downloads_abs']).mean()
            results['mature_avg_dau_ratio'] = round(mature_dau_ratio * 100, 2)
        else:
            results['mature_avg_dau_ratio'] = 0

        results['decline_avg_dl'] = round(decline_df['downloads_abs'].mean(), 2) if len(decline_df) > 0 else 0
        results['decline_avg_rev'] = round(decline_df['revenue_abs'].mean(), 2) if len(decline_df) > 0 else 0

        # 衰退产品DAU/下载量比率
        if len(decline_df) > 0:
            decline_dau_ratio = safe_division(decline_df['dau_abs'], decline_df['downloads_abs']).mean()
            results['decline_avg_dau_ratio'] = round(decline_dau_ratio * 100, 2)
        else:
            results['decline_avg_dau_ratio'] = 0

        # ======================== 存量生命周期细分字段 ========================
        # 1. mature_product_growth_contribution_pct：成熟产品对存量增长的贡献占比
        mature_dl_growth = mature_df['downloads_growth'].sum() if len(mature_df) > 0 else 0
        existing_total_dl_growth = existing_df['downloads_growth'].sum() or 1
        mature_contribution = round(safe_division(mature_dl_growth, existing_total_dl_growth) * 100, 2)
        results['mature_product_growth_contribution_pct'] = mature_contribution

        # 2. decline_product_dau_retention_ratio：衰退产品DAU留存率（相对上线首年）
        # 简化计算：用当前DAU / 衰退产品平均下载量 * 100（替代首年DAU）
        if len(decline_df) > 0:
            decline_current_dau = decline_df['dau_abs'].mean()
            decline_avg_dl = decline_df['downloads_abs'].mean()
            decline_dau_retention = round(safe_division(decline_current_dau, decline_avg_dl) * 100, 2)
        else:
            decline_dau_retention = 0
        results['decline_product_dau_retention_ratio'] = decline_dau_retention

        # 3. existing_product_age_growth_correlation：存量产品年龄与年度下载增长值的相关系数（适配年度）
        existing_df['release_days'] = (current_date - existing_df['release_date']).dt.days.fillna(0)
        # 改为使用年度下载增长值（而非增长率）
        age_growth_corr = calculate_pearson_correlation(existing_df['release_days'],
                                                        existing_df['downloads_growth'])
        results['existing_product_age_growth_correlation'] = round(age_growth_corr, 4)

    else:
        results['top10_existing_products'] = pd.DataFrame()
        results['decline_avg_dau_ratio'] = 0
        # 字段默认值
        results['mature_product_growth_contribution_pct'] = 0
        results['decline_product_dau_retention_ratio'] = 0
        results['existing_product_age_growth_correlation'] = 0

    return results


# ======================== 结果输出与可视化 ========================
def _rename_dimension_column(df):
    """输出时把内部维度列 sub_genre 改名为当前配置的维度列名"""
    return df.rename(columns={'sub_genre': Config.DIMENSION})


def save_analysis_results(all_results, output_folder):
    """保存分析结果到 Excel 文件"""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    def filter_none_results(results_list):
        return [res for res in results_list if res is not None]

    # 整合集中度分析结果
    concentration_data = []
    for res in filter_none_results(all_results['concentration']):
        simplified_res = {k: v for k, v in res.items() if not isinstance(v, pd.DataFrame)}
        concentration_data.append(simplified_res)

    # 收集TOP10产品数据
    top_products_data = []
    for res in filter_none_results(all_results['concentration']):
        if 'top10_products' in res and not res['top10_products'].empty:
            top10_df = res['top10_products'].copy()
            top10_df['sub_genre'] = res['sub_genre']
            top10_df['year'] = res['year']
            top_products_data.append(top10_df)

    # 保存主报告
    try:
        with pd.ExcelWriter(os.path.join(output_folder, "game_category_analysis_report_5years.xlsx"),
                            engine='openpyxl') as writer:
            # 集中度分析
            if concentration_data:
                _rename_dimension_column(pd.DataFrame(concentration_data)).to_excel(writer, sheet_name='集中度分析', index=False)

            # 吸量效率分析
            acquisition_data = []
            for res in filter_none_results(all_results['concentration']):
                # 提取吸量效率相关字段
                acquisition_res = {
                    'sub_genre': res['sub_genre'],
                    'year': res['year'],
                    'category_avg_acquisition': res.get('category_avg_acquisition', 0),
                    'new_product_avg_acquisition': res.get('new_product_avg_acquisition', 0),
                    'head_avg_acquisition': res.get('head_avg_acquisition', 0),
                    'mid_avg_acquisition': res.get('mid_avg_acquisition', 0),
                    'tail_avg_acquisition': res.get('tail_avg_acquisition', 0),
                    'avg_acquisition_growth_efficiency': res.get('avg_acquisition_growth_efficiency', 0),
                    'avg_acquisition_retention_efficiency': res.get('avg_acquisition_retention_efficiency', 0),
                    'avg_acquisition_monetization_efficiency': res.get('avg_acquisition_monetization_efficiency', 0)
                }
                acquisition_data.append(acquisition_res)
            if acquisition_data:
                _rename_dimension_column(pd.DataFrame(acquisition_data)).to_excel(writer, sheet_name='吸量效率分析', index=False)

            # 新品表现分析
            new_product_data = []
            for res in filter_none_results(all_results['new_product']):
                simplified_res = {k: v for k, v in res.items() if not isinstance(v, pd.DataFrame)}
                new_product_data.append(simplified_res)
            if new_product_data:
                _rename_dimension_column(pd.DataFrame(new_product_data)).to_excel(writer, sheet_name='新品表现分析', index=False)

            # 存量产品分析
            existing_product_data = []
            for res in filter_none_results(all_results['existing_product']):
                simplified_res = {k: v for k, v in res.items() if not isinstance(v, pd.DataFrame)}
                existing_product_data.append(simplified_res)
            if existing_product_data:
                _rename_dimension_column(pd.DataFrame(existing_product_data)).to_excel(writer, sheet_name='存量产品分析', index=False)

# TOP10产品详情（含双维度贡献率）
            if top_products_data:
                _rename_dimension_column(pd.concat(top_products_data, ignore_index=True)).to_excel(writer, sheet_name='TOP10产品详情',
                                                                         index=False)

        print(f"5年分析结果已保存至：{output_folder}/game_category_analysis_report_5years.xlsx")
    except Exception as e:
        print(f"保存Excel文件失败：{str(e)}")


def plot_concentration_chart(all_results, output_folder):
    """绘制 CR5 集中度可视化图表"""
    cr5_data = []
    for res in all_results['concentration']:
        if res and 'CR5_revenue_pct' in res:
            cr5_data.append({
                'sub_genre': res['sub_genre'],
                'year': res['year'],
                'cr5': res['CR5_revenue_pct']
            })
    cr5_df = pd.DataFrame(cr5_data)

    if len(cr5_df) == 0:
        print("警告：没有CR5数据可绘制图表")
        return

    try:
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.figure(figsize=(18, 10))

        years = sorted(cr5_df['year'].unique())
        subgenres = sorted(cr5_df['sub_genre'].unique())
        x = np.arange(len(subgenres))
        width = 0.15  # 调整柱宽适配5年数据
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']  # 5种颜色

        # 绘制多年份对比柱状图
        for i, year in enumerate(years):
            year_data = []
            for sg in subgenres:
                val = cr5_df[(cr5_df['sub_genre'] == sg) & (cr5_df['year'] == year)]['cr5'].values
                year_data.append(val[0] if len(val) > 0 else 0)

            offset = width * (i - len(years) / 2 + 0.5)
            plt.bar(x + offset, year_data, width, label=f"{int(year)}年", color=colors[i % len(colors)])

        plt.xticks(x, subgenres, rotation=45, ha='right')
        plt.title('各子品类CR5收入集中度5年对比', fontsize=14)
        plt.xlabel('子品类', fontsize=12)
        plt.ylabel('CR5收入占比（%）', fontsize=12)
        plt.legend(loc='upper right')
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(output_folder, "cr5_concentration_5years.png"), dpi=300, bbox_inches='tight')
        plt.close()
        print("5年CR5集中度图表已保存")
    except Exception as e:
        print(f"绘制图表失败：{str(e)}")


def plot_acquisition_efficiency_chart(all_results, output_folder):
    """绘制吸量效率可视化图表"""
    acquisition_data = []
    for res in all_results['concentration']:
        if res and 'category_avg_acquisition' in res:
            acquisition_data.append({
                'sub_genre': res['sub_genre'],
                'year': res['year'],
                'avg_acquisition': res['category_avg_acquisition'],
                'head_acquisition': res['head_avg_acquisition'],
                'new_product_acquisition': res['new_product_avg_acquisition']
            })
    acquisition_df = pd.DataFrame(acquisition_data)

    if len(acquisition_df) == 0:
        print("警告：没有吸量效率数据可绘制图表")
        return

    try:
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.figure(figsize=(18, 10))

        years = sorted(acquisition_df['year'].unique())
        subgenres = sorted(acquisition_df['sub_genre'].unique())
        x = np.arange(len(subgenres))
        width = 0.15
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

        # 绘制5年吸量效率对比
        for i, year in enumerate(years):
            year_data = []
            for sg in subgenres:
                val = acquisition_df[(acquisition_df['sub_genre'] == sg) & (acquisition_df['year'] == year)][
                    'avg_acquisition'].values
                year_data.append(val[0] if len(val) > 0 else 0)

            offset = width * (i - len(years) / 2 + 0.5)
            plt.bar(x + offset, year_data, width, label=f"{int(year)}年", color=colors[i % len(colors)])

        plt.xticks(x, subgenres, rotation=45, ha='right')
        plt.title('各子品类平均吸量效率5年对比', fontsize=14)
        plt.xlabel('子品类', fontsize=12)
        plt.ylabel('平均下载量/产品', fontsize=12)
        plt.legend(loc='upper right')
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(output_folder, "acquisition_efficiency_5years.png"), dpi=300, bbox_inches='tight')
        plt.close()
        print("5年吸量效率图表已保存")
    except Exception as e:
        print(f"绘制吸量效率图表失败：{str(e)}")


# ======================== 主函数 =========================
def main():
    print("=" * 50)
    print("开始执行游戏品类数据分析程序（5年数据版）")
    print(f"分析年份：{Config.ANALYSIS_YEARS}")
    print("=" * 50)

    print("\n1. 加载数据...")
    df = load_all_data(Config.DATA_FOLDER)

    if df.empty:
        print("错误：没有加载到任何有效数据，程序终止")
        return

    print(f"\n数据加载完成，共{len(df)}条记录")

    all_results = {
        "concentration": [],
        "new_product": [],
        "existing_product": []
    }

    unique_sub_genres = df['sub_genre'].dropna().unique()
    if len(unique_sub_genres) == 0:
        print("错误：数据中没有有效的子品类信息，程序终止")
        return

    print(f"\n2. 发现 {len(unique_sub_genres)} 个子品类：")
    for idx, sg in enumerate(unique_sub_genres, 1):
        print(f"   {idx}. {sg}")

    print("\n3. 开始分析数据...")
    print("-" * 50)

    # 分批处理（避免内存溢出）
    batch_size = 5  # 每次分析5个子品类
    for i in range(0, len(unique_sub_genres), batch_size):
        batch_subgenres = unique_sub_genres[i:i + batch_size]
        print(f"\n处理第 {i // batch_size + 1} 批子品类：{batch_subgenres}")

        for sub_genre in batch_subgenres:
            for year in Config.ANALYSIS_YEARS:
                print(f"  正在分析：{sub_genre} - {year}年")
                concen_res = concentration_analysis(df, sub_genre, year)
                all_results['concentration'].append(concen_res)
                new_prod_res = new_product_analysis(df, sub_genre, year)
                all_results['new_product'].append(new_prod_res)
                existing_prod_res = existing_product_analysis(df, sub_genre, year)
                all_results['existing_product'].append(existing_prod_res)

    print("\n" + "-" * 50)
    print("4. 保存分析结果...")
    save_analysis_results(all_results, Config.OUTPUT_FOLDER)

    print("\n5. 生成可视化图表...")
    plot_concentration_chart(all_results, Config.OUTPUT_FOLDER)
    plot_acquisition_efficiency_chart(all_results, Config.OUTPUT_FOLDER)

    print("\n" + "=" * 50)
    print(f"5年数据分析完成！结果已保存至 {Config.OUTPUT_FOLDER}")
    print("=" * 50)


if __name__ == "__main__":
    main()