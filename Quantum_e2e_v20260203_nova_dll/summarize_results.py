# -*- coding: utf-8 -*-
# name: summarize_results.py
# author: weiyb2
# date: 2026-01-29
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
import time
import math
from loguru import logger

#==================================================
# 场景 -> (pass列名, 总数列名, latency列名, TTFT列名, generation_speed列名)
SCENE_PASS_MAP = {
    "memory": ("Result", None, "response_time", "ttft", "generation_speed"),
    "file search": ("Result", None, "response_time", "ttft", "generation_speed"),
    "kbqa": ("Result", None, "response_time", "ttft", "generation_speed"),
    "tool calling": ("pass", None, "response_time", "ttft", "generation_speed"),
}
#==================================================


def scan_one_excel(file_path: Path, filter_local_brain="auto"):
    """
    扫一个 Excel，返回 {scene: {total:int, pass:int, latency:list, TTFT:list, generation_speed:list}}
    """
    logger.info(f"正在扫描文件: {file_path}")
    try:
        df = pd.read_excel(file_path, sheet_name=0)
        logger.info(f"文件包含 {len(df)} 行数据")
        if 'scene' not in df.columns:
            logger.error(f"'scene' 列不存在于文件 {file_path}")
            return {}
        unique_scenes = df['scene'].dropna().unique()
        logger.info(f"发现的唯一场景值: {unique_scenes}")
    except Exception as e:
        logger.error("读取失败 %s: %s", file_path, e)
        return {}

    scene_stat = defaultdict(lambda: {
        "total": 0,
        "result_pass": 0,
        "tool_check": 0,
        "retrieval_check": 0,
        "final_answer": 0,
        "latency": [],
        "ttft": [],
        "completion": [],
        "memory_ingestion_success": 0,  # Memory ingestion 成功的数量
        "valid_case": 0,  #（memory_ingestion_success=Y 且 result 正常）
        "valid_pass": 0,   # result_pass=1 的数量
        "valid_ttft": [],  # Memory场景有效注册成功的Case的TTFT
        "valid_completion": [],  # Memory场景有效Case的Completion列表
        "valid_tool_check": 0,      # 新增：有效的Tool_Check数量
        "valid_retrieval_check": 0, # 新增：有效的Retrieval_Check数量
        "valid_final_answer": 0     # 新增：有效的Final Answer数量
    })

    for idx, row in df.iterrows():
        scene = str(row.get("scene", "")).strip().lower()
        if scene in ['', 'nan', 'none', 'null']:
            continue
        if scene == "memory question":
            scene = "memory"
        elif scene == "file-based":
            scene = "kbqa"
        elif scene == "file search":
            scene = "file search"
        elif scene == "tool calling":
            scene = "tool calling"
        else:
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

        # 过滤 Local Brain with 数据，在云端会调用 Local Brain 的场景
        data_json_list = str(row.get("data_json_list", "")).strip()
        should_filter = "Local Brain with" in data_json_list
        if filter_local_brain == "yes" and should_filter:
            continue
        elif filter_local_brain == "auto" and should_filter:
            continue

        pass_col, _, latency_col, ttft_col, gen_speed_col = SCENE_PASS_MAP.get(
            scene.split(" (")[0] if " (" in scene else scene,
            SCENE_PASS_MAP.get("tool calling")
        )

        # 筛选错误结果（超时等CTTV相关的case）
        result = str(row.get("result", "")).strip()
        is_error_result = (
            result in ["CTTVError: Request Timeout", "CTTVError: Empty response from server"]
            or str(result).startswith("CTTVError: Task failed -")
        )

        tool_check = int(row.get("Tool_Check", 0)) if pd.notna(row.get("Tool_Check")) else 0
        retrieval_check = int(row.get("Retrieval_Check", 0)) if pd.notna(row.get("Retrieval_Check")) else 0
        result_val = int(row.get(pass_col, 0)) if pd.notna(row.get(pass_col)) else 0

        # 对 memory 场景特殊处理：不过滤 is_error_result
        if scene == "memory":
            memory_reg_success = str(row.get("Memory_reg_success", "")).strip().upper()
            is_valid_ingestion = memory_reg_success in ["Y", "YES", "TRUE"]

            # 总数无条件累加（不管 result 是否异常）
            scene_stat[scene]["total"] += 1
            scene_stat[scene]["memory_ingestion_success"] += is_valid_ingestion

            # 仅在非异常情况下统计 valid_case 和 valid_pass
            if not is_error_result and is_valid_ingestion:
                scene_stat[scene]["valid_case"] += 1
                if result_val == 1:
                    scene_stat[scene]["valid_pass"] += 1

                # 收集 TTFT 和 Completion
                if ttft_col and pd.notna(row.get(ttft_col)):
                    try:
                        val = float(row[ttft_col])
                        if pd.notna(val) and val >= 0:
                            scene_stat[scene]["valid_ttft"].append(val)
                    except (ValueError, TypeError):
                        pass

                if latency_col and pd.notna(row.get(latency_col)):
                    try:
                        val = float(row[latency_col])
                        if pd.notna(val) and val >= 0:
                            scene_stat[scene]["valid_completion"].append(val)
                    except (ValueError, TypeError):
                        pass

                # 工具链检查
                if tool_check == 1:
                    scene_stat[scene]["valid_tool_check"] += 1
                if tool_check == 1 and retrieval_check == 1:
                    scene_stat[scene]["valid_retrieval_check"] += 1
                if tool_check == 1 and retrieval_check == 1 and result_val == 1:
                    scene_stat[scene]["valid_final_answer"] += 1

        # 其他场景按原逻辑处理
        elif not is_error_result:
            scene_stat[scene]["total"] += 1
            scene_stat[scene]["result_pass"] += result_val
            scene_stat[scene]["tool_check"] += tool_check
            scene_stat[scene]["retrieval_check"] += (tool_check and retrieval_check)
            scene_stat[scene]["final_answer"] += (tool_check and retrieval_check and result_val)

            # latency
            if latency_col and pd.notna(row.get(latency_col)):
                try:
                    val = float(row[latency_col])
                    if pd.notna(val) and val >= 0:
                        scene_stat[scene]["latency"].append(val)
                except (ValueError, TypeError):
                    pass

            # TTFT
            if ttft_col and pd.notna(row.get(ttft_col)):
                try:
                    val = float(row[ttft_col])
                    if pd.notna(val) and val >= 0:
                        scene_stat[scene]["ttft"].append(val)
                except (ValueError, TypeError):
                    pass

            # Completion
            if latency_col and pd.notna(row.get(latency_col)):
                try:
                    val = float(row[latency_col])
                    if pd.notna(val) and val >= 0:
                        scene_stat[scene]["completion"].append(val)
                except (ValueError, TypeError):
                    pass

    return scene_stat


