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
    )
    
    response_text = response.choices[0].message.content
    
    if 'No' in response_text:
        print('没有拒答')
        response = client.chat.completions.create(
            messages=[
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
        print(response_text_final)
        
        # 修复原始代码中的逻辑错误：'pass' in response_text_final 而不是完全相等
        if '{<Result: pass>}' in response_text_final or 'pass' in response_text_final and 'pass*>' not in response_text_final and 'fail' not in response_text_final:
            return {"Result": 1, "Reason": ""}
        elif '{<Result: pass*>}' in response_text_final or ('pass*' in response_text_final and 'pass*>' not in response_text_final):
            return {"Result": 1, "Reason": ""}  # 根据原始逻辑，pass* 也是通过的
        elif '{<Result: fail>}' in response_text_final or 'fail' in response_text_final:
            reason = re.search(r'reason:([^,}]+)', response_text_final).group(1)
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
        return {"Result": '', "Reason": "LLM拒答返回格式不规范"}