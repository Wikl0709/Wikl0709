# -*- coding: utf-8 -*-
"""
判决结束后二次扫描，生成“场景-指标”汇总表
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

def scan_one_excel(file_path: Path):
    """扫一个 Excel，返回 {scene: {total:int, pass:int, latency:list, TTFT:list, generation_speed:list}}"""
    try:
        df = pd.read_excel(file_path, sheet_name=0)
    except Exception as e:
        logging.error("读取失败 %s: %s", file_path, e)
        return {}

    # 修改统计结构，支持 tool calling 的 domain 细分
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

        pass_col, _, latency_col, ttft_col, gen_speed_col = SCENE_PASS_MAP.get(
            scene.split(" (")[0] if " (" in scene else scene, 
            SCENE_PASS_MAP.get("tool calling")  # 默认使用 tool calling 的配置
        )

        # pass 判定
        pv = row.get(pass_col)
        is_pass = 0
        if pd.notna(pv):
            try:
                is_pass = int(float(pv))
            except (ValueError, TypeError):
                is_pass = 0

        # 记录
        scene_stat[scene]["total"] += 1
        scene_stat[scene]["pass"] += is_pass

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

# def scan_one_excel(file_path: Path):
#     """扫一个 Excel，返回 {scene: {total:int, pass:int, latency:list, TTFT:list, generation_speed:list}}"""
#     try:
#         df = pd.read_excel(file_path, sheet_name=0)
#     except Exception as e:
#         logging.error("读取失败 %s: %s", file_path, e)
#         return {}

#     scene_stat = defaultdict(lambda: {"total": 0, "pass": 0, "latency": [], "TTFT": [], "generation_speed": []})
#     for _, row in df.iterrows():
#         scene = str(row.get("scene", "")).strip().lower()
#         if not scene or scene not in SCENE_PASS_MAP:
#             continue

#         pass_col, _, latency_col, ttft_col, gen_speed_col = SCENE_PASS_MAP[scene]

#         # pass 判定
#         pv = row.get(pass_col)
#         is_pass = 0
#         if pd.notna(pv):
#             try:
#                 is_pass = int(float(pv))
#             except (ValueError, TypeError):
#                 is_pass = 0

#         # 记录
#         scene_stat[scene]["total"] += 1
#         scene_stat[scene]["pass"] += is_pass

#         # latency
#         if latency_col and pd.notna(row.get(latency_col)):
#             try:
#                 scene_stat[scene]["latency"].append(float(row[latency_col]))
#             except (ValueError, TypeError):
#                 pass

#         # TTFT
#         if ttft_col and pd.notna(row.get(ttft_col)):
#             try:
#                 scene_stat[scene]["TTFT"].append(float(row[ttft_col]))
#             except (ValueError, TypeError):
#                 pass
                
#         # Generation Speed
#         if gen_speed_col and pd.notna(row.get(gen_speed_col)):
#             try:
#                 scene_stat[scene]["generation_speed"].append(float(row[gen_speed_col]))
#             except (ValueError, TypeError):
#                 pass
#     return scene_stat


def summarize(excel_paths: list[Path], output_path: Path = Path("summary.csv")):
    """多文件聚合汇总"""
    final = defaultdict(lambda: {"total": 0, "pass": 0, "latency": [], "TTFT": [], "generation_speed": []})

    for file_path in excel_paths:
        sub = scan_one_excel(file_path)
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
        rate = pass_num / total if total else 0
        
        # 计算平均延迟
        avg_lat = sum(v["latency"]) / len(v["latency"]) if v["latency"] else None
        
        # 计算 generation_speed <= 200 的平均值
        gen_speed_filtered = [speed for speed in v["generation_speed"] if speed <= 200]
        avg_gen_speed = sum(gen_speed_filtered) / len(gen_speed_filtered) if gen_speed_filtered else None
        
        row = {
            "Category": scene,
            "#Case": total,
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

    summarize(files, output_path=Path(args.output))


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