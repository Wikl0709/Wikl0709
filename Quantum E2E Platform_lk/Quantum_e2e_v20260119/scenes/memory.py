# scenes/memory.py
import time
import logging
import requests
from typing import Dict
import pandas as pd
import threading
from openai import AzureOpenAI

logging.basicConfig(level=logging.INFO)

# ===== 配置区域 =====
# Azure OpenAI 配置
AZURE_ENDPOINT = "https://llm-east-us2-test.openai.azure.com/"
AZURE_KEY = "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY"
DEPLOYMENT_NAME = "gpt-4.1"
API_VERSION = "2024-12-01-preview"

client = AzureOpenAI(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=AZURE_KEY,
    api_version=API_VERSION
)

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
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=0.2,
            max_tokens=500
        )
        
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


# # ===== 测试代码 =====
# if __name__ == "__main__":
#     print("开始测试 memory.py 脚本...")
    
#     # 测试用例1：一致的答案
#     test_row_1 = {
#         "question": "什么是Python编程语言？",
#         "answer": "Python是一种高级编程语言，具有简单易学、可读性强的特点，广泛用于Web开发、数据科学、人工智能等领域。",
#         "result": "Python是一门高级编程语言，具有简单易学和可读性强的特性，被广泛应用于Web开发、数据科学和人工智能等多个领域。"
#     }
    
#     print(f"测试用例1 - 问题: {test_row_1['question']}")
#     print(f"标准答案: {test_row_1['answer']}")
#     print(f"模型响应: {test_row_1['result']}")
    
#     result_1 = main(test_row_1)
#     print(f"测试结果: {result_1}")
#     print("-" * 60)