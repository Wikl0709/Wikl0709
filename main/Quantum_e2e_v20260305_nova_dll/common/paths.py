"""
路径工具：查找 quantum-sdk DLL、quantum_core 日志目录等
"""
from pathlib import Path
from loguru import logger


def find_quantum_sdk_dll_simple():
    """
    简单查找 quantum-sdk DLL 文件
    """
    user_home = Path.home()
    possible_paths = [
        user_home / 'AppData' / 'Local' / 'Lenovo' / 'Qira' / 'QuantumApp' / 'QuantumApp',
        user_home / 'AppData' / 'Local' / 'Lenovo' / 'Qira' / 'QuantumApp',
        user_home / 'AppData' / 'Local' / 'Lenovo' / 'Qira',
        user_home / 'AppData' / 'Local' / 'Lenovo',
    ]

    for path in possible_paths:
        if path.exists():
            for dll_file in path.glob('quantum-sdk-*.dll'):
                return str(dll_file)
            for dll_file in path.rglob('quantum-sdk-*.dll'):
                return str(dll_file)

    logger.info("在常规路径未找到 DLL，尝试备选路径...")
    backup_path = Path(r"C:\Program Files\Lenovo\Lenovo Qira\QuantumApp")
    if backup_path.exists():
        for dll_file in backup_path.glob('quantum-sdk-*.dll'):
            return str(dll_file)

    raise FileNotFoundError("无法找到 quantum-sdk DLL 文件")


def get_quantum_core_path():
    """
    获取 Lenovo Qira 日志目录路径。
    Returns:
        str: 日志目录路径，不存在则返回 None
    """
    try:
        user_home = Path.home()
        quantum_core_path = user_home / 'AppData' / 'Local' / 'Lenovo' / 'Lenovo Qira' / 'Log'
        if quantum_core_path.exists():
            logger.info(f"找到 quantum_core 路径: {quantum_core_path}")
            return str(quantum_core_path)
        logger.warning(f"quantum_core 路径不存在: {quantum_core_path}")
        return None
    except Exception as e:
        logger.error(f"获取 quantum_core 路径时发生错误: {e}")
        return None
