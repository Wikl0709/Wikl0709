import os
import pandas as pd
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from tqdm import tqdm
import numpy as np
import csv
import time
import threading
from datetime import datetime
import httpx
from openai import OpenAI
from typing import Dict
#from google import genai
#from google.genai import types
# 添加线程锁用于日志记录
write_lock = threading.Lock()

def log_gpt_usage(total_tokens, prompt_tokens, out_tokens, model):
    """记录GPT API使用情况到CSV文件"""
    log_dir = "./log"
    log_file = os.path.join(log_dir, "gpt_api_usage.csv")
    os.makedirs(log_dir, exist_ok=True)
    max_retries = 3
    retry_delay = 0.1
    
    with write_lock:  # 使用同一个线程锁
        for attempt in range(max_retries):
            try:
                with open(log_file, "a+", newline='', encoding='utf-8') as f:
                    # 移动到文件开始以检查是否需要写入表头
                    f.seek(0)
                    first_line = f.readline().strip()
                    write_header = not first_line
                    
                    # 计算当前行号
                    f.seek(0)
                    current_row = sum(1 for _ in f)
                    if current_row > 0:
                        current_row -= 1
                    
                    # 移动到文件末尾进行写入
                    f.seek(0, 2)
                    writer = csv.writer(f)
                    
                    if write_header:
                        writer.writerow(["row_id","timestamp", "total_tokens", "prompt_tokens", "out_tokens","model"])
                    
                    writer.writerow([current_row + 1, datetime.now().isoformat(),
                                   total_tokens, prompt_tokens, out_tokens, model])
                    
                return  # 成功写入后返回
                
            except (IOError, OSError) as e:
                if attempt == max_retries - 1:
                    print(f"Failed to write to log file after {max_retries} attempts: {e}")
                    raise
                time.sleep(retry_delay * (attempt + 1))

def api_gpt41_mini_text_evaluation(prompt):
    """调用GPT进行评估 """
    endpoint = "https://llm-east-us2-test.openai.azure.com/"
    subscription_key = "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY"
    model_name = "gpt-4.1-mini"
    deployment = "gpt-4.1-mini"
    api_version = "2024-12-01-preview"
    
    client = AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )
    
    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_completion_tokens=100,
            temperature=0.1,
            model=deployment
        )
        
        result = response.choices[0].message.content.strip()
        print(f"GPT Evaluation Result: {result}")
        
        # 记录token使用情况（如果API返回usage信息）
        if hasattr(response, 'usage') and response.usage:
            total_tokens = response.usage.total_tokens
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            log_gpt_usage(total_tokens, prompt_tokens, completion_tokens, model_name)
        
        return result
        
    except Exception as e:
        print(f"Error in GPT evaluation: {str(e)}")
        return None

def evaluate_detail_captioning(answer, prediction):
    """评估Detail Captioning类型，从多个维度评估并返回0-100的综合相似度分数"""
    prompt = f"""Evaluate the similarity between the following two texts along the dimensions below.
    Each dimension should be scored from 0 to 100.

    1. Object Recognition (Weight: 40%):
    - Whether the main objects in the image are correctly identified
    - Whether the number of objects is accurate
    - Whether the object categories are correct

    2. Attribute Description (Weight: 30%):
    - Whether attributes such as color, size, and shape are accurately described
    - Whether object states, materials, and related characteristics are accurate

    3. Relationship Description (Weight: 30%):
    - Whether spatial relationships between objects are accurately described
    - Whether interaction relationships between objects are accurately described

    Reference answer: {answer}
    Predicted answer: {prediction}

    Return the scores in the following format (numbers only, no extra text):
    Object recognition score
    Attribute description score
    Relationship description score"""


    result = api_gpt41_mini_text_evaluation(prompt)
    if result:
        try:
            # 提取三个维度的分数
            # 更灵活的数字提取
            scores = []
            for line in result.split('\n'):
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    scores.append(int(numbers[0]))
            if len(scores) >= 3:
                object_score = min(max(scores[0], 0), 100)
                attribute_score = min(max(scores[1], 0), 100)
                relation_score = min(max(scores[2], 0), 100)
                
                # 计算加权综合分数
                final_score = (
                    object_score * 0.4 +     # 物体识别权重40%
                    attribute_score * 0.3 +   # 属性描述权重30%
                    relation_score * 0.3      # 关系描述权重30%
                )
                print(f"Detail Captioning Scores - Object: {object_score}, Attribute: {attribute_score}, Relation: {relation_score}, Final: {final_score}")
                return round(final_score)
        except:
            pass
    return 0

