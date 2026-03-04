# -*- coding: utf-8 -*-
"""
处理测试结果文件，提取各场景的 response_time TP50 值
并按时间点生成汇总表
"""

import pandas as pd
import os
import re
from datetime import datetime
import argparse
import logging


# 配置日志记录器
def setup_logger():
    """设置并返回一个日志记录器"""
    logger = logging.getLogger(__name__)
    if not logger.handlers:  # 避免重复添加处理器
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

# 创建全局logger实例
logger = setup_logger()



# def extract_time_from_filename(filename):
#     """
#     从文件名中提取时间点，例如：
#     20251129_135959 -> 14:00 (向上取整到最近的整点)
#     匹配最靠近文件扩展名的时间戳
#     """
#     # 匹配最后出现的日期时间模式（在文件扩展名之前）
#     match = re.search(r'(\d{8})_(\d{6})(?=(_cycle\d+)?\.xlsx)', filename)
#     if match:
#         time_part = match.group(2)   # 135959
#         hour = int(time_part[:2])    # 13
#         minute = int(time_part[2:4]) # 59
        
#         # 如果分钟数大于0，则小时数加1
#         if minute > 30:
#             hour += 1
            
#         # 处理24小时制边界情况
#         if hour >= 24:
#             hour = 0
            
#         return f"{hour:02d}:00"      # 返回格式化的时间，如 "14:00"
#     return None
def extract_time_from_filename(filename):
    """
    从文件名中提取时间点，例如：
    20251129_135959 -> 2025-11-29 14:00 (包含日期和向上取整到最近的整点)
    匹配最靠近文件扩展名的时间戳
    """
    # 匹配最后出现的日期时间模式（在文件扩展名之前）
    match = re.search(r'(\d{8})_(\d{6})(?=(_cycle\d+)?\.xlsx)', filename)
    if match:
        date_part = match.group(1)   # 20251129
        time_part = match.group(2)   # 135959
        
        year = int(date_part[:4])
        month = int(date_part[4:6])
        day = int(date_part[6:8])
        
        hour = int(time_part[:2])    # 13
        minute = int(time_part[2:4]) # 59
        
        # 如果分钟数大于30，则小时数加1
        if minute > 30:
            hour += 1
            
        # 处理24小时制边界情况
        if hour >= 24:
            hour = 0
            # 日期加一天
            dt = datetime(year, month, day) + pd.Timedelta(days=1)
            year, month, day = dt.year, dt.month, dt.day
            
        return f"{year}-{month:02d}-{day:02d} {hour:02d}:00"  # 返回格式化的时间，如 "2025-11-30 14:00"
    return None
def process_result_file(filepath, output_dir="output"):
    """
    处理单个结果文件，返回该文件的时间点和各场景的 TP50 值
    """
    try:
        df = pd.read_excel(filepath, sheet_name='result')
        logger.info(f"成功加载文件: {filepath}")
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return None

    # 过滤无效响应
    valid_mask = ~df['response_time'].isin(['Error: Request Timeout', 'Error: Empty response from server'])
    df_filtered = df[valid_mask]

    # 提取时间点
    time_point = extract_time_from_filename(os.path.basename(filepath))
    if not time_point:
        logger.warning(f"无法从文件名提取时间点: {filepath}")
        return None

    # 定义目标场景列表
    categories = [
        'greeting',
        'open/close app',
        'set PC volume',
        'send an email',
        'sematic file search',
        'memory',
        'KBQA',
        'document summary',
        'image search',
        'multi-modal'
    ]

    # 计算每个场景的 TP50 (中位数)
    tp50_values = {}
    for cat in categories:
        cat_data = df_filtered[df_filtered['category'] == cat]
        if len(cat_data) > 0:
            tp50_values[cat] = cat_data['response_time'].median()
        else:
            tp50_values[cat] = None  # 或者设为 NaN

    return {
        'time': time_point,
        'tp50': tp50_values
    }


def aggregate_results(file_list, output_path):
    """
    聚合多个文件的结果，生成最终表格
    横行为时间，纵行为场景
    支持多次调用结果累加（不会覆盖）
    保持原有的场景列顺序
    """
    all_results = []

    for filepath in file_list:
        result = process_result_file(filepath)
        if result:
            all_results.append(result)

    if not all_results:
        logger.error("没有有效数据")
        return

    # 定义目标场景列表（保持固定顺序）
    categories = [
        'greeting',
        'open/close app',
        'set PC volume',
        'send an email',
        'sematic file search',
        'memory',
        'KBQA',
        'document summary',
        'image search',
        'multi-modal'
    ]

    # 创建DataFrame，以场景为索引，时间为列
    data = pd.DataFrame(index=categories)

    data = data.reindex(index=categories)  # 强制重新索引以保证顺序
    
    # 为每个时间点创建列
    for r in all_results:
        time_point = r['time']
        data[time_point] = [r['tp50'][cat] for cat in categories]

    # 检查输出文件是否已存在
    if os.path.exists(output_path):
        # 如果文件已存在，读取现有数据
        existing_data = pd.read_excel(output_path, index_col=0)
        
        # 确保现有数据的索引与我们的场景列表一致
        existing_data = existing_data.reindex(index=categories)
        
        # 合并新数据和现有数据
        combined_data = existing_data.join(data, how='outer')
        # 再次强制重新索引，防止 join 打乱顺序
        combined_data = combined_data.reindex(index=categories)
        # 保存合并后的数据，强制指定列顺序
        combined_data.to_excel(output_path, index=True, header=True)
        logger.info(f"结果已追加到: {output_path}")
    else:
        # 如果文件不存在，直接保存
        data.to_excel(output_path, index=True, header=True)
        logger.info(f"结果已保存至: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="处理多轮测试结果文件，生成 TP50 汇总表")
    parser.add_argument('--input-dir', help='输入文件夹路径，包含多个 test_results_*.xlsx 文件')
    # parser.add_argument('--input-file', help='单个输入文件路径（可选）',default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251112_nova_R19\testresult\test_results_Brain+Latency+Case+2025-11-13_nova_1124_20251129_124602_cycle1_20251129_135959.xlsx")
    parser.add_argument('--input-file', help='单个输入文件路径（可选）',default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251112_nova_R19\testresult\test_results_Brain+Latency+Case+2025-11-13_nova_1124_20251129_124602_cycle1_20251129_145959.xlsx")
    
    parser.add_argument('--output-file', help='输出 Excel 文件路径',default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251112_nova_R19\testresult\result.xlsx")


    args = parser.parse_args()

    # 获取输入文件列表
    input_files = []
    
    if args.input_file:
        # 如果指定了单个文件
        if os.path.exists(args.input_file) and args.input_file.endswith('.xlsx'):
            input_files.append(args.input_file)
        else:
            logger.error(f"输入文件不存在或不是Excel文件: {args.input_file}")
            return
    elif args.input_dir:
        # 如果指定了文件夹
        if os.path.exists(args.input_dir):
            for file in os.listdir(args.input_dir):
                if file.endswith('.xlsx') and 'test_results' in file.lower():
                    input_files.append(os.path.join(args.input_dir, file))
        else:
            logger.error(f"输入目录不存在: {args.input_dir}")
            return
    else:
        logger.error("必须指定 --input-dir 或 --input-file")
        return

    if not input_files:
        logger.error("未找到符合条件的文件")
        return

    logger.info(f"找到 {len(input_files)} 个文件待处理")

    # 聚合结果
    aggregate_results(input_files, args.output_file)


if __name__ == "__main__":
    main()