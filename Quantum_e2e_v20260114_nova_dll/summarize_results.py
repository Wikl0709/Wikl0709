# -*- coding: utf-8 -*-
"""
判决结束后二次扫描，生成"场景-指标"汇总表
用法：
    python summarize_results.py --files result_v20251205_latc_python_brain.xlsx
    # 或扫整个目录
    python summarize_results.py --dir ./output
"""
import argparse
import sys
from pathlib import Path
import pandas as pd
from collections import defaultdict
import logging
import time

# 使用 loguru 作为 logger
from loguru import logger

# 场景 -> (pass列名, 总数列名,latency列名, TTFT列名)
SCENE_PASS_MAP = {
    "memory": ("Result", None, "response_time", "ttft","generation_speed"),
    "file search": ("Result", None, "response_time", "ttft","generation_speed"),
    "kbqa": ("Result", None, "response_time", "ttft","generation_speed"),
    "tool calling": ("pass", None, "response_time", "ttft","generation_speed"),
    # "memory": ("Result", None, "response_time", "first_token_time"),
    # "multimodal q&a": ("pass", None, "response_time", "first_token_time"),
    # "web search": ("Result", None, "response_time", "first_token_time"),
    # "free-chat q&a": ("Result", None, "response_time", "first_token_time"),
    # "multi-turn interactions": ("Result", None, "response_time", "first_token_time"),
}

# 在 SCENE_PASS_MAP 中不需要修改，但需要在处理逻辑中增加 domain 细分

def scan_one_excel(file_path: Path, filter_local_brain="auto"):
    """扫一个 Excel，返回 {scene: {total:int, pass:int, latency:list, TTFT:list, generation_speed:list}}"""
    logger.info(f"正在扫描文件: {file_path}")
    try:
        df = pd.read_excel(file_path, sheet_name=0)
        logger.info(f"文件包含 {len(df)} 行数据")
        # logger.info(f"文件列名: {list(df.columns)}")
        
        # 检查scene列
        if 'scene' not in df.columns:
            logger.error(f"'scene' 列不存在于文件 {file_path}")
            return {}
        
        # 显示scene列的值
        unique_scenes = df['scene'].dropna().unique()
        logger.info(f"发现的唯一场景值: {unique_scenes}")
        
    except Exception as e:
        logger.error("读取失败 %s: %s", file_path, e)
        return {}

    scene_stat = defaultdict(lambda: {"total": 0, "pass": 0, "latency": [], "TTFT": [], "generation_speed": []})
    
    for idx, row in df.iterrows():
        scene = str(row.get("scene", "")).strip().lower()
        
        # 跳过空值或NaN
        if scene in ['', 'nan', 'none', 'null']:
            continue
            
        # 标准化场景名称
        if scene == "memory question":
            scene = "memory"  # 将"memory question"映射到"memory"
        elif scene == "file-based":
            scene = "kbqa"     # 将"file-based"映射到"kbqa"
        elif scene == "file search":
            scene = "file search"  # 确保正确映射
        elif scene == "tool calling":
            scene = "tool calling"  # 确保正确映射
        elif scene == "kbqa":
            scene = "kbqa"  # 确保正确映射
        else:
            # 如果场景名称不在预定义列表中，跳过
            if scene not in SCENE_PASS_MAP:
                logger.debug(f"跳过未识别的场景: {scene}")
                continue
        
        if not scene or scene not in SCENE_PASS_MAP:
            continue

        # 特殊处理 tool calling 场景，根据 domain 细分
        if scene == "tool calling":
            domain = str(row.get("domain", "")).strip()
            if domain in ["Device setting", "App Control"]:
                scene = f"tool calling ({domain})"

        # 根据 filter_local_brain 参数决定是否过滤 "Local Brain with" 数据
        data_json_list = str(row.get("data_json_list", "")).strip()
        should_filter = "Local Brain with" in data_json_list
        
        # 根据过滤选项决定是否跳过该行
        if filter_local_brain == "yes" and should_filter:
            continue  # 跳过该行
        elif filter_local_brain == "no":
            # 不过滤，处理所有数据
            pass
        elif filter_local_brain == "auto" and should_filter:
            # 自动模式下，如果包含 "Local Brain with" 则跳过
            continue  # 跳过该行

        pass_col, _, latency_col, ttft_col, gen_speed_col = SCENE_PASS_MAP.get(
            scene.split(" (")[0] if " (" in scene else scene, 
            SCENE_PASS_MAP.get("tool calling")
        )

        # 筛选：result 不为错误值 - 只影响latency等指标，不影响total和pass统计
        result = str(row.get("result", "")).strip()
        is_error_result = result in ["CTTVError: Request Timeout", "CTTVError: Empty response from server"]

        # pass 判定
        pv = row.get(pass_col)
        is_pass = 0
        if pd.notna(pv):
            try:
                is_pass = int(float(pv))
            except (ValueError, TypeError):
                is_pass = 0

        # 总数和pass始终统计（包括错误结果）
        scene_stat[scene]["total"] += 1
        scene_stat[scene]["pass"] += is_pass

        # 只有非错误结果才统计latency、TTFT、generation_speed
        if not is_error_result:
            # latency
            if latency_col and pd.notna(row.get(latency_col)):
                try:
                    latency_val = float(row[latency_col])
                    if pd.notna(latency_val) and latency_val >= 0:  # 确保值有效
                        scene_stat[scene]["latency"].append(latency_val)
                except (ValueError, TypeError):
                    pass

            # TTFT
            if ttft_col and pd.notna(row.get(ttft_col)):
                try:
                    ttft_val = float(row[ttft_col])
                    if pd.notna(ttft_val) and ttft_val >= 0:  # 确保值有效
                        scene_stat[scene]["TTFT"].append(ttft_val)
                except (ValueError, TypeError):
                    pass
                    
            # Generation Speed
            if gen_speed_col and pd.notna(row.get(gen_speed_col)):
                try:
                    gen_speed_val = float(row[gen_speed_col])
                    if pd.notna(gen_speed_val) and gen_speed_val >= 0:  # 确保值有效
                        scene_stat[scene]["generation_speed"].append(gen_speed_val)
                except (ValueError, TypeError):
                    pass
                    
    logger.info(f"从文件 {file_path} 扫描到的场景统计: {dict(scene_stat)}")
    return scene_stat

