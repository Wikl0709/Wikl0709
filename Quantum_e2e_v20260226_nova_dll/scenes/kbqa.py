# scenes/kbqa.py
import time
import logging
import ast
import re
from typing import Dict
from openai import AzureOpenAI
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from rouge import Rouge
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

logging.basicConfig(level=logging.INFO)

# ===== 独立配置 =====
endpoint = 'https://llm-east-us2-test.openai.azure.com/'
subscription_key = 'A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY'

# 初始化全局客户端
client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=endpoint,
    api_key=subscription_key,
)
rouge = Rouge()

# 线程锁（用于线程安全的打印）
print_lock = Lock()


# ============ KB检索评估相关辅助函数 ============

def clean_string_for_xml(s):
    """移除所有非打印字符"""
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', s)


def clean_string(s):
    """删除字符串开头和结尾的空格、方括号和标点符号"""
    cleaned = s.strip()
    cleaned = cleaned.strip('[]')
    cleaned = re.sub(r'[^\w\s]', '', cleaned)
    return cleaned


def remove_punctuation(text):
    """删除标点符号"""
    return re.sub('[^\w\s]', '', text)


def longest_common_substring(s1, s2):
    """计算两个字符串的最长公共子串"""
    m, n = len(s1), len(s2)
    max_len = 0
    end = 0
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
                if dp[i][j] > max_len:
                    max_len = dp[i][j]
                    end = i
            else:
                dp[i][j] = 0
    
    return s1[end - max_len:end]


def text_similarity(references, candidate):
    """计算文本相似度"""
    all_len = 0
    all_lcs_len = 0
    
    for reference in references:
        lcs = longest_common_substring(reference, candidate)
        all_lcs_len += len(lcs)
        all_len += len(reference)
    
    similarity = 1.0 * all_lcs_len / all_len if all_len > 0 else 0
    return '', similarity


def chunk_eval_comp_map(eval_ls):
    """将评估结果映射为数值"""
    value_ls = []
    for eval in eval_ls:
        if "Alternative answer in chunk" in eval:
            value_ls.append(4)
        elif "All reference text in chunk" in eval or "Reference answer in chunk" in eval:
            value_ls.append(5)
        elif eval == "0分":
            value_ls.append(0)
        elif eval == "1分":
            value_ls.append(1)
        else:
            value_ls.append('error')
    return value_ls


