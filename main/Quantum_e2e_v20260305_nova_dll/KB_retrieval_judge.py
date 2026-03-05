import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
import time
import ast
import re
from rouge import Rouge
from openai import AzureOpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import traceback


class KBRetrievalEvaluator:
    """
    知识库检索评估器（并发版本）
    用于评估知识库检索的准确性和相关性
    """
    
    def __init__(self, endpoint=None, subscription_key=None, deployment="o4-mini", max_workers=32):
        """
        初始化评估器
        
        Args:
            endpoint: Azure OpenAI 端点
            subscription_key: Azure OpenAI 订阅密钥
            deployment: 使用的模型部署名称
            max_workers: 最大并发线程数
        """
        self.endpoint = endpoint or 'https://llm-east-us2-test.openai.azure.com/'
        self.subscription_key = subscription_key or 'A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY'
        self.deployment = deployment
        self.rouge = Rouge()
        self.max_workers = max_workers
        self.lock = Lock()  # 用于线程安全的进度打印
        
        # 初始化 Azure OpenAI 客户端
        self.client = AzureOpenAI(
            api_version="2024-12-01-preview",
            azure_endpoint=self.endpoint,
            api_key=self.subscription_key,
        )
    
    @staticmethod
    def clean_string_for_xml(s):
        """移除所有非打印字符（包括控制字符和NULL字节）"""
        return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', s)
    
    @staticmethod
    def clean_string(s):
        """删除字符串开头和结尾的空格、方括号和标点符号"""
        cleaned = s.strip()
        cleaned = cleaned.strip('[]')
        cleaned = re.sub(r'[^\w\s]', '', cleaned)
        return cleaned
    
    @staticmethod
    def remove_punctuation(text):
        """删除标点符号"""
        return re.sub('[^\w\s]', '', text)
    
    @staticmethod
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
    
    def text_similarity(self, references, candidate):
        """计算文本相似度（基于最长公共子序列）"""
        all_len = 0
        all_lcs_len = 0
        
        for reference in references:
            lcs = self.longest_common_substring(reference, candidate)
            all_lcs_len += len(lcs)
            all_len += len(reference)
        
        similarity = 1.0 * all_lcs_len / all_len if all_len > 0 else 0
        return '', similarity
    
    @staticmethod
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
    
    @staticmethod
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
    
    def ask_gpt(self, prompt, max_retries=3):
        """
        调用 GPT 模型进行评估
        
        Args:
            prompt: 提示词
            max_retries: 最大重试次数
            
        Returns:
            GPT 的响应文本
        """
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
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
                    model=self.deployment
                )
                
                response_text = response.choices[0].message.content
                res1 = str(response_text).replace("```json", "").replace("```", "").strip()
                return res1
                
            except Exception as e:
                print(f"GPT 调用失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # 等待2秒后重试
                else:
                    raise
    
    def all_details_check(self, query, ref_answer, ref_text, retrieved_chunk):
        """
        检查检索块是否包含所需信息
        
        Args:
            query: 问题
            ref_answer: 参考答案
            ref_text: 参考文本
            retrieved_chunk: 检索到的文本块
            
        Returns:
            评估结果
        """
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
        
        return self.ask_gpt(prompt)
    
    def evaluate_single_chunk(self, row, k, topk=3):
        """
        评估单个检索块
        
        Args:
            row: 数据行
            k: 当前检索块的索引
            topk: 检索的top-k数量
            
        Returns:
            'pass' 或 'fail'
        """
        searched_files_list = ast.literal_eval(row['search_file_list'])
        searched_text_list = ast.literal_eval(row['search_text_list'])
        
        # 检查是否有检索结果
        if not searched_files_list or not searched_text_list:
            return 'fail'
        
        # 检查是否有足够的检索结果
        if len(searched_files_list) < k + 1:
            return 'fail'
        
        # 处理表格文件
        if any(ext in row['gt_file'] for ext in ['.xlsx', '.xls', '.csv']):
            return self._evaluate_table_file(row, searched_files_list, searched_text_list, k)
        
        # 处理文本文件
        return self._evaluate_text_file(row, searched_text_list, k)
    
    def _evaluate_table_file(self, row, searched_files_list, searched_text_list, k):
        """评估表格文件检索结果"""
        return_results = searched_files_list[k] + ' ' + searched_text_list[k]
        gt = row['gt_file']
        return 'pass' if return_results == gt else 'fail'
    
    def _evaluate_text_file(self, row, searched_text_list, k):
        """评估文本文件检索结果"""
        # 预处理参考文本
        gt_text_list = [
            self.remove_punctuation(t.replace(" ", "").replace("\t", "").replace("\r", ""))
            for t in str(row['gt_text']).split('\n')
        ]
        
        gt_text_list1 = [
            self.remove_punctuation(t.replace("\t", "").replace("\r", ""))
            for t in str(row['gt_text']).split('\n')
        ]
        
        gt_text1 = ''.join(gt_text_list1)
        
        # 预处理检索文本
        try:
            searched_text = self.remove_punctuation(
                searched_text_list[k].replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "")
            )
            searched_text1 = self.remove_punctuation(
                searched_text_list[k].replace("\n", "").replace("\t", "").replace("\r", "")
            )
            searched_text_new = self.clean_string_for_xml(
                ILLEGAL_CHARACTERS_RE.sub(r'', searched_text_list[k])
            )
        except:
            searched_text = ''
            searched_text1 = ''
            searched_text_new = ''
        
        # 计算文本相似度
        _, lcs_similarity = self.text_similarity(gt_text_list, searched_text)
        
        # 计算 ROUGE 分数
        semantic_score = 0
        if searched_text1:
            try:
                max_len = 1000
                text1 = searched_text1[:max_len] if len(searched_text1) >= max_len else searched_text1
                text2 = gt_text1[:max_len] if len(gt_text1) >= max_len else gt_text1
                
                if text1 and text2:
                    scores = self.rouge.get_scores(text1, text2, avg=True)
                    semantic_score = scores['rouge-l']['r']
            except Exception as e:
                print(f"ROUGE 计算失败: {str(e)}")
                semantic_score = 0
        
        # 如果相似度足够高，直接返回 pass
        if lcs_similarity >= 0.4 or semantic_score >= 0.4:
            return 'pass'
        
        # 使用 GPT 进行详细评估
        return self._evaluate_with_gpt(row, searched_text_list[k])
    
    def _evaluate_with_gpt(self, row, searched_text):
        """使用 GPT 进行详细评估"""
        chunk_eva_complete_ls = []
        times = 0
        max_times = 1
        
        while times < max_times:
            chunk_eva_complete = self.all_details_check(
                row['question'],
                row['answer'],
                row['gt_text'],
                searched_text
            )
            
            chunk_eva_com_clean = self.clean_string(self.result_find(chunk_eva_complete))
            
            # 检查是否得到有效结果
            if any(keyword in chunk_eva_com_clean for keyword in [
                "All reference text in chunk",
                "Reference answer in chunk",
                "Alternative answer in chunk"
            ]):
                break
            
            times += 1
        
        chunk_eva_complete_ls.append(chunk_eva_com_clean)
        comp_eva_value = self.chunk_eval_comp_map(chunk_eva_complete_ls)
        
        return 'pass' if comp_eva_value[0] in [4, 5] else 'fail'
    
    def _evaluate_single_row(self, index, row, topk, total_rows, processed_count):
        """
        评估单行数据（用于并发执行）
        
        Args:
            index: 行索引
            row: 数据行
            topk: top-k数量
            total_rows: 总行数
            processed_count: 已处理计数器（列表，用于线程安全）
            
        Returns:
            (index, final_result, error_msg)
        """
        try:
            # 评估 top-k 个检索结果
            tool_result_list = []
            for k in range(topk):
                try:
                    tool_result = self.evaluate_single_chunk(row, k, topk)
                    tool_result_list.append(tool_result)
                except Exception as e:
                    tool_result_list.append('fail')
                    with self.lock:
                        print(f"  [索引 {index}] Top-{k+1} 评估失败: {str(e)}")
            
            # 判断最终结果
            if pd.isna(row.get('CURRENT_INTENT_RECOGNITION')):
                has_pass = any(x.lower() == 'pass' for x in tool_result_list)
                final_result = 'pass' if has_pass else 'fail'
            else:
                final_result = ''
            
            # 线程安全的进度打印
            with self.lock:
                processed_count[0] += 1
                print(f"✅ [{processed_count[0]}/{total_rows}] 索引 {index} 完成 | 结果: {final_result}")
            
            return (index, final_result, None)
            
        except Exception as e:
            error_msg = f"评估失败: {str(e)}\n{traceback.format_exc()}"
            with self.lock:
                processed_count[0] += 1
                print(f"❌ [{processed_count[0]}/{total_rows}] 索引 {index} 失败: {str(e)}")
            return (index, 'fail', error_msg)
    
    def evaluate_excel(self, input_excel, output_excel, topk=3, scene_filter_list=['kbqa', 'Kbqa']):
        """
        评估整个 Excel 文件（并发版本）
        
        Args:
            input_excel: 输入 Excel 文件路径
            output_excel: 输出 Excel 文件路径
            topk: 检索的 top-k 数量
            scene_filter_list: 场景过滤器，只评估特定场景的数据
            
        Returns:
            评估后的 DataFrame
        """
        print(f"\n{'='*60}")
        print(f"🚀 开始并发评估")
        print(f"{'='*60}")
        print(f"输入文件: {input_excel}")
        print(f"输出文件: {output_excel}")
        print(f"场景过滤: {scene_filter_list}")
        print(f"Top-K: {topk}")
        print(f"并发线程数: {self.max_workers}")
        print(f"{'='*60}\n")
        
        # 读取数据
        result_data = pd.read_excel(input_excel)
        
        # 筛选需要评估的行
        filtered_indices = []
        for index, row in result_data.iterrows():
            if row["scene"] in scene_filter_list:
                filtered_indices.append(index)
        
        total_rows = len(filtered_indices)
        print(f"📊 总行数: {len(result_data)}, 需评估行数: {total_rows}\n")
        
        if total_rows == 0:
            print("⚠️  没有符合条件的数据需要评估")
            result_data.to_excel(output_excel, index=False)
            return result_data
        
        # 初始化进度计数器
        processed_count = [0]
        
        # 使用线程池并发执行
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(
                    self._evaluate_single_row,
                    index,
                    result_data.loc[index],
                    topk,
                    total_rows,
                    processed_count
                ): index
                for index in filtered_indices
            }
            
            # 收集结果
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    row_index, final_result, error_msg = future.result()
                    result_data.loc[row_index, 'kbRetrieval_check'] = final_result
                    
                    if error_msg:
                        # 可选：将错误信息写入额外的列
                        if 'evaluation_error' not in result_data.columns:
                            result_data['evaluation_error'] = ''
                        result_data.loc[row_index, 'evaluation_error'] = error_msg
                        
                except Exception as e:
                    print(f"❌ 处理索引 {index} 的结果时出错: {str(e)}")
                    result_data.loc[index, 'kbRetrieval_check'] = 'fail'
        
        # 计算耗时
        elapsed_time = time.time() - start_time
        
        # 保存结果
        result_data.to_excel(output_excel, index=False)
        
        print(f"\n{'='*60}")
        print(f"✅ 评估完成！")
        print(f"{'='*60}")
        print(f"总耗时: {elapsed_time:.2f} 秒")
        print(f"平均每行: {elapsed_time/total_rows:.2f} 秒")
        print(f"结果已保存到: {output_excel}")
        print(f"{'='*60}\n")
        
        return result_data
    
    def get_statistics(self, df, scene_filter_list=['kbqa', 'Kbqa']):
        """
        获取评估统计信息
        
        Args:
            df: 评估后的 DataFrame
            scene_filter_list: 场景过滤器
            
        Returns:
            统计信息字典
        """
        filtered_df = df[df['scene'].isin(scene_filter_list)]
        
        if 'kbRetrieval_check' not in filtered_df.columns:
            return {
                'error': 'kbRetrieval_check 列不存在，请先运行评估'
            }
        
        total = len(filtered_df)
        pass_count = len(filtered_df[filtered_df['kbRetrieval_check'] == 'pass'])
        fail_count = len(filtered_df[filtered_df['kbRetrieval_check'] == 'fail'])
        pass_rate = pass_count / total * 100 if total > 0 else 0
        
        return {
            'total': total,
            'pass': pass_count,
            'fail': fail_count,
            'pass_rate': f"{pass_rate:.2f}%"
        }


# 使用示例
if __name__ == '__main__':
    # 创建评估器实例（设置并发线程数）
    evaluator = KBRetrievalEvaluator(max_workers=10)  # 可根据需要调整线程数
    
    # 配置文件路径
    input_excel = r"C:\Users\zhoutian2\Downloads\NV_test_results_local_solution_case_EN_0121_20260121_143611_cycle1_Auto_Judge_Final (4).xlsx"
    output_excel = r"C:\Users\zhoutian2\Downloads\NV_test_results_local_solution_case_EN_0121_20260121_143611_cycle1_Auto_Judge_Final (4)_result.xlsx"
    
    # 执行评估
    result_df = evaluator.evaluate_excel(
        input_excel=input_excel,
        output_excel=output_excel,
        topk=3,
        scene_filter_list=['kbqa', 'Kbqa']
    )
    
    # 获取统计信息
    stats = evaluator.get_statistics(result_df, scene_filter_list=['kbqa', 'Kbqa'])
    print("\n" + "="*50)
    print("📊 评估统计信息:")
    print("="*50)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("="*50)