def scan_kb_file_ingestion(dir_path: Path):
    """
    扫描 testresult 目录下所有 document_registration_ 开头的 Excel 文件，
    计算 KB File Ingestion 的指标
    """
    kb_ingestion_dir = dir_path / "testresult"
    if not kb_ingestion_dir.exists():
        logger.warning(f"未找到 testresult 目录: {kb_ingestion_dir}")
        return {"total": 0, "completed": 0, "total_gap_time": []}

    files = [f for f in kb_ingestion_dir.rglob("document_registration_*.xlsx") if f.is_file()]
    if not files:
        logger.info("未找到 document_registration_ 开头的文件")
        return {"total": 0, "completed": 0, "total_gap_time": []}
    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    total_count = 0
    completed_count = 0
    gap_times = []

    for file_path in [latest_file]:
        logger.info(f"扫描 KB File Ingestion 文件: {file_path}")
        try:
            df = pd.read_excel(file_path, sheet_name="Data")
            if "id" not in df.columns or "status" not in df.columns or "total_gap_time" not in df.columns:
                logger.warning(f"文件 {file_path} 缺少必要列")
                continue

            total_count += len(df)
            completed_count += (df["status"] == "COMPLETED").sum()

            valid_times = df["total_gap_time"].dropna().astype(float)
            gap_times.extend(valid_times.tolist())

        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")

    avg_completion = sum(gap_times) / len(gap_times) if gap_times else None
    return {
        "total": total_count,
        "completed": completed_count,
        "completion": round(avg_completion, 2) if avg_completion is not None else None
    }


