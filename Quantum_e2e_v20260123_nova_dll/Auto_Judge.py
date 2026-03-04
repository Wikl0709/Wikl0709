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
            "session_id_list": row_data.get("session_id_list", ""), #如果没有这列就置为空值
            "root_path": out_dir
        }
    elif scene_key == "kbqa":
        params = {
            "问题类型": row_data["问题类型"],
            "question": row_data["question"],
            "answer": row_data["answer"],
            "result": row_data["result"]
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

def run(doc_dir,out_dir, excel_files=None,filter_local_brain='no',test_mode='local'):
    judge_results_dir = os.path.join(out_dir, "judge_results")
    if not os.path.exists(judge_results_dir):
        os.makedirs(judge_results_dir)

    judge_results_dir = Path(judge_results_dir)
    # if excel_files is None or not excel_files:
    #     latest = get_latest_test_excel(out_dir)
    #     if not latest:
    #         logger.info("[ERROR] 未找到可处理的Excel文件")
    #         return
    #     excel_files = [latest]
    
    for excel_file in excel_files:
        logger.info(f"[INFO] 正在处理文件: {excel_file}")
        excel_path = Path(excel_file)
        # 这是判决结果文件的路径
        judgment_output_path = judge_results_dir / f"{excel_path.stem}_Auto_Judge{excel_path.suffix}"

        try:
            all_sheets = pd.read_excel(excel_file, sheet_name=None)
            if 'result' not in all_sheets:
                logger.info(f"[WARN] 文件中没有'result' sheet: {excel_file}")
                continue
            df = all_sheets['result'].copy()
            total_rows = len(df)
            
            # 初始化processed_indices为空列表
            processed_indices = []
            
            # 如果判决结果文件已存在，读取其中已有的结果
            if judgment_output_path.exists():
                try:
                    existing_judgment_df = pd.read_excel(judgment_output_path, sheet_name='result')
                    # 将已有结果合并到当前df中
                    if 'Result' in existing_judgment_df.columns:
                        df['Result'] = existing_judgment_df.get('Result', pd.Series([None] * len(df)))
                    if 'Reason' in existing_judgment_df.columns:
                        df['Reason'] = existing_judgment_df.get('Reason', pd.Series([None] * len(df)))
                    if 'pass' in existing_judgment_df.columns:
                        df['pass'] = existing_judgment_df.get('pass', pd.Series([None] * len(df)))
                    
                    # 获取已处理的行索引
                    processed_indices = existing_judgment_df[
                        (existing_judgment_df['Result'].notna()) | 
                        (existing_judgment_df['Result'].isin([0, 1]))  # 包括0分的情况
                    ].index.tolist()
                    logger.info(f"[INFO] 检测到已处理 {len(processed_indices)} 行，将继续处理剩余行")
                except Exception as e:
                    logger.info(f"[WARN] 无法读取已有结果文件: {e}")
                    processed_indices = []
            
            for index, rows in df.iterrows():
                if pd.notna(rows.get('Result')) and rows['Result'] in [0, 1]:
                    logger.info(f"[SKIPPED] 第 {index+1} 行已存在结果，跳过处理")
                    continue
                # 检查场景是否为空值，如果为空则跳过
                if pd.isna(rows['scene']) or str(rows['scene']).lower() == 'nan':
                    logger.info(f"[SKIPPED] 第 {index+1} 行场景为空，跳过处理")
                    continue
                if index in processed_indices:
                    logger.info(f"[SKIPPED] 已处理第 {index+1} 行，跳过")
                    continue
                
                try:
                    if str(rows['scene']).lower() in ["memory", "kbqa", "file search", "tool calling", "multimodal", "free-chat q&a"]:
                        try:
                            if str(rows['scene']).lower() != "memory":
                                if rows['result'] == "CTTVError: Empty response from server":
                                    df.at[index, 'Result'] = 0
                                    df.at[index, 'Reason'] = '接口返回为空'
                                elif rows['result'] == "CTTVError: Request Timeout":
                                    df.at[index, 'Result'] = 0
                                    df.at[index, 'Reason'] = '接口返回超时'
                                elif str(rows['result']).startswith("CTTVError: Task failed -"):
                                    df.at[index, 'Result'] = 0
                                    df.at[index, 'Reason'] = '接口返回failed错误'
                                else:
                                    # 动态加载模块
                                    scene_module = load_scene_module(rows['scene'])
                                    # 准备参数
                                    params = prepare_scene_params(rows['scene'], rows, doc_dir, test_mode=test_mode,out_dir=out_dir)
                                    # 执行处理
                                    result_dict = scene_module.main(params)
                            else:

                                # Memory场景单独处理
                                scene_module = load_scene_module(rows['scene'])
                                params = prepare_scene_params(rows['scene'], rows, doc_dir, test_mode=test_mode,out_dir=out_dir)
                                result_dict = scene_module.main(params)
                            # 验证返回结果格式
                            if not isinstance(result_dict, dict):
                                raise ValueError(f"场景模块 {rows['scene']} 返回的结果不是字典类型")
                            
                            # 根据不同场景处理 Result 字段
                            scene_key = str(rows['scene']).lower()
                            if scene_key == "tool calling":
                                # Tool Calling 场景特殊处理：使用 Task_Success_Rate 作为 Result
                                if "Task_Success_Rate" in result_dict:
                                    df.at[index, 'Result'] = result_dict["Task_Success_Rate"]
                                else:
                                    raise KeyError(f"场景模块 {rows['scene']} 返回的结果缺少 'Task_Success_Rate' 键")
                            elif scene_key == "free-chat q&a":
                                # Free-chat q&a 场景特殊处理：检查是否包含 eval_is_correct 字段
                                if "eval_is_correct" in result_dict:
                                    # 根据 eval_is_correct 的值设置 Result
                                    is_correct = result_dict["eval_is_correct"]
                                    if is_correct is True:
                                        df.at[index, 'Result'] = 1
                                    elif is_correct is False:
                                        df.at[index, 'Result'] = 0
                                    else:
                                        # 如果 eval_is_correct 不是布尔值，可能是解析错误
                                        df.at[index, 'Result'] = 0
                                elif "Result" in result_dict:
                                    # 如果场景模块已按标准格式返回 Result，直接使用
                                    df.at[index, 'Result'] = result_dict["Result"]
                                else:
                                    raise KeyError(f"场景模块 {rows['scene']} 返回的结果缺少 'eval_is_correct' 或 'Result' 键")
                            else:
                                # 其他场景使用 Result 键
                                if "Result" not in result_dict:
                                    raise KeyError(f"场景模块 {rows['scene']} 返回的结果缺少 'Result' 键")
                                df.at[index, 'Result'] = result_dict["Result"]
                            
                            # 根据不同场景处理 Reason 或 pass 字段
                            if scene_key in ["tool calling", "multimodal"]:
                                # 对于 Tool calling 和 Multimodal 场景，可能存在 pass 字段
                                if "pass" in result_dict:
                                    df.at[index, 'pass'] = result_dict["pass"]
                                if "TSR_Rationale" in result_dict:
                                    df.at[index, 'Reason'] = result_dict["TSR_Rationale"]
                                elif "Rationale" in result_dict:
                                    df.at[index, 'Reason'] = result_dict["Rationale"]
                                # 如果以上都没有，但有 Reason，则使用 Reason
                                elif "Reason" in result_dict:
                                    df.at[index, 'Reason'] = result_dict["Reason"]
                            elif scene_key == "free-chat q&a":
                                # Free-chat q&a 场景特殊处理：使用 eval_explanation 作为 Reason
                                if "eval_explanation" in result_dict:
                                    df.at[index, 'Reason'] = result_dict["eval_explanation"]
                                elif "Reason" in result_dict:
                                    df.at[index, 'Reason'] = result_dict["Reason"]
                                else:
                                    # 如果没有 eval_explanation，可以使用其他字段或设置默认值
                                    df.at[index, 'Reason'] = result_dict.get("eval_confidence", "评估完成")
                            else:
                                # 其他场景使用 Reason 字段
                                if "Reason" in result_dict:
                                    df.at[index, 'Reason'] = result_dict["Reason"]
                                    
                            # memory 场景特殊返回字段处理
                            if scene_key == "memory":
                                if "Memory_reg_success" in result_dict:
                                    df.at[index, 'Memory_reg_success'] = result_dict["Memory_reg_success"]
                                if "matched_content_all" in result_dict:
                                    df.at[index, 'matched_content_all'] = result_dict["matched_content_all"]
                                if "Memory_reg_reason" in result_dict:
                                    df.at[index, 'Memory_reg_reason'] = result_dict["Memory_reg_reason"]

                        except KeyError as e:
                            logger.info(f"[ERROR] 场景 {rows['scene']} 返回结果格式错误: {e}")
                            df.at[index, 'Result'] = ''
                            df.at[index, 'Reason'] = f'返回结果格式错误: 缺少 {str(e)} 键'
                        except Exception as e:
                            logger.info(f"[ERROR] 处理场景 {rows['scene']} 时出错: {e}")
                            df.at[index, 'Result'] = ''
                            df.at[index, 'Reason'] = f'处理异常: {str(e)}'


                    # 每处理一行就保存一次，防止程序中断丢失结果
                    all_sheets['result'] = df
                    with pd.ExcelWriter(judgment_output_path, engine='openpyxl') as writer:
                        for sheet_name, sheet_df in all_sheets.items():
                            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    logger.info(f"[SAVED] 已处理 {index+1}/{total_rows} 行 (场景: {rows['scene']})")
                    
                except Exception as e:
                    logger.info(f"[ERROR] 处理第{index+1}行时出错: {e}")
                    df.at[index, 'Result'] = ''
                    df.at[index, 'Reason'] = f'处理异常: {str(e)}'
                    # 即使出错也要保存结果
                    all_sheets['result'] = df
                    with pd.ExcelWriter(judgment_output_path, engine='openpyxl') as writer:
                        for sheet_name, sheet_df in all_sheets.items():
                            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            logger.info(f"[SUCCESS] 全部处理完成，结果已保存至: {judgment_output_path}")
            
            try:
                logger.info("\n" + "="*50)
                logger.info(f"[INFO] 为 {excel_file} 生成独立指标汇总...")
                logger.info("="*50)
                # script_dir = os.path.dirname(os.path.abspath(__file__))
                
                # 直接使用summary_results目录，不再创建子目录
                summary_dir = os.path.join(out_dir, "summary_results")

                os.makedirs(summary_dir, exist_ok=True)
                logger.info(f"[INFO] {excel_file} 的汇总结果将保存至: {summary_dir}")
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # summary文件路径（与判决结果文件不同）
                summary_output_path = os.path.join(summary_dir, f"summary_{timestamp}.xlsx")
                
                # 正确：将判决结果文件路径作为输入
                excel_paths = [Path(judgment_output_path)]
                
                logger.info(f"[INFO] 正在为 {excel_file} 生成指标汇总...")
                # summary_df = summarize_results.summarize(
                #     excel_paths=excel_paths,
                #     output_path=Path(summary_output_path)  # summary输出路径
                # )

                summary_df = summarize_results.summarize(
                    excel_paths=excel_paths,
                    output_path=Path(summary_output_path),
                    filter_local_brain=filter_local_brain 
                )
                
                csv_path = summary_output_path.replace('.xlsx', '.csv')
                summary_df.to_csv(csv_path, index=False)
                logger.info(f"[INFO] {excel_file} 的汇总结果CSV格式已保存至: {csv_path}")
                
                logger.info("\n" + "="*50)
                logger.info(f"[SUCCESS] {excel_file} 的指标汇总完成！")
                logger.info(f"    Excel: {summary_output_path}")
                logger.info(f"    CSV: {csv_path}")
                logger.info("="*50)
                
            except Exception as e:
                logger.info(f"\n" + "="*50)
                logger.info(f"[ERROR] 为 {excel_file} 生成指标汇总时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                logger.info("="*50)
            
        except Exception as e:
            logger.info(f"[ERROR] 处理文件失败 {excel_file}: {e}")

    
if __name__ == "__main__":
    
    current_dir = Path(__file__).resolve().parent
    default_out_dir = current_dir / "output"
    
    
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
