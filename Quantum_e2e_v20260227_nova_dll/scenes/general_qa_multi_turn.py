
# -*- coding: utf-8 -*-
"""
- 封装为模块：提供 main(row_dict) -> int
- 仅根据 final answer 判决 Task Success Rate (TSR)，并给出简短理由
- 调用 Azure OpenAI Chat Completions（自动重试）
Author: Zimeng
"""
import os
import json
import re
import time
from typing import Tuple, Dict, Any, Optional
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from openai import AzureOpenAI

# -----------------------------
# 固定参数（按需修改/或由环境变量传入）
# -----------------------------
# AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://llm-east-us2-test.openai.azure.com/")
# AZURE_SUBSCRIPTION_KEY = os.getenv("AZURE_OPENAI_KEY", "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY")
# AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
# AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")

AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://llm-east-us2-test.openai.azure.com/")
AZURE_SUBSCRIPTION_KEY = os.getenv("AZURE_OPENAI_KEY", "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")

# AZURE_ENDPOINT = "https://llm-east-us2-test.openai.azure.com/"
# AZURE_KEY = "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY"
# DEPLOYMENT_NAME = "gpt-4.1"
# API_VERSION = "2024-12-01-preview"

# 生成参数
TEMPERATURE = 0.0
MAX_COMPLETION_TOKENS = 512

# -----------------------------
# Prompt：仅判决 TSR
# -----------------------------


SYSTEM_PROMPT = """
You are an answer consistency verification expert.

Task:
First, fully understand the question.
Then, determine whether the model-generated response is semantically consistent with the real_answer.

Scoring criteria:
1) Output Score = 1 if the core meaning of the response matches the real_answer.
   Differences in wording or minor details are allowed.
2) Output Score = 0 if the core meaning differs, the response is irrelevant,
   or key information is missing.

Output STRICT JSON only:
{
 "Task_Success_Rate": 0|1,
 "Rationale": "≤25 words, concise, tied to the final answer wording"
}
No extra keys, no markdown.

"""

USER_PROMPT_TEMPLATE = """
You will verify whether a model response is semantically consistent with the provided real_answer.

# Question (may be multi-turn intent summarized):
{question}

# Model response (the candidate answer to verify):
{result}

# real_answer (ground truth):
{answer}

Return ONLY the JSON object defined in SYSTEM_PROMPT.
"""


# -----------------------------
# AzureOpenAI 客户端 & 自动重试
# -----------------------------
def build_client(
    endpoint: Optional[str] = None,
    key: Optional[str] = None,
    api_version: Optional[str] = None,
) -> AzureOpenAI:
    """允许调用方传入连接参数；若为空则使用模块级常量/环境变量。"""
    return AzureOpenAI(
        api_version=api_version or AZURE_API_VERSION,
        azure_endpoint=endpoint or AZURE_ENDPOINT,
        api_key=key or AZURE_SUBSCRIPTION_KEY,
    )

class TransientAPIError(Exception):
    """用于触发 tenacity 重试的临时错误类型"""
    pass

@retry(
    wait=wait_exponential(multiplier=1, min=1, max=30), # 指数退避：1s -> 2s -> ... -> 30s
    stop=stop_after_attempt(5),                         # 最多重试 5 次
    retry=retry_if_exception_type(TransientAPIError)
)
def call_model_with_retry(client: AzureOpenAI, messages: list) -> Dict[str, Any]:
    """
    带自动重试的模型调用。
    返回 dict：{"content": str, "usage": usage_dict}
    """
    try:
        rsp = client.chat.completions.create(
            messages=messages,
            model=AZURE_DEPLOYMENT,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )
    except Exception as e:
        raise TransientAPIError(f"SDK/Network error: {e}")

    # 响应基础校验
    if not rsp or not getattr(rsp, "choices", None):
        raise TransientAPIError("Invalid response: empty choices")
    msg = rsp.choices[0].message
    content = getattr(msg, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise TransientAPIError("Invalid response content")

    # usage 抽取：兼容不同字段命名
    usage_dict = {}
    try:
        usage = getattr(rsp, "usage", None)
        if usage:
            usage_dict["input_tokens"] = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)
            usage_dict["output_tokens"] = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None)
            usage_dict["total_tokens"]  = getattr(usage, "total_tokens", None)
        # 如果属性不可用，尝试序列化到 dict
        if not usage_dict.get("input_tokens") or not usage_dict.get("output_tokens"):
            if hasattr(rsp, "model_dump_json"):
                d = json.loads(rsp.model_dump_json())
                u = d.get("usage", {})
                usage_dict["input_tokens"] = u.get("input_tokens") or u.get("prompt_tokens")
                usage_dict["output_tokens"] = u.get("output_tokens") or u.get("completion_tokens")
                usage_dict["total_tokens"]  = u.get("total_tokens")
    except Exception:
        usage_dict = {"input_tokens": None, "output_tokens": None, "total_tokens": None}

    return {"content": content, "usage": usage_dict}