def evaluate_comprehensive_evaluation(answer, prediction):
    """评估Comprehensive Evaluation类型，返回True/False"""
    prompt = f"""Determine whether the predicted answer is correct based on the reference answer.
    If the meanings are semantically similar, consider it correct.

    Reference answer: {answer}
    Predicted answer: {prediction}

    Return ONLY 1 (correct) or 0 (incorrect). Do not output any other text."""

    
    result = api_gpt41_mini_text_evaluation(prompt)
    if result:
        result_clean = result.strip()
        if result_clean == '1':
            return 1
        elif result_clean == '0':
            return 0
    return False

def extract_numerical_answer_gpt(text):
    """使用GPT从文本中提取数值答案"""
    prompt = f"""Extract the FINAL numeric answer from the following text.
    If multiple numbers appear, extract the one that represents the final answer.

    Text: {text}

    Return ONLY a single number with no additional text.
    If no number appears in the text, return "no number"."""

    
    result = api_gpt41_mini_text_evaluation(prompt)
    if result:
        try:
            import re
            # 提取数字（包括负数和小数）
            numbers = re.findall(r'-?\d+\.?\d*', result.strip())
            if numbers:
                return float(numbers[0])
        except:
            pass
    return None

def is_numerical_equal_math(answer, prediction, tolerance=1e-6):
    """比较两个数值是否相等，考虑浮点数精度"""
    try:
        # 尝试直接转换为数字
        ans_num = float(answer) if isinstance(answer, str) else answer
        pred_num = float(prediction) if isinstance(prediction, str) else prediction
        
        return abs(ans_num - pred_num) < tolerance
    except:
        return False

def evaluate_math(answer, prediction):
    """评估Math domain，使用GPT辅助提取数值答案后进行比较"""
    # 首先尝试直接数值比较
    try:
        if is_numerical_equal_math(answer, prediction):
            return 1
    except:
        pass
    
    # 如果直接比较失败，使用GPT提取数值
    answer_num = extract_numerical_answer_gpt(str(answer))
    prediction_num = extract_numerical_answer_gpt(str(prediction))
    
    if answer_num is not None and prediction_num is not None:
        if is_numerical_equal_math(answer_num, prediction_num):
            return 1
    
    # 如果数值提取失败，回退到GPT文本比较
    prompt = f"""Determine whether the following two math answers are numerically equal.
    Focus on the FINAL numeric result, not the expression format.

    Evaluation rules:
    1) If the final numeric values are equal, it is correct, even if the number of decimal places differs.
    2) Focus on the final computed result, not intermediate steps.
    3) If the predicted answer only describes a process but does not produce the same final numeric result, it is incorrect.
    
    Reference answer: {answer}
    Predicted answer: {prediction}

    Return ONLY 1 (correct) or 0 (incorrect). Do not output any other text."""

    
    result = api_gpt41_mini_text_evaluation(prompt)
    if result:
        result_clean = result.strip()
        if result_clean == '1':
            return 1
        elif result_clean == '0':
            return 0
    return 0

