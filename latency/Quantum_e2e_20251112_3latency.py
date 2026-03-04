# -*- coding: utf-8 -*-
# 创建时间：2023年11月12日
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
    DEFAULT_HANDLER = "aaitc-graph-brain"
    DEFAULT_MODEL_NAME = "gpt"
    DEFAULT_MODEL_VERSION = "gpt-4.1"
    def __init__(self):
        self.upload_id = None
        self.session_id = None
        self.job_id = None
        self.query_upload_id = None
        self.response_time = 0
        self.registered_docs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registered_docs.json")
        self.registered_docs = self.load_registered_docs()
        self.cycle_output_path = None 

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
                            
                            # 确保doc_list是列表类型
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
                                    
                                    logger.info(f"文档总数: {len(doc_list)}, COMPLETED状态的文档数量: {completed_count}")
                                    # 如果没有文档在处理中，则完成
                                    if not has_processing_docs:
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
            response = requests.get(url, params=params, stream=True)
            end_time = time.time()
            response_time = end_time - start_time
            
            # 保存原始响应内容
            raw_response_content = ""
            result_text = ""
            
            for line in response.iter_lines():
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
                                    break  # 找到第一个output-data后就退出
                        except Exception as e:
                            logger.info(f"解析失败: {e}")
                            # 即使解析失败，也保留原始数据
                            result_text = data_str
                            continue
            
            logger.info(f"响应时间: {response_time:.2f}秒")
            
            return {
                "success": True if result_text else False,
                "result_text": result_text,
                "response_time": response_time,
                "raw_response": raw_response_content  # 添加原始响应内容
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
    def send_query_with_image(self, query_text="", handler=None, image_paths=None,modelName=None,modelVersion=None):
        """发送带图片的查询请求"""
        if not self.session_id:
            logger.info("请先获取会话信息")
            return False
        # 使用配置类的默认值或传入的参数
        handler = handler or self.DEFAULT_HANDLER
        modelName = modelName or self.DEFAULT_MODEL_NAME
        modelVersion = modelVersion or self.DEFAULT_MODEL_VERSION

        if image_paths is None:
            image_paths = []
        elif isinstance(image_paths, str):
            image_paths = [image_paths]

        url = f"{BASE_URL}/upload"
        payload_data = {
            "text": json.dumps({
                "query": query_text,
                "handler": handler,
                "modelName": modelName,
                "modelVersion": modelVersion
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
    def get_response_content(self):
        """获取响应内容并返回文本"""
        if not self.query_upload_id:
            logger.info("请先发送查询请求")
            return None

        url = f"{BASE_URL}/query"
        params = {"fileData": self.query_upload_id}
        
        # 只保存关键的JSON数据
        key_json_data = []
        # 初始化变量，确保在所有执行路径中都定义
        end_time_str = None
        start_time_str = None
        
        try:
            response = requests.get(url, params=params, stream=True, timeout=180) 
            start_time = time.time()
            start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            logger.info(f"开始时间: {start_time_str}")
            result_text = ""
            # 修改 get_response_content 方法中的解析逻辑    适配1031版本
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        data_str = decoded_line[6:]  # 移除 "data: " 前缀
                        try:
                            data_json = json.loads(data_str)
                            # 只保存关键的JSON数据
                            if data_json.get("type") in ["job-id", "output-data"]:
                                key_json_data.append(data_json)
                                logger.debug(data_json)
                                
                            if data_json.get("type") == "output-data":
                                output_data = json.loads(data_json.get("contents"))
                                
                                text_content = ""
                                if isinstance(output_data, dict) and "data" in output_data:
                                    if isinstance(output_data["data"], dict) and "text" in output_data["data"]:
                                        text_content = output_data["data"]["text"]
                                    else:
                                        logger.info(f"output_data['data']结构异常: {output_data['data']}")
                                else:
                                    logger.info(f"output_data结构异常: {output_data}")
                                
                                if text_content:
                                    try:
                                        # 首先尝试解析为JSON
                                        text_json = json.loads(text_content)
                                        # 检查是否有response字段（新的格式）
                                        if "response" in text_json:
                                            result_text = text_json.get("response", "")
                                        else:
                                            # 保持向后兼容（旧的格式）
                                            result_text = text_content
                                    except json.JSONDecodeError:
                                        # 如果不是JSON格式，直接使用文本内容
                                        result_text = text_content
                                
                                # 检查状态，如果是 update_progress 或 complete，则退出循环
                                status = output_data.get("status")
                                if status in ["update_progress", "complete"]:
                                    # 当状态为 update_progress 或 complete 时记录结束时间
                                    end_time = time.time()
                                    end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                    self.response_time = end_time - start_time
                                    logger.info(f"响应时间: {self.response_time:.2f}秒")
                                    logger.info(f"结束时间: {end_time_str}")
                                    break
                        except Exception as e:
                            logger.info(f"解析失败: {e}")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            
            return result_text
            
        except requests.exceptions.ConnectTimeout:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"连接超时，耗时: {self.response_time:.2f}秒")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            return "Error: Request Timeout"
            
        except requests.exceptions.ReadTimeout:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"读取超时，耗时: {self.response_time:.2f}秒")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            return "Error: Request Timeout"
            
        except requests.exceptions.Timeout:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"请求超时，耗时: {self.response_time:.2f}秒")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
            return "Error: Request Timeout"
            
        except requests.exceptions.RequestException as e:
            end_time = time.time()
            end_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.response_time = end_time - start_time
            logger.info(f"请求异常: {e}")
            self.data_json_list = key_json_data
            self.start_time_str = start_time_str
            self.end_time_str = end_time_str
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
            return None
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
                            "docName": doc.get("docName", ""),
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
                
                # 跳过空值
                if pd.isna(cell_value) or cell_value == "":
                    continue
                    
                logger.info(f"处理第 {row_index + 1} 行, 列 '{column_name}'...")
                
                # 发送查询请求
                if memory_api.send_query_with_image(query_text=str(cell_value)):
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
    def run_query_only(self, query_text="", handler=None, image_paths=None, modelName=None, modelVersion=None):
        """只运行查询流程，不包含文档注册"""
                # 使用类默认值或传入的参数
        handler = handler or self.DEFAULT_HANDLER
        modelName = modelName or self.DEFAULT_MODEL_NAME
        modelVersion = modelVersion or self.DEFAULT_MODEL_VERSION

        # 重置响应时间
        self.response_time = 0
        if not self.create_session():
            return None
        time.sleep(1)
        session_info = self.get_session_info()
        if not session_info.get("success", False):
            return None

        # 发送查询请求
        if not self.send_query_with_image(query_text, handler, image_paths,modelName,modelVersion):
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
            
            # 注册文档
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
    def _format_time(self, seconds):
        """格式化时间显示为 HH:MM:SS 格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    # def process_main_excel_only(self, cycle=1):
    #     """
    #     仅处理主Excel文件，支持循环执行，但只保存最后一轮结果
    #     """
    #     logger.info(f"开始处理主Excel文件，循环轮数: {cycle}")
        
    #     # 用于存储所有轮次的最终结果（按行索引）
    #     final_results = {}

    #     for cycle_index in range(cycle):
    #         logger.info(f"开始执行第 {cycle_index + 1}/{cycle} 轮循环")
            
    #         try:
    #             df = pd.read_excel(EXCEL_FILE_PATH, sheet_name=0)
    #             logger.info(f"成功加载 Excel，共 {len(df)} 行数据")
    #         except Exception as e:
    #             logger.info(f"读取 Excel 失败: {e}")
    #             return False

    #         # 创建本轮的输出路径（仅用于临时存储或合并）
    #         # if cycle > 1:
    #         #     cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
    #         # else:
    #         #     cycle_output_path = OUTPUT_EXCEL_PATH
    #         # 永远使用 _cycleN 格式，不再生成主文件
    #         cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
    #         # 尝试加载已有结果（如果存在）
    #         try:
    #             df_output = pd.read_excel(cycle_output_path)
    #             logger.info(f"加载现有输出文件，已有 {len(df_output)} 行数据")
    #         except FileNotFoundError:
    #             df_output = df.copy()
    #             df_output['result'] = None
    #             df_output['response_time'] = 0
    #             df_output['data_json_list'] = None 
    #             df_output['start_time'] = None 
    #             df_output['end_time'] = None   
    #             try:
    #                 df_output.to_excel(cycle_output_path, index=False, sheet_name='result')
    #                 logger.info(f"创建新的输出文件: {cycle_output_path}")
    #             except Exception as e:
    #                 logger.info(f"创建输出文件失败: {e}")
    #                 return False
    #         except Exception as e:
    #             logger.info(f"读取输出文件失败: {e}")
    #             return False

    #         start_index = 0
    #         if 'result' in df_output.columns:
    #             for i, result in enumerate(df_output['result']):
    #                 if pd.isna(result) or result is None:
    #                     start_index = i
    #                     break
    #             else:
    #                 start_index = len(df_output)

    #         logger.info(f"从第 {start_index + 1} 行开始处理")

    #         for index in range(start_index, len(df)):
    #             if index >= len(df_output):
    #                 break  

    #             question = str(df.iloc[index]['question']).strip()
    #             image_names = str(df.iloc[index]['pathlist']).strip()
                
    #             if not question or question.lower() in ['nan', 'none', 'null', ''] or question == '1':
    #                 logger.info(f"第 {index + 1} 行跳过：question 为空或者为1")
    #                 df_output.at[index, 'result'] = "Error: Empty question"
    #                 df_output.at[index, 'response_time'] = 0
    #                 df_output.at[index, 'data_json_list'] = None
    #                 df_output.at[index, 'start_time'] = None  
    #                 df_output.at[index, 'end_time'] = None  
    #                 continue

    #             image_paths = []
    #             missing_images = []
    #             if image_names and image_names.lower() not in ['nan', 'none', 'null', '']:
    #                 image_name_list = [name.strip() for name in re.split(r'[,;]+', image_names) if name.strip()]
                    
    #                 for image_name in image_name_list:
    #                     if image_name.lower() in ['nan', 'none', 'null', '']:
    #                         continue
    #                     found_image = None
    #                     for file_path in IMAGE_DIR.rglob(image_name):
    #                         if file_path.is_file():
    #                             found_image = str(file_path)
    #                             break
                        
    #                     if found_image:
    #                         image_paths.append(found_image)
    #                     else:
    #                         missing_images.append(image_name)
                    
    #                 if missing_images:
    #                     logger.info(f"第 {index + 1} 行缺少文件: {missing_images}")
    #                     if not image_paths:
    #                         df_output.at[index, 'result'] = "Error: No valid images found"
    #                         df_output.at[index, 'response_time'] = 0
    #                         df_output.at[index, 'data_json_list'] = None
    #                         df_output.at[index, 'start_time'] = None  
    #                         df_output.at[index, 'end_time'] = None  
    #                         continue
    #             else:
    #                 logger.info("该case不需要附件输入")

    #             logger.info(f"\n=== 正在处理第 {index + 1} 行 ===")
    #             logger.info(f"Question: {question}")
    #             logger.info(f"Pathlist: {image_paths}")

    #             try:
    #                 api = MultimodalAPI()
    #                 result = api.run_query_only(
    #                     query_text=question,
    #                     handler="aaitc-graph-brain",
    #                     image_paths=image_paths if image_paths else None
    #                 )

    #                 response_time = api.get_response_time()
    #                 start_time_str = getattr(api, 'start_time_str', None)
    #                 end_time_str = getattr(api, 'end_time_str', None)
    #                 data_json_content = None
    #                 if hasattr(api, 'data_json_list') and api.data_json_list:
    #                     data_json_content = json.dumps(api.data_json_list, ensure_ascii=False, indent=2)

    #                 # 结果处理逻辑
    #                 if result is not None and isinstance(result, str) and len(result.strip()) > 0 and not result.startswith("Error:"):
    #                     df_output.at[index, 'result'] = result
    #                     df_output.at[index, 'response_time'] = response_time
    #                     df_output.at[index, 'data_json_list'] = data_json_content 
    #                     df_output.at[index, 'start_time'] = start_time_str 
    #                     df_output.at[index, 'end_time'] = end_time_str      
    #                     logger.info(f"第 {index + 1} 行处理成功，结果长度: {len(result)}，响应时间: {response_time:.2f}秒")
    #                 else:
    #                     if result == "Error: Request Timeout":
    #                         df_output.at[index, 'result'] = "Error: Request Timeout"
    #                     elif result is None or result == "" or (isinstance(result, str) and len(result.strip()) == 0):
    #                         df_output.at[index, 'result'] = "Error: Empty response from server"
    #                     else:
    #                         df_output.at[index, 'result'] = result if result else "Error: Empty response from server"
                        
    #                     df_output.at[index, 'response_time'] = response_time
    #                     df_output.at[index, 'data_json_list'] = data_json_content
    #                     df_output.at[index, 'start_time'] = start_time_str
    #                     df_output.at[index, 'end_time'] = end_time_str    
    #                     logger.info(f"第 {index + 1} 行处理完成但响应为空或出错: {result}")

    #             except Exception as e:
    #                 logger.info(f"第 {index + 1} 行处理失败: {e}")
    #                 df_output.at[index, 'result'] = f"Error: {str(e)}"
    #                 df_output.at[index, 'response_time'] = response_time
    #                 df_output.at[index, 'data_json_list'] = None
    #                 df_output.at[index, 'start_time'] = getattr(api, 'start_time_str', None) 
    #                 df_output.at[index, 'end_time'] = getattr(api, 'end_time_str', None) 
    #                 logger.info(f"第 {index + 1} 行错误已记录，继续处理下一条数据")


    #             try:
    #                 df_output.to_excel(cycle_output_path, index=False,sheet_name='result')
    #                 logger.info(f"第 {index + 1} 行结果已保存")
    #             except Exception as e:
    #                 logger.info(f"保存第 {index + 1} 行结果失败: {e}")

    #         logger.info(f"\n第 {cycle_index + 1} 轮循环完成，结果已保存至: {cycle_output_path}")
            
    #     logger.info(f"\n所有 {cycle} 轮循环已完成")
    #     return True
    def process_main_excel_only(self, cycle=1):
        """
        仅处理主Excel文件，支持循环执行，每轮结果保存到独立文件中
        修改点：
        1. 每次循环都从原始输入文件读取数据，确保数据来源最新。
        2. 输出文件名包含轮次和时间戳，避免覆盖历史数据。
        3. 固定从第1行开始处理，全量重新处理所有数据。
        """
        # 为本次执行生成唯一的时间戳
        execution_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"开始处理主Excel文件，循环轮数: {cycle}，执行时间: {execution_timestamp}")
        
        # 保存执行时间戳到实例变量，供外部访问
        self.execution_timestamp = execution_timestamp

        cycle_output_paths = []
        for cycle_index in range(cycle):
            logger.info(f"开始执行第 {cycle_index + 1}/{cycle} 轮循环")
            try:
                # 每次循环都从原始输入文件读取数据
                df = pd.read_excel(EXCEL_FILE_PATH, sheet_name=0)
                logger.info(f"成功加载 Excel，共 {len(df)} 行数据")
            except Exception as e:
                logger.info(f"读取 Excel 失败: {e}")
                return False

            cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_{execution_timestamp}_cycle{cycle_index+1}.xlsx')
            cycle_output_paths.append(cycle_output_path)
            # 初始化输出DataFrame，确保有必要的列
            df_output = df.copy()
            if 'result' not in df_output.columns:
                df_output['result'] = None
            if 'response_time' not in df_output.columns:
                df_output['response_time'] = 0
            if 'data_json_list' not in df_output.columns:
                df_output['data_json_list'] = None
            if 'start_time' not in df_output.columns:
                df_output['start_time'] = None
            if 'end_time' not in df_output.columns:
                df_output['end_time'] = None

            try:
                # 创建新的输出文件
                df_output.to_excel(cycle_output_path, index=False, sheet_name='result')
                logger.info(f"创建新的输出文件: {cycle_output_path}")
            except Exception as e:
                logger.info(f"创建输出文件失败: {e}")
                return False

            # 固定从第1行开始处理
            start_index = 0
            logger.info(f"从第 {start_index + 1} 行开始处理")

            for index in range(start_index, len(df)):
                question = str(df.iloc[index]['question']).strip()
                image_names = str(df.iloc[index]['pathlist']).strip()
                
                if not question or question.lower() in ['nan', 'none', 'null', ''] or question == '1':
                    logger.info(f"第 {index + 1} 行跳过：question 为空或者为1")
                    df_output.at[index, 'result'] = "Error: Empty question"
                    df_output.at[index, 'response_time'] = 0
                    df_output.at[index, 'data_json_list'] = None
                    df_output.at[index, 'start_time'] = None  
                    df_output.at[index, 'end_time'] = None  
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
                            continue
                else:
                    logger.info("该case不需要附件输入")

                logger.info(f"\n=== 正在处理第 {index + 1} 行 ===")
                logger.info(f"Question: {question}")
                logger.info(f"Pathlist: {image_paths}")

                try:
                    api = MultimodalAPI()
                    result = api.run_query_only(
                        query_text=question,
                        handler="aaitc-graph-brain",
                        image_paths=image_paths if image_paths else None
                    )

                    response_time = api.get_response_time()
                    start_time_str = getattr(api, 'start_time_str', None)
                    end_time_str = getattr(api, 'end_time_str', None)
                    data_json_content = None
                    if hasattr(api, 'data_json_list') and api.data_json_list:
                        data_json_content = json.dumps(api.data_json_list, ensure_ascii=False, indent=2)

                    # 结果处理逻辑
                    if result is not None and isinstance(result, str) and len(result.strip()) > 0 and not result.startswith("Error:"):
                        df_output.at[index, 'result'] = result
                        df_output.at[index, 'response_time'] = response_time
                        df_output.at[index, 'data_json_list'] = data_json_content 
                        df_output.at[index, 'start_time'] = start_time_str 
                        df_output.at[index, 'end_time'] = end_time_str      
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
                        logger.info(f"第 {index + 1} 行处理完成但响应为空或出错: {result}")

                except Exception as e:
                    logger.info(f"第 {index + 1} 行处理失败: {e}")
                    df_output.at[index, 'result'] = f"Error: {str(e)}"
                    df_output.at[index, 'response_time'] = response_time
                    df_output.at[index, 'data_json_list'] = None
                    df_output.at[index, 'start_time'] = getattr(api, 'start_time_str', None) 
                    df_output.at[index, 'end_time'] = getattr(api, 'end_time_str', None) 
                    logger.info(f"第 {index + 1} 行错误已记录，继续处理下一条数据")

                try:
                    df_output.to_excel(cycle_output_path, index=False, sheet_name='result')
                    logger.info(f"第 {index + 1} 行结果已保存")
                except Exception as e:
                    logger.info(f"保存第 {index + 1} 行结果失败: {e}")

            logger.info(f"第 {cycle_index + 1} 轮循环完成，结果已保存至: {cycle_output_path}")

        logger.info("所有循环已完成")
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
    global  OUTPUT_EXCEL_PATH, EXCEL_FILE_PATH
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
                        # 在finally块中添加资源数据到结果文件
            if resource_csv_path and os.path.exists(resource_csv_path):
                try:
                    # 如果有输出文件，将资源数据添加到其中
                    if 'OUTPUT_EXCEL_PATH' in globals() and OUTPUT_EXCEL_PATH and os.path.exists(OUTPUT_EXCEL_PATH):
                        add_resource_data_to_results(resource_csv_path, OUTPUT_EXCEL_PATH)
                except Exception as e:
                    logger.error(f"添加资源数据失败: {e}")
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

        resource_csv_path = None
        try:
            monitor, resource_csv_path, start_timestamp = start_resource_monitoring(GPU_TYPE)
            
            # 对于 --process_all 模式，处理所有Excel文件
            if args.process_all:
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
                for excel_file in excel_files:
                    logger.info(f"\n正在处理文件: {excel_file.name}")
                    
                    OUTPUT_EXCEL_PATH = os.path.join(TEST_RESULTS_DIR, f"test_results_{excel_file.stem}_{timestamp}.xlsx")
                    EXCEL_FILE_PATH = str(excel_file)
                    
                    api = MultimodalAPI()
                    
                    # 根据参数执行特定流程
                    success = True
                    if args.process_memory:
                        success = api.process_memory_data_only()
                    
                    if success and args.process_document:
                        success = api.process_document_registration_only()
                        
                    if success and args.process_main:
                        success = api.process_main_excel_only(CYCLE_COUNT)
                    
                    if success:
                        logger.info(f"文件 {excel_file.name} 处理完成")
                    else:
                        logger.info(f"文件 {excel_file.name} 处理失败")

        finally:
            # 在finally块中停止资源监控并添加资源数据
            try:
                if monitor:
                    stop_resource_monitoring(monitor)
                
                # 添加资源数据到结果文件
                if resource_csv_path and os.path.exists(resource_csv_path):
                    # 如果是处理所有Excel文件的情况
                    if args.process_all:
                        for excel_file in excel_files:
                            output_base_path = os.path.join(TEST_RESULTS_DIR, f"test_results_{excel_file.stem}_{timestamp}.xlsx")
                            # 添加资源数据到所有循环文件
                            for cycle_index in range(CYCLE_COUNT):
                                try:
                                    # 使用实例中的execution_timestamp或者全局timestamp
                                    execution_timestamp = timestamp  # 默认使用全局timestamp
                                    if 'api' in locals() and hasattr(api, 'execution_timestamp'):
                                        execution_timestamp = api.execution_timestamp
                                    
                                    cycle_output_path = output_base_path.replace('.xlsx', f'_{execution_timestamp}_cycle{cycle_index+1}.xlsx')
                                    if os.path.exists(cycle_output_path):
                                        add_resource_data_to_results(resource_csv_path, cycle_output_path)
                                        # 在此处调用process_result.py的功能处理cycle_output_path文件
                                        process_single_result_file(cycle_output_path)
                                except Exception as e:
                                    logger.error(f"添加资源数据到 {excel_file.name} 循环{cycle_index+1}失败: {e}")
                                    continue
                    else:
                        # 如果是单独处理的情况
                        for excel_file in excel_files:
                            output_base_path = os.path.join(TEST_RESULTS_DIR, f"test_results_{excel_file.stem}_{timestamp}.xlsx")
                            # 添加资源数据到所有循环文件
                            for cycle_index in range(CYCLE_COUNT):
                                try:
                                    # 使用实例中的execution_timestamp或者全局timestamp
                                    execution_timestamp = timestamp  # 默认使用全局timestamp
                                    if 'api' in locals() and hasattr(api, 'execution_timestamp'):
                                        execution_timestamp = api.execution_timestamp
                                    
                                    cycle_output_path = output_base_path.replace('.xlsx', f'_{execution_timestamp}_cycle{cycle_index+1}.xlsx')
                                    if os.path.exists(cycle_output_path):
                                        add_resource_data_to_results(resource_csv_path, cycle_output_path)
                                        # 在此处调用process_result.py的功能处理cycle_output_path文件
                                        process_single_result_file(cycle_output_path)
                                except Exception as e:
                                    logger.error(f"添加资源数据到 {excel_file.name} 循环{cycle_index+1}失败: {e}")
                                    continue
                            
            except Exception as e:
                logger.error(f"资源清理过程中出现错误: {e}")
                
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

