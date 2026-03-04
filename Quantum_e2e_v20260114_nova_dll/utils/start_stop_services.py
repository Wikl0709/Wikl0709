import subprocess
import os
import time
import logging
from datetime import datetime
import re
import win32com.shell.shell as shell
import win32con
import psutil
import os
import time
import logging
def start_mcp_service(base_dir, logger):
    """
    使用 pywin32 库以管理员身份启动 mcpMgmtService.exe
    
    Args:
        service_dir: 服务目录路径
        logger: 日志记录器

    Returns:
        bool: 启动是否成功
    """
    service_dir = os.path.join(base_dir, "Lenovo.McpMgmtService")
    # 记录启动时间戳
    start_time = datetime.now()
    timestamp_str = start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    logger.info(f"开始启动 mcpMgmtService.exe，时间戳: {timestamp_str}")

    # 构建服务可执行文件路径
    mcp_executable = os.path.join(service_dir, "mcpMgmtService.exe")

    if not os.path.exists(mcp_executable):
        logger.error(f"mcpMgmtService.exe 不存在: {mcp_executable}")
        return False

    try:
        
        # 使用 ShellExecuteEx 以管理员身份运行
        shell.ShellExecuteEx(
            fMask=0,
            lpVerb="runas",              # 以管理员身份运行
            lpFile=mcp_executable,       # 要执行的文件
            lpParameters="",             # 参数
            lpDirectory=service_dir,     # 工作目录
            nShow=win32con.SW_SHOWNORMAL       # 隐藏窗口
        )

        # 等待服务启动（最多等待 120秒）
        wait_time = 120
        sleep_interval = 1
        attempts = 0

        while attempts < (wait_time // sleep_interval):
            attempts += 1
            time.sleep(sleep_interval)

            # 检查日志文件是否出现 "application ready event"
            if check_mcp_service_ready(service_dir, timestamp_str, logger):
                logger.info("mcpMgmtService.exe 启动成功")
                return True

        logger.error("mcpMgmtService.exe 启动超时")
        return False

    except Exception as e:
        logger.error(f"启动 mcpMgmtService.exe 失败: {e}")
        return False
def check_mcp_service_ready(service_dir, start_timestamp, logger):
    """
    检查mcpMgmtService.exe是否启动成功
    
    Args:
        service_dir: 服务目录路径
        start_timestamp: 启动时间戳
        logger: 日志记录器
    
    Returns:
        bool: 是否启动成功
    """
    # 获取当前用户名
    username = os.getlogin()
    log_dir = os.path.join("C:\\Users", username, "AppData\\Local", "mcp_mgmt_service")
    if not os.path.exists(log_dir):
        logger.warning(f"日志目录不存在: {log_dir}")
        return False
    # 查找最近的.log文件
    latest_log_file = None
    for file in os.listdir(log_dir):
        if file.endswith(".log"):
            file_path = os.path.join(log_dir, file)
            if latest_log_file is None or os.path.getmtime(file_path) > os.path.getmtime(latest_log_file):
                latest_log_file = file_path
    
    if latest_log_file is None:
        logger.warning("未找到日志文件")
        return False
    # 解析日志文件，查找application ready event
    try:
        with open(latest_log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # 转换时间戳为datetime对象用于比较
        start_datetime = datetime.strptime(start_timestamp, "%Y-%m-%d %H:%M:%S.%f")
        # 查找在启动时间戳之后且包含application ready event的日志
        target_line = None
        for line in lines:
            match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}', line)
            if match:
                log_timestamp_str = match.group()
                try:
                    log_datetime = datetime.strptime(log_timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
                    
                    # 检查日志时间是否在启动时间之后，并且包含application ready event
                    if log_datetime > start_datetime and "application ready event" in line.lower():
                        target_line = line
                        startup_duration = (log_datetime - start_datetime).total_seconds()
                        logger.info(f"找到在启动时间之后的application ready event: {target_line.strip()}")
                        logger.info(f"MCP服务启动时间: {startup_duration:.3f}秒 (从 {start_timestamp} 到 {log_timestamp_str})")
                        return True
                except ValueError:
                    continue
        
        if target_line:
            logger.info(f"找到application ready event: {target_line.strip()}")
            return True
        else:
            logger.info("未找到在启动时间之后的application ready event")
            return False
            
    except Exception as e:
        logger.error(f"解析日志文件失败: {e}")
        return False


def start_quantum_service(base_dir, logger):
    """
    使用 pywin32 库以管理员身份启动 com.lenovo.quantum.exe 服务
    
    Args:
        base_dir: 基础服务目录路径
        logger: 日志记录器
    
    Returns:
        bool: 启动是否成功
    """
    quantum_service_dir = os.path.join(base_dir, "com.lenovo.quantum")
    quantum_executable = os.path.join(quantum_service_dir, "com.lenovo.quantum.exe")
    
    if not os.path.exists(quantum_executable):
        logger.error(f"com.lenovo.quantum.exe不存在: {quantum_executable}")
        return False
    
    # 记录启动时间戳
    start_time = datetime.now()
    timestamp_str = start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    logger.info(f"开始启动 com.lenovo.quantum.exe，时间戳: {timestamp_str}")
    
    try:
        # 使用 ShellExecuteEx 以管理员身份运行
        shell.ShellExecuteEx(
            fMask=0,
            lpVerb="runas",              # 以管理员身份运行
            lpFile=quantum_executable,   # 要执行的文件
            lpParameters="",             # 参数
            lpDirectory=quantum_service_dir,  # 工作目录设置为量子服务目录
            nShow=win32con.SW_SHOWNORMAL # 显示窗口
        )
        
        # 等待服务启动（最多等待 120秒）
        wait_time = 120
        sleep_interval = 1
        attempts = 0

        while attempts < (wait_time // sleep_interval):
            attempts += 1
            time.sleep(sleep_interval)

            # 检查日志文件是否出现工具列表信息
            if check_quantum_service_ready(base_dir, timestamp_str, logger):
                logger.info("com.lenovo.quantum.exe 启动成功")
                return True
            

        logger.error("com.lenovo.quantum.exe 启动超时")
        return False
            
    except Exception as e:
        logger.error(f"启动com.lenovo.quantum.exe失败: {e}")
        return False
def check_quantum_service_ready(base_dir, start_timestamp, logger):
    """
    检查quantum_service是否启动成功，并提取工具列表信息
    
    Args:
        base_dir: 基础服务目录路径
        start_timestamp: 启动时间戳
        logger: 日志记录器
    
    Returns:
        bool: 是否启动成功
    """
    # 获取当前用户名
    username = os.getlogin()
    log_dir = os.path.join("C:\\Users", username, "AppData\\Local", "quantum_core")
    
    if not os.path.exists(log_dir):
        logger.warning(f"量子服务日志目录不存在: {log_dir}")
        return False
    
    # 查找最近的.log文件
    latest_log_file = None
    for file in os.listdir(log_dir):
        if file.endswith(".log"):
            file_path = os.path.join(log_dir, file)
            if latest_log_file is None or os.path.getmtime(file_path) > os.path.getmtime(latest_log_file):
                latest_log_file = file_path
    
    if latest_log_file is None:
        logger.warning("未找到量子服务日志文件")
        return False
    
    # 解析日志文件，查找== ToolSize ==信息
    try:
        with open(latest_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        start_datetime = datetime.strptime(start_timestamp, "%Y-%m-%d %H:%M:%S.%f")
        
        # 查找启动时间之后的所有== ToolSize ==行，记录工具数量最多的那一个
        max_tools_count = -1
        best_tool_list_line = None
        best_tool_size = None
        
        # 从后往前查找最新的== ToolSize ==行
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            # 检查是否有时间戳
            match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}', line)
            if match:
                log_timestamp_str = match.group()
                try:
                    log_datetime = datetime.strptime(log_timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
                    
                    # 检查日志时间是否在启动时间之后
                    if log_datetime > start_datetime and " == ToolSize == " in line:
                        # 找到== ToolSize ==行，获取上一行的工具列表
                        if i > 0:
                            tool_list_line = lines[i-1].strip()
                            tool_size_str = line.split(" == ToolSize == ")[1].strip()
                            try:
                                tool_size = int(tool_size_str)
                                # 检查是否是目前找到的工具数量最多的记录
                                if tool_size > max_tools_count:
                                    max_tools_count = tool_size
                                    best_tool_list_line = tool_list_line
                                    best_tool_size = tool_size_str
                            except ValueError:
                            
                                continue
                except ValueError:
                    continue
        
        if best_tool_list_line is not None:
            logger.info(f"找到在启动时间之后工具数量最多的工具列表信息: {best_tool_list_line}")
            logger.info(f"工具数量: {best_tool_size}")
            # 尝试解析工具列表
            if '[' in best_tool_list_line and ']' in best_tool_list_line:
                # 提取方括号中的内容
                tools_str = best_tool_list_line[best_tool_list_line.find('['):best_tool_list_line.rfind(']')+1]
                try:
                    tools_list = tools_str.replace('[', '').replace(']', '').split(', ')
                    tools_list = [tool.strip().strip('\'"') for tool in tools_list if tool.strip()]
                    logger.info(f"检测到 {len(tools_list)} 个工具: {tools_list}")
                except Exception as e:
                    logger.info(f"解析工具列表失败: {e}")
            return True
        else:
            logger.info("未找到在启动时间之后的工具列表信息")
            return False
            
    except Exception as e:
        logger.error(f"解析量子服务日志文件失败: {e}")
        return False
def check_quantum_service_running(logger):
    """
    检查量子服务是否正在运行
    
    Args:
        logger: 日志记录器
    
    Returns:
        bool: 是否正在运行
    """
    required_processes = [
        'com.lenovo.quantum.exe',
        'mcpMgmtService.exe',
        'lenovo.pfm.pipe.exe'
    ]
    
    # 获取当前所有进程
    try:
        result = subprocess.run(['tasklist'], capture_output=True, text=True)
        processes = result.stdout.lower()
        
        # 检查每个必需的进程
        running_processes = []
        for process in required_processes:
            if process.lower() in processes:
                running_processes.append(process)
        
        # 检查是否所有必需进程都在运行
        if len(running_processes) == len(required_processes):
            logger.info(f"所有必需进程正在运行: {running_processes}")
            return True
        else:
            missing_processes = [p for p in required_processes if p not in running_processes]
            logger.warning(f"缺少以下进程: {missing_processes}")
            return False
            
    except Exception as e:
        logger.error(f"检查进程状态失败: {e}")
        return False
def start_services(base_dir, logger):
    """
    启动所有服务的主函数
    
    Args:
        service_dir: 服务目录路径
        logger: 日志记录器
    
    Returns:
        bool: 所有服务是否启动成功
    """
    logger.info(f"开始启动服务，服务目录: {base_dir}")
    
    # 启动mcpMgmtService.exe
    if not start_mcp_service(base_dir, logger):
        logger.error("mcpMgmtService.exe启动失败")
        return False
    
    # 启动com.lenovo.quantum.exe
    if not start_quantum_service(base_dir, logger):
        logger.error("com.lenovo.quantum.exe启动失败")
        return False
    
    logger.info("所有服务启动成功")
    return True


def stop_services(logger):
    """
    使用psutil库停止所有相关服务进程
    
    Args:
        logger: 日志记录器
    
    Returns:
        bool: 是否成功停止所有服务
    """
    required_processes = [
        'com.lenovo.quantum.exe',
        'mcpMgmtService.exe',
        'lenovo.pfm.pipe.exe','fileSearch.exe'
    ]
    
    try:
        # 查找需要终止的进程
        processes_to_kill = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                process_name = proc.info['name'].lower()
                for target_process in required_processes:
                    if target_process.lower() == process_name:
                        processes_to_kill.append({
                            'name': target_process,
                            'pid': proc.info['pid'],
                            'process': proc
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # 只输出找到的进程列表
        if processes_to_kill:
            found_processes = [f"{p['name']} (PID: {p['pid']})" for p in processes_to_kill]
            logger.info(f"找到需要终止的进程: {found_processes}")
        else:
            logger.info("未找到需要终止的服务进程")
            return True
        
        # 终止进程
        for proc_info in processes_to_kill:
            try:
                process = psutil.Process(proc_info['pid'])
            
                process.terminate()
            except psutil.NoSuchProcess:
                pass
            except psutil.AccessDenied:
                try:
                    process = psutil.Process(proc_info['pid'])
                    process.kill()
                except Exception:
                    pass
            except Exception:
                pass
        time.sleep(2)
        
        # 检查是否所有进程都已终止，如果还有进程在运行，尝试再次强制终止
        for proc_info in processes_to_kill:
            try:
                process = psutil.Process(proc_info['pid'])
                if process.is_running():
                    try:
                        process.kill()
                    except Exception:
                        pass
            except psutil.NoSuchProcess:
                pass
            except psutil.AccessDenied:
                pass
        
        # 最终验证
        time.sleep(1)
        remaining_processes = []
        for proc_info in processes_to_kill:
            try:
                process = psutil.Process(proc_info['pid'])
                if process.is_running():
                    remaining_processes.append(f"{proc_info['name']} (PID: {proc_info['pid']})")
            except psutil.NoSuchProcess:
                pass
            except psutil.AccessDenied:
                pass
        
        if remaining_processes:
            logger.error(f"最终仍有以下进程未终止: {remaining_processes}")
            return False
        else:
            logger.info("所有服务进程已成功终止")
            return True
            
    except Exception as e:
        logger.error(f"停止服务进程失败: {e}")
        return False
    