def evaluate_other_domains(answer, prediction):
    """评估其他domain类型，返回True/False"""
    prompt = f"""Carefully evaluate whether the predicted answer is semantically consistent with or correct compared to the reference (gold) answer.

    NUMERIC ANSWER RULES:
    1) If the reference answer is a pure number, the prediction is correct if its final numeric result is numerically equal to the reference, even if the number of decimal places differs.
    2) For numeric answers, focus on the FINAL numeric result. Do NOT mark it correct merely because the prediction mentions the correct number somewhere in the intermediate steps.
    3) If the reference answer is numeric but the prediction only describes a process without producing the same final numeric result, mark it incorrect.

    TEXT ANSWER RULES:
    1) If the reference answer is a short Yes/No, judge only whether the prediction’s core answer (extract Yes/No only) matches the reference.
    2) If the reference answer contains specific keywords or a required format (e.g., a list like ['repsol']), the prediction must contain the same key information and be semantically consistent. Case differences should be ignored.

    ANALYSIS STEPS:
    1) What is the core content of the reference answer? (number / keywords / yes-no decision)
    2) Does the prediction explicitly contain this core content?
    3) Is the prediction’s conclusion consistent with the reference answer?

    Reference answer: {answer}
    Predicted answer: {prediction}

    Return ONLY 1 (correct) or 0 (incorrect). Do not output any other text."""
 
    result = api_gpt41_mini_text_evaluation(prompt)
    if result:
        result_clean = result.strip()
        if result_clean == '1':
            return 1
        elif result_clean == '0':
            return 0
    return False

def calculate_metrics(df):
    """计算新的Metrics：使用pass列为1的数量除以总数乘以100"""
    total_samples = len(df)
    if total_samples == 0:
        return 0
    
    # 计算pass列为1的数量
    pass_count = len(df[df['pass'] == 1])
    
    # 计算百分比
    accuracy_percentage = (pass_count / total_samples) * 100
    
    return {
        'accuracy_percentage': accuracy_percentage,
        'pass_count': pass_count,
        'total_samples': total_samples
    }

def calculate_overall_accuracy(df):
    """计算所有样本的平均准确率"""
    total_correct = 0
    total_samples = len(df)
    
    # 分别处理Detail Captioning和其他domain的样本
    detail_captioning_mask = df['domain'] == 'Detail Captioning'
    
    # Detail Captioning样本
    dc_samples = df[detail_captioning_mask]
    total_correct += len(dc_samples[dc_samples['score'] >= 75])
    
    # 其他domain样本
    other_samples = df[~detail_captioning_mask]
    total_correct += len(other_samples[other_samples['score'] == True])
    
    # 计算整体准确率
    overall_accuracy = total_correct / total_samples if total_samples > 0 else 0
    
    return overall_accuracy

def main(row: Dict) -> Dict:
    start_time = time.time()
    # 取字段（与主框架列名一致）
    answer     = str(row.get("answer", ""))
    prediction = str(row.get("result", ""))
    domain     = str(row.get("domain", ""))   # 可选：Detail Captioning / Comprehensive Evaluation / Math ...

    try:
        # 1. 根据 domain 调用你已有的评估函数
        if domain == "Detail Captioning":
            score = evaluate_detail_captioning(answer, prediction)
        elif domain == "Comprehensive Evaluation":
            score = evaluate_comprehensive_evaluation(answer, prediction)
        else:
            # 兜底：其他 domain 用通用文本比较
            score = evaluate_other_domains(answer, prediction)
    except Exception as e:
        print(f"Error processing row: {str(e)}")
        # 根据domain类型设置默认值
        if domain == 'Detail Captioning':
            score = 0
        else:
            score = False

    try:
        # 检查是否是数值
        if isinstance(score, (int, float)):
            # 如果是数值，检查是否为0或1
            if score not in [0, 1]:
                # 大于等于75改为1，小于75改为0
                is_pass = 1 if score >= 75 else 0
            else:
                is_pass = score
        else:
            # 如果不是数值，检查是否是布尔值或字符串
            str_value = str(score).upper()
            if str_value == 'TRUE':
                is_pass = 1
            elif str_value == 'FALSE':
                is_pass = 0
            else:
                # 既不是数值也不是TRUE/FALSE，改为0
                is_pass = 0
    except Exception as e:
        print(f"Error processing pass value: {str(e)}")
        is_pass = 0

    cost_time = time.time() - start_time
    return {"Result": score, "pass": is_pass}

if __name__ == "__main__":
    main()