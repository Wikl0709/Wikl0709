import time
import json
import logging
import re
import os
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from openai import AzureOpenAI

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------
# Azure OpenAI 配置
# -----------------------------
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://llm-east-us2-test.openai.azure.com/")
AZURE_SUBSCRIPTION_KEY = os.getenv("AZURE_OPENAI_KEY",
                                   "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
TEMPERATURE = 0.0
MAX_COMPLETION_TOKENS = 512


# -----------------------------
# 异常类定义
# -----------------------------
class TransientAPIError(Exception):
    """用于触发 tenacity 重试的临时错误类型"""
    pass


# -----------------------------
# Azure OpenAI 客户端
# -----------------------------
def build_client():
    """构建 Azure OpenAI 客户端"""
    return AzureOpenAI(
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_SUBSCRIPTION_KEY,
    )


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(TransientAPIError)
)
def call_model_with_retry(client, messages):
    """
    带自动重试的模型调用
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

    # usage 抽取
    usage_dict = {}
    try:
        usage = getattr(rsp, "usage", None)
        if usage:
            usage_dict["input_tokens"] = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)
            usage_dict["output_tokens"] = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens",
                                                                                           None)
            usage_dict["total_tokens"] = getattr(usage, "total_tokens", None)

        # 如果属性不可用，尝试序列化到 dict
        if not usage_dict.get("input_tokens") or not usage_dict.get("output_tokens"):
            if hasattr(rsp, "model_dump_json"):
                d = json.loads(rsp.model_dump_json())
                u = d.get("usage", {})
                usage_dict["input_tokens"] = u.get("input_tokens") or u.get("prompt_tokens")
                usage_dict["output_tokens"] = u.get("output_tokens") or u.get("completion_tokens")
                usage_dict["total_tokens"] = u.get("total_tokens")
    except Exception:
        usage_dict = {"input_tokens": None, "output_tokens": None, "total_tokens": None}

    return {"content": content, "usage": usage_dict}


def generate(messages):
    """
    使用 Azure OpenAI 模型生成文本。
    """
    starttime = time.time()

    try:
        # 构建客户端
        client = build_client()

        # 调用模型
        api_result = call_model_with_retry(client, messages)

        # 提取结果
        output_text = api_result["content"]
        usage_dict = api_result.get("usage", {})

        # 提取token使用量
        prompt_tokens = usage_dict.get("input_tokens", 0) or usage_dict.get("prompt_tokens", 0)
        completion_tokens = usage_dict.get("output_tokens", 0) or usage_dict.get("completion_tokens", 0)
        total_tokens = usage_dict.get("total_tokens", 0)

        # 如果没有获取到token数，尝试估算
        if prompt_tokens == 0:
            prompt_tokens = estimate_tokens(messages)
        if completion_tokens == 0:
            completion_tokens = estimate_tokens([{"content": output_text}])
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        duration = round(time.time() - starttime, 2)

        logger.info(
            f"API调用完成，耗时: {duration}秒，使用Token: {total_tokens} (输入: {prompt_tokens}, 输出: {completion_tokens})")

        return {
            'completion': output_text,
            'output_text': output_text,
            'prompt_or_messages': messages,
            'response': api_result,
            'duration': duration,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens
        }

    except Exception as e:
        duration = round(time.time() - starttime, 2)
        logger.error(f"API调用失败: {e}")

        return {
            'completion': '',
            'output_text': "",
            'prompt_or_messages': messages,
            'response': f"Error: {e}",
            'duration': duration,
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0
        }


def estimate_tokens(data):
    """
    简单估算token数
    """
    if isinstance(data, list):
        text = " ".join([str(item.get("content", "")) for item in data if isinstance(item, dict)])
    elif isinstance(data, dict):
        text = str(data.get("content", ""))
    else:
        text = str(data)

    # 简单估算：英文大约4个字符一个token，中文大约2个字符一个token
    # 这是一个粗略的估算，实际token数由模型的分词器决定
    char_count = len(text)

    # 判断文本中中文字符的比例
    chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
    chinese_ratio = chinese_chars / max(char_count, 1)

    if chinese_ratio > 0.5:  # 主要是中文
        estimated_tokens = char_count // 2
    else:  # 主要是英文
        estimated_tokens = char_count // 4

    return max(estimated_tokens, 1)


def create_evaluation_prompt(question, result):
    """
    创建评估提示词 - 增强版本
    """
    prompt = f"""这是一段用户与AI Agent的会话，请按照以下规则，从用户体验的角度判断这轮对话中AI  Agent的回答是否可以接受，是否正确。

