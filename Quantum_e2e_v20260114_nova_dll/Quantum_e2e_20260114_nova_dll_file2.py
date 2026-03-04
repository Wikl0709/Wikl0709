import pandas as pd
import json
from datetime import datetime
import time
from pathlib import Path
import os
import argparse
import openpyxl
import logging
from loguru import logger
import re
import utils.monitor_util as memory
from utils.start_stop_services import start_services,stop_services
import atexit
import sys
import random
import shutil
from datetime import datetime, timedelta
import Auto_Judge
import mimetypes
import subprocess
import ctypes
from ctypes import CFUNCTYPE, c_int, c_long, c_char_p, POINTER, Structure, c_void_p
import queue
import threading
import subprocess
import sys
import close_openwifi
sys.stdout.reconfigure(encoding='utf-8')

_MEMORY_PROCESSED_GLOBAL = False
start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
script_dir = os.path.dirname(os.path.abspath(__file__))
logs_dir = os.path.join(script_dir, "logs")
os.makedirs(logs_dir, exist_ok=True)
# log_file_path = os.path.join(logs_dir, f'Quantum_api_{start_timestamp}.log')
resource_csv_path = os.path.join(logs_dir, f'resource_monitor_{start_timestamp}.csv')

# 在文件开头添加
def setup_logging(output_dir):
    """设置 loguru 日志系统"""
    # 移除默认 handler
    logger.remove()
    
    # 创建日志目录
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = logs_dir / f'Quantum_api_{start_timestamp}.log'
    
    # 控制台输出（彩色）
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>[{file}:{line}]</cyan> | "
               "<cyan>[{function}]</cyan> | "
               "<level>{message}</level>",
        level="DEBUG"
    )
    
    # 文件输出
    logger.add(
        log_file_path,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | [{file}:{line}] - [{function}] - {message}",
        level="DEBUG",
        encoding="utf-8",
        rotation="500 MB",
        retention="30 days",
        compression="zip"
    )
    
    logger.info("日志系统初始化完成")
    logger.info(f"输出目录: {output_dir}")
    return logger

# 初始化日志系统
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
setup_logging(script_dir)