def result_find(strings):
    """从字符串中提取评估结果"""
    patterns = [
        r"Rate: (.*)",
        r"\*\*Rate:\*\* (.*)",
        r"\*\*Rate\*\*: (.*)",
        r"Rate:(.*)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, str(strings))
        if match:
            return match.group(1).strip()
    
    return "No match found"


def ask_gpt(prompt, deployment="o4-mini", max_retries=3):
    """调用 GPT 模型"""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                max_completion_tokens=100000,
                model=deployment
            )
            
            response_text = response.choices[0].message.content
            res1 = str(response_text).replace("```json", "").replace("```", "").strip()
            return res1
            
        except Exception as e:
            with print_lock:
                print(f"GPT 调用失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise


def all_details_check(query, ref_answer, ref_text, retrieved_chunk):
    """检查检索块是否包含所需信息"""
    prompt = f"""
You are an expert retrieval evaluator.
You are given a question, a reference answer, a reference text, and a retrieval chunk, and evaluate the retrieval chunk falls into which of the following categories:

# Rules 
1. "All reference text in chunk" means that the reference text is entirely included within the retrieval chunk (Note: This should be evaluated literally, not semantically).--exact match
2. "Reference answer in chunk" means the reference answer can be obtained directly or indirectly from the content of the retrieval chunk, answering the question.
3. "Alternative answer in chunk" means the retrieval chunk is inconsistent with the reference text and reference answer, but the retrieval chunk contains content that can answer the question
    (Notes: As long as the retrieval chunk contains content that can answer the question, it's okay if it's different from the reference text).
4. If none of the above rules are satisfied, please rate the retrieval chunk:
  "0分" means the retrieval chunk is irrelevant with the question.
  "1分" means the retrieval chunk is partly related to the question.

Before evaluating the category of the retrieval chunk, please provide the rationale for your assessment 
using the terms "All reference text in chunk", "Reference answer in chunk", "Alternative answer in chunk", "0分", "1分". 

# Question 
{query} 

# Reference answer 
{ref_answer}

# Reference text
{ref_text}

# Retrieval chunk 
{retrieved_chunk} 

# Output Format: 
Thought: [Reason of your evaluation result] 
Rate: [All reference text in chunk/Reference answer in chunk/Alternative answer in chunk/0分/1分]
"""
    
    return ask_gpt(prompt)


def evaluate_single_chunk(row, k, topk=3):
    """评估单个检索块"""
    try:
        # 解析检索结果列表
        if isinstance(row.get('search_file_list'), str):
            searched_files_list = ast.literal_eval(row['search_file_list'])
        else:
            searched_files_list = row.get('search_file_list', [])
        
        if isinstance(row.get('search_text_list'), str):
            searched_text_list = ast.literal_eval(row['search_text_list'])
        else:
            searched_text_list = row.get('search_text_list', [])
    except Exception as e:
        with print_lock:
            print(f"解析检索列表失败: {e}")
        return 'fail'
    
    # 检查是否有检索结果
    if not searched_files_list or not searched_text_list:
        return 'fail'
    
    # 检查是否有足够的检索结果
    if len(searched_files_list) < k + 1 or len(searched_text_list) < k + 1:
        return 'fail'
    
    gt_file = row.get('gt_file', '')
    
    # 处理表格文件
    if any(ext in str(gt_file) for ext in ['.xlsx', '.xls', '.csv']):
        return_results = searched_files_list[k] + ' ' + searched_text_list[k]
        return 'pass' if return_results == gt_file else 'fail'
    
    # 处理文本文件
    return evaluate_text_file(row, searched_text_list, k)


def evaluate_text_file(row, searched_text_list, k):
    """评估文本文件检索结果"""
    gt_text = str(row.get('gt_text', ''))
    
    # 预处理参考文本
    gt_text_list = [
        remove_punctuation(t.replace(" ", "").replace("\t", "").replace("\r", ""))
        for t in gt_text.split('\n')
    ]
    
    gt_text_list1 = [
        remove_punctuation(t.replace("\t", "").replace("\r", ""))
        for t in gt_text.split('\n')
    ]
    
    gt_text1 = ''.join(gt_text_list1)
    
    # 预处理检索文本
    try:
        searched_text = remove_punctuation(
            searched_text_list[k].replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "")
        )
        searched_text1 = remove_punctuation(
            searched_text_list[k].replace("\n", "").replace("\t", "").replace("\r", "")
        )
    except:
        searched_text = ''
        searched_text1 = ''
    
    # 计算文本相似度
    _, lcs_similarity = text_similarity(gt_text_list, searched_text)
    
    # 计算 ROUGE 分数
    semantic_score = 0
    if searched_text1 and gt_text1:
        try:
            max_len = 1000
            text1 = searched_text1[:max_len] if len(searched_text1) >= max_len else searched_text1
            text2 = gt_text1[:max_len] if len(gt_text1) >= max_len else gt_text1
            
            if text1 and text2:
                scores = rouge.get_scores(text1, text2, avg=True)
                semantic_score = scores['rouge-l']['r']
        except Exception as e:
            with print_lock:
                print(f"ROUGE 计算失败: {str(e)}")
            semantic_score = 0
    
    # 如果相似度足够高，直接返回 pass
    if lcs_similarity >= 0.4 or semantic_score >= 0.4:
        return 'pass'
    
    # 使用 GPT 进行详细评估
    return evaluate_with_gpt(row, searched_text_list[k])


def evaluate_with_gpt(row, searched_text):
    """使用 GPT 进行详细评估"""
    chunk_eva_complete_ls = []
    times = 0
    max_times = 1
    
    while times < max_times:
        chunk_eva_complete = all_details_check(
            row.get('question', ''),
            row.get('answer', ''),
            row.get('gt_text', ''),
            searched_text
        )
        
        chunk_eva_com_clean = clean_string(result_find(chunk_eva_complete))
        
        # 检查是否得到有效结果
        if any(keyword in chunk_eva_com_clean for keyword in [
            "All reference text in chunk",
            "Reference answer in chunk",
            "Alternative answer in chunk"
        ]):
            break
        
        times += 1
    
    chunk_eva_complete_ls.append(chunk_eva_com_clean)
    comp_eva_value = chunk_eval_comp_map(chunk_eva_complete_ls)
    
    return 'pass' if comp_eva_value[0] in [4, 5] else 'fail'


def _evaluate_chunk_wrapper(row, k, topk):
    """
    包装函数：用于并发执行单个chunk的评估
    
    Args:
        row: 数据行
        k: chunk索引
        topk: 总数量
        
    Returns:
        (k, result) 元组
    """
    try:
        result = evaluate_single_chunk(row, k, topk)
        with print_lock:
            print(f"  [KB检索评估] Top-{k+1} 结果: {result}")
        return (k, result)
    except Exception as e:
        with print_lock:
            print(f"  [KB检索评估] Top-{k+1} 评估失败: {str(e)}")
        return (k, 'fail')


