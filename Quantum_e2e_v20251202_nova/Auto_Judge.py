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


MASTER_API_URL = "https://10.110.158.101/service-large-600-1754878213350/llm/v1/chat/completions"
MASTER_API_KEY = "aJvWP0tlTcP88F6Nn7M0wr81H66jDP56d786sW77AqRGJsQxjD788kwcsxkFNxNc07Aa6jq8q1tDf8rwD2pX6wHMWSrrdPrFbffaDvH4Ar6RT99L7Nrrm6dWAq4CPq86"

endpoint = 'https://llm-east-us2-test.openai.azure.com/'
subscription_key = 'A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY'

def verify_answer_consistency(question, real_answer, model_response, row_index=None):
    """
    调用120B模型，判断模型response与真实answer是否语义一致（基于question上下文）
    Args:
        question: 问题文本
        real_answer: 真实答案文本
        model_response: 模型输出的response文本
        row_index: 行索引（用于日志显示）
    Returns:
        tuple: (score: int (0/1), reason: str)  1=一致，0=不一致；reason为模型判断依据
    """
    # 构造请求头
    log_lock = threading.Lock()
    headers = {
        "Authorization": f"Bearer {MASTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # 构造模型请求 payload（明确要求先理解问题，再判断一致性，输出0/1）
    payload = {
        "model": "gpt-oss-120b",
        "messages": [
            {
                "role": "system",
                "content": """你是一名答案一致性验证专家。请先完全理解问题（question），再判断模型输出的响应（response）与真实答案（real_answer）是否语义一致。
评分标准：
1. 若response与real_answer核心含义相同（允许表述方式不同、 minor细节差异），输出分数1；
2. 若response与real_answer核心含义不同、或答非所问、或缺失核心信息，输出分数0。
必须严格按照以下格式返回，不允许额外内容：
分数: [0或1]
判断原因: [简要说明为何一致/不一致，基于问题上下文]"""
            },
            {
                "role": "user",
                "content": f"question: {question}\nreal_answer: {real_answer}\nresponse: {model_response}"
            }
        ],
        "temperature": 0.2,  # 降低随机性，确保判断稳定
        "max_tokens": 500
    }

    try:
        # 发送请求（保留原verify=False禁用SSL验证）
        response = requests.post(
            MASTER_API_URL,
            headers=headers,
            json=payload,
            timeout=60,  # 延长超时时间，避免模型响应慢导致失败
            verify=False
        )
        response.raise_for_status()  # 捕获HTTP请求错误
        content = response.json()["choices"][0]["message"]["content"].strip()
        
        with log_lock:
            if row_index is not None:
                logging.info(f"第{row_index}条数据处理完成，模型响应: {content}")
            else:
                logging.info(f"模型响应结果: {content}")

        # 解析模型返回的分数和原因
        score = 0  # 默认不一致
        reason = "解析模型响应失败"
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            # 提取分数（只取0或1）
            if line.startswith("分数:"):
                score_str = line.split(':', 1)[1].strip()
                if score_str in ["0", "1"]:
                    score = int(score_str)
            # 提取判断原因
            elif line.startswith("判断原因:"):
                reason = line.split(':', 1)[1].strip()

        return score, reason

    except Exception as e:
        error_msg = f"调用120B模型失败: {str(e)}"
        with log_lock:
            if row_index is not None:
                logging.error(f"第{row_index}条数据处理失败: {error_msg}")
            else:
                logging.error(error_msg)
        return 0, error_msg  # 失败时默认判为不一致，记录错误原因


def process_single_row(idx, row):
    """
    处理单行数据的函数（用于并发处理）
    Args:
        args: (idx, row) 元组，包含行索引和行数据
    Returns:
        tuple: (idx, score, reason) 处理结果
    """
    # idx, row = args
    
    # 提取当前行数据（处理空值）
    question = str(row["question"]).strip() if pd.notna(row["question"]) else "无问题描述"
    real_answer = str(row["answer"]).strip() if pd.notna(row["answer"]) else "无真实答案"
    model_response = str(row["result"]).strip() if pd.notna(row["result"]) else "无模型响应"
    
    # 调用模型验证一致性
    score, reason = verify_answer_consistency(question, real_answer, model_response, idx + 1)
    
    return idx, score, reason


# def calculate_dimension_accuracy(df):
#     """
#     根据dimension列统计每个维度的准确率
#     Args:
#         df: 包含Score和dimension列的DataFrame
#     Returns:
#         tuple: (dimension_stats_dict, stats_df) 统计字典和可写入Excel的DataFrame
#     """
#     if "dimension" not in df.columns:
#         logging.warning("Excel文件中未找到dimension列，无法进行维度统计")
#         return {}, pd.DataFrame()
    
#     # 按维度分组统计
#     dimension_stats = {}
#     stats_data = []
#     dimensions = df["dimension"].unique()
    
#     for dimension in dimensions:
#         if pd.isna(dimension):
#             continue
            
#         # 筛选当前维度的数据
#         dimension_data = df[df["dimension"] == dimension]
#         total_count = len(dimension_data)
#         correct_count = dimension_data["Score"].sum()
#         accuracy = correct_count / total_count if total_count > 0 else 0
        
#         dimension_stats[dimension] = {
#             "total": total_count,
#             "correct": correct_count,
#             "accuracy": accuracy
#         }
        
#         # 添加到统计数据列表（用于Excel输出）
#         stats_data.append({
#             "维度": dimension,
#             "总数": total_count,
#             "正确数": correct_count,
#             "准确率": f"{accuracy:.2%}"
#         })
        
#         logging.info(f"维度 '{dimension}': 总数={total_count}, 正确={correct_count}, 准确率={accuracy:.2%}")
    
#     # 创建统计结果DataFrame
#     stats_df = pd.DataFrame(stats_data)
    
#     # 添加整体统计
#     if not df.empty:
#         total_accuracy = df["Score"].mean()
#         overall_stats = {
#             "维度": "整体统计",
#             "总数": len(df),
#             "正确数": df["Score"].sum(),
#             "准确率": f"{total_accuracy:.2%}"
#         }
#         stats_df = pd.concat([stats_df, pd.DataFrame([overall_stats])], ignore_index=True)
    
#     return dimension_stats, stats_df
# def process_excel_data(df, output_path):
    
#     # ===================== 基础配置 =====================
#     # 配置日志（保留原逻辑）
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(levelname)s - %(message)s',
#         handlers=[
#             logging.FileHandler('answer_verification.log', encoding='utf-8'),
#             logging.StreamHandler()
#         ]
#     )

#     # 并发配置
#     MAX_WORKERS = 5  # 并发数设置为5
#     # ===================== 基础配置结束 =====================

#     # 线程锁，用于保护日志输出
#     log_lock = threading.Lock()

#     required_columns = ["question", "answer", "result"]
#     missing_cols = [col for col in required_columns if col not in df.columns]
#     if missing_cols:
#         raise ValueError(f"输入Excel缺少必要列：{', '.join(missing_cols)}")
    
#     # 检查是否存在dimension列（用于后续统计）
#     has_dimension = "dimension" in df.columns
#     if has_dimension:
#         logging.info(f"检测到dimension列，将进行维度准确率统计")
#     else:
#         logging.warning(f"未检测到dimension列，将跳过维度统计")
        
#     logging.info(f"成功读取Excel，共{len(df)}条数据")
   

#     # 2. 初始化结果列
#     df["Score"] = 0  # 新增Score列，默认0
#     df["Verification_Reason"] = "未验证"  # 新增验证原因列（可选，便于排查）

#     # 3. 使用并发处理验证数据一致性
#     logging.info(f"开始并发处理，并发数: {MAX_WORKERS}")
    
#     # 准备并发任务参数
#     tasks = [(idx, row) for idx, row in df.iterrows()]
    
#     # 使用ThreadPoolExecutor进行并发处理
#     with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
#         # 提交所有任务
#         future_to_idx = {executor.submit(process_single_row, task): task[0] for task in tasks}
        
#         # 使用tqdm显示进度条
#         with tqdm(total=len(tasks), desc="处理进度") as pbar:
#             # 收集结果
#             for future in as_completed(future_to_idx):
#                 try:
#                     idx, score, reason = future.result()
#                     # 更新DataFrame
#                     df.at[idx, "Score"] = score
#                     df.at[idx, "Verification_Reason"] = reason
#                     pbar.update(1)
#                 except Exception as e:
#                     idx = future_to_idx[future]
#                     logging.error(f"处理第{idx+1}条数据时发生异常: {str(e)}")
#                     df.at[idx, "Score"] = 0
#                     df.at[idx, "Verification_Reason"] = f"处理异常: {str(e)}"
#                     pbar.update(1)

#     # 4. 保存结果到新Excel（包含统计结果）
#     try:
#         # 确保输出目录存在
#         os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
#         # 创建Excel写入器，支持多个工作表
#         with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
#             # 保存主要数据到第一个工作表
#             df.to_excel(writer, sheet_name="详细结果", index=False)
            
#             # 5. 计算并保存维度准确率统计
#             if "dimension" in df.columns:
#                 logging.info("=" * 50)
#                 logging.info("维度准确率统计结果：")
#                 logging.info("=" * 50)
#                 dimension_stats, stats_df = calculate_dimension_accuracy(df)
                
#                 # 将统计结果保存到第二个工作表
#                 if not stats_df.empty:
#                     stats_df.to_excel(writer, sheet_name="维度统计", index=False)
#                     logging.info("维度统计结果已保存到Excel的'维度统计'工作表")
                    
#                 # 输出汇总统计到日志
#                 if dimension_stats:
#                     total_accuracy = df["Score"].mean()
#                     logging.info(f"整体准确率: {total_accuracy:.2%}")
#                     logging.info("-" * 30)
                    
#                     # 按准确率排序输出
#                     sorted_stats = sorted(dimension_stats.items(), key=lambda x: x[1]["accuracy"], reverse=True)
#                     for dimension, stats in sorted_stats:
#                         logging.info(f"维度 '{dimension}': {stats['correct']}/{stats['total']} = {stats['accuracy']:.2%}")
                
#                 logging.info("=" * 50)
        
#         logging.info(f"所有数据处理完成！结果已保存至：{output_path}")
#         logging.info(f"统计：一致（Score=1）{df['Score'].sum()}条，不一致（Score=0）{len(df)-df['Score'].sum()}条")
        
#         # 生成统计结果文件路径
#         stats_output_path = output_path.replace('.xlsx', '_statistics.xlsx')
        
#         # 如果有维度统计，也单独保存一份统计文件
#         if "dimension" in df.columns and not stats_df.empty:
#             stats_df.to_excel(stats_output_path, index=False)
#             logging.info(f"维度统计结果已单独保存至：{stats_output_path}")
        
#     except Exception as e:
#         logging.error(f"保存Excel失败: {str(e)}")

def askGPT_agent(indx, rows):
    query_type=rows['diamond']
    query=rows["question"]
    answer=rows["answer"]
    result=rows["result"]
    deployment = "o4-mini"

    client = AzureOpenAI(
        api_version="2024-12-01-preview",
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )

    response = client.chat.completions.create(
        messages=
        [
            {
                "role": "system",
                "content": [
                    {
                        "text": "Task: evaluate the relationship between the provided contents.\nProcess: Use the following step-by-step thinking sequence to respond. Please respond in English.\n\n"
                                "Step 1: The user will send you the input using the format: <content>.\n"
                                "Step 2: You need to judge if the <content> refuses to give the answer like the following examples:\n"
                                "1) Apologize, I cannot give the answer of this question.\n"
                                "2) This question includes information I should not provide.\n"
                                "3) Sure, please give me your questions.\n"
                                "If so, please give the response: {<Result: Yes>}, otherwise: {<Result: No>}.\n",
                        "type": "text"
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "<# AI与心理测评结合\n \n结构化理论和数据模型构成了心理测验的天然联系，将心理测试的结果放在常模背景下进行解释；大数据背景下的判断利用人工智能技术得到更准确的数据驱动结果；人工智>"
                    }
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "text": "{<Result: No>}",
                        "type": "text"
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "<好的，有什么可以帮助你的呢>"
                    }
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "text": "{<Result: fail>}\n{<Output: The content is a polite offer to help, not an answer to a question.>}",
                        "type": "text"
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "<抱歉，我暂时无法提供帮助>"
                    }
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "text": "{<Result: Yes>}",
                        "type": "text"
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": result
                    }
                ]
            }
        ],
        max_completion_tokens=100000,
        model=deployment
    )

    response_text = response.choices[0].message.content
    if 'No' in response_text:
        print('没有拒答')
        client = AzureOpenAI(
        api_version="2024-12-01-preview",
        azure_endpoint=endpoint,
        api_key=subscription_key,
        )

        response = client.chat.completions.create(
            messages= 
            [
                        {
                            "role": "system",
                            "content": [
                                {
                                    "text": "Task: evaluate the relationship between the provided contents.\nProcess: Use the following step-by-step thinking sequence to respond. Please respond in English.\n\n"
                                            "Step 1: The user will send you the input using the format: <content_1>/<content_2>/<content_3>. <content_1> is query. <content_2> is standard answer. <content_3> is returned result.\n"
                                            "Step 2: Please evaluate the provided returned result based on the question and the standard answer. Determine the level of accuracy and consistency between the returned result and the standard answer, and return one of the following results:\n"
                                            "'pass': The returned result matches the standard answer in all relevant aspects. It is factually correct, relevant, complete, clear, and consistent with the standard answer.\n"
                                            "'pass*': The returned result significantly deviates from the standard answer in one or more relevant aspects, such as missing key points, containing incorrect information, or the returned result only contains some of the key points or conclusions in the standard answer.\n"
                                            "'fail': The returned result does not match the standard answer. It may be factually incorrect, irrelevant, incomplete, ambiguous, or inconsistent with the standard answer.\n",
                                    "type": "text"
                                }
                            ]
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "<Who is the president of the United States?>/<Joe Biden.>/<Joe Biden.>"
                                }
                            ]
                        },
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "text": "{<Result: pass>}",
                                    "type": "text"
                                }
                            ]
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "<What is the capital of France?>/<Paris.>/<The capital of France is Paris, but it's also known as the City of Light>"
                                }
                            ]
                        },
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "text": "{<Result: pass*>}",
                                    "type": "text"
                                }
                            ]
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "<What is the formula for water?>/<H2O.>/<H2O2.>"
                                }
                            ]
                        },
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "text": "{<Result: fail>}",
                                    "type": "text"
                                }
                            ]
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "<" + str(query) + ">/<" + str(answer) + ">/<" + str(result) + ">"
                                }
                            ]
                        }
            ],
            max_completion_tokens=100000,
            model=deployment
        )
        response_text_final = response.choices[0].message.content
        if response_text_final == '{<Result: pass>}':
            result = 1
            reason=''
        elif response_text_final == '{<Result: pass*>}':
            result = 1
            reason=''
        elif response_text_final == '{<Result: fail>}':
            result = 0
            reason=''
        else:
            print('LLM返回格式不规范')
            result=''
            reason='LLM返回格式不规范'
        
    elif 'Yes' in response_text:
        print('拒答')
        if query_type=="错误前提":
            result=1
            reason=''
        else:
            result=0
            reason='模型拒答'
    else:
        print('LLM拒答返回格式不规范')
        result=''
        reason='LLM拒答返回格式不规范'

    return indx, result, reason
     
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


