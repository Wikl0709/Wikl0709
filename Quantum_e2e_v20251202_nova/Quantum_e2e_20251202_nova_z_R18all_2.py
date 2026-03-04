# -*- coding: utf-8 -*-
# 创作时间 20251127
# 作者：weiyb2

import pandas as pd
import requests
import json
from datetime import datetime
import time
from pathlib import Path
import os
import argparse
import openpyxl
import logging
import re
import utils.monitor_util as memory
from utils.start_stop_services import start_services,stop_services
import atexit
import sys
import random
import shutil
from datetime import datetime, timedelta
import Auto_Judge


_MEMORY_PROCESSED_GLOBAL = False
start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
script_dir = os.path.dirname(os.path.abspath(__file__))
logs_dir = os.path.join(script_dir, "logs")
os.makedirs(logs_dir, exist_ok=True)
log_file_path = os.path.join(logs_dir, f'Quantum_api_{start_timestamp}.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - [%(filename)s:%(lineno)d] - [%(funcName)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

logger = logging.getLogger(__name__)
logger.info("日志系统初始化完成")

# 注册程序退出时的清理函数
def cleanup_logging():
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
atexit.register(cleanup_logging)

class MultimodalAPI:
    """
    MultimodalAPI类，用于处理多模态数据上传、查询和下载
    """
    _memory_processed = False
    _document_registered = False 
    # 类级别的默认参数定义
    DEFAULT_HANDLER = "nova"
    # DEFAULT_MODEL_NAME = "gpt"
    # DEFAULT_MODEL_VERSION = "gpt-4.1"
    def __init__(self):
        self.upload_id = None
        self.session_id = None
        self.job_id = None
        self.query_upload_id = None
        self.response_time = 0
        self.text_response_count = 0
        self.first_text_response_time = None
        self.registered_docs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registered_docs.json")
        self.registered_docs = self.load_registered_docs()

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
        """检查文档是否已注册"""
        if not doc_paths:
            return False
        if not self.registered_docs:
            return False
        return all(os.path.abspath(path) in self.registered_docs for path in doc_paths)

    def mark_documents_registered(self, doc_paths):
        """标记文档为已注册"""
        count = 0
        for path in doc_paths:
            abspath = os.path.abspath(path)
            if abspath not in self.registered_docs:
                self.registered_docs.add(abspath)
                count += 1
        if count > 0:
            self.save_registered_docs()
        logger.info(f"标记 {count} 个新文档为已注册，总共已注册 {len(self.registered_docs)} 个文档")

    def create_session(self):
        """创建会话"""
        url = f"{BASE_URL}/upload"
        payload = {
            "command": "session",
            "data": {
                "text": "{\"action\": \"create\"}"
            }
        }
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                self.upload_id = response.text.strip()
                logger.info(f"成功创建会话，upload_id: {self.upload_id}")
                return True
            else:
                logger.info(f"创建会话失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return False

    def get_session_info(self):
        """获取会话信息，提取 sessionID 和 jobId"""
        if not self.upload_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        url = f"{BASE_URL}/query"
        params = {"fileData": self.upload_id}
        try:
            start_time = time.time()
            response = requests.get(url, params=params, stream=True)
            end_time = time.time()
            response_time = end_time - start_time
            
            job_id = None
            session_id = None
            
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        data_str = decoded_line[6:]
                        try:
                            data_json = json.loads(data_str)
                            if data_json.get("type") == "job-id":
                                job_id = data_json.get("contents")
                                self.job_id = job_id
                                logger.info(f"jobId: {job_id}")
                            elif data_json.get("type") == "output-data":
                                output_data = json.loads(data_json.get("contents"))
                                text_data = json.loads(output_data["data"]["text"])
                                session_id = text_data.get("sessionID")
                                self.session_id = session_id
                                logger.info(f"sessionID: {session_id}")
                        except Exception as e:
                            logger.info(f"解析失败: {e}")
            
            if session_id:
                return {
                    "success": True,
                    "session_id": session_id,
                    "job_id": job_id,
                    "response_time": response_time,
                    "status_code": response.status_code 
                }
            else:
                logger.info("未获取到 sessionID")
                return {
                    "success": False,
                    "session_id": None,
                    "job_id": job_id,
                    "response_time": response_time,
                    "status_code": response.status_code, 
                    "error": "未获取到 sessionID"
                }
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return {
                "success": False,
                "status_code": "N/A",  # 异常情况下状态码为N/A
                "error": str(e)
            }

    def register_document(self, file_paths):
        """注册文档接口"""
        if not self.upload_id:
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

        url = f"{BASE_URL}/upload"
        payload = {
            "command": "document",
            "data": {
                "text": json.dumps({
                    "action": "add",
                    "body": {
                        "doc_paths": file_paths,
                        "isTempFile": False
                    }
                })
            }
        }
        logger.info(f"注册文档: {file_paths}")
        try:
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                upload_id = response.text.strip()
                logger.info(f"成功注册文档，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                
                # 注册文档后立即获取响应内容
                response_content_result = self.get_response_content_detailed()
                # 获取原始响应内容（不经过解析）
                raw_response_content = response_content_result.get("raw_response", "")
                
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "response_text": response.text,
                    "response_content": response_content_result,
                    "raw_response_content": raw_response_content  # 添加原始响应内容
                }
            else:
                logger.info(f"注册文档失败: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "upload_id": None,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "response_text": response.text
                }
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return {
                "success": False,
                "upload_id": None,
                "response_time": 0,
                "error": str(e)
                }
    def get_register_document(self):
        """获取注册文档列表，检查一次文档解析状态"""
        if not self.upload_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        url = f"{BASE_URL}/upload"
        # 构建请求体，包含文件路径和操作类型
        payload = {
            "command": "document",
            "data": {
                "text": json.dumps({
                    "action": "list",
                    "body": {
                        "folder_path": ''
                    }
                })
            }
        }
        logger.info("检查文档注册状态...")
        try:
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            response_time = end_time - start_time
            
            # 如果有文档注册的起始时间，计算已用时间
            if hasattr(self, '_document_registration_start_time'):
                elapsed_time = time.time() - self._document_registration_start_time
                logger.info(f"文档注册已用时间: {elapsed_time:.2f}秒 ({self._format_time(elapsed_time)})")
            
            if response.status_code == 200:
                upload_id = response.text.strip()
                logger.info(f"成功获取文档列表，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                
                # 获取响应内容
                response_content_result = self.get_response_content_detailed()
                raw_response_content = response_content_result.get("raw_response", "")
                result_text = response_content_result.get("result_text", "")
                logger.info(f"获取到的result_text: {result_text}")  
                
                if result_text:
                    try:
                        # 解析外层JSON
                        outer_data = json.loads(result_text)
                        # 检查是否有job状态信息
                        job_status = outer_data.get("status", "").lower()
                        if job_status in ["running", "processing", "pending"]:
                            logger.info(f"任务仍在处理中(status: {job_status})")
                            return {
                                "success": False,
                                "upload_id": upload_id,
                                "response_time": response_time,
                                "status_code": response.status_code,
                                "response_text": response.text,
                                "response_content": response_content_result,
                                "raw_response_content": raw_response_content,
                                "status": job_status
                            }
                        
                        # 获取实际的文档列表数据
                        if "data" in outer_data and "text" in outer_data["data"]:
                            inner_text = outer_data["data"]["text"]
                            # 解析内部的文档列表JSON
                            doc_list = json.loads(inner_text)
                            
                            # # 确保doc_list是列表类型
                            # if isinstance(doc_list, list):
                            #     if len(doc_list) > 0:
                            #         logger.info(f"文档数量: {len(doc_list)}")
                            #         # 检查所有文档的状态
                            #         has_processing_docs = False
                            #         doc_ids = []  # 存储所有文档ID的列表
                            #         completed_count = 0 #统计COMPLETED状态的文档数量
                            #         for i, doc in enumerate(doc_list):
                            #             #logger.info(f"第{i+1}个文档类型: {type(doc)}")
                            #             if isinstance(doc, dict):
                            #                 status = doc.get("status", "UNKNOWN").upper()
                            #                 # logger.info(f"第{i+1}个文档状态: {status}")
                            #                 # 收集文档ID
                            #                 doc_id = doc.get("id")
                            #                 if doc_id is not None:
                            #                     doc_ids.append(doc_id)
                            #                     # logger.info(f"第{i+1}个文档ID: {doc_id}")
                            #                 # 包含所有表示处理中的状态
                            #                 if status in ["RUNNING", "ADDED", "PROCESSING", "PENDING"]:
                            #                     has_processing_docs = True
                            #                 elif status == "COMPLETED":
                            #                     completed_count += 1
                            #             else:
                            #                 logger.info(f"第{i+1}个文档不是字典类型: {type(doc)}")
                                    
                            #         logger.info(f"文档总数: {len(doc_list)}, COMPLETED状态的文档数量: {completed_count}")
                            #         # 如果没有文档在处理中，则完成
                            #         if not has_processing_docs:
                            #             # 计算总耗时
                            #             total_time = None
                            #             if hasattr(self, '_document_registration_start_time'):
                            #                 total_time = time.time() - self._document_registration_start_time
                            #                 logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                            #                 # 清除起始时间
                            #                 delattr(self, '_document_registration_start_time')
                                        
                            #             logger.info("所有文档解析完成")
                            #             logger.info(f"文档ID列表: {doc_ids}")


                            if isinstance(doc_list, list):
                                if len(doc_list) > 0:
                                    logger.info(f"文档数量: {len(doc_list)}")
                                    # 检查所有文档的状态
                                    has_processing_docs = False
                                    doc_ids = []  # 存储所有文档ID的列表
                                    completed_count = 0 #统计COMPLETED状态的文档数量
                                    for i, doc in enumerate(doc_list):
                                        #logger.info(f"第{i+1}个文档类型: {type(doc)}")
                                        if isinstance(doc, dict):
                                            status = doc.get("status", "UNKNOWN").upper()
                                            # logger.info(f"第{i+1}个文档状态: {status}")
                                            # 收集文档ID
                                            doc_id = doc.get("id")
                                            if doc_id is not None:
                                                doc_ids.append(doc_id)
                                                # logger.info(f"第{i+1}个文档ID: {doc_id}")
                                            # 包含所有表示处理中的状态
                                            if status in ["RUNNING", "ADDED", "PROCESSING", "PENDING"]:
                                                has_processing_docs = True
                                            elif status == "COMPLETED":
                                                completed_count += 1
                                        else:
                                            logger.info(f"第{i+1}个文档不是字典类型: {type(doc)}")
                                    
                                    total_count = len(doc_list)
                                    completion_rate = (completed_count / total_count) * 100 if total_count > 0 else 0
                                    logger.info(f"文档总数: {total_count}, COMPLETED状态的文档数量: {completed_count}, 完成率: {completion_rate:.2f}%")
                                    # 如果没有文档在处理中，或者完成率达到90%及以上，则完成
                                    if not has_processing_docs or completion_rate >= 90:
                                        # 计算总耗时
                                        total_time = None
                                        if hasattr(self, '_document_registration_start_time'):
                                            total_time = time.time() - self._document_registration_start_time
                                            logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                                            # 清除起始时间
                                            delattr(self, '_document_registration_start_time')
                                        
                                        logger.info("所有文档解析完成")
                                        logger.info(f"文档ID列表: {doc_ids}")


                                        # # 在所有文档解析完成后，保存文档详细信息到Excel的sheet2
                                        # self.save_document_details_to_excel(result_text, OUTPUT_EXCEL_PATH)
                                        test_results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testresult")
                                        os.makedirs(test_results_dir, exist_ok=True)
                                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        default_excel_path = os.path.join(test_results_dir, f"document_registration_{timestamp}.xlsx")
                                        self.save_document_details_to_excel(result_text, default_excel_path)
                                        return {
                                            "success": True,
                                            "upload_id": upload_id,
                                            "response_time": response_time,
                                            "status_code": response.status_code,
                                            "response_text": response.text,
                                            "response_content": response_content_result,
                                            "raw_response_content": raw_response_content,
                                            "doc_ids": doc_ids  # 返回文档ID列表
                                        }
                                    else:
                                        logger.info("仍有文档在处理中")
                                        return {
                                            "success": False,
                                            "upload_id": upload_id,
                                            "response_time": response_time,
                                            "status_code": response.status_code,
                                            "response_text": response.text,
                                            "response_content": response_content_result,
                                            "raw_response_content": raw_response_content,
                                            "doc_ids": doc_ids,
                                            "status": "processing"
                                        }
                                else:
                                    # 计算总耗时
                                    total_time = None
                                    if hasattr(self, '_document_registration_start_time'):
                                        total_time = time.time() - self._document_registration_start_time
                                        logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                                        # 清除起始时间
                                        delattr(self, '_document_registration_start_time')
                                    
                                    logger.info(f"文档列表为空，任务已完成")
                                    return {
                                        "success": True,
                                        "upload_id": upload_id,
                                        "response_time": response_time,
                                        "status_code": response.status_code,
                                        "response_text": response.text,
                                        "response_content": response_content_result,
                                        "raw_response_content": raw_response_content,
                                        "doc_ids": []  # 空列表
                                    }
                            else:
                                # 计算总耗时
                                total_time = None
                                if hasattr(self, '_document_registration_start_time'):
                                    total_time = time.time() - self._document_registration_start_time
                                    logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                                    # 清除起始时间
                                    delattr(self, '_document_registration_start_time')
                                
                                # 如果内部不是列表格式，认为已完成
                                logger.info(f"内部数据不是文档列表格式，认为任务已完成")
                                return {
                                    "success": True,
                                    "upload_id": upload_id,
                                    "response_time": response_time,
                                    "status_code": response.status_code,
                                    "response_text": response.text,
                                    "response_content": response_content_result,
                                    "raw_response_content": raw_response_content,
                                    "doc_ids": []  # 空列表
                                }
                        else:
                            # 计算总耗时
                            total_time = None
                            if hasattr(self, '_document_registration_start_time'):
                                total_time = time.time() - self._document_registration_start_time
                                logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                                # 清除起始时间
                                delattr(self, '_document_registration_start_time')
                            
                            # 如果没有预期的data.text结构，认为已完成
                            logger.info(f"返回结果没有预期的data.text结构，认为任务已完成")
                            return {
                                "success": True,
                                "upload_id": upload_id,
                                "response_time": response_time,
                                "status_code": response.status_code,
                                "response_text": response.text,
                                "response_content": response_content_result,
                                "raw_response_content": raw_response_content,
                                "doc_ids": []  # 空列表
                            }
                    except json.JSONDecodeError as e:
                        # 计算总耗时
                        total_time = None
                        if hasattr(self, '_document_registration_start_time'):
                            total_time = time.time() - self._document_registration_start_time
                            logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                            # 清除起始时间
                            delattr(self, '_document_registration_start_time')
                        
                        # 如果解析JSON失败，认为已完成
                        logger.info(f"JSON解析失败({e})，认为任务已完成")
                        return {
                            "success": True,
                            "upload_id": upload_id,
                            "response_time": response_time,
                            "status_code": response.status_code,
                            "response_text": response.text,
                            "response_content": response_content_result,
                            "raw_response_content": raw_response_content,
                            "doc_ids": []  # 空列表
                        }
                    
                # 如果没有结果文本，认为已完成
                # 计算总耗时
                total_time = None
                if hasattr(self, '_document_registration_start_time'):
                    total_time = time.time() - self._document_registration_start_time
                    logger.info(f"文档注册完成，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                    # 清除起始时间
                    delattr(self, '_document_registration_start_time')
                
                logger.info(f"没有获取到结果文本，认为任务已完成")
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "response_text": response.text,
                    "response_content": response_content_result,
                    "raw_response_content": raw_response_content,
                    "doc_ids": []  # 空列表
                }
            else:
                # 计算总耗时
                total_time = None
                if hasattr(self, '_document_registration_start_time'):
                    total_time = time.time() - self._document_registration_start_time
                    logger.info(f"文档注册失败，已用时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                
                logger.info(f"获取文档列表失败: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "upload_id": None,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "response_text": response.text
                }
        except Exception as e:
            # 计算总耗时
            total_time = None
            if hasattr(self, '_document_registration_start_time'):
                total_time = time.time() - self._document_registration_start_time
                logger.info(f"文档注册检查异常，已用时: {total_time:.2f}秒 ({self._format_time(total_time)})")
            
            logger.info(f"请求发送失败: {e}")
            # 出现异常也认为已完成
            return {
                "success": False,
                "upload_id": None,
                "response_time": 0,
                "error": str(e)
            }
    def get_response_content_detailed(self):
        """获取响应内容并返回文本（详细版本）"""
        if not self.query_upload_id:
            logger.info("请先发送查询请求")
            return {
                "success": False,
                "error": "请先发送查询请求"
            }

        url = f"{BASE_URL}/query"
        params = {"fileData": self.query_upload_id}
        try:
            start_time = time.time()
            logger.info(f"开始获取响应内容，upload_id: {self.query_upload_id}")
            # 添加超时设置
            response = requests.get(url, params=params, stream=True,timeout=7200)  # 连接超时30秒，读取超时5分钟

            
            # 保存原始响应内容
            raw_response_content = ""
            result_text = ""
            
            logger.info("开始读取流式响应...")
            line_count = 0
            for line in response.iter_lines():
                line_count += 1
                if line:
                    raw_response_content += line.decode('utf-8') + "\n"
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        data_str = decoded_line[6:]
                        try:
                            data_json = json.loads(data_str)
                            # 确保data_json是字典类型
                            if isinstance(data_json, dict):
                                if data_json.get("type") == "output-data":
                                    # 直接使用contents作为结果文本
                                    result_text = data_json.get("contents", "")
                                    logger.info(f"获取到output-data，内容长度: {len(result_text)}")
                                    break  # 找到第一个output-data后就退出
                        except Exception as e:
                            logger.info(f"解析第{line_count}行失败: {e}")
                            # 即使解析失败，也保留原始数据
                            result_text = data_str
                            continue
            end_time = time.time()
            response_time = end_time - start_time
            logger.info(f"响应时间: {response_time:.2f}秒，处理行数: {line_count}")
            
            return {
                "success": True if result_text else False,
                "result_text": result_text,
                "response_time": response_time,
                "raw_response": raw_response_content  # 添加原始响应内容
            }
        except requests.exceptions.Timeout as e:
            logger.info(f"请求超时: {e}")
            return {
                "success": False,
                "error": f"请求超时: {str(e)}",
                "raw_response": raw_response_content
            }
        except requests.exceptions.ChunkedEncodingError as e:
            # 流式响应可能正常结束时出现此异常
            logger.info(f"流式响应结束，响应时间: {response_time:.2f}秒")
            return {
                "success": True if result_text else False,
                "result_text": result_text,
                "response_time": response_time,
                "raw_response": raw_response_content
            }
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "raw_response": raw_response_content
            }
    def _get_mime_type(self, file_path):
        """根据文件扩展名返回对应的MIME类型"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            return 'application/pdf'
        elif ext == '.docx':
            return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif ext == '.txt':
            return 'text/plain'
        elif ext == '.jpg' or ext == '.jpeg':
            return 'image/jpeg'
        elif ext == '.png':
            return 'image/png'
        else:
            return 'application/octet-stream'  # 默认二进制流


    # def send_query_with_image(self, query_text="", handler=None, image_paths=None):
    #     """发送带图片的查询请求，支持将路径列表转为二进制数据上传"""
    #     if not self.session_id:
    #         logger.info("请先获取会话信息")
    #         return False

    #     # 使用配置类的默认值或传入的参数
    #     handler = handler or self.DEFAULT_HANDLER

    #     if image_paths is None:
    #         image_paths = []
    #     elif isinstance(image_paths, str):
    #         image_paths = [image_paths]

    #     url = f"{BASE_URL}/upload"
    #     payload_data = {
    #         "text": json.dumps({
    #             "query": query_text,
    #             "handler": handler
    #         })
    #     }

    #     # 如果有文件路径，将其转为二进制数据并设置mime类型
    #     if image_paths:
    #         binary_data = []
    #         for path in image_paths:
    #             if not os.path.exists(path):
    #                 logger.error(f"文件不存在: {path}")
    #                 continue
    #             mime_type = self._get_mime_type(path)
    #             with open(path, "rb") as f:
    #                 file_data = f.read()
    #             data_chunks = []
    #             data_chunks.append(file_data)
    #             # 直接使用二进制数据，不进行Base64编码
    #             binary_data.append({
    #                 "mime": mime_type,
    #                 "data": file_data  # 直接使用二进制数据
    #             })

    #         payload_data["binary"] = binary_data

    #     payload = {
    #         "command": "query",
    #         "sessionId": self.session_id,
    #         "data": payload_data
    #     }
    #     logger.info(f"发送查询请求: {payload}")
    #     try:
    #         response = requests.post(url, json=payload)
    #         if response.status_code == 200:
    #             self.query_upload_id = response.text.strip()
    #             logger.info(f"查询请求成功，返回 upload_id: {self.query_upload_id}")
    #             return True
    #         else:
    #             logger.info(f"查询请求失败: {response.status_code} - {response.text}")
    #             return False
    #     except Exception as e:
    #         logger.info(f"请求发送失败: {e}")
    #         return False

    def send_query_with_image(self, query_text="", handler=None, image_paths=None):
        """发送带图片的查询请求"""
        if not self.session_id:
            logger.info("请先获取会话信息")
            return False
        # 使用配置类的默认值或传入的参数
        handler = handler or self.DEFAULT_HANDLER
        # modelName = modelName or self.DEFAULT_MODEL_NAME
        # modelVersion = modelVersion or self.DEFAULT_MODEL_VERSION

        if image_paths is None:
            image_paths = []
        elif isinstance(image_paths, str):
            image_paths = [image_paths]

        url = f"{BASE_URL}/upload"
        payload_data = {
            "text": json.dumps({
                "query": query_text,
                "handler": handler
                # "modelName": modelName,
                # "modelVersion": modelVersion
            })
        }
        if image_paths:
            payload_data["uri"] = image_paths

        payload = {
            "command": "query",
            "sessionId": self.session_id,
            "data": payload_data
        }
        logger.info(f"发送查询请求: {payload}")
        # print(payload)
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                self.query_upload_id = response.text.strip()
                # print(payload)
                logger.info(f"查询请求成功，返回 upload_id: {self.query_upload_id}")
                return True
            else:
                logger.info(f"查询请求失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return False
    #11.20更新细化超时
    def get_response_content(self):
        """获取响应内容并返回文本"""
        if not self.query_upload_id:
            logger.info("请先发送查询请求")
            return None

        url = f"{BASE_URL}/query"
        params = {"fileData": self.query_upload_id}

        # 初始化性能指标
        first_word_time = None
        token_count = 0
        complete_prev_time = None
        last_in_progress_text_time = None
        result_text = ""
        self.text_response_count = 0 
        self.first_text_response_time = None

        # 只保存关键的JSON数据
        key_json_data = []
        try:
            start_time = time.time()
            start_time_dt = datetime.now()
            start_time_str = start_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            logger.info(f"开始时间: {start_time_str}")
            
            response = requests.get(url, params=params, stream=True, timeout=180)
            
            # 用于存储响应行的时间信息
            response_lines = []
            
            for line in response.iter_lines():
                line_time = datetime.now()
                if line:
                    response_lines.append((line_time, line))
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        data_str = decoded_line[6:]
                        try:
                            data_json = json.loads(data_str)
                            # 只保存关键的JSON数据
                            if data_json.get("type") in ["job-id", "output-data"]:
                                key_json_data.append(data_json)
                                logger.debug(data_json)
                                
                            if data_json.get("type") == "output-data":
                                # 检查是否为文本类型响应
                                output_data = json.loads(data_json.get("contents"))
                                text_content = output_data["data"]["text"]
                                
                                # 检查文本类型
                                text_type = None
                                if isinstance(text_content, dict):
                                    text_type = text_content.get("type")
                                elif isinstance(text_content, str):
                                    try:
                                        text_json = json.loads(text_content)
                                        if isinstance(text_json, dict):
                                            text_type = text_json.get("type")
                                    except json.JSONDecodeError:
                                        pass
                                #12.20更新
                               
                                # 检查文本类型
                                text_type = None
                                if isinstance(text_content, dict):
                                    text_type = text_content.get("type")
                                elif isinstance(text_content, str):
                                    try:
                                        text_json = json.loads(text_content)
                                        if isinstance(text_json, dict):
                                            text_type = text_json.get("type")
                                    except json.JSONDecodeError:
                                        pass

                                # 记录首字时间 - 优先使用tool类型，否则使用第一个text类型
                                if first_word_time is None:
                                    # 优先检查内层是否为tool类型（比外层优先级更高）
                                    if text_type == "tool":
                                        first_word_time = line_time
                                        logger.info(f"首字时间 (tool类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                                    # 检查外层是否为tool类型
                                    elif data_json.get("type") == "tool":
                                        first_word_time = line_time
                                        logger.info(f"首字时间 (tool类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

                                # 只有在是text类型时才处理文本内容
                                if text_type == "text":
                                    # 增加text响应计数
                                    self.text_response_count += 1
                                    
                                    # 记录第一个text响应时间
                                    if self.text_response_count == 1:
                                        self.first_text_response_time = line_time
                                        logger.info(f"第一个text响应时间: {self.first_text_response_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

                                    try:
                                        if isinstance(text_content, str):
                                            text_json = json.loads(text_content)
                                            current_text = text_json.get("response", text_content)
                                        else:
                                            current_text = text_content.get("response", "")
                                        
                                        # 只有在有新内容时才更新result_text
                                        if current_text and current_text != result_text:
                                            result_text = current_text
                                    except json.JSONDecodeError:
                                        result_text = text_content

                                    # 如果还没有首字时间且这是第一个text响应，则使用text类型
                                    if first_word_time is None and self.text_response_count == 1 and text_type == "text":
                                        first_word_time = line_time
                                        logger.info(f"首字时间 (text类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

                                if output_data.get("status") == "in_progress" and text_type == "text":
                                    # 第一个text响应即开始计数token
                                    if self.text_response_count >= 1:
                                        token_count += 1
                                        last_in_progress_text_time = line_time  # 记录时间点
                                        logger.debug(f"接收到 in_progress 且类型为text的消息，当前token计数: {token_count}")

                                if output_data.get("status") == "complete":
                                    complete_prev_time = last_in_progress_text_time if last_in_progress_text_time else line_time
                                    logger.info(f"完成前最后一个时间点: {complete_prev_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                                    break


                                    # 替换 #selectedCode 中的代码为以下内容：
                                # 在处理text_type == "text"的部分进行修改
                                # if text_type == "text":
                                #     # 增加text响应计数
                                #     self.text_response_count += 1
                                    
                                #     # 记录第一个text响应时间
                                #     if self.text_response_count == 1:
                                #         self.first_text_response_time = line_time
                                #         logger.info(f"第一个text响应时间: {self.first_text_response_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

                                #     try:
                                #         if isinstance(text_content, str):
                                #             text_json = json.loads(text_content)
                                #             current_text = text_json.get("response", text_content)
                                #         else:
                                #             current_text = text_content.get("response", "")
                                        
                                #         # 只有在有新内容时才更新result_text
                                #         if current_text and current_text != result_text:
                                #             result_text = current_text
                                #     except json.JSONDecodeError:
                                #         result_text = text_content

                                #     # 记录首字时间 - 只有当这是第二个或之后的text响应时才记录
                                #     if first_word_time is None and self.text_response_count >= 2:
                                #         # 优先检查外层是否为tool类型
                                #         if data_json.get("type") == "tool":
                                #             first_word_time = line_time
                                #             logger.info(f"首字时间 (tool类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                                #         # 检查内层是否为tool类型
                                #         elif text_type == "tool":
                                #             first_word_time = line_time
                                #             logger.info(f"首字时间 (tool类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                                #         # 最后检查是否为text类型
                                #         elif text_type == "text":
                                #             first_word_time = line_time
                                #             logger.info(f"首字时间 (text类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

                                # # 在处理响应的循环中更新条件判断
                                # if output_data.get("status") == "in_progress" and text_type == "text":
                                #     # 只有当这是第二个或之后的text响应时才增加token计数
                                #     if self.text_response_count >= 2:
                                #         token_count += 1
                                #         last_in_progress_text_time = line_time  # 记录时间点
                                #         logger.debug(f"接收到 in_progress 且类型为text的消息，当前token计数: {token_count}")

                                # if output_data.get("status") == "complete":
                                #     complete_prev_time = last_in_progress_text_time if last_in_progress_text_time else line_time
                                #     logger.info(f"完成前最后一个时间点: {complete_prev_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                                #     break
                        except Exception as e:
                            logger.info(f"解析失败: {e}")
            
            end_time = time.time()
            end_time_dt = datetime.now()
            end_time_str = end_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"响应时间: {self.response_time:.2f}秒")
            logger.info(f"结束时间: {end_time_str}")
            
            # 计算性能指标
            if first_word_time and complete_prev_time:
                ttft = (first_word_time - start_time_dt).total_seconds()
                gen_time = (complete_prev_time - first_word_time).total_seconds()
                generation_speed = token_count / gen_time if gen_time > 0 else 0
                
                # 设置性能指标属性
                self.first_word_time = first_word_time
                self.ttft_seconds = ttft
                self.token_count = token_count
                self.generation_speed = generation_speed
                
                # 输出性能指标日志
                logger.info(f"性能指标:")
                logger.info(f"  - 首字时间: {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                logger.info(f"  - TTFT (Time To First Token): {ttft:.3f}秒")
                logger.info(f"  - Token数量: {token_count}")
                logger.info(f"  - 生成速度: {generation_speed:.2f} tokens/秒")
                logger.info(f"  - 生成时间: {gen_time:.3f}秒")
            else:
                # 如果无法计算完整指标，设置默认值
                self.first_word_time = None
                self.ttft_seconds = 0
                self.token_count = 0
                self.generation_speed = 0
                logger.warning("无法计算完整的性能指标")
            
            # 保存关键JSON数据和其他信息
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            
            logger.info(f"最终结果长度: {len(result_text) if result_text else 0} 字符")
            return result_text
            
        except requests.exceptions.ConnectTimeout:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"连接超时，耗时: {self.response_time:.2f}秒")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            
            # 设置默认性能指标
            self.first_word_time = None
            self.ttft_seconds = 0
            self.token_count = 0
            self.generation_speed = 0
            
            return "Error: Request Timeout"
            
        except requests.exceptions.ReadTimeout:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"读取超时，耗时: {self.response_time:.2f}秒")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            
            # 设置默认性能指标
            self.first_word_time = None
            self.ttft_seconds = 0
            self.token_count = 0
            self.generation_speed = 0
            
            return "Error: Request Timeout"
            
        except requests.exceptions.Timeout:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"请求超时，耗时: {self.response_time:.2f}秒")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            
            # 设置默认性能指标
            self.first_word_time = None
            self.ttft_seconds = 0
            self.token_count = 0
            self.generation_speed = 0
            
            return "Error: Request Timeout"
            
        except requests.exceptions.RequestException as e:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"请求异常: {e}")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            
            # 设置默认性能指标
            self.first_word_time = None
            self.ttft_seconds = 0
            self.token_count = 0
            self.generation_speed = 0
            
            timeout_keywords = ["timed out", "timeout", "time out"]
            exception_str = str(e).lower()
            if any(keyword in exception_str for keyword in timeout_keywords):
                logger.info("检测到超时相关异常，返回超时标识")
                return "Error: Request Timeout"
            return None
            
        except Exception as e:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"请求发送失败: {e}")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            
            # 设置默认性能指标
            self.first_word_time = None
            self.ttft_seconds = 0
            self.token_count = 0
            self.generation_speed = 0
            
            return None
    # def get_response_content(self):
    #     """获取响应内容并返回文本"""
    #     if not self.query_upload_id:
    #         logger.info("请先发送查询请求")
    #         return None

    #     url = f"{BASE_URL}/query"
    #     params = {"fileData": self.query_upload_id}

    #     # 初始化性能指标
    #     first_word_time = None
    #     token_count = 0
    #     complete_prev_time = None
    #     last_in_progress_text_time = None
    #     result_text=""

        
    #     # 只保存关键的JSON数据
    #     key_json_data = []
    #     try:
    #         response = requests.get(url, params=params, stream=True, timeout=180) 
    #         result_text = ""
    #         start_time_dt = datetime.now()
    #         start_time = time.time()
    #         start_time_str = start_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    #         logger.info(f"开始时间: {start_time_str}")
    #         # 用于存储响应行的时间信息
    #         response_lines = []
            
    #         for line in response.iter_lines():
    #             line_time = datetime.now()
    #             if line:
    #                 response_lines.append((line_time, line))
    #                 decoded_line = line.decode('utf-8')
    #                 if decoded_line.startswith('data: '):
    #                     data_str = decoded_line[6:]
    #                     try:
    #                         data_json = json.loads(data_str)
    #                         # 只保存关键的JSON数据
    #                         if data_json.get("type") in ["job-id", "output-data"]:
    #                             key_json_data.append(data_json)
    #                             logger.debug(data_json)
                                
    #                         if data_json.get("type") == "output-data":
    #                             # 检查是否为文本类型响应
    #                             output_data = json.loads(data_json.get("contents"))
    #                             text_content = output_data["data"]["text"]
                                
    #                             # 检查文本类型
    #                             text_type = None
    #                             if isinstance(text_content, dict):
    #                                 text_type = text_content.get("type")
    #                             elif isinstance(text_content, str):
    #                                 try:
    #                                     text_json = json.loads(text_content)
    #                                     if isinstance(text_json, dict):
    #                                         text_type = text_json.get("type")
    #                                 except json.JSONDecodeError:
    #                                     pass
                                


    #                                 # 记录首字时间 - 优先考虑tool类型（无论是外层还是内层），其次text类型
    #                             if first_word_time is None:
    #                                 # 优先检查外层是否为tool类型
    #                                 if data_json.get("type") == "tool":
    #                                     first_word_time = line_time
    #                                     logger.info(f"首字时间 (tool类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    #                                 # 检查内层是否为tool类型
    #                                 elif text_type == "tool":
    #                                     first_word_time = line_time
    #                                     logger.info(f"首字时间 (tool类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    #                                 # 最后检查是否为text类型
    #                                 elif text_type == "text":
    #                                     first_word_time = line_time
    #                                     logger.info(f"首字时间 (text类型): {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    #                             if text_type == "text":
    #                                 try:
    #                                     if isinstance(text_content, str):
    #                                         text_json = json.loads(text_content)
    #                                         current_text = text_json.get("response", text_content)
    #                                     else:
    #                                         current_text = text_content.get("response", "")
                                        
    #                                     # 只有在有新内容时才更新result_text
    #                                     if current_text and current_text != result_text:
    #                                         result_text = current_text
    #                                 except json.JSONDecodeError:
    #                                     result_text = text_content

    #                             # 在处理响应的循环中更新条件判断
    #                             if output_data.get("status") == "in_progress" and text_type == "text":
    #                                 token_count += 1
    #                                 last_in_progress_text_time = line_time  # 记录时间点
    #                                 logger.debug(f"接收到 in_progress 且类型为text的消息，当前token计数: {token_count}")

    #                             # 在处理完成状态时使用记录的时间点
    #                             if output_data.get("status") == "complete":
    #                                 complete_prev_time = last_in_progress_text_time if last_in_progress_text_time else line_time
    #                                 logger.info(f"完成前最后一个时间点: {complete_prev_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    #                                 break
    #                     except Exception as e:
    #                         logger.info(f"解析失败: {e}")
            
    #         end_time = time.time()
    #         end_time_dt = datetime.now()
    #         end_time_str = end_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    #         self.response_time = end_time - start_time
    #         logger.info(f"响应时间: {self.response_time:.2f}秒")
    #         logger.info(f"结束时间: {end_time_str}")
            
    #         # 计算性能指标
    #         if first_word_time and complete_prev_time:
    #             ttft = (first_word_time - start_time_dt).total_seconds()
    #             gen_time = (complete_prev_time - first_word_time).total_seconds()
    #             generation_speed = token_count / gen_time if gen_time > 0 else 0
                
    #             # 设置性能指标属性
    #             self.first_word_time = first_word_time
    #             self.ttft_seconds = ttft
    #             self.token_count = token_count
    #             self.generation_speed = generation_speed
                
    #             # 输出性能指标日志
    #             logger.info(f"性能指标:")
    #             logger.info(f"  - 首字时间: {first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    #             logger.info(f"  - TTFT (Time To First Token): {ttft:.3f}秒")
    #             logger.info(f"  - Token数量: {token_count}")
    #             logger.info(f"  - 生成速度: {generation_speed:.2f} tokens/秒")
    #             logger.info(f"  - 生成时间: {gen_time:.3f}秒")
    #         else:
    #             # 如果无法计算完整指标，设置默认值
    #             self.first_word_time = None
    #             self.ttft_seconds = 0
    #             self.token_count = 0
    #             self.generation_speed = 0
    #             logger.warning("无法计算完整的性能指标")
            
    #         # 保存关键JSON数据和其他信息
    #         self.data_json_list = key_json_data
    #         self.start_time_str = start_time_str
    #         self.end_time_str = end_time_str
            
    #         logger.info(f"最终结果长度: {len(result_text) if result_text else 0} 字符")
    #         return result_text
        
    #     except requests.exceptions.Timeout:
    #         end_time = time.time()
    #         end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    #         self.response_time = end_time - start_time  # 修正：记录实际耗时而不是0
    #         logger.info(f"请求超时，耗时: {self.response_time:.2f}秒")
    #         self.data_json_list = key_json_data
    #         self.start_time_str = start_time_str
    #         self.end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
    #         # 设置默认性能指标
    #         self.first_word_time = None
    #         self.ttft_seconds = 0
    #         self.token_count = 0
    #         self.generation_speed = 0
            
    #         return "Error: Request Timeout"
    #     except requests.exceptions.RequestException as e:
    #         logger.info(f"请求异常: {e}")
    #         self.response_time = 0
    #         self.data_json_list = key_json_data
    #         self.start_time_str = start_time_str
    #         self.end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
    #         # 设置默认性能指标
    #         self.first_word_time = None
    #         self.ttft_seconds = 0
    #         self.token_count = 0
    #         self.generation_speed = 0
            
    #         return None
    #     except Exception as e:
    #         logger.info(f"请求发送失败: {e}")
    #         self.response_time = 0
    #         self.data_json_list = key_json_data
    #         self.start_time_str = start_time_str
    #         self.end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
    #         # 设置默认性能指标
    #         self.first_word_time = None
    #         self.ttft_seconds = 0
    #         self.token_count = 0
    #         self.generation_speed = 0
            
    #         return None
        
    def get_response_time(self):
        """获取响应时间"""
        return self.response_time


    def save_document_details_to_excel(self, result_text, excel_path):
        """解析文档详细信息并保存到独立的Excel文件"""
        try:
            # 解析result_text
            outer_data = json.loads(result_text)
            if "data" in outer_data and "text" in outer_data["data"]:
                inner_text = outer_data["data"]["text"]
                doc_list = json.loads(inner_text)
                
                if isinstance(doc_list, list) and len(doc_list) > 0:
                    # 准备文档详细信息数据
                    doc_details = []
                    for i, doc in enumerate(doc_list):
                        doc_info = {
                            "id": doc.get("id", ""),
                            "status": doc.get("status", "UNKNOWN"),
                            "errorMsg": doc.get("errorDescription", ""),
                            "createTime": doc.get("createTime", ""),
                            "fileName": doc.get("fileName", ""),
                            "editTime": doc.get("editTime", ""),
                            "isDeleted": doc.get("isDeleted", ""),
                            "isTmpFile": doc.get("isTmpFile", ""),
                            "keywords": doc.get("keywords", ""),
                            "labelNameList": doc.get("labelNameList", ""),
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
                            "tokenNum": doc.get("tokenNum", "")
                        }
                        doc_details.append(doc_info)
                    
                    if doc_details:
                        # 修复路径处理逻辑
                        base_dir = os.path.dirname(excel_path) if excel_path else os.path.dirname(os.path.abspath(__file__))
                        base_name = os.path.splitext(os.path.basename(excel_path))[0] if excel_path else "document_details"
                        doc_details_path = os.path.join(base_dir, f"{base_name}_document.xlsx")
                        
                        # 创建包含文档详细信息的DataFrame并保存
                        doc_df = pd.DataFrame(doc_details)
                        doc_df.to_excel(doc_details_path, index=False, sheet_name='文档注册详情')
                        
                        logger.info(f"文档详细信息已保存到 {doc_details_path}")
                        logger.info(f"共保存 {len(doc_details)} 个文档的详细信息")
                        return True
                else:
                    logger.info("文档列表为空，无法保存详细信息")
            else:
                logger.info("result_text格式不符合预期，无法解析文档详细信息")
        except json.JSONDecodeError as e:
            logger.info(f"解析result_text失败: {e}")
        except Exception as e:
            logger.info(f"保存文档详细信息到Excel时出错: {e}")
            import traceback
            traceback.print_exc()

        return False
    def process_memory_data(self):
        """
        处理Memory_data.xlsx文件，在文档注册前执行
        读取Memory_data.xlsx文件，为每行创建新会话，对包含"user_content"的列执行查询
        """
        # 读取Excel文件
        memory_excel_path = MEMORY_EXCEL_PATH
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        memory_output_path = os.path.join(current_dir, "Memory_data_with_responses.xlsx")
        
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
                        # 计算写入位置
                        result_col_index = len(df.columns) + col_index * 2
                        write_column = chr(ord('A') + result_col_index)
                        write_row = row_index + 2  # +1 for header, +1 for 1-based indexing
                        
                        # 写入失败信息
                        worksheet[f'{write_column}{write_row}'] = "会话创建失败"
                        
                # 保存到文件
                try:
                    workbook.save(memory_output_path)
                    logger.info(f"第 {row_index + 1} 行结果已保存")
                    time.sleep(random.uniform(1, 3)) 

                except Exception as e:
                    logger.info(f"保存第 {row_index + 1} 行结果失败: {e}")
                continue
                
            # 获取会话信息
            session_info = memory_api.get_session_info()
            if not session_info["success"]:
                logger.info(f"第 {row_index + 1} 行获取会话信息失败: {session_info.get('error', '')}")
                # 在结果列中记录失败信息
                for col_index, column_name in enumerate(user_content_columns):
                    if column_name in row and (not pd.isna(row[column_name]) and row[column_name] != ""):
                        # 计算写入位置
                        result_col_index = len(df.columns) + col_index * 2
                        write_column = chr(ord('A') + result_col_index)
                        write_row = row_index + 2  # +1 for header, +1 for 1-based indexing
                        
                        # 写入失败信息
                        error_msg = f"会话信息获取失败: {session_info.get('error', '')}"
                        worksheet[f'{write_column}{write_row}'] = error_msg
                        
                # 保存到文件
                try:
                    workbook.save(memory_output_path)
                    logger.info(f"第 {row_index + 1} 行结果已保存")
                except Exception as e:
                    logger.info(f"保存第 {row_index + 1} 行结果失败: {e}")
                continue
                
            # 仅为包含"user_content"的列执行查询
            for col_index, column_name in enumerate(user_content_columns):
                cell_value = row[column_name]
                
                # # 跳过空值
                # if pd.isna(cell_value) or cell_value == "":
                #     continue
                    
                logger.info(f"处理第 {row_index + 1} 行, 列 '{column_name}'...")
    
                # 检查是否有pathlist列并处理图片路径
                image_paths = []
                missing_images = []
                if 'pathlist' in df.columns and row_index < len(df):
                    pathlist_value = df.iloc[row_index]['pathlist']
                    if not pd.isna(pathlist_value) and pathlist_value and str(pathlist_value).lower() not in ['nan', 'none', 'null', '']:
                        # 解析pathlist中的图片路径
                        pathlist_str = str(pathlist_value).strip()
                        if pathlist_str:
                            # 支持逗号或分号分隔的多个路径
                            image_names = [name.strip() for name in re.split(r'[,;]+', pathlist_str) if name.strip()]
                            
                            # 使用IMAGE_DIR查找图片文件
                            for image_name in image_names:
                                if image_name.lower() in ['nan', 'none', 'null', '']:
                                    continue
                                
                                found_image = None
                                # 使用全局IMAGE_DIR变量查找图片
                                if 'IMAGE_DIR' in globals():
                                    for file_path in IMAGE_DIR.rglob(image_name):
                                        if file_path.is_file():
                                            found_image = str(file_path)
                                            break
                                
                                if found_image:
                                    image_paths.append(found_image)
                                    logger.info(f"找到图片文件: {found_image}")
                                else:
                                    missing_images.append(image_name)
                                    logger.info(f"在目录 {IMAGE_DIR} 中未找到图片文件: {image_name}")
                # 处理逻辑：
                # 1. 如果user_content有值，image_paths有值 -> 发送文本+图片
                # 2. 如果user_content有值，image_paths无值 -> 只发送文本
                # 3. 如果user_content无值，image_paths有值 -> 只发送图片
                # 4. 如果user_content无值，image_paths无值 -> 跳过处理
                
                if pd.isna(cell_value) or cell_value == "":
                    # user_content为空的情况
                    if not image_paths:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content为空且无图片，跳过执行")
                        continue  # 如果既没有内容也没有图片，则跳过
                    else:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content为空，但有图片，仅发送图片")
                else:
                    # user_content不为空的情况
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content不为空")
                    if image_paths:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content不为空且有图片，发送文本+图片")
                    
                    else:
                        logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' user_content不为空但无图片，仅发送文本")

                # 如果有图片缺失且没有找到任何图片，可以选择跳过或者继续执行
                if missing_images and not image_paths:
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 所有图片都未找到，跳过执行")
                    result_col_index = len(df.columns) + col_index * 2
                    write_column = chr(ord('A') + result_col_index)
                    write_row = row_index + 2 
                    worksheet[f'{write_column}{write_row}'] = "Error: 所有图片未找到"
                    # 保存到文件并继续下一个
                    try:
                        workbook.save(memory_output_path)
                        logger.info(f"第 {row_index + 1} 行结果已保存")
                    except Exception as e:
                        logger.info(f"保存第 {row_index + 1} 行结果失败: {e}")
                    continue  # 跳过当前列的处理

                # 发送查询请求，传递图片路径和可能的文本内容
                query_text = "" if (pd.isna(cell_value) or cell_value == "") else str(cell_value)
                if memory_api.send_query_with_image(query_text=query_text, image_paths=image_paths if image_paths else None):
                    # 获取响应内容
                    response_content = memory_api.get_response_content()
                    response_time = memory_api.get_response_time()
                    
                    # 计算写入位置
                    result_col_index = len(df.columns) + col_index * 2
                    write_column = chr(ord('A') + result_col_index)
                    write_row = row_index + 2  # +1 for header, +1 for 1-based indexing
                    
                    # 将响应内容写入对应单元格
                    worksheet[f'{write_column}{write_row}'] = response_content if response_content else "无响应内容"
                    # 在相邻列记录响应时间
                    if response_time is not None:
                        time_column = chr(ord('A') + result_col_index + 1)
                        worksheet[f'{time_column}{write_row}'] = f"{response_time:.2f}s"
                    
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 处理完成")
                else:
                    logger.info(f"第 {row_index + 1} 行, 列 '{column_name}' 查询发送失败")

                    result_col_index = len(df.columns) + col_index * 2
                    write_column = chr(ord('A') + result_col_index)
                    write_row = row_index + 2 
                    worksheet[f'{write_column}{write_row}'] = "查询发送失败"
                
                # 保存到文件
                try:
                    workbook.save(memory_output_path)
                    logger.info(f"第 {row_index + 1} 行结果已保存")
                except Exception as e:
                    logger.info(f"保存第 {row_index + 1} 行结果失败: {e}")
                
                time.sleep(1)

            time.sleep(2)
        try:
            workbook.save(memory_output_path)
            logger.info(f"\n所有Memory数据处理完成，结果已保存到: {memory_output_path}")
            return True
        except Exception as e:
            logger.info(f"最终保存Memory文件失败: {e}")
            return False
        
    def run_query_only(self, query_text="", handler=None, image_paths=None, modelName=None, modelVersion=None, reuse_session=False):
        """只运行查询流程，不包含文档注册"""
        # 使用类默认值或传入的参数
        handler = handler or self.DEFAULT_HANDLER
        # modelName = modelName or self.DEFAULT_MODEL_NAME
        # modelVersion = modelVersion or self.DEFAULT_MODEL_VERSION

        # 重置响应时间
        self.response_time = 0
        
        # 如果不是复用会话，则创建新会话
        if not reuse_session:
            if not self.create_session():
                return None
            time.sleep(1)
            session_info = self.get_session_info()
            if not session_info.get("success", False):
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

        logger.info(f"最终结果: {result}")
        return result
    def process_memory_data_only(self):
        """
        仅处理Memory数据
        """
        logger.info("开始处理Memory数据...")
        memory_success = self.process_memory_data()
        if memory_success:
            logger.info("Memory数据处理完成")
            return True
        else:
            logger.info("Memory数据处理失败")
            return False
        
    #增加对注册库实际状态的检查：
    def process_document_registration_only(self):
        """
        仅处理文档注册流程
        """
        logger.info("开始文档注册流程...")
        if not self.create_session():
            logger.info("创建会话失败")
            return False

        time.sleep(1)
        session_info = self.get_session_info()
        if not session_info.get("success", False):
            logger.info("获取会话信息失败")
            return False
        
        # 获取文档列表
        doc_file_list = []
        if os.path.exists(doc_directory):
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

        # 检查是否需要注册文档
        is_registered = self.is_document_registered(doc_file_list)
        
        # 如果显示已注册，进一步检查注册库是否真的存在这些文档
        if is_registered:
            logger.info("检查注册库实际状态...")
            # 调用获取文档列表接口检查实际注册状态
            check_result = self.get_register_document()
            if check_result.get("success", False):
                # 解析返回的结果检查文档是否存在
                result_text = check_result.get("response_content", {}).get("result_text", "")
                if result_text:
                    try:
                        outer_data = json.loads(result_text)
                        if "data" in outer_data and "text" in outer_data["data"]:
                            inner_text = outer_data["data"]["text"]
                            doc_list = json.loads(inner_text)
                            # 如果返回的文档列表为空，说明注册库已被清理
                            if not doc_list or len(doc_list) == 0:
                                logger.info("检测到注册库已被清理，将重新注册文档")
                                is_registered = False
                                # 清除本地注册记录
                                self.registered_docs.clear()
                                self.save_registered_docs()
                    except Exception as e:
                        logger.info(f"检查注册库状态时解析失败: {e}")
                else:
                    logger.info("注册库可能已被清理，将重新注册文档")
                    is_registered = False
                    # 清除本地注册记录
                    self.registered_docs.clear()
                    self.save_registered_docs()
            else:
                logger.info("无法获取注册库状态，假设需要重新注册")
                is_registered = False
                # 清除本地注册记录
                self.registered_docs.clear()
                self.save_registered_docs()
        
        if not is_registered:
            # 记录文档注册开始时间
            self._document_registration_start_time = time.time()
            logger.info(f"开始文档注册，时间: {datetime.fromtimestamp(self._document_registration_start_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
            # # 注册文档 - 修改这部分代码
            # register_result = self.register_documents_individually(doc_file_list)
            # success_count = register_result.get("success_count", 0)
            # total_count = register_result.get("total", 0)

            # logger.info(f"文档注册结果: {success_count}/{total_count} 成功")

            # if success_count == 0:
            #     logger.error("所有文档注册失败")
            #     # 清除起始时间
            #     if hasattr(self, '_document_registration_start_time'):
            #         delattr(self, '_document_registration_start_time')
            #     return False
            # elif success_count < total_count:
            #     logger.warning(f"部分文档注册失败: {success_count}/{total_count} 成功")
            #     # 可以选择继续处理或者返回失败
            #     # 这里我们选择继续处理，但记录警告
            # else:
            #     logger.info("所有文档注册成功")



            register_result = self.register_document(doc_file_list)
            if not register_result.get("success", False):
                logger.info("文档注册失败")
                # 清除起始时间
                if hasattr(self, '_document_registration_start_time'):
                    delattr(self, '_document_registration_start_time')
                return False
            time.sleep(2)
            max_retries = 10000000
            retry_interval = 2
            attempt = 0
            
            while attempt < max_retries:
                attempt += 1
                logger.info(f"第{attempt}次检查文档处理状态...")
                
                doc_status = self.get_register_document()
                if doc_status.get("success", False):
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
                    # 清除起始时间
                    if hasattr(self, '_document_registration_start_time'):
                        delattr(self, '_document_registration_start_time')
                    return False
            else:
                logger.info(f"超过最大重试次数({max_retries})，文档可能仍在处理中")
                return False
        else:
            logger.info("文档已注册，跳过注册流程")
        
        logger.info("文档注册流程完成")
        return True
    # 添加辅助方法用于格式化时间显示

    #逐个注册
    # def process_document_registration_only(self):
    #     """
    #     仅处理文档注册流程
    #     """
    #     logger.info("开始文档注册流程...")
    #     if not self.create_session():
    #         logger.info("创建会话失败")
    #         return False

    #     time.sleep(1)
    #     session_info = self.get_session_info()
    #     if not session_info.get("success", False):
    #         logger.info("获取会话信息失败")
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

    #     # 检查是否需要注册文档
    #     is_registered = self.is_document_registered(doc_file_list)
        
    #     # 如果显示已注册，进一步检查注册库是否真的存在这些文档
    #     if is_registered:
    #         logger.info("检查注册库实际状态...")
    #         # 调用获取文档列表接口检查实际注册状态
    #         check_result = self.get_register_document()
    #         if check_result.get("success", False):
    #             # 解析返回的结果检查文档是否存在
    #             result_text = check_result.get("response_content", {}).get("result_text", "")
    #             if result_text:
    #                 try:
    #                     outer_data = json.loads(result_text)
    #                     if "data" in outer_data and "text" in outer_data["data"]:
    #                         inner_text = outer_data["data"]["text"]
    #                         doc_list = json.loads(inner_text)
    #                         # 如果返回的文档列表为空，说明注册库已被清理
    #                         if not doc_list or len(doc_list) == 0:
    #                             logger.info("检测到注册库已被清理，将重新注册文档")
    #                             is_registered = False
    #                             # 清除本地注册记录
    #                             self.registered_docs.clear()
    #                             self.save_registered_docs()
    #                 except Exception as e:
    #                     logger.info(f"检查注册库状态时解析失败: {e}")
    #             else:
    #                 logger.info("注册库可能已被清理，将重新注册文档")
    #                 is_registered = False
    #                 # 清除本地注册记录
    #                 self.registered_docs.clear()
    #                 self.save_registered_docs()
    #         else:
    #             logger.info("无法获取注册库状态，假设需要重新注册")
    #             is_registered = False
    #             # 清除本地注册记录
    #             self.registered_docs.clear()
    #             self.save_registered_docs()
        
    #     if not is_registered:
    #         # 记录文档注册开始时间
    #         self._document_registration_start_time = time.time()
    #         logger.info(f"开始文档注册，时间: {datetime.fromtimestamp(self._document_registration_start_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
    #         # 逐个注册文档，避免一次性注册所有文档导致卡顿
    #         success_count = 0
    #         total_count = len(doc_file_list)

    #         for doc_path in doc_file_list:
    #             logger.info(f"注册文档: {doc_path}")
    #             register_result = self.register_document([doc_path])  # 每次只注册一个文档
    #             if register_result.get("success", False):
    #                 success_count += 1
    #                 logger.info(f"文档注册成功: {doc_path}")
    #             else:
    #                 logger.info(f"文档注册失败: {doc_path}")
    #             time.sleep(2)  # 每次注册之间间隔1秒

    #         register_result = {
    #             "success": success_count == total_count,
    #             "success_count": success_count,
    #             "total": total_count
    #         }
            
    #         if not register_result.get("success", False):
    #             logger.info("文档注册失败")
    #             # 清除起始时间
    #             if hasattr(self, '_document_registration_start_time'):
    #                 delattr(self, '_document_registration_start_time')
    #             return False
    #         # time.sleep(2)
    #         max_retries = 10000000
    #         retry_interval = 2
    #         attempt = 0
            
    #         while attempt < max_retries:
    #             attempt += 1
    #             logger.info(f"第{attempt}次检查文档处理状态...")
                
    #             doc_status = self.get_register_document()
    #             if doc_status.get("success", False):
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
    #                 # 清除起始时间
    #                 if hasattr(self, '_document_registration_start_time'):
    #                     delattr(self, '_document_registration_start_time')
    #                 return False
    #         else:
    #             logger.info(f"超过最大重试次数({max_retries})，文档可能仍在处理中")
    #             return False
    #     else:
    #         logger.info("文档已注册，跳过注册流程")
        
    #     logger.info("文档注册流程完成")
    #     return True
    def _format_time(self, seconds):
        """格式化时间显示为 HH:MM:SS 格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def process_main_excel_only(self, cycle=1):
        """
        仅处理主Excel文件，支持循环执行，但只保存最后一轮结果
        支持根据 new_session 列决定是否复用 session
        """
        logger.info(f"开始处理主Excel文件，循环轮数: {cycle}")
        
        # 用于存储所有轮次的最终结果（按行索引）
        final_results = {}

        for cycle_index in range(cycle):
            logger.info(f"开始执行第 {cycle_index + 1}/{cycle} 轮循环")
            
            try:
                df = pd.read_excel(EXCEL_FILE_PATH, sheet_name=0)
                logger.info(f"成功加载 Excel，共 {len(df)} 行数据")
            except Exception as e:
                logger.info(f"读取 Excel 失败: {e}")
                return False

            # 永远使用 _cycleN 格式，不再生成主文件
            cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
            
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

            # 保存上一个会话的信息
            previous_api = None

            for index in range(start_index, len(df)):
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
                        for file_path in IMAGE_DIR.rglob(image_name):
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
                     #1126 添加第一个text响应时间

                    first_text_response_time_str = getattr(api, 'first_text_response_time', None)
                    if first_text_response_time_str:
                        first_text_response_time_str = first_text_response_time_str.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    
                    if hasattr(api, 'data_json_list') and api.data_json_list:
                        data_json_content = json.dumps(api.data_json_list, ensure_ascii=False, indent=2)

                    # 结果处理逻辑
                    if result is not None and isinstance(result, str) and len(result.strip()) > 0 and not result.startswith("Error:"):
                        df_output.at[index, 'result'] = result
                        df_output.at[index, 'response_time'] = response_time
                        df_output.at[index, 'data_json_list'] = data_json_content 
                        df_output.at[index, 'start_time'] = start_time_str 
                        df_output.at[index, 'end_time'] = end_time_str   
                        # 保存性能指标
                        df_output.at[index, 'first_word_time'] = first_word_time_str
                        df_output.at[index, 'first_text_response_time'] = first_text_response_time_str
                        df_output.at[index, 'ttft'] = ttft
                        df_output.at[index, 'token_count'] = token_count
                        df_output.at[index, 'generation_speed'] = generation_speed
                        
                        logger.info(f"第 {index + 1} 行处理成功，结果长度: {len(result)}，响应时间: {response_time:.2f}秒")
                    else:
                        if result == "Error: Request Timeout":
                            df_output.at[index, 'result'] = "Error: Request Timeout"
                        elif result is None or result == "" or (isinstance(result, str) and len(result.strip()) == 0):
                            df_output.at[index, 'result'] = "Error: Empty response from server"
                        else:
                            df_output.at[index, 'result'] = result if result else "Error: Empty response from server"
                        
                        df_output.at[index, 'response_time'] = response_time
                        df_output.at[index, 'data_json_list'] = data_json_content
                        df_output.at[index, 'start_time'] = start_time_str
                        df_output.at[index, 'end_time'] = end_time_str    
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
                    # 异常情况下的性能指标
                    df_output.at[index, 'first_word_time'] = None
                    df_output.at[index, 'first_text_response_time'] = None
                    df_output.at[index, 'ttft'] = 0
                    df_output.at[index, 'token_count'] = 0
                    df_output.at[index, 'generation_speed'] = 0
                    logger.info(f"第 {index + 1} 行错误已记录，继续处理下一条数据")


                try:
                    df_output.to_excel(cycle_output_path, index=False,sheet_name='result')
                    logger.info(f"第 {index + 1} 行结果已保存")
                except Exception as e:
                    logger.info(f"保存第 {index + 1} 行结果失败: {e}")

            logger.info(f"\n第 {cycle_index + 1} 轮循环完成，结果已保存至: {cycle_output_path}")
            
        logger.info(f"\n所有 {cycle} 轮循环已完成")
        return True

    def run_main_process(self, cycle=1):
        """
        运行完整的主流程逻辑，支持循环执行
        """
        # 首先处理Memory数据（仅当未处理过时）
        if not MultimodalAPI._memory_processed:
            logger.info("开始处理Memory数据...")
            memory_success = self.process_memory_data()
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
        return self.process_main_excel_only(cycle)

def start_resource_monitoring(gpu_type):
    """启动资源监控"""
    process_names = ['com.lenovo.quantum.exe','com.lenovo.quantum.exe','mcpMgmtService.exe','mcpMgmtService.exe','lenovo.pfm.pipe.exe'] # 需要监控的进程名
    start_timestamp = int(time.time() * 1000)
    # logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    log_file_path = os.path.join(logs_dir, f'resource_monitor_{timestamp}.log')
    
    # 创建资源监控日志目录
    resource_logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resource")
    os.makedirs(resource_logs_dir, exist_ok=True)
    resource_csv_path = os.path.join(resource_logs_dir, f'resource_{timestamp}.csv')
    
    # 创建SystemMonitor实例
    monitor = memory.SystemMonitor(
        process_name_list=process_names,
        product_type=gpu_type,
        start_timestamp=str(start_timestamp),
        log_file_path=log_file_path
    )
    
    # 启动监控线程
    monitor.start_monitoring_resource(resource_csv_path)
    return monitor, resource_csv_path, start_timestamp

def stop_resource_monitoring(monitor):
    """停止资源监控"""
    if monitor:
        monitor.stop_monitoring_resource()
def add_resource_data_to_results(resource_csv_path, excel_output_path):
    """
    将资源监控数据添加到结果Excel文件的resource sheet中
    """
    try:
        # 读取资源监控数据
        resource_df = pd.read_csv(resource_csv_path)
        
        # 如果结果Excel文件已存在，以追加模式打开
        if os.path.exists(excel_output_path):
            with pd.ExcelWriter(excel_output_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
                resource_df.to_excel(writer, sheet_name='resource', index=False)
        else:
            # 如果文件不存在，创建新文件
            with pd.ExcelWriter(excel_output_path, engine='openpyxl') as writer:
                resource_df.to_excel(writer, sheet_name='resource', index=False)
                
        logger.info(f"资源监控数据已保存到 {excel_output_path} 的 resource sheet中")
    except Exception as e:
        logger.error(f"保存资源监控数据失败: {e}")
        import traceback
        traceback.print_exc()  # 添加详细错误信息
def backup_and_cleanup_directories():
    """
    在运行测试前备份和清理相关目录
    1. 备份指定目录并重命名为带时间戳的名称
    2. 删除指定目录的内容
    """
    username = os.getenv('USERNAME') or os.getenv('USER')
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    logger.info("开始备份日志信息和清理目录...")
    # 需要备份的目录
    backup_dirs = [
        f"C:\\Users\\{username}\\AppData\\Local\\mcp_mgmt_service",
        f"C:\\Users\\{username}\\AppData\\Local\\quantum_core"
    ]
    
    # 需要删除的目录
    delete_dirs = [
        f"C:\\Users\\{username}\\.quantum",
        f"C:\\Users\\{username}\\Documents\\QTCore",
        f"C:\\Users\\{username}\\AppData\\Quantum",
        f"C:\\Users\\{username}\\AppData\\Local\\Lenovo\\QuantumAI"
    ]
    
    # 备份目录
    for dir_path in backup_dirs:
        if os.path.exists(dir_path):
            backup_path = f"{dir_path}_{timestamp}"
            try:
                shutil.copytree(dir_path, backup_path)
                logger.info(f"成功备份日志目录: {dir_path} -> {backup_path}")
                shutil.rmtree(dir_path)
                logger.info(f"成功删除日志目录: {dir_path}")
            except Exception as e:
                logger.error(f"备份目录失败 {dir_path}: {e}")
        else:
            logger.info(f"备份目录不存在: {dir_path}")
    
    # 删除目录
    for dir_path in delete_dirs:
        if os.path.exists(dir_path):
            try:
                if os.path.isfile(dir_path):
                    os.remove(dir_path)
                else:
                    shutil.rmtree(dir_path)
                logger.info(f"成功删除目录: {dir_path}")
            except Exception as e:
                logger.error(f"删除目录失败 {dir_path}: {e}")
        else:
            logger.info(f"删除目录不存在: {dir_path}")

def run_quantum_e2e_process(args):
    """
    运行 Quantum_e2e_v20251110 的主流程逻辑。
    
    参数:
        args: argparse.Namespace 对象，包含运行所需的参数。
    
    返回:
        bool: 流程是否成功完成。
    """
    global OUTPUT_EXCEL_PATH, EXCEL_FILE_PATH, _MEMORY_PROCESSED_GLOBAL
    
    #4、处理流程==================================================================================================================
    if args.process_memory or args.process_document or args.process_main:
        args.process_all = False
    if args.process_document and not (args.process_memory or args.process_main or args.process_all):
        # 只处理文档注册，不需要Excel文件
        logger.info("开始文档注册流程...")
        # 启动资源监控
        monitor = None
        resource_csv_path = None
        try:
            monitor, resource_csv_path, start_timestamp = start_resource_monitoring(GPU_TYPE)
            api = MultimodalAPI()
            success = api.process_document_registration_only()
            if success:
                logger.info("文档注册流程完成")
                return True
            else:
                logger.info("文档注册流程失败")
                return False
        finally:
            # 停止资源监控
            if monitor:
                stop_resource_monitoring(monitor)

    # 修改主程序中的文件处理部分
    if args.process_main or args.process_memory or args.process_all:
        # 检查excel_dir是文件还是目录
        excel_path = Path(EXCEL_DIR)
        
        if excel_path.is_file() and excel_path.suffix.lower() == '.xlsx':
            # 如果指定了具体的Excel文件
            excel_files = [excel_path]
            logger.info(f"处理指定的Excel文件: {excel_path.name}")
        else:
            # 如果是目录，则获取目录下所有Excel文件
            excel_files = list(excel_path.glob("*.xlsx"))
            if not excel_files:
                logger.info(f"在目录 {EXCEL_DIR} 中未找到Excel文件")
                return False
            logger.info(f"找到 {len(excel_files)} 个Excel文件")
        monitor = None
        try:
            monitor, resource_csv_path, start_timestamp = start_resource_monitoring(GPU_TYPE)
            
            # 对于 --process_all 模式，处理所有Excel文件
            if args.process_all:
                # 首先处理Memory数据（如果需要且尚未处理）
                if args.process_memory and not _MEMORY_PROCESSED_GLOBAL and not MultimodalAPI._memory_processed:
                    logger.info("开始处理Memory数据...")
                    memory_api = MultimodalAPI()
                    memory_success = memory_api.process_memory_data_only()
                    _MEMORY_PROCESSED_GLOBAL = True
                    MultimodalAPI._memory_processed = True
                    if memory_success:
                        logger.info("Memory数据处理完成")
                    else:
                        logger.info("Memory数据处理失败")
                
                # 处理所有Excel文件
                for excel_file in excel_files:
                    logger.info(f"\n正在处理文件: {excel_file.name}")
                    OUTPUT_EXCEL_PATH = os.path.join(TEST_RESULTS_DIR, f"test_results_{excel_file.stem}_{timestamp}.xlsx")
                    EXCEL_FILE_PATH = str(excel_file)
                    
                    # 为每个文件创建新的API实例
                    api = MultimodalAPI()
                    success = api.run_main_process(CYCLE_COUNT)
                    
                    if success:
                        logger.info(f"文件 {excel_file.name} 处理完成")
                    else:
                        logger.info(f"文件 {excel_file.name} 处理失败")
            else:
                # 处理每个Excel文件（根据特定参数）
                # 首先处理Memory数据（如果需要且尚未处理）
                if args.process_memory and not _MEMORY_PROCESSED_GLOBAL and not MultimodalAPI._memory_processed:
                    logger.info("开始处理Memory数据...")
                    memory_api = MultimodalAPI()
                    memory_success = memory_api.process_memory_data_only()
                    _MEMORY_PROCESSED_GLOBAL = True
                    MultimodalAPI._memory_processed = True
                    if memory_success:
                        logger.info("Memory数据处理完成")
                    else:
                        logger.info("Memory数据处理失败")
                
                for excel_file in excel_files:
                    logger.info(f"\n正在处理文件: {excel_file.name}")
                    
                    OUTPUT_EXCEL_PATH = os.path.join(TEST_RESULTS_DIR, f"test_results_{excel_file.stem}_{timestamp}.xlsx")
                    EXCEL_FILE_PATH = str(excel_file)
                    
                    api = MultimodalAPI()
                    
                    # 根据参数执行特定流程（跳过Memory处理，因为已经全局处理过了）
                    success = True
                    if args.process_document:
                        success = api.process_document_registration_only()
                        
                    if success and args.process_main:
                        success = api.process_main_excel_only(CYCLE_COUNT)
                    
                    if success:
                        logger.info(f"文件 {excel_file.name} 处理完成")
                    else:
                        logger.info(f"文件 {excel_file.name} 处理失败")

        finally:
            try:
                if monitor:
                    stop_resource_monitoring(monitor)
                
                if resource_csv_path and os.path.exists(resource_csv_path):
                    for cycle_index in range(CYCLE_COUNT):
                        try:
                            cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
                            add_resource_data_to_results(resource_csv_path, cycle_output_path)
                        except Exception as e:
                            logger.error(f"添加资源数据到循环{cycle_index+1}失败: {e}")
                            continue  
                            
            except Exception as e:
                logger.error(f"资源清理过程中出现错误: {e}")
            # finally:
            #     # 确保服务总是被关闭
            #     try:
            #         logger.info("测试完成,关闭服务")
            #         stop_services(logger)
            #     except Exception as e:
            #         logger.error(f"关闭服务时出现错误: {e}")
    return True


def save_args_to_json(args, config_path):
    """
    将命令行参数保存到 JSON 文件中。
    
    参数:
        args: argparse.Namespace 对象，包含运行所需的参数。
        config_path: str，JSON 配置文件的路径。
    """
    try:
        # 将 Namespace 转换为字典
        args_dict = vars(args)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # 写入 JSON 文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(args_dict, f, ensure_ascii=False, indent=4)
        
        logger.info(f"参数已成功保存到 JSON 文件: {config_path}")
    except Exception as e:
        logger.error(f"保存参数到 JSON 文件失败: {e}")

if __name__ == "__main__":
    BASE_URL = "http://127.0.0.1:35253"
    TEST_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testresult")
    os.makedirs(TEST_RESULTS_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description='API Test')
    parser.add_argument('--excel_dir', type=str, default=r"C:\Users\obe\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251201_nova\dataset1126\Memory_question _v3_1016+EN_DOC_30_1031+en_query30_1031.xlsx", help='Excel文件目录路径')
    parser.add_argument('--image_dir', type=str, default=r"C:\Users\obe\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251201_nova\OneDrive_1_2025-12-1\document", help='是否需要用到pathlist')
    parser.add_argument('--doc_dir', type=str, default=r"C:\Users\obe\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251201_nova\files1114\Files20251126", help='文档目录路径')
    parser.add_argument('--memory_excel', type=str, default=r"C:\Users\obe\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251201_nova\Memory_data+_v3_1016_a.xlsx", help='Memory Excel文件路径')
    parser.add_argument('--process_memory', action='store_true',default=False, help='处理Memory数据')
    parser.add_argument('--process_document', action='store_true',default=False, help='处理文档注册')
    parser.add_argument('--process_main', action='store_true',default=True, help='处理主Excel文件')
    parser.add_argument('--process_all', action='store_true', default=False, help='执行完整流程（默认）')
    parser.add_argument('--cycle', type=int, default=1, help='循环轮数，默认为1')
    parser.add_argument('--gpu_type', type=str, default="aGPU", choices=["dGPU", "iGPU", "aGPU"], help='GPU类型')
    parser.add_argument('--service_path', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\version\LATC_Brain_20251031\Lenovo_Quantum_Core_V20251030_R8_226", help='服务目录路径')
    args = parser.parse_args()
    logger.info("程序启动参数: " + ", ".join([f"{k}={v}" for k, v in vars(args).items()]))
    CONFIG_PATH = os.path.join(script_dir, "config.json")
    save_args_to_json(args, CONFIG_PATH)

    EXCEL_DIR = args.excel_dir
    IMAGE_DIR = Path(args.image_dir)
    doc_directory = args.doc_dir
    MEMORY_EXCEL_PATH = args.memory_excel
    CYCLE_COUNT = args.cycle
    GPU_TYPE = args.gpu_type
    base_dir = args.service_path

    #1、清理数据前停止服务======================================================================================================
    # logger.info("备份前停止服务...")
    # try:
    #     stop_services(logger)
    #     logger.info("服务已停止，开始备份和清理目录...")
    # except Exception as e:
    #     logger.warning(f"停止服务时出现异常: {e}")
    
    # #2、备份和清理目录===========================================================================================================
    # backup_and_cleanup_directories()
    
    # #3、启动服务=================================================================================================================
    # logger.info("开始启动服务...")
    # if start_services(base_dir, logger):
    #     logger.info("所有服务启动成功，可以继续执行后续流程")
    # else:
    #     logger.error("服务启动失败，无法继续执行后续流程")
    #     exit(1)
    #4、处理流程==================================================================================================================
    try:
        success = run_quantum_e2e_process(args)
        if success:
            logger.info("所有流程成功完成！")
            logger.info("开始自动判断...")
            Auto_Judge.run(args.doc_dir)
        else:
            logger.info("流程执行失败！")
    except Exception as e:
        logger.error(f"主流程执行过程中出现错误: {e}")
    # Auto_Judge.run(args.doc_dir)
    # finally:
    # # 5. 确保服务总是被关闭
    #     try:
    #         logger.info("测试完成, 关闭服务")
    #         stop_services(logger)
    #     except Exception as e:
    #         logger.error(f"关闭服务时出现错误: {e}")
        #4、处理流程==================================================================================================================
    # try:
    #     interval_seconds = 2 * 60 * 60  # 2小时
    #     while True:
    #         success = run_quantum_e2e_process(args)
    #         if success:
    #             logger.info("所有流程成功完成！")
    #         else:
    #             logger.info("流程执行失败！")
            
    #         # 计算下次执行时间
    #         next_run = datetime.now() + timedelta(hours=2)
    #         logger.info(f"等待{interval_seconds}秒后再次执行，预计下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    #         time.sleep(interval_seconds)
    # except KeyboardInterrupt:
    #     logger.info("用户中断程序执行")
    # except Exception as e:
    #     logger.error(f"主流程执行过程中出现错误: {e}")
#4、处理流程==================================================================================================================
    # try:
    #     interval_seconds = 2 * 60 * 60  # 2小时
    #     cycle_count = 1
    #     while True:
    #         logger.info(f"开始第 {cycle_count} 轮循环执行")
    #         try:
    #             success = run_quantum_e2e_process(args)
    #             if success:
    #                 logger.info("所有流程成功完成！")
    #             else:
    #                 logger.info("流程执行失败！")
    #         except Exception as e:
    #             logger.error(f"主流程执行过程中出现错误: {e}")
    #             import traceback
    #             traceback.print_exc()
            
    #         # 计算下次执行时间
    #         next_run = datetime.now() + timedelta(hours=2)
    #         logger.info(f"第 {cycle_count} 轮执行完成，等待 {interval_seconds} 秒后再次执行，预计下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    #         cycle_count += 1
            
    #         time.sleep(interval_seconds)
    # except KeyboardInterrupt:
    #     logger.info("用户中断程序执行")
    # except Exception as e:
    #     logger.error(f"定时执行过程中出现错误: {e}")
    