# ------------------------------
# 量子客户端管理器
# ------------------------------
class QuantumClientManager:
    def __init__(self):
        self.client_handle = None
        self.status_callback = None
        self.result_callback = None
        self.result_queue = queue.Queue()
        self.connection_event = threading.Event()
        self.connected = False
        self.error = None
        self.lock = threading.Lock()
        self.pending_jobs = {}  # 存储待处理的任务
        self.job_to_api_map = {}  # 添加映射来跟踪 job_id 到 API 实例的关系
    # ========================================
    # 连接状态处理回调
    # ========================================
    def on_connection_status(self, status):
        """Handle connection status updates"""
        status_names = {
            0: "Unknown",
            1: "Connected",
            2: "Disconnected",
            3: "Error",
            4: "Died"
        }
        logger.info(f"Connection status: {status_names.get(status, f'Unknown({status})')}")
        
        if status == 1:  # Connected
            self.connected = True
            self.connection_event.set()
        elif status in [2, 3, 4]:  # Disconnected, Error, Died
            self.connected = False
            self.connection_event.clear()
            if status == 3 or status == 4:
                self.error = f"Connection error (status: {status})"
    # 修改 on_result 方法中的token计数逻辑部分
    # ========================================
    # 结果处理回调
    # ========================================
    def on_result(self, output_data_ptr):
        """Handle command results"""
        if not output_data_ptr:
            return
        
        try:
            job_id = quantum_output_get_job_id(output_data_ptr)
            status_ptr = quantum_output_get_status(output_data_ptr)
            status = ctypes.string_at(status_ptr).decode('utf-8')
            
            data_ptr = quantum_output_get_data(output_data_ptr)
            result_data = None
            
            if data_ptr:
                text_ptr = quantum_data_get_text(data_ptr)
                if text_ptr:
                    text = ctypes.string_at(text_ptr).decode('utf-8')
                    # logger.info(f"Response data: {text}")
                    try:
                        result_data = json.loads(text)
                        
                        # 检测首字时间（first_word_time）
                        # 如果是text类型且response不为空，则记录为首字时间
                        if isinstance(result_data, dict):
                            # 检查文本类型
                            text_type = result_data.get("type")
                            response_content = result_data.get("response")
                            
                            if job_id in self.job_to_api_map:
                                api_instance = self.job_to_api_map[job_id]
                                
                                # >>> 修改：模式识别逻辑 <<<
                                # 在in_progress响应中持续检测模式，确保最后识别的是Local Brain（如果存在）
                                if status == "in_progress":
                                    # 检查是否是handler类型响应
                                    if text_type == "handler":
                                        handler_name = response_content
                                        # 检查是否为Local Brain模式（优先级最高）
                                        if isinstance(handler_name, str) and "Local Brain" in handler_name:
                                            old_mode = api_instance.current_mode
                                            api_instance.current_mode = "local_brain"
                                            if old_mode != "local_brain":
                                                logger.info("检测到 Local Brain 模式，更新处理模式")
                                        elif handler_name == "Azure Agent" and api_instance.current_mode is None:
                                            # 只有在还没有确定模式时才设置为Azure Agent
                                            api_instance.current_mode = "azure_agent"
                                            logger.info("检测到 Azure Agent 模式")
                                        elif api_instance.current_mode is None:
                                            # 默认为Local Brain模式
                                            api_instance.current_mode = "local_brain"
                                            logger.info("默认设置为 Local Brain 模式")
                                    
                                    # 如果没有明确的handler类型，但包含特定关键字
                                    elif isinstance(response_content, str):
                                        if "Local Brain" in response_content:
                                            old_mode = api_instance.current_mode
                                            api_instance.current_mode = "local_brain"
                                            if old_mode != "local_brain":
                                                logger.info("检测到 Local Brain 模式，更新处理模式")
                                        elif "Azure Agent" in response_content and api_instance.current_mode is None:
                                            # 只有在还没有确定模式时才设置为Azure Agent
                                            api_instance.current_mode = "azure_agent"
                                            logger.info("检测到 Azure Agent 模式")
                                        elif api_instance.current_mode is None:
                                            # 默认为Local Brain模式
                                            api_instance.current_mode = "local_brain"
                                            logger.info("默认设置为 Local Brain 模式")
                                
                                # 确保模式已识别（在任务完成时再次确认）
                                if api_instance.current_mode is None and status == "complete":
                                    logger.warning("无法识别模式，使用默认模式: local_brain")
                                    api_instance.current_mode = "local_brain"
                                
                                # 记录首字时间 - 根据识别到的模式决定
                                if (not hasattr(api_instance, 'first_word_time') or api_instance.first_word_time is None):
                                    # 优先检查tool类型
                                    if text_type == "tool":
                                        api_instance.first_word_time = datetime.now()
                                        first_word_time_str = api_instance.first_word_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                        logger.info(f"首字时间 (tool类型): {first_word_time_str}")
                                    # 根据模式决定是否记录text类型
                                    elif text_type == "text":
                                        if api_instance.current_mode == "azure_agent":
                                            # Azure Agent模式：第一个text响应即记录
                                            api_instance.first_word_time = datetime.now()
                                            first_word_time_str = api_instance.first_word_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                            logger.info(f"首字时间 (text类型): {first_word_time_str}")
                                        elif api_instance.current_mode == "local_brain":
                                            # Local Brain模式：第二个text响应才记录
                                            # 注意：这里的判断基于text_response_count的值
                                            if api_instance.text_response_count >= 1:  # 已经有一个text响应了
                                                api_instance.first_word_time = datetime.now()
                                                first_word_time_str = api_instance.first_word_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                                logger.info(f"首字时间 (text类型): {first_word_time_str}")

                                # 只有在是text类型时才处理文本内容
                                if text_type == "text":
                                    # 记录第一个text响应时间（始终记录）
                                    if api_instance.text_response_count == 0:
                                        api_instance.first_text_response_time = datetime.now()
                                        first_text_response_time_str = api_instance.first_text_response_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                        logger.info(f"第一个text响应时间: {first_text_response_time_str}")
                                    
                                    # 增加text响应计数
                                    api_instance.text_response_count += 1
                                    
                                    # 根据模式决定token计数起始点
                                    if status == "in_progress":
                                        token_count_start = 1  # Azure Agent模式从第一个text开始
                                        if api_instance.current_mode == "local_brain":
                                            token_count_start = 2  # Local Brain模式从第二个text开始
                                        
                                        # 只有当text响应计数达到起始点时才开始计数token
                                        if api_instance.text_response_count >= token_count_start:
                                            api_instance.token_count += 1
                                            logger.debug(f"接收到 in_progress 且类型为text的消息，当前token计数: {api_instance.token_count}")

                    except json.JSONDecodeError:
                        result_data = text
                    quantum_free_string(text_ptr)
                quantum_free_ref(data_ptr)
            
            quantum_free_string(status_ptr)
            quantum_free_ref(output_data_ptr)
            
            # 构造要存储的结果对象
            result_entry = {
                'job_id': job_id,
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'data': result_data
            }
            
            # 如果存在对应的 API 实例，将结果添加到其 data_json_list 中
            if job_id in self.job_to_api_map:
                api_instance = self.job_to_api_map[job_id]
                api_instance.data_json_list.append(result_entry)
                logger.info(f"Got result for job {job_id}: {result_entry}")
                
                # 如果任务完成，计算性能指标
                if status == "complete":
                    # 记录结束时间
                    api_instance.end_time_dt = datetime.now()
                    api_instance.end_time_str = api_instance.end_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    
                    # 计算响应时间
                    if api_instance.start_time_dt:
                        api_instance.response_time = (api_instance.end_time_dt - api_instance.start_time_dt).total_seconds()
                        logger.info(f"响应时间: {api_instance.response_time:.2f}秒")
                        logger.info(f"结束时间: {api_instance.end_time_str}")
                    
                    # 计算性能指标
                    if (hasattr(api_instance, 'first_word_time') and api_instance.first_word_time and 
                        hasattr(api_instance, 'end_time_dt') and api_instance.end_time_dt):
                        # 计算TTFT
                        ttft = (api_instance.first_word_time - api_instance.start_time_dt).total_seconds()
                        api_instance.ttft_seconds = ttft
                        logger.info(f"TTFT (Time To First Token): {ttft:.3f}秒")
                        
                        # 计算生成速度
                        if api_instance.token_count > 0 and ttft > 0:
                            gen_time = (api_instance.end_time_dt - api_instance.first_word_time).total_seconds()
                            generation_speed = api_instance.token_count / gen_time if gen_time > 0 else 0
                            api_instance.generation_speed = generation_speed
                            
                            logger.info(f"性能指标:")
                            logger.info(f"  - 首字时间: {api_instance.first_word_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                            logger.info(f"  - TTFT (Time To First Token): {ttft:.3f}秒")
                            logger.info(f"  - Token数量: {api_instance.token_count}")
                            logger.info(f"  - 生成速度: {generation_speed:.2f} tokens/秒")
                            logger.info(f"  - 生成时间: {gen_time:.3f}秒")
            
            # 将结果放入队列并通知等待的线程
            self.result_queue.put(result_entry)
            
            # 只有在任务完成时才移除映射关系
            if job_id in self.pending_jobs and status == "complete":
                event = self.pending_jobs.pop(job_id)
                event.set()
                
                # 只有在任务完成时才移除 job_id 到 API 实例的映射
                if job_id in self.job_to_api_map:
                    del self.job_to_api_map[job_id]
                    
        except Exception as e:
            logger.error(f"Error processing result: {e}")
            if output_data_ptr:
                quantum_free_ref(output_data_ptr)
            self.result_queue.put({
                'error': str(e)
            })
    # ========================================
    # 客户端初始化
    # ========================================
    def initialize(self):
        """Initialize and connect the quantum client"""
        with self.lock:
            if self.client_handle is not None:
                return True
            
            try:
                logger.info("quantum_get_client start")
                self.client_handle = quantum_get_client()
                logger.info("quantum_get_client end")
                
                if self.client_handle == 0:
                    raise Exception("Client initialization failed")
                
                logger.info("Client initialized successfully")
                
                # Set up callbacks
                self.status_callback = ConnectionStatusCallback(self.on_connection_status)
                self.result_callback = ResultCallback(self.on_result)
                
                # Connect to the service
                logger.info("quantum_connect start")
                result = quantum_connect(
                    self.client_handle,
                    self.status_callback,
                    self.result_callback,
                    None  # No config JSON
                )
                logger.info("quantum_connect end")
                
                if result != 0:
                    error_code = ctypes.get_last_error()
                    raise Exception(f"Failed to connect with error code: {result}, last error: {error_code}")
                
                # Wait for connection confirmation
                if not self.connection_event.wait(timeout=10.0):
                    raise Exception("Timeout waiting for connection")
                    
                if self.error:
                    raise Exception(self.error)
                    
                logger.info("Connected to quantum service")
                return True
            except Exception as e:
                self.error = str(e)
                logger.error(f"Initialization error: {e}")
                self.cleanup()
                return False
    # ========================================
    # 发送模型调用命令
    # ========================================
    def send_model_call(self, payload, command_type=b"", api_instance=None, blobs=None):
        """
        Send a model call command to the quantum SDK
        
        Args:
            payload: The payload data to send
            command_type: Type of command (b"session", b"document", b"query", b"model_call")
            api_instance: The MultimodalAPI instance associated with this call
            blobs: List of binary blobs, each containing 'mime' and 'data' fields
        """
        with self.lock:
            if not self.connected or self.client_handle is None:
                if not self.initialize():
                    return None
            
            logger.info(f"Sending {command_type.decode()} call with payload: {json.dumps(payload)}")
            
            # Create JSON payload
            json_payload = json.dumps(payload).encode('utf-8')
            
            # 如果没有附件，直接使用空数组版本
            if not blobs or len(blobs) == 0:
                empty_array = (ctypes.c_void_p * 0)()
                data_container = quantum_create_data_container(
                    json_payload,
                    empty_array,
                    0,
                    None
                )
            else:
                # 有附件的情况 - 处理所有附件
                blob_ptrs = []
                
                for blob in blobs:
                    mime = blob.get("mime", "application/octet-stream")
                    data = blob.get("data", [])
                    
                    if not data:
                        logger.warning(f"Skipping empty blob with mime: {mime}")
                        continue
                    
                    try:
                        # 创建一个临时的内存块
                        data_bytes = bytes(data)
                        # 使用 Python 的内存管理
                        data_ptr = ctypes.cast(
                            (ctypes.c_ubyte * len(data_bytes))(*data_bytes),
                            ctypes.c_void_p
                        )
                        
                        # Create blob data pointer
                        blob_ptr = quantum_create_blob_data(
                            mime.encode('utf-8'),
                            data_ptr,
                            len(data_bytes)
                        )
                        
                        if blob_ptr:
                            blob_ptrs.append(blob_ptr)
                            logger.info(f"Successfully created blob: mime={mime}, size={len(data_bytes)} bytes")
                        else:
                            logger.error(f"Failed to create blob data for mime: {mime}")
                            
                    except Exception as e:
                        logger.error(f"Error creating blob data for mime {mime}: {e}")
                        continue
                
                # 创建附件数组
                if blob_ptrs:
                    # 创建适当大小的数组
                    blob_array = (ctypes.c_void_p * len(blob_ptrs))()
                    for i, ptr in enumerate(blob_ptrs):
                        blob_array[i] = ptr
                    
                    data_container = quantum_create_data_container(
                        json_payload,
                        blob_array,
                        len(blob_ptrs),
                        None
                    )
                    logger.info(f"Created data container with {len(blob_ptrs)} blobs")
                else:
                    # 如果所有附件都处理失败，使用空数组
                    empty_array = (ctypes.c_void_p * 0)()
                    data_container = quantum_create_data_container(
                        json_payload,
                        empty_array,
                        0,
                        None
                    )
                    logger.warning("No valid blobs created, using empty data container")
            
            if not data_container:
                logger.error("Failed to create data container")
                return None
            
            # Determine session ID based on command type and API instance
            session_id_bytes = b""
            if api_instance and api_instance.session_id:
                session_id_bytes = api_instance.session_id.encode('utf-8')
            elif command_type == b"session":
                session_id_bytes = b""
            else:
                logger.warning(f"No valid session ID for {command_type.decode()} command")
            
            # Create input data
            input_data = quantum_create_input_data(
                command_type,
                session_id_bytes,
                -1,
                data_container
            )
            logger.info(f"sessionid: {session_id_bytes}")
            if not input_data:
                logger.error("Failed to create input data")
                quantum_free_ref(data_container)
                return None
            
            # Send the command
            logger.info("quantum_send_command start")
            job_id = quantum_send_command(self.client_handle, input_data)
            logger.info("quantum_send_command end")
            
            if job_id == -1:
                logger.error("Failed to send command")
                return None
            
            # Associate job_id with API instance
            if api_instance is not None:
                self.job_to_api_map[job_id] = api_instance
            
            logger.info(f"Sent {command_type.decode()} call, job ID: {job_id}")
            return job_id
    # ========================================
    # 查询任务结果
    # ========================================
    def query_result(self, job_id, timeout=180):
        """
        Query the result for a specific job ID using callback mechanism
        
        Returns:
            result: The fully parsed result data, or None if failed
        """
        start_time = time.time()
        
        # 持续等待直到获得最终结果
        while time.time() - start_time < timeout:
            # 创建事件用于等待回调
            event = threading.Event()
            self.pending_jobs[job_id] = event
            
            # 等待回调通知
            if event.wait(timeout=timeout):
                # 从队列中获取结果
                try:
                    while not self.result_queue.empty():
                        result = self.result_queue.get_nowait()
                        if 'job_id' in result and result['job_id'] == job_id:
                            # logger.info(f"Got result for job {job_id}: {result}")
                            
                            if 'error' in result:
                                logger.error(f"Error in result processing: {result['error']}")
                                return None
                            
                            # Handle different status types
                            status = result['status']
                            # logger.info(f"Job status: {status}")
                            
                            # 如果是完成状态，返回结果
                            if status == "complete":
                                # 在这里打印整个 data_json_list 内容以验证
                                if job_id in self.job_to_api_map:
                                    api_instance = self.job_to_api_map[job_id]
                                    logger.info(f"Complete data_json_list for job {job_id}: {json.dumps(api_instance.data_json_list, ensure_ascii=False, indent=2)}")
                                
                                if not result['data']:
                                    logger.error(f"Job {job_id} returned empty data")
                                    return None
                                
                                final_result = result['data']
                                
                                # First level: Check if data is a string that needs parsing
                                if isinstance(final_result, str):
                                    try:
                                        final_result = json.loads(final_result)
                                    except json.JSONDecodeError:
                                        pass
                                
                                # Second level: Check for contents field
                                if isinstance(final_result, dict) and "message" in final_result and "data" in final_result:
                                    try:
                                        contents = final_result["message"]
                                        if "success" != contents:
                                            return None
                                        else:
                                            data = final_result["data"]
                                            return data
                                    except Exception as e:
                                        logger.error(f"Error parsing nested result structure: {e}")
                                        return None
                                
                                return final_result
                            
                            # 如果还在进行中，继续等待
                            elif status == "in_progress":
                                # 继续等待直到完成
                                continue
                                
                            # 其他状态视为失败
                            else:
                                logger.error(f"Job failed with status: {result['status']}")
                                return None
                except queue.Empty:
                    pass
            else:
                logger.error(f"Timeout waiting for job {job_id} result after {timeout} seconds")
                # 超时情况下确保API实例有结束时间和响应时间
                if job_id in self.job_to_api_map:
                    api_instance = self.job_to_api_map[job_id]
                    # 只有当还没有设置结束时间时才设置
                    if not api_instance.end_time_dt:
                        api_instance.end_time_dt = datetime.now()
                        api_instance.end_time_str = api_instance.end_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    # 设置响应时间为超时时间
                    if api_instance.response_time == 0:  # 只有当还未设置时才设置
                        api_instance.response_time = time.time() - start_time
                        logger.info(f"设置超时响应时间: {api_instance.response_time:.2f}秒")
                # 移除挂起的任务
                if job_id in self.pending_jobs:
                    del self.pending_jobs[job_id]
                return None
        
        logger.error(f"Timeout waiting for job {job_id} result after {timeout} seconds")
        # 超时情况下确保API实例有结束时间和响应时间
        if job_id in self.job_to_api_map:
            api_instance = self.job_to_api_map[job_id]
            # 只有当还没有设置结束时间时才设置
            if not api_instance.end_time_dt:
                api_instance.end_time_dt = datetime.now()
                api_instance.end_time_str = api_instance.end_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            # 设置响应时间为超时时间
            if api_instance.response_time == 0:  # 只有当还未设置时才设置
                api_instance.response_time = time.time() - start_time
                logger.info(f"设置超时响应时间: {api_instance.response_time:.2f}秒")
        # 移除挂起的任务
        if job_id in self.pending_jobs:
            del self.pending_jobs[job_id]
        return None
    # ========================================
    # 资源清理
    # ========================================
    def cleanup(self):
        """Clean up resources"""
        with self.lock:
            if self.client_handle:
                logger.info("Disconnecting...")
                quantum_disconnect(self.client_handle)
                quantum_release_client(self.client_handle)
                self.client_handle = None
                self.connected = False
                logger.info("Cleanup completed")


# ========================================
# 多模态API类
# 用于处理多模态数据上传、查询和下载
# ========================================
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
        self.registered_docs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registered_docs.json")
        self.registered_docs = self.load_registered_docs()
        # 新增：存储最初尝试注册的文档列表（绝对路径）
        self.original_registered_docs = []
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
            payload = {"action": "create"}
            job_id = quantum_client_manager.send_model_call(payload, b"session", self)
            
            # 更详细的错误处理
            if job_id is None:
                logger.error("创建会话失败：无法获取 job_id")
                return False
                
            # 增加重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = quantum_client_manager.query_result(job_id, timeout=30)
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
            job_id = quantum_client_manager.send_model_call(
                payload=payload, 
                command_type=b"fkb_memory", 
                api_instance=self
            )
            end_time = time.time()
            response_time = end_time - start_time
            
            if job_id is not None:
                logger.info(f"成功发送获取memory请求，job_id: {job_id}")
                
                # 查询结果
                result = quantum_client_manager.query_result(job_id, timeout=180)
                
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
    def process_memory_data(self, min_wait_time=1.0, max_wait_time=10.0, enable_random_wait=True):
        """
        处理Memory_data.xlsx文件，在文档注册前执行
        读取Memory_data.xlsx文件，为每行创建新会话，对包含"user_content"的列执行查询
        支持文本、图片、以及 add_memory 操作
        """
        # 读取Excel文件
        memory_excel_path = MEMORY_EXCEL_PATH
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        memory_output_path = os.path.join(current_dir, f"Memory_data_with_responses_{timestamp}.xlsx")
        
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
                    toolname_value = self.extract_toolname_from_data_json_list(memory_api.data_json_list)
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
                    
                    # 检查是否在 data_json_list 中有失败信息
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
                            if isinstance(failure_data, list) and len(failure_data) >= 2:
                                failure_message = str(failure_data)
                                # 也可以更友好地显示
                                failure_message = ', '.join(map(str, failure_data))
                    
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
                    toolname_value = self.extract_toolname_from_data_json_list(memory_api.data_json_list)
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

        # 计算并记录平均值
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            logger.info(f"响应时间平均值(过滤Error后): {avg_response_time:.2f}秒 (共 {len(response_times)} 个有效数据点)")
        else:
            avg_response_time = 0
            logger.info("没有有效的响应时间用于计算平均值")

        if ttft_times:
            avg_ttft = sum(ttft_times) / len(ttft_times)
            logger.info(f"TTFT平均值(过滤Error后): {avg_ttft:.3f}秒 (共 {len(ttft_times)} 个有效数据点)")
        else:
            avg_ttft = 0
            logger.info("没有有效的TTFT时间用于计算平均值")

        # 添加平均值到Excel
        if response_times or ttft_times:
            last_row = len(df) + 2
            avg_label_col = chr(ord('A'))
            worksheet[f'{avg_label_col}{last_row}'] = "平均值(过滤Error后)"
            
            for col_index, column_name in enumerate(user_content_columns):
                result_col_index = len(df.columns) + col_index * 5
                time_column = chr(ord('A') + result_col_index + 1)
                ttft_column = chr(ord('A') + result_col_index + 2)
                
                worksheet[f'{time_column}{last_row}'] = round(avg_response_time, 2) if response_times else "N/A"
                worksheet[f'{ttft_column}{last_row}'] = round(avg_ttft, 3) if ttft_times else "N/A"

        logger.info("Memory数据处理完成，开始获取memory数据...")
        memory_result = self.get_all_memory()

        #更新保存到json文件
        if memory_result["success"]:
            memory_data = memory_result["data"]
            logger.info("成功获取memory数据")
            
            try:
                workbook.save(memory_output_path)
                logger.info(f"当前进度已保存: {memory_output_path}")
            except Exception as e:
                logger.error(f"保存当前进度失败: {e}")
            
            # 修改：改为保存到JSON文件
            # 构建JSON文件路径（与Excel文件同目录，但扩展名为.json）
            memory_json_path = memory_output_path.replace('.xlsx', '_get_all_memory.json')
            save_success = self.save_memory_to_json(memory_data, memory_json_path)
            if save_success:
                logger.info("Memory数据已成功保存到JSON文件")
            else:
                logger.error("保存Memory数据到JSON文件失败")
        else:
            logger.error(f"获取memory数据失败: {memory_result.get('error', '未知错误')}")

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
    def extract_toolname_from_data_json_list(self, data_json_list):
        """
        从 data_json_list 中提取所有 type 为 tool 的 response 值
        返回包含所有tool响应的列表
        如果没有找到，返回空列表
        """
        if not data_json_list or not isinstance(data_json_list, list):
            return []
        
        tool_responses = []
        
        for item in data_json_list:
            if isinstance(item, dict) and 'data' in item:
                data_item = item['data']
                if isinstance(data_item, dict) and data_item.get('type') == 'tool':
                    response = data_item.get('response', '')
                    tool_responses.append(str(response))  # 确保转换为字符串
        
        return tool_responses
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
            job_id = quantum_client_manager.send_model_call(payload, b"document", self)  # 传递 self
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
            job_id = quantum_client_manager.send_model_call(payload, b"document", self)  # 传递 self
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
                result = quantum_client_manager.query_result(job_id)
                
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
                                    test_results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testresult")
                                    os.makedirs(test_results_dir, exist_ok=True)
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    default_excel_path = os.path.join(test_results_dir, f"document_registration_{timestamp}.xlsx")
                                    
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
            job_id = quantum_client_manager.send_model_call(
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
            result = quantum_client_manager.query_result(job_id, timeout=180)
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
            job_id = quantum_client_manager.send_model_call(payload, b"fkb_memory", self)
            
            if not job_id:
                return []
            
            result = quantum_client_manager.query_result(job_id, timeout=180)
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
            job_id = quantum_client_manager.send_model_call(payload, b"fkb_memory", self)
            
            if not job_id:
                logger.error("发送 delete_memory 请求失败")
                return False
            
            result = quantum_client_manager.query_result(job_id, timeout=180)
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
                "action": "list_pagination",
                "folder_path": ""
            }

            # 发送请求
            job_id = quantum_client_manager.send_model_call(
                payload=payload,
                command_type=b"document",
                api_instance=self
            )

            if job_id is None:
                logger.error("发送 get_fkb 请求失败")
                return []


            raw_result = quantum_client_manager.query_result(job_id, timeout=180)
            if raw_result is None or not isinstance(raw_result, dict):
                logger.error("查询 get_fkb 原始结果失败或结果格式错误")
                return []


            documents = []
            
            # 检查是否是直接包含文档列表的格式
            if isinstance(raw_result, list):
                documents = raw_result
            elif isinstance(raw_result, dict):
                if "documents" in raw_result:
                    documents = raw_result["documents"]
                elif "data" in raw_result and isinstance(raw_result["data"], list):
                    documents = raw_result["data"]
                elif "documentList" in raw_result:
                    documents = raw_result["documentList"]
                elif "data" in raw_result and isinstance(raw_result["data"], dict) and "documents" in raw_result["data"]:
                    documents = raw_result["data"]["documents"]
                else:
                    # 如果没有找到文档，尝试使用 get_fkb_result
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

            if not isinstance(documents, list):
                logger.error(f"获取到的文档数据格式错误: {type(documents)}")
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
            job_id = quantum_client_manager.send_model_call(payload, b"document", self)
            
            if not job_id:
                logger.error("发送 delete_fkb 请求失败")
                return False
            
            result = quantum_client_manager.query_result(job_id, timeout=180)
            
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
            logger.info(f"发送查询请求: {json.dumps(payload)}")
            
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
            job_id = quantum_client_manager.send_model_call(
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
            result = quantum_client_manager.query_result(int(self.query_upload_id),timeout=180)
            end_time = time.time()
            # self.response_time = end_time - start_time
            
            # # 记录结束时间
            # self.end_time_dt = datetime.now()
            # self.end_time_str = self.end_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            # logger.info(f"结束时间: {self.end_time_str}")
            # logger.info(f"响应时间: {self.response_time:.2f}秒")


            # 检查是否超时
            if result is None and self.response_time >= 180:  # 根据实际超时值调整
                logger.error("请求超时，未收到响应")
                return "CTTVError: Request Timeout"
            # # 如果已经有first_word_time，则计算TTFT
            # if hasattr(self, 'first_word_time') and self.first_word_time:
            #     ttft = (self.first_word_time - self.start_time_dt).total_seconds()
            #     self.ttft_seconds = ttft
            #     logger.info(f"TTFT (Time To First Token): {ttft:.3f}秒")

            if result:
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

        logger.info(f"最终结果: {result}")
        return result
    # 分批次处理文档
    # 每次最多处理4个文档
    # 按顺序分批处理，确保不重复
    # 例如：30个文件 → 8批（7批4个 + 1批2个）

    # 每次注册完一个批次后等待5秒
    # 等待时间不计入总耗时统计
    # 不重复处理相同文件
    def process_document_registration_only(self):
        """
        仅处理文档注册流程，批量处理文档（每次最多4个）
        """
        logger.info("开始文档注册流程...")
        if not self.create_session():
            logger.info("创建会话失败")
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

        # 检查是否需要注册文档（检查是否已注册且文件仍然存在）
        is_registered = self.is_document_registered(doc_file_list)
        
        if not is_registered:
            # 记录文档注册开始时间
            start_time = time.time()  # 只记录实际开始时间
            
            # 记录总的文档数量，用于后续完成率计算
            self._original_total_docs_count = len(doc_file_list)
            
            logger.info(f"开始文档注册，时间: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 按每批4个文档进行注册
            batch_size = 4
            total_files = len(doc_file_list)
            total_batches = (total_files + batch_size - 1) // batch_size  # 向上取整
            
            logger.info(f"总共 {total_files} 个文档，将分 {total_batches} 批进行注册")
            
            for batch_index in range(total_batches):
                start_idx = batch_index * batch_size
                end_idx = min((batch_index + 1) * batch_size, total_files)
                batch_files = doc_file_list[start_idx:end_idx]
                
                logger.info(f"正在注册第 {batch_index + 1}/{total_batches} 批文档: {batch_files}")
                
                # 注册当前批次的文档
                register_result = self.register_document(batch_files)
                if not register_result.get("success", False):
                    logger.info(f"第 {batch_index + 1} 批文档注册失败")
                    return False
                
                # 如果不是最后一批，等待5秒再继续下一批（等待时间不计入总耗时）
                if batch_index < total_batches - 1:
                    logger.info(f"等待 5 秒后继续下一批注册...")
                    time.sleep(5)
            
            logger.info("所有文档批次注册完成")
            
            # 最后检查所有文档的处理状态
            max_retries = 10000000
            retry_interval = 2
            attempt = 0
            
            while attempt < max_retries:
                attempt += 1
                logger.info(f"第{attempt}次检查文档处理状态...")
                
                doc_status = self.get_register_document()
                if doc_status.get("success", False):
                    # 计算总耗时（不包括等待时间）
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
                # 计算总耗时（不包括最后一次等待）
                total_time = time.time() - start_time
                logger.info(f"文档处理超时，总耗时: {total_time:.2f}秒 ({self._format_time(total_time)})")
                return False
        else:
            logger.info("文档已注册，跳过注册流程")
        
        logger.info("文档注册流程完成")
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

            # 筛选并重新处理超时错误的case
            timeout_indices = []
            for idx, result in enumerate(df_output['result']):
                if isinstance(result, str) and "CTTVError: Request Timeout" in result:
                    timeout_indices.append(idx)
            
            if timeout_indices:
                logger.info(f"发现 {len(timeout_indices)} 个超时错误的case，开始重新处理: {timeout_indices}")
                self._process_rows(df, df_output, cycle_output_path, -1, min_wait_time, max_wait_time, enable_random_wait, timeout_indices)
                logger.info(f"超时错误的case重新处理完成")
            else:
                logger.info("没有发现超时错误的case")
        
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
                toolname_value = self.extract_toolname_from_data_json_list(api.data_json_list)
                toolname_value = json.dumps(toolname_value, ensure_ascii=False) if toolname_value else "[]"

                # 结果处理逻辑
                if result is not None and isinstance(result, str) and len(result.strip()) > 0 and not result.startswith("Error:"):
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

def start_resource_monitoring(gpu_type):
    """启动资源监控"""
    process_names = ['com.lenovo.quantum.exe','com.lenovo.quantum.exe','mcpMgmtService.exe','mcpMgmtService.exe','lenovo.pfm.pipe.exe'] # 需要监控的进程名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # 为每次调用生成新的时间戳
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
        
        # 检查Excel文件是否已经存在resource sheet
        if os.path.exists(excel_output_path):
            try:
                # 加载现有的Excel文件
                existing_workbook = openpyxl.load_workbook(excel_output_path)
                
                # 如果resource sheet已存在，我们需要处理数据合并或替换
                if 'resource' in existing_workbook.sheetnames:
                    # 方案1: 直接替换resource sheet（保持原逻辑）
                    with pd.ExcelWriter(excel_output_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
                        resource_df.to_excel(writer, sheet_name='resource', index=False)
                else:
                    # 如果resource sheet不存在，则添加
                    with pd.ExcelWriter(excel_output_path, mode='a', engine='openpyxl') as writer:
                        resource_df.to_excel(writer, sheet_name='resource', index=False)
                        
            except Exception as e:
                # 如果加载工作簿出现问题，重新创建文件
                logger.warning(f"无法加载现有Excel文件，将重新创建: {e}")
                with pd.ExcelWriter(excel_output_path, engine='openpyxl') as writer:
                    resource_df.to_excel(writer, sheet_name='resource', index=False)
        else:
            # 如果文件不存在，创建新文件
            with pd.ExcelWriter(excel_output_path, engine='openpyxl') as writer:
                resource_df.to_excel(writer, sheet_name='resource', index=False)
                
        logger.info(f"资源监控数据已保存到 {excel_output_path} 的 resource sheet中")
    except Exception as e:
        logger.error(f"保存资源监控数据失败: {e}")
        import traceback
        traceback.print_exc()  
        
# ========================================
# 主流程逻辑
#优化单独的注册和memory处理时候也有资源监控
"""三种监控场景：

should_start_overall_monitor：单独执行 process_memory 或 process_document
should_start_combined_monitor：同时执行 process_memory 和 process_document
should_start_pre_monitor：process_memory/process_document + process_main
资源数据处理：确保在所有场景下，资源数据都能正确地添加到对应的结果文件中

现在无论哪种组合（process_memory + process_document、process_memory + process_main、process_document + process_main等），都会有相应的资源监控。"""
def run_quantum_e2e_process(args):
    """
    运行 Quantum_e2e_v20260108_nova_dll 的主流程逻辑。
    """
    global OUTPUT_EXCEL_PATH, EXCEL_FILE_PATH, _MEMORY_PROCESSED_GLOBAL
    output_files_list = []
    
    # 为单独的memory和文档注册启动资源监控
    overall_monitor = None
    overall_resource_csv_path = None
    
    try:
        # 如果只处理memory或文档注册（不处理main excel），启动全局资源监控
        should_start_overall_monitor = (
            (args.process_memory or args.process_document) and 
            not (args.process_main or args.process_all)
        )
        
        # 如果同时处理memory和文档注册（不处理main excel），也需要监控
        should_start_combined_monitor = (
            args.process_memory and args.process_document and
            not (args.process_main or args.process_all)
        )
        
        # 如果同时处理memory/文档注册和主Excel，为memory/文档注册阶段启动监控
        should_start_pre_monitor = (
            (args.process_memory or args.process_document) and
            (args.process_main or args.process_all)
        )
        
        # 启动适当的监控
        if should_start_overall_monitor or should_start_combined_monitor:
            overall_monitor, overall_resource_csv_path, start_timestamp = start_resource_monitoring(GPU_TYPE)
        elif should_start_pre_monitor and overall_resource_csv_path is None:
            # 为预处理阶段（memory和文档注册）启动监控
            pre_monitor, pre_resource_csv_path, start_timestamp = start_resource_monitoring(GPU_TYPE)
        
        # 处理Memory数据（如果需要）
        memory_output_paths = []
        if args.process_memory:
            logger.info("开始处理Memory数据...")
            memory_api = MultimodalAPI()
            memory_success = memory_api.process_memory_data_only(
                args.min_wait_time, 
                args.max_wait_time, 
                args.enable_random_wait
            )
            if memory_success:
                logger.info("Memory数据处理完成")
                
                # 记录memory结果文件路径，以便后续添加资源数据
                current_dir = os.path.dirname(os.path.abspath(__file__))
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                memory_output_path = os.path.join(current_dir, f"Memory_data_with_responses_{timestamp}.xlsx")
                memory_output_paths.append(memory_output_path)
                
            else:
                logger.info("Memory数据处理失败")

        # 处理文档注册（如果需要）
        doc_output_paths = []
        if args.process_document:
            # 为文档注册创建新的API实例
            api = MultimodalAPI()
            
            success = api.process_document_registration_only()
            
            # 记录文档注册结果文件路径
            if success:
                # 获取文档注册生成的文件路径（这个需要在process_document_registration_only中记录）
                doc_output_paths.extend(getattr(api, 'generated_files', []))

        # 如果是预处理监控模式，停止预处理监控
        if 'pre_monitor' in locals() and should_start_pre_monitor:
            stop_resource_monitoring(pre_monitor)

        # 仅当需要处理主Excel文件时才检查Excel文件
        excel_files = []
        if args.process_main or args.process_all:
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
                    return False, output_files_list
                logger.info(f"找到 {len(excel_files)} 个Excel文件")

        # 处理所有Excel文件，为每个文件单独启动资源监控
        for excel_file in excel_files:
            logger.info(f"\n正在处理文件: {excel_file.name}")
            
            # 为每个文件创建独立的资源监控
            file_monitor = None
            file_resource_csv_path = None
            
            try:
                # 为每个文件启动独立的资源监控
                file_monitor, file_resource_csv_path, _ = start_resource_monitoring(GPU_TYPE)
                
                OUTPUT_EXCEL_PATH = os.path.join(
                    TEST_RESULTS_DIR, 
                    f"test_results_{excel_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                )
                EXCEL_FILE_PATH = str(excel_file)
                
                # 为每个文件创建新的API实例
                api = MultimodalAPI()
                
                # 处理文档注册（如果需要）- 这里主要是为了兼容性，实际已在前面处理
                success = True
                if args.process_document:
                    # 如果前面已经处理过文档注册，这里可以跳过或重新检查
                    success = api.process_document_registration_only()
                    
                # 处理主Excel文件（如果需要）
                if success and args.process_main:
                    success = api.process_main_excel_only(
                        CYCLE_COUNT, 
                        args.min_wait_time, 
                        args.max_wait_time, 
                        args.enable_random_wait
                    )
                
                # 收集主Excel处理生成的文件
                if success:
                    logger.info(f"文件 {excel_file.name} 处理完成")
                    for cycle_index in range(CYCLE_COUNT):
                        cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
                        if os.path.exists(cycle_output_path):
                            output_files_list.append(cycle_output_path)
                else:
                    logger.info(f"文件 {excel_file.name} 处理失败")
                    
            finally:
                # 为每个文件单独停止资源监控并添加资源数据
                try:
                    if file_monitor:
                        stop_resource_monitoring(file_monitor)
                    
                    if file_resource_csv_path and os.path.exists(file_resource_csv_path):
                        # 将资源数据添加到该文件的输出中
                        for cycle_index in range(CYCLE_COUNT):
                            try:
                                cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
                                if os.path.exists(cycle_output_path):
                                    add_resource_data_to_results(file_resource_csv_path, cycle_output_path)
                            except Exception as e:
                                logger.error(f"添加资源数据到 {cycle_output_path} 失败: {e}")
                                continue  
                                
                except Exception as e:
                    logger.error(f"资源清理过程中出现错误: {e}")

        # 如果只有memory或文档注册处理（没有处理main excel），添加资源数据到结果文件
        if should_start_overall_monitor or should_start_combined_monitor:
            if overall_resource_csv_path and os.path.exists(overall_resource_csv_path):
                # 添加资源数据到memory结果文件
                for memory_output_path in memory_output_paths:
                    if os.path.exists(memory_output_path):
                        add_resource_data_to_results(overall_resource_csv_path, memory_output_path)
                        logger.info(f"资源数据已添加到memory结果文件: {memory_output_path}")
                
                # 添加资源数据到文档注册结果文件
                for doc_output_path in doc_output_paths:
                    if os.path.exists(doc_output_path):
                        add_resource_data_to_results(overall_resource_csv_path, doc_output_path)
                        logger.info(f"资源数据已添加到文档注册结果文件: {doc_output_path}")
        
        # 如果是预处理监控模式，将预处理阶段的资源数据也添加到结果中
        if should_start_pre_monitor and 'pre_resource_csv_path' in locals() and os.path.exists(pre_resource_csv_path):
            # 将预处理（memory和文档注册）的资源数据添加到主Excel结果中
            for cycle_index in range(CYCLE_COUNT):
                try:
                    cycle_output_path = OUTPUT_EXCEL_PATH.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
                    if os.path.exists(cycle_output_path):
                        add_resource_data_to_results(pre_resource_csv_path, cycle_output_path)
                        logger.info(f"预处理资源数据已添加到主Excel结果文件: {cycle_output_path}")
                except Exception as e:
                    logger.error(f"添加预处理资源数据失败: {e}")
                    continue

    finally:
        # 停止全局监控（如果启动了）
        if overall_monitor:
            stop_resource_monitoring(overall_monitor)

    return True, output_files_list


# =============================
# 合并所有输出文件并分析性能指标
# =============================
#20251217
def merge_and_analyze_output_files(output_files):
    """
    合并多个 output_files 中的 .xlsx 文件，
    按 scene 分组计算 TTFT 和 Latency 的平均值（不过滤），
    generation_speed 只过滤 >=200 的值。
    并保存为 Latency_时间戳.xlsx
    """
    import pandas as pd
    import os
    from datetime import datetime

    # 确保 output_files 是列表
    if isinstance(output_files, str):
        output_files = [output_files]

    # 收集所有有效数据（不提前过滤）
    all_data = []
    for file_path in output_files:
        if not os.path.exists(file_path):
            logger.warning(f"文件不存在: {file_path}")
            continue
        try:
            df = pd.read_excel(file_path)
            all_data.append(df)
        except Exception as e:
            logger.error(f"读取文件失败: {file_path}, 错误: {e}")

    if not all_data:
        logger.error("没有有效数据可处理")
        return

    # 合并所有 DataFrame
    merged_df = pd.concat(all_data, ignore_index=True)

    # 按 scene 分组
    grouped = merged_df.groupby('scene')

    # 计算 TTFT 和 Latency（不过滤）
    ttft_mean = grouped['ttft'].mean().round(2)
    latency_mean = grouped['response_time'].mean().round(2)

    # 计算 generation_speed（仅过滤 >=200 的值）
    gen_speed_filtered = merged_df[merged_df['generation_speed'] < 200]
    gen_speed_mean = gen_speed_filtered.groupby('scene')['generation_speed'].mean().round(2)

    # 合并结果
    result = pd.DataFrame({
        'Category': ttft_mean.index,
        'TTFT': ttft_mean.values,
        'Latency': latency_mean.values,
        'Generation_Speed': gen_speed_mean.values
    })

    # 输出文件名：Latency_时间戳.xlsx
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = os.path.dirname(output_files[0]) if output_files else os.getcwd()
    output_path = os.path.join(target_dir, f"Latency_{timestamp}.xlsx")

    # 写入 Excel
    result.to_excel(output_path, index=False)
    logger.info(f"性能统计结果已保存至: {output_path}")

    # 打印日志
    logger.info("\n性能统计结果:")
    for _, row in result.iterrows():
        logger.info(f"{row['Category']:<20} | TTFT: {row['TTFT']:<6.2f} | Latency: {row['Latency']:<6.2f} | GenSpeed: {row['Generation_Speed']:<6.2f}")

def find_quantum_sdk_dll_simple():
    """
    简单查找 quantum-sdk DLL 文件
    """
    # 获取用户目录
    user_home = Path.home()
    
    # 定义基础搜索路径
   # 定义可能的路径
    possible_paths = [
        user_home / 'AppData' / 'Local' / 'Lenovo' / 'Qira' / 'QuantumApp' / 'QuantumApp',
        user_home / 'AppData' / 'Local' / 'Lenovo' / 'Qira' / 'QuantumApp',
        user_home / 'AppData' / 'Local' / 'Lenovo' / 'Qira',
        user_home / 'AppData' / 'Local' / 'Lenovo',
    ]
    
    
    # 在可能的路径中查找
    for path in possible_paths:
        if path.exists():
            for dll_file in path.glob('quantum-sdk-*.dll'):
                return str(dll_file)
            # 也递归搜索子目录
            for dll_file in path.rglob('quantum-sdk-*.dll'):
                return str(dll_file)
    
    # 如果在常规路径找不到，尝试备选路径
    logger.info("在常规路径未找到 DLL，尝试备选路径...")
    backup_path = Path(r"C:\Program Files\Lenovo\Lenovo Qira\QuantumApp")
    if backup_path.exists():
        # 查找所有匹配的DLL文件
        for dll_file in backup_path.glob('quantum-sdk-*.dll'):
            return str(dll_file)
    
    raise FileNotFoundError("无法找到 quantum-sdk DLL 文件")

if __name__ == "__main__":
    TEST_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testresult")
    os.makedirs(TEST_RESULTS_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description='API Test')
    # parser.add_argument('--dll_path', type=str, default=r"C:\Users\woel0\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251219_nova_dll\quantum-sdk-1.0.8.dll", help='量子SDK DLL文件路径') 
    parser.add_argument('--excel_dir', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260106_nova_dll\dataset20260106\test.xlsx", help='Excel文件目录路径')
    parser.add_argument('--image_dir', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260106_nova_dll\Memory_data_260107\image", help='是否需要用到pathlist')
    parser.add_argument('--doc_dir', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260106_nova_dll\Reg_Documents\KBQA-30-1208-ocr&layout", help='文档注册,文档的路径')
    parser.add_argument('--memory_excel', type=str, default=r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260106_nova_dll\Memory_data_260107\Memory_data _v6_260107_7.xlsx", help='Memory注册,Excel文件路径')
    parser.add_argument('--process_memory', action='store_true',default=False, help='处理Memory数据')
    parser.add_argument('--process_document', action='store_true',default=False, help='处理文档注册')
    parser.add_argument('--process_main', action='store_true',default=True, help='处理主Excel文件')
    parser.add_argument('--process_all', action='store_true', default=False, help='执行完整流程（默认）')
    parser.add_argument('--cycle', type=int, default=1, help='循环轮数，默认为1')
    parser.add_argument('--gpu_type', type=str, default="iGPU", choices=["dGPU", "iGPU", "aGPU"], help='GPU类型')
    parser.add_argument('--test_mode', type=str, default="cloud", choices=["cloud", "local"], help='测试模式：云端测试或本地测试')
    parser.add_argument('--filter_local_brain', type=str, default="yes", choices=["auto", "yes", "no"], 
                   help='是否过滤包含"Local Brain with"的数据: auto(根据test_mode自动判断), yes(总是过滤), no(从不过滤)')
    parser.add_argument('--min_wait_time', type=float, default=5.0, help='随机等待的最小时间（秒），默认为1.0')
    parser.add_argument('--max_wait_time', type=float, default=10.0, help='随机等待的最大时间（秒），默认为10.0')
    parser.add_argument('--enable_random_wait', type=bool, default=True, help='默认为False,不启用随机等待功能')
    #20260114更新
    #新增参数控制清理操作
    parser.add_argument('--cleanup_after_run', action='store_true', default=False, help='运行完成后清理所有数据（memory和文档）')
    
    args = parser.parse_args()
    logger.info("程序启动参数: " + ", ".join([f"{k}={v}" for k, v in vars(args).items()]))

    EXCEL_DIR = args.excel_dir
    IMAGE_DIR = Path(args.image_dir)
    doc_directory = args.doc_dir
    MEMORY_EXCEL_PATH = args.memory_excel
    CYCLE_COUNT = args.cycle
    GPU_TYPE = args.gpu_type
    # DLL_PATH = args.dll_path

    try:
        dll_path = find_quantum_sdk_dll_simple()
        logger.info(f"找到 quantum-sdk DLL 文件: {dll_path}")
        quantum_sdk = ctypes.CDLL(dll_path)
    except Exception as e:  
        logger.error(f"Failed to load DLL: {e}")
        raise
    # Define callback function types
    ConnectionStatusCallback = CFUNCTYPE(None, c_int)
    ResultCallback = CFUNCTYPE(None, c_void_p)

    # Define the DataContainer structure
    class DataContainer(Structure):
        _fields_ = [("pinned", c_void_p)]

    # Define the InputData structure
    class InputData(Structure):
        _fields_ = [("pinned", c_void_p)]

    # Function declarations
    quantum_create_blob_data = quantum_sdk.quantum_create_blob_data
    quantum_create_blob_data.argtypes = [c_char_p, c_void_p, c_int]
    quantum_create_blob_data.restype = c_void_p

    quantum_create_data_container = quantum_sdk.quantum_create_data_container
    quantum_create_data_container.argtypes = [c_char_p, POINTER(c_void_p), c_int, c_char_p]
    quantum_create_data_container.restype = c_void_p

    quantum_create_input_data = quantum_sdk.quantum_create_input_data
    quantum_create_input_data.argtypes = [c_char_p, c_char_p, c_long, c_void_p]
    quantum_create_input_data.restype = c_void_p

    quantum_get_client = quantum_sdk.quantum_get_client
    quantum_get_client.argtypes = []
    quantum_get_client.restype = c_long

    quantum_connect = quantum_sdk.quantum_connect
    quantum_connect.argtypes = [c_long, ConnectionStatusCallback, ResultCallback, c_char_p]
    quantum_connect.restype = c_int

    quantum_send_command = quantum_sdk.quantum_send_command
    quantum_send_command.argtypes = [c_long, c_void_p]
    quantum_send_command.restype = c_long

    quantum_disconnect = quantum_sdk.quantum_disconnect
    quantum_disconnect.argtypes = [c_long]
    quantum_disconnect.restype = c_int

    quantum_release_client = quantum_sdk.quantum_release_client
    quantum_release_client.argtypes = [c_long]
    quantum_release_client.restype = None

    quantum_free_string = quantum_sdk.quantum_free_string
    quantum_free_string.argtypes = [c_void_p]
    quantum_free_string.restype = None

    quantum_free_ref = quantum_sdk.quantum_free_ref
    quantum_free_ref.argtypes = [c_void_p]
    quantum_free_ref.restype = None

    # Output data functions
    quantum_output_get_job_id = quantum_sdk.quantum_output_get_job_id
    quantum_output_get_job_id.argtypes = [c_void_p]
    quantum_output_get_job_id.restype = c_long

    quantum_output_get_status = quantum_sdk.quantum_output_get_status
    quantum_output_get_status.argtypes = [c_void_p]
    quantum_output_get_status.restype = c_void_p

    quantum_output_get_data = quantum_sdk.quantum_output_get_data
    quantum_output_get_data.argtypes = [c_void_p]
    quantum_output_get_data.restype = c_void_p

    quantum_data_get_text = quantum_sdk.quantum_data_get_text
    quantum_data_get_text.argtypes = [c_void_p]
    quantum_data_get_text.restype = c_void_p


    # Initialize quantum client manager at module level
    quantum_client_manager = QuantumClientManager()
    try:

        if hasattr(args, 'test_mode') and args.test_mode == "local":
            logger.info("检测到本地测试模式，准备关闭WiFi...")
            max_retries = 3
            retry_count = 0
            wifi_closed_successfully = False
            
            while retry_count < max_retries and not wifi_closed_successfully:
                try:
                    retry_count += 1
                    logger.info(f"尝试关闭WiFi (第 {retry_count}/{max_retries} 次)...")
                    
                    # 直接调用函数而不是执行脚本
                    success = close_openwifi.toggle_wifi("off")
                    
                    if success:
                        time.sleep(60)
                        logger.info("WiFi已成功关闭")
                        wifi_closed_successfully = True
                    else:
                        logger.error("WiFi关闭操作未成功")
                        if retry_count < max_retries:
                            logger.info("等待5秒后重试...")
                            time.sleep(5)
                            continue
                        else:
                            logger.error("关闭WiFi失败，无法继续执行，程序退出")
                            sys.exit(1)
                except Exception as e:
                    logger.error(f"关闭WiFi过程中出错: {str(e)}")
                    if retry_count < max_retries:
                        logger.info("等待5秒后重试...")
                        time.sleep(5)
                        continue
                    else:
                        logger.error("关闭WiFi失败，无法继续执行，程序退出")
                        sys.exit(1)

        # Initialize quantum client before starting the process
        logger.info("初始化量子客户端...")
        quantum_client_manager.initialize()
        
        # 执行主流程
        success, output_files = run_quantum_e2e_process(args)
        
        if success:
            logger.info("所有流程成功完成！")
            logger.info(f"生成了 {len(output_files)} 个输出文件:")
            logger.info(output_files)
            for i, file_path in enumerate(output_files, 1):
                logger.info(f"  {i}. {file_path}")
            # 在需要打开WiFi的地方（约3018行附近）：
            if hasattr(args, 'test_mode') and args.test_mode == "local":
                logger.info("检测到本地测试模式，开始自动化判断前打开WiFi...")
                max_retries = 3
                retry_count = 0
                wifi_opened_successfully = False
                
                while retry_count < max_retries and not wifi_opened_successfully:
                    try:
                        retry_count += 1
                        logger.info(f"尝试打开WiFi (第 {retry_count}/{max_retries} 次)...")
                        
                        # 直接调用函数而不是执行脚本
                        success = close_openwifi.toggle_wifi("on")
                        
                        if success:
                            time.sleep(60)
                            logger.info("WiFi已成功打开")
                            wifi_opened_successfully = True
                        else:
                            logger.error("WiFi打开操作未成功")
                            if retry_count < max_retries:
                                logger.info("等待5秒后重试...")
                                time.sleep(5)
                                continue
                            else:
                                logger.error("打开WiFi失败，无法继续执行，程序退出")
                                sys.exit(1)
                    except Exception as e:
                        logger.error(f"打开WiFi过程中出错: {str(e)}")
                        if retry_count < max_retries:
                            logger.info("等待5秒后重试...")
                            time.sleep(5)
                            continue
                        else:
                            logger.error("打开WiFi失败，无法继续执行，程序退出")
                            sys.exit(1)

            # 开始自动化判断
            if args.process_main or args.process_all:
                if CYCLE_COUNT == 1:
                    logger.info("开始计算latency...")
                    merge_and_analyze_output_files(output_files)
                    if output_files:
                        logger.info("开始自动判断...")
                        Auto_Judge.run(args.doc_dir, output_files, filter_local_brain=args.filter_local_brain)
                    else:
                        # 如果没有output_files，则使用默认行为（查找最新文件）
                        logger.info("没有可用的输出文件，将使用默认行为（查找最新文件）")
                        Auto_Judge.run(args.doc_dir, filter_local_brain=args.filter_local_brain)
                else:
                    logger.info(f"当前是第{CYCLE_COUNT}轮循环，不进行自动判断")
                    logger.info("开始计算latency...")
                    merge_and_analyze_output_files(output_files)
            #20260114更新
            # 根据参数决定是否清理数据
            if args.cleanup_after_run:
                logger.info("根据参数清理所有数据...")
                try:
                    api_instance = MultimodalAPI()
                    cleanup_success = api_instance.cleanup_all_data()
                    if cleanup_success:
                        logger.info("数据清理完成")
                    else:
                        logger.error("数据清理部分失败")
                except Exception as e:
                    logger.error(f"清理数据时发生错误: {e}")
        else:
            logger.info("流程执行失败！")
    except Exception as e:
        logger.error(f"主流程执行过程中出现错误: {e}")
    finally:
        # Clean up quantum client
        logger.info("清理量子客户端资源...")
        quantum_client_manager.cleanup()
        input("执行完成，按回车键退出程序...")


    # logger.info("根据参数清理所有数据...")
    # api_instance = MultimodalAPI()
    # # 确保量子客户端已初始化
    # if not quantum_client_manager.initialize():
    #     logger.error("量子客户端初始化失败，无法执行清理操作")
    # else:
    #     cleanup_success = api_instance.cleanup_all_data()
    #     if cleanup_success:
    #         logger.info("数据清理完成")
    #     else:
    #         logger.error("数据清理部分失败")


    # output_files = [r"C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260106_nova_dll\testresult\test_results_Memory_question _v6_260107_20260107_195101_cycle1.xlsx"]
    # # 开始自动化判断
    # if args.process_main:
    #     logger.info("开始自动判断...")
    #     if output_files:
    #         logger.info("开始自动判断...")
    #         Auto_Judge.run(args.doc_dir, output_files, filter_local_brain=args.filter_local_brain)
    #     else:
    #         # 如果没有output_files，则使用默认行为（查找最新文件）
    #         logger.info("没有可用的输出文件，将使用默认行为（查找最新文件）")
    #         Auto_Judge.run(args.doc_dir)


    