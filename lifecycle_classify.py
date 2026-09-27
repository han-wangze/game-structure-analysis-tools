import pandas as pd
import numpy as np
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from datetime import datetime


def load_analysis_data(file_path):
    """读取分析数据集（恢复原始列名以便输出）"""
    try:
        df = pd.read_excel(file_path)
        print(f"成功读取分析数据集，数据形状: {df.shape}")

        # 保留原始列名映射（仅用于过滤，不重命名原始列）
        column_mapping = {
            'Downloads (Absolute)': '下载',
            'Revenue (Absolute)': '收入',
            'Game Sub-genre': 'genre',
            'Earliest Release Date': '首发日期'
        }

        # 创建临时列用于过滤
        df['下载'] = df['Downloads (Absolute)']
        df['收入'] = df['Revenue (Absolute)']
        df['genre'] = df['Game Sub-genre']
        df['首发日期'] = df['Earliest Release Date']

        # 合并品类：只保留目标品类
        df['合并后品类'] = df['genre'].map({
            'Squad RPG': '卡牌',
            'Turn-based RPG': '卡牌',
            'MMORPG': 'MMO',
            'Idle RPG': 'Idle',
            'Open World Adventure': 'Open World'
        })

        # 过滤条件
        target_genres = ['MMO', 'Idle', 'Open World', '卡牌']
        target_countries = ['CN', 'US', 'JP', 'KR']
        target_years = ['2021', '2022', '2023', '2024', '2025']

        # 应用过滤
        df = df[df['合并后品类'].isin(target_genres)].copy()
        df = df[df['国家'].isin(target_countries)].copy()
        df['年份'] = df['年份'].astype(str)
        df = df[df['年份'].isin(target_years)].copy()

        # 处理首发日期
        def parse_release_date(date_str):
            """兼容多种日期格式的解析函数"""
            if pd.isna(date_str) or date_str == '' or str(date_str).strip() == 'nan':
                return pd.NaT
            try:
                date_formats = ['%Y/%m/%d', '%Y-%m-%d', '%Y.%m.%d', '%Y%m%d']
                for fmt in date_formats:
                    try:
                        return pd.to_datetime(date_str, format=fmt, errors='strict')
                    except:
                        continue
                return pd.to_datetime(date_str, errors='coerce')
            except:
                return pd.NaT

        # 解析日期（不修改原始列）
        df['首发日期_解析'] = df['首发日期'].apply(parse_release_date)
        df['首发年份_精准'] = df['首发日期_解析'].dt.year
        df['首发日期_显示'] = df['首发日期_解析'].dt.strftime('%Y-%m-%d').fillna('未知')

        # 处理数值列
        df['下载'] = pd.to_numeric(df['下载'], errors='coerce').fillna(0).astype(float)
        df['收入'] = pd.to_numeric(df['收入'], errors='coerce').fillna(0).astype(float)

        # 打印关键验证信息
        print(f"\n=== 数据验证 ===")
        print(f"筛选后数据量：{len(df)} 行")
        print(f"涉及国家：{df['国家'].unique()}")
        print(f"涉及年份：{df['年份'].unique()}")
        print(f"涉及品类：{df['合并后品类'].unique()}")

        return df

    except Exception as e:
        print(f"读取文件出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def get_top20_products_with_ranks(df):
    """
    按年份-国家-品类维度，获取每年各品类下载量和收入top20的产品及排名
        """
    top20_dict = {
        'download': {},  # key: (年份, 国家, 品类), value: 产品名称列表
        'revenue': {}  # key: (年份, 国家, 品类), value: 产品名称列表
    }

    rank_dict = {
        'download': {},  # key: (年份, 国家, 品类, 产品名), value: 排名
        'revenue': {}  # key: (年份, 国家, 品类, 产品名), value: 排名
    }

    # 遍历所有年份、国家、品类
    years = ['2021', '2022', '2023', '2024', '2025']
    countries = ['CN', 'US', 'JP', 'KR']
    genres = ['MMO', 'Idle', 'Open World', '卡牌']

    for year in years:
        for country in countries:
            for genre in genres:
                # 筛选当前年份-国家-品类的全量数据
                mask = (df['年份'] == year) & (df['国家'] == country) & (df['合并后品类'] == genre)
                year_country_genre_df = df[mask].copy()

                if len(year_country_genre_df) == 0:
                    print(f"⚠️ {year}-{country}-{genre} 无数据")
                    top20_dict['download'][(year, country, genre)] = []
                    top20_dict['revenue'][(year, country, genre)] = []
                    continue

                # 下载量排名（本品类内降序）
                download_sorted = year_country_genre_df.sort_values('下载', ascending=False).reset_index(drop=True)
                download_top20 = download_sorted.head(20)['Unified Name'].tolist()
                # 记录本品类内所有产品的下载排名
                for idx, row in download_sorted.iterrows():
                    rank_dict['download'][(year, country, genre, row['Unified Name'])] = idx + 1  # 排名从1开始

                # 收入排名（本品类内降序）
                revenue_sorted = year_country_genre_df.sort_values('收入', ascending=False).reset_index(drop=True)
                revenue_top20 = revenue_sorted.head(20)['Unified Name'].tolist()
                # 记录本品类内所有产品的收入排名
                for idx, row in revenue_sorted.iterrows():
                    rank_dict['revenue'][(year, country, genre, row['Unified Name'])] = idx + 1  # 排名从1开始

                top20_dict['download'][(year, country, genre)] = download_top20
                top20_dict['revenue'][(year, country, genre)] = revenue_top20

                print(f"✅ {year}-{country}-{genre} 下载量top20产品数：{len(download_top20)}")
                print(f"✅ {year}-{country}-{genre} 收入top20产品数：{len(revenue_top20)}")

    return top20_dict, rank_dict


def classify_products(df, top20_dict):
    """
    对产品进行分类：
    1. 始终在榜：2021-2025每年在本品类内下载或收入至少一项进入top20
    2. 曾经在榜：至少有一年在本品类内下载或收入进入top20，但并非每年都在榜
    3. 从未在榜：从未在本品类内进入过top20
    """
    # 存储分类结果
    product_classification = {}
    # 按产品-国家-品类维度去重
    all_product_countries_genres = df[['Unified Name', '国家', '合并后品类']].drop_duplicates()
    years = ['2021', '2022', '2023', '2024', '2025']

    for _, row in all_product_countries_genres.iterrows():
        product_name = row['Unified Name']
        country = row['国家']
        genre = row['合并后品类']

        # 记录每年是否在榜（本品类内下载或收入任一进入top20）
        yearly_status = {}
        total_years_in_top20 = 0

        for year in years:
            # 检查是否有该年份-品类数据
            year_country_genre_mask = (df['年份'] == year) & (df['国家'] == country) & \
                                      (df['合并后品类'] == genre) & (df['Unified Name'] == product_name)
            if len(df[year_country_genre_mask]) == 0:
                yearly_status[year] = '无数据'
                continue

            # 检查是否在本品类内的下载或收入top20（任一即可）
            in_download_top20 = product_name in top20_dict['download'].get((year, country, genre), [])
            in_revenue_top20 = product_name in top20_dict['revenue'].get((year, country, genre), [])

            if in_download_top20 or in_revenue_top20:
                yearly_status[year] = '在榜'
                total_years_in_top20 += 1
            else:
                yearly_status[year] = '不在榜'

        # 分类判断
        # 有数据的年份数
        years_with_data = sum(1 for v in yearly_status.values() if v != '无数据')
        # 始终在榜：所有有数据的年份都在本品类榜内
        if years_with_data > 0 and total_years_in_top20 == years_with_data:
            classification = '始终在榜'
        # 曾经在榜：至少有一年在本品类榜内，但不是所有年份都在榜
        elif total_years_in_top20 > 0:
            classification = '曾经在榜'
        # 从未在榜
        else:
            classification = '从未在榜'

        product_classification[(product_name, country, genre)] = {
            'classification': classification,
            'yearly_status': yearly_status,
            'total_years_in_top20': total_years_in_top20,
            'years_with_data': years_with_data
        }

    return product_classification


def add_rank_and_classification_columns(df, rank_dict, product_classification):
    """
    为DataFrame添加下载排名（本品类）、收入排名（本品类）、产品分类字段
    """
    df = df.copy()

    # 添加排名字段（基于年份-国家-品类-产品名获取排名）
    def get_rank(row, rank_type):
        """获取单个产品在本品类内的排名"""
        key = (row['年份'], row['国家'], row['合并后品类'], row['Unified Name'])
        return rank_dict[rank_type].get(key, np.nan)

    df['下载排名（本品类）'] = df.apply(lambda row: get_rank(row, 'download'), axis=1)
    df['收入排名（本品类）'] = df.apply(lambda row: get_rank(row, 'revenue'), axis=1)

    # 添加产品分类字段（基于产品-国家-品类维度）
    def get_classification(row):
        """获取产品在本品类内的分类"""
        key = (row['Unified Name'], row['国家'], row['合并后品类'])
        if key in product_classification:
            return product_classification[key]['classification']
        return '未知'

    # 添加年度状态字段
    def get_yearly_status(row):
        """获取该年份在本品类内的在榜状态"""
        key = (row['Unified Name'], row['国家'], row['合并后品类'])
        if key in product_classification:
            yearly_status = product_classification[key]['yearly_status']
            return yearly_status.get(row['年份'], '未知')
        return '未知'

    df['产品分类（本品类）'] = df.apply(get_classification, axis=1)
    df['年度在榜状态（本品类）'] = df.apply(get_yearly_status, axis=1)

    # 过滤：只保留始终在榜和曾经在榜的记录
    df_filtered = df[df['产品分类（本品类）'].isin(['始终在榜', '曾经在榜'])].copy()
    print(f"\n=== 数据过滤 ===")
    print(f"过滤后总数据行数：{len(df_filtered)}")
    print(f"始终在榜数据行数：{len(df_filtered[df_filtered['产品分类（本品类）'] == '始终在榜'])}")
    print(f"曾经在榜数据行数：{len(df_filtered[df_filtered['产品分类（本品类）'] == '曾经在榜'])}")

    return df_filtered


def export_target_products_data(df, output_path):
    """
    导出始终在榜和曾经在榜产品数据，包含本品类排名和分类字段
    """
    # 定义需要输出的字段顺序（更新排名字段名）
    output_columns = [
        '年份', '国家', '合并后品类', 'Unified Name', '产品分类（本品类）', '年度在榜状态（本品类）',
        '下载排名（本品类）', '收入排名（本品类）', 'RPD',
        'Downloads (Absolute)', 'Downloads (PoP Growth)', 'Downloads (PoP Growth %)',
        'Revenue (Absolute)', 'Revenue (PoP Growth)', 'Revenue (PoP Growth %)',
        'DAU (Absolute)', 'DAU (PoP Growth)', 'DAU (PoP Growth %)',
        'RPD (All Time, WW)', 'Game Sub-genre', 'Game Product Model',
        'Earliest Release Date', 'Most Popular Country by Downloads'
    ]

    # 确保列存在（处理可能的列名缺失）
    for col in output_columns:
        if col not in df.columns:
            df[col] = np.nan
            print(f"⚠️ 字段 {col} 不存在，已填充为空值")

    # 筛选出需要的列
    export_df = df[output_columns].copy()

    # 数据格式化
    # 数值列格式化
    numeric_columns = [
        'RPD', 'Downloads (Absolute)', 'Downloads (PoP Growth)', 'Downloads (PoP Growth %)',
        'Revenue (Absolute)', 'Revenue (PoP Growth)', 'Revenue (PoP Growth %)',
        'DAU (Absolute)', 'DAU (PoP Growth)', 'DAU (PoP Growth %)',
        '下载排名（本品类）', '收入排名（本品类）'
    ]

    for col in numeric_columns:
        export_df[col] = pd.to_numeric(export_df[col], errors='coerce')

    # 创建Excel文件并设置样式
    wb = Workbook()

    # 工作表1：合并数据（始终在榜+曾经在榜）
    ws_combined = wb.active
    ws_combined.title = "在榜产品合并数据（按品类排名）"

    # 工作表2：始终在榜产品
    ws_consistent = wb.create_sheet(title="始终在榜产品（按品类排名）")

    # 工作表3：曾经在榜产品
    ws_former = wb.create_sheet(title="曾经在榜产品（按品类排名）")

    # 样式定义
    header_font = Font(bold=True, size=12, color='FFFFFF')
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    center_align = Alignment(horizontal='center', vertical='center')
    border = Border(left=Side(style='thin'), right=Side(style='thin'),
                    top=Side(style='thin'), bottom=Side(style='thin'))

    # 分类样式
    consistent_fill = PatternFill(start_color='E6F3FF', end_color='E6F3FF', fill_type='solid')  # 浅蓝色（始终在榜）
    former_fill = PatternFill(start_color='FFF2E6', end_color='FFF2E6', fill_type='solid')  # 浅橙色（曾经在榜）

    # 写入数据到各个工作表
    for ws, filter_condition, sheet_name in [
        (ws_combined, None, "在榜产品合并数据（按品类排名）"),
        (ws_consistent, export_df['产品分类（本品类）'] == '始终在榜', "始终在榜产品（按品类排名）"),
        (ws_former, export_df['产品分类（本品类）'] == '曾经在榜', "曾经在榜产品（按品类排名）")
    ]:
        # 筛选数据
        if filter_condition is not None:
            sheet_df = export_df[filter_condition].copy()
        else:
            sheet_df = export_df.copy()

        print(f"\n=== {sheet_name} ===")
        print(f"数据行数：{len(sheet_df)}")
        print(f"涉及产品数：{len(sheet_df['Unified Name'].unique())}")
        print(f"涉及品类分布：{sheet_df['合并后品类'].value_counts().to_dict()}")

        # 写入表头
        for col_idx, col_name in enumerate(output_columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = border

        # 写入数据
        for row_idx, (_, row) in enumerate(sheet_df.iterrows(), 2):
            for col_idx, col_name in enumerate(output_columns, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=row[col_name])
                cell.border = border

                # 设置行背景色
                if col_idx == 1:  # 只设置一次行样式
                    if row['产品分类（本品类）'] == '始终在榜':
                        cell.fill = consistent_fill
                        ws.row_dimensions[row_idx].fill = consistent_fill
                    elif row['产品分类（本品类）'] == '曾经在榜':
                        cell.fill = former_fill
                        ws.row_dimensions[row_idx].fill = former_fill

                # 数值列右对齐，文本列左对齐
                if col_name in numeric_columns:
                    cell.alignment = Alignment(horizontal='right', vertical='center')
                    # 设置数值格式
                    if col_name.endswith('%'):
                        cell.number_format = '0.00%'
                    elif col_name in ['Downloads (Absolute)', 'Revenue (Absolute)', 'DAU (Absolute)']:
                        cell.number_format = '#,##0'
                    elif col_name in ['下载排名（本品类）', '收入排名（本品类）']:
                        cell.number_format = '0'
                else:
                    cell.alignment = Alignment(horizontal='left', vertical='center')

    # 调整列宽
    column_widths = {
        '年份': 8, '国家': 8, '合并后品类': 12, 'Unified Name': 30,
        '产品分类（本品类）': 15, '年度在榜状态（本品类）': 18,
        '下载排名（本品类）': 12, '收入排名（本品类）': 12, 'RPD': 12,
        'Downloads (Absolute)': 20, 'Downloads (PoP Growth)': 20, 'Downloads (PoP Growth %)': 20,
        'Revenue (Absolute)': 20, 'Revenue (PoP Growth)': 20, 'Revenue (PoP Growth %)': 20,
        'DAU (Absolute)': 15, 'DAU (PoP Growth)': 15, 'DAU (PoP Growth %)': 15,
        'RPD (All Time, WW)': 15, 'Game Sub-genre': 20, 'Game Product Model': 20,
        'Earliest Release Date': 15, 'Most Popular Country by Downloads': 20
    }

    for ws in [ws_combined, ws_consistent, ws_former]:
        for col_idx, col_name in enumerate(output_columns, 1):
            col_letter = chr(64 + col_idx)
            ws.column_dimensions[col_letter].width = column_widths.get(col_name, 15)

    # 保存文件
    wb.save(output_path)
    print(f"\n✅ 已导出在榜产品分析数据到：{output_path}")

    return export_df


def print_classification_summary(product_classification):
    """打印产品分类统计摘要（仅显示在榜产品，按品类维度）"""
    summary = {
        '始终在榜': 0,
        '曾经在榜': 0,
        '在榜产品总计': 0
    }

    # 按国家和品类统计
    country_summary = {}
    genre_summary = {}

    for (product, country, genre), info in product_classification.items():
        classification = info['classification']
        if classification in ['始终在榜', '曾经在榜']:
            summary[classification] += 1
            summary['在榜产品总计'] += 1

            # 按国家统计
            if country not in country_summary:
                country_summary[country] = {'始终在榜': 0, '曾经在榜': 0, '总计': 0}
            country_summary[country][classification] += 1
            country_summary[country]['总计'] += 1

            # 按品类统计
            if genre not in genre_summary:
                genre_summary[genre] = {'始终在榜': 0, '曾经在榜': 0, '总计': 0}
            genre_summary[genre][classification] += 1
            genre_summary[genre]['总计'] += 1

    print(f"\n=== 📊 在榜产品分类统计摘要（按品类排名） ===")
    print(f"在榜产品总计（按产品-国家-品类维度）：{summary['在榜产品总计']}")
    print(f"始终在榜产品数：{summary['始终在榜']} ({summary['始终在榜'] / summary['在榜产品总计'] * 100:.1f}%)")
    print(f"曾经在榜产品数：{summary['曾经在榜']} ({summary['曾经在榜'] / summary['在榜产品总计'] * 100:.1f}%)")

    print(f"\n按国家统计：")
    for country, stats in country_summary.items():
        print(f"  {country}:")
        print(f"    始终在榜：{stats['始终在榜']} 个")
        print(f"    曾经在榜：{stats['曾经在榜']} 个")
        print(f"    总计：{stats['总计']} 个")

    print(f"\n按品类统计：")
    for genre, stats in genre_summary.items():
        print(f"  {genre}:")
        print(f"    始终在榜：{stats['始终在榜']} 个")
        print(f"    曾经在榜：{stats['曾经在榜']} 个")
        print(f"    总计：{stats['总计']} 个")


def main():
    # 文件路径配置
    input_file = "data/analysis_dataset.xlsx"
    output_file = "data/在榜产品分析_按品类排名.xlsx"

    # 检查输入文件
    if not Path(input_file).exists():
        print(f"❌ 输入文件不存在：{input_file}")
        return

    # 1. 读取并预处理数据
    print("📥 读取分析数据集...")
    df = load_analysis_data(input_file)
    if df is None:
        print("❌ 数据读取失败")
        return

    # 2. 获取每年各国家-品类的top20产品及排名（按品类排名）
    print("\n📊 计算每年各国家-品类下载量和收入top20产品及排名...")
    top20_dict, rank_dict = get_top20_products_with_ranks(df)

    # 3. 产品分类（按品类维度）
    print("\n🎯 产品分类分析（按品类维度）...")
    product_classification = classify_products(df, top20_dict)

    # 4. 添加排名和分类字段，并过滤出在榜产品
    print("\n📝 添加品类排名和分类字段，过滤在榜产品...")
    df_filtered = add_rank_and_classification_columns(df, rank_dict, product_classification)

    if df_filtered.empty:
        print("⚠️ 未找到任何在榜产品数据")
        return

    # 5. 导出结果
    print("\n💾 导出分析结果...")
    export_df = export_target_products_data(df_filtered, output_file)

    # 6. 打印统计信息
    print_classification_summary(product_classification)

    # 打印按品类的详细产品列表
    for genre in ['MMO', 'Idle', 'Open World', '卡牌']:
        genre_df = export_df[export_df['合并后品类'] == genre]
        if len(genre_df) == 0:
            continue

        print(f"\n=== 📋 {genre}品类 - 始终在榜产品列表 ===")
        consistent_products = genre_df[genre_df['产品分类（本品类）'] == '始终在榜'][
            ['国家', 'Unified Name']].drop_duplicates()
        for _, row in consistent_products.iterrows():
            print(f"  {row['国家']} - {row['Unified Name']}")

        print(f"\n=== 📋 {genre}品类 - 曾经在榜产品列表 ===")
        former_products = genre_df[genre_df['产品分类（本品类）'] == '曾经在榜'][
            ['国家', 'Unified Name']].drop_duplicates()
        for _, row in former_products.iterrows():
            print(f"  {row['国家']} - {row['Unified Name']}")

    print("\n=== 🎉 分析完成 ===")
    print(f"📄 输出文件：{output_file}")


if __name__ == "__main__":
    main()