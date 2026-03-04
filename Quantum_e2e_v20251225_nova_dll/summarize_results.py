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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
    try:
        df = pd.read_excel(file_path, sheet_name=0)
    except Exception as e:
        logging.error("读取失败 %s: %s", file_path, e)
        return {}

    scene_stat = defaultdict(lambda: {"total": 0, "pass": 0, "latency": [], "TTFT": [], "generation_speed": []})
    
    for _, row in df.iterrows():
        scene = str(row.get("scene", "")).strip().lower()
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
                    scene_stat[scene]["latency"].append(float(row[latency_col]))
                except (ValueError, TypeError):
                    pass

            # TTFT
            if ttft_col and pd.notna(row.get(ttft_col)):
                try:
                    scene_stat[scene]["TTFT"].append(float(row[ttft_col]))
                except (ValueError, TypeError):
                    pass
                    
            # Generation Speed
            if gen_speed_col and pd.notna(row.get(gen_speed_col)):
                try:
                    scene_stat[scene]["generation_speed"].append(float(row[gen_speed_col]))
                except (ValueError, TypeError):
                    pass
                
    return scene_stat

# def summarize(excel_paths: list[Path], output_path: Path = Path("summary.csv"), filter_local_brain="auto"):
#     """多文件聚合汇总"""
#     final = defaultdict(lambda: {"total": 0, "pass": 0, "latency": [], "TTFT": [], "generation_speed": []})

#     for file_path in excel_paths:
#         sub = scan_one_excel(file_path, filter_local_brain=filter_local_brain)
#         for scene, v in sub.items():
#             final[scene]["total"] += v["total"]
#             final[scene]["pass"] += v["pass"]
#             final[scene]["latency"].extend(v["latency"])
#             final[scene]["TTFT"].extend(v["TTFT"])
#             final[scene]["generation_speed"].extend(v["generation_speed"])

#     # 决定是否输出 TTFT 和 Generation Speed 列
#     has_ttft = any(v["TTFT"] for v in final.values())
#     has_gen_speed = any(v["generation_speed"] for v in final.values())
#     records = []
#     for scene, v in final.items():
#         total = v["total"]
#         pass_num = v["pass"]
#         rate = pass_num / total if total else 0
        
#         avg_lat = sum(v["latency"]) / len(v["latency"]) if v["latency"] else None
#         gen_speed_filtered = [speed for speed in v["generation_speed"] if speed <= 200]
#         avg_gen_speed = sum(gen_speed_filtered) / len(gen_speed_filtered) if gen_speed_filtered else None
        
#         row = {
#             "Category": scene,
#             "#Case": total,  # 原始总数（可能含被过滤的）
#             "Actual #Case": total,  # 实际参与统计的样本数（已过滤后）
#             "Pass Num": pass_num,
#             "Pass Rate": f"{rate:.2%}",
#             "Avg Latency": round(avg_lat, 2) if avg_lat else None,
#             "Avg GenSpeed(<=200)": round(avg_gen_speed, 2) if avg_gen_speed is not None and has_gen_speed else None
#         }
#         print(row)
        
#         if has_ttft:
#             avg_ttft = sum(v["TTFT"]) / len(v["TTFT"]) if v["TTFT"] else None
#             row["Avg TTFT"] = round(avg_ttft, 2) if avg_ttft else None
            
#         records.append(row)

#     df = pd.DataFrame(records).sort_values("Category")
#     print("\n========== 判决结果汇总 ==========")
#     print(df.to_string(index=False))
#     df.to_excel(output_path, index=False)
#     print(f"\n已保存 -> {output_path}")
#     return df

def summarize(excel_paths: list[Path], output_path: Path = Path("summary.csv"), filter_local_brain="auto"):
    """多文件聚合汇总"""
    final = defaultdict(lambda: {"total": 0, "pass": 0, "latency": [], "TTFT": [], "generation_speed": []})

    for file_path in excel_paths:
        sub = scan_one_excel(file_path, filter_local_brain=filter_local_brain)
        for scene, v in sub.items():
            final[scene]["total"] += v["total"]
            final[scene]["pass"] += v["pass"]
            final[scene]["latency"].extend(v["latency"])
            final[scene]["TTFT"].extend(v["TTFT"])
            final[scene]["generation_speed"].extend(v["generation_speed"])

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
        print(row)
        
        if has_ttft:
            avg_ttft = sum(v["TTFT"]) / len(v["TTFT"]) if v["TTFT"] else None
            row["Avg TTFT"] = round(avg_ttft, 2) if avg_ttft else None
            
        records.append(row)

    df = pd.DataFrame(records).sort_values("Category")
    print("\n========== 判决结果汇总 ==========")
    print(df.to_string(index=False))
    df.to_excel(output_path, index=False)
    print(f"\n已保存 -> {output_path}")
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
        print("请提供 --files 或 --dir 参数")
        sys.exit(1)

    files = []
    if args.files:
        files.extend([Path(p) for p in args.files])
    if args.dir:
        files.extend(list(Path(args.dir).rglob("*.xlsx")))

    if not files:
        print("未找到任何 Excel 文件")
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