def get_next_two_hour_mark(now=None):
    """
    返回严格大于当前时刻的下一个 2 小时整点（小时为偶数，且分钟秒为 0）。
    示例：
      19:58 -> 20:00
      20:00 -> 22:00
      21:00 -> 22:00
    用法：
      now = datetime.now()
      next_run = get_next_two_hour_mark(now)
      sleep_seconds = max(1, int((next_run - now).total_seconds()))
      time.sleep(sleep_seconds)
    """
    from datetime import datetime, timedelta

    if now is None:
        now = datetime.now()

    # 先对齐到当前小时的整点
    candidate = now.replace(minute=0, second=0, microsecond=0)

    # 保证下一次触发时刻严格晚于当前时刻
    if now >= candidate:
        candidate += timedelta(hours=1)

    # 调整到偶数小时（2 小时整点）
    if candidate.hour % 2 != 0:
        candidate += timedelta(hours=1)

    return candidate
def process_single_result_file(filepath):
    """
    处理单个结果文件，提取TP50值并更新汇总表
    """
    try:
        # 导入process_result.py中的必要函数
        import sys
        import importlib.util
        
        # 获取process_result.py的路径
        process_result_path = os.path.join(os.path.dirname(__file__), "process_result.py")
        
        # 动态导入模块
        spec = importlib.util.spec_from_file_location("process_result", process_result_path)
        process_result_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(process_result_module)
        
        # 调用处理函数
        result = process_result_module.process_result_file(filepath)
        
        if result:
            # 定义汇总表路径
            summary_file = os.path.join(os.path.dirname(filepath), "result.xlsx")
            
            # 调用聚合函数更新汇总表
            process_result_module.aggregate_results([filepath], summary_file)
            
            logger.info(f"已处理文件 {filepath} 并更新汇总表")
        else:
            logger.warning(f"处理文件 {filepath} 时未获得有效结果")
            
    except Exception as e:
        logger.error(f"处理单个结果文件 {filepath} 时出错: {e}")
        import traceback
        traceback.print_exc()
