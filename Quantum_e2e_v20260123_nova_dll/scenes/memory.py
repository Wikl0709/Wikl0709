# scenes/memory.py
import time
import logging
import requests
from typing import Dict
import pandas as pd
import threading
from openai import AzureOpenAI
import os
import json
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

logging.basicConfig(level=logging.INFO)

# ===== 配置区域 =====
# Azure OpenAI 配置
AZURE_ENDPOINT = "https://llm-east-us2-test.openai.azure.com/"
AZURE_KEY = "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY"
DEPLOYMENT_NAME = "gpt-4.1"
API_VERSION = "2024-12-01-preview"

COLUMNS = ["Result", "Reason", "cost_sec"]

# ===== 独立实现 =====
def verify_answer_consistency(question: str, real_answer: str, model_response: str) -> tuple[int, str]:
    log_lock = threading.Lock()
    
    # 构造模型请求消息
    messages = [
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
    ]
    
    try:
        response = chat_completion_with_retry(messages, max_retry=5, sleep_base=1)
        if response is None:
            raise Exception("GPT 调用失败，重试后仍无返回")
            
        content = response.choices[0].message.content.strip()

        with log_lock:
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
        error_msg = f"调用GPT-4.1模型失败: {str(e)}"
        with log_lock:
            logging.error(f"数据处理失败: {error_msg}")
        return 0, error_msg  # 失败时默认判为不一致，记录错误原因



FILE_PREFIX = "Memory_data_with_responses"
FAIL_RESULT = "failed_input_invalid, no input data"
CORE_COLS = ["user_content_1_result", "user_content_1_response_time"]
RATE_LIMIT_DELAY = 0.2
from typing import Any

def create_azure_client():
    return AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_KEY,
        api_version=API_VERSION
    )
    
def chat_completion_with_retry(messages, max_retry=5, sleep_base=1):
    """
    Azure OpenAI ChatCompletion 重试封装（最小侵入式）
    """
    for attempt in range(1, max_retry + 1):
        try:
            client = create_azure_client()
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.1,
                max_completion_tokens=500,
                timeout=30  # 加超时
            )
            return response
        
        except Exception as e:
            logging.error(f"GPT调用失败，第{attempt}次重试，错误: {str(e)}")
            time.sleep(sleep_base * attempt)  # 递增等待
    return None 
  
def is_numeric_sid(sid: str) -> bool:
    """判断session_id是否为数值型"""
    try:
        float(str(sid).strip())
        return True
    except:
        return False

def load_entries(json_path: str) -> list[dict]:
    """读取JSON中的entries数据"""
    if not os.path.exists(json_path):
        logging.warning(f"⚠ JSON文件不存在：{json_path}")
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    memory_data = data.get("memory_data", {})
    entries_str = memory_data.get("entries", "[]")
    try:
        return json.loads(entries_str)
    except:
        return ast.literal_eval(entries_str)

