"""
运行上下文：输出目录、日志、运行时配置（Excel/文档路径等）
"""
import os
import re
import sys
from pathlib import Path
from loguru import logger

# 脚本所在目录
script_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent

# 运行上下文（由 init_run_context 初始化）
RUN_ID = None
OUTPUT_ROOT = None
LOGS_DIR = None
RESOURCE_DIR = None
TEST_RESULTS_DIR = None
REGISTERED_DOCS_PATH = None

# 运行时配置（由 main 从 args 设置）
_runtime_config = {}
# 文档注册详情路径（由 MultimodalAPI.save_document_details_to_excel 设置）
_doc_details_path = None


def _sanitize_run_id(run_id: str) -> str:
    """
    使 RUN_ID 可安全用作目录名。
    Windows 不允许: <>:"/\\|?*，且末尾不能是空格/点。
    """
    s = (run_id or "").strip()
    if not s:
        s = "Quantum_e2e_TestResult"
    s = re.sub(r'[<>:"/\\|?*]+', "_", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip(" .")
    return s or "Quantum_e2e_TestResult"


def init_run_context(version_config: str):
    """
    初始化本次运行的输出目录结构。
    RUN_ID 使用 version_config 的值（用于输出目录名）。
    """
    global RUN_ID, OUTPUT_ROOT, LOGS_DIR, RESOURCE_DIR, TEST_RESULTS_DIR, REGISTERED_DOCS_PATH

    RUN_ID = _sanitize_run_id(version_config)
    OUTPUT_ROOT = script_dir / "outputs" / f"run_{RUN_ID}"
    LOGS_DIR = OUTPUT_ROOT / "logs"
    RESOURCE_DIR = OUTPUT_ROOT / "resource"
    TEST_RESULTS_DIR = OUTPUT_ROOT / "testresult"
    REGISTERED_DOCS_PATH = OUTPUT_ROOT / "registered_docs.json"

    for d in [OUTPUT_ROOT, LOGS_DIR, RESOURCE_DIR, TEST_RESULTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    return OUTPUT_ROOT


def setup_logging(output_dir):
    """设置 loguru 日志系统"""
    logger.remove()

    if output_dir is None:
        raise ValueError("setup_logging: output_dir 不能为 None，请先调用 init_run_context()")
    output_dir = Path(output_dir)
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    from datetime import datetime
    start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = logs_dir / f'Quantum_api_{start_timestamp}.log'

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


def set_runtime_config(**kwargs):
    """设置运行时配置（Excel 目录、图片目录、文档目录等）"""
    global _runtime_config
    _runtime_config.update(kwargs)


def get_config():
    """获取运行时配置字典"""
    return _runtime_config.copy()


def set_doc_details_path(path):
    global _doc_details_path
    _doc_details_path = path


def get_doc_details_path():
    return _doc_details_path
