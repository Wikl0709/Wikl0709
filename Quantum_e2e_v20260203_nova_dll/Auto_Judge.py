import importlib
import json
import pandas as pd
import os
from loguru import logger
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm
import time
import argparse
from datetime import datetime
from pathlib import Path
import summarize_results
import sys
import os
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
# MASTER_API_URL = "https://10.110.158.101/service-large-600-1754878213350/llm/v1/chat/completions"
# MASTER_API_KEY = "aJvWP0tlTcP88F6Nn7M0wr81H66jDP56d786sW77AqRGJsQxjD788kwcsxkFNxNc07Aa6jq8q1tDf8rwD2pX6wHMWSrrdPrFbffaDvH4Ar6RT99L7Nrrm6dWAq4CPq86"

# endpoint = 'https://llm-east-us2-test.openai.azure.com/'
# subscription_key = 'A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY'


# def process_single_row(idx, row):
#     """
#     处理单行数据的函数（用于并发处理）
#     Args:
#         args: (idx, row) 元组，包含行索引和行数据
#     Returns:
#         tuple: (idx, score, reason) 处理结果
#     """
#     # idx, row = args
    
#     # 提取当前行数据（处理空值）
#     question = str(row["question"]).strip() if pd.notna(row["question"]) else "无问题描述"
#     real_answer = str(row["answer"]).strip() if pd.notna(row["answer"]) else "无真实答案"
#     model_response = str(row["result"]).strip() if pd.notna(row["result"]) else "无模型响应"
    
#     # 注意：此函数现在不再使用，因为Memory场景已移到scenes/memory.py中处理
#     # 这里保留是为了避免其他地方可能还在调用它
#     return idx, 0, "函数已弃用"


def get_latest_test_excel(out_dir):
    """
    在当前脚本同路径下的 testresult 目录中，
    查找以 'test' 开头的 Excel 文件（.xlsx/.xls），
    返回创建时间最新的那个文件的 Path 对象。
    若不存在或目录不存在则返回 None。
    # """
    # base_dir = Path(__file__).resolve().parent  # 当前脚本所在目录
    # target_dir = base_dir / "testresult"
    target_dir = out_dir / "testresult"

    if not target_dir.exists() or not target_dir.is_dir():
        logger.info(f"[WARN] 目录不存在：{target_dir}")

        return None

    # 匹配以 test 开头的 Excel 文件
    candidates = list(target_dir.glob("test*.xlsx")) + list(target_dir.glob("test*.xls"))
    if not candidates:
        logger.info(f"[WARN] 未找到匹配文件（test*.xlsx / test*.xls）于：{target_dir}")
        return None

    # 按创建时间（ctime）选择最新；如需按修改时间改为 st_mtime
    latest = max(candidates, key=lambda p: p.stat().st_ctime)
    return latest

def load_scene_module(scene_name):
    """
    根据场景名称动态加载对应的处理模块
    """
    # 场景名称到模块名的映射（不区分大小写）
    scene_to_module = {
        "memory": "memory",
        "kbqa": "kbqa",
        "file-based": "kbqa",
        "file search": "file_search",
        "tool calling": "toolcalling",
        "multimodal": "multimodal",
        "free-chat q&a": "free-chat_q&a"
    }
    
    # 转换为小写进行匹配
    scene_key = scene_name.lower()
    if scene_key not in scene_to_module:
        raise ValueError(f"不支持的场景: {scene_name}")
    
    module_name = scene_to_module[scene_key]
    try:
        module = importlib.import_module(f"scenes.{module_name}")
        return module
    except ImportError as e:
        raise ImportError(f"无法导入模块 scenes.{module_name}: {e}")

