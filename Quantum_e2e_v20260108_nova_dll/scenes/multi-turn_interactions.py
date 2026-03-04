import time
import json
import logging
import re
from typing import List, Dict, Optional
from openai import OpenAI

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==================== 全局对话历史管理器 ====================
class ConversationHistory:
    """对话历史管理器，用于保存多轮对话的历史记录"""

    def __init__(self):
        self.history: List[Dict] = []  # 存储所有历史对话
        self.current_session_id = None  # 当前会话ID

    def add_turn(self, question: str, result: str, session_id: str = "default"):
        """
        添加一轮对话到历史记录

        Args:
            question: 用户问题
            result: 助手回答
            session_id: 会话ID，用于区分不同的对话会话
        """
        # 如果切换了会话，清空历史
        if self.current_session_id != session_id:
            self.clear_history()
            self.current_session_id = session_id

        turn = {
            'timestamp': time.time(),
            'question': question,
            'result': result,
            'session_id': session_id
        }
        self.history.append(turn)
        logger.info(f"已保存第{len(self.history)}轮对话到会话'{session_id}'")

    def get_context(self, session_id: str = "default", max_turns: Optional[int] = None) -> str:
        """
        获取当前会话的对话上下文

        Args:
            session_id: 会话ID
            max_turns: 最大返回轮次数，None表示返回所有

        Returns:
            上下文字符串
        """
        if self.current_session_id != session_id or not self.history:
            return ""

        # 获取当前会话的历史
        session_history = [turn for turn in self.history if turn.get('session_id') == session_id]

        # 如果指定了最大轮次，只返回最近的对话
        if max_turns is not None and max_turns > 0:
            recent_history = session_history[-max_turns:]
        else:
            recent_history = session_history

        # 构建上下文字符串
        context_parts = []
        for turn in recent_history:
            context_parts.append(f"用户: {turn['question']}")
            context_parts.append(f"助手: {turn['result']}")

        return "\n".join(context_parts)

    def get_full_history(self, session_id: str = "default") -> List[Dict]:
        """获取指定会话的完整历史"""
        if self.current_session_id != session_id:
            return []
        return self.history.copy()

    def clear_history(self, session_id: str = "default"):
        """清空指定会话的历史记录"""
        if session_id == "all" or self.current_session_id == session_id:
            self.history = []
            self.current_session_id = None
            logger.info(f"已清空会话'{session_id}'的历史记录")

    def get_session_info(self, session_id: str = "default") -> Dict:
        """获取会话信息"""
        session_turns = [turn for turn in self.history if turn.get('session_id') == session_id]
        return {
            'session_id': session_id,
            'total_turns': len(session_turns),
            'current_turn': len(self.history),
            'has_history': len(session_turns) > 0
        }


# 创建全局对话历史管理器实例
conversation_history = ConversationHistory()


# ==================== 核心功能函数 ====================
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


