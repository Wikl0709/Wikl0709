import ctypes
import json
from ctypes import c_long, c_int, c_char_p, c_void_p, CFUNCTYPE, POINTER

# 定义回调函数类型
ConnectionStatusDelegate = CFUNCTYPE(None, c_int)
ResultDelegate = CFUNCTYPE(None, c_void_p)

# 加载DLL
quantum_dll = ctypes.CDLL(r"C:\Users\woel0\AppData\Local\Lenovo\Qira\QuantumApp\quantum-sdk-1.0.10.dll")


# 定义结构体（Python中用ctypes结构体模拟）
class DataContainer(ctypes.Structure):
    _fields_ = [("pinned", c_void_p)]


class InputData(ctypes.Structure):
    _fields_ = [("pinned", c_void_p)]


# 函数原型定义
# quantum_create_blob_data
quantum_dll.quantum_create_blob_data.argtypes = [c_char_p, c_void_p, c_int]
quantum_dll.quantum_create_blob_data.restype = c_void_p

# quantum_create_data_container
quantum_dll.quantum_create_data_container.argtypes = [c_char_p, POINTER(c_void_p), c_int, c_char_p]
quantum_dll.quantum_create_data_container.restype = c_void_p

# quantum_create_input_data
quantum_dll.quantum_create_input_data.argtypes = [c_char_p, c_char_p, c_long, c_void_p]
quantum_dll.quantum_create_input_data.restype = c_void_p

# quantum_get_client
quantum_dll.quantum_get_client.argtypes = []
quantum_dll.quantum_get_client.restype = c_long

# quantum_connect
quantum_dll.quantum_connect.argtypes = [c_long, ConnectionStatusDelegate, ResultDelegate, c_char_p]
quantum_dll.quantum_connect.restype = c_int

# quantum_send_command
quantum_dll.quantum_send_command.argtypes = [c_long, c_void_p]
quantum_dll.quantum_send_command.restype = c_long

# quantum_disconnect
quantum_dll.quantum_disconnect.argtypes = [c_long]
quantum_dll.quantum_disconnect.restype = c_int

# quantum_release_client
quantum_dll.quantum_release_client.argtypes = [c_long]
quantum_dll.quantum_release_client.restype = None

# quantum_free_string
quantum_dll.quantum_free_string.argtypes = [c_void_p]
quantum_dll.quantum_free_string.restype = None

# quantum_free_ref
quantum_dll.quantum_free_ref.argtypes = [c_void_p]
quantum_dll.quantum_free_ref.restype = None

# quantum_output_get_job_id
quantum_dll.quantum_output_get_job_id.argtypes = [c_void_p]
quantum_dll.quantum_output_get_job_id.restype = c_long

# quantum_output_get_status
quantum_dll.quantum_output_get_status.argtypes = [c_void_p]
quantum_dll.quantum_output_get_status.restype = c_void_p

# quantum_output_get_data
quantum_dll.quantum_output_get_data.argtypes = [c_void_p]
quantum_dll.quantum_output_get_data.restype = c_void_p

# quantum_data_get_text
quantum_dll.quantum_data_get_text.argtypes = [c_void_p]
quantum_dll.quantum_data_get_text.restype = c_void_p

# quantum_data_get_binary_count
quantum_dll.quantum_data_get_binary_count.argtypes = [c_void_p]
quantum_dll.quantum_data_get_binary_count.restype = c_int

# quantum_data_get_binary_at
quantum_dll.quantum_data_get_binary_at.argtypes = [c_void_p, c_int]
quantum_dll.quantum_data_get_binary_at.restype = c_void_p

# quantum_data_get_uri_count
quantum_dll.quantum_data_get_uri_count.argtypes = [c_void_p]
quantum_dll.quantum_data_get_uri_count.restype = c_int

# quantum_data_get_uri_at
quantum_dll.quantum_data_get_uri_at.argtypes = [c_void_p, c_int]
quantum_dll.quantum_data_get_uri_at.restype = c_void_p

# quantum_blob_get_mime
quantum_dll.quantum_blob_get_mime.argtypes = [c_void_p]
quantum_dll.quantum_blob_get_mime.restype = c_void_p

# quantum_blob_get_size
quantum_dll.quantum_blob_get_size.argtypes = [c_void_p]
quantum_dll.quantum_blob_get_size.restype = c_int

# quantum_blob_get_data
quantum_dll.quantum_blob_get_data.argtypes = [c_void_p]
quantum_dll.quantum_blob_get_data.restype = c_void_p

# 全局变量保存回调函数和客户端句柄（防止GC回收）
_status_callback = None
_result_callback = None
_client_handle = 0