if __name__ == "__main__":
    BASE_URL = "http://127.0.0.1:35253"
    TEST_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testresult")
    os.makedirs(TEST_RESULTS_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description='API Test')
    parser.add_argument('--excel_dir', type=str, default=r'C:\Users\19867\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251112\dataset\Brain+Latency+Case+2025-11-24_brain.xlsx', help='Excel文件目录路径')
    parser.add_argument('--image_dir', type=str, default=r"C:\Users\19867\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251112\images", help='是否需要用到pathlist')
    parser.add_argument('--doc_dir', type=str, default=r"C:\Users\i\Desktop\LRIA_llm_eval\eval\20251114\Quantum_e2e_v20251112\files1114", help='文档目录路径')
    parser.add_argument('--memory_excel', type=str, default=r"C:\Users\i\Desktop\LRIA_llm_eval\eval\20251114\Quantum_e2e_v20251112\Memory_data _v3_1016.xlsx", help='Memory Excel文件路径')
    parser.add_argument('--process_memory', action='store_true',default=False, help='处理Memory数据')
    parser.add_argument('--process_document', action='store_true',default=False, help='处理文档注册')
    parser.add_argument('--process_main', action='store_true',default=True, help='处理主Excel文件')
    parser.add_argument('--process_all', action='store_true', default=False, help='执行完整流程（默认）')
    parser.add_argument('--cycle', type=int, default=1, help='循环轮数，默认为1')
    parser.add_argument('--gpu_type', type=str, default="iGPU", choices=["dGPU", "iGPU", "aGPU"], help='GPU类型')
    parser.add_argument('--service_path', type=str, default=r"C:\Users\i\Desktop\LRIA_llm_eval\version\LATC_Brain_20251031", help='服务目录路径')
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
    
    #2、备份和清理目录===========================================================================================================
    # backup_and_cleanup_directories()
    
    # #3、启动服务=================================================================================================================
    # logger.info("开始启动服务...")
    # if start_services(base_dir, logger):
    #     logger.info("所有服务启动成功，可以继续执行后续流程")
    # else:
    #     logger.error("服务启动失败，无法继续执行后续流程")
    #     exit(1)
    #4、处理流程==================================================================================================================
    # try:
    #     success = run_quantum_e2e_process(args)
    #     if success:
    #         logger.info("所有流程成功完成！")
    #     else:
    #         logger.info("流程执行失败！")
    # except Exception as e:
    #     logger.error(f"主流程执行过程中出现错误: {e}")
    # finally:
    # # 5. 确保服务总是被关闭
    #     try:
    #         logger.info("测试完成, 关闭服务")
    #         stop_services(logger)
    #     except Exception as e:
    #         logger.error(f"关闭服务时出现错误: {e}")

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



    try:

        cycle_count = 1
        while True:
            logger.info(f"开始第 {cycle_count} 轮循环执行")
            try:
                success = run_quantum_e2e_process(args)
                if success:
                    logger.info("所有流程成功完成！")
                else:
                    logger.info("流程执行失败！")
            except Exception as e:
                logger.error(f"主流程执行过程中出现错误: {e}")
                import traceback
                traceback.print_exc()
            
            # ——改为对齐到“下一个 2 小时整点”——
            now = datetime.now()
            next_run = get_next_two_hour_mark(now)
            sleep_seconds = max(1, int((next_run - now).total_seconds()))
            logger.info(
                f"第 {cycle_count} 轮执行完成，将在下一个 2 小时整点再次执行："
                f"{next_run.strftime('%Y-%m-%d %H:%M:%S')}（等待 {sleep_seconds} 秒）"
            )
            cycle_count += 1
            time.sleep(sleep_seconds)
            # time.sleep(5)

    except KeyboardInterrupt:
        logger.info("用户中断程序执行")
    except Exception as e:
        logger.error(f"定时执行过程中出现错误: {e}")