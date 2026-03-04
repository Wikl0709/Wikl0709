import importlib
import json
import pandas as pd
import os
import logging
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm
import time
from openai import OpenAI
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from datetime import datetime
from pathlib import Path
import summarize_results
import sys
import os
from pathlib import Path

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


def get_latest_test_excel():
    """
    在当前脚本同路径下的 testresult 目录中，
    查找以 'test' 开头的 Excel 文件（.xlsx/.xls），
    返回创建时间最新的那个文件的 Path 对象。
    若不存在或目录不存在则返回 None。
    """
    base_dir = Path(__file__).resolve().parent  # 当前脚本所在目录
    target_dir = base_dir / "testresult"

    if not target_dir.exists() or not target_dir.is_dir():
        print(f"[WARN] 目录不存在：{target_dir}")
        return None

    # 匹配以 test 开头的 Excel 文件
    candidates = list(target_dir.glob("test*.xlsx")) + list(target_dir.glob("test*.xls"))
    if not candidates:
        print(f"[WARN] 未找到匹配文件（test*.xlsx / test*.xls）于：{target_dir}")
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

def prepare_scene_params(scene_name, row_data, doc_dir):
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
            "result": row_data["result"]
        }
    elif scene_key == "kbqa":
        params = {
            "diamond": row_data["diamond"],
            "question": row_data["question"],
            "answer": row_data["answer"],
            "result": row_data["result"]
        }
    elif scene_key == "file search":
        params = {
            "doc_dir": doc_dir,
            "gt": row_data["gt"],
            "result": row_data["result"]
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

def run(doc_dir, excel_files=None):
    project_root = Path(__file__).resolve().parent
    judge_results_dir = project_root / "judge_results"
    judge_results_dir.mkdir(exist_ok=True, parents=True)

    if excel_files is None or not excel_files:
        latest = get_latest_test_excel()
        if not latest:
            print("[ERROR] 未找到可处理的Excel文件")
            return
        excel_files = [latest]
    
    for excel_file in excel_files:
        print(f"[INFO] 正在处理文件: {excel_file}")
        excel_path = Path(excel_file)
        # 这是判决结果文件的路径
        judgment_output_path = judge_results_dir / f"{excel_path.stem}_Auto_Judge{excel_path.suffix}"

        try:
            all_sheets = pd.read_excel(excel_file, sheet_name=None)
            if 'result' not in all_sheets:
                print(f"[WARN] 文件中没有'result' sheet: {excel_file}")
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
                    print(f"[INFO] 检测到已处理 {len(processed_indices)} 行，将继续处理剩余行")
                except Exception as e:
                    print(f"[WARN] 无法读取已有结果文件: {e}")
                    processed_indices = []
            
            for index, rows in df.iterrows():
                # 检查场景是否为空值，如果为空则跳过
                if pd.isna(rows['scene']) or str(rows['scene']).lower() == 'nan':
                    print(f"[SKIPPED] 第 {index+1} 行场景为空，跳过处理")
                    continue
                if index in processed_indices:
                    print(f"[SKIPPED] 已处理第 {index+1} 行，跳过")
                    continue
                
                try:
                    if rows['result'] == "Error: Empty response from server":
                        df.at[index, 'Result'] = 0
                        df.at[index, 'Reason'] = '接口返回为空'
                    elif rows['result'] == "Error: Request Timeout":
                        df.at[index, 'Result'] = 0
                        df.at[index, 'Reason'] = '接口返回超时'
                    elif str(rows['scene']).lower() in ["memory", "kbqa", "file search", "tool calling", "multimodal", "free-chat q&a"]:
                        # 替换原有的处理逻辑（约224行）
                        try:
                            # 动态加载模块
                            scene_module = load_scene_module(rows['scene'])
                            
                            # 准备参数
                            params = prepare_scene_params(rows['scene'], rows, doc_dir)
                            
                            # 执行处理
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
                            else:
                                # 其他场景使用 Reason 字段
                                if "Reason" in result_dict:
                                    df.at[index, 'Reason'] = result_dict["Reason"]

                        except KeyError as e:
                            print(f"[ERROR] 场景 {rows['scene']} 返回结果格式错误: {e}")
                            df.at[index, 'Result'] = ''
                            df.at[index, 'Reason'] = f'返回结果格式错误: 缺少 {str(e)} 键'
                        except Exception as e:
                            print(f"[ERROR] 处理场景 {rows['scene']} 时出错: {e}")
                            df.at[index, 'Result'] = ''
                            df.at[index, 'Reason'] = f'处理异常: {str(e)}'
                        # try:
                        #     # 动态加载模块
                        #     scene_module = load_scene_module(rows['scene'])
                            
                        #     # 准备参数
                        #     params = prepare_scene_params(rows['scene'], rows, doc_dir)
                            
                        #     # 执行处理
                        #     result_dict = scene_module.main(params)
                        #     df.at[index, 'Result'] = result_dict["Result"]
                            
                        #     # 根据不同场景处理 Reason 或 pass 字段
                        #     scene_key = str(rows['scene']).lower()
                        #     if scene_key in ["tool calling", "multimodal"]:
                        #         # 对于 Tool calling 和 Multimodal 场景，可能存在 pass 字段
                        #         if "pass" in result_dict:
                        #             df.at[index, 'pass'] = result_dict["pass"]
                        #         if "TSR_Rationale" in result_dict:
                        #             df.at[index, 'Reason'] = result_dict["TSR_Rationale"]
                        #         elif "Rationale" in result_dict:
                        #             df.at[index, 'Reason'] = result_dict["Rationale"]
                        #     else:
                        #         # 其他场景使用 Reason 字段
                        #         if "Reason" in result_dict:
                        #             df.at[index, 'Reason'] = result_dict["Reason"]
                            
                        # except Exception as e:
                        #     print(f"[ERROR] 处理场景 {rows['scene']} 时出错: {e}")
                        #     df.at[index, 'Result'] = ''
                        #     df.at[index, 'Reason'] = f'处理异常: {str(e)}'

                    # 每处理一行就保存一次，防止程序中断丢失结果
                    all_sheets['result'] = df
                    with pd.ExcelWriter(judgment_output_path, engine='openpyxl') as writer:
                        for sheet_name, sheet_df in all_sheets.items():
                            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    print(f"[SAVED] 已处理 {index+1}/{total_rows} 行 (场景: {rows['scene']})")
                    
                except Exception as e:
                    print(f"[ERROR] 处理第{index+1}行时出错: {e}")
                    df.at[index, 'Result'] = ''
                    df.at[index, 'Reason'] = f'处理异常: {str(e)}'
                    # 即使出错也要保存结果
                    all_sheets['result'] = df
                    with pd.ExcelWriter(judgment_output_path, engine='openpyxl') as writer:
                        for sheet_name, sheet_df in all_sheets.items():
                            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            print(f"[SUCCESS] 全部处理完成，结果已保存至: {judgment_output_path}")
            
            try:
                print("\n" + "="*50)
                print(f"[INFO] 为 {excel_file} 生成独立指标汇总...")
                print("="*50)
                script_dir = os.path.dirname(os.path.abspath(__file__))
                
                # 直接使用summary_results目录，不再创建子目录
                summary_dir = os.path.join(script_dir, "summary_results")
                os.makedirs(summary_dir, exist_ok=True)
                print(f"[INFO] {excel_file} 的汇总结果将保存至: {summary_dir}")
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # summary文件路径（与判决结果文件不同）
                summary_output_path = os.path.join(summary_dir, f"summary_{timestamp}.xlsx")
                
                # 正确：将判决结果文件路径作为输入
                excel_paths = [Path(judgment_output_path)]
                
                print(f"[INFO] 正在为 {excel_file} 生成指标汇总...")
                summary_df = summarize_results.summarize(
                    excel_paths=excel_paths,
                    output_path=Path(summary_output_path)  # summary输出路径
                )
                
                csv_path = summary_output_path.replace('.xlsx', '.csv')
                summary_df.to_csv(csv_path, index=False)
                print(f"[INFO] {excel_file} 的汇总结果CSV格式已保存至: {csv_path}")
                
                print("\n" + "="*50)
                print(f"[SUCCESS] {excel_file} 的指标汇总完成！")
                print(f"    Excel: {summary_output_path}")
                print(f"    CSV: {csv_path}")
                print("="*50)
                
            except Exception as e:
                print(f"\n" + "="*50)
                print(f"[ERROR] 为 {excel_file} 生成指标汇总时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                print("="*50)
            
        except Exception as e:
            print(f"[ERROR] 处理文件失败 {excel_file}: {e}")

# if __name__ == "__main__":
#     # 指定文档目录
#     doc_dir = "."  # 文档目录，根据实际需要修改
    
#     # 指定具体的Excel文件路径
#     excel_file_path = r"C:\Users\weiyb2\Downloads\TEMP\test_results_local_solution_case_1222_20251222_151850_cycle1.xlsx"  # 修改为实际的文件路径
    
#     # 调用run函数处理指定文件
#     run(doc_dir, excel_files=[excel_file_path])