def prepare_scene_params(scene_name, row_data, doc_dir, test_mode='local', out_dir=None):
    """
    根据场景准备相应的参数
    """
    params = {}
    
    # 转换为小写进行匹配
    scene_key = scene_name.lower()
    
    if scene_key == "memory":
        params = {
            "question": row_data["question"],
            "answer": row_data["answer"],
            "result": row_data["result"],
            "dimension": row_data["dimension"],
            "memory_retrieval_topk": row_data.get("MemoryRetrievalTop10", "") if test_mode == "cloud" else row_data.get("MemoryRetrievalTop3", ""),
            "session_id_list": row_data.get("session_id_list", ""), #如果没有这列就置为空值
            "root_path": out_dir,
            "test_mode": test_mode
        }
    elif scene_key == "kbqa":
        params = {
            "问题类型": row_data["问题类型"],
            "question": row_data["question"],
            "answer": row_data["answer"],
            "result": row_data["result"],
            "search_file_list": row_data.get("search_file_list", "") ,
            "search_text_list": row_data.get("search_text_list", ""),
            "gt_file": row_data.get("gt_file", "") if "gt_file" in row_data else row_data.get("GT_Filename", ""),
            "gt_text": row_data.get("gt_text", ""),
            "toolname": row_data.get("toolname", ""),
            "test_mode": test_mode
        }
    elif scene_key == "file search":
        params = {
            "doc_dir": doc_dir,
            "gt": row_data["gt"],
            "result": row_data["result"],
            "label_judge":row_data["label_judge"],
            "test_mode": test_mode
            
        }
    elif scene_key == "tool calling":
        params = {
            "question": row_data["question"],
            "result": row_data["result"]
        }
    elif scene_key == "multimodal":
        params = {
            "answer": row_data["answer"],
            "result": row_data["result"],
            "domain": row_data["domain"]
        }
    elif scene_key == "free-chat q&a":
        params = {
            "question": row_data["question"],
            "result": row_data["result"]
        }
    
    return params

def _judge_one_row(index, row, doc_dir, out_dir, test_mode):
    """
    子线程执行：只负责计算，不写df、不写excel
    返回: (index, updates_dict)
    updates_dict 是要写回 df 的列和值
    """
    try:
        # scene 空在主线程已过滤，这里只做保护
        if pd.isna(row.get('scene')) or str(row.get('scene')).lower() == 'nan':
            return index, None

        scene_key = str(row['scene']).lower()

        # 只允许这些场景
        if scene_key not in ["memory", "kbqa", "file search", "tool calling", "multimodal", "free-chat q&a"]:
            return index, {'Result': '', 'Reason': f'不支持的场景: {row.get("scene")}'}

        # 非 memory 场景快捷错误
        if scene_key not in ["memory","kbqa"]:
            if row.get('result') == "CTTVError: Empty response from server":
                return index, {'Result': 0, 'Reason': '接口返回为空'}
            if row.get('result') == "CTTVError: Request Timeout":
                return index, {'Result': 0, 'Reason': '接口返回超时'}
            if isinstance(row.get('result'), str) and row.get('result', '').startswith("CTTVError: Task failed -"):
                return index, {'Result': 0, 'Reason': '接口返回failed错误'}

        # 调场景模块
        scene_module = load_scene_module(row['scene'])
        params = prepare_scene_params(row['scene'], row, doc_dir, test_mode=test_mode, out_dir=out_dir)
        result_dict = scene_module.main(params)

        if not isinstance(result_dict, dict):
            return index, {'Result': '', 'Reason': f'场景模块返回非dict: {type(result_dict)}'}

        updates = {}

        # Result 字段
        if scene_key == "tool calling":
            if "Task_Success_Rate" not in result_dict:
                return index, {'Result': '', 'Reason': "返回结果缺少 'Task_Success_Rate' 键"}
            updates['Result'] = result_dict["Task_Success_Rate"]

        elif scene_key == "free-chat q&a":
            if "eval_is_correct" in result_dict:
                is_correct = result_dict["eval_is_correct"]
                updates['Result'] = 1 if is_correct is True else 0
            elif "Result" in result_dict:
                updates['Result'] = result_dict["Result"]
            else:
                return index, {'Result': '', 'Reason': "返回结果缺少 'eval_is_correct' 或 'Result' 键"}

        else:
            if "Result" not in result_dict:
                return index, {'Result': '', 'Reason': "返回结果缺少 'Result' 键"}
            updates['Result'] = result_dict["Result"]

        # Reason / pass
        if scene_key in ["tool calling", "multimodal"]:
            if "pass" in result_dict:
                updates['pass'] = result_dict["pass"]
            if "TSR_Rationale" in result_dict:
                updates['Reason'] = result_dict["TSR_Rationale"]
            elif "Rationale" in result_dict:
                updates['Reason'] = result_dict["Rationale"]
            elif "Reason" in result_dict:
                updates['Reason'] = result_dict["Reason"]

        elif scene_key == "free-chat q&a":
            if "eval_explanation" in result_dict:
                updates['Reason'] = result_dict["eval_explanation"]
            elif "Reason" in result_dict:
                updates['Reason'] = result_dict["Reason"]
            else:
                updates['Reason'] = result_dict.get("eval_confidence", "评估完成")

        else:
            if "Reason" in result_dict:
                updates['Reason'] = result_dict["Reason"]

        # memory 特殊字段
        if scene_key == "memory":
            if "Memory_reg_success" in result_dict:
                updates['Memory_reg_success'] = result_dict["Memory_reg_success"]
            if "matched_content_all" in result_dict:
                updates['matched_content_all'] = result_dict["matched_content_all"]
            if "Memory_reg_reason" in result_dict:
                updates['Memory_reg_reason'] = result_dict["Memory_reg_reason"]
            if "Retrieval_Check" in result_dict:
                updates['Retrieval_Check'] = result_dict["Retrieval_Check"]
            if "Retrieval_Reason" in result_dict:
                updates['Retrieval_Reason'] = result_dict["Retrieval_Reason"]
        if scene_key == "kbqa":
            if "Retrieval_Check" in result_dict:
                updates['Retrieval_Check'] = result_dict["Retrieval_Check"]


        return index, updates

    except KeyError as e:
        return index, {'Result': '', 'Reason': f'返回结果格式错误: 缺少 {str(e)} 键'}
    except Exception as e:
        return index, {'Result': '', 'Reason': f'处理异常: {str(e)}'}



