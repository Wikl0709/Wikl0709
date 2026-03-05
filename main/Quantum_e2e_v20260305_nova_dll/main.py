"""
Quantum E2E 测试主入口：解析参数、初始化上下文与 SDK、执行主流程、收尾打包。
"""
import json
import os
import sys
import time
from pathlib import Path

from loguru import logger

# 与原有脚本一致：以项目根为工作目录，保证 utils、common 等可导入
sys.stdout.reconfigure(encoding='utf-8')

from utils.getDeviceInfo import getDeviceInfo
import close_openwifi
import packageLog
from combined_analysis import process_excel
import analysis_log_local

from common.run_context import (
    init_run_context,
    setup_logging,
    OUTPUT_ROOT,
    set_runtime_config,
)
from common.paths import find_quantum_sdk_dll_simple, get_quantum_core_path
from common.quantum_sdk import load_quantum_sdk
from common.quantum_client_manager import (
    QuantumClientManager,
    set_quantum_client_manager,
    get_quantum_client_manager,
)
from common.main_process import run_quantum_e2e_process
from common.bundle import create_output_bundle_zip
from common.multimodal_api import MultimodalAPI


def main():
    import argparse

    parser = argparse.ArgumentParser(description='API Test')
    parser.add_argument('--excel_dir', type=str, default=r"C:\Users\woel0\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260203_nova_dll\dataset\EN_memory_v8\Memory_v9_KBQA_Filesearch_v20250210.xlsx", help='Excel文件目录路径')
    parser.add_argument('--image_dir', type=str, default=r"C:\Users\woel0\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260203_nova_dll\dataset\EN_memory_v8\Image_v9_260210", help='pathlist 图片目录')
    parser.add_argument('--doc_dir', type=str, default=r"C:\Users\woel0\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260203_nova_dll\dataset\EN_memory_v8\EN_KBQA", help='文档注册路径')
    parser.add_argument('--memory_excel', type=str, default=r"C:\Users\woel0\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20260203_nova_dll\dataset\EN_memory_v8\Memory_data _v9_260201_en.xlsx", help='Memory 注册 Excel 路径')
    parser.add_argument('--process_memory', action='store_true', default=True, help='处理 Memory 数据')
    parser.add_argument('--process_document', action='store_true', default=True, help='处理文档注册')
    parser.add_argument('--process_main', action='store_true', default=False, help='处理主 Excel 文件')
    parser.add_argument('--process_all', action='store_true', default=False, help='执行完整流程')
    parser.add_argument('--cycle', type=int, default=1, help='循环轮数')
    parser.add_argument('--gpu_type', type=str, default="iGPU", choices=["dGPU", "iGPU", "aGPU"], help='GPU 类型')
    parser.add_argument('--test_mode', type=str, default="cloud", choices=["cloud", "local"], help='测试模式')
    parser.add_argument('--version_config', type=str, default="v20260226_1120-R73.25", help='config.json 的 version 字段')
    parser.add_argument('--test_mode_config', type=str, default="cloud", choices=["cloud", "local"], help='config.json 的 test_mode 字段')
    parser.add_argument('--filter_local_brain', type=str, default="yes", choices=["auto", "yes", "no"])
    parser.add_argument('--min_wait_time', type=float, default=5.0)
    parser.add_argument('--max_wait_time', type=float, default=10.0)
    parser.add_argument('--enable_random_wait', type=bool, default=True)
    parser.add_argument('--cleanup_after_run', action='store_true', default=False)

    args = parser.parse_args()

    # 使用 init_run_context 返回值，避免导入时的 OUTPUT_ROOT 仍为 None
    OUTPUT_ROOT = init_run_context(args.version_config)
    setup_logging(OUTPUT_ROOT)
    logger.info("程序启动参数: " + ", ".join([f"{k}={v}" for k, v in vars(args).items()]))

    # 生成 OUTPUT_ROOT 下 config.json
    try:
        original_config_path = Path(r"C:\config.json")
        original_config = {}
        if original_config_path.exists():
            with original_config_path.open("r", encoding="utf-8") as f:
                original_config = json.load(f) or {}
        else:
            logger.warning(f"原始配置文件不存在: {original_config_path}")

        new_config = {
            "version": args.version_config,
            "test_mode": args.test_mode_config,
        }
        if original_config.get("device_type") is not None:
            new_config["device_type"] = original_config["device_type"]
        if original_config.get("device_model") is not None:
            new_config["device_model"] = original_config["device_model"]

        device_info_str = getDeviceInfo()
        device_info = json.loads(device_info_str)
        new_config.update(device_info)

        output_config_path = OUTPUT_ROOT / "config.json"
        output_config_path.parent.mkdir(parents=True, exist_ok=True)
        with output_config_path.open("w", encoding="utf-8") as f:
            json.dump(new_config, f, ensure_ascii=False, indent=4)
        logger.info(f"新的配置文件已生成: {output_config_path}")
    except Exception as e:
        logger.error(f"生成新的 config.json 时出错: {e}")
        raise

    # 运行时配置，供 common 内模块使用
    set_runtime_config(
        EXCEL_DIR=args.excel_dir,
        IMAGE_DIR=Path(args.image_dir),
        doc_directory=args.doc_dir,
        MEMORY_EXCEL_PATH=args.memory_excel,
        CYCLE_COUNT=args.cycle,
        GPU_TYPE=args.gpu_type,
    )

    try:
        dll_path = find_quantum_sdk_dll_simple()
        logger.info(f"找到 quantum-sdk DLL 文件: {dll_path}")
        sdk = load_quantum_sdk(dll_path)
        quantum_client_manager = QuantumClientManager(sdk)
        set_quantum_client_manager(quantum_client_manager)
    except Exception as e:
        logger.error(f"Failed to load DLL: {e}")
        raise

    try:
        if getattr(args, 'test_mode', None) == "local":
            logger.info("检测到本地测试模式，准备关闭WiFi...")
            for retry in range(1, 4):
                try:
                    if close_openwifi.toggle_wifi("off"):
                        time.sleep(60)
                        logger.info("WiFi已成功关闭")
                        break
                    if retry == 3:
                        logger.error("关闭WiFi失败，程序退出")
                        sys.exit(1)
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"关闭WiFi出错: {e}")
                    if retry == 3:
                        sys.exit(1)
                    time.sleep(5)

        logger.info("初始化量子客户端...")
        quantum_client_manager.initialize()
        success, output_files = run_quantum_e2e_process(args)

        if success:
            logger.info("所有流程成功完成！")
            logger.info(f"生成了 {len(output_files)} 个输出文件: {output_files}")
            for i, fp in enumerate(output_files, 1):
                logger.info(f"  {i}. {fp}")

            if getattr(args, 'test_mode', None) == "local":
                logger.info("检测到本地测试模式，打开WiFi...")
                for retry in range(1, 4):
                    try:
                        if close_openwifi.toggle_wifi("on"):
                            time.sleep(60)
                            logger.info("WiFi已成功打开")
                            break
                        if retry == 3:
                            logger.error("打开WiFi失败，程序退出")
                            sys.exit(1)
                        time.sleep(5)
                    except Exception as e:
                        logger.error(f"打开WiFi出错: {e}")
                        if retry == 3:
                            sys.exit(1)
                        time.sleep(5)

            if (args.process_main or args.process_all) and str(getattr(args, "test_mode_config", "cloud")).lower() == "cloud":
                logger.info("处理在日志中获取 memory 和 kbqa 的 Retrieval 结果")
                quantum_core_path = get_quantum_core_path()
                if quantum_core_path:
                    for output_file in output_files:
                        if not os.path.exists(output_file):
                            continue
                        try:
                            process_excel(
                                excel_path=output_file,
                                log_dir=quantum_core_path,
                                output_path=output_file,
                                scene_filter=None,
                            )
                            logger.info(f"成功处理Excel文件: {output_file}")
                        except Exception as e:
                            logger.error(f"处理Excel文件时出错: {e}")

                if getattr(args, 'cleanup_after_run', False):
                    logger.info("根据参数清理所有数据...")
                    try:
                        api_instance = MultimodalAPI()
                        if api_instance.cleanup_all_data():
                            logger.info("数据清理完成")
                        else:
                            logger.error("数据清理部分失败")
                    except Exception as e:
                        logger.error(f"清理数据时发生错误: {e}")

        logger.info("开始打包日志...")
        packageLog.main(OUTPUT_ROOT)
        try:
            output_root_path = Path(OUTPUT_ROOT)
            target_zip = output_root_path / "PackageAllLogs.zip"
            zip_candidates = list(output_root_path.glob("*.zip"))
            non_target = [p for p in zip_candidates if p.resolve() != target_zip.resolve() and not p.name.startswith("TestResult_")]
            if non_target:
                zip_to_rename = max(non_target, key=lambda p: p.stat().st_mtime)
                zip_to_rename.replace(target_zip)
        except Exception as e:
            logger.error(f"重命名日志压缩包失败: {e}")
        logger.info("日志打包完成")

        if str(getattr(args, "test_mode_config", "cloud")).lower() == "local" and (args.process_main or args.process_all):
            try:
                logger.info("执行 analysis_log_local 日志解析...")
                analysis_log_local.main(str(OUTPUT_ROOT))
                logger.info("analysis_log_local 执行完成")
            except SystemExit as e:
                logger.error(f"analysis_log_local 触发 SystemExit，已捕获: {e}")
            except Exception as e:
                logger.error(f"调用 analysis_log_local 失败: {e}")

        if args.process_main or args.process_all:
            try:
                bundle_zip_path = create_output_bundle_zip(
                    Path(OUTPUT_ROOT),
                    str(getattr(args, "test_mode_config", "cloud")).lower(),
                    None,
                    str(getattr(args, "version_config", "")).strip(),
                )
                logger.info(f"总包zip已生成: {bundle_zip_path}")
            except Exception as e:
                logger.error(f"生成总包zip失败: {e}")
    except Exception as e:
        logger.error(f"主流程执行过程中出现错误: {e}")
    finally:
        logger.info("清理量子客户端资源...")
        get_quantum_client_manager().cleanup()
        input("执行完成，按回车键退出程序...")


if __name__ == "__main__":
    main()
