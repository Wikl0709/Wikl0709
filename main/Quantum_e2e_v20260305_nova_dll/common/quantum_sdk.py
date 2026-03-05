"""
量子 SDK：加载 DLL 并绑定 ctypes 函数与回调类型
"""
import ctypes
from ctypes import CFUNCTYPE, c_int, c_long, c_char_p, POINTER, Structure, c_void_p


# 回调类型
ConnectionStatusCallback = CFUNCTYPE(None, c_int)
ResultCallback = CFUNCTYPE(None, c_void_p)


class DataContainer(Structure):
    _fields_ = [("pinned", c_void_p)]


class InputData(Structure):
    _fields_ = [("pinned", c_void_p)]


def load_quantum_sdk(dll_path: str):
    """
    加载 quantum-sdk DLL 并返回包含所有 API 的命名空间对象。
    调用方可将此对象传入 QuantumClientManager(sdk)。
    """
    quantum_sdk = ctypes.CDLL(dll_path)

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

    class SDK:
        pass

    sdk = SDK()
    sdk.ConnectionStatusCallback = ConnectionStatusCallback
    sdk.ResultCallback = ResultCallback
    sdk.quantum_create_blob_data = quantum_create_blob_data
    sdk.quantum_create_data_container = quantum_create_data_container
    sdk.quantum_create_input_data = quantum_create_input_data
    sdk.quantum_get_client = quantum_get_client
    sdk.quantum_connect = quantum_connect
    sdk.quantum_send_command = quantum_send_command
    sdk.quantum_disconnect = quantum_disconnect
    sdk.quantum_release_client = quantum_release_client
    sdk.quantum_free_string = quantum_free_string
    sdk.quantum_free_ref = quantum_free_ref
    sdk.quantum_output_get_job_id = quantum_output_get_job_id
    sdk.quantum_output_get_status = quantum_output_get_status
    sdk.quantum_output_get_data = quantum_output_get_data
    sdk.quantum_data_get_text = quantum_data_get_text
    return sdk