# ============ 业务函数1：知识库检索评估（并发版本）============

def evaluate_kb_retrieval(row: Dict, max_workers: int = 5):
    """
    评估知识库检索结果（并发版本）
    
    Args:
        row: 数据行（字典），需包含以下字段：
            - search_file_list: 检索文件列表
            - search_text_list: 检索文本列表
            - gt_file: 标准文件
            - gt_text: 标准文本
            - question: 问题
            - answer: 标准答案
            - CURRENT_INTENT_RECOGNITION: 意图识别结果（可选）
            - test_mode: 测试模式 ('cloud' 或 'local')
        max_workers: 最大并发线程数
        
    Returns:
        - cloud模式: 1 (pass) 或 0 (fail)
        - local模式: 'pass' 或 'fail'
        - 跳过评估: ''
    """
    final_result = ''
    try:
        # 检查是否需要评估（如果toolname列不包含Searching Knowledge字段 则跳过）
        if row.get('toolname') and str(row.get('toolname')).lower().find('searching knowledge') == -1:
            print("[KB检索评估] 跳过：存在意图识别结果")
            return ''
        
        # 检查是否有检索数据
        if not row.get('search_file_list') or not row.get('search_text_list'):
            print("[KB检索评估] 跳过：缺少检索数据")
            return ''
        
        # 根据测试模式确定topk
        topk = 10
        if row.get("test_mode") == "cloud":
            topk = 10
        elif row.get("test_mode") == "local":
            topk = 3
        
        print(f"[KB检索评估] 开始并发评估 (topk={topk}, max_workers={max_workers})")
        start_time = time.time()
        
        # ============ 并发评估 top-k 个检索结果 ============
        tool_result_dict = {}  # 使用字典存储结果，保持顺序
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = {
                executor.submit(_evaluate_chunk_wrapper, row, k, topk): k
                for k in range(topk)
            }
            
            # 收集结果
            for future in as_completed(futures):
                k, result = future.result()
                tool_result_dict[k] = result
        
        # 按顺序提取结果
        tool_result_list = [tool_result_dict[k] for k in sorted(tool_result_dict.keys())]
        
        elapsed_time = time.time() - start_time
        print(f"[KB检索评估] 并发评估完成，耗时: {elapsed_time:.2f}秒")
        
        # 判断最终结果（只要有一个 pass 就算 pass）
        has_pass = any(x.lower() == 'pass' for x in tool_result_list)
        final_result = 'pass' if has_pass else 'fail'

    except Exception as e:
        print(f"[KB检索评估] 异常: {str(e)}")
        final_result = 'fail'
    
    # 根据模式返回不同格式
    if row.get("test_mode") == "cloud":
        final_result = 1 if final_result == "pass" else 0

    print(f"[KB检索评估] 最终结果: {final_result}")
    return final_result


# ============ 业务函数2：答案质量评估 ============

