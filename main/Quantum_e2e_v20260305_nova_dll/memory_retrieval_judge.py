import json
import pandas as pd
import os
import logging
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm
from openai import AzureOpenAI
import time


class MemoryRetrievalJudge:
    """
    内存检索判断器类：用于判断模型预测结果是否包含真实答案
    
    使用示例：
        judge = MemoryRetrievalJudge(
            azure_endpoint="your_endpoint",
            azure_key="your_key",
            deployment_name="gpt-4.1",
            max_workers=10
        )
        judge.verify_excel(
            input_path="input.xlsx",
            output_path="output.xlsx",
            question_col="question",
            gt_col="answer",
            pred_col="MemoryRetrievalTop3",
            dimension_col="dimension"  # 可选
        )
    """
    
    def __init__(
        self,
        azure_endpoint,
        azure_key,
        test_mode = "local",    # cloud or local
        deployment_name="gpt-4.1",
        api_version="2024-12-01-preview",
        max_workers=32,
        request_delay=0.1,
        log_file="answer_verification.log"
    ):
        """
        初始化答案验证器
        
        Args:
            azure_endpoint: Azure OpenAI 端点
            azure_key: Azure OpenAI API密钥
            deployment_name: 部署模型名称
            api_version: API版本
            max_workers: 并发线程数
            request_delay: API请求延迟（秒）
            log_file: 日志文件路径
        """
        # Azure OpenAI 配置
        self.azure_endpoint = azure_endpoint
        self.azure_key = azure_key
        self.deployment_name = deployment_name
        self.api_version = api_version
        
        # 并发配置
        self.max_workers = max_workers
        self.request_delay = request_delay
        
        # 线程锁
        self.api_lock = threading.Lock()
        self.log_lock = threading.Lock()
        
        # 配置日志
        self._setup_logging(log_file)
        
        # 初始化Azure OpenAI客户端
        self.client = AzureOpenAI(
            azure_endpoint=self.azure_endpoint,
            api_key=self.azure_key,
            api_version=self.api_version
        )
        
        logging.info("MemoryRetrievalJudge初始化完成")
    
    def _setup_logging(self, log_file):
        """配置日志系统"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ],
            force=True  # 强制重新配置
        )
    
    def verify_answer_consistency(self, question, gt_answer, pre_response, row_index=None):
        """
        调用Azure GPT模型，判断Pre是否完全包含GT答案
        
        Args:
            question: 问题文本
            gt_answer: 真实答案（GT）
            pre_response: 模型预测结果（Pre）
            row_index: 行索引（用于日志显示）
            
        Returns:
            tuple: (result: str (pass/fail), reason: str) 判决结果及原因
        """
        # 构造模型请求消息
        messages = [
        {
            "role": "system",
            "content": """You are a retrieval quality evaluation expert for a Retrieval-Augmented Generation (RAG) system.
Your task is to judge whether the user's Question can be correctly answered solely based on the context information (Pre) recalled by the model, and whether the derived answer is consistent with the Ground Truth (GT).

Please strictly follow this judgment logic:
1. **Independent Inference**: Ignore your own external knowledge and attempt to answer the Question **solely based on the information provided in Pre**.
2. **Consistency Check**: Compare the answer you derived based on Pre with the GT.

Judgment Rules:

**Pass (Qualified)**:
1. **Completely Consistent**: Pre contains the key information needed to answer the Question, and the answer derived from this information is consistent with the core content (including factual details) of the GT.
2. **Pure Negation/No Memory/Fact Correction**:
   - When GT indicates "no relevant information" or "No", or GT makes a **fact correction** (e.g., "Not A, only B"), and this correction is based on the non-existence of the fact.
   - **Criteria**:
     - If Pre indeed **does not contain** the incorrect object asked in the question (e.g., asked "Father", Pre only has "Mother"), corroborating "no information on father", matching the first part of GT -> **Pass**.
     - If Pre further contains the correct object mentioned in GT (e.g., GT says "actually it's mother", Pre indeed has "Mother" info), it is a perfect **Pass**.
     - If Pre is empty or contains only irrelevant information, as long as the core meaning of GT is "No/None/Don't know", it is considered consistent, judge **Pass**.

