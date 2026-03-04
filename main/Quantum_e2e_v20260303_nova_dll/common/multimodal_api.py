"""
MultimodalAPI 类：从 run_context / config / quantum_client_manager 获取路径与客户端。
"""
import pandas as pd
import json
from datetime import datetime
import time
import os
import openpyxl
import re
import mimetypes
import random
from pathlib import Path

from loguru import logger

from common import run_context
from common.run_context import (
    get_config,
    set_doc_details_path,
    get_doc_details_path,
)
from common.quantum_client_manager import get_quantum_client_manager
from common.paths import get_quantum_core_path
import analysis_log_0130_cloud
# get_regist_duration_single_file from analysis_log_0130_cloud
get_regist_duration_single_file = analysis_log_0130_cloud.get_regist_duration_single_file


class MultimodalAPI:
    """
    MultimodalAPI类，用于处理多模态数据上传、查询和下载
    """
    _memory_processed = False
    _document_registered = False 
    # 类级别的默认参数定义
    DEFAULT_HANDLER = "nova"
    
    def __init__(self):
        self.upload_id = None
        self.session_id = None
        self.job_id = None
        self.query_upload_id = None
        self.data_json_list=[]
        self.response_time = 0
        self.text_response_count = 0
        self.first_text_response_time = None
        self.text_response_count = 0
        self.first_word_time = None
        self.ttft_seconds = 0
        self.token_count = 0
        self.generation_speed = 0
        self.current_mode = None
        self.start_time_dt = None
        self.end_time_dt = None
        self.start_time_str = None
        self.end_time_str = None 
        # 将已注册文档信息写入本次运行的输出目录，避免污染脚本目录
        self.registered_docs_file = str(run_context.REGISTERED_DOCS_PATH)
        self.registered_docs = self.load_registered_docs()
        # 新增：存储最初尝试注册的文档列表（绝对路径）
        self.original_registered_docs = []
                # 新增：存储tool响应
        self.tool_responses = []
    # ========================================
    # 文档注册管理
    # ========================================
    def load_registered_docs(self):
        """从文件加载已注册文档列表"""
        if os.path.exists(self.registered_docs_file):
            try:
                with open(self.registered_docs_file, 'r', encoding='utf-8') as f:
                    docs = json.load(f)
                    return set(docs) if isinstance(docs, list) else set()
            except Exception as e:
                logger.info(f"加载已注册文档列表失败: {e}")
                return set()
        return set()
    
    def save_registered_docs(self):
        """保存已注册文档列表到文件"""
        try:
            with open(self.registered_docs_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.registered_docs), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.info(f"保存已注册文档列表失败: {e}")

    def is_document_registered(self, doc_paths):
        """检查文档是否已注册且仍然存在"""
        if not doc_paths:
            return False
        if not self.registered_docs:
            return False
        
        # 检查所有文档是否都在注册列表中且文件仍然存在
        for path in doc_paths:
            abs_path = os.path.abspath(path)
            # 检查是否在注册列表中且文件仍然存在
            if abs_path not in self.registered_docs or not os.path.exists(abs_path):
                return False
        return True

    def mark_documents_registered(self, doc_paths):
        """标记文档为已注册（仅当文档存在时）"""
        count = 0
        for path in doc_paths:
            abspath = os.path.abspath(path)
            # 仅当文档存在且尚未注册时才标记为已注册
            if abspath not in self.registered_docs and os.path.exists(abspath):
                self.registered_docs.add(abspath)
                count += 1
        if count > 0:
            self.save_registered_docs()
        logger.info(f"标记 {count} 个新文档为已注册，总共已注册 {len(self.registered_docs)} 个文档")
    # ========================================
    # 会话管理
    # ========================================
    def create_session(self):
        """创建会话并直接获取 sessionID"""
        try:
            # 增加重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # 每次重试都重新发送一次 create session 请求
                    payload = {"action": "create"}
                    job_id = get_quantum_client_manager().send_model_call(payload, b"session", self)

                    # 更详细的错误处理
                    if job_id is None:
                        logger.error(f"第 {attempt+1} 次尝试：创建会话失败，无法获取 job_id")
                        time.sleep(1)
                        continue

                    result = get_quantum_client_manager().query_result(job_id, timeout=30)
                    if result and isinstance(result, dict):
                        session_id = result.get("sessionID", "")
                        if session_id:
                            self.session_id = session_id
                            self.job_id = job_id
                            logger.info(f"成功创建会话，session_id: {self.session_id}, job_id: {self.job_id}")
                            return True
                    logger.warning(f"第 {attempt+1} 次尝试：未能获取有效的 sessionID")
                    time.sleep(1)  # 短暂等待后重试
                except Exception as e:
                    logger.warning(f"第 {attempt+1} 次尝试：查询结果失败: {e}")
                    time.sleep(1)
                    
            logger.error("创建会话失败：超过最大重试次数仍未获取到 sessionID")
            return False
            
        except Exception as e:
            logger.error(f"创建会话请求发送失败: {e}")
            return False
    # ========================================
    # Memory数据处理
    # ========================================
    def get_all_memory(self):
        """
        获取所有memory数据的接口
        对应量子SDK的fkb_memory命令
        # """

        try:
            # 构建获取所有memory的payload，使用与测试代码相同的格式
            payload = {
                "action": "get_all_memory",
                "model": "lucene_AAITC-Emb_hybrid"
            }
            
            logger.info(f"获取所有memory数据: {payload}")
            
            start_time = time.time()
            # 使用b"fkb_memory"命令类型发送请求，与测试代码一致
            job_id = get_quantum_client_manager().send_model_call(
                payload=payload, 
                command_type=b"fkb_memory", 
                api_instance=self
            )
            end_time = time.time()
            response_time = end_time - start_time
            
            if job_id is not None:
                logger.info(f"成功发送获取memory请求，job_id: {job_id}")
                
                # 查询结果
                result = get_quantum_client_manager().query_result(job_id, timeout=180)
                
                if result is not None:
                    logger.info("成功获取memory数据")
                    return {
                        "success": True,
                        "data": result,
                        "response_time": response_time,
                        "status_code": 200
                    }
                else:
                    logger.info("获取memory数据失败")
                    return {
                        "success": False,
                        "data": None,
                        "response_time": response_time,
                        "status_code": 500,
                        "error": "查询结果为空"
                    }
            else:
                logger.info("发送获取memory请求失败")
                return {
                    "success": False,
                    "data": None,
                    "response_time": response_time,
                    "status_code": 500,
                    "error": "无法获取job_id"
                }
        except Exception as e:
            logger.info(f"获取memory数据请求发送失败: {e}")
            return {
                "success": False,
                "data": None,
                "response_time": 0,
                "error": str(e)
            }
    #优化写入json文件
    def save_memory_to_json(self, memory_data, json_path):
        """
        将memory数据保存到JSON文件中
        """
        try:
            if memory_data is None:
                logger.warning("memory_data为None，无法保存")
                return False
            
            # 创建包含memory数据的字典
            memory_dict = {
                'memory_data': memory_data,
                'timestamp': datetime.now().isoformat(),
                'type': 'fkb_memory'
            }
            
            # 确保目录存在
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            
            # 直接写入JSON文件，覆盖原有内容
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(memory_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Memory数据已保存到 {json_path}")
            return True
            
        except PermissionError:
            logger.error(f"权限不足，无法写入文件: {json_path}")
            return False
        except Exception as e:
            logger.error(f"保存memory数据到JSON失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    def get_all_ocr_memory(self):
        """
        获取所有OCR memory数据的接口
        对应量子SDK的fkb_memory命令，使用OCR bucket
        """
        try:
            # 构建获取所有OCR memory的payload，使用OCR bucket
            payload = {
                "action": "get_all_memory",
                "model": "default",
                "bucket": "OCR"
            }
            
            logger.info(f"获取所有OCR memory数据: {payload}")
            
            start_time = time.time()
            # 使用b"fkb_memory"命令类型发送请求，与测试代码一致
            job_id = get_quantum_client_manager().send_model_call(
                payload=payload, 
                command_type=b"fkb_memory", 
                api_instance=self
            )
            end_time = time.time()
            response_time = end_time - start_time
            
            if job_id is not None:
                logger.info(f"成功发送获取OCR memory请求，job_id: {job_id}")
                
                # 查询结果
                result = get_quantum_client_manager().query_result(job_id, timeout=180)
                
                if result is not None:
                    logger.info("成功获取OCR memory数据")
                    return {
                        "success": True,
                        "data": result,
                        "response_time": response_time,
                        "status_code": 200
                    }
                else:
                    logger.info("获取OCR memory数据失败")
                    return {
                        "success": False,
                        "data": None,
                        "response_time": response_time,
                        "status_code": 500,
                        "error": "查询结果为空"
                    }
            else:
                logger.info("发送获取OCR memory请求失败")
                return {
                    "success": False,
                    "data": None,
                    "response_time": response_time,
                    "status_code": 500,
                    "error": "无法获取job_id"
                }
        except Exception as e:
            logger.info(f"获取OCR memory数据请求发送失败: {e}")
            return {
                "success": False,
                "data": None,
                "response_time": 0,
                "error": str(e)
            }

    def save_ocr_memory_to_json(self, memory_data, json_path):
        """
        将OCR memory数据保存到JSON文件中
        """
        try:
            if memory_data is None:
                logger.warning("memory_data为None，无法保存")
                return False
            
            # 创建包含OCR memory数据的字典
            memory_dict = {
                'memory_data': memory_data,
                'timestamp': datetime.now().isoformat(),
                'type': 'fkb_memory_ocr'
            }
            
            # 确保目录存在
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            
            # 直接写入JSON文件，覆盖原有内容
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(memory_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"OCR Memory数据已保存到 {json_path}")
            return True
            
        except PermissionError:
            logger.error(f"权限不足，无法写入文件: {json_path}")
            return False
        except Exception as e:
            logger.error(f"保存OCR memory数据到JSON失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def _recalculate_statistics(self, df, worksheet, user_content_columns):
        """
        重新计算所有有效数据的平均值（包括重跑成功的case）
        """
        logger.info("开始重新计算统计数据...")
        
        # 重新收集所有有效的响应时间和TTFT数据
        response_times = []
        ttft_times = []
        
        # 遍历所有数据行
        for row_index in range(len(df)):
            for col_index, column_name in enumerate(user_content_columns):
                result_col_index = len(df.columns) + col_index * 5
                write_row = row_index + 2  # Excel行号从2开始（第1行是标题）
                
                # 获取响应时间
                time_column = chr(ord('A') + result_col_index + 1)
                time_cell_value = worksheet[f'{time_column}{write_row}'].value
                
                # 检查是否为有效数字且大于0（排除失败的case）
                if time_cell_value is not None and isinstance(time_cell_value, (int, float)) and time_cell_value > 0:
                    response_times.append(time_cell_value)
                
                # 获取TTFT时间
                ttft_column = chr(ord('A') + result_col_index + 2)
                ttft_cell_value = worksheet[f'{ttft_column}{write_row}'].value
                
                # 检查是否为有效数字且大于0
                if ttft_cell_value is not None and isinstance(ttft_cell_value, (int, float)) and ttft_cell_value > 0:
                    ttft_times.append(ttft_cell_value)
        
        # 计算平均值
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        avg_ttft = sum(ttft_times) / len(ttft_times) if ttft_times else 0
        
        # 更新Excel中的平均值行
        last_row = len(df) + 2
        avg_label_col = chr(ord('A'))
        
        # 清空之前的平均值行
        for col_index in range(len(worksheet[1])):  # 清空整行
            col_letter = chr(ord('A') + col_index)
            worksheet[f'{col_letter}{last_row}'] = ""
        
        # 重新写入平均值标签
        worksheet[f'{avg_label_col}{last_row}'] = "平均值(过滤Error后)"
        
        # 为每个user_content列更新平均值
        for col_index, column_name in enumerate(user_content_columns):
            result_col_index = len(df.columns) + col_index * 5
            time_column = chr(ord('A') + result_col_index + 1)
            ttft_column = chr(ord('A') + result_col_index + 2)
            
            # 写入平均响应时间
            if response_times:
                worksheet[f'{time_column}{last_row}'] = round(avg_response_time, 2)
            else:
                worksheet[f'{time_column}{last_row}'] = "N/A"
            
            # 写入平均TTFT
            if ttft_times:
                worksheet[f'{ttft_column}{last_row}'] = round(avg_ttft, 3)
            else:
                worksheet[f'{ttft_column}{last_row}'] = "N/A"
        
        logger.info(f"重新计算完成:")
        logger.info(f"  - 有效响应时间数据点: {len(response_times)} 个")
        logger.info(f"  - 响应时间平均值: {avg_response_time:.2f}秒")
        logger.info(f"  - 有效TTFT数据点: {len(ttft_times)} 个") 
        logger.info(f"  - TTFT平均值: {avg_ttft:.3f}秒")
        return avg_response_time, avg_ttft
    def process_memory_data(self, min_wait_time=1.0, max_wait_time=10.0, enable_random_wait=True):
        """
        处理Memory_data.xlsx文件，在文档注册前执行
        读取Memory_data.xlsx文件，为每行创建新会话，对包含"user_content"的列执行查询
        支持文本、图片、以及 add_memory 操作
        """
        # 读取Excel文件
        memory_excel_path = get_config().get('MEMORY_EXCEL_PATH')
        
        # Memory 输出统一写入本次运行目录下（运行时从 run_context 获取，避免导入时为 None）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        memory_output_path = run_context.OUTPUT_ROOT / f"Memory_data_with_responses_{timestamp}.xlsx"
        # 记录到实例上，供外部使用
        self.memory_output_path = str(memory_output_path)
        
        if not os.path.exists(memory_excel_path):
            logger.info(f"Memory文件不存在: {memory_excel_path}")
            return False
        
        try:
            df = pd.read_excel(memory_excel_path)
            logger.info(f"成功读取Memory Excel文件，共有 {len(df)} 行数据")
        except Exception as e:
            logger.info(f"读取Memory Excel文件失败: {e}")
            return False
        
        # 筛选出包含"user_content"的列
        user_content_columns = [col for col in df.columns if 'user_content' in col]
        if not user_content_columns:
            logger.info("未找到包含'user_content'的列")
            return True  # 不是错误，只是没有需要处理的列
        
        logger.info(f"找到 {len(user_content_columns)} 个包含'user_content'的列: {user_content_columns}")
        
        # 创建新的列名列表，包含原始列和结果列
        new_columns = list(df.columns)
        for col_name in user_content_columns:
            new_columns.append(f"{col_name}_result")
            new_columns.append(f"{col_name}_response_time")
            new_columns.append(f"{col_name}_ttft")  # 新增TTFT
            new_columns.append(f"{col_name}_data_json_list")
            new_columns.append(f"{col_name}_toolname")
        
        # 如果输出文件不存在，先创建它
        if not os.path.exists(memory_output_path):
            # 创建新的DataFrame包含所有列名
            new_df = pd.DataFrame(columns=new_columns)
            # 复制原始数据
            for col in df.columns:
                new_df[col] = df[col]
            # 保存带新列标题的DataFrame到Excel
            new_df.to_excel(memory_output_path, index=False)
        
        try:
            workbook = openpyxl.load_workbook(memory_output_path)
            worksheet = workbook.active
        except Exception as e:
            logger.info(f"加载Memory Excel文件失败: {e}")
            return False
        
        # 为每行处理数据并立即写入
        response_times = []  # 收集响应时间用于计算平均值
        ttft_times = []  # 收集TTFT时间用于计算平均值

        for row_index, row in df.iterrows():
            logger.info(f"\n处理Memory第 {row_index + 1} 行...")
            
            # 为每行创建新会话
            memory_api = MultimodalAPI()
            
            # 创建会话
            if not memory_api.create_session():
                logger.info(f"第 {row_index + 1} 行会话创建失败")
                # 在结果列中记录失败信息
                for col_index, column_name in enumerate(user_content_columns):
                    if column_name in row and (not pd.isna(row[column_name]) and row[column_name] != ""):
                        result_col_index = len(df.columns) + col_index * 5
                        write_column = chr(ord('A') + result_col_index)
                        write_row = row_index + 2
                        worksheet[f'{write_column}{write_row}'] = "会话创建失败"
                
                try:
                    workbook.save(memory_output_path)
                    logger.info(f"第 {row_index + 1} 行结果已保存")
                except Exception as e:
                    logger.info(f"保存第 {row_index + 1} 行结果失败: {e}")
                continue
            
            # 仅为包含"user_content"的列执行查询
            for col_index, column_name in enumerate(user_content_columns):
                cell_value = row[column_name]
                
                logger.info(f"处理第 {row_index + 1} 行, 列 '{column_name}'...")
                
                # 检查是否有pathlist列并处理图片路径
                image_paths = []
                missing_images = []
                if 'pathlist' in df.columns and row_index < len(df):
                    pathlist_value = df.iloc[row_index]['pathlist']
                    if not pd.isna(pathlist_value) and pathlist_value and str(pathlist_value).lower() not in ['nan', 'none', 'null', '']:
                        pathlist_str = str(pathlist_value).strip()
                        if pathlist_str:
                            image_names = [name.strip() for name in re.split(r'[,;]+', pathlist_str) if name.strip()]
                            
                            for image_name in image_names:
                                if image_name.lower() in ['nan', 'none', 'null', '']:
                                    continue
                                
                                found_image = None
                                image_dir = get_config().get('IMAGE_DIR')
                                if image_dir is not None:
                                    for file_path in image_dir.rglob(image_name):
                                        if file_path.is_file():
                                            found_image = str(file_path)
                                            break
                                
                                if found_image:
                                    image_paths.append(found_image)
                                    logger.info(f"找到图片文件: {found_image}")
                                else:
                                    missing_images.append(image_name)
                                    logger.info(f"在目录 {image_dir} 中未找到图片文件: {image_name}")
                
                # 处理逻辑：4种情况
                if pd.isna(cell_value) or cell_value == "":
                    if not image_paths:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content为空且无图片，跳过执行")
                        continue
                    else:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content为空，但有图片，仅发送图片")
                else:
                    if image_paths:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content不为空且有图片，发送文本+图片")
                    else:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content不为空但无图片，仅发送文本")

                # 图片缺失处理
                if missing_images and not image_paths:
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 所有图片都未找到，跳过执行")
                    result_col_index = len(df.columns) + col_index * 5
                    write_column = chr(ord('A') + result_col_index)
                    write_row = row_index + 2
                    worksheet[f'{write_column}{write_row}'] = "Error: 所有图片未找到"
                    
                    try:
                        workbook.save(memory_output_path)
                        logger.info(f"第 {row_index + 1} 行结果已保存")
                    except Exception as e:
                        logger.info(f"保存第 {row_index + 1} 行结果失败: {e}")
                    continue
                
                # 发送请求：根据是否为 add_memory 决定调用方式
                query_text = "" if (pd.isna(cell_value) or cell_value == "") else str(cell_value)
                
                # 使用 add_memory 而不是 send_query_with_image
                if memory_api.add_memory(user_text=query_text, image_paths=image_paths if image_paths else None):
                    # 获取 add_memory 的结果
                    response_content = memory_api.get_add_memory_result()
                    response_time = memory_api.get_response_time()
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' add_memory 结果: {response_content}")
                    # 记录写入位置
                    result_col_index = len(df.columns) + col_index * 5
                    write_column = chr(ord('A') + result_col_index)
                    write_row = row_index + 2
                    
                    # 检查是否有错误
                    has_error = False
                    if isinstance(response_content, dict) and "error" in response_content:
                        has_error = True
                    
                    # 写入响应内容
                    worksheet[f'{write_column}{write_row}'] = json.dumps(response_content, ensure_ascii=False, indent=2) if response_content else "无响应内容"
                    
                    # 写入响应时间
                    if response_time is not None:
                        time_column = chr(ord('A') + result_col_index + 1)
                        worksheet[f'{time_column}{write_row}'] = round(response_time, 2)
                        if not has_error:
                            response_times.append(response_time)
                    
                    # 写入 TTFT
                    ttft_column = chr(ord('A') + result_col_index + 2)
                    ttft_value = getattr(memory_api, 'ttft_seconds', 0)
                    worksheet[f'{ttft_column}{write_row}'] = round(ttft_value, 3)
                    if not has_error:
                        ttft_times.append(ttft_value)
                    
                    # 写入 data_json_list
                    data_json_list_column = chr(ord('A') + result_col_index + 3)
                    if hasattr(memory_api, 'data_json_list') and memory_api.data_json_list:
                        data_json_str = json.dumps(memory_api.data_json_list, ensure_ascii=False, indent=2)
                        worksheet[f'{data_json_list_column}{write_row}'] = data_json_str
                    else:
                        worksheet[f'{data_json_list_column}{write_row}'] = "[]"
                    
                    # 提取 toolname
                    toolname_column = chr(ord('A') + result_col_index + 4)
                    toolname_value =memory_api.extract_toolname_from_data_json_list()
                    toolname_value = json.dumps(toolname_value, ensure_ascii=False) if toolname_value else "[]"
                    worksheet[f'{toolname_column}{write_row}'] = toolname_value
                    
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 处理完成")
                # else:
                    # logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 查询发送失败")
                    # result_col_index = len(df.columns) + col_index * 5
                    # write_column = chr(ord('A') + result_col_index)
                    # write_row = row_index + 2
                    # worksheet[f'{write_column}{write_row}'] = "查询发送失败"
                else:
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 查询发送失败")
                    result_col_index = len(df.columns) + col_index * 5
                    write_column = chr(ord('A') + result_col_index)
                    write_row = row_index + 2
                    
                    # 检查是否在 data_json_list 中有失败信息（包括 CTTVError 等）
                    failure_message = "查询发送失败"
                    if hasattr(memory_api, 'data_json_list') and memory_api.data_json_list:
                        # 查找最新的失败条目
                        latest_failure = None
                        for entry in reversed(memory_api.data_json_list):
                            if entry.get('status') == 'failed' and 'data' in entry:
                                latest_failure = entry
                                break
                        
                        if latest_failure:
                            failure_data = latest_failure['data']
                            # 统一处理 list / str / 其他类型，确保像 CTTVError 这类信息能写入
                            if isinstance(failure_data, list):
                                if failure_data:
                                    # 将列表里的所有元素拼成字符串（通常只有一个，如 CTTVError: ...）
                                    failure_message = ', '.join(map(str, failure_data))
                            else:
                                failure_message = str(failure_data)
                    
                    worksheet[f'{write_column}{write_row}'] = failure_message
                    
                    # 写入响应时间（0表示失败）
                    time_column = chr(ord('A') + result_col_index + 1)
                    worksheet[f'{time_column}{write_row}'] = 0
                    
                    # 写入TTFT
                    ttft_column = chr(ord('A') + result_col_index + 2)
                    worksheet[f'{ttft_column}{write_row}'] = 0
                    
                    # 写入 data_json_list（包含失败信息）
                    data_json_list_column = chr(ord('A') + result_col_index + 3)
                    if hasattr(memory_api, 'data_json_list') and memory_api.data_json_list:
                        data_json_str = json.dumps(memory_api.data_json_list, ensure_ascii=False, indent=2)
                        worksheet[f'{data_json_list_column}{write_row}'] = data_json_str
                    else:
                        worksheet[f'{data_json_list_column}{write_row}'] = "[]"
                    
                    # 提取 toolname（可能为空）
                    toolname_column = chr(ord('A') + result_col_index + 4)
                    toolname_value = memory_api.extract_toolname_from_data_json_list()
                    toolname_value = json.dumps(toolname_value, ensure_ascii=False) if toolname_value else "[]"
                    worksheet[f'{toolname_column}{write_row}'] = toolname_value
                
                # 保存到文件
                try:
                    workbook.save(memory_output_path)
                    logger.info(f"第 {row_index + 1} 行结果已保存")
                except Exception as e:
                    logger.info(f"保存第 {row_index + 1} 行结果失败: {e}")
                
                # 随机等待
                if enable_random_wait:
                    wait_time = random.uniform(min_wait_time, max_wait_time)
                    logger.info(f"第 {row_index + 1} 个Memory行执行完成，随机等待 {wait_time:.2f} 秒...")
                    time.sleep(wait_time)
                else:
                    logger.info(f"第 {row_index + 1} 个Memory行执行完成，随机等待已禁用")

        # 使用统一的方法重新计算所有有效数据的平均值（包括重跑成功的case）
        initial_avg_response_time, initial_avg_ttft = self._recalculate_statistics(
            df, worksheet, user_content_columns
        )
        # # 计算并记录平均值
        # if response_times:
        #     avg_response_time = sum(response_times) / len(response_times)
        #     logger.info(f"响应时间平均值(过滤Error后): {avg_response_time:.2f}秒 (共 {len(response_times)} 个有效数据点)")
        # else:
        #     avg_response_time = 0
        #     logger.info("没有有效的响应时间用于计算平均值")

        # if ttft_times:
        #     avg_ttft = sum(ttft_times) / len(ttft_times)
        #     logger.info(f"TTFT平均值(过滤Error后): {avg_ttft:.3f}秒 (共 {len(ttft_times)} 个有效数据点)")
        # else:
        #     avg_ttft = 0
        #     logger.info("没有有效的TTFT时间用于计算平均值")

        # # 添加平均值到Excel
        # if response_times or ttft_times:
        #     last_row = len(df) + 2
        #     avg_label_col = chr(ord('A'))
        #     worksheet[f'{avg_label_col}{last_row}'] = "平均值(过滤Error后)"
            
        #     for col_index, column_name in enumerate(user_content_columns):
        #         result_col_index = len(df.columns) + col_index * 5
        #         time_column = chr(ord('A') + result_col_index + 1)
        #         ttft_column = chr(ord('A') + result_col_index + 2)
                
        #         worksheet[f'{time_column}{last_row}'] = round(avg_response_time, 2) if response_times else "N/A"
        #         worksheet[f'{ttft_column}{last_row}'] = round(avg_ttft, 3) if ttft_times else "N/A"

        # 检查是否有需要重跑的错误case
        need_rerun_indices = []
        for row_index, row in df.iterrows():
            for col_index, column_name in enumerate(user_content_columns):
                result_col_index = len(df.columns) + col_index * 5
                write_column = chr(ord('A') + result_col_index)
                write_row = row_index + 2
                result_cell = worksheet[f'{write_column}{write_row}'].value
                
                # 检查是否需要重跑：
                # 1）包含 "failed"（SDK 业务失败）
                # 2）包含 "CTTVError"（本地封装的 CTTVError 前缀）
                # 3）包含 "timeout"（请求 / 流式超时）
                # 4）包含 "查询发送失败"（例如 entries 非有效列表导致的发送失败）
                if result_cell:
                    original_text = str(result_cell)
                    text = original_text.lower()
                    if (
                        "failed" in text
                        or "cttverror" in text
                        or "timeout" in text
                        or "查询发送失败" in original_text
                    ):
                        if (row_index, col_index) not in need_rerun_indices:
                            need_rerun_indices.append((row_index, col_index))

        if need_rerun_indices:
            logger.info(f"发现 {len(need_rerun_indices)} 个需要重跑的错误case: {need_rerun_indices}")
            
            # 整体按批次重跑：所有需要重跑的 case 一轮轮重试
            max_rerun_rounds = 2  # 整体重试轮数，例如 3 个 case 就是 1,2,3 一轮；再 1,2,3 第二轮
            
            for round_idx in range(max_rerun_rounds):
                logger.info(f"开始第 {round_idx + 1}/{max_rerun_rounds} 轮重跑...")
                round_had_failure = False
                
                for row_index, col_index in need_rerun_indices:
                    column_name = user_content_columns[col_index]
                    
                    # 每轮开始前，重新检查当前单元格是否仍然是失败状态；如果前一轮已经成功，这一轮就跳过
                    result_col_index = len(df.columns) + col_index * 5
                    write_column = chr(ord('A') + result_col_index)
                    write_row = row_index + 2
                    current_cell = worksheet[f'{write_column}{write_row}'].value
                    
                    if not current_cell:
                        continue
                    
                    current_text = str(current_cell).lower()
                    current_text_raw = str(current_cell)
                    # 与收集 need_rerun_indices 时的条件一致：除 failed/cttverror/timeout 外，也需识别「查询发送失败」
                    if not (
                        "failed" in current_text
                        or "cttverror" in current_text
                        or "timeout" in current_text
                        or "查询发送失败" in current_text_raw
                    ):
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 已在之前轮重跑成功，本轮跳过")
                        continue
                    
                    # 取原始 user_content 作为本轮请求的输入
                    cell_value = df.iloc[row_index][column_name]
                    
                    logger.info(f"第 {round_idx + 1} 轮重跑第 {row_index + 1} 行, 列 '{column_name}'...")
                    
                    # 为重跑创建新会话
                    memory_api = MultimodalAPI()
                    
                    # 创建会话
                    if not memory_api.create_session():
                        logger.info(f"重跑第 {row_index + 1} 行会话创建失败")
                        round_had_failure = True
                        # 记录失败信息但不阻塞其他 case
                        failure_message = "重跑失败：会话创建失败"
                        worksheet[f'{write_column}{write_row}'] = failure_message
                        try:
                            workbook.save(memory_output_path)
                            logger.info(f"重跑第 {row_index + 1} 行结果已保存")
                        except Exception as e:
                            logger.info(f"保存重跑第 {row_index + 1} 行结果失败: {e}")
                        continue
                    
                    # 检查是否有pathlist列并处理图片路径
                    image_paths = []
                    if 'pathlist' in df.columns and row_index < len(df):
                        pathlist_value = df.iloc[row_index]['pathlist']
                        if not pd.isna(pathlist_value) and pathlist_value and str(pathlist_value).lower() not in ['nan', 'none', 'null', '']:
                            pathlist_str = str(pathlist_value).strip()
                            if pathlist_str:
                                image_names = [name.strip() for name in re.split(r'[,;]+', pathlist_str) if name.strip()]
                                
                                for image_name in image_names:
                                    if image_name.lower() in ['nan', 'none', 'null', '']:
                                        continue
                                
                                    found_image = None
                                    image_dir = get_config().get('IMAGE_DIR')
                                    if image_dir is not None:
                                        for file_path in image_dir.rglob(image_name):
                                            if file_path.is_file():
                                                found_image = str(file_path)
                                                break
                                
                                    if found_image:
                                        image_paths.append(found_image)
                                        logger.info(f"找到图片文件: {found_image}")
                    
                    # 发送请求
                    query_text = "" if (pd.isna(cell_value) or cell_value == "") else str(cell_value)
                    
                    if memory_api.add_memory(user_text=query_text, image_paths=image_paths if image_paths else None):
                        # 获取 add_memory 的结果
                        response_content = memory_api.get_add_memory_result()
                        response_time = memory_api.get_response_time()
                        logger.info(f"重跑第 {row_index + 1} 行, 列 '{column_name}' add_memory 结果: {response_content}")
                        
                        # 记录写入位置（上面已算过 result_col_index / write_column / write_row）
                        
                        # 检查是否有错误
                        has_error = False
                        if isinstance(response_content, dict) and "error" in response_content:
                            has_error = True
                        
                        # 更新响应内容
                        worksheet[f'{write_column}{write_row}'] = json.dumps(response_content, ensure_ascii=False, indent=2) if response_content else "无响应内容"
                        
                        # 更新响应时间
                        if response_time is not None:
                            time_column = chr(ord('A') + result_col_index + 1)
                            worksheet[f'{time_column}{write_row}'] = round(response_time, 2)
                            if not has_error:
                                response_times.append(response_time)
                        
                        # 更新 TTFT
                        ttft_column = chr(ord('A') + result_col_index + 2)
                        ttft_value = getattr(memory_api, 'ttft_seconds', 0)
                        worksheet[f'{ttft_column}{write_row}'] = round(ttft_value, 3)
                        if not has_error:
                            ttft_times.append(ttft_value)
                        
                        # 更新 data_json_list
                        data_json_list_column = chr(ord('A') + result_col_index + 3)
                        if hasattr(memory_api, 'data_json_list') and memory_api.data_json_list:
                            data_json_str = json.dumps(memory_api.data_json_list, ensure_ascii=False, indent=2)
                            worksheet[f'{data_json_list_column}{write_row}'] = data_json_str
                        else:
                            worksheet[f'{data_json_list_column}{write_row}'] = "[]"
                        
                        # 更新 toolname
                        toolname_column = chr(ord('A') + result_col_index + 4)
                        toolname_value = memory_api.extract_toolname_from_data_json_list()
                        toolname_value = json.dumps(toolname_value, ensure_ascii=False) if toolname_value else "[]"
                        worksheet[f'{toolname_column}{write_row}'] = toolname_value
                        
                        logger.info(f"重跑第 {row_index + 1} 行, 列 '{column_name}' 成功")
                    
                    else:
                        logger.info(f"重跑第 {row_index + 1} 行, 列 '{column_name}' 失败")
                        round_had_failure = True
                        
                        # 检查重跑是否也是 "failed" 错误
                        failure_message = "重跑失败"
                        if hasattr(memory_api, 'data_json_list') and memory_api.data_json_list:
                            latest_failure = None
                            for entry in reversed(memory_api.data_json_list):
                                if entry.get('status') == 'failed' and 'data' in entry:
                                    latest_failure = entry
                                    break
                            
                            if latest_failure:
                                failure_data = latest_failure['data']
                                if isinstance(failure_data, list) and len(failure_data) >= 2:
                                    failure_message = ', '.join(map(str, failure_data))
                        
                        # 更新失败信息
                        worksheet[f'{write_column}{write_row}'] = failure_message
                    
                    # 保存重跑结果到文件
                    try:
                        workbook.save(memory_output_path)
                        logger.info(f"重跑第 {row_index + 1} 行结果已保存")
                    except Exception as e:
                        logger.info(f"保存重跑第 {row_index + 1} 行结果失败: {e}")
                
                # 如果本轮已经没有失败 case，提前结束后续轮次
                if not round_had_failure:
                    logger.info(f"第 {round_idx + 1} 轮重跑结束，所有需要重跑的case均已成功，提前结束重跑循环")
                    break
                
                # 如果还有失败的 case，且不是最后一轮，则在轮次之间等待 5 分钟
                if round_had_failure and round_idx < max_rerun_rounds - 1:
                    logger.info("本轮重跑仍有失败case，等待5分钟后进行下一轮重跑...")
                    time.sleep(300)
        # if need_rerun_indices:
        #     logger.info(f"发现 {len(need_rerun_indices)} 个需要重跑的错误case: {need_rerun_indices}")
            
        #     # 重跑错误的case
        #     consecutive_failed_count = 0  # 当前case的连续失败计数
        #     rerun_idx = 0
        #     max_retries_per_case = 3      # 每个case最多重试次数，防止单个case长时间阻塞
        #     while rerun_idx < len(need_rerun_indices):
        #         row_index, col_index = need_rerun_indices[rerun_idx]
        #         column_name = user_content_columns[col_index]
        #         cell_value = df.iloc[row_index][column_name]
                
        #         # 如果当前case已经连续失败超过最大次数，则跳过该case，继续下一个
        #         if consecutive_failed_count >= max_retries_per_case:
        #             logger.info(
        #                 f"第 {row_index + 1} 行, 列 '{column_name}' 已连续失败 {consecutive_failed_count} 次，"
        #                 f"跳过该case，继续处理下一个需要重跑的case"
        #             )
        #             consecutive_failed_count = 0
        #             rerun_idx += 1
        #             continue
        #         # 检查是否是连续失败
        #         if consecutive_failed_count > 0:
        #             # 如果连续失败，等待5分钟
        #             logger.info(f"检测到连续失败，等待5分钟后重跑第 {rerun_idx + 1} 个错误case...")
        #             time.sleep(300)  # 等待5分钟
                
        #         logger.info(f"重跑第 {row_index + 1} 行, 列 '{column_name}'...")
                
        #         # 为重跑创建新会话
        #         memory_api = MultimodalAPI()
                
        #         # 创建会话
        #         if not memory_api.create_session():
        #             logger.info(f"重跑第 {row_index + 1} 行会话创建失败")
        #             consecutive_failed_count += 1
        #             # 仅移动到下一个case，不重试当前case
        #             rerun_idx += 1
        #             continue
                
        #         # 检查是否有pathlist列并处理图片路径
        #         image_paths = []
        #         if 'pathlist' in df.columns and row_index < len(df):
        #             pathlist_value = df.iloc[row_index]['pathlist']
        #             if not pd.isna(pathlist_value) and pathlist_value and str(pathlist_value).lower() not in ['nan', 'none', 'null', '']:
        #                 pathlist_str = str(pathlist_value).strip()
        #                 if pathlist_str:
        #                     image_names = [name.strip() for name in re.split(r'[,;]+', pathlist_str) if name.strip()]
                            
        #                     for image_name in image_names:
        #                         if image_name.lower() in ['nan', 'none', 'null', '']:
        #                             continue
                                
        #                         found_image = None
        #                         if 'IMAGE_DIR' in globals():
        #                             for file_path in IMAGE_DIR.rglob(image_name):
        #                                 if file_path.is_file():
        #                                     found_image = str(file_path)
        #                                     break
                                
        #                         if found_image:
        #                             image_paths.append(found_image)
        #                             logger.info(f"找到图片文件: {found_image}")
                
        #         # 发送请求
        #         query_text = "" if (pd.isna(cell_value) or cell_value == "") else str(cell_value)
                
        #         if memory_api.add_memory(user_text=query_text, image_paths=image_paths if image_paths else None):
        #             # 获取 add_memory 的结果
        #             response_content = memory_api.get_add_memory_result()
        #             response_time = memory_api.get_response_time()
        #             logger.info(f"重跑第 {row_index + 1} 行, 列 '{column_name}' add_memory 结果: {response_content}")
                    
        #             # 记录写入位置
        #             result_col_index = len(df.columns) + col_index * 5
        #             write_column = chr(ord('A') + result_col_index)
        #             write_row = row_index + 2
                    
        #             # 检查是否有错误
        #             has_error = False
        #             if isinstance(response_content, dict) and "error" in response_content:
        #                 has_error = True
                    
        #             # 更新响应内容
        #             worksheet[f'{write_column}{write_row}'] = json.dumps(response_content, ensure_ascii=False, indent=2) if response_content else "无响应内容"
                    
        #             # 更新响应时间
        #             if response_time is not None:
        #                 time_column = chr(ord('A') + result_col_index + 1)
        #                 worksheet[f'{time_column}{write_row}'] = round(response_time, 2)
        #                 if not has_error:
        #                     response_times.append(response_time)
                    
        #             # 更新 TTFT
        #             ttft_column = chr(ord('A') + result_col_index + 2)
        #             ttft_value = getattr(memory_api, 'ttft_seconds', 0)
        #             worksheet[f'{ttft_column}{write_row}'] = round(ttft_value, 3)
        #             if not has_error:
        #                 ttft_times.append(ttft_value)
                    
        #             # 更新 data_json_list
        #             data_json_list_column = chr(ord('A') + result_col_index + 3)
        #             if hasattr(memory_api, 'data_json_list') and memory_api.data_json_list:
        #                 data_json_str = json.dumps(memory_api.data_json_list, ensure_ascii=False, indent=2)
        #                 worksheet[f'{data_json_list_column}{write_row}'] = data_json_str
        #             else:
        #                 worksheet[f'{data_json_list_column}{write_row}'] = "[]"
                    
        #             # 更新 toolname
        #             toolname_column = chr(ord('A') + result_col_index + 4)
        #             toolname_value = memory_api.extract_toolname_from_data_json_list()
        #             toolname_value = json.dumps(toolname_value, ensure_ascii=False) if toolname_value else "[]"
        #             worksheet[f'{toolname_column}{write_row}'] = toolname_value
                    
        #             logger.info(f"重跑第 {row_index + 1} 行, 列 '{column_name}' 成功")
                    
        #             # 如果重跑成功，重置连续失败计数，并移动到下一个case
        #             consecutive_failed_count = 0
        #             rerun_idx += 1
        #         else:
        #             logger.info(f"重跑第 {row_index + 1} 行, 列 '{column_name}' 失败")
                    
        #             # 检查重跑是否也是 "failed" 错误
        #             failure_message = "重跑失败"
        #             if hasattr(memory_api, 'data_json_list') and memory_api.data_json_list:
        #                 latest_failure = None
        #                 for entry in reversed(memory_api.data_json_list):
        #                     if entry.get('status') == 'failed' and 'data' in entry:
        #                         latest_failure = entry
        #                         break
                        
        #                 if latest_failure:
        #                     failure_data = latest_failure['data']
        #                     if isinstance(failure_data, list) and len(failure_data) >= 2:
        #                         failure_message = str(failure_data)
        #                         failure_message = ', '.join(map(str, failure_data))
                    
        #             # 更新失败信息
        #             result_col_index = len(df.columns) + col_index * 5
        #             write_column = chr(ord('A') + result_col_index)
        #             write_row = row_index + 2
        #             worksheet[f'{write_column}{write_row}'] = failure_message
                    
        #             # 检查是否是同样的错误
        #             if "failed" in str(failure_message).lower():
        #                 consecutive_failed_count += 1
        #                 # 继续尝试重跑同一个case（不增加rerun_idx）
        #                 logger.info(f"重跑失败，继续尝试重跑第 {row_index + 1} 行, 列 '{column_name}'")
        #             else:
        #                 # 如果是其他类型的错误，重置连续失败计数，移动到下一个case
        #                 consecutive_failed_count = 0
        #                 rerun_idx += 1
                
        #         # 保存重跑结果到文件
        #         try:
        #             workbook.save(memory_output_path)
        #             logger.info(f"重跑第 {row_index + 1} 行结果已保存")
        #         except Exception as e:
        #             logger.info(f"保存重跑第 {row_index + 1} 行结果失败: {e}")
            
            # 重跑完成后，重新计算所有数据的平均值
            logger.info("="*50)
            logger.info("所有重跑完成，开始重新计算统计数据...")
            logger.info("="*50)
            
            # 重新计算所有有效数据的平均值
            final_avg_response_time, final_avg_ttft = self._recalculate_statistics(
                df, worksheet, user_content_columns
            )
            
            # 保存更新后的统计数据
            try:
                workbook.save(memory_output_path)
                logger.info("重跑后的统计数据已保存到Excel文件")
            except Exception as e:
                logger.error(f"保存重跑统计数据失败: {e}")
            
            logger.info("="*50)
            logger.info("重跑后统计数据计算完成!")
            logger.info("="*50)


        logger.info("Memory数据处理完成，开始获取memory数据...")
        # 获取普通memory数据
        memory_result = self.get_all_memory()

        # 保存普通memory数据
        if memory_result["success"]:
            memory_data = memory_result["data"]
            logger.info("成功获取memory数据")
            
            try:
                workbook.save(memory_output_path)
                logger.info(f"当前进度已保存: {memory_output_path}")
            except Exception as e:
                logger.error(f"保存当前进度失败: {e}")
            
            # 保存普通memory到JSON文件（与 Memory Excel 同目录）
            memory_json_path = str(memory_output_path).replace('.xlsx', '_get_all_memory.json')
            save_success = self.save_memory_to_json(memory_data, memory_json_path)
            if save_success:
                logger.info("Memory数据已成功保存到JSON文件")
            else:
                logger.error("保存Memory数据到JSON文件失败")
        else:
            logger.error(f"获取memory数据失败: {memory_result.get('error', '未知错误')}")

        # 获取OCR memory数据
        logger.info("开始获取OCR memory数据...")
        ocr_memory_result = self.get_all_ocr_memory()

        # 保存OCR memory数据
        if ocr_memory_result["success"]:
            ocr_memory_data = ocr_memory_result["data"]
            logger.info("成功获取OCR memory数据")
            
            # 保存OCR memory到JSON文件（与 Memory Excel 同目录）
            ocr_memory_json_path = str(memory_output_path).replace('.xlsx', '_get_all_ocr_memory.json')
            ocr_save_success = self.save_ocr_memory_to_json(ocr_memory_data, ocr_memory_json_path)
            if ocr_save_success:
                logger.info("OCR Memory数据已成功保存到JSON文件")
            else:
                logger.error("保存OCR Memory数据到JSON文件失败")
        else:
            logger.error(f"获取OCR memory数据失败: {ocr_memory_result.get('error', '未知错误')}")

        # 最终保存
        try:
            if os.path.exists(memory_output_path):
                with pd.ExcelWriter(memory_output_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    pass
            logger.info(f"\n所有Memory数据处理完成，结果已保存到: {memory_output_path}")
            return True
        except Exception as e:
            logger.error(f"最终保存Memory文件失败: {e}")
            return False
    def extract_toolname_from_data_json_list(self):
        """
        从接口返回中直接获取tool响应，不再从data_json_list中提取
        返回包含所有tool响应的列表
        如果没有找到，返回空列表
        """
        # 直接返回实例中存储的tool响应列表
        if hasattr(self, 'tool_responses') and isinstance(self.tool_responses, list):
            return self.tool_responses[:]
        else:
            return []
    # ========================================
    # 文档注册处理
    # ========================================
    def register_document(self, file_paths):
        """注册文档接口"""
        if not self.session_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        # 确保 file_paths 是一个列表
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        elif file_paths is None:
            file_paths = []
        # 存储原始文档列表（转换为绝对路径）
        self.original_registered_docs = [os.path.abspath(path) for path in file_paths]

        try:
            # 构建注册文档的payload
            payload = {
                "action": "add",
                "body": {
                    "doc_paths": file_paths,
                    "isTempFile": False
                }
            }
            logger.info(f"注册文档: {file_paths}")
            
            start_time = time.time()
            job_id = get_quantum_client_manager().send_model_call(payload, b"document", self)  # 传递 self
            end_time = time.time()
            response_time = end_time - start_time
            
            if job_id is not None:
                upload_id = str(job_id)
                logger.info(f"成功注册文档，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": response_time,
                    "status_code": 200,
                    "response_text": upload_id
                }
            else:
                logger.info("注册文档失败")
                return {
                    "success": False,
                    "upload_id": None,
                    "response_time": response_time,
                    "status_code": 500,
                    "response_text": ""
                }
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return {
                "success": False,
                "upload_id": None,
                "response_time": 0,
                "error": str(e)
            }
    #20260114更新可直接替换
    def get_register_document(self):
        """获取注册文档列表，检查一次文档解析状态"""
        if not self.session_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        try:
            # 构建获取文档列表的payload
            payload = {
                "action": "list",
                "body": {
                    "folder_path": ''
                }
            }
            logger.info("检查文档注册状态...")
            
            start_time = time.time()
            job_id = get_quantum_client_manager().send_model_call(payload, b"document", self)  # 传递 self
            end_time = time.time()
            response_time = end_time - start_time
            
            # 如果有文档注册的起始时间，计算已用时间
            if hasattr(self, '_document_registration_start_time'):
                elapsed_time = time.time() - self._document_registration_start_time
                logger.info(f"文档注册已用时间: {elapsed_time:.2f}秒 ({self._format_time(elapsed_time)})")
            
            if job_id is not None:
                upload_id = str(job_id)
                logger.info(f"成功获取文档列表，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                
                # 获取响应内容
                result = get_quantum_client_manager().query_result(job_id)
                
                # 修改：特别处理空数组的情况
                if result is not None:
                    try:
                        # 处理空数组情况 - 这是正常情况之一
                        if result == []:
                            logger.info("获取到空文档列表，可能是暂无文档或初始状态")
                            # 清除起始时间标记
                            if hasattr(self, '_document_registration_start_time'):
                                delattr(self, '_document_registration_start_time')
                            
                            return {
                                "success": True,  # 空列表也是成功状态
                                "upload_id": upload_id,
                                "response_time": response_time,
                                "status_code": 200,
                                "response_text": upload_id,
                                "doc_ids": [],
                                "documents": [],
                                "total_registration_time": None
                            }
                        
                        # 根据日志信息，result应该直接是一个包含文档的列表
                        if isinstance(result, list):
                            doc_list = result
                        # 或者result是一个字典，其中包含documents字段
                        elif isinstance(result, dict) and "documents" in result:
                            doc_list = result["documents"]
                        else:
                            doc_list = []
                        
                        if isinstance(doc_list, list):
                            if len(doc_list) > 0:
                                logger.info(f"文档数量: {len(doc_list)}")
                                # 检查所有文档的状态
                                has_processing_docs = False
                                doc_ids = []
                                completed_count = 0
                                
                                for doc in doc_list:
                                    if isinstance(doc, dict):
                                        status = doc.get("status", "UNKNOWN").upper()
                                        doc_id = doc.get("id")
                                        if doc_id is not None:
                                            doc_ids.append(doc_id)
                                        if status in ["RUNNING", "ADDED", "PROCESSING", "PENDING"]:
                                            has_processing_docs = True
                                        elif status == "COMPLETED":
                                            completed_count += 1
                                
                                # 修复：使用最初注册的所有文档总数，而不是当前批次的数量
                                if hasattr(self, '_original_total_docs_count'):
                                    total_count = self._original_total_docs_count
                                else:
                                    total_count = len(self.original_registered_docs) if hasattr(self, 'original_registered_docs') and self.original_registered_docs else len(doc_list)
                                
                                completion_rate = (completed_count / total_count) * 100 if total_count > 0 else 0
                                logger.info(f"文档总数: {total_count}, COMPLETED状态的文档数量: {completed_count}, 完成率: {completion_rate:.2f}%")
                                
                                if not has_processing_docs and completion_rate >= 95:
                                    logger.info("所有文档解析完成")
                                    logger.info(f"文档ID列表: {doc_ids}")
                                    
                                    # 计算总耗时（在process_document_registration_only中处理）
                                    # 清除起始时间标记，表示已完成
                                    if hasattr(self, '_document_registration_start_time'):
                                        delattr(self, '_document_registration_start_time')
                                    
                                    # >>> 新增：检查缺失文档 <<<
                                    if hasattr(self, 'original_registered_docs') and self.original_registered_docs:
                                        # 创建一个字典，将返回的文档路径与状态关联
                                        registered_paths = {}
                                        for doc in doc_list:
                                            if isinstance(doc, dict) and "path" in doc:
                                                path = doc["path"]
                                                status = doc.get("status", "UNKNOWN").upper()
                                                registered_paths[path] = status
                                        
                                        # 检查原始文档列表中哪些没有出现在返回列表中
                                        missing_docs = []
                                        for original_path in self.original_registered_docs:
                                            found = False
                                            for registered_path in registered_paths.keys():
                                                if os.path.abspath(original_path) == os.path.abspath(registered_path):
                                                    found = True
                                                    break
                                            
                                            if not found:
                                                missing_docs.append(original_path)
                                        
                                        if missing_docs:
                                            logger.warning(f"发现 {len(missing_docs)} 个文档未成功注册:")
                                            for i, doc_path in enumerate(missing_docs, 1):
                                                logger.warning(f"  {i}. {doc_path}")
                                        else:
                                            logger.info("所有文档都已成功注册")
                                    
                                    # <<< 新增结束 >>>
                                    
                                    # 在所有文档解析完成后，保存文档详细信息到Excel的sheet2
                                    test_results_dir = run_context.TEST_RESULTS_DIR
                                    test_results_dir.mkdir(parents=True, exist_ok=True)
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    default_excel_path = os.path.join(str(test_results_dir), f"document_registration_{timestamp}.xlsx")
                                    
                                    # 创建模拟的result_text结构用于保存
                                    mock_result_data = {
                                        "data": {
                                            "text": json.dumps(doc_list, ensure_ascii=False)
                                        }
                                    }
                                    mock_result_text = json.dumps(mock_result_data, ensure_ascii=False)
                                    
                                    # 调用方法保存文档详细信息到Excel
                                    self.save_document_details_to_excel(mock_result_text, default_excel_path)
                                    
                                    return {
                                        "success": True,
                                        "upload_id": upload_id,
                                        "response_time": response_time,
                                        "status_code": 200,
                                        "response_text": upload_id,
                                        "doc_ids": doc_ids,
                                        "documents": doc_list,
                                        "total_registration_time": None  # 在process_document_registration_only中计算
                                    }
                                elif not has_processing_docs and completion_rate < 90:
                                    # 这里就是您提到的日志语句应该在的位置
                                    logger.info(f"无处理中文档，但完成率较低 ({completion_rate:.2f}%)，继续等待...")
                                    # 返回处理中的状态，继续等待
                                    return {
                                        "success": False,
                                        "upload_id": upload_id,
                                        "response_time": response_time,
                                        "status_code": 200,
                                        "response_text": upload_id,
                                        "doc_ids": doc_ids,
                                        "status": "processing",
                                        "documents": doc_list
                                    }
                                else:
                                    logger.info("仍有文档在处理中")
                                    return {
                                        "success": False,
                                        "upload_id": upload_id,
                                        "response_time": response_time,
                                        "status_code": 200,
                                        "response_text": upload_id,
                                        "doc_ids": doc_ids,
                                        "status": "processing",
                                        "documents": doc_list
                                    }
                            else:
                                logger.info("文档列表为空，任务已完成")
                                # 清除起始时间标记
                                if hasattr(self, '_document_registration_start_time'):
                                    delattr(self, '_document_registration_start_time')
                                
                                return {
                                    "success": True,
                                    "upload_id": upload_id,
                                    "response_time": response_time,
                                    "status_code": 200,
                                    "response_text": upload_id,
                                    "doc_ids": [],
                                    "documents": [],
                                    "total_registration_time": None
                                }
                    except Exception as e:
                        logger.info(f"解析文档列表失败: {e}")
                        # 清除起始时间标记
                        if hasattr(self, '_document_registration_start_time'):
                            delattr(self, '_document_registration_start_time')
                        
                        # 计算总耗时
                        total_time = time.time() - start_time
                        logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                    
                    # 计算总耗时
                    total_time = time.time() - start_time
                    logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                    # 清除起始时间标记
                    if hasattr(self, '_document_registration_start_time'):
                        delattr(self, '_document_registration_start_time')
                    
                    logger.info("没有获取到结果文本，认为任务已完成")
                    return {
                        "success": True,
                        "upload_id": upload_id,
                        "response_time": response_time,
                        "status_code": 200,
                        "response_text": upload_id,
                        "doc_ids": [],
                        "documents": [],
                        "total_registration_time": None
                    }
                else:
                    # 修改：处理result为None的情况
                    logger.info("获取文档列表返回空结果，这可能是临时状态，返回处理中状态")
                    return {
                        "success": False,  # 返回False表示需要继续重试
                        "upload_id": None,
                        "response_time": response_time,
                        "status_code": 200,
                        "response_text": "",
                        "status": "processing",  # 明确指出仍在处理中
                        "total_registration_time": None
                    }
            else:
                logger.info("获取文档列表失败")
                # 清除起始时间标记
                if hasattr(self, '_document_registration_start_time'):
                    delattr(self, '_document_registration_start_time')
                
                return {
                    "success": False,
                    "upload_id": None,
                    "response_time": response_time,
                    "status_code": 500,
                    "response_text": "",
                    "total_registration_time": None
                }
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            # 清除起始时间标记
            if hasattr(self, '_document_registration_start_time'):
                delattr(self, '_document_registration_start_time')
            
            return {
                "success": False,
                "upload_id": None,
                "response_time": 0,
                "error": str(e),
                "total_registration_time": None
            }


    # 添加时间格式化辅助方法到 MultimodalAPI 类中
    def _format_time(self, seconds):
        """将秒数格式化为易读的时间格式"""
        if seconds is None:
            return "N/A"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟{secs}秒"
        elif minutes > 0:
            return f"{minutes}分钟{secs}秒"
        else:
            return f"{secs}秒"


    def save_document_details_to_excel(self, result_text, excel_path):
        """解析文档详细信息并保存到独立的Excel文件"""
        try:
            # 解析result_text
            if isinstance(result_text, str):
                outer_data = json.loads(result_text)
            else:
                outer_data = result_text
                
            doc_list = []
            if isinstance(outer_data, list):
                doc_list = outer_data
            elif isinstance(outer_data, dict):
                if "data" in outer_data and "text" in outer_data["data"]:
                    inner_text = outer_data["data"]["text"]
                    if isinstance(inner_text, str):
                        doc_list = json.loads(inner_text)
                    else:
                        doc_list = inner_text
                elif "documents" in outer_data:
                    doc_list = outer_data["documents"]
            
            if isinstance(doc_list, list) and len(doc_list) > 0:
                # 准备文档详细信息数据
                doc_details = []
                for i, doc in enumerate(doc_list):
                    if isinstance(doc, dict):
                        doc_info = {
                            "id": doc.get("id", ""),
                            "status": doc.get("status", "UNKNOWN"),
                            "errorMsg": doc.get("errorDescription", "") or doc.get("errorMsg", ""),
                            "createTime": doc.get("createTime", ""),
                            "fileName": doc.get("fileName", ""),
                            "editTime": doc.get("editTime", ""),
                            "isDeleted": doc.get("isDeleted", ""),
                            "isTmpFile": doc.get("isTmpFile", ""),
                            "keywords": doc.get("keywords", ""),
                            "labelNameList": str(doc.get("labelNameList", "")),
                            "labelPriority": doc.get("labelPriority", ""),
                            "md5": doc.get("md5", ""),
                            "ownerId": doc.get("ownerId", ""),
                            "previewPath": doc.get("previewPath", ""),
                            "priority": doc.get("priority", ""),
                            "score": doc.get("score", ""),
                            "summarizedStatus": doc.get("summarizedStatus", ""),
                            "targetFileName": doc.get("targetFileName", ""),
                            "targetFolder": doc.get("targetFolder", ""),
                            "targetLastModifyTime": doc.get("targetLastModifyTime", ""),
                            "targetPath": doc.get("targetPath", ""),
                            "tokenNum": doc.get("tokenNum", ""),
                            "path": doc.get("path", ""),
                            "description": doc.get("description", ""),
                            "docName": doc.get("docName", ""),
                            "fileType": doc.get("fileType", ""),
                            "folder": doc.get("folder", ""),
                            "lastModifyTime": doc.get("lastModifyTime", ""),
                            "source": doc.get("source", ""),
                            "uriPath": doc.get("uriPath", "")
                        }
                        doc_details.append(doc_info)
                
                if doc_details:
                    # 文档注册详情统一写入本次运行目录下的 testresult 目录
                    base_name = os.path.splitext(os.path.basename(excel_path))[0] if excel_path else "document_details"
                    base_dir = run_context.TEST_RESULTS_DIR
                    base_dir.mkdir(parents=True, exist_ok=True)
                    doc_details_path_value = os.path.join(str(base_dir), f"{base_name}_document.xlsx")
                    
                    # 创建包含文档详细信息的DataFrame并保存
                    doc_df = pd.DataFrame(doc_details)
                    doc_df.to_excel(doc_details_path_value, index=False, sheet_name='文档注册详情')
                    
                    logger.info(f"文档详细信息已保存到 {doc_details_path_value}")
                    set_doc_details_path(doc_details_path_value)
                    logger.info(f"共保存 {len(doc_details)} 个文档的详细信息")
                    return True
            else:
                logger.info("文档列表为空，无法保存详细信息")
        except json.JSONDecodeError as e:
            logger.info(f"解析result_text失败: {e}")
        except Exception as e:
            logger.info(f"保存文档详细信息到Excel时出错: {e}")
            import traceback
            traceback.print_exc()
        return False
    # ========================================
    # 查询处理
    # ========================================
    def _get_mime_type(self, file_path):
        """根据文件扩展名自动获取 MIME 类型"""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or 'application/octet-stream'  # 如果无法识别则返回默认二进制流
    def get_add_memory_result(self):
        """
        获取 add_memory 操作的返回结果
        返回格式: {'action': 'add_memory', 'entries': [...]}
        """
        if not self.data_json_list:
            return None
        
        for entry in reversed(self.data_json_list):
            if isinstance(entry, dict) and entry.get("status") == "complete":
                data = entry.get("data")
                if isinstance(data, dict):
                    if data.get("action") == "add_memory":
                        entries = data.get("entries")
                        if isinstance(entries, str):
                            try:
                                entries = json.loads(entries)
                            except json.JSONDecodeError:
                                pass
                        return {
                            "action": "add_memory",
                            "entries": entries
                        }
                elif isinstance(data, str):
                    try:
                        d = json.loads(data)
                        if d.get("action") == "add_memory":
                            entries = d.get("entries")
                            if isinstance(entries, str):
                                try:
                                    entries = json.loads(entries)
                                except json.JSONDecodeError:
                                    pass
                            return {
                                "action": "add_memory",
                                "entries": entries
                            }
                    except json.JSONDecodeError:
                        pass
        return None
    def add_memory(self, user_text="", image_paths=None):
        """
        添加 memory 数据到量子系统
        支持文本和图片上传
        返回 True 表示成功，False 表示失败
        """
        try:
            # 构建 payload
            payload = {
                "action": "add_memory",
                "userText": user_text,
                "model": "default"
            }

            # 如果有图片路径，添加 blobs
            blobs = []
            if image_paths and isinstance(image_paths, list):
                for img_path in image_paths:
                    if os.path.exists(img_path):
                        mime_type, _ = mimetypes.guess_type(img_path)
                        if not mime_type:
                            mime_type = "image/jpeg"  # 默认类型
                        with open(img_path, "rb") as f:
                            data = f.read()
                        blobs.append({
                            "mime": mime_type,
                            "data": data
                        })
                    else:
                        logger.warning(f"图片文件不存在: {img_path}")
                        return False

            # 发送请求
            job_id = get_quantum_client_manager().send_model_call(
                payload=payload,
                command_type=b"fkb_memory",
                api_instance=self,
                blobs=blobs
            )
            self.start_time_dt = datetime.now()
            self.start_time_str = self.start_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            logger.info(f"add_memory 开始时间: {self.start_time_str}")
            if job_id is None:
                logger.error("发送 add_memory 请求失败")
                return False

            # 查询结果
            result = get_quantum_client_manager().query_result(job_id, timeout=180)

            # 1）处理字符串错误（例如 CTTVError: Stream timeout 等），写入 data_json_list，方便上层 Excel 精确记录
            if isinstance(result, str):
                logger.error(f"add_memory 返回错误字符串: {result}")
                try:
                    self.data_json_list.append({
                        "job_id": job_id,
                        "status": "failed",
                        "timestamp": datetime.now().isoformat(),
                        "data": [result]
                    })
                except Exception as e:
                    logger.error(f"记录 add_memory 字符串错误到 data_json_list 失败: {e}")
                return False

            # 2）处理 query_result 返回的失败字典（status == 'failed'），同样写入 data_json_list
            if isinstance(result, dict) and result.get("status") == "failed":
                failure_data = result.get("data")
                logger.error(f"add_memory 返回失败结果: {failure_data}")
                if not isinstance(failure_data, list):
                    failure_data = [failure_data]
                try:
                    self.data_json_list.append({
                        "job_id": job_id,
                        "status": "failed",
                        "timestamp": datetime.now().isoformat(),
                        "data": failure_data
                    })
                except Exception as e:
                    logger.error(f"记录 add_memory 失败结果到 data_json_list 失败: {e}")
                return False

            if result is None or not isinstance(result, dict):
                logger.error("查询 add_memory 结果失败或结果格式错误")
                return False

            # 检查 action 是否匹配
            if result.get("action") != "add_memory":
                logger.error(f"add_memory 返回 action 不匹配: {result.get('action')}")
                return False

            # 处理 entries 字段：可能是字符串形式的 JSON 数组
            entries = result.get("entries")
            if isinstance(entries, str):
                try:
                    entries = json.loads(entries)  # 转换为列表
                except json.JSONDecodeError:
                    logger.error(f"无法解析 entries 字符串: {entries}")
                    return False

            if not isinstance(entries, list) or len(entries) == 0:
                logger.error("add_memory 返回的 entries 非有效列表")
                return False

            # 成功：记录 entry ID 到实例中（可选）
            self.memory_entries = entries
            logger.info(f"成功添加 memory，entries: {entries}")

            return True

        except Exception as e:
            logger.error(f"add_memory 出错: {e}")
            return False

#20260114更新需求
#############################################################################################################################################
#############################################################################################################################################
    def get_all_memory_result(self):
        """
        获取所有memory数据并直接处理响应，返回entries列表
        """
        try:
            payload = {"action": "get_all_memory", "model": "lucene_AAITC-Emb_hybrid"}
            job_id = get_quantum_client_manager().send_model_call(payload, b"fkb_memory", self)
            
            if not job_id:
                return []
            
            result = get_quantum_client_manager().query_result(job_id, timeout=180)
            if not result:
                return []
            
            # 提取entries
            entries = result.get("entries") or (result.get("data", {}).get("entries") if isinstance(result.get("data"), dict) else None)
            if isinstance(entries, str):
                try:
                    entries = json.loads(entries)
                except:
                    return []
            
            if not isinstance(entries, list):
                return []
            
            # 提取ID
            ids = []
            for entry in entries:
                if isinstance(entry, dict):
                    ids.append(entry.get("id") or entry.get("Id"))
                elif isinstance(entry, (str, int)):
                    ids.append(entry)
            
            return [id for id in ids if id is not None]
        except Exception as e:
            logger.error(f"获取memory结果失败: {e}")
            return []

    def delete_memory(self):
        """
        删除所有memory数据
        """
        try:
            ids_list = self.get_all_memory_result()
            if not ids_list:
                logger.warning("没有需要删除的memory IDs")
                return True
            
            logger.info(f"准备删除 {len(ids_list)} 个memory条目")
            
            payload = {"action": "delete_memory", "model": "lucene_AAITC-Emb", "entries": ids_list}
            job_id = get_quantum_client_manager().send_model_call(payload, b"fkb_memory", self)
            
            if not job_id:
                logger.error("发送 delete_memory 请求失败")
                return False
            
            result = get_quantum_client_manager().query_result(job_id, timeout=180)
            if not result:
                logger.error("查询 delete_memory 结果失败")
                return False
            
            # 判断是否成功
            if isinstance(result, dict):
                action = result.get("action")
                if action != "delete_memory":
                    logger.error(f"返回 action 不匹配: {action}")
                    return False
                success = "action" in result and "entries" in result
            else:
                success = True  
            
            if success:
                logger.info(f"成功删除 {len(ids_list)} 个 memory 条目")
            else:
                logger.error(f"删除 memory 失败: {result}")
            
            return success
        except Exception as e:
            logger.error(f"delete_memory 出错: {e}")
            return False

    def get_fkb(self):
        """
        获取当前所有的注册文档，返回文档ID列表
        """
        try:
            # 构建 payload
            payload = {
                "action": "list",
                "folder_path": ""
            }

            # 发送请求
            job_id = get_quantum_client_manager().send_model_call(
                payload=payload,
                command_type=b"document",
                api_instance=self
            )

            if job_id is None:
                logger.error("发送 get_fkb 请求失败")
                return []

            raw_result = get_quantum_client_manager().query_result(job_id, timeout=180)
            if raw_result is None:
                logger.error("查询 get_fkb 原始结果为空")
                return []

            documents = []
            
            # 检查返回结果的类型并进行相应处理
            if isinstance(raw_result, list):
                # 如果直接返回列表
                documents = raw_result
            elif isinstance(raw_result, dict):
                # 如果返回字典，查找各种可能的文档字段
                if "documents" in raw_result:
                    documents = raw_result["documents"]
                elif "data" in raw_result and isinstance(raw_result["data"], list):
                    # 这是当前日志显示的结构
                    documents = raw_result["data"]
                elif "documentList" in raw_result:
                    documents = raw_result["documentList"]
                elif "data" in raw_result and isinstance(raw_result["data"], dict) and "documents" in raw_result["data"]:
                    documents = raw_result["data"]["documents"]
                else:
                    # 如果以上都没有找到，记录详细信息用于调试
                    logger.warning(f"未找到预期的文档字段，raw_result keys: {list(raw_result.keys()) if isinstance(raw_result, dict) else type(raw_result)}")
                    logger.debug(f"raw_result content: {raw_result}")
                    
                    # 尝试使用 get_fkb_result
                    # 为了使用 get_fkb_result，需要临时将结果添加到实例的数据列表中
                    temp_entry = {
                        'job_id': job_id,
                        'status': 'complete',
                        'timestamp': datetime.now().isoformat(),
                        'data': raw_result
                    }
                    original_data_list = self.data_json_list.copy()
                    self.data_json_list.append(temp_entry)
                    formatted_result = self.get_fkb_result()
                    self.data_json_list = original_data_list  # 恢复原始数据
                    
                    if formatted_result and "documents" in formatted_result:
                        documents = formatted_result["documents"]
            else:
                logger.error(f"未知的返回结果类型: {type(raw_result)}")
                return []

            if not isinstance(documents, list):
                logger.error(f"获取到的文档数据格式错误: {type(documents)}, 原始结果: {raw_result}")
                return []

            doc_ids = []
            for doc in documents:
                if isinstance(doc, dict):
                    doc_id = doc.get("id")
                    if doc_id:
                        doc_ids.append(doc_id)

            logger.info(f"获取到 {len(doc_ids)} 个注册文档")
            return doc_ids

        except Exception as e:
            logger.error(f"get_fkb 出错: {e}")
            import traceback
            traceback.print_exc()
            return []


    def delete_fkb(self, doc_ids=None):
        """
        删除指定文档，如未指定则删除所有文档
        """
        try:
            if doc_ids is None:
                doc_ids = self.get_fkb()
            
            if not doc_ids:
                logger.warning("没有需要删除的文档ID")
                return True
            
            logger.info(f"准备删除 {len(doc_ids)} 个文档")
            
            payload = {"action": "delete", "body": {"doc_ids": doc_ids}}
            job_id = get_quantum_client_manager().send_model_call(payload, b"document", self)
            
            if not job_id:
                logger.error("发送 delete_fkb 请求失败")
                return False
            
            result = get_quantum_client_manager().query_result(job_id, timeout=180)
            
            # 判断成功 - 修改逻辑以适应返回 [False, False] 的情况
            # 根据日志显示，即使返回 [False, False] 实际上文档也已删除
            # 这可能是一个API返回值的问题，所以我们要根据实际情况调整判断逻辑
            success = False
            if isinstance(result, list):
                # 如果返回的是布尔值列表，检查是否所有操作都有响应（不一定都是True）
                # 根据您的日志，似乎即使返回False也表示操作已完成
                success = len(result) > 0 
            elif isinstance(result, dict):
                success = result.get("success", False)
            elif isinstance(result, bool):
                success = result
            else:

                success = result is not None
            
            if success:
                logger.info(f"成功删除 {len(doc_ids)} 个文档")
            else:
                logger.error(f"删除文档失败: {result}")
            
            return success
        except Exception as e:
            logger.error(f"delete_fkb 出错: {e}")
            return False
    def cleanup_all_data(self):
        """
        清理所有数据：删除所有memory和所有注册文档
        """
        logger.info("开始清理所有数据...")
        
        memory_deleted = self.delete_memory()
        fkb_deleted = self.delete_fkb()
        
        success = memory_deleted and fkb_deleted
        if success:
            logger.info("所有Memory和FKB数据清理完成")
        else:
            logger.error(f"数据清理部分失败 - Memory删除: {memory_deleted}, FKB删除: {fkb_deleted}")
        
        return success 
#############################################################################################################################################
#############################################################################################################################################
#############################################################################################################################################
#############################################################################################################################################


    def send_query_with_image(self, query_text="", handler=None, image_paths=None):
        self.tool_responses = []
        """发送带图片的查询请求"""
        if not self.session_id:
            logger.info("请先获取会话信息")
            return False

        handler = handler or self.DEFAULT_HANDLER

        if image_paths is None:
            image_paths = []
        elif isinstance(image_paths, str):
            image_paths = [image_paths]

        try:
            # 构建查询文本部分
            query_data = {
                "query": query_text,
                "handler": handler,
            }

            # 处理图像路径并生成 binary blobs
            blobs = []
            for path in image_paths:
                if not os.path.exists(path):
                    logger.error(f"文件不存在: {path}")
                    continue
                mime_type = self._get_mime_type(path)
                with open(path, "rb") as f:
                    byte_array = list(f.read())  # 转为整数列表
                blobs.append({
                    "mime": mime_type,
                    "data": byte_array
                })
                logger.info(f"Added image to blobs: {path}, mime={mime_type}, size={len(byte_array)} bytes")

            # 如果有图像，则添加到 uri 字段（保持兼容性）
            if blobs:
                query_data["uri"] = image_paths
                logger.info(f"Total images processed: {len(blobs)}")

            # 构建完整的payload data部分
            payload = query_data
            # logger.info(f"发送查询请求: {json.dumps(payload)}")
            logger.info(f"发送查询请求: {json.dumps(payload, ensure_ascii=False)}")
            
            # 重置所有与查询相关的属性，确保每次查询都是独立的
            self.first_word_time = None
            self.ttft_seconds = 0
            self.token_count = 0
            self.generation_speed = 0
            self.first_text_response_time = None
            self.text_response_count = 0
            self.current_mode = None
            self.data_json_list = []  # 清空之前的数据
            self.response_time = 0
            self.end_time_dt = None
            self.end_time_str = None
            
            # 使用统一的发送方法
            # 发送请求，传入 blobs
            job_id = get_quantum_client_manager().send_model_call(
                payload=query_data,
                command_type=b"query",
                api_instance=self,
                blobs=blobs  # 传入二进制数据
            )
            # 记录开始时间并重置所有查询相关的属性
            self.start_time_dt = datetime.now()
            self.start_time_str = self.start_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            logger.info(f"开始时间: {self.start_time_str}")

            if job_id is not None:
                self.query_upload_id = str(job_id)
                logger.info(f"任务ID: {job_id}")
                return True
            else:
                logger.info("发送查询请求失败")
                return False
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return False
    def get_response_content(self):
        """获取响应内容并返回文本"""
        if not self.query_upload_id:
            logger.info("请先发送查询请求")
            return None

        try:
            start_time = time.time()
            result = get_quantum_client_manager().query_result(int(self.query_upload_id), timeout=180)
            end_time = time.time()

            if result:
                # 检查是否是失败状态
                if isinstance(result, dict) and result.get("status") == "failed":
                    # 提取失败原因
                    error_reason = result.get("error_reason", result.get("data"))
                    if isinstance(error_reason, list):
                        # 如果失败原因是列表，转换为字符串
                        error_msg = f"CTTVError: Task failed - {', '.join(map(str, error_reason))}"
                    else:
                        error_msg = f"CTTVError: Task failed - {error_reason}"
                    
                    logger.error(error_msg)
                    return error_msg
                
                # 根据返回结果提取文本内容，只取response字段
                if isinstance(result, dict):
                    # 如果结果中有response字段，直接返回该字段内容
                    if "response" in result:
                        return result["response"]
                    # 如果有data字段且是字典，从中提取text或response
                    elif "data" in result and isinstance(result["data"], dict):
                        data = result["data"]
                        if "response" in data:
                            return data["response"]
                        elif "text" in data:
                            return data["text"]
                    # 如果有text字段，返回该字段
                    elif "text" in result:
                        return result["text"]
                # 如果结果是字符串，直接返回
                return str(result)
            else:
                return None
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return None
    def get_response_time(self):
        """获取响应时间"""
        return self.response_time

    def run_query_only(self, query_text="", handler=None, image_paths=None, reuse_session=False):
        """只运行查询流程，不包含文档注册"""
        # 重置响应时间
        self.response_time = 0
        
        # 如果不是复用会话，则创建新会话
        if not reuse_session:
            if not self.create_session(): 
                return None

        else:
            # 复用会话时，检查是否有 session_id
            if not self.session_id:
                logger.info("尝试复用会话但 session_id 为空")
                return None
            logger.info(f"复用现有会话: {self.session_id}")

        # 发送查询请求
        if not self.send_query_with_image(query_text, handler, image_paths):
            return None
        result = self.get_response_content()
        if result is None:
            logger.info("未能获取响应内容")
            return None

        # logger.info(f"最终结果: {result}")
        logger.info(f"最终结果: {result}")
        # # 如果结果包含CTTVError，则等待3分钟
        # if result and isinstance(result, dict) and 'error_reason' in result:
        #     if "CTTVError" in str(result['error_reason']):
        #         logger.info("检测到CTTVError，等待3分钟后执行下一条case")
        #         time.sleep(180)  # 任务失败后等待3分钟
        # elif result and isinstance(result, str):
        #     if "CTTVError" in result:
        #         logger.info("检测到CTTVError，等待3分钟后执行下一条case")
        #         time.sleep(180)  # 任务失败后等待3分钟
        return result
    # 分批次处理文档
    # 每次最多处理4个文档
    # 按顺序分批处理，确保不重复
    # 例如：30个文件 → 8批（7批4个 + 1批2个）

    # 每次注册完一个批次后等待5秒
    # 等待时间不计入总耗时统计
    # 不重复处理相同文件
    
    # def process_document_registration_only(self):
    #     """
    #     仅处理文档注册流程，批量处理文档（每次最多4个）
    #     """
    #     logger.info("开始文档注册流程...")
    #     if not self.create_session():
    #         logger.info("创建会话失败")
    #         return False

    #     # 获取文档列表
    #     doc_file_list = []
    #     if os.path.exists(doc_directory):
    #         for root, dirs, files in os.walk(doc_directory):
    #             for file in files:
    #                 file_path = os.path.join(root, file)
    #                 doc_file_list.append(file_path)
    #         logger.info(f"找到 {len(doc_file_list)} 个文档文件")
    #     else:
    #         logger.info(f"目录 {doc_directory} 不存在")
    #         return False

    #     if not doc_file_list:
    #         logger.info("没有找到文档文件")
    #         return False

    #     # 检查是否需要注册文档（检查是否已注册且文件仍然存在）
    #     is_registered = self.is_document_registered(doc_file_list)
        
    #     if not is_registered:
    #         # 记录文档注册开始时间
    #         start_time = time.time()  # 只记录实际开始时间
            
    #         # 记录总的文档数量，用于后续完成率计算
    #         self._original_total_docs_count = len(doc_file_list)
            
    #         logger.info(f"开始文档注册，时间: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
    #         # 按每批4个文档进行注册
    #         batch_size = 4
    #         total_files = len(doc_file_list)
    #         total_batches = (total_files + batch_size - 1) // batch_size  # 向上取整
            
    #         logger.info(f"总共 {total_files} 个文档，将分 {total_batches} 批进行注册")
            
    #         for batch_index in range(total_batches):
    #             start_idx = batch_index * batch_size
    #             end_idx = min((batch_index + 1) * batch_size, total_files)
    #             batch_files = doc_file_list[start_idx:end_idx]
                
    #             logger.info(f"正在注册第 {batch_index + 1}/{total_batches} 批文档: {batch_files}")
                
    #             # 注册当前批次的文档
    #             register_result = self.register_document(batch_files)
    #             if not register_result.get("success", False):
    #                 logger.info(f"第 {batch_index + 1} 批文档注册失败")
    #                 return False
                
    #             # 如果不是最后一批，等待5秒再继续下一批（等待时间不计入总耗时）
    #             if batch_index < total_batches - 1:
    #                 logger.info(f"等待 5 秒后继续下一批注册...")
    #                 time.sleep(5)
            
    #         logger.info("所有文档批次注册完成")
            
    #         # 最后检查所有文档的处理状态
    #         max_retries = 10000000
    #         retry_interval = 2
    #         attempt = 0
            
    #         while attempt < max_retries:
    #             attempt += 1
    #             logger.info(f"第{attempt}次检查文档处理状态...")
                
    #             doc_status = self.get_register_document()
    #             if doc_status.get("success", False):
    #                 # 计算总耗时（不包括等待时间）
    #                 total_time = time.time() - start_time
    #                 logger.info(f"文档处理完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                    
    #                 logger.info("文档处理完成")
    #                 # 标记文档为已注册
    #                 self.mark_documents_registered(doc_file_list)
    #                 break
    #             elif "status" in doc_status and doc_status["status"] in ["running", "processing", "pending"]:
    #                 logger.info(f"文档仍在处理中，等待{retry_interval}秒后重试...")
    #                 time.sleep(retry_interval)
    #                 continue
    #             else:
    #                 logger.info("文档处理检查失败")
    #                 return False
    #         else:
    #             logger.info(f"超过最大重试次数({max_retries})，文档可能仍在处理中")
    #             # 计算总耗时（不包括最后一次等待）
    #             total_time = time.time() - start_time
    #             logger.info(f"文档处理超时，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
    #             return False
    #     else:
    #         logger.info("文档已注册，跳过注册流程")
        
    #     logger.info("文档注册流程完成")
    #     return True
    def process_document_registration_only(self):
        """
        仅处理文档注册流程，直接注册所有文档
        """
        logger.info("开始文档注册流程...")
        doc_directory = get_config().get('doc_directory')
        if not self.create_session():
            logger.info("创建会话失败")
            return False

        # 获取文档列表
        doc_file_list = []
        if doc_directory and os.path.exists(doc_directory):
            for root, dirs, files in os.walk(doc_directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    doc_file_list.append(file_path)
            logger.info(f"找到 {len(doc_file_list)} 个文档文件")
        else:
            logger.info(f"目录 {doc_directory} 不存在")
            return False

        if not doc_file_list:
            logger.info("没有找到文档文件")
            return False

        # 检查是否需要注册文档（检查是否已注册且文件仍然存在）
        is_registered = self.is_document_registered(doc_file_list)
        
        if not is_registered:
            # 记录文档注册开始时间
            start_time = time.time()  # 只记录实际开始时间
            
            # 记录总的文档数量，用于后续完成率计算
            self._original_total_docs_count = len(doc_file_list)
            
            logger.info(f"开始文档注册，时间: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
            logger.info(f"正在注册所有 {len(doc_file_list)} 个文档")
            
            # 直接注册所有文档
            register_result = self.register_document(doc_file_list)
            if not register_result.get("success", False):
                logger.info("文档注册失败")
                return False
            
            logger.info("文档注册请求已发送")
            
            # 检查所有文档的处理状态
            max_retries = 10000000
            retry_interval = 2
            attempt = 0
            
            while attempt < max_retries:
                attempt += 1
                logger.info(f"第{attempt}次检查文档处理状态...")
                
                doc_status = self.get_register_document()
                if doc_status.get("success", False):
                    # 计算总耗时
                    total_time = time.time() - start_time
                    logger.info(f"文档处理完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                    
                    logger.info("文档处理完成")
                    # 标记文档为已注册
                    self.mark_documents_registered(doc_file_list)
                    break
                elif "status" in doc_status and doc_status["status"] in ["running", "processing", "pending"]:
                    logger.info(f"文档仍在处理中，等待{retry_interval}秒后重试...")
                    time.sleep(retry_interval)
                    continue
                else:
                    logger.info("文档处理检查失败")
                    return False
            else:
                logger.info(f"超过最大重试次数({max_retries})，文档可能仍在处理中")
                # 计算总耗时
                total_time = time.time() - start_time
                logger.info(f"文档处理超时，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                return False
        else:
            logger.info("文档已注册，跳过注册流程")
        
        logger.info("文档注册流程完成")
        time.sleep(60)
        # 文档注册流程完成后，进行 Quantum Core 日志注册分析
        try:
            quantum_core_path = get_quantum_core_path()
            logger.info(f"文档注册分析 - doc_details_path: {get_doc_details_path()}, quantum_core_path: {quantum_core_path}")
            if get_doc_details_path() and quantum_core_path:
                logger.info("进行Quantum Core 日志注册分析")
                get_regist_duration_single_file(get_doc_details_path(), quantum_core_path)
            else:
                logger.warning("doc_details_path 未定义，跳过文档注册分析")
        except Exception as e:
            logger.error(f"文档注册分析过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
        
        return True
    # 处理主Excel文件，优化对result中存在CTTVError: Request Timeout的case需要筛选出来重新跑一次/
    def process_main_excel_only(self, cycle=1, min_wait_time=1.0, max_wait_time=10.0, enable_random_wait=True):
        """
        仅处理主Excel文件，支持循环执行，但只保存最后一轮结果
        支持根据 new_session 列决定是否复用 session
        """
        logger.info(f"开始处理主Excel文件，循环轮数: {cycle}")
        
        for cycle_index in range(cycle):
            logger.info(f"开始执行第 {cycle_index + 1}/{cycle} 轮循环")
            
            try:
                df = pd.read_excel(get_config().get('EXCEL_FILE_PATH') or get_config().get('EXCEL_FILE_PATH',''), sheet_name=0)
                logger.info(f"成功加载 Excel，共 {len(df)} 行数据")
            except Exception as e:
                logger.info(f"读取 Excel 失败: {e}")
                return False

            # 永远使用 _cycleN 格式，不再生成主文件
            cycle_output_path = (get_config().get('OUTPUT_EXCEL_PATH') or '').replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
            
            # 尝试加载已有结果（如果存在）
            try:
                df_output = pd.read_excel(cycle_output_path)
                logger.info(f"加载现有输出文件，已有 {len(df_output)} 行数据")
            except FileNotFoundError:
                df_output = df.copy()
                df_output['result'] = None
                df_output['response_time'] = 0
                df_output['data_json_list'] = None 
                df_output['start_time'] = None 
                df_output['end_time'] = None  
                df_output['toolname'] = None  # 新增toolname列
                # 添加性能指标列
                df_output['first_word_time'] = None
                df_output['first_text_response_time'] = None  
                df_output['ttft'] = 0
                df_output['token_count'] = 0
                df_output['generation_speed'] = 0
                
                try:
                    df_output.to_excel(cycle_output_path, index=False, sheet_name='result')
                    logger.info(f"创建新的输出文件: {cycle_output_path}")
                except Exception as e:
                    logger.info(f"创建输出文件失败: {e}")
                    return False
            except Exception as e:
                logger.info(f"读取输出文件失败: {e}")
                return False

            start_index = 0
            if 'result' in df_output.columns:
                for i, result in enumerate(df_output['result']):
                    if pd.isna(result) or result is None:
                        start_index = i
                        break
                else:
                    start_index = len(df_output)

            logger.info(f"从第 {start_index + 1} 行开始处理")
            self._process_rows(df, df_output, cycle_output_path, start_index, min_wait_time, max_wait_time, enable_random_wait)
            # 筛选并重新处理超时错误和其他失败的case，在检查任务失败时，排除包含 failed_input_safety 的错误信息
            timeout_indices = []
            task_failed_indices = []

            for idx, result in enumerate(df_output['result']):
                if isinstance(result, str):
                    if "CTTVError: Request Timeout" in result:
                        timeout_indices.append(idx)
                    elif "CTTVError: Stream timeout" in result:
                        timeout_indices.append(idx) 
                    elif "CTTVError: Task failed -" in result:
                        # 排除输入安全检查失败的情况
                        if "failed_input_safety" not in result:
                            task_failed_indices.append(idx)

            # 合并所有需要重跑的索引
            all_retry_indices = timeout_indices + task_failed_indices

            if all_retry_indices:
                logger.info(f"发现 {len(timeout_indices)} 个超时错误的case: {timeout_indices}")
                logger.info(f"发现 {len(task_failed_indices)} 个可重跑的任务失败case: {task_failed_indices}")
                
                # 检查是否有被排除的安全检查失败
                safety_failed_indices = []
                for idx, result in enumerate(df_output['result']):
                    if isinstance(result, str) and "CTTVError: Task failed - failed_input_safety" in result:
                        safety_failed_indices.append(idx)
                
                if safety_failed_indices:
                    logger.info(f"发现 {len(safety_failed_indices)} 个输入安全检查失败的case，这些case不会重跑: {safety_failed_indices}")
                
                logger.info(f"总共 {len(all_retry_indices)} 个需要重跑的case")
                
                # 重新处理所有需要重跑的失败case
                self._process_rows(df, df_output, cycle_output_path, -1, min_wait_time, max_wait_time, enable_random_wait, all_retry_indices)
                logger.info(f"失败的case重新处理完成")
            else:
                logger.info("没有发现需要重跑的错误case")

                
            # # 筛选并重新处理超时错误的case
            # timeout_indices = []
            # for idx, result in enumerate(df_output['result']):
            #     if isinstance(result, str) and "CTTVError: Request Timeout" in result:
            #         timeout_indices.append(idx)
            
            # if timeout_indices:
            #     logger.info(f"发现 {len(timeout_indices)} 个超时错误的case，开始重新处理: {timeout_indices}")
            #     self._process_rows(df, df_output, cycle_output_path, -1, min_wait_time, max_wait_time, enable_random_wait, timeout_indices)
            #     logger.info(f"超时错误的case重新处理完成")
            # else:
            #     logger.info("没有发现超时错误的case")
        
        logger.info(f"\n所有 {cycle} 轮循环已完成")
        return True

    def _process_rows(self, df, df_output, cycle_output_path, start_index, min_wait_time, max_wait_time, enable_random_wait, timeout_indices=None):
        """处理行数据的辅助方法"""
        # 保存上一个会话的信息
        previous_api = None

        # 如果是重试超时case
        if timeout_indices is not None:
            indices_to_process = timeout_indices
        else:
            # 正常处理：从start_index开始
            indices_to_process = range(start_index, len(df))

        for index in indices_to_process:
            if index >= len(df_output):
                break  

            question = str(df.iloc[index]['question']).strip()
            image_names = str(df.iloc[index]['pathlist']).strip()
            
            # 获取 new_session 字段，默认为 'Y'
            new_session = str(df.iloc[index].get('new_session', 'Y')).strip().upper()
            if new_session not in ['Y', 'N']:
                new_session = 'Y'  # 如果值无效，默认新建会话

            if not question or question.lower() in ['nan', 'none', 'null', ''] or question == '1':
                logger.info(f"第 {index + 1} 行跳过：question 为空或者为1")
                df_output.at[index, 'result'] = "Error: Empty question"
                df_output.at[index, 'response_time'] = 0
                df_output.at[index, 'data_json_list'] = None
                df_output.at[index, 'start_time'] = None  
                df_output.at[index, 'end_time'] = None  
                df_output.at[index, 'toolname'] = None  # 新增toolname列

                # 性能指标设为默认值
                df_output.at['first_text_response_time'] = None  
                df_output.at[index, 'first_word_time'] = None
                df_output.at[index, 'ttft'] = 0
                df_output.at[index, 'token_count'] = 0
                df_output.at[index, 'generation_speed'] = 0
                continue

            image_paths = []
            missing_images = []
            if image_names and image_names.lower() not in ['nan', 'none', 'null', '']:
                image_name_list = [name.strip() for name in re.split(r'[,;]+', image_names) if name.strip()]
                
                for image_name in image_name_list:
                    if image_name.lower() in ['nan', 'none', 'null', '']:
                        continue
                    found_image = None
                    image_dir = get_config().get('IMAGE_DIR')
                    if image_dir is not None:
                        for file_path in image_dir.rglob(image_name):
                            if file_path.is_file():
                                found_image = str(file_path)
                                break
                    
                    if found_image:
                        image_paths.append(found_image)
                    else:
                        missing_images.append(image_name)
                
                if missing_images:
                    logger.info(f"第 {index + 1} 行缺少文件: {missing_images}")
                    if not image_paths:
                        df_output.at[index, 'result'] = "Error: No valid images found"
                        df_output.at[index, 'response_time'] = 0
                        df_output.at[index, 'data_json_list'] = None
                        df_output.at[index, 'start_time'] = None  
                        df_output.at[index, 'end_time'] = None  
                        df_output.at[index, 'toolname'] = None  # 新增toolname列
                        # 性能指标设为默认值
                        df_output.at['first_text_response_time'] = None  
                        df_output.at[index, 'first_word_time'] = None
                        df_output.at[index, 'ttft'] = 0
                        df_output.at[index, 'token_count'] = 0
                        df_output.at[index, 'generation_speed'] = 0
                        continue
            else:
                logger.info("该case不需要附件输入")

            logger.info(f"\n=== 正在处理第 {index + 1} 行 ===")
            logger.info(f"Question: {question}")
            logger.info(f"Pathlist: {image_paths}")
            logger.info(f"New Session: {new_session}")

            try:
                # 决定是否复用会话
                reuse_session = (new_session == 'N' and previous_api is not None and previous_api.session_id is not None)
                
                if reuse_session:
                    # 复用上一个API实例
                    api = previous_api
                    logger.info(f"复用上一个会话: {api.session_id}")
                else:
                    # 创建新的API实例
                    api = MultimodalAPI()
                
                result = api.run_query_only(
                    query_text=question,
                    handler="nova",
                    image_paths=image_paths if image_paths else None,
                    reuse_session=reuse_session
                )

                # 保存当前API实例供下一行可能复用
                if new_session == 'Y' or new_session == '':
                    previous_api = api

                response_time = api.get_response_time()
                start_time_str = getattr(api, 'start_time_str', None)
                end_time_str = getattr(api, 'end_time_str', None)
                data_json_content = None
                
                # 获取性能指标
                first_word_time_str = getattr(api, 'first_word_time', None)
                if first_word_time_str:
                    first_word_time_str = first_word_time_str.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                ttft = getattr(api, 'ttft_seconds', 0)
                token_count = getattr(api, 'token_count', 0)
                generation_speed = getattr(api, 'generation_speed', 0)
                
                first_text_response_time_str = getattr(api, 'first_text_response_time', None)
                if first_text_response_time_str:
                    first_text_response_time_str = first_text_response_time_str.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                
                # 添加获取 data_json_list 的代码
                if hasattr(api, 'data_json_list') and api.data_json_list:
                    data_json_content = json.dumps(api.data_json_list, ensure_ascii=False, indent=2)

                # 提取toolname
                toolname_value = api.extract_toolname_from_data_json_list()
                logger.info(f"toolname_value: {toolname_value}")
                toolname_value = json.dumps(toolname_value, ensure_ascii=False) if toolname_value else "[]"

                # 结果处理逻辑（成功：非空且非 Error/CTTVError）
                if result is not None and isinstance(result, str) and len(result.strip()) > 0 and not result.startswith("Error:") and not result.startswith("CTTVError:"):
                    df_output.at[index, 'result'] = result
                    df_output.at[index, 'response_time'] = response_time
                    df_output.at[index, 'data_json_list'] = data_json_content 
                    df_output.at[index, 'start_time'] = start_time_str 
                    df_output.at[index, 'end_time'] = end_time_str   
                    df_output.at[index, 'toolname'] = toolname_value  # 新增toolname列
                    # 保存性能指标
                    df_output.at[index, 'first_word_time'] = first_word_time_str
                    df_output.at[index, 'first_text_response_time'] = first_text_response_time_str
                    df_output.at[index, 'ttft'] = ttft
                    df_output.at[index, 'token_count'] = token_count
                    df_output.at[index, 'generation_speed'] = generation_speed
                    
                    logger.info(f"第 {index + 1} 行处理成功，结果长度: {len(result)}，响应时间: {response_time:.2f}秒")
                else:
                    # 检查是否为超时错误
                    if result == "Error: Request Timeout":
                        df_output.at[index, 'result'] = "CTTVError: Request Timeout"
                    elif result is None or result == "" or (isinstance(result, str) and len(result.strip()) == 0):
                        df_output.at[index, 'result'] = "CTTVError: Empty response from server"
                    else:
                        df_output.at[index, 'result'] = result if result else "CTTVError: Empty response from server"
                    
                    df_output.at[index, 'response_time'] = response_time
                    df_output.at[index, 'data_json_list'] = data_json_content
                    df_output.at[index, 'start_time'] = start_time_str
                    df_output.at[index, 'end_time'] = end_time_str    
                    df_output.at[index, 'toolname'] = toolname_value  # 新增toolname列
                    # 错误情况下的性能指标
                    df_output.at[index, 'first_word_time'] = first_word_time_str
                    df_output.at[index, 'first_text_response_time'] = first_text_response_time_str
                    df_output.at[index, 'ttft'] = ttft
                    df_output.at[index, 'token_count'] = token_count
                    df_output.at[index, 'generation_speed'] = generation_speed
                    
                    logger.info(f"第 {index + 1} 行处理完成但响应为空或出错: {result}")

            except Exception as e:
                logger.info(f"第 {index + 1} 行处理失败: {e}")
                df_output.at[index, 'result'] = f"Error: {str(e)}"
                df_output.at[index, 'response_time'] = response_time
                df_output.at[index, 'data_json_list'] = None
                df_output.at[index, 'start_time'] = getattr(api, 'start_time_str', None) 
                df_output.at[index, 'end_time'] = getattr(api, 'end_time_str', None) 
                df_output.at[index, 'toolname'] = None  # 新增toolname列
                # 异常情况下的性能指标
                df_output.at[index, 'first_word_time'] = None
                df_output.at[index, 'first_text_response_time'] = None
                df_output.at[index, 'ttft'] = 0
                df_output.at[index, 'token_count'] = 0
                df_output.at[index, 'generation_speed'] = 0
                logger.info(f"第 {index + 1} 行错误已记录，继续处理下一条数据")

            try:
                df_output.to_excel(cycle_output_path, index=False, sheet_name='result')
                logger.info(f"第 {index + 1} 行结果已保存")
            except Exception as e:
                logger.info(f"保存第 {index + 1} 行结果失败: {e}")
            
            # 每个case执行完成后随机等待指定时间范围
            if enable_random_wait:
                wait_time = random.uniform(min_wait_time, max_wait_time)
                logger.info(f"第 {index + 1} 个case执行完成，随机等待 {wait_time:.2f} 秒...")
                time.sleep(wait_time)
            else:
                logger.info(f"第 {index + 1} 个case执行完成，随机等待已禁用")
    
    def process_memory_data_only(self, min_wait_time=1.0, max_wait_time=10.0, enable_random_wait=True):
        """
        仅处理Memory数据
        """
        logger.info("开始处理Memory数据...")
        memory_success = self.process_memory_data(min_wait_time, max_wait_time, enable_random_wait)
        if memory_success:
            logger.info("Memory数据处理完成")
            return True
        else:
            logger.info("Memory数据处理失败")
            return False
    def run_main_process(self, cycle=1, min_wait_time=1.0, max_wait_time=10.0, enable_random_wait=True):
        """
        运行完整的主流程逻辑，支持循环执行
        """
        # 首先处理Memory数据（仅当未处理过时）
        if not MultimodalAPI._memory_processed:
            logger.info("开始处理Memory数据...")
            memory_success = self.process_memory_data(min_wait_time, max_wait_time, enable_random_wait)
            MultimodalAPI._memory_processed = True  # 标记为已处理
            if memory_success:
                logger.info("Memory数据处理完成")
            else:
                logger.info("Memory数据处理失败，但继续执行主流程")
        else:
            logger.info("Memory数据已处理过，跳过处理")

        # 完成文档注册流程（仅当未注册过时）
        if not MultimodalAPI._document_registered:
            if not self.process_document_registration_only():
                logger.info("文档注册流程失败")
                return False
            # 标记文档注册已完成
            MultimodalAPI._document_registered = True
        else:
            logger.info("文档已注册过，跳过注册流程")

        # 处理主Excel文件，支持循环
        return self.process_main_excel_only(cycle, min_wait_time, max_wait_time, enable_random_wait)