def scan_memory_ingestion_latency(dir_path: Path):
    """
    扫描 args.dir 下所有包含 'Memory_data_with_responses_' 的 xlsx 文件，
    计算 user_content_1_response_time 的平均值
    """
    memory_files = [f for f in dir_path.rglob("*Memory_data_with_responses_*.xlsx") if f.is_file()]
    if not memory_files:
        logger.warning("未找到 Memory_data_with_responses_ 开头的文件")
        return None

    all_times = []
    latest_file = max(memory_files, key=lambda f: f.stat().st_mtime)
    for file_path in [latest_file]:
        logger.info(f"扫描 Memory Ingestion 延迟文件: {file_path}")
        try:
            df = pd.read_excel(file_path, sheet_name=0)
            if "user_content_1_response_time" not in df.columns:
                logger.warning(f"文件 {file_path} 缺少 user_content_1_response_time 列")
                continue
            times = df["user_content_1_response_time"].dropna().astype(float)
            all_times.extend(times.tolist())
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")

    if not all_times:
        return None

    avg_latency = sum(all_times) / len(all_times)
    return round(avg_latency, 2)


def summarize(excel_paths: list[Path], output_path: Path = Path("summary.csv"), filter_local_brain="auto", dir_path: Path = None):

    """多文件聚合汇总"""
    final = defaultdict(lambda: {
        "total": 0,
        "result_pass": 0,
        "tool_check": 0,
        "retrieval_check": 0,
        "final_answer": 0,
        "latency": [],
        "ttft": [],
        "completion": [],
        "memory_ingestion_success": 0,
        "valid_case": 0,
        "valid_pass": 0,
        "valid_ttft": [],
        "valid_completion": [],
        "valid_tool_check": 0,
        "valid_retrieval_check": 0,
        "valid_final_answer": 0
    })

    for file_path in excel_paths:
        logger.info(f"处理文件: {file_path}")
        sub = scan_one_excel(file_path, filter_local_brain=filter_local_brain)
        for scene, v in sub.items():
            final[scene]["total"] += v["total"]
            final[scene]["result_pass"] += v["result_pass"]
            final[scene]["tool_check"] += v["tool_check"]
            final[scene]["retrieval_check"] += v["retrieval_check"]
            final[scene]["final_answer"] += v["final_answer"]
            final[scene]["latency"].extend(v["latency"])
            final[scene]["ttft"].extend(v["ttft"])
            final[scene]["completion"].extend(v["completion"])
            final[scene]["memory_ingestion_success"] += v["memory_ingestion_success"]
            final[scene]["valid_case"] += v["valid_case"]
            final[scene]["valid_pass"] += v["valid_pass"]
            final[scene]["valid_ttft"].extend(v["valid_ttft"])
            final[scene]["valid_completion"].extend(v["valid_completion"])
            final[scene]["valid_tool_check"] += v["valid_tool_check"]
            final[scene]["valid_retrieval_check"] += v["valid_retrieval_check"]
            final[scene]["valid_final_answer"] += v["valid_final_answer"]

    records = []

    category_map = {
        "file search": "File Search",
        "kbqa": "KB QA",
        "memory": "Memory QA",
        "tool calling": "Tool Calling",
        "tool calling (Device setting)": "Tool Calling (Device setting)",
        "tool calling (App Control)": "Tool Calling (App Control)"
    }

    for scene, v in final.items():
        total = v["total"]
        if total == 0:
            continue

        display_category = category_map.get(scene, scene)
        e2e_ratio = v["result_pass"] / total if total > 0 else 0
        tool_calling_ratio = v["tool_check"] / total if total > 0 else 0
        retrieval_ratio = v["retrieval_check"] / v["tool_check"] if v["tool_check"] > 0 else 0
        final_answer_ratio = v["final_answer"] / v["retrieval_check"] if v["retrieval_check"] > 0 else 0
        avg_ttft = sum(v["ttft"]) / len(v["ttft"]) if v["ttft"] and len(v["ttft"]) > 0 else None
        avg_completion = sum(v["completion"]) / len(v["completion"]) if v["completion"] and len(v["completion"]) > 0 else None

        # 处理 NaN/inf
        if avg_ttft is not None:
            if math.isnan(avg_ttft) or math.isinf(avg_ttft):
                avg_ttft = None
        if avg_completion is not None:
            if math.isnan(avg_completion) or math.isinf(avg_completion):
                avg_completion = None

        row = {
            "Category": display_category,
            "# Case": total,
            "E2E": f"{v['result_pass']}/{total}={e2e_ratio:.1%}",
            "Tool Calling": f"{v['tool_check']}/{total}={tool_calling_ratio:.1%}",
            "Retrieval": f"{v['retrieval_check']}/{v['tool_check']}={retrieval_ratio:.1%}" if v["tool_check"] > 0 else "--",
            "Final Answer": f"{v['final_answer']}/{v['retrieval_check']}={final_answer_ratio:.1%}" if v["retrieval_check"] > 0 else "--",
            "TTFT": round(avg_ttft, 2) if avg_ttft else None,
            "Completion": round(avg_completion, 2) if avg_completion else None,
            "Comments": ""
        }

        if scene == "memory":
            valid_case = v["valid_case"]
            valid_pass = v["valid_pass"]
            if valid_case > 0:
                avg_valid_ttft = sum(v["valid_ttft"]) / len(v["valid_ttft"]) if v["valid_ttft"] and len(v["valid_ttft"]) > 0 else None
                avg_valid_completion = sum(v["valid_completion"]) / len(v["valid_completion"]) if v["valid_completion"] and len(v["valid_completion"]) > 0 else None

                if avg_valid_ttft is not None:
                    if math.isnan(avg_valid_ttft) or math.isinf(avg_valid_ttft):
                        avg_valid_ttft = None
                if avg_valid_completion is not None:
                    if math.isnan(avg_valid_completion) or math.isinf(avg_valid_completion):
                        avg_valid_completion = None

                valid_tool_calling_ratio = v["valid_tool_check"] / valid_case if valid_case > 0 else 0
                valid_retrieval_ratio = v["valid_retrieval_check"] / v["valid_tool_check"] if v["valid_tool_check"] > 0 else 0
                valid_final_answer_ratio = v["valid_final_answer"] / v["valid_retrieval_check"] if v["valid_retrieval_check"] > 0 else 0

                memory_qa_row = {
                    "Category": "Memory QA",
                    "# Case": valid_case,
                    "E2E": f"{valid_pass}/{valid_case}={valid_pass/valid_case:.1%}",
                    "Tool Calling": f"{v['valid_tool_check']}/{valid_case}={valid_tool_calling_ratio:.1%}",
                    "Retrieval": f"{v['valid_retrieval_check']}/{v['valid_tool_check']}={valid_retrieval_ratio:.1%}" if v["valid_tool_check"] > 0 else "--",
                    "Final Answer": f"{v['valid_final_answer']}/{v['valid_retrieval_check']}={valid_final_answer_ratio:.1%}" if v["valid_retrieval_check"] > 0 else "--",
                    "TTFT": round(avg_valid_ttft, 2) if avg_valid_ttft else None,
                    "Completion": round(avg_valid_completion, 2) if avg_valid_completion else None,
                    "Comments": ""
                }
                records.append(memory_qa_row)

                if v["memory_ingestion_success"] > 0:
                    ingestion_total = v["total"]
                    ingestion_e2e_ratio = v["memory_ingestion_success"] / ingestion_total if ingestion_total > 0 else 0
                    new_row = {
                        "Category": "Memory Ingestion",
                        "# Case": ingestion_total,
                        "E2E": f"{v['memory_ingestion_success']}/{ingestion_total}={ingestion_e2e_ratio:.1%}",
                        "Tool Calling": "--",
                        "Retrieval": "--",
                        "Final Answer": "--",
                        "TTFT": "--",
                        "Completion": "--",
                        "Comments": ""
                    }
                    records.append(new_row)
            else:
                records.append(row)
        else:
            records.append(row)

    # === 新增：KB File Ingestion ===
    if dir_path is not None:
        kb_ingestion_stats = scan_kb_file_ingestion(dir_path)
    if kb_ingestion_stats["total"] > 0:
        kb_row = {
            "Category": "KB File Ingestion",
            "# Case": kb_ingestion_stats["total"],
            "E2E": f"{kb_ingestion_stats['completed']}/{kb_ingestion_stats['total']}={kb_ingestion_stats['completed']/kb_ingestion_stats['total']:.1%}",
            "Tool Calling": "--",
            "Retrieval": "--",
            "Final Answer": "--",
            "TTFT": "--",
            "Completion": kb_ingestion_stats["completion"] if kb_ingestion_stats["completion"] is not None else "--",
            "Comments": ""
        }
        records.append(kb_row)

    # === 新增：Memory Ingestion 的 Latency ===
    if dir_path is not None:
        memory_latency = scan_memory_ingestion_latency(dir_path)
    if memory_latency is not None:
        for i, row in enumerate(records):
            if row["Category"] == "Memory Ingestion":
                records[i]["Completion"] = memory_latency
                break

    df = pd.DataFrame(records, columns=[
        "Category", "# Case", "E2E", "Tool Calling", "Retrieval",
        "Final Answer", "TTFT", "Completion", "Comments"
    ])

    if "Category" in df.columns:
        df = df.sort_values("Category")

    logger.info("========== 判决结果汇总 ==========")
    if not df.empty:
        logger.info("\n" + df.to_string(index=False))
    else:
        logger.info("没有可汇总的数据")

    # === 使用 xlsxwriter 设置合并单元格 ===
    with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Summary')

        workbook = writer.book
        worksheet = writer.sheets['Summary']
        worksheet.set_column('A:A', 15)
        worksheet.set_column('B:B', 10)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)
        worksheet.set_column('E:E', 15)
        worksheet.set_column('F:F', 15)
        worksheet.set_column('G:G', 10)
        worksheet.set_column('H:H', 10)
        worksheet.set_column('I:I', 15)

        header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#D9E1F2'})
        subheader_format = workbook.add_format({'bold': True, 'bg_color': '#E6E6E6', 'border': 1})
        data_format = workbook.add_format({'border': 1})

        worksheet.merge_range('C1:F1', 'Pass Rate', header_format)
        worksheet.write('C2', 'E2E', subheader_format)
        worksheet.write('D2', 'Tool Calling', subheader_format)
        worksheet.write('E2', 'Retrieval', subheader_format)
        worksheet.write('F2', 'Final Answer', subheader_format)

        worksheet.merge_range('G1:H1', 'Latency', header_format)
        worksheet.write('G2', 'TTFT', subheader_format)
        worksheet.write('H2', 'Completion', subheader_format)

        worksheet.merge_range('A1:A2', 'Category', header_format)
        worksheet.merge_range('B1:B2', '# Case', header_format)

        def safe_write_value(worksheet, row, col, value, format_obj):
            if pd.isna(value):
                worksheet.write(row, col, "", format_obj)
            elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                worksheet.write(row, col, "", format_obj)
            else:
                worksheet.write(row, col, value, format_obj)

        for row_idx in range(2, len(df) + 2):
            for col_idx in range(0, 9):
                safe_write_value(worksheet, row_idx, col_idx, df.iloc[row_idx-2].iloc[col_idx], data_format)

    logger.info(f"已保存 -> {output_path}")
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
        judge_results_path = Path(args.dir) / "judge_results"
        if judge_results_path.exists() and judge_results_path.is_dir():
            files.extend([f for f in judge_results_path.rglob("*.xlsx") if f.is_file()])
        else:
            logger.warning(f"未找到 'judge_results' 文件夹，将扫描整个目录: {args.dir}")
            files.extend([f for f in Path(args.dir).rglob("*.xlsx") if f.is_file()])

    logger.info(f"找到的文件: {[str(f) for f in files]}")

    if not files:
        logger.error("未找到任何 Excel 文件")
        sys.exit(1)

    summarize(files, output_path=Path(args.output), filter_local_brain=args.filter_local_brain, dir_path=Path(args.dir))


if __name__ == "__main__":
    main()