def summarize(excel_paths: list[Path], output_path: Path = Path("summary.csv"), filter_local_brain="auto"):
    """多文件聚合汇总"""
    final = defaultdict(lambda: {"total": 0, "pass": 0, "latency": [], "TTFT": [], "generation_speed": []})

    for file_path in excel_paths:
        logger.info(f"处理文件: {file_path}")
        sub = scan_one_excel(file_path, filter_local_brain=filter_local_brain)
        logger.info(f"文件 {file_path} 扫描结果: {dict(sub)}")
        
        for scene, v in sub.items():
            final[scene]["total"] += v["total"]
            final[scene]["pass"] += v["pass"]
            final[scene]["latency"].extend(v["latency"])
            final[scene]["TTFT"].extend(v["TTFT"])
            final[scene]["generation_speed"].extend(v["generation_speed"])

    logger.info(f"聚合后的最终统计: {dict(final)}")

    # 决定是否输出 TTFT 和 Generation Speed 列
    has_ttft = any(v["TTFT"] for v in final.values())
    has_gen_speed = any(v["generation_speed"] for v in final.values())
    records = []
    
    for scene, v in final.items():
        total = v["total"]
        pass_num = v["pass"]
        
        # 计算实际参与统计的样本数（非错误结果的数量）
        actual_case_count = len(v["latency"]) if v["latency"] else 0
        
        # Pass Rate 基于 Actual #Case 计算
        rate = pass_num / actual_case_count if actual_case_count > 0 else 0
        
        avg_lat = sum(v["latency"]) / len(v["latency"]) if v["latency"] else None
        gen_speed_filtered = [speed for speed in v["generation_speed"] if speed <= 200]
        avg_gen_speed = sum(gen_speed_filtered) / len(gen_speed_filtered) if gen_speed_filtered else None
        
        row = {
            "Category": scene,
            "#Case": total,  # 原始总数（可能含被过滤的）
            "Actual #Case": actual_case_count,  # 实际参与统计的样本数（已过滤后）
            "Pass Num": pass_num,
            "Pass Rate": f"{rate:.2%}",
            "Avg Latency": round(avg_lat, 2) if avg_lat else None,
            "Avg GenSpeed(<=200)": round(avg_gen_speed, 2) if avg_gen_speed is not None and has_gen_speed else None
        }
        logger.info(f"记录行: {row}")
        
        if has_ttft:
            avg_ttft = sum(v["TTFT"]) / len(v["TTFT"]) if v["TTFT"] else None
            row["Avg TTFT"] = round(avg_ttft, 2) if avg_ttft else None
            
        records.append(row)

    # 安全处理：检查records是否为空
    if not records:
        logger.warning(f"警告: 没有找到任何有效的场景数据进行汇总，检查文件: {[str(path) for path in excel_paths]}")
        
        # 检查输入文件
        for file_path in excel_paths:
            if file_path.exists():
                try:
                    df_check = pd.read_excel(file_path)
                    logger.info(f"文件 {file_path} 包含列: {list(df_check.columns)}")
                    logger.info(f"文件 {file_path} 行数: {len(df_check)}")
                    
                    if 'scene' in df_check.columns:
                        unique_scenes = df_check['scene'].dropna().unique()
                        logger.info(f"文件 {file_path} 中的唯一场景值: {unique_scenes}")
                        
                        # 检查有多少场景能匹配到预定义场景
                        matched_scenes = [s for s in unique_scenes if str(s).lower() in SCENE_PASS_MAP]
                        unmatched_scenes = [s for s in unique_scenes if str(s).lower() not in SCENE_PASS_MAP]
                        logger.info(f"匹配的场景: {matched_scenes}")
                        logger.info(f"未匹配的场景: {unmatched_scenes}")
                        
                        # 检查是否有Result列
                        if 'Result' in df_check.columns:
                            logger.info(f"Result列前5个值: {df_check['Result'].head().tolist()}")
                        else:
                            logger.info("Result列不存在")
                            
                    else:
                        logger.error(f"文件 {file_path} 中没有 'scene' 列")
                        
                        # 尝试查找类似的列名
                        similar_cols = [col for col in df_check.columns if 'scene' in col.lower()]
                        if similar_cols:
                            logger.info(f"发现相似列名: {similar_cols}")
                except Exception as e:
                    logger.error(f"无法读取文件 {file_path}: {e}")
            else:
                logger.error(f"文件不存在: {file_path}")
        
        # 创建一个包含必需列的空DataFrame
        columns = ["Category", "#Case", "Actual #Case", "Pass Num", "Pass Rate", "Avg Latency", "Avg GenSpeed(<=200)"]
        if has_ttft:
            columns.append("Avg TTFT")
        df = pd.DataFrame(columns=columns)
    else:
        # 创建DataFrame并进行安全排序
        df = pd.DataFrame(records)
        if "Category" in df.columns:
            df = df.sort_values("Category")
        else:
            logger.error("DataFrame 中没有 'Category' 列，这不应该发生")
            # 创建一个包含必需列的空DataFrame
            columns = ["Category", "#Case", "Actual #Case", "Pass Num", "Pass Rate", "Avg Latency", "Avg GenSpeed(<=200)"]
            if has_ttft:
                columns.append("Avg TTFT")
            df = pd.DataFrame(columns=columns)
        
    logger.info("\n========== 判决结果汇总 ==========")
    if not df.empty:
        logger.info(df.to_string(index=False))
    else:
        logger.info("没有可汇总的数据")
    df.to_excel(output_path, index=False)
    logger.info(f"\n已保存 -> {output_path}")
    return df