# -----------------------------
# 解析模型输出 JSON（仅 TSR + 理由）
# -----------------------------
def parse_tsr(output_text: str) -> Tuple[int, str]:
    """
    解析严格 JSON。
    返回： tsr, rationale
    """
    # 去除可能的```json 包裹
    cleaned = re.sub(r"^```json\s*\n|\n```$", "", output_text.strip(), flags=re.IGNORECASE)
    obj = None
    try:
        obj = json.loads(cleaned)
    except Exception:
        # 尝试提取首个 {...}
        m = re.search(r"\{.*?\}", cleaned, flags=re.DOTALL)
        if not m:
            raise ValueError(f"无法解析模型返回内容（非 JSON）：{output_text}")
        obj = json.loads(m.group(0))

    if "Task_Success_Rate" not in obj or "Rationale" not in obj:
        raise ValueError(f"JSON 缺少字段: {obj}")

    tsr = int(obj["Task_Success_Rate"])
    if tsr not in {0, 1}:
        raise ValueError(f"评分值超范围: {obj}")

    rationale = str(obj["Rationale"]).strip()
    # 可选：截断理由到 ≤25 词（容错；不强制）
    words = rationale.split()
    if len(words) > 25:
        rationale = " ".join(words[:25])
    return tsr, rationale

# -----------------------------
# 对外暴露的单行评分函数（核心封装）
# -----------------------------
def main(row_dict: Dict[str, Any],
              client: Optional[AzureOpenAI] = None) -> int:
    """
    输入：Excel的一行数据（dict），至少包含 'question' 与 'result' 两个键。
    输出：TSR分数（int；1/2/3）

    例：
    row = {"question": "...", "result": "...", "其它列": "..."}
    score = main(row)
    """
    if "question" not in row_dict or "result" not in row_dict or "answer" not in row_dict:
        raise ValueError("缺少必需键：'question' 或 'result'")

    question = str(row_dict["question"])
    result   = str(row_dict["result"])  # final answer
    answer = str(row_dict["answer"]) # gt

    user_prompt = USER_PROMPT_TEMPLATE.format(question=question, result=result, answer=answer)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt}
    ]

    # 构建/复用客户端
    client = client or build_client()

    # 计时（如调用方想做性能统计，可用）
    start = time.time()
    rsp = call_model_with_retry(client, messages)
    output_text = rsp["content"]
    tsr, rationale = parse_tsr(output_text)

    _duration = round(time.time() - start, 3)

    # 如果需要也可以返回理由或耗时；此处按需求仅返回分数
    return {"Task_Success_Rate": tsr, "TSR_Rationale": rationale}

# -----------------------------
# 可选：模块自测（不影响被主函数调用）
# -----------------------------
if __name__ == "__main__":
    # 演示：构造一个行dict并评分
    demo_row = {
        "question": "Not good, create a new one.",
        "result": "Day1:- Morning: Arrive in Shenzhen; check into your hotel (e.g., Mercure Shenzhen North Tower).- Afternoon: Visit the Futian Hi-Tech Zone for an introduction to local tech companies and innovations.- Evening: Dinner at a nearby restaurant, try dim sum or local cuisine.Day2- Breakfast & late morning: Explore the Zhangjiajie National Forest Park (short drive from Shenzhen; visit waterfalls like Tianyun Waterfall).- Lunch in Xinyuan Town (try traditional snacks such as tangyuan dumplings).- Afternoon: Visit Hong Kong-Zhuhai-Macao Bridge for a scenic boat ride to see the coastline.- Evening: Enjoy dinner and nightlife at Nanshan Bay, exploring shopping malls or late-night food options.Day3:- Breakfast & late morning: Take a day trip to Macau (approx.1-hour drive; visit St. Paul's Square, Ruins of A-Ma).- Lunch in Macao.- Afternoon back to Shenzhen for last-minute souvenir shopping at the Futian Hi-Tech Zone or Nanshan Bay.- Evening: Depart from Shenzhen Airport after dinner and return home.",
        "answer": "three-day travel plan in Shenzhen"
    }
    print("TSR =", main(demo_row))
