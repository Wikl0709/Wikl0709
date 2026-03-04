# common 包：量子 E2E 测试公共模块
from common.run_context import (
    RUN_ID,
    OUTPUT_ROOT,
    LOGS_DIR,
    RESOURCE_DIR,
    TEST_RESULTS_DIR,
    REGISTERED_DOCS_PATH,
    init_run_context,
    setup_logging,
    get_config,
    set_runtime_config,
    set_doc_details_path,
    get_doc_details_path,
)

__all__ = [
    "RUN_ID",
    "OUTPUT_ROOT",
    "LOGS_DIR",
    "RESOURCE_DIR",
    "TEST_RESULTS_DIR",
    "REGISTERED_DOCS_PATH",
    "init_run_context",
    "setup_logging",
    "get_config",
    "set_runtime_config",
    "set_doc_details_path",
    "get_doc_details_path",
]
