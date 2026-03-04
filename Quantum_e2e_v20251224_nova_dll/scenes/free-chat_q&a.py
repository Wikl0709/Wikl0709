import time
import json
import logging
import re
from openai import OpenAI

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def generate(messages):
    """
    使用 OpenRouter API 调用 DeepSeek-V3-0324 模型生成文本。
    """
    starttime = time.time()
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="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",
    )
    try:
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "",
                "X-Title": "",
            },
            extra_body={},
            model="deepseek/deepseek-r1",
            messages=messages,
            seed=10000
        )
        output_text = completion.choices[0].message.content
        ori_response = completion

        # 提取token使用量
        if hasattr(completion, 'usage') and completion.usage:
            prompt_tokens = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens
            total_tokens = completion.usage.total_tokens
        else:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

    except Exception as e:
        completion = ''
        output_text = ""
        ori_response = f"Error: {e}"
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        logger.error(f"API调用失败: {e}")

    duration = round(time.time() - starttime, 2)
    logger.info(
        f"API调用完成，耗时: {duration}秒，使用Token: {total_tokens} (输入: {prompt_tokens}, 输出: {completion_tokens})")

    return {
        'completion': completion,
        'output_text': output_text,
        'prompt_or_messages': messages,
        'response': ori_response,
        'duration': duration,
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens
    }


def create_evaluation_prompt(question, result):
    """
    创建评估提示词 - 增强版本
    """
    prompt = f"""请你扮演一个质量评估专家的角色，帮我判断以下问答对中"result"字段的回答是否正确。

【评估规则】
1. 对于事实性问题：检查事实准确性
2. 对于翻译问题：检查翻译是否准确、自然
3. 对于代码问题：检查代码语法和逻辑是否正确
4. 对于数学问题：检查计算过程和结果是否正确
5. 对于指令跟随：检查是否完整准确地执行了指令

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
问题：{question}
回答：{result}

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
        'question': '什么是Python？',
        'result': 'Python是一种高级编程语言'
    }

    final_result_single = main(single_input)
    print(f"final_result:{final_result_single}")

