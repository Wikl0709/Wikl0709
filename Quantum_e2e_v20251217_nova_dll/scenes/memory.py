# scenes/memory.py
import time
import logging
import requests
from typing import Dict
import pandas as pd
import threading

logging.basicConfig(level=logging.INFO)

# ===== 独立配置 =====
MASTER_API_URL = "https://10.110.158.101/service-large-600-1754878213350/llm/v1/chat/completions"
MASTER_API_KEY = "aJvWP0tlTcP88F6Nn7M0wr81H66jDP56d786sW77AqRGJsQxjD788kwcsxkFNxNc07Aa6jq8q1tDf8rwD2pX6wHMWSrrdPrFbffaDvH4Ar6RT99L7Nrrm6dWAq4CPq86"

COLUMNS = ["Result", "Reason", "cost_sec"]

# ===== 独立实现 =====
def verify_answer_consistency(question: str, real_answer: str, model_response: str) -> tuple[int, str]:
    log_lock = threading.Lock()
    # 构造请求头
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
        "temperature": 0.2,
        "max_tokens": 500
    }
    
    try:
        # 发送请求（保留原verify=False禁用SSL验证）
        response = requests.post(MASTER_API_URL, headers=headers, json=payload, timeout=60, verify=False)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()

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
        error_msg = f"调用120B模型失败: {str(e)}"
        with log_lock:
            logging.error(f"数据处理失败: {error_msg}")
        return 0, error_msg  # 失败时默认判为不一致，记录错误原因

def main(row: Dict) -> Dict:
    start_time = time.time()

    # 提取当前行数据（处理空值）
    question = str(row["question"]).strip() if pd.notna(row["question"]) else "无问题描述"
    real_answer = str(row["answer"]).strip() if pd.notna(row["answer"]) else "无真实答案"
    model_response = str(row["result"]).strip() if pd.notna(row["result"]) else "无模型响应"

    # 调用模型验证一致性
    score, reason = verify_answer_consistency(question, real_answer, model_response)
    cost_time = time.time() - start_time
    return {"Result": score, "Reason": reason}