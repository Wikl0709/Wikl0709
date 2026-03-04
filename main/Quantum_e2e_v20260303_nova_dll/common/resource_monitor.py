"""
资源监控：启动/停止监控，将监控数据写入结果 Excel
"""
import os
from datetime import datetime
import time
import pandas as pd
import openpyxl
from loguru import logger

from common import run_context
import utils.monitor_util as memory


def start_resource_monitoring(gpu_type):
    """启动资源监控（运行时从 run_context 获取路径，避免导入时为 None）"""
    process_names = [
        'LenovoQiraCore.exe', 'LenovoQiraCore.exe',
        'mcpMgmtService.exe', 'mcpMgmtService.exe',
        'lenovo.pfm.pipe.exe',
        'file-index-service.exe', 'file-index-service.exe',
        'file-search-service.exe', 'file-search-service.exe',
    ]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_timestamp = int(time.time() * 1000)
    log_file_path = str(run_context.LOGS_DIR / f'resource_monitor_{timestamp}.log')
    resource_csv_path = str(run_context.RESOURCE_DIR / f'resource_{timestamp}.csv')

    monitor = memory.SystemMonitor(
        process_name_list=process_names,
        product_type=gpu_type,
        start_timestamp=str(start_timestamp),
        log_file_path=log_file_path
    )
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
        resource_df = pd.read_csv(resource_csv_path)

        if os.path.exists(excel_output_path):
            try:
                existing_workbook = openpyxl.load_workbook(excel_output_path)
                if 'resource' in existing_workbook.sheetnames:
                    with pd.ExcelWriter(excel_output_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
                        resource_df.to_excel(writer, sheet_name='resource', index=False)
                else:
                    with pd.ExcelWriter(excel_output_path, mode='a', engine='openpyxl') as writer:
                        resource_df.to_excel(writer, sheet_name='resource', index=False)
            except Exception as e:
                logger.warning(f"无法加载现有Excel文件，将重新创建: {e}")
                with pd.ExcelWriter(excel_output_path, engine='openpyxl') as writer:
                    resource_df.to_excel(writer, sheet_name='resource', index=False)
        else:
            with pd.ExcelWriter(excel_output_path, engine='openpyxl') as writer:
                resource_df.to_excel(writer, sheet_name='resource', index=False)

        logger.info(f"资源监控数据已保存到 {excel_output_path} 的 resource sheet中")
    except Exception as e:
        logger.error(f"保存资源监控数据失败: {e}")
        import traceback
        traceback.print_exc()