def main():
    parser = argparse.ArgumentParser(description="判决完成后汇总各场景指标")
    parser.add_argument("--files", nargs="+", help="指定结果 Excel 文件（可多个）")
    parser.add_argument("--dir", type=str, help="扫描目录下所有 *.xlsx")
    parser.add_argument("--filter_local_brain", type=str, default="no", choices=["auto", "yes", "no"], 
                       help='是否过滤包含"Local Brain with"的数据: auto(根据test_mode自动判断), yes(总是过滤), no(从不过滤)')
    parser.add_argument("-o", "--output", help="输出汇总表文件名")
    args = parser.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    if not args.output:
        args.output = f"summary_{ts}.xlsx"

    if not args.files and not args.dir:
        logger.error("请提供 --files 或 --dir 参数")
        sys.exit(1)

    files = []
    if args.files:
        files.extend([Path(p) for p in args.files])
    if args.dir:
        files.extend(list(Path(args.dir).rglob("*.xlsx")))

    if not files:
        logger.error("未找到任何 Excel 文件")
        sys.exit(1)

    summarize(files, output_path=Path(args.output), filter_local_brain=args.filter_local_brain)


if __name__ == "__main__":
    main()


# if output_files:
#     Auto_Judge.run(args.doc_dir, output_files)
    
#     # 直接导入并调用汇总函数
#     try:
#         from summarize_results import summarize
#         # 生成输出文件名
#         from datetime import datetime
#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"summary_{timestamp}.xlsx")
        
#         # 转换文件路径为 Path 对象
#         from pathlib import Path
#         excel_paths = [Path(f) for f in output_files]
        
#         # 调用汇总函数
#         summarize(excel_paths, output_path=Path(output_path))
#         logger.info(f"指标汇总完成，结果已保存至: {output_path}")
#     except Exception as e:
#         logger.error(f"执行指标汇总时出错: {e}")