def evaluate_answer_quality(row: Dict, deployment: str = "o4-mini") -> Dict:
    """
    评估答案质量（包括拒答检测和答案正确性评估）
    
    Args:
        row: 数据行（字典），需包含以下字段：
            - question: 问题
            - answer: 标准答案
            - result: 模型返回结果
            - 问题类型: 问题类型（可选）
        deployment: 使用的模型部署名称
        
    Returns:
        字典，包含以下字段：
            - Result: 0=失败, 1=通过, ''=格式错误
            - Reason: 失败原因或评估理由
    """
    query = "" if row.get("question") is None else str(row.get("question"))
    answer = "" if row.get("answer") is None else str(row.get("answer"))
    result = "" if row.get("result") is None else str(row.get("result"))
    query_type = "" if row.get("问题类型") is None else str(row.get("问题类型"))

    # 检查特殊错误情况
    if result == "CTTVError: Empty response from server":
        return {"Result": 0, "Reason": "接口返回为空"}
    elif result == "CTTVError: Request Timeout":
        return {"Result": 0, "Reason": "接口返回超时"}
    elif str(result).startswith("CTTVError: Task failed -"):
        return {"Result": 0, "Reason": "接口返回failed错误"}

    # 检查问题是否为空
    if not query or query.lower() == "nan":
        return {"Result": 0, "Reason": "EmptyQuestion"}

    # ============ 1. 拒答检测 ============
    print("\n[答案质量评估] 步骤1: 拒答检测")
    
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
                "content": [{"type": "text", "text": "{<Result: No>}"}]
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "<Sure, how can I help you?>"}]
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "{<Result: No>}"}]
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "<Sorry, I am unable to provide assistance at this time.>"}]
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "{<Result: Yes>}"}]
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": result}]
            }
        ],
        max_completion_tokens=100000,
    )

    # 获取拒答检测结果
    for _ in range(3):
        try:
            response_text = response.choices[0].message.content
            break
        except:
            response_text = response.choices[0].message.content
    
    print(f"[答案质量评估] 拒答检测结果: {response_text}")
    
    # ============ 2. 根据拒答结果进行后续评估 ============
    if 'No' in response_text:
        # 没有拒答，评估答案正确性
        print('[答案质量评估] 步骤2: 答案正确性评估')
        
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

        for _ in range(3):
            try:
                response_text_final = response.choices[0].message.content
                break
            except:
                response_text_final = response.choices[0].message.content
        
        print(f"[答案质量评估] 正确性评估结果: {response_text_final}")
        
        try:
            reason = re.search(r'reason:([^,}]+)', response_text_final).group(1)
        except:
            reason = response_text_final
        
        # 判断结果
        if '{<Result: pass>}' in response_text_final or ('pass' in response_text_final and 'pass*>' not in response_text_final and 'fail' not in response_text_final):
            return {"Result": 1, "Reason": reason}
        elif '{<Result: pass*>}' in response_text_final or ('pass*' in response_text_final and 'pass*>' not in response_text_final):
            return {"Result": 1, "Reason": reason}
        elif '{<Result: fail>}' in response_text_final or 'fail' in response_text_final:
            return {"Result": 0, "Reason": reason}
        else:
            print('[答案质量评估] LLM返回格式不规范')
            return {"Result": '', "Reason": "LLM返回格式不规范"}
            
    elif 'Yes' in response_text:
        # 检测到拒答
        print('[答案质量评估] 检测到拒答')
        if query_type == "错误前提":
            return {"Result": 1, "Reason": "正确拒答错误前提问题"}
        else:
            return {"Result": 0, "Reason": "模型拒答"}
    else:
        print('[答案质量评估] LLM拒答返回格式不规范')
        return {"Result": 0, "Reason": "LLM拒答返回格式不规范"}


# ============ 主函数：整合两个业务函数 ============

def main(row: Dict) -> Dict:
    """
    KBQA 场景的主评估函数
    
    Args:
        row: 包含以下字段的字典
            - question: 问题
            - answer: 标准答案
            - result: 模型返回结果
            - 问题类型: 问题类型（可选）
            - search_file_list: 检索文件列表（用于KB检索评估，可选）
            - search_text_list: 检索文本列表（用于KB检索评估，可选）
            - gt_file: 标准文件（用于KB检索评估，可选）
            - gt_text: 标准文本（用于KB检索评估，可选）
            - test_mode: 测试模式 ('cloud' 或 'local')
            
    Returns:
        包含以下字段的字典：
            - Result: 0=失败, 1=通过, ''=格式错误
            - Reason: 失败原因或评估理由
            - Retrieval_Check: KB检索评估结果 (cloud模式下为1/0，local模式下为'pass'/'fail'/'')
    """
    start_time = time.time()
    
    # ============ 业务2：答案质量评估 ============
    try:
        answer_quality_result = evaluate_answer_quality(row, deployment="o4-mini")
    except Exception as e:
        print(f"[答案质量评估] 异常: {str(e)}")
        answer_quality_result = {"Result": 0, "Reason": f"评估异常: {str(e)}"}
    
    # ============ 整合结果 ============
    if row.get("test_mode") == "cloud":
        # cloud模式：执行KB检索评估（并发）
        kb_retrieval_result = evaluate_kb_retrieval(row, max_workers=5)  # 可调整并发数
        final_result = {
            "Result": answer_quality_result.get("Result", 0),
            "Reason": answer_quality_result.get("Reason", ""),
            "Retrieval_Check": kb_retrieval_result
        }
        print(f"  - 答案评估: Result={final_result['Result']}, Reason={final_result['Reason']}")
        print(f"  - KB检索: {final_result['Retrieval_Check']}")
        
    else:
        # local模式：不执行KB检索评估
        final_result = {
            "Result": answer_quality_result.get("Result", 0),
            "Reason": answer_quality_result.get("Reason", "")
        }
        print(f"  - 答案评估: Result={final_result['Result']}, Reason={final_result['Reason']}")
    
    elapsed_time = time.time() - start_time
    print(f"\n[评估完成] 总耗时: {elapsed_time:.2f}秒")
    
    return final_result
