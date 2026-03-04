import pandas as pd
import requests
import json
import time
from pathlib import Path
import os
import numpy as np
from datetime import datetime
import argparse
import logging
from utils.start_stop_services import start_services,stop_services
import shutil

# 配置日志
start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
script_dir = os.path.dirname(os.path.abspath(__file__))
logs_dir = os.path.join(script_dir, "logs")
os.makedirs(logs_dir, exist_ok=True)
log_file_path = os.path.join(logs_dir, f'Bvt_Quantum_api_{start_timestamp}.log')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)
logger = logging.getLogger(__name__)
logger.info("日志系统初始化完成")

# BASE_URL = "http://127.0.0.1:35253"
# doc_directory = r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251031\bvt1031\bvtfiles"
# xlsx_path = r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251031\bvt1031\Pod7_Multimodal_cases_bvtall.xlsx"
# IMAGE_DIR = Path(r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251031\bvt1031\images")


# 解析命令行参数
parser = argparse.ArgumentParser(description='Multimodal API Test Tool')
parser.add_argument('--doc_dir', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_Bvt_20251110\bvtfiles", 
                    help='文档目录路径')
parser.add_argument('--input_path', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_Bvt_20251110\Pod7_Multimodal_cases_bvtall.xlsx", 
                    help='Excel测试用例文件路径')
parser.add_argument('--image_dir', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_Bvt_20251110\images",     
                    help='图片目录路径')