**Fail (Unqualified)**:
1. **Information Missing/Reason Unsupported**:
   - If GT contains specific facts or reasons (even if GT starts with "No", e.g., "No, because Andy is allergic").
   - At this time, if Pre **lacks** key information supporting this reason (e.g., Pre is completely irrelevant), making it impossible to derive the specific reason in GT, it must be judged as **Fail**.
2. **Contradiction**: The answer derived based on Pre contradicts GT.
   - Example: GT says "None", but Pre contains the exact memory referred to in the question.
3. **Pre is Empty but GT Contains Specific Facts**:
   - **Important**: If GT is "No" or negative, but implies facts that need confirmation (e.g., asking "Is the store open in the morning?", GT says "No" implying knowledge of store hours but not including morning).
   - At this time, if **Pre is empty**, it means the system retrieved absolutely no information about the store, cannot judge its opening hours, and thus cannot confidently answer "No" (can only answer "Don't know").
   - This case is judged as **Fail** (because possibility cannot be excluded based on Pre, classifying as retrieval failure).
   - *Exception*: If GT explicitly says "No record of the store", then Pre being empty is Pass. But if GT is answering a factual question (like "It's not open"), Pre being empty is Fail.
4. **URL Inconsistency or Incompleteness**:
   - If GT contains a complete URL (starting with "http://" or "https://"):
     - Pre must contain the EXACT same complete URL string(starting with "http://" or "https://").
     - If Pre only contains a domain name, partial URL, reformatted URL, inferred URL, or descriptive reference,
       it must be judged as Fail, regardless of semantic similarity.
       
**Ownership/Subject Matching Principle**:
- If the question specifies "my/User's" item (e.g., "my company's gym"), Pre must explicitly contain the item belonging to the user to count as "present".
- If Pre only has generic info (e.g., "Power Pulse Gym") without attribution, treat as "no relevant information".
- In this case, if GT is "No/None", it matches GT, judge **Pass**.