def merge_match_files(root_path: str) -> pd.DataFrame:
    """合并Excel+匹配所有JSON（非固定名称），返回带Memory列的DataFrame，合并后Excel仅输出到指定根目录"""
    # 1. 合并Excel
    excel_files = [f for f in os.listdir(root_path) if f.startswith(FILE_PREFIX) and f.endswith(".xlsx") and f != "result.xlsx"]
    if not excel_files:
        logging.warning("无匹配的Excel文件")
        return pd.DataFrame()
    # 合并所有匹配的Excel
    all_df = pd.concat([pd.read_excel(os.path.join(root_path, f)) for f in excel_files], ignore_index=True)
    # 补全缺失的核心列
    for col in CORE_COLS:
        if col not in all_df.columns:
            all_df[col] = None
    
    # 2. 按session去重
    final_data = []
    for sid, group in all_df.groupby("session_id"):
        if is_numeric_sid(sid):
            def is_fail(row):
                res = row[CORE_COLS[0]]
                t = row[CORE_COLS[1]]
                res_fail = pd.isna(res) or res == FAIL_RESULT
                t_fail = pd.isna(t) or t in (0, 0.0, "")
                return (pd.isna(res) and pd.isna(t)) or (res_fail and t_fail)
            valid_rows = group[~group.apply(is_fail, axis=1)]
            final_row = valid_rows.iloc[0].copy() if not valid_rows.empty else group.iloc[0].copy()
        else:
            normal_rows = group[~(group[CORE_COLS[0]] == FAIL_RESULT)]
            final_row = normal_rows.iloc[0].copy() if not normal_rows.empty else group.iloc[0].copy()
        final_data.append(final_row)
    merged_df = pd.DataFrame(final_data)
    
    # ===== 合并后Excel仅输出到指定根目录 =====
    excel_output_path = os.path.join(root_path, "memory_data_result_all.xlsx")  # 输出固定名称，覆盖原有同名文件
    merged_df.to_excel(excel_output_path, index=False)
    logging.info(f"合并后的Excel已保存至：{excel_output_path}")
    
    # ===== 遍历根目录所有JSON，不固定名称，解析失败则跳过 =====
    id2content = {}  # 存储所有有效JSON的id-content映射
    # 获取根目录下所有.json后缀的文件
    all_json_files = [f for f in os.listdir(root_path) if f.endswith(".json")]
    if not all_json_files:
        logging.warning("根目录下无JSON文件")
        merged_df["session_id"] = merged_df["session_id"].astype(str)
        return merged_df
    
    # 遍历每个JSON文件，尝试解析，失败则跳过（判定为非目标数据）
    for json_file in all_json_files:
        json_path = os.path.join(root_path, json_file)
        try:
            # 调用原有load_entries解析，失败会抛异常，直接进入except
            entries = load_entries(json_path)
            # 过滤有效条目（含id和content），更新到映射字典
            valid_entries = {item["id"]: item["content"] for item in entries if "id" in item and "content" in item}
            id2content.update(valid_entries)
            logging.info(f"成功解析JSON：{json_file}，有效条目数：{len(valid_entries)}")
        except Exception as e:
            # 解析失败，判定为非目标数据，仅打印警告，不中断流程
            logging.warning(f"JSON文件{json_file}非目标数据（解析失败），跳过：{str(e)[:50]}...")
            continue
    
    if not id2content:
        logging.warning("所有JSON文件均为非目标数据，无有效id-content映射")
        merged_df["session_id"] = merged_df["session_id"].astype(str)
        return merged_df
    
    # 4. 填充Memory列
    def extract_ids(cell):
        if pd.isna(cell):
            return []
        try:
            return json.loads(cell).get("entries", [])
        except:
            return []
    merged_df["user_content_1_result_id"] = merged_df["user_content_1_result"].apply(extract_ids)
    merged_df["Memory_list"] = merged_df["user_content_1_result_id"].apply(lambda x: [id2content.get(i, "") for i in x])
    merged_df["session_id"] = merged_df["session_id"].astype(str)
    return merged_df

def gpt_judge_memory_answer(
    matched_content_all: str,
    question: str,
    answer: str
) -> Dict[str, Any]:

    # 强制 utf-8，替换非法字符
    matched_content_all = matched_content_all.encode('utf-8', errors='replace').decode('utf-8')
    question = question.encode('utf-8', errors='replace').decode('utf-8')
    answer = answer.encode('utf-8', errors='replace').decode('utf-8')

    time.sleep(RATE_LIMIT_DELAY)
    client = create_azure_client()

   
    system_prompt = """
你是一个严格的记忆判决助手。

你的任务是判断：
给定的 matched_content 是否能够回答 question，
并且回答内容在语义上与 answer 一致。

判断标准：
1. 不要求逐字一致，只要语义、事实、结论一致即可。
2. 如果 matched_content 中明确包含或可以直接推断出 answer，判定为“是”。
3. 如果信息缺失、无关、矛盾、或无法支持 answer，判定为“否”。
4. 如果 question 是在询问某个属性 / 物体 / 结构 是否存在，且 matched_content 对对象进行了完整或合理的描述，但未出现该属性，同时 answer 是否定（如“没有 / 否”），则应判定为“是”，因为内容支持该否定结论。

请基于事实，不要进行主观猜测或补充外部常识。
"""

    user_prompt = f"""
matched_content:
{matched_content_all}

question:
{question}

answer:
{answer}

请给出判决结果，并返回 JSON：
{{
  "judge_memory_answer": "是" 或 "否",
  "reason": "简要说明为什么可以或不可以回答"
}}
"""

    try:
        response = chat_completion_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        content = response.choices[0].message.content
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            return {
                "judge_memory_answer": "否",
                "reason": "无法解析 GPT 返回结果"
            }

    except Exception as e:
        return {
            "judge_memory_answer": "否",
            "reason": f"GPT 调用失败: {str(e)}"
        }