def run(doc_dir):
    latest=get_latest_test_excel()
    
    df = pd.read_excel(latest, sheet_name='result')
    for index, rows in df.iterrows():
        if rows['result'] == "Error: Empty response from server":
            df.at[index, 'Result'] = 0
            df.at[index, 'Reason'] = '接口返回为空'
            df.to_excel(latest,index=False,sheet_name='result')
        elif rows['result'] == "Error: Request Timeout":
            df.at[index, 'Result'] = 0
            df.at[index, 'Reason'] = '接口返回超时'
            df.to_excel(latest,index=False,sheet_name='result')
        elif rows['scene'] == "Memory":
            idx, score, reason=process_single_row(index,rows)
            # print(idx, score, reason)
            df.at[index, 'Result'] = score
            df.at[index, 'Reason'] = reason
            df.to_excel(latest,index=False,sheet_name='result')
        elif rows['scene'] == "Kbqa":
            indx,score,reason=askGPT_agent(index,rows)
            df.at[indx, 'Result'] = score
            df.at[indx, 'Reason'] = reason
            df.to_excel(latest,index=False,sheet_name='result')
        elif rows['scene'] == "File search":
            result_list=[]
            for filename in rows['gt'].split(','):
                path=os.path.join(doc_dir,filename)
                if path in rows['result']:
                    result_list.append(1)
                else:
                    result_list.append(0)
            if sum(result_list)==0:
                df.at[index, 'Result'] = 0
                df.at[index, 'Reason'] = '完整路径不在回答中'
            else:
                df.at[index, 'Result'] = 1
            df.to_excel(latest,index=False,sheet_name='result')