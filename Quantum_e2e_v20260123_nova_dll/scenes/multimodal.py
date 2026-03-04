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
    prompt = f"""请从以下维度评估两段文本的相似度，每个维度的分数为0-100：

1. 物体识别 (Object Recognition, 权重40%):
   - 是否正确识别了图中的主要物体
   - 物体数量是否准确
   - 物体类别是否准确

2. 属性描述 (Attribute Description, 权重30%):
   - 物体的颜色、大小、形状等属性描述是否准确
   - 物体的状态、材质等特征是否准确

3. 关系描述 (Relationship Description, 权重30%):
   - 物体之间的空间关系描述是否准确
   - 物体之间的交互关系描述是否准确

标准答案: {answer}
预测答案: {prediction}

请按以下格式返回评分（只需返回数字）：
物体识别分数
属性描述分数
关系描述分数"""

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
    prompt = f"""请根据标准答案判断预测答案是否正确。语义相近即可认为正确。
    
标准答案: {answer}
预测答案: {prediction}

请只返回1(代表正确)或0(代表错误)，不要包含其他文字。"""
    
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
    prompt = f"""请从以下文本中提取最终的数值答案。如果有多个数字，请提取作为最终答案的那个数字。
    
文本: {text}

请只返回一个数字，不要包含其他文字。如果没有数字，请返回"无数字"。"""
    
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
    prompt = f"""请判断以下两个数学答案是否在数值上相等。重点关注最终的数值结果，而不是表达形式。

标准答案: {answer}
预测答案: {prediction}

评估规则：
1. 如果两个答案的数值结果相等，即使小数保留位数不同也算正确
2. 重点关注最终计算结果，而不是中间过程
3. 如果预测答案只是描述过程但没有得出相同结果，应判断为错误

请只返回1(代表正确)或0(代表错误)，不要包含其他文字。"""
    
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
#     prompt = f"""请根据标准答案判断预测答案是否正确。预测答案不需要完全匹配，但要包含标准答案中的关键信息。
    
# 标准答案: {answer}
# 预测答案: {prediction}

# 请只返回1(代表正确)或0(代表错误)，不要包含其他文字。"""
    prompt = f"""请仔细评估预测答案是否与标准答案在语义上一致或正确。评估标准：

**数值类答案评估规则：**
1. 如果标准答案是纯数字，预测答案中的数值结果与标准答案在数值上相等即可认为正确，即使小数保留位数不同。
2. 对于数值答案，重点关注最终数值结果，而不是中间过程的出现预测答案就算正确
3. 如果标准答案是数值，预测答案只是描述过程但没有得出相同结果，应判断为错误

**文本类答案评估规则：**
1. 如果标准答案是简短的Yes/No，只判断预测答案的核心答案（只提取Yes/No）和标注答案是否相符
2. 如果标准答案包含特定关键词或格式（如列表格式['repsol']），预测答案必须包含相同的关键信息且语义一致，不需要区分大小写

**分析步骤：**
1. 标准答案的核心内容是什么？（数值/关键词/判断）
2. 预测答案是否明确包含了这个核心内容？
3. 预测答案的结论是否与标准答案一致？

标准答案: {answer}
预测答案: {prediction}

请只返回1(代表正确)或0(代表错误)，不要包含其他文字。"""    
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