# ================= Image文本注册判决函数 =================
def judge_image_text(
    matched_content_all: str,
    register_text: str
) -> Dict[str, Any]:
    client = create_azure_client()
    time.sleep(RATE_LIMIT_DELAY)

    # 原prompt完全保留，一字不改
    system_prompt = """
你正在判断【Image 维度的注册是否成功】。

背景：
- register_text 是用户原始希望被记住的文字信息
- matched_content 是模型基于图片生成并记住的内容

判定目标：
判断 matched_content 是否在语义上表达了 register_text 中的关键信息或事实关系。

重要规则：
规则1（基础判定项）：register_text若仅为客观事实（无主观语义），matched_content需在语义上表达该事实关系，才算注册成功；
规则2（通用项）：仅描述图片外观、颜色、形状、材质、图案等，未表达register_text中的核心事实/语义，**一律不算注册成功**；
规则3（否定项补充）：若register_text询问某属性/物体是否存在，matched_content完整描述对象但未出现该属性，且答案为否定，判定为「是」。
补充规则：请优先检查matched_content中是否包含register_text的核心语义/关键信息，哪怕这些内容被其他信息包裹，只要存在就需判定为“是”。
"""

    user_prompt = f"""
register_text:
{register_text}

matched_content:
{matched_content_all}

请返回 JSON：
{{
  "judge_image_register": "是" 或 "否",
  "reason": "用中文说明是否真正注册了文字信息"
}}
"""

    try:
        response = chat_completion_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        content = response.choices[0].message.content
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())

        return {
            "judge_image_register": "否",
            "reason": "无法解析 Image 注册判定结果"
        }
    except Exception as e:
        logging.error(f"⚠️ Image 注册判定失败: {str(e)}")
        return {
            "judge_image_register": "否",
            "reason": f"Image 注册判定失败: {str(e)}"
        }

def gpt_judge_negative_with_content(
    matched_content_all: str,
    question: str,
    answer: str
) -> Dict[str, Any]:
    """
    反例 Memory 判决：
    判断 matched_content 是否【不支持 / 不包含】question 所询问的信息，
    且 answer 是否为合理的否定回答。
    """

    matched_content_all = matched_content_all.encode('utf-8', errors='replace').decode('utf-8')
    question = question.encode('utf-8', errors='replace').decode('utf-8')
    answer = answer.encode('utf-8', errors='replace').decode('utf-8')

    time.sleep(RATE_LIMIT_DELAY)
    client = create_azure_client()

    system_prompt ="""
你是一个严格的【记忆反例判决助手】。

当前样本为反例场景，但“反例”不代表 matched_content 一定不包含信息。
你的任务是判断：

核心问题：
matched_content 是否支持 answer 对 question 的回答。

判定逻辑：
1. 如果 matched_content 中包含明确事实，并且 answer 是基于该事实对 question 的正确否定或肯定，判定为“是”。
2. 如果 matched_content 中不包含相关信息，但 answer 是合理的否定回答，判定为“是”。
3. 如果 matched_content 与 answer 矛盾，或无法支持 answer，判定为“否”。

特别说明：
- 如果 question 与 matched_content 中的事实不一致，而 answer 是基于 matched_content 的纠正性否定（例如事实是12月2日，而问题问12月3日），应判定为“是”。
- 不允许基于常识补充内容，只能基于 matched_content 本身判断。

请严格基于 matched_content 判断。
"""

    user_prompt = f"""
matched_content:
{matched_content_all}

question:
{question}

answer:
{answer}

请返回 JSON：
{{
  "judge_memory_answer": "是" 或 "否",
  "reason": "简要说明为何该反例回答是正确或错误"
}}
"""

    try:
        response = chat_completion_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        content = response.choices[0].message.content
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())

        return {
            "judge_memory_answer": "否",
            "reason": "无法解析 GPT 返回的反例判定结果"
        }

    except Exception as e:
        return {
            "judge_memory_answer": "否",
            "reason": f"反例 GPT 调用失败: {str(e)}"
        }

    