【评估规则】
1. AI Agent的回复是否与用户输入具有关联性
2. AI Agent的回复内容中的事实是否有明显的事实错误
3. 忽略AI Agent的回复中的json格式问题


【重要要求】
- 请只输出JSON格式，不要有任何其他文字、解释或标记
- JSON必须严格遵循下面的格式
- 不要使用markdown代码块标记
- 确保JSON格式正确，可以直接被解析

【输出格式】
{{
    "is_correct": true/false,
    "confidence": "高/中/低",
    "explanation": "详细解释",
    "correct_answer": "如果是错误的，请提供正确答案"
}}

【待评估数据】
User Query：{question} （用户实际输入）
AI Agent：{result}（AI Agent的回答）

现在请只输出JSON："""

    return prompt


def parse_evaluation_result(output_text):
    """
    解析评估结果，如果失败则尝试清理和重试
    """
    # 第一次尝试直接解析
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        logger.warning("第一次JSON解析失败，尝试清理文本")

    # 尝试清理文本：移除可能的markdown代码块标记
    cleaned_text = output_text.strip()

    # 移除markdown代码块标记
    if cleaned_text.startswith('```json'):
        cleaned_text = cleaned_text[7:]
    elif cleaned_text.startswith('```'):
        cleaned_text = cleaned_text[3:]

    if cleaned_text.endswith('```'):
        cleaned_text = cleaned_text[:-3]

    cleaned_text = cleaned_text.strip()

    # 修复双引号移义问题 - 将 "" 替换为 "
    cleaned_text = cleaned_text.replace('""', '"')

    # 第二次尝试解析清理后的文本
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logger.warning(f"清理后JSON解析仍然失败: {e}")

    # 尝试提取JSON对象
    try:
        # 查找第一个{和最后一个}
        start = cleaned_text.find('{')
        end = cleaned_text.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = cleaned_text[start:end]
            # 再次修复双引号移义
            json_str = json_str.replace('""', '"')
            return json.loads(json_str)
    except Exception as e:
        logger.warning(f"提取JSON对象失败: {e}")

    # 尝试使用正则表达式修复常见JSON格式问题
    try:
        # 修复布尔值格式
        fixed_text = re.sub(r':\s*true\b', ': true', cleaned_text, flags=re.IGNORECASE)
        fixed_text = re.sub(r':\s*false\b', ': false', fixed_text, flags=re.IGNORECASE)
        fixed_text = re.sub(r':\s*null\b', ': null', fixed_text, flags=re.IGNORECASE)

        # 修复字符串引号问题
        fixed_text = re.sub(r'(\w+)\s*:', r'"\1":', fixed_text)

        return json.loads(fixed_text)
    except Exception as e:
        logger.warning(f"正则修复JSON失败: {e}")

    # 如果所有方法都失败，返回空结果
    logger.error("所有JSON解析方法都失败")
    return {
        "is_correct": None,
        "confidence": "未知",
        "explanation": "JSON解析失败",
        "correct_answer": ""
    }


def evaluate_single_qa(question, result, max_retries=2):
    """
    评估单个问答对，包含重试机制
    """
    prompt = create_evaluation_prompt(question, result)
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(max_retries + 1):
        api_result = generate(messages)
        output_text = api_result['output_text']

        # 尝试解析结果
        eval_data = parse_evaluation_result(output_text)

        # 如果解析成功，返回结果
        if eval_data.get("is_correct") is not None:
            return {
                **api_result,
                "eval_data": eval_data,
                "attempts": attempt + 1
            }

        # 如果最后一次尝试仍然失败，记录错误
        if attempt == max_retries:
            logger.error(f"经过{max_retries + 1}次尝试后仍然无法解析JSON")
            return {
                **api_result,
                "eval_data": {
                    "is_correct": None,
                    "confidence": "解析失败",
                    "explanation": f"经过{max_retries + 1}次尝试后JSON解析仍然失败",
                    "correct_answer": ""
                },
                "attempts": attempt + 1
            }

        logger.info(f"第{attempt + 1}次尝试失败，进行重试...")
        time.sleep(1)  # 重试前等待1秒


def evaluate_single_input(input_data):
    """
    评估单个输入字典（包含question和result字段）

    Args:
        input_data: 字典，包含'question'和'result'字段
            {
                'question': '问题内容',
                'result': '回答内容'
            }

    Returns:
        评估结果字典，包含所有评估字段
    """
    try:
        # 从输入字典中提取question和result
        question = input_data.get('question', '')
        result = input_data.get('result', '')

        if not question or not result:
            logger.error("输入数据缺少question或result字段")
            return {
                'error': '输入数据缺少question或result字段',
                'eval_prompt': '',
                'eval_result': '',
                'eval_is_correct': '',
                'eval_confidence': '',
                'eval_explanation': '',
                'eval_correct_answer': '',
                'eval_output_text': '',
                'eval_prompt_tokens': 0,
                'eval_completion_tokens': 0,
                'eval_total_tokens': 0,
                'eval_duration': 0.0,
                'eval_attempts': 0
            }

        logger.info(f"开始评估: {question[:50]}...")

        # 评估单个问答对
        eval_result = evaluate_single_qa(question, result)

        # 获取评估提示词
        eval_prompt = create_evaluation_prompt(question, result)

        # 解析评估结果
        eval_data = eval_result['eval_data']
        eval_result_json = json.dumps(eval_data, ensure_ascii=False)

        # 构建返回的评估结果
        row_eval_data = {
            'eval_prompt': eval_prompt,
            'eval_result': eval_result_json,
            'eval_is_correct': eval_data.get('is_correct', ''),
            'eval_confidence': eval_data.get('confidence', ''),
            'eval_explanation': eval_data.get('explanation', ''),
            'eval_correct_answer': eval_data.get('correct_answer', ''),
            'eval_output_text': eval_result['output_text'],
            'eval_prompt_tokens': eval_result['prompt_tokens'],
            'eval_completion_tokens': eval_result['completion_tokens'],
            'eval_total_tokens': eval_result['total_tokens'],
            'eval_duration': eval_result['duration'],
            'eval_attempts': eval_result.get('attempts', 1)
        }

        logger.info(f"评估完成: is_correct={eval_data.get('is_correct')}")
        return row_eval_data

    except Exception as e:
        logger.error(f"评估过程中出错: {e}")
        return {
            'error': str(e),
            'eval_prompt': '',
            'eval_result': '',
            'eval_is_correct': '',
            'eval_confidence': '',
            'eval_explanation': '',
            'eval_correct_answer': '',
            'eval_output_text': '',
            'eval_prompt_tokens': 0,
            'eval_completion_tokens': 0,
            'eval_total_tokens': 0,
            'eval_duration': 0.0,
            'eval_attempts': 0
        }


def evaluate_multiple_inputs(input_list):
    """
    评估多个输入数据

    Args:
        input_list: 字典列表，每个字典包含'question'和'result'字段

    Returns:
        评估结果列表
    """
    all_eval_results = []

    for index, input_data in enumerate(input_list):
        logger.info(f"正在处理第{index + 1}条数据...")

        # 评估单个输入
        eval_result = evaluate_single_input(input_data)
        all_eval_results.append(eval_result)

        # 添加延时避免频繁调用
        time.sleep(1)

    logger.info(f"所有数据评估完成，共处理{len(all_eval_results)}条记录")
    return all_eval_results


def main(input_data):
    """
    主函数 - 根据输入类型进行评估

    Args:
        input_data: 可以是单个字典或字典列表
            单个字典: {'question': '...', 'result': '...'}
            字典列表: [{'question': '...', 'result': '...'}, ...]

    Returns:
        评估结果列表
    """
    logger.info("开始问答对评估...")

    # 根据输入类型调用不同的评估函数
    if isinstance(input_data, dict):
        # 单个字典输入
        logger.info("输入类型: 单个字典")
        eval_result = evaluate_single_input(input_data)
        return eval_result
        # final_result = [eval_result]  # 包装成列表以保持返回类型一致
    elif isinstance(input_data, list):
        # 字典列表输入
        logger.info(f"输入类型: 列表，包含{len(input_data)}个字典")
        final_result = evaluate_multiple_inputs(input_data)
    else:
        logger.error(f"不支持的输入类型: {type(input_data)}")
        final_result = [{
            'error': f'不支持的输入类型: {type(input_data)}，请输入字典或字典列表'
        }]

    if final_result and 'error' not in final_result[0]:
        print(f"评估完成！成功处理 {len(final_result)} 条记录")

    # 返回评估结果列表
    return final_result


if __name__ == "__main__":
    single_input = {
        'question': 'What is the capital of France?',
        'result': 'message:The capital of France is Paris.,intent:general_generation'
    }

    final_result_single = main(single_input)
    print(f"final_result:{final_result_single}")