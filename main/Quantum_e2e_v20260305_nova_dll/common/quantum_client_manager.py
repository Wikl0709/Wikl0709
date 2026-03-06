"""
Quantum client manager module - singleton and QuantumClientManager class.
All quantum SDK calls go through self.sdk.
"""
import json
import time
import queue
import threading
import ctypes
from datetime import datetime
from loguru import logger


_manager = None


def get_quantum_client_manager():
    return _manager


def set_quantum_client_manager(manager):
    global _manager
    _manager = manager


# ------------------------------
# 量子客户端管理器
# ------------------------------
class QuantumClientManager:
    def __init__(self, sdk):
        self.sdk = sdk
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
                
   # 结果处理回调
    # ========================================
    # 在QuantumClientManager类的on_result方法中，找到处理text类型的代码段，添加对tool类型的处理
    # 在原有的text类型处理之前添加以下代码：

    # 修改 on_result 方法中的token计数逻辑部分
    # ========================================
    # 结果处理回调
    # ========================================
    def on_result(self, output_data_ptr):
        first_word_time_str =None
        first_text_response_time_str =None
        """Handle command results"""
        if not output_data_ptr:
            return
        
        try:
            job_id = self.sdk.quantum_output_get_job_id(output_data_ptr)
            status_ptr = self.sdk.quantum_output_get_status(output_data_ptr)
            status = ctypes.string_at(status_ptr).decode('utf-8')
            
            data_ptr = self.sdk.quantum_output_get_data(output_data_ptr)
            result_data = None
            
            if data_ptr:
                text_ptr = self.sdk.quantum_data_get_text(data_ptr)
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
                                            # Local Brain模式：现在改为与Azure Agent模式一致，第一个text响应即记录
                                            api_instance.first_word_time = datetime.now()
                                            first_word_time_str = api_instance.first_word_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                            logger.info(f"首字时间 (text类型): {first_word_time_str}")

                                # 处理tool类型响应 - 新增
                                if text_type == "tool":
                                    tool_response = result_data.get("response", "")
                                    if hasattr(api_instance, 'tool_responses'):
                                        api_instance.tool_responses.append(str(tool_response))
                                        logger.info(f"记录tool响应: {tool_response}")

                                # 只有在是text类型时才处理文本内容
                                if text_type == "text":
                                    # 记录第一个text响应时间（始终记录）
                                    if api_instance.text_response_count == 0:
                                        api_instance.first_text_response_time = datetime.now()
                                        first_text_response_time_str = api_instance.first_text_response_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                        logger.info(f"第一个text响应时间: {first_text_response_time_str}")
                                    
                                    # 增加text响应计数
                                    api_instance.text_response_count += 1
                                    
                                    # 统一token计数逻辑：对于两种模式都从第一个text响应开始计数
                                    if status == "in_progress":
                                        # 统一逻辑：无论哪种模式，都从第一个text响应开始计数
                                        token_count_start = 1
                                        
                                        # 只有当text响应计数达到起始点时才开始计数token
                                        if api_instance.text_response_count >= token_count_start:
                                            api_instance.token_count += 1
                                            logger.debug(f"接收到 in_progress 且类型为text的消息，当前token计数: {api_instance.token_count}")

                    except json.JSONDecodeError:
                        result_data = text
                    self.sdk.quantum_free_string(text_ptr)
                self.sdk.quantum_free_ref(data_ptr)
            
            self.sdk.quantum_free_string(status_ptr)
            self.sdk.quantum_free_ref(output_data_ptr)
            
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
                
                # 添加：如果任务失败，也记录相关信息
                elif status == "failed":
                    # 记录结束时间
                    api_instance.end_time_dt = datetime.now()
                    api_instance.end_time_str = api_instance.end_time_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    
                    # 计算响应时间
                    if api_instance.start_time_dt:
                        api_instance.response_time = (api_instance.end_time_dt - api_instance.start_time_dt).total_seconds()
                        logger.info(f"任务失败，响应时间: {api_instance.response_time:.2f}秒")
                        logger.info(f"结束时间: {api_instance.end_time_str}")
                    
                    logger.info(f"任务失败，失败原因: {result_data}")
            
            # 将结果放入队列并通知等待的线程
            self.result_queue.put(result_entry)
            
            # 只有在任务完成或失败时才移除映射关系
            if job_id in self.pending_jobs and status in ["complete", "failed"]:
                event = self.pending_jobs.pop(job_id)
                event.set()
                
                # 只有在任务完成或失败时才移除 job_id 到 API 实例的映射process_excel
                if job_id in self.job_to_api_map:
                    del self.job_to_api_map[job_id]
                    
        except Exception as e:
            logger.error(f"Error processing result: {e}")
            if output_data_ptr:
                self.sdk.quantum_free_ref(output_data_ptr)
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
                # logger.info("quantum_get_client start")
                self.client_handle = self.sdk.quantum_get_client()
                # logger.info("quantum_get_client end")
                logger.info(f"Client handle: {self.client_handle}")
                if self.client_handle == 0:
                    raise Exception("Client initialization failed")
                
                logger.info("Client initialized successfully")
                
                # Set up callbacks
                self.status_callback = self.sdk.ConnectionStatusCallback(self.on_connection_status)
                self.result_callback = self.sdk.ResultCallback(self.on_result)
                
                # Connect to the service
                logger.info("quantum_connect start")
                result = self.sdk.quantum_connect(
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
            
            # logger.info(f"Sending {command_type.decode()} call with payload: {json.dumps(payload)}")
            logger.info(f"Sending {command_type.decode()} call with payload: {json.dumps(payload, ensure_ascii=False)}")
            # Create JSON payload
            # json_payload = json.dumps(payload).encode('utf-8')
            json_payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            # 如果没有附件，直接使用空数组版本
            if not blobs or len(blobs) == 0:
                empty_array = (ctypes.c_void_p * 0)()
                data_container = self.sdk.quantum_create_data_container(
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
                        blob_ptr = self.sdk.quantum_create_blob_data(
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
                    
                    data_container = self.sdk.quantum_create_data_container(
                        json_payload,
                        blob_array,
                        len(blob_ptrs),
                        None
                    )
                    logger.info(f"Created data container with {len(blob_ptrs)} blobs")
                else:
                    # 如果所有附件都处理失败，使用空数组
                    empty_array = (ctypes.c_void_p * 0)()
                    data_container = self.sdk.quantum_create_data_container(
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
            input_data = self.sdk.quantum_create_input_data(
                command_type,
                session_id_bytes,
                -1,
                data_container
            )
            logger.info(f"sessionid: {session_id_bytes}")
            if not input_data:
                logger.error("Failed to create input data")
                self.sdk.quantum_free_ref(data_container)
                return None
            
            # Send the command
            logger.info("quantum_send_command start")
            job_id = self.sdk.quantum_send_command(self.client_handle, input_data)
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
    def query_result(self, job_id, timeout=180, stream_timeout=60):
        """
        Query the result for a specific job ID using callback mechanism
        
        Args:
            job_id: The job ID to query
            timeout: Overall timeout in seconds (default 180)
            stream_timeout: Timeout between stream responses in seconds (default 60)
        
        Returns:
            result: The fully parsed result data, or None if failed
        """
        start_time = time.time()
        last_stream_time = time.time()  # Track time of last stream response
        
        # 持续等待直到获得最终结果
        while time.time() - start_time < timeout:
            # 创建事件用于等待回调
            event = threading.Event()
            self.pending_jobs[job_id] = event
            
            # 等待回调通知，但不超过stream_timeout
            wait_time = min(stream_timeout, timeout - (time.time() - start_time))
            if event.wait(timeout=wait_time):
                # 从队列中获取结果
                try:
                    while not self.result_queue.empty():
                        result = self.result_queue.get_nowait()
                        if 'job_id' in result and result['job_id'] == job_id:
                            # 更新最后一次流式响应的时间
                            last_stream_time = time.time()
                            
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
                            
                            # 添加：如果任务失败，返回失败原因
                            elif status == "failed":
                                logger.error(f"Job {job_id} failed: {result['data']}")
                                logger.info(f"Job{job_id} 任务失败，等待30秒后执行下一条case")
                                time.sleep(30)  # 任务失败后等待30秒
                                # 返回包含失败信息的字典，包含失败的具体原因
                                return {
                                    "status": "failed",
                                    "data": result['data'],
                                    "error_reason": result['data'],  # 失败原因
                                    "job_id": job_id
                                }
                            
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
                # 检查是否超过了流式超时时间
                if time.time() - last_stream_time >= stream_timeout:
                    err_msg = f"CTTVError: Stream timeout: No response received for {stream_timeout} seconds for job {job_id}"
                    logger.error(err_msg)
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
                    return err_msg
                # 检查是否超过总体超时时间
                elif time.time() - start_time >= timeout:
                    logger.error(f"Overall timeout waiting for job {job_id} result after {timeout} seconds")
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
                    return "CTTVError: Request Timeout"

        logger.error(f"Overall timeout waiting for job {job_id} result after {timeout} seconds")
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
        return "CTTVError: Request Timeout"
    # ========================================
    # 资源清理
    # ========================================
    def cleanup(self):
        """Clean up resources"""
        with self.lock:
            if self.client_handle:
                logger.info("Disconnecting...")
                self.sdk.quantum_disconnect(self.client_handle)
                self.sdk.quantum_release_client(self.client_handle)
                self.client_handle = None
                self.connected = False
                logger.info("Cleanup completed")