def run(doc_dir, out_dir, excel_files=None, filter_local_brain='no', test_mode='local'):
    judge_results_dir = os.path.join(out_dir, "judge_results")
    os.makedirs(judge_results_dir, exist_ok=True)
    judge_results_dir = Path(judge_results_dir)

    for excel_file in excel_files:
        logger.info(f"[INFO] 正在处理文件: {excel_file}")
        excel_path = Path(excel_file)
        judgment_output_path = judge_results_dir / f"{excel_path.stem}_Auto_Judge{excel_path.suffix}"

        try:
            all_sheets = pd.read_excel(excel_file, sheet_name=None)
            if 'result' not in all_sheets:
                logger.info(f"[WARN] 文件中没有'result' sheet: {excel_file}")
                continue

            df = all_sheets['result'].copy()
            total_rows = len(df)

            processed_indices = []

            # 断点续跑：合并已有结果
            if judgment_output_path.exists():
                try:
                    existing_judgment_df = pd.read_excel(judgment_output_path, sheet_name='result')

                    if 'Result' in existing_judgment_df.columns:
                        df['Result'] = existing_judgment_df.get('Result', pd.Series([None] * len(df)))
                    if 'Reason' in existing_judgment_df.columns:
                        df['Reason'] = existing_judgment_df.get('Reason', pd.Series([None] * len(df)))
                    if 'pass' in existing_judgment_df.columns:
                        df['pass'] = existing_judgment_df.get('pass', pd.Series([None] * len(df)))

                    processed_indices = existing_judgment_df[
                        (existing_judgment_df['Result'].notna()) |
                        (existing_judgment_df['Result'].isin([0, 1]))
                    ].index.tolist()

                    logger.info(f"[INFO] 检测到已处理 {len(processed_indices)} 行，将继续处理剩余行")
                except Exception as e:
                    logger.info(f"[WARN] 无法读取已有结果文件: {e}")
                    processed_indices = []

            # 收集需要处理的行
            to_process = []
            for index, row in df.iterrows():
                if pd.notna(row.get('Result')) and row['Result'] in [0, 1]:
                    continue
                if index in processed_indices:
                    continue
                if pd.isna(row.get('scene')) or str(row.get('scene')).lower() == 'nan':
                    logger.info(f"[SKIPPED] 第 {index+1} 行场景为空，跳过处理")
                    continue
                to_process.append(index)

            logger.info(f"[INFO] 待处理行数: {len(to_process)} / {total_rows}")

            # 并行执行：只算分，写df和写excel仍在主线程
            max_workers = MAX_WORKERS
            completed = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_judge_one_row, idx, df.loc[idx], doc_dir, out_dir, test_mode): idx
                    for idx in to_process
                }

                for fut in as_completed(futures):
                    idx = futures[fut]
                    index, updates = fut.result()

                    # 写回df（主线程）
                    if updates:
                        for k, v in updates.items():
                            df.at[index, k] = v

                    completed += 1

                    # ✅ 每完成一条就保存一次（保持你原逻辑）
                    all_sheets['result'] = df
                    with pd.ExcelWriter(judgment_output_path, engine='openpyxl') as writer:
                        for sheet_name, sheet_df in all_sheets.items():
                            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

                    scene_val = df.at[index, 'scene'] if 'scene' in df.columns else 'unknown'
                    logger.info(f"[SAVED] 并行已完成 {completed}/{len(to_process)} 行 (场景: {scene_val})")

            logger.info(f"[SUCCESS] 全部处理完成，结果已保存至: {judgment_output_path}")

            # 汇总
            try:
                logger.info("\n" + "="*50)
                logger.info(f"[INFO] 为 {excel_file} 生成独立指标汇总...")
                logger.info("="*50)

                summary_dir = os.path.join(out_dir, "summary_results")
                os.makedirs(summary_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                summary_output_path = os.path.join(summary_dir, f"summary_{timestamp}.xlsx")

                excel_paths = [Path(judgment_output_path)]
                summary_df = summarize_results.summarize(
                    excel_paths=excel_paths,
                    output_path=Path(summary_output_path),
                    filter_local_brain=filter_local_brain,
                    dir_path=out_dir
                )

                csv_path = summary_output_path.replace('.xlsx', '.csv')
                summary_df.to_csv(csv_path, index=False)

                logger.info(f"[SUCCESS] {excel_file} 的指标汇总完成！")
                logger.info(f"    Excel: {summary_output_path}")
                logger.info(f"    CSV: {csv_path}")
                logger.info("="*50)

            except Exception as e:
                logger.info("\n" + "="*50)
                logger.info(f"[ERROR] 为 {excel_file} 生成指标汇总时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                logger.info("="*50)

        except Exception as e:
            logger.info(f"[ERROR] 处理文件失败 {excel_file}: {e}")


    
if __name__ == "__main__":
    
    current_dir = Path(__file__).resolve().parent
    default_out_dir = current_dir / "output"
    MAX_WORKERS = 64
    
    
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description='自动评判测试结果的脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 使用默认参数（自动查找最新的test文件）
  python script.py --doc_dir . --out_dir ./output
  
  # 指定具体的Excel文件
  python script.py --doc_dir . --out_dir ./output --excel_files file1.xlsx file2.xlsx
  
  # 过滤本地知识库
  python script.py --doc_dir . --out_dir ./output --filter_local_brain yes
        '''
    )
    
    # 添加参数
    parser.add_argument(
        '--doc_dir',
        type=str,
        default='./Reg_Docements',
        help='文档目录路径 (默认: 当前目录 ".")'
    )
    
    parser.add_argument(
        '--out_dir',
        type=str,
        default=str(default_out_dir),
        help='输出目录路径 (默认: ./output)'
    )
    
    parser.add_argument(
        '--excel_files',
        type=str,
        nargs='+',
        default=None,
        help='指定要处理的Excel文件路径，可以指定多个文件，用空格分隔。如果不指定，将自动查找最新的test文件'
    )
    
    parser.add_argument(
        '--filter_local_brain',
        type=str,
        choices=['yes', 'no'],
        default='no',
        help='是否过滤本地知识库 (默认: no)'
    )
    
    parser.add_argument(
        '--test_mode',
        type=str,
        choices=['local', 'cloud'],
        default='local',
        help='测试模式，选择本地(local)或云端(cloud) (默认: local)'
    )
    
    # 解析参数
    args = parser.parse_args()
    print('===========')
    print(args)
    # 转换 out_dir 为 Path 对象
    out_dir = Path(args.out_dir)
    
    # 调用run函数
    run(
        doc_dir=args.doc_dir,
        out_dir=out_dir,
        excel_files=args.excel_files,
        filter_local_brain=args.filter_local_brain,
        test_mode=args.test_mode
    )