**Example Reference**:
- Q: "Father jogging?" | GT: "No info on father, mother jogs." | Pre: ["Mother jogs"] -> **Pass** (Pre confirms no father and has mother)
- Q: "My company's gym?" | GT: "No." | Pre: ["Power Pulse Gym" (generic)] -> **Pass** (No attribution = No relevant info = Matches No)
- Q: "Is store open morning?" | GT: "No" (implied: it's open at other times) | Pre: [] -> **Fail** (No info cannot judge hours, cannot derive No)
- Q: "Go to flower sea?" | GT: "No, Andy is allergic." | Pre: [Irrelevant] -> **Fail** (Cannot derive allergy reason)
- Q: "Which site has recipes?" | GT: "https://home.meishi.com." | Pre: [home.meishi.com.] -> **Fail** (Not provide the complete URL "https://home.meishi.com.")
- Q: "Which website hosts programming resources?" | GT: "https://github.com/" | Pre: [GitHub] -> **Fail** (Not provide the complete URL, only domain name)

Note: Pre might describe in third person (User/He/She), please treat as user's memory.
Must strictly return in the following format, no extra content allowed:
Judgment Result: [pass or fail]
Judgment Reason: [Brief explanation of conclusion derived from Pre and its relation to GT]"""
            },
            {
                "role": "user",
                "content": f"Question: {question}\nGround Truth (GT): {gt_answer}\nModel Prediction (Pre): {pre_response}"
            }
        ]

        try:
            with self.api_lock:
                time.sleep(self.request_delay)
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=500
                )
            
            content = response.choices[0].message.content.strip()
            
            with self.log_lock:
                if row_index is not None:
                    logging.info(f"第{row_index}条数据处理完成，模型响应: {content}")
                else:
                    logging.info(f"模型响应结果: {content}")

            # 解析模型返回的判决结果和原因
            result = "fail"  # 默认失败
            reason = "解析模型响应失败"
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith("判决结果:"):
                    result_str = line.split(':', 1)[1].strip()
                    if result_str in ["pass", "fail"]:
                        result = result_str
                elif line.startswith("判决原因:"):
                    reason = line.split(':', 1)[1].strip()

            return result, reason

        except Exception as e:
            error_msg = f"调用GPT模型失败: {str(e)}"
            with self.log_lock:
                if row_index is not None:
                    logging.error(f"第{row_index}条数据处理失败: {error_msg}")
                else:
                    logging.error(error_msg)
            return "fail", error_msg
    
    def _process_single_row(self, args):
        """
        处理单行数据的内部函数
        
        Args:
            args: (idx, row, question_col, gt_col, pred_col)
            
        Returns:
            tuple: (idx, result, reason)
        """
        idx, row, question_col, gt_col, pred_col = args
        
        # 检查预测结果列是否为空，如果为空直接返回空结果
        if pd.isna(row[pred_col]) or str(row[pred_col]).strip() == "":
            return idx, "", ""

        # 提取当前行数据
        question = str(row[question_col]).strip() if pd.notna(row[question_col]) else "无问题描述"
        gt_answer = str(row[gt_col]).strip() if pd.notna(row[gt_col]) else "无真实答案"
        pre_response = str(row[pred_col]).strip()
        
        # 调用模型验证包含关系
        result, reason = self.verify_answer_consistency(question, gt_answer, pre_response, idx + 1)
        
        return idx, result, reason
    
    def verify_excel(
        self,
        input_path,
        output_path,
        question_col="question",
        gt_col="answer",
        pred_col="MemoryRetrievalTop3",
        dimension_col=None,
        result_col="memoryRetrieval_check",
        reason_col="memoryRetrieval_reason"
    ):
        """
        主处理函数：读取Excel，验证答案一致性，输出结果
        
        Args:
            input_path: 输入Excel路径
            output_path: 输出Excel路径
            question_col: 问题列名
            gt_col: 真实答案列名
            pred_col: 预测结果列名
            dimension_col: 维度列名（可选，用于统计）
            result_col: 判决结果列名（输出）
            reason_col: 判决原因列名（输出）
            
        Returns:
            dict: 包含统计信息的字典
        """
        # 1. 读取Excel文件
        try:
            df = pd.read_excel(input_path)
            
            # 检查domain列是否存在
            if "domain" not in df.columns:
                raise ValueError("输入Excel缺少'domain'列")
            
            required_columns = [question_col, gt_col, pred_col]
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols:
                raise ValueError(f"输入Excel缺少必要列：{', '.join(missing_cols)}")
            
            # 筛选出domain为'Memory'的行
            memory_df = df[df["domain"] == 'Memory'].copy()
            memory_count = len(memory_df)
            
            logging.info(f"成功读取Excel，共{len(df)}条数据，其中Memory域{memory_count}条")
            
            # 检查是否存在dimension列
            has_dimension = dimension_col and dimension_col in df.columns
            if has_dimension:
                logging.info(f"检测到{dimension_col}列，将进行维度准确率统计")
                dimension_stats = {}
            else:
                if dimension_col:
                    logging.warning(f"未检测到{dimension_col}列，将跳过维度统计")
                dimension_stats = None
                
        except Exception as e:
            logging.error(f"读取Excel失败: {str(e)}")
            raise

        # 2. 初始化结果列（对所有行）
        df[result_col] = ""  # 默认为空
        df[reason_col] = ""  # 默认为空

        # 3. 使用并发处理验证数据一致性（仅处理Memory域）
        if memory_count > 0:
            logging.info(f"开始并发处理Memory域数据，并发数: {self.max_workers}")
            
            # 准备并发任务参数（仅包含Memory域的行）
            tasks = [(idx, row, question_col, gt_col, pred_col) for idx, row in memory_df.iterrows()]
            
            # 使用ThreadPoolExecutor进行并发处理
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_idx = {executor.submit(self._process_single_row, task): task[0] for task in tasks}
                
                # 使用tqdm显示进度条
                with tqdm(total=len(tasks), desc="Memory域处理进度") as pbar:
                    # 收集结果
                    for future in as_completed(future_to_idx):
                        try:
                            idx, result, reason = future.result()
                            # 更新DataFrame（注意这里更新的是原始df，使用原始索引）
                            df.at[idx, result_col] = result
                            df.at[idx, reason_col] = reason
                            
                            # 更新维度统计
                            if has_dimension:
                                row = df.loc[idx]
                                dimension = row[dimension_col]
                                if pd.isna(dimension):
                                    dimension = "未分类"
                                # 初始化维度统计项
                                if dimension not in dimension_stats:
                                    dimension_stats[dimension] = {"correct": 0, "total": 0, "accuracy": 0.0}
                                # 更新统计
                                dimension_stats[dimension]["total"] += 1
                                if result == "pass":
                                    dimension_stats[dimension]["correct"] += 1
                                # 计算准确率
                                dimension_stats[dimension]["accuracy"] = dimension_stats[dimension]["correct"] / dimension_stats[dimension]["total"]
                            
                            pbar.update(1)
                        except Exception as e:
                            idx = future_to_idx[future]
                            logging.error(f"处理第{idx+1}条数据时发生异常: {str(e)}")
                            df.at[idx, result_col] = "fail"
                            df.at[idx, reason_col] = f"处理异常: {str(e)}"
                            pbar.update(1)
        else:
            logging.warning("没有找到domain为'Memory'的数据，跳过处理")

        # 4. 保存结果到新Excel（保留所有原始列和所有行）
        try:
            df.to_excel(output_path, index=False, engine="openpyxl")

            # 计算统计信息（仅针对Memory域）
            memory_results = df[df["domain"] == 'Memory'][result_col]
            pass_count = (memory_results == "pass").sum()
            pass_ratio = pass_count / memory_count if memory_count > 0 else 0
            
            logging.info(f"Memory域Pass比例: {pass_ratio:.2%}（{pass_count}/{memory_count}）")
            
            # 准备返回的统计信息
            stats_result = {
                "total": len(df),
                "memory_total": memory_count,
                "pass_count": pass_count,
                "pass_ratio": pass_ratio,
                "dimension_stats": None
            }
            
            # 输出汇总统计到日志
            if dimension_stats:
                total_accuracy = pass_ratio
                logging.info(f"Memory域整体准确率: {total_accuracy:.2%}")
                logging.info("-" * 30)
                
                # 按准确率排序输出
                sorted_stats = sorted(dimension_stats.items(), key=lambda x: x[1]["accuracy"], reverse=True)
                for dimension, stats in sorted_stats:
                    logging.info(f"维度 '{dimension}': {stats['correct']}/{stats['total']} = {stats['accuracy']:.2%}")
                    
                logging.info("=" * 50)
                
                # 生成维度统计DataFrame
                stats_data = []
                for dim, stats in dimension_stats.items():
                    stats_data.append({
                        "维度": dim,
                        "正确数": stats["correct"],
                        "总数": stats["total"],
                        "准确率": stats["accuracy"]
                    })
                stats_df = pd.DataFrame(stats_data)
                
                # 保存维度统计
                stats_output_path = output_path.replace('.xlsx', '_statistics.xlsx')
                stats_df.to_excel(stats_output_path, index=False)
                logging.info(f"维度统计结果已单独保存至：{stats_output_path}")
                
                stats_result["dimension_stats"] = dimension_stats
            
            logging.info(f"所有数据处理完成！结果已保存至：{output_path}")
            
            return stats_result
            
        except Exception as e:
            logging.error(f"保存Excel失败: {str(e)}")
            raise


# ===================== 使用示例 =====================
if __name__ == "__main__":
    # 配置参数
    AZURE_ENDPOINT = "https://llm-east-us2-test.openai.azure.com/"
    AZURE_KEY = "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY"
    DEPLOYMENT_NAME = "gpt-4.1"
    
    INPUT_EXCEL_PATH = r"D:\Pod\pod10\Zimeng_case分析\Results\test_results_Memory_question _v6_260107_20260107_194204_cycle1_Auto_Judge_result_duration.xlsx"
    OUTPUT_EXCEL_PATH = r"D:\Pod\pod10\Zimeng_case分析\Results\retrieval_memorycheck.xlsx"
    
    # 创建验证器实例
    judge = MemoryRetrievalJudge(
        azure_endpoint=AZURE_ENDPOINT,
        azure_key=AZURE_KEY,
        deployment_name=DEPLOYMENT_NAME,
        max_workers=10,
        request_delay=0.1
    )
    
    # 执行验证
    stats = judge.verify_excel(
        input_path=INPUT_EXCEL_PATH,
        output_path=OUTPUT_EXCEL_PATH,
        question_col="question",
        gt_col="answer",
        pred_col="MemoryRetrievalTop3",
        dimension_col="dimension"  # 如果没有维度列，可以设为None或不传
    )
    
    # 打印统计结果
    print(f"\n处理完成！")
    print(f"总数据量: {stats['total']}")
    print(f"Memory域数据量: {stats['memory_total']}")
    print(f"Memory域通过数: {stats['pass_count']}")
    print(f"Memory域通过率: {stats['pass_ratio']:.2%}")