def on_connection_status(status):
    """连接状态回调函数"""
    status_map = {
        0: "Unknown",
        1: "Connected",
        2: "Disconnected",
        3: "Error",
        4: "Died"
    }
    status_name = status_map.get(status, f"Unknown({status})")
    print(f"Connection status: {status_name}")

    if status == 1:  # 已连接，发送测试请求
        print("Client connected")

        # 发送capabilities请求
        data_container = quantum_dll.quantum_create_data_container(
            None,
            (c_void_p * 0)(),  # 空数组
            0,
            None
        )
        input_data = quantum_dll.quantum_create_input_data(
            b"capabilities",
            b"",
            -1,
            data_container
        )
        job_id = quantum_dll.quantum_send_command(_client_handle, input_data)
        quantum_dll.quantum_free_ref(data_container)
        quantum_dll.quantum_free_ref(input_data)
        print(f"Capabilities job ID: {job_id}")



        # 发送模型调用请求
        # prompt_text = json.dumps({
        #     "modelName": "gpt",
        #     "modelVersion": "gpt-4.1-nano",
        #     "prompt": "hello"
        # }).encode("utf-8")

        # prompt_text = json.dumps({
        #     # "modelName": "gpt",
        #     # "modelVersion": "gpt-4.1-nano",
        #     "query": "hello",
        #     "handler":"nova",
        #     "sessionID": "1851aa89-e04d-4b63-967b-3155c604ba0c"
        # }).encode("utf-8")




        # file_paths = [
        #     r"C:\Users\obe\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251210_nova\files1114\test\yuzhixing.txt"]
        # prompt_text = json.dumps({
        # "action": "add",
        # "body": {
        # "doc_paths": file_paths,
        # "isTempFile": False}}).encode("utf-8")
        



        # prompt_text = json.dumps({
        #             "action": "list",
        #             "body": {
        #                 "folder_path": ''
        #             }
        #         }).encode("utf-8")

        # prompt_text = json.dumps({
        #     "query": "What is the users dream destinations?",
        #     "handler":"nova"
        #     # ,
        #     # "sessionID": "857165d1-dc93-46c4-8ba2-fa4f266d0886"
        # }).encode("utf-8")

        prompt_text = json.dumps({
               "action":"get_all_memory",
               "model":"lucene_AAITC-Emb_hybrid"
            }).encode("utf-8")
        
        data_container = quantum_dll.quantum_create_data_container(
            prompt_text,
            (c_void_p * 0)(),
            0,
            None
        )
        # input_data = quantum_dll.quantum_create_input_data(
        #     b"query",
        #     b"08259a4a-d332-442a-89d2-e7c118647010",
        #     -1,
        #     data_container
        # )
        input_data = quantum_dll.quantum_create_input_data(
            b"fkb_memory",
            b"",
            -1,
            data_container
        )
        query_job_id = quantum_dll.quantum_send_command(_client_handle, input_data)
        quantum_dll.quantum_free_ref(data_container)
        quantum_dll.quantum_free_ref(input_data)
        print(f"Query job ID: {query_job_id}")

def on_result(output_data_ptr):
    """结果回调函数"""
    if output_data_ptr is None or output_data_ptr == c_void_p(0):
        return

    try:
        # 获取Job ID
        job_id = quantum_dll.quantum_output_get_job_id(output_data_ptr)
        # 获取状态
        status_ptr = quantum_dll.quantum_output_get_status(output_data_ptr)
        status = ctypes.string_at(status_ptr).decode("utf-8") if status_ptr else ""
        print(f"Result: jobId={job_id}, status={status}")
        quantum_dll.quantum_free_string(status_ptr)

        # 获取数据容器
        data_ptr = quantum_dll.quantum_output_get_data(output_data_ptr)
        if data_ptr != c_void_p(0):
            # 获取文本数据
            text_ptr = quantum_dll.quantum_data_get_text(data_ptr)
            text = ctypes.string_at(text_ptr).decode("utf-8") if text_ptr else ""
            print(f"Data text: {text}")
            quantum_dll.quantum_free_string(text_ptr)
            quantum_dll.quantum_free_ref(data_ptr)
    finally:
        quantum_dll.quantum_free_ref(output_data_ptr)


def main():
    global _status_callback, _result_callback, _client_handle
    try:
        # 初始化客户端
        _client_handle = quantum_dll.quantum_get_client()
        if _client_handle == 0:
            print("Client initialization failed")
            return
        print("Client initialized successfully")

        # 注册回调函数
        _status_callback = ConnectionStatusDelegate(on_connection_status)
        _result_callback = ResultDelegate(on_result)

        # 连接服务器
        result = quantum_dll.quantum_connect(
            _client_handle,
            _status_callback,
            _result_callback,
            None
        )
        if result != 0:
            print(f"Failed to connect")
            quantum_dll.quantum_release_client(_client_handle)
            return

        print("Connected. Press Enter to exit...")
        input()  # 等待用户输入

        # 断开连接并释放资源
        quantum_dll.quantum_disconnect(_client_handle)
        quantum_dll.quantum_release_client(_client_handle)
    except Exception as ex:
        print(f"Error: {str(ex)}")


if __name__ == "__main__":
    main()