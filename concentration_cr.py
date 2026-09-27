import pandas as pd
import numpy as np
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from datetime import datetime


def load_analysis_data(file_path):
    """读取分析数据集"""
    try:
        df = pd.read_excel(file_path)
        print(f"成功读取分析数据集，数据形状: {df.shape}")

        # 列名映射（确保列名统一）
        column_mapping = {
            'Downloads (Absolute)': '下载',
            'Revenue (Absolute)': '收入',
            'Game Sub-genre': 'genre',
            'Earliest Release Date': '首发日期'
        }
        df.rename(columns=column_mapping, inplace=True)

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

        # 处理首发日期（兼容多种格式，提取年份）
        def parse_release_date(date_str):
            """兼容多种日期格式的解析函数"""
            if pd.isna(date_str) or date_str == '' or str(date_str).strip() == 'nan':
                return pd.NaT
            try:
                # 优先尝试常见格式
                date_formats = ['%Y/%m/%d', '%Y-%m-%d', '%Y.%m.%d', '%Y%m%d']
                for fmt in date_formats:
                    try:
                        return pd.to_datetime(date_str, format=fmt, errors='strict')
                    except:
                        continue
                # 最后尝试自动解析
                return pd.to_datetime(date_str, errors='coerce')
            except:
                return pd.NaT

        # 解析日期并提取精准年份
        df['首发日期_解析'] = df['首发日期'].apply(parse_release_date)
        df['首发年份_精准'] = df['首发日期_解析'].dt.year  # 保留为数值类型，便于精准对比
        df['首发日期_显示'] = df['首发日期_解析'].dt.strftime('%Y-%m-%d').fillna('未知')

        # 处理数值列
        df['下载'] = pd.to_numeric(df['下载'], errors='coerce').fillna(0).astype(int)
        df['收入'] = pd.to_numeric(df['收入'], errors='coerce').fillna(0).round().astype(int)

        # 打印关键验证信息
        print(f"\n=== 数据验证 ===")
        print(f"筛选后数据量：{len(df)} 行")
        print(f"首发年份分布：\n{df['首发年份_精准'].value_counts(dropna=False).head(10)}")

        return df

    except Exception as e:
        print(f"读取文件出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def calculate_market_share(df, country, genre, year):
    """计算市场占有率（下载CR按下载排名、收入CR按收入排名，Open World用CR4）"""
    # 严格筛选
    filtered_df = df[
        (df['国家'] == country) &
        (df['合并后品类'] == genre) &
        (df['年份'] == year)
        ].copy()

    if len(filtered_df) == 0:
        print(f"  ❌ {country}-{genre}-{year}: 无数据")
        # 根据品类返回CR4/CR5默认值
        cr_key = 'cr4' if genre == 'Open World' else 'cr5'
        return (None,
                {'total_download': 0, 'total_revenue': 0},
                {f'{cr_key}_download': 0, f'{cr_key}_revenue': 0},
                {'cr10_download': 0, 'cr10_revenue': 0})

    # ========== 分别按收入/下载量排序 ==========
    # 收入维度：按收入降序（用于收入CR计算+前10产品展示）
    sorted_by_revenue = filtered_df.sort_values('收入', ascending=False).reset_index(drop=True)
    # 下载量维度：按下载量降序（仅用于下载CR计算）
    sorted_by_download = filtered_df.sort_values('下载', ascending=False).reset_index(drop=True)

    # 精准判断当年首发（基于收入排序的列表）
    target_year = int(year)
    sorted_by_revenue['是否当年首发'] = sorted_by_revenue['首发年份_精准'] == target_year
    sorted_by_revenue['是否当年首发'] = sorted_by_revenue['是否当年首发'].fillna(False)

    # 下载排序的列表也添加当年首发标识（新增）
    sorted_by_download['是否当年首发'] = sorted_by_download['首发年份_精准'] == target_year
    sorted_by_download['是否当年首发'] = sorted_by_download['是否当年首发'].fillna(False)

    # 取前10名（收入排序）
    top10_revenue = sorted_by_revenue.head(10).copy()
    # 下载量前10（用于下载专项表）
    top10_download = sorted_by_download.head(10).copy()

    # 打印验证信息
    print(f"  ✅ {country}-{genre}-{year}: {len(filtered_df)} 行数据")
    new_products = top10_revenue[top10_revenue['是否当年首发']]
    if len(new_products) > 0:
        print(f"    当年首发产品（收入前10名内）：")
        for idx, row in new_products.iterrows():
            print(f"      - {row['Unified Name']} | 首发日期={row['首发日期_显示']} | 首发年份={row['首发年份_精准']}")
    else:
        print(f"    收入前10名内无当年首发产品")

    # ========== 按品类确定CR计算基数（Open World用CR4） ==========
    cr_base = 4 if genre == 'Open World' else 5  # CR4/CR5切换
    total_download = filtered_df['下载'].sum()
    total_revenue = filtered_df['收入'].sum()

    # 下载量CR：按下载排名取前N名（N=4/5）
    cr_download = round(
        (sorted_by_download.head(cr_base)['下载'].sum() / total_download * 100)) if total_download > 0 else 0
    # 收入CR：按收入排名取前N名（N=4/5）
    cr_revenue = round(
        (sorted_by_revenue.head(cr_base)['收入'].sum() / total_revenue * 100)) if total_revenue > 0 else 0

    # CR10计算（保持不变）
    cr10_download = round(
        (sorted_by_download.head(10)['下载'].sum() / total_download * 100)) if total_download > 0 else 0
    cr10_revenue = round((sorted_by_revenue.head(10)['收入'].sum() / total_revenue * 100)) if total_revenue > 0 else 0

    # 构造返回结果（兼容CR4/CR5字段名）
    cr_result = {
        f'cr{cr_base}_download': cr_download,
        f'cr{cr_base}_revenue': cr_revenue
    }

    return (
        top10_revenue, top10_download,  # 新增返回下载前10数据
        {'total_download': total_download, 'total_revenue': total_revenue},
        cr_result,
        {'cr10_download': cr10_download, 'cr10_revenue': cr10_revenue}
    )


def create_country_worksheet(wb, df, country, country_name):
    """创建原有收入维度工作表（适配CR4显示+下载CR计算逻辑）"""
    ws = wb.create_sheet(title=country_name)

    # 样式定义
    header_font = Font(bold=True, size=12)
    subheader_font = Font(bold=True, size=10)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')
    right_align = Alignment(horizontal='right', vertical='center')
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'),
                    bottom=Side(style='thin'))

    # 背景色
    header_fill = PatternFill(start_color='E6E6FA', end_color='E6E6FA', fill_type='solid')
    total_fill = PatternFill(start_color='F0F8FF', end_color='F0F8FF', fill_type='solid')
    cr_fill = PatternFill(start_color='F8F8FF', end_color='F8F8FF', fill_type='solid')

    # 高亮样式（精准应用）
    highlight_font = Font(bold=True, color='FF0000')  # 红色字体
    highlight_fill = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')  # 黄色背景

    # 分析维度
    genres = ['MMO', 'Idle', 'Open World', '卡牌']
    years = ['2021', '2022', '2023', '2024', '2025']
    current_row = 1

    for genre in genres:
        print(f"  📊 处理 {country_name}-{genre} 品类（收入维度）...")

        # 确定当前品类的CR基数（Open World=4，其他=5）
        cr_base = 4 if genre == 'Open World' else 5
        cr_label = f'CR{cr_base} (市场占有率)'

        # 1. 品类标题
        ws.merge_cells(f'A{current_row}:AF{current_row}')
        ws[f'A{current_row}'] = f'{genre} 品类分析（收入维度）'
        ws[f'A{current_row}'].font = Font(bold=True, size=14)
        ws[f'A{current_row}'].alignment = center_align
        current_row += 2

        # 2. 表头
        # 年份行
        for i, y in enumerate(years):
            col_start = 2 + i * 4
            ws.merge_cells(f'{chr(64 + col_start)}{current_row}:{chr(64 + col_start + 3)}{current_row}')
            ws[f'{chr(64 + col_start)}{current_row}'] = f'{y}年'
            ws[f'{chr(64 + col_start)}{current_row}'].font = header_font
            ws[f'{chr(64 + col_start)}{current_row}'].alignment = center_align
            ws[f'{chr(64 + col_start)}{current_row}'].fill = header_fill
        current_row += 1

        # 列名行
        headers = ['排名']
        for _ in years:
            headers.extend(['产品名称', '下载量', '收入', '首发日期'])
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col, value=h)
            cell.font = subheader_font
            cell.alignment = center_align
            cell.fill = header_fill
            cell.border = border
        current_row += 1

        # 3. 准备每年数据
        year_data_revenue = {}  # 收入前10
        year_data_download = {}  # 下载前10（新增）
        year_totals = {}
        year_cr = {}  # 兼容CR4/CR5
        year_cr10 = {}

        for y in years:
            top10_revenue, top10_download, totals, cr, cr10 = calculate_market_share(df, country, genre, y)
            year_data_revenue[y] = top10_revenue
            year_data_download[y] = top10_download  # 存储下载前10数据
            year_totals[y] = totals
            year_cr[y] = cr
            year_cr10[y] = cr10

        # 4. 填充前10名数据（收入排序）
        for rank in range(10):
            row_vals = [rank + 1]
            for y in years:
                top10 = year_data_revenue[y]
                if top10 is not None and rank < len(top10):
                    row = top10.iloc[rank]
                    # 提取数据
                    product_name = row['Unified Name']
                    download = row['下载']
                    revenue = row['收入']
                    release_date = row['首发日期_显示']
                    is_new = row['是否当年首发']

                    row_vals.extend([product_name, download, revenue, release_date])
                else:
                    row_vals.extend(['-', 0, 0, '未知'])

            # 写入行并应用样式
            for col_idx, val in enumerate(row_vals, 1):
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.border = border

                # 样式逻辑
                if col_idx == 1:  # 排名列
                    cell.alignment = center_align
                elif (col_idx - 2) % 4 == 0:  # 产品名称列（精准高亮）
                    cell.alignment = left_align
                    current_year = years[(col_idx - 2) // 4]
                    if (top10 is not None and rank < len(top10) and
                            year_data_revenue[current_year] is not None and
                            rank < len(year_data_revenue[current_year]) and
                            year_data_revenue[current_year].iloc[rank]['是否当年首发']):
                        cell.font = highlight_font
                        cell.fill = highlight_fill
                elif (col_idx - 4) % 4 == 0:  # 首发日期列
                    cell.alignment = center_align
                else:  # 数值列（下载/收入）
                    cell.alignment = right_align
                    if isinstance(val, (int, float)) and val != 0:
                        cell.number_format = '#,##0'

            current_row += 1

        # 5. 总量行
        total_row = ['当年总量']
        for y in years:
            totals = year_totals[y]
            total_row.extend(['', totals['total_download'], totals['total_revenue'], ''])
        for col_idx, val in enumerate(total_row, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = subheader_font
            cell.fill = total_fill
            cell.border = border
            cell.alignment = center_align if col_idx == 1 else (
                right_align if isinstance(val, (int, float)) else left_align)
            if isinstance(val, (int, float)) and val != 0:
                cell.number_format = '#,##0'
        current_row += 1

        # 6. CR行（CR4/CR5动态切换）
        cr_row = [cr_label]
        for y in years:
            cr = year_cr[y]
            cr_download = cr[f'cr{cr_base}_download']
            cr_revenue = cr[f'cr{cr_base}_revenue']
            cr_row.extend(['', f"{cr_download}%", f"{cr_revenue}%", ''])
        for col_idx, val in enumerate(cr_row, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = subheader_font
            cell.fill = cr_fill
            cell.border = border
            cell.alignment = center_align if col_idx == 1 else (right_align if '%' in str(val) else left_align)
        current_row += 1

        # 7. CR10行
        cr10_row = ['CR10 (市场占有率)']
        for y in years:
            cr10 = year_cr10[y]
            cr10_row.extend(['', f"{cr10['cr10_download']}%", f"{cr10['cr10_revenue']}%", ''])
        for col_idx, val in enumerate(cr10_row, 1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = subheader_font
            cell.fill = cr_fill
            cell.border = border
            cell.alignment = center_align if col_idx == 1 else (right_align if '%' in str(val) else left_align)
        current_row += 1

        current_row += 3  # 品类间距

    # 调整列宽
    col_widths = [6, 30, 18, 22, 15]  # 排名、产品名称、下载量、收入、首发日期
    for i, w in enumerate(col_widths, 1):
        for j in range(5):
            col = i + j * 4
            if col <= 32:
                ws.column_dimensions[chr(64 + col)].width = w


def create_download_worksheet(wb, df):
    """创建下载量维度专项分析表"""
    ws = wb.create_sheet(title="下载量专项分析", index=0)  # 放在第一个标签页

    # 样式定义（与原有样式保持一致）
    header_font = Font(bold=True, size=12)
    subheader_font = Font(bold=True, size=10)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')
    right_align = Alignment(horizontal='right', vertical='center')
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'),
                    bottom=Side(style='thin'))
    header_fill = PatternFill(start_color='E6E6FA', end_color='E6E6FA', fill_type='solid')
    total_fill = PatternFill(start_color='F0F8FF', end_color='F0F8FF', fill_type='solid')
    cr_fill = PatternFill(start_color='F8F8FF', end_color='F8F8FF', fill_type='solid')
    highlight_font = Font(bold=True, color='FF0000')
    highlight_fill = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')

    # 分析维度
    countries = [('CN', '中国'), ('US', '美国'), ('JP', '日本'), ('KR', '韩国')]
    genres = ['MMO', 'Idle', 'Open World', '卡牌']
    years = ['2021', '2022', '2023', '2024', '2025']
    current_row = 1

    # 表格标题
    ws.merge_cells(f'A{current_row}:AF{current_row}')
    ws[f'A{current_row}'] = '下载量维度专项分析（下载量排名前10 + CR数据）'
    ws[f'A{current_row}'].font = Font(bold=True, size=16)
    ws[f'A{current_row}'].alignment = center_align
    current_row += 3

    for country_code, country_name in countries:
        # 国家标题
        ws.merge_cells(f'A{current_row}:AF{current_row}')
        ws[f'A{current_row}'] = f'【{country_name}】'
        ws[f'A{current_row}'].font = Font(bold=True, size=14)
        ws[f'A{current_row}'].alignment = center_align
        current_row += 2

        for genre in genres:
            print(f"  📊 处理 {country_name}-{genre} 品类（下载维度）...")
            cr_base = 4 if genre == 'Open World' else 5
            cr_label = f'CR{cr_base} (下载量占有率)'

            # 1. 品类子标题
            ws.merge_cells(f'A{current_row}:AF{current_row}')
            ws[f'A{current_row}'] = f'{genre} 品类（下载量维度）'
            ws[f'A{current_row}'].font = Font(bold=True, size=12)
            ws[f'A{current_row}'].alignment = center_align
            current_row += 2

            # 2. 表头：年份行
            for i, y in enumerate(years):
                col_start = 2 + i * 4
                ws.merge_cells(f'{chr(64 + col_start)}{current_row}:{chr(64 + col_start + 3)}{current_row}')
                ws[f'{chr(64 + col_start)}{current_row}'] = f'{y}年'
                ws[f'{chr(64 + col_start)}{current_row}'].font = header_font
                ws[f'{chr(64 + col_start)}{current_row}'].alignment = center_align
                ws[f'{chr(64 + col_start)}{current_row}'].fill = header_fill
            current_row += 1

            # 3. 表头：列名行
            headers = ['下载排名']
            for _ in years:
                headers.extend(['产品名称', '下载量', '收入', '首发日期'])
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=current_row, column=col, value=h)
                cell.font = subheader_font
                cell.alignment = center_align
                cell.fill = header_fill
                cell.border = border
            current_row += 1

            # 4. 准备每年下载维度数据
            year_data_download = {}
            year_totals = {}
            year_cr = {}
            year_cr10 = {}

            for y in years:
                _, top10_download, totals, cr, cr10 = calculate_market_share(df, country_code, genre, y)
                year_data_download[y] = top10_download
                year_totals[y] = totals
                year_cr[y] = cr
                year_cr10[y] = cr10

            # 5. 填充下载量前10数据
            for rank in range(10):
                row_vals = [rank + 1]
                for y in years:
                    top10 = year_data_download[y]
                    if top10 is not None and rank < len(top10):
                        row = top10.iloc[rank]
                        product_name = row['Unified Name']
                        download = row['下载']
                        revenue = row['收入']
                        release_date = row['首发日期_显示']
                        is_new = row['是否当年首发']

                        row_vals.extend([product_name, download, revenue, release_date])
                    else:
                        row_vals.extend(['-', 0, 0, '未知'])

                # 写入行并应用样式
                for col_idx, val in enumerate(row_vals, 1):
                    cell = ws.cell(row=current_row, column=col_idx, value=val)
                    cell.border = border

                    # 样式逻辑
                    if col_idx == 1:  # 下载排名列
                        cell.alignment = center_align
                    elif (col_idx - 2) % 4 == 0:  # 产品名称列（高亮当年首发）
                        cell.alignment = left_align
                        current_year = years[(col_idx - 2) // 4]
                        if (top10 is not None and rank < len(top10) and
                                year_data_download[current_year] is not None and
                                rank < len(year_data_download[current_year]) and
                                year_data_download[current_year].iloc[rank]['是否当年首发']):
                            cell.font = highlight_font
                            cell.fill = highlight_fill
                    elif (col_idx - 4) % 4 == 0:  # 首发日期列
                        cell.alignment = center_align
                    else:  # 数值列
                        cell.alignment = right_align
                        if isinstance(val, (int, float)) and val != 0:
                            cell.number_format = '#,##0'

                current_row += 1

            # 6. 总量行
            total_row = ['当年下载总量']
            for y in years:
                totals = year_totals[y]
                total_row.extend(['', totals['total_download'], totals['total_revenue'], ''])
            for col_idx, val in enumerate(total_row, 1):
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.font = subheader_font
                cell.fill = total_fill
                cell.border = border
                cell.alignment = center_align if col_idx == 1 else (
                    right_align if isinstance(val, (int, float)) else left_align)
                if isinstance(val, (int, float)) and val != 0:
                    cell.number_format = '#,##0'
            current_row += 1

            # 7. CR行（仅展示下载量CR）
            cr_row = [cr_label]
            for y in years:
                cr = year_cr[y]
                cr_download = cr[f'cr{cr_base}_download']
                cr_row.extend(['', f"{cr_download}%", '', ''])  # 仅展示下载CR
            for col_idx, val in enumerate(cr_row, 1):
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.font = subheader_font
                cell.fill = cr_fill
                cell.border = border
                cell.alignment = center_align if col_idx == 1 else (right_align if '%' in str(val) else left_align)
            current_row += 1

            # 8. CR10行（仅展示下载量CR10）
            cr10_row = ['CR10 (下载量占有率)']
            for y in years:
                cr10 = year_cr10[y]
                cr10_row.extend(['', f"{cr10['cr10_download']}%", '', ''])  # 仅展示下载CR10
            for col_idx, val in enumerate(cr10_row, 1):
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.font = subheader_font
                cell.fill = cr_fill
                cell.border = border
                cell.alignment = center_align if col_idx == 1 else (right_align if '%' in str(val) else left_align)
            current_row += 1

            current_row += 3  # 品类间距
        current_row += 5  # 国家间距

    # 调整列宽
    col_widths = [8, 30, 18, 22, 15]  # 下载排名、产品名称、下载量、收入、首发日期
    for i, w in enumerate(col_widths, 1):
        for j in range(5):
            col = i + j * 4
            if col <= 32:
                ws.column_dimensions[chr(64 + col)].width = w


def generate_excel_report(df, output_path):
    """生成最终报告（包含新增的下载量专项表）"""
    wb = Workbook()
    wb.remove(wb.active)

    # 先创建下载量专项分析表（放在第一个标签）
    print("\n📝 生成下载量专项分析表...")
    create_download_worksheet(wb, df)

    # 再创建原有国家收入维度表
    countries = [('CN', '中国'), ('US', '美国'), ('JP', '日本'), ('KR', '韩国')]
    for code, name in countries:
        print(f"\n🌍 生成 {name} 收入维度工作表...")
        create_country_worksheet(wb, df, code, name)

    wb.save(output_path)
    print(f"\n✅ 报告生成完成：{output_path}")


def main():
    # 文件路径
    input_file = "data/analysis_dataset.xlsx"
    output_file = "data/RPG手游市场分析报告.xlsx"

    # 检查文件
    if not Path(input_file).exists():
        print(f"❌ 输入文件不存在：{input_file}")
        return

    # 读取数据
    print("📥 读取分析数据集...")
    df = load_analysis_data(input_file)
    if df is None:
        print("❌ 数据读取失败")
        return

    # 生成报告
    print("\n📝 生成Excel报告...")
    generate_excel_report(df, output_file)

    print("\n=== 🎉 最终报告生成完成 ===")
    print(f"📄 输出文件：{output_file}")


if __name__ == "__main__":
    main()