def verify_Memory_reg_success(question: str, answer: str, session_id_list: str, dimension: str, root_path: str) -> tuple[str, str, str]:
    """重写：复用原文件的双判定逻辑，保证规则一致"""
    if not root_path or not os.path.exists(root_path):
        return "否", "根目录不存在", ""
    
    # 1. 合并匹配文件
    matched_df = merge_match_files(root_path)
    if matched_df.empty:
        return "否", "无有效数据", ""
    
    # 2. 提取当前session的Memory内容和register_text
    contents = []
    register_texts = []
    if session_id_list:
        sids = [s.strip() for s in session_id_list.split(",") if s.strip()]
        for sid in sids:
            mask = matched_df["session_id"] == sid
            if mask.any():
                row = matched_df[mask].iloc[0]
                contents.extend([c for c in row["Memory_list"] if c.strip()])
                if pd.notna(row.get("user_content_1")):
                    register_texts.append(str(row["user_content_1"]).strip())
    
    matched_content_all = "\n".join(contents)
    register_text = "\n".join(register_texts)
    
    if not matched_content_all:
        return "否", "无匹配的Memory内容", ""
    is_negative_case = False

    if session_id_list:
        sids = [s.strip() for s in session_id_list.split(",") if s.strip()]
        for sid in sids:
            mask = matched_df["session_id"] == sid
            if mask.any():
                row = matched_df[mask].iloc[0]
    
                # === 关键新增逻辑 ===
                sub_dim = str(row.get("Sub-dimension-1", "")).strip()
                if sub_dim in ["反例"]:
                    is_negative_case = True

    # 3. 双判定逻辑（memory_answer + Image_text）
    # ---------- Image 判定 ----------
    img_flag = "是"
    img_reason = ""
    # ---------- Image_text判定 ----------
    if dimension == "Image" and matched_content_all:
        if register_text:
            judgment_uc1 = judge_image_text(
                matched_content_all=matched_content_all,
                register_text=register_text
            )
            img_flag = judgment_uc1["judge_image_register"]
            img_reason = judgment_uc1["reason"]
        else:
            img_flag = "否"
            img_reason = "无可用于判定的注册文本（user_content_1）"
    
    # ---------- memory_answer判定 ----------
    if matched_content_all and question and answer:
        if is_negative_case:
            judgment = gpt_judge_negative_with_content(
                matched_content_all, question, answer
            )
        else:
            judgment = gpt_judge_memory_answer(
                matched_content_all, question, answer
            )

    else:
        judgment = {
            "judge_memory_answer": "否",
            "reason": "matched_content 或 question / answer 为空"
        }
    memory_flag = judgment["judge_memory_answer"]
    memory_reason = judgment["reason"]
    
    # ---------- 最终判定 ----------
    final_flag = "Y" if (memory_flag == "是" and img_flag == "是") else "N"
    final_reason = f"memory_answer：{memory_reason}\nImage_text（user_content_1判定）：{img_reason}"
    
    return final_flag, final_reason, matched_content_all
    
def main(row: Dict) -> Dict:

    start_time = time.time()

    # 提取当前行数据（处理空值）
    question = str(row["question"]).strip() if pd.notna(row["question"]) else "无问题描述"
    real_answer = str(row["answer"]).strip() if pd.notna(row["answer"]) else "无真实答案"
    model_response = str(row["result"]).strip() if pd.notna(row["result"]) else "无模型响应"
    session_id_list = str(row["session_id_list"]).strip() if pd.notna(row["session_id_list"]) else "无session_id_list列"
    dimension = str(row["dimension"]).strip() if pd.notna(row["dimension"]) else "无dimension列"
    root_path = str(row["root_path"]).strip() if pd.notna(row["root_path"]) else ""

    
    # root_path = r"/home/taas/yangzy26/Benchmark/duanyy5/Memory_judge/result/"
   
    score, reason = verify_answer_consistency(question, real_answer, model_response)
    memory_reg_success, memory_reg_reason, matched_content_all = verify_Memory_reg_success(
        question=question,
        answer=real_answer,
        session_id_list=session_id_list,
        dimension=dimension,
        root_path=root_path
    )

    cost_time = time.time() - start_time
    return {"Result": score, "Reason":reason, "matched_content_all":matched_content_all,"Memory_reg_success":memory_reg_success,"Memory_reg_reason":memory_reg_reason}