def create_evaluation_prompt_multi_turn(question, result, context_info=None):
    """
    创建多轮对话评估提示词
    """
    context_part = ""
    if context_info:
        context_part = f"\n【对话上下文】\n{context_info}\n"

    prompt = f"""请你扮演一个质量评估专家的角色，帮我判断以下多轮对话中当前轮次的回答是否正确。

【评估规则】
1. 对于事实性问题：检查事实准确性
2. 对于翻译问题：检查翻译是否准确、自然
3. 对于代码问题：检查代码语法和逻辑是否正确
4. 对于数学问题：检查计算过程和结果是否正确
5. 对于指令跟随：检查是否完整准确地执行了指令
6. 对于多轮对话：检查是否理解上下文，回答是否连贯一致

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

【待评估数据】{context_part}
当前问题：{question}
当前回答：{result}

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

    # 修复双引号转义问题 - 将 "" 替换为 "
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
            # 再次修复双引号转义
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


def evaluate_single_qa_multi_turn(question, result, context_info=None, max_retries=2):
    """
    评估单个多轮对话问答对，包含重试机制
    """
    prompt = create_evaluation_prompt_multi_turn(question, result, context_info)
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


def create_error_result(error_message):
    """
    创建错误结果
    """
    return {
        'eval_context': '',
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
        'eval_attempts': 0,
        'error': error_message
    }


def evaluate_single_turn(input_data, session_id="default", use_history=True, max_context_turns=None):
    """
    评估单轮对话，自动保存历史并构建上下文

    Args:
        input_data: 字典，包含'question'和'result'字段
        session_id: 会话ID，用于区分不同的对话会话
        use_history: 是否使用历史上下文
        max_context_turns: 最大上下文轮次，None表示使用全部历史

    Returns:
        评估结果字典，包含所有评估字段
    """
    try:
        # 从输入字典中提取question和result
        question = input_data.get('question', '')
        result = input_data.get('result', '')

        if not question or not result:
            logger.error("输入数据缺少question或result字段")
            return create_error_result("输入数据缺少question或result字段")

        # 获取历史上下文
        context_info = None
        if use_history:
            context_info = conversation_history.get_context(session_id, max_context_turns)

        logger.info(
            f"开始第{len(conversation_history.get_full_history(session_id)) + 1}轮对话评估 (会话: {session_id})")
        logger.info(f"问题: {question[:50]}...")

        # 评估单个问答对
        eval_result = evaluate_single_qa_multi_turn(question, result, context_info)

        # 获取评估提示词
        eval_prompt = create_evaluation_prompt_multi_turn(question, result, context_info)

        # 解析评估结果
        eval_data = eval_result['eval_data']
        eval_result_json = json.dumps(eval_data, ensure_ascii=False)

        # 构建返回的评估结果
        evaluation_result = {
            'eval_context': context_info or '',
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
            'eval_attempts': eval_result.get('attempts', 1),
            'session_id': session_id,
            'turn_number': len(conversation_history.get_full_history(session_id)) + 1,
            'context_turns_used': len(conversation_history.get_full_history(session_id)),
            'session_info': conversation_history.get_session_info(session_id)
        }

        # 将当前对话保存到历史记录
        conversation_history.add_turn(question, result, session_id)

        logger.info(f"评估完成: is_correct={eval_data.get('is_correct')}")
        return evaluation_result

    except Exception as e:
        logger.error(f"评估过程中出错: {e}")
        return create_error_result(str(e))


def main(input_data, session_id="default", use_history=True, max_context_turns=None):
    """
    主函数 - 评估多轮对话的单轮输入

    Args:
        input_data: 单个字典，包含'question'和'result'字段
        session_id: 会话ID，用于区分不同的对话会话
        use_history: 是否使用历史上下文
        max_context_turns: 最大上下文轮次，None表示使用全部历史

    Returns:
        评估结果字典，包含所有评估字段
    """
    logger.info("开始多轮对话评估...")

    if isinstance(input_data, dict):
        # 单个字典输入 - 单轮对话评估
        logger.info(f"输入类型: 单个字典（会话: {session_id}）")
        eval_result = evaluate_single_turn(input_data, session_id, use_history, max_context_turns)
        return eval_result
        # final_result = [eval_result]

    elif isinstance(input_data, list) and all(isinstance(item, dict) for item in input_data):
        # 字典列表输入 - 批量处理多个轮次
        logger.info(f"输入类型: 字典列表（批量处理），包含{len(input_data)}轮对话")
        all_results = []
        for turn in input_data:
            result = evaluate_single_turn(turn, session_id, use_history, max_context_turns)
            all_results.append(result)
            time.sleep(1)  # 批量处理时添加延时
        final_result = all_results

    else:
        logger.error(f"不支持的输入类型: {type(input_data)}")
        final_result = [create_error_result(f'不支持的输入类型: {type(input_data)}，请输入字典或字典列表')]

    # 检查是否有错误
    if final_result and 'error' not in final_result[0]:
        correct_count = sum(1 for r in final_result if r.get('eval_is_correct') == True)
        total_count = len(final_result)
        accuracy = correct_count / total_count if total_count > 0 else 0

        print(f"评估完成！本次评估 {total_count} 轮对话，累计正确率: {accuracy:.2%}")
        print(f"会话ID: {session_id}")
        print(f"当前累计对话轮次: {conversation_history.get_session_info(session_id)['total_turns']}")

    return final_result


# ==================== 辅助函数 ====================
def get_conversation_history(session_id="default"):
    """
    获取指定会话的对话历史

    Args:
        session_id: 会话ID

    Returns:
        对话历史列表
    """
    return conversation_history.get_full_history(session_id)


def clear_conversation_history(session_id="default"):
    """
    清空指定会话的对话历史

    Args:
        session_id: 会话ID
    """
    conversation_history.clear_history(session_id)


def get_current_context(session_id="default", max_turns=None):
    """
    获取当前会话的上下文

    Args:
        session_id: 会话ID
        max_turns: 最大返回轮次数

    Returns:
        上下文字符串
    """
    return conversation_history.get_context(session_id, max_turns)


# ==================== 使用示例 ====================
if __name__ == "__main__":
    turn1 = {'question': '什么是Python？', 'result': 'Python是一种高级编程语言'}
    result1 = main(turn1, session_id="python_session")
    print(f"result1: {result1}")

