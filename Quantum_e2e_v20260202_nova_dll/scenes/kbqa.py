# scenes/kbqa.py
import time
import logging
import os
from typing import Dict
from openai import AzureOpenAI
import re

logging.basicConfig(level=logging.INFO)

# ===== 独立配置 =====
endpoint = 'https://llm-east-us2-test.openai.azure.com/'
subscription_key = 'A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY'


def main(row: Dict) -> Dict:
    start_time = time.time()
    query_type = row['问题类型']
    query = row["question"]
    answer = row["answer"]
    result = row["result"]

    if not query or query.lower() == "nan":
        return {"Result": 0, "Reason": "EmptyQuestion"}

    deployment = "o4-mini"
    client = AzureOpenAI(
        api_version="2024-12-01-preview",
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )

    # 1. 拒答检测
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Task: Evaluate whether the provided content is a refusal to answer.\n"
                            "Process: Follow the steps below and respond in English only.\n\n"
                            "Step 1: The user will provide input in the format: <content>.\n"
                            "Step 2: Determine whether <content> is a refusal to answer, such as:\n"
                            "1) Apologizing and stating inability to answer.\n"
                            "2) Saying the information cannot be provided.\n"
                            "3) Declining to answer and asking the user to ask something else.\n\n"
                            "If the content is a refusal, output exactly: {<Result: Yes>}.\n"
                            "Otherwise, output exactly: {<Result: No>}."
                        )
                    }
                ]
            },

            # ===== Example 1: NOT a refusal =====
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "<AI and psychological assessment are closely connected. Structured theories and data models form the foundation of psychological testing, where results are interpreted using normative references.>"
                    }
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "{<Result: No>}"
                    }
                ]
            },

            # ===== Example 2: Polite offer, still NOT a refusal =====
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "<Sure, how can I help you?>"
                    }
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "{<Result: No>}"
                    }
                ]
            },

            # ===== Example 3: Explicit refusal =====
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "<Sorry, I am unable to provide assistance at this time.>"
                    }
                ]
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "{<Result: Yes>}"
                    }
                ]
            },

            # ===== Actual content to evaluate =====
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
    )

    for range_num in range(3):
        try:
            response_text = response.choices[0].message.content
            break
        except:
            response_text = response.choices[0].message.content
    
    if 'No' in response_text:
        print('没有拒答')
        SYSTEM_PROMPT = (
            "You are an impartial evaluator.\n\n"
            "[Input]\n"
            "The user provides a single line in the format:\n"
            "<content_1>/<content_2>/<content_3>\n"
            "where:\n"
            "- content_1 = query\n"
            "- content_2 = standard answer\n"
            "- content_3 = returned result\n\n"
            "[Task]\n"
            "Evaluate the returned result (content_3) against the query (content_1) and the standard answer (content_2).\n\n"
            "[Labels]\n"
            "- pass: The returned result matches the standard answer in all relevant aspects. It is factually correct, relevant, complete, clear, and consistent.\n"
            "- pass*: The returned result deviates in one or more relevant aspects (e.g., missing key points, contains incorrect information), but still overlaps with some key points/conclusions.\n"
            "- fail: The returned result does not match the standard answer. It may be factually incorrect, irrelevant, incomplete, ambiguous, or inconsistent.\n\n"
            "[Output]\n"
            "Output exactly one line in the following format (no extra text):\n"
            "{<Result: pass|pass*|fail,reason:xxxxx>,}\n"
        )
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": [{"type": "text", "text": SYSTEM_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "<Who is the president of the United States?>/<Joe Biden.>/<Joe Biden.>"}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "{<Result: pass,reason:xxxxx>,}"}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "<What is the capital of France?>/<Paris.>/<The capital of France is Paris, but it's also known as the City of Light>"}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "{<Result: pass*,reason:xxxxx>,}"}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "<What is the formula for water?>/<H2O.>/<H2O2.>"}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "{<Result: fail,reason:xxxxx>,}"}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": f"<{query}>/<{answer}>/<{result}>"}],
                },
            ],
            max_completion_tokens=100000,
        )


        for range_num in range(3):
            try:
                response_text_final = response.choices[0].message.content
                break
            except:
                response_text_final = response.choices[0].message.content
        print(response_text_final)
        try:
            reason = re.search(r'reason:([^,}]+)', response_text_final).group(1)
        except:
            reason=response_text_final
        # 修复原始代码中的逻辑错误：'pass' in response_text_final 而不是完全相等
        if '{<Result: pass>}' in response_text_final or 'pass' in response_text_final and 'pass*>' not in response_text_final and 'fail' not in response_text_final:
            return {"Result": 1, "Reason": reason}
        elif '{<Result: pass*>}' in response_text_final or ('pass*' in response_text_final and 'pass*>' not in response_text_final):
            return {"Result": 1, "Reason": reason}  # 根据原始逻辑，pass* 也是通过的
        elif '{<Result: fail>}' in response_text_final or 'fail' in response_text_final:
            return {"Result": 0, "Reason": reason}
        else:
            print('LLM返回格式不规范')
            return {"Result": '', "Reason": "LLM返回格式不规范"}
            
    elif 'Yes' in response_text:
        print('拒答')
        if query_type == "错误前提":
            return {"Result": 1, "Reason": ""}
        else:
            return {"Result": 0, "Reason": "模型拒答"}
    else:
        print('LLM拒答返回格式不规范')
        return {"Result": 0, "Reason": "LLM拒答返回格式不规范"}