parser.add_argument('--service_path', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\version\LATC_Brain_20251031\Lenovo_Quantum_Core_V20251030_R8_226", help='服务目录路径')

args = parser.parse_args()

doc_directory = args.doc_dir
xlsx_path = args.input_path
IMAGE_DIR = Path(args.image_dir)
base_dir = args.service_path
TEST_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testresult")
os.makedirs(TEST_RESULTS_DIR, exist_ok=True)
timestamp = time.strftime("%Y%m%d_%H%M%S")
TEST_RESULT_PATH = os.path.join(TEST_RESULTS_DIR, f"test_results_{timestamp}.xlsx")

BASE_URL = "http://127.0.0.1:35253"

class MultimodalAPI:
    def __init__(self):
        self.upload_id = None
        self.session_id = None
        self.job_id = None
        self.query_upload_id = None
        self.response_time = 0
    def find_image_paths(self, image_names):
        """根据文件名称查找完整路径"""
        if not image_names or not isinstance(image_names, str):
            return []
        
        image_paths = []
        image_name_list = [name.strip() for name in image_names.replace(';', ',').replace(' ', ',').split(',') if name.strip()]
        
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
                logger.info(f"警告: 未找到图片 {image_name}")
        return image_paths
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
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                self.upload_id = response.text.strip()
                logger.info(f"成功创建会话，upload_id: {self.upload_id}")
                return {
                    "success": True,
                    "upload_id": self.upload_id,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "response_text": response.text
                }
            else:
                logger.info(f"创建会话失败: {response.status_code} - {response.text}")
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
            raw_response_content = ""
            job_id = None
            session_id = None
            
            for line in response.iter_lines():
                if line:
                    raw_response_content += line.decode('utf-8') + "\n"
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
                    "status_code": response.status_code,
                    "raw_response": raw_response_content  # 添加原始响应内容
                }
            else:
                logger.info("未获取到 sessionID")
                return {
                    "success": False,
                    "session_id": None,
                    "job_id": job_id,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "raw_response": raw_response_content,  # 添加原始响应内容
                    "error": "未获取到 sessionID"
                }
        except Exception as e:
            logger.info(f"请求发送失败: {e}")
            return {
                "success": False,
                "status_code": "N/A",
                "error": str(e)
            }

    def get_response_content(self):
        """获取响应内容并返回文本"""
        if not self.query_upload_id:
            logger.info("请先发送查询请求")
            return {
                "success": False,
                "error": "请先发送查询请求"
            }

        url = f"{BASE_URL}/query"
        params = {"fileData": self.query_upload_id}
        # logger.info(params)
        try:
            start_time = time.time()
            start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            logger.info(f"开始时间: {start_time_str}")
            response = requests.get(url, params=params, stream=True,timeout=600)
            # response_time = end_time - start_time
            
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
            end_time = time.time() 
            response_time = end_time - start_time
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
    def register_document(self, file_path):
        """注册文档接口"""
        if not self.upload_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        url = f"{BASE_URL}/upload"
        payload = {
            "command": "document",
            "data": {
                "text": json.dumps({
                    "action": "add",
                    "body": {
                        "doc_paths": file_path,
                        "isTempFile": False
                    }
                })
            }
        }
        logger.info(payload)
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
                response_content_result = self.get_response_content()
                
                # 获取原始响应内容（不经过解析）
                raw_response_content = response_content_result.get("raw_response", "")
                final_response_time = response_content_result.get("response_time", "")
                # logger.info(f"原始响应内容: {raw_response_content}")
                
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": final_response_time,
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
        """获取注册文档列表，持续轮询直到所有文档处理完成"""
        if not self.upload_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        url = f"{BASE_URL}/upload"
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
        logger.info(payload)
        
        # 持续检查文档状态，直到所有文档处理完成
        attempt = 0
        while True:
            attempt += 1
            try:
                start_time = time.time()
                response = requests.post(url, json=payload)
                end_time = time.time()
                response_time = end_time - start_time
                
                if response.status_code == 200:
                    upload_id = response.text.strip()
                    logger.info(f"成功获取文档列表，upload_id: {upload_id}")
                    self.query_upload_id = upload_id  # 更新查询ID
                    
                    response_content_result = self.get_response_content()
                    raw_response_content = response_content_result.get("raw_response", "")
                    result_text = response_content_result.get("result_text", "")
                    final_response_time = response_content_result.get("response_time", "")
                    logger.info(f"第{attempt}次尝试，获取到的result_text: {result_text}")  
                    if result_text:
                        try:
                            # 解析外层JSON
                            outer_data = json.loads(result_text)
                            # 检查是否有job状态信息
                            job_status = outer_data.get("status", "").lower()
                            if job_status in ["running", "processing", "pending"]:
                                logger.info(f"任务仍在处理中(status: {job_status})，第{attempt}次尝试...")
                                time.sleep(2)  # 固定2秒间隔
                                continue
                            
                            # 获取实际的文档列表数据
                            if "data" in outer_data and "text" in outer_data["data"]:
                                inner_text = outer_data["data"]["text"]
                                # 解析内部的文档列表JSON
                                doc_list = json.loads(inner_text)
                                if isinstance(doc_list, list):
                                    if len(doc_list) > 0:
                                        logger.info(f"文档数量: {len(doc_list)}")
                                        has_processing_docs = False
                                        doc_ids = [] 
                                        for i, doc in enumerate(doc_list):
                                            if isinstance(doc, dict):
                                                status = doc.get("status", "UNKNOWN").upper()
                                                logger.info(f"第{i+1}个文档状态: {status}")
                                                doc_id = doc.get("id")
                                                if doc_id is not None:
                                                    doc_ids.append(doc_id)
                                                if status in ["RUNNING", "ADDED", "PROCESSING", "PENDING"]:
                                                    has_processing_docs = True
                                        
                                        if not has_processing_docs:
                                            logger.info("所有文档解析完成")
                                            logger.info(f"文档ID列表: {doc_ids}")
                                            return {
                                                "success": True,
                                                "upload_id": upload_id,
                                                "response_time": final_response_time,
                                                "status_code": response.status_code,
                                                "response_text": response.text,
                                                "response_content": response_content_result,
                                                "raw_response_content": raw_response_content,
                                                "doc_ids": doc_ids  # 返回文档ID列表
                                            }
                                        else:
                                            logger.info(f"仍有文档在处理中，第{attempt}次尝试...")
                                            time.sleep(2)  # 固定2秒间隔
                                            continue
                                    else:
                                        logger.info(f"文档列表为空，任务已完成")
                                        return {
                                            "success": True,
                                            "upload_id": upload_id,
                                            "response_time": final_response_time,
                                            "status_code": response.status_code,
                                            "response_text": response.text,
                                            "response_content": response_content_result,
                                            "raw_response_content": raw_response_content,
                                            "doc_ids": []  # 空列表
                                        }
                                else:
                                    # 如果内部不是列表格式，认为已完成
                                    logger.info(f"内部数据不是文档列表格式，认为任务已完成")
                                    return {
                                        "success": True,
                                        "upload_id": upload_id,
                                        "response_time": final_response_time,
                                        "status_code": response.status_code,
                                        "response_text": response.text,
                                        "response_content": response_content_result,
                                        "raw_response_content": raw_response_content,
                                        "doc_ids": []  # 空列表
                                    }
                            else:
                                # 如果没有预期的data.text结构，认为已完成
                                logger.info(f"返回结果没有预期的data.text结构，认为任务已完成")
                                return {
                                    "success": True,
                                    "upload_id": upload_id,
                                    "response_time": final_response_time,
                                    "status_code": response.status_code,
                                    "response_text": response.text,
                                    "response_content": response_content_result,
                                    "raw_response_content": raw_response_content,
                                    "doc_ids": []  # 空列表
                                }
                        except json.JSONDecodeError as e:
                            # 如果解析JSON失败，认为已完成
                            logger.info(f"JSON解析失败({e})，认为任务已完成")
                            return {
                                "success": True,
                                "upload_id": upload_id,
                                "response_time": final_response_time,
                                "status_code": response.status_code,
                                "response_text": response.text,
                                "response_content": response_content_result,
                                "raw_response_content": raw_response_content,
                                "doc_ids": []  # 空列表
                            }
                    
                    # 如果没有结果文本，认为已完成
                    logger.info(f"没有获取到结果文本，认为任务已完成")
                    return {
                        "success": True,
                        "upload_id": upload_id,
                        "response_time": final_response_time,
                        "status_code": response.status_code,
                        "response_text": response.text,
                        "response_content": response_content_result,
                        "raw_response_content": raw_response_content,
                        "doc_ids": []  # 空列表
                    }
                else:
                    logger.info(f"获取文档列表失败: {response.status_code} - {response.text}")
                    return {
                        "success": False,
                        "upload_id": None,
                        "response_time": response_time,
                        "status_code": response.status_code,
                        "response_text": response.text
                    }
            except Exception as e:
                logger.info(f"请求发送失败: {e}")
                # 出现异常也认为已完成
                return {
                    "success": False,
                    "upload_id": None,
                    "response_time": 0,
                    "error": str(e)
                }

    def delete_register_documnet(self, doc_ids):
        """删除注册文件"""
        if not self.upload_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        if not doc_ids or not isinstance(doc_ids, list):
            logger.info("请提供有效的文档ID列表")
            return {
                "success": False,
                "error": "请提供有效的文档ID列表"
            }

        url = f"{BASE_URL}/upload"
        payload = {
            "command": "document",
            "data": {
                "text": json.dumps({
                    "action": "delete",
                    "body": {
                        "doc_ids": doc_ids
                    }
                })
            }
        }
        logger.info(payload)
        try:
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                upload_id = response.text.strip()
                logger.info(f"成功发送删除请求，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                response_content_result = self.get_response_content()
                raw_response_content = response_content_result.get("raw_response", "")
                final_response_time = response_content_result.get("response_time", "")
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": final_response_time,
                    "status_code": response.status_code,
                    "response_text": response.text,
                    "response_content": response_content_result,
                    "raw_response_content": raw_response_content
                }
            else:
                logger.info(f"删除文档失败: {response.status_code} - {response.text}")
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

    def query(self, prompt='hi', image_names=None,modelName='gpt',modelVersion='gpt-4.1'):
        """ 对话"""
        if not self.session_id:
            logger.info("请先创建会话并获取session_id")
            return {
                "success": False,
                "error": "请先创建会话并获取session_id"
            }

        # 构建基础payload
        payload_data = {
            "text": json.dumps({
                "query": prompt,
                "handler": "aaitc-graph-brain",
                "modelName": modelName,
                "modelVersion": modelVersion
            })
        }
        if image_names:
            image_paths = self.find_image_paths(image_names)
            if image_paths:
                payload_data["uri"] = image_paths
                logger.info(f"文件路径: {image_paths}")

        url = f"{BASE_URL}/upload"
        payload = {
            "command": "query",
            "sessionId": self.session_id,
            "data": payload_data
        }
        logger.info(payload)
        try:
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                upload_id = response.text.strip()
                logger.info(f"成功发送查询请求，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                
                # 获取响应内容
                response_content_result = self.get_response_content()
                raw_response_content = response_content_result.get("raw_response", "")
                final_response_time = response_content_result.get("response_time", "")
                # 检查响应内容是否为空
                result_text = response_content_result.get("result_text", "")
                if not result_text or result_text.strip() == "":
                    logger.info("查询响应内容为空")
                    return {
                        "success": False,
                        "upload_id": upload_id,
                        "response_time": final_response_time,
                        "status_code": response.status_code,
                        "response_text": response.text,
                        "response_content": response_content_result,
                        "raw_response_content": raw_response_content,
                        "error": "查询响应内容为空"
                    }
                
                # 如果响应内容不为空，进一步检查解析后的内容
                try:
                    # 解析响应内容
                    outer_data = json.loads(result_text)
                    if "data" in outer_data and "text" in outer_data["data"]:
                        inner_text = outer_data["data"]["text"]
                        inner_data = json.loads(inner_text)
                        # 检查response字段是否为空
                        response_field = inner_data.get("response", "")
                        if not response_field or response_field.strip() == "":
                            logger.info("查询响应内容为空")
                            return {
                                "success": False,
                                "upload_id": upload_id,
                                "response_time": final_response_time,
                                "status_code": response.status_code,
                                "response_text": response.text,
                                "response_content": response_content_result,
                                "raw_response_content": raw_response_content,
                                "error": "查询响应内容为空"
                            }
                except json.JSONDecodeError:
                    # 如果无法解析JSON，不作特殊处理，继续返回原结果
                    pass
                
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": final_response_time,
                    "status_code": response.status_code,
                    "response_text": response.text,
                    "response_content": response_content_result,
                    "raw_response_content": raw_response_content
                }
            else:
                logger.info(f"查询请求失败: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "upload_id": None,
                    "response_time": final_response_time,
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

    def parse_document(self, doc_ids):
        """立即解析指定文档"""
        if not self.upload_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        if not doc_ids or not isinstance(doc_ids, list):
            logger.info("请提供有效的文档ID列表")
            return {
                "success": False,
                "error": "请提供有效的文档ID列表"
            }

        url = f"{BASE_URL}/upload"
        payload = {
            "command": "document",
            "data": {
                "text": json.dumps({
                    "action": "parse",
                    "body": {
                        "doc_ids": doc_ids
                    }
                })
            }
        }
        logger.info(payload)
        
        try:
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                upload_id = response.text.strip()
                logger.info(f"成功发送解析请求，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                
                # 获取响应内容
                response_content_result = self.get_response_content()
                raw_response_content = response_content_result.get("raw_response", "")
                final_response_time = response_content_result.get("response_time", "")
                
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": final_response_time,
                    "status_code": response.status_code,
                    "response_text": response.text,
                    "response_content": response_content_result,
                    "raw_response_content": raw_response_content
                }
            else:
                logger.info(f"发送解析请求失败: {response.status_code} - {response.text}")
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

    def add_and_parse_document(self, file_paths):
        """上传并立即解析文档"""
        if not self.upload_id:
            logger.info("请先创建会话")
            return {
                "success": False,
                "error": "请先创建会话"
            }

        if not file_paths:
            logger.info("请提供有效的文件路径列表")
            return {
                "success": False,
                "error": "请提供有效的文件路径列表"
            }

        # 确保file_paths是列表格式
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        
        url = f"{BASE_URL}/upload"
        payload = {
            "command": "document",
            "data": {
                "text": json.dumps({
                    "action": "add_and_parse",
                    "body": {
                        "doc_paths": file_paths
                    }
                })
            }
        }
        logger.info(payload)
        
        try:
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                upload_id = response.text.strip()
                logger.info(f"成功上传并解析文档，upload_id: {upload_id}")
                self.query_upload_id = upload_id  # 更新查询ID
                
                # 获取响应内容
                response_content_result = self.get_response_content()
                raw_response_content = response_content_result.get("raw_response", "")
                final_response_time = response_content_result.get("response_time", "")
                
                # 检查响应内容是否为空
                result_text = response_content_result.get("result_text", "")
                if not result_text or result_text.strip() == "":
                    logger.info("上传并解析响应内容为空")
                    return {
                        "success": False,
                        "upload_id": upload_id,
                        "response_time": final_response_time,
                        "status_code": response.status_code,
                        "response_text": response.text,
                        "response_content": response_content_result,
                        "raw_response_content": raw_response_content,
                        "error": "上传并解析响应内容为空"
                    }
                
                return {
                    "success": True,
                    "upload_id": upload_id,
                    "response_time": final_response_time,
                    "status_code": response.status_code,
                    "response_text": response.text,
                    "response_content": response_content_result,
                    "raw_response_content": raw_response_content
                }
            else:
                logger.info(f"上传并解析文档失败: {response.status_code} - {response.text}")
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

def save_test_results_to_excel(test_results):
    """将测试结果保存到Excel文件"""
    df = pd.DataFrame(test_results)
    
    try:
        df.to_excel(TEST_RESULT_PATH, index=False)
        logger.info(f"\n测试结果已保存到: {TEST_RESULT_PATH}")
        return True
    except Exception as e:
        logger.info(f"保存测试结果失败: {e}")
        return False
# ==================== 新增：逐条写入 Excel 的函数 ====================
def write_result_to_excel(result_dict):
    """将单条测试结果写入Excel文件"""
    try:
        from openpyxl import load_workbook
        if os.path.exists(TEST_RESULT_PATH):
            wb = load_workbook(TEST_RESULT_PATH)
            ws = wb.active
        else:
            wb = None
            ws = None

        df = pd.DataFrame([result_dict])
        if ws is None:
            df.to_excel(TEST_RESULT_PATH, index=False)
        else:
            for row in df.values:
                ws.append(row.tolist())
            wb.save(TEST_RESULT_PATH)
            wb.close()
        logger.info(f"✅ 已写入测试结果: {result_dict['接口名称']}")
    except Exception as e:
        logger.info(f"❌ 写入Excel失败: {e}")
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

# ==================== 主函数修改 ====================
if __name__ == "__main__":
    # 备份和清理目录
    backup_and_cleanup_directories()
    
    logger.info("开始启动服务...")
    # 启动服务
    if start_services(base_dir, logger):
        logger.info("所有服务启动成功，可以继续执行后续流程")
    else:
        logger.error("服务启动失败，无法继续执行后续流程")
        exit(1)

    logger.info("开始API接口自动化测试...")
    test_results = []  # 用于临时存储（可选）

    def add_test_result(name, description, success, response_time, status_code="N/A", content="", details=""):
        # 强制转换为浮点数，避免 None 或非数字
        rt = float(response_time) if response_time is not None and isinstance(response_time, (int, float)) else 0.0
        
        logger.info(f"DEBUG: 添加测试结果 - 接口: {name}, 响应时间: {rt:.2f}")

        result = {
            "接口名称": name,
            "接口描述": description,
            "测试时间": time.strftime("%Y-%m-%d %H:%M:%S"),
            "测试结果": "pass" if success else ("fail" if success is not None else "跳过"),
            "响应时间(秒)": f"{rt:.2f}",  # 注意这里是字符串格式化
            "状态码": status_code,
            "返回内容": content,
            "详细信息": details
        }
        test_results.append(result)
        write_result_to_excel(result)  # 立即写入

    # 测试用例1: create_session
    logger.info("=== 测试 create_session 接口 ===")
    api = MultimodalAPI()
    create_result = api.create_session()
    add_test_result(
        "create_session",
        "创建一个新的会话",
        create_result["success"],
        create_result.get("response_time"),
        create_result.get("status_code", "N/A"),
        create_result.get("response_text", create_result.get("error", "")),
        f"upload_id: {create_result.get('upload_id', 'N/A')}"
    )

    if not create_result["success"]:
        for name, desc in [
            ("get_session_info", "获取会话信息，提取sessionID和jobId"),
            ("register_document", "注册文档到会话"),
            ("get_register_document", "查询注册文档"),
            ("delete_register_documnet", "删除注册文件")
        ]:
            add_test_result(name, desc, None, content="由于create_session失败，跳过此测试")
    else:
        # 继续其他测试...
        # get_session_info
        logger.info("\n=== 测试 get_session_info 接口 ===")
        session_result = api.get_session_info()
        add_test_result(
            "get_session_info",
            "获取会话信息，提取sessionID和jobId",
            session_result["success"],
            session_result.get("response_time", 0),
            session_result.get("status_code", "N/A"),
            session_result.get("raw_response", str(session_result)),
            f"session_id: {session_result.get('session_id', 'N/A')}, job_id: {session_result.get('job_id', 'N/A')}"
        )

        # register_document
        logger.info("\n=== 测试 register_document 接口 ===")
        doc_file_list = []
        if os.path.exists(doc_directory):
            for root, dirs, files in os.walk(doc_directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    doc_file_list.append(file_path)
            logger.info(f"找到 {len(doc_file_list)} 个文档文件")
        else:
            doc_file_list = [r"C:\Users\yangl\Desktop\912\16.docx"]

        doc_result = api.register_document(doc_file_list)
        response_content_raw = ""
        if "response_content" in doc_result:
            response_content_result = doc_result["response_content"]
            if "raw_response" in response_content_result:
                response_content_raw = response_content_result["raw_response"]

        add_test_result(
            "register_document",
            "注册文档到会话",
            doc_result["success"],
            doc_result.get("response_time", 0),
            doc_result.get("status_code", "N/A"),
            response_content_raw,
            f"upload_id: {doc_result.get('upload_id', 'N/A')}"
        )

        # get_register_document
        logger.info("\n=== 测试 get_register_document 接口 ===")
        get_registe_result = api.get_register_document()
        response_content_raw = ""
        if "response_content" in get_registe_result:
            response_content_result = get_registe_result["response_content"]
            if "raw_response" in response_content_result:
                response_content_raw = response_content_result["raw_response"]

        add_test_result(
            "get_register_document",
            "查询注册文档",
            get_registe_result["success"],
            get_registe_result.get("response_time", 0),
            get_registe_result.get("status_code", "N/A"),
            response_content_raw,
            f"upload_id: {get_registe_result.get('upload_id', 'N/A')}, doc_ids: {get_registe_result.get('doc_ids', [])}"
        )

        # add_and_parse_document
        logger.info("\n=== 测试 add_and_parse_document 接口 ===")
        api_add_parse = MultimodalAPI()
        create_result_add_parse = api_add_parse.create_session()

        if create_result_add_parse["success"]:
            session_result_add_parse = api_add_parse.get_session_info()
            if session_result_add_parse["success"]:
                files_to_add_parse = []
                if os.path.exists(doc_directory):
                    for root, dirs, files in os.walk(doc_directory):  # ✅ 修复此处
                        for file in files[:2]:
                            file_path = os.path.join(root, file)
                            files_to_add_parse.append(file_path)
                            if len(files_to_add_parse) >= 2:
                                break
                        if len(files_to_add_parse) >= 2:
                            break
                logger.info(f"准备上传并解析 {len(files_to_add_parse)} 个文件: {files_to_add_parse}")
                add_parse_result = api_add_parse.add_and_parse_document(files_to_add_parse)

                response_content_raw = ""
                if "response_content" in add_parse_result:
                    response_content_result = add_parse_result["response_content"]
                    if "raw_response" in response_content_result:
                        response_content_raw = response_content_result["raw_response"]

                add_test_result(
                    "add_and_parse_document",
                    "上传并立即解析文档",
                    add_parse_result["success"],
                    add_parse_result.get("response_time", 0),
                    add_parse_result.get("status_code", "N/A"),
                    response_content_raw,
                    f"upload_id: {add_parse_result.get('upload_id', 'N/A')}"
                )

                # parse_document
                if add_parse_result["success"]:
                    logger.info("\n=== 测试 parse_document 接口 ===")
                    registered_docs_result = api_add_parse.get_register_document()
                    if registered_docs_result["success"] and registered_docs_result.get("doc_ids"):
                        doc_ids_to_parse = registered_docs_result["doc_ids"][:2]
                        parse_result = api_add_parse.parse_document(doc_ids_to_parse)

                        response_content_raw = ""
                        if "response_content" in parse_result:
                            response_content_result = parse_result["response_content"]
                            if "raw_response" in response_content_result:
                                response_content_raw = response_content_result["raw_response"]

                        add_test_result(
                            "parse_document",
                            "立即解析指定文档",
                            parse_result["success"],
                            parse_result.get("response_time", 0),
                            parse_result.get("status_code", "N/A"),
                            response_content_raw,
                            f"upload_id: {parse_result.get('upload_id', 'N/A')}"
                        )
                    else:
                        add_test_result(
                            "parse_document",
                            "立即解析指定文档",
                            None,
                            content="未能获取文档ID列表，跳过此测试"
                        )
            else:
                add_test_result(
                    "add_and_parse_document",
                    "上传并立即解析文档",
                    None,
                    content="由于获取会话信息失败，跳过此测试"
                )
        else:
            add_test_result(
                "add_and_parse_document",
                "上传并立即解析文档",
                None,
                content="由于创建会话失败，跳过此测试"
            )

        # query 接口
        logger.info("\n=== 测试 query 接口 ===")
        api_query = MultimodalAPI()
        new_create_result = api_query.create_session()

        if new_create_result["success"]:
            new_session_result = api_query.get_session_info()
            if new_session_result["success"]:
                query_result = api_query.query("hi")
                response_content_raw = ""
                if "response_content" in query_result:
                    response_content_result = query_result["response_content"]
                    if "raw_response" in response_content_result:
                        response_content_raw = response_content_result["raw_response"]
                error_msg = query_result.get("error", "")
                test_success = query_result["success"]
                additional_info = ""
                if not test_success and "查询响应内容为空" in error_msg:
                    additional_info = "响应内容为空"

                add_test_result(
                    "query",
                    "对话接口",
                    test_success,
                    query_result.get("response_time", 0),
                    query_result.get("status_code", "N/A"),
                    response_content_raw,
                    f"upload_id: {query_result.get('upload_id', 'N/A')}, {additional_info}"
                )
            else:
                add_test_result(
                    "query",
                    "对话查询接口",
                    None,
                    content="由于获取新会话信息失败，跳过此测试"
                )
        else:
            add_test_result(
                "query",
                "对话查询接口",
                None,
                content="由于创建新会话失败，跳过此测试"
            )

        # 批量查询
        logger.info("\n==================================bvtcaserun======================================")
        if os.path.exists(xlsx_path):
            try:
                df = pd.read_excel(xlsx_path)
                for index, row in df.iterrows():
                    query_text = row.get('question', '')
                    image_names = row.get('pathlist', '')

                    if query_text and isinstance(query_text, str):
                        logger.info(f"\n执行第 {index+1} 条查询: {query_text}")
                        api_query = MultimodalAPI()
                        new_create_result = api_query.create_session()

                        if new_create_result["success"]:
                            new_session_result = api_query.get_session_info()
                            if new_session_result["success"]:
                                query_result = api_query.query(query_text, image_names)
                                response_content_raw = ""
                                if "response_content" in query_result:
                                    response_content_result = query_result["response_content"]
                                    if "raw_response" in response_content_result:
                                        response_content_raw = response_content_result["raw_response"]
                                error_msg = query_result.get("error", "")
                                test_success = query_result["success"]
                                additional_info = ""
                                if not test_success and "查询响应内容为空" in error_msg:
                                    additional_info = "响应内容为空"

                                add_test_result(
                                    f"query_batch_{index+1}",
                                    f"{query_text}",
                                    test_success,
                                    query_result.get("response_time", 0),
                                    query_result.get("status_code", "N/A"),
                                    response_content_raw,
                                    f"upload_id: {query_result.get('upload_id', 'N/A')}, {additional_info}"
                                )
                            else:
                                add_test_result(
                                    f"query_batch_{index+1}",
                                    f"{query_text}",
                                    None,
                                    content="由于获取新会话信息失败，跳过此测试"
                                )
                        else:
                            add_test_result(
                                f"query_batch_{index+1}",
                                f"批量查询: {query_text}",
                                None,
                                content="由于创建新会话失败，跳过此测试"
                            )
                    else:
                        logger.info(f"第 {index+1} 行查询为空或无效，跳过")
                        add_test_result(
                            f"query_batch_{index+1}",
                            f"批量查询: 空查询",
                            None,
                            content="查询内容为空或无效"
                        )
            except Exception as e:
                logger.info(f"读取或处理查询文件时出错: {e}")
                add_test_result(
                    "query_batch",
                    "批量查询",
                    None,
                    content=f"读取查询文件失败: {str(e)}"
                )
        else:
            logger.info(f"查询文件不存在: {xlsx_path}")
            add_test_result(
                "query_batch",
                "批量查询",
                None,
                content=f"查询文件不存在: {xlsx_path}"
            )

        # delete_register_documnet
        logger.info("\n=== 测试 delete_register_documnet 接口 ===")
        doc_ids_to_delete = get_registe_result.get("doc_ids", [])
        delete_result = api.delete_register_documnet(doc_ids_to_delete)

        response_content_raw = ""
        if "response_content" in delete_result:
            response_content_result = delete_result["response_content"]
            if "raw_response" in response_content_result:
                response_content_raw = response_content_result["raw_response"]

        add_test_result(
            "delete_register_documnet",
            "删除注册文件",
            delete_result["success"],
            delete_result.get("response_time", 0),
            delete_result.get("status_code", "N/A"),
            response_content_raw,
            f"upload_id: {delete_result.get('upload_id', 'N/A')}"
        )
        # ==================== 验证删除是否成功 ====================
        logger.info("\n=== 验证删除是否成功 ===")
        if doc_ids_to_delete:
            # 再次获取注册文档列表
            verify_result = api.get_register_document()
            
            if verify_result["success"]:
                current_doc_ids = verify_result.get("doc_ids", [])
                
                # 检查是否所有要删除的 doc_id 都不在当前列表中
                remaining_deleted_ids = [doc_id for doc_id in doc_ids_to_delete if doc_id in current_doc_ids]
                
                if len(remaining_deleted_ids) == 0:
                    logger.info(f"✅ 所有文档均已成功删除: {doc_ids_to_delete}")
                    add_test_result(
                        "verify_delete",
                        "验证文档是否已删除",
                        True,
                        verify_result.get("response_time", 0),
                        verify_result.get("status_code", "N/A"),
                        "",
                        f"删除的文档ID: {doc_ids_to_delete}, 当前文档ID: {current_doc_ids}"
                    )
                else:
                    logger.info(f"❌ 删除失败！以下文档仍在列表中: {remaining_deleted_ids}")
                    add_test_result(
                        "verify_delete",
                        "验证文档是否已删除",
                        False,
                        verify_result.get("response_time", 0),
                        verify_result.get("status_code", "N/A"),
                        "",
                        f"未删除成功的文档ID: {remaining_deleted_ids}, 当前文档ID: {current_doc_ids}"
                    )
            else:
                logger.info("❌ 获取文档列表失败，无法验证删除结果")
                add_test_result(
                    "verify_delete",
                    "验证文档是否已删除",
                    None,
                    content="获取文档列表失败，无法验证删除结果"
                )
        else:
            logger.info("⚠️ 无文档可删除，跳过验证")
            add_test_result(
                "verify_delete",
                "验证文档是否已删除",
                None,
                content="无文档可删除，跳过验证"
            )

    # 最终统计（可选）
    logger.info("\n=== 测试结果摘要 ===")
    passed_count = sum(1 for result in test_results if result["测试结果"] == "pass")
    failed_count = sum(1 for result in test_results if result["测试结果"] == "fail")
    skipped_count = sum(1 for result in test_results if result["测试结果"] == "跳过")

    logger.info(f"总测试用例数: {len(test_results)}")
    logger.info(f"pass: {passed_count}")
    logger.info(f"fail: {failed_count}")
    logger.info(f"跳过: {skipped_count}")
    logger.info("测试完成,关闭服务")
    stop_services(logger)                                 