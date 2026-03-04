"""
主流程：run_quantum_e2e_process、merge_and_analyze_output_files
"""
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from loguru import logger

from common import run_context
from common.run_context import set_runtime_config, get_config
from common.resource_monitor import (
    start_resource_monitoring,
    stop_resource_monitoring,
    add_resource_data_to_results,
)
from common.multimodal_api import MultimodalAPI


def run_quantum_e2e_process(args):
    """
    运行 Quantum E2E 主流程逻辑。
    运行时配置（EXCEL_DIR, IMAGE_DIR, doc_directory, MEMORY_EXCEL_PATH, CYCLE_COUNT, GPU_TYPE）
    需由 main 在调用前通过 set_runtime_config 设置。
    """
    output_files_list = []
    overall_monitor = None
    overall_resource_csv_path = None
    cfg = get_config()
    EXCEL_DIR = cfg.get('EXCEL_DIR')
    CYCLE_COUNT = cfg.get('CYCLE_COUNT', 1)
    GPU_TYPE = cfg.get('GPU_TYPE', 'iGPU')

    try:
        should_start_overall_monitor = (
            (args.process_memory or args.process_document) and
            not (args.process_main or args.process_all)
        )
        should_start_combined_monitor = (
            args.process_memory and args.process_document and
            not (args.process_main or args.process_all)
        )
        should_start_pre_monitor = (
            (args.process_memory or args.process_document) and
            (args.process_main or args.process_all)
        )

        if should_start_overall_monitor or should_start_combined_monitor:
            overall_monitor, overall_resource_csv_path, _ = start_resource_monitoring(GPU_TYPE)
        elif should_start_pre_monitor and overall_resource_csv_path is None:
            pre_monitor, pre_resource_csv_path, _ = start_resource_monitoring(GPU_TYPE)

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
                if hasattr(memory_api, 'memory_output_path'):
                    memory_output_paths.append(memory_api.memory_output_path)
            else:
                logger.info("Memory数据处理失败")

        doc_output_paths = []
        if args.process_document:
            api = MultimodalAPI()
            success = api.process_document_registration_only()
            if success:
                doc_output_paths.extend(getattr(api, 'generated_files', []))

        if 'pre_monitor' in locals() and should_start_pre_monitor:
            stop_resource_monitoring(pre_monitor)

        excel_files = []
        if args.process_main or args.process_all:
            excel_path = Path(EXCEL_DIR) if EXCEL_DIR else None
            if not excel_path:
                logger.info("未配置 EXCEL_DIR，跳过主 Excel 处理")
            elif excel_path.is_file() and excel_path.suffix.lower() == '.xlsx':
                excel_files = [excel_path]
                logger.info(f"处理指定的Excel文件: {excel_path.name}")
            else:
                excel_files = list(excel_path.glob("*.xlsx"))
                if not excel_files:
                    logger.info(f"在目录 {EXCEL_DIR} 中未找到Excel文件")
                    return False, output_files_list
                logger.info(f"找到 {len(excel_files)} 个Excel文件")

        for excel_file in excel_files:
            logger.info(f"\n正在处理文件: {excel_file.name}")
            file_monitor = None
            file_resource_csv_path = None

            try:
                file_monitor, file_resource_csv_path, _ = start_resource_monitoring(GPU_TYPE)

                output_excel_path = os.path.join(
                    str(run_context.TEST_RESULTS_DIR),
                    f"test_results_{excel_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                )
                excel_file_path = str(excel_file)
                set_runtime_config(OUTPUT_EXCEL_PATH=output_excel_path, EXCEL_FILE_PATH=excel_file_path)

                api = MultimodalAPI()
                success = True
                if args.process_document:
                    success = api.process_document_registration_only()

                if success and args.process_main:
                    success = api.process_main_excel_only(
                        CYCLE_COUNT,
                        args.min_wait_time,
                        args.max_wait_time,
                        args.enable_random_wait
                    )

                if success:
                    logger.info(f"文件 {excel_file.name} 处理完成")
                    for cycle_index in range(CYCLE_COUNT):
                        cycle_output_path = output_excel_path.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
                        if os.path.exists(cycle_output_path):
                            output_files_list.append(cycle_output_path)
                else:
                    logger.info(f"文件 {excel_file.name} 处理失败")

            finally:
                try:
                    if file_monitor:
                        stop_resource_monitoring(file_monitor)
                    if file_resource_csv_path and os.path.exists(file_resource_csv_path):
                        current_output = get_config().get('OUTPUT_EXCEL_PATH') or output_excel_path
                        for cycle_index in range(CYCLE_COUNT):
                            try:
                                cycle_output_path = current_output.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
                                if os.path.exists(cycle_output_path):
                                    add_resource_data_to_results(file_resource_csv_path, cycle_output_path)
                            except Exception as e:
                                logger.error(f"添加资源数据失败: {e}")
                except Exception as e:
                    logger.error(f"资源清理过程中出现错误: {e}")

        if should_start_overall_monitor or should_start_combined_monitor:
            if overall_resource_csv_path and os.path.exists(overall_resource_csv_path):
                for memory_output_path in memory_output_paths:
                    if os.path.exists(memory_output_path):
                        add_resource_data_to_results(overall_resource_csv_path, memory_output_path)
                        logger.info(f"资源数据已添加到memory结果文件: {memory_output_path}")
                for doc_output_path in doc_output_paths:
                    if os.path.exists(doc_output_path):
                        add_resource_data_to_results(overall_resource_csv_path, doc_output_path)
                        logger.info(f"资源数据已添加到文档注册结果文件: {doc_output_path}")

        if should_start_pre_monitor and 'pre_resource_csv_path' in locals() and os.path.exists(pre_resource_csv_path):
            output_excel_path = get_config().get('OUTPUT_EXCEL_PATH') or ''
            for cycle_index in range(CYCLE_COUNT):
                try:
                    cycle_output_path = output_excel_path.replace('.xlsx', f'_cycle{cycle_index+1}.xlsx')
                    if os.path.exists(cycle_output_path):
                        add_resource_data_to_results(pre_resource_csv_path, cycle_output_path)
                        logger.info(f"预处理资源数据已添加到主Excel结果文件: {cycle_output_path}")
                except Exception as e:
                    logger.error(f"添加预处理资源数据失败: {e}")

    finally:
        if overall_monitor:
            stop_resource_monitoring(overall_monitor)

    return True, output_files_list


def merge_and_analyze_output_files(output_files):
    """
    合并多个 output_files 中的 .xlsx 文件，
    按 scene 分组计算 TTFT 和 Latency 的平均值（不过滤），
    generation_speed 只过滤 >=200 的值。
    并保存为 Latency_时间戳.xlsx
    """
    if isinstance(output_files, str):
        output_files = [output_files]

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

    merged_df = pd.concat(all_data, ignore_index=True)
    grouped = merged_df.groupby('scene')
    ttft_mean = grouped['ttft'].mean().round(2)
    latency_mean = grouped['response_time'].mean().round(2)
    gen_speed_filtered = merged_df[merged_df['generation_speed'] < 200]
    gen_speed_mean = gen_speed_filtered.groupby('scene')['generation_speed'].mean().round(2)

    result = pd.DataFrame({
        'Category': ttft_mean.index,
        'TTFT': ttft_mean.values,
        'Latency': latency_mean.values,
        'Generation_Speed': gen_speed_mean.values
    })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = os.path.dirname(output_files[0]) if output_files else os.getcwd()
    output_path = os.path.join(target_dir, f"Latency_{timestamp}.xlsx")
    result.to_excel(output_path, index=False)
    logger.info(f"性能统计结果已保存至: {output_path}")

    logger.info("\n性能统计结果:")
    for _, row in result.iterrows():
        logger.info(f"{row['Category']:<20} | TTFT: {row['TTFT']:<6.2f} | Latency: {row['Latency']:<6.2f} | GenSpeed: {row['Generation_Speed']:<6.2f}")
