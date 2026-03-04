import os
import sys
sys.path.insert(0,os.path.dirname(__file__))
import psutil
import subprocess as sp
import pandas as pd
import pynvml
import threading
import time
from colorama import init
import logging
from contextlib import contextmanager
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
init(autoreset=True)


class SystemMonitor:
    """
    系统资源监控类，用于监控 CPU、GPU、内存等系统资源使用情况。

    该类支持多种硬件平台（如 dGPU, iGPU, aGPU, qcom）的资源监控，并提供启动/停止监控线程的方法。
    
    属性:
        process_name_list: 需要监控的进程名称列表。
        product_type: 产品类型，包括 dGPU、iGPU、aGPU、qcom。
        start_timestamp: 监控开始时间戳。
        threadFlag: 线程标志，控制线程是否运行。
        monitor_thread: 资源监控线程对象。
        logger: 日志记录器。

    方法:
        start_monitoring_resource: 启动指定类型的资源监控线程。
        stop_monitoring_resource: 停止当前运行的资源监控线程。
        get_pid_by_name: 获取指定名称的进程 PID。
        kill_monitored_processes: 终止所有被监控的进程。
        get_cpu_memory_disk_info: 获取系统整体 CPU、内存、磁盘使用情况。
        get_pid_cpu_memory_info: 获取指定 PID 的 CPU 和内存使用信息。
        run_command: 执行 PowerShell 命令并返回数值结果。
        get_iGPU_info: 获取集成 GPU 使用率和显存占用。
        get_aGPU_info: 获取 AMD GPU 使用率、显存和功耗。
        suppress_cpp_output: 上下文管理器，用于屏蔽 C++ 输出。
        monitor_aGPU: 监控 AMD GPU 资源并写入 CSV。
        monitor_qGPU: 监控 Qualcomm GPU 资源并写入 CSV。
        monitor_iGPU: 监控 Intel 集成 GPU 资源并写入 CSV。
        get_dGPU_info: 获取 NVIDIA GPU 显存、利用率、功耗等信息。
        monitor_dGPU: 监控 NVIDIA GPU 资源并写入 CSV。
        get_arm_power: 获取 ARM 平台下的 CPU/GPU 功耗。
        get_amd_power: 获取 AMD 平台下的 CPU 功耗。
        get_power: 获取通用平台下的 CPU/GPU 功耗。
        check_libraries: 检查相关库是否安装及硬件是否存在。
    """
    def __init__(self,process_name_list:list,product_type:str,start_timestamp:str,log_file_path:str)->None:
        """
        初始化 SystemMonitor 实例。

        参数:
            process_name_list: 需要监控的进程名称列表。
            product_type: 产品类型，包括 dGPU、iGPU、aGPU、qcom。
            start_timestamp: 监控开始时间戳。
            log_file_path: 日志文件路径。
        """
        self.process_name_list = process_name_list
        self.product_type = product_type
        self.start_timestamp = start_timestamp

        self.is_dxgi_installed = False
        self.is_directx12_installed = False

        self.is_npu_exist = False
        self.is_gpu_exist = False

        self.is_nvidia_gpu_exist = False
        self.is_amd_gpu_exist = False
        self.is_intel_gpu_exist = False
        self.is_qualcomm_gpu_exist = False
        self.search_hardware_gpu = True
        self.threadFlag = True
        self.monitor_thread = None
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(level = logging.INFO)
        handler = logging.FileHandler(log_file_path,encoding="utf-8")
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        if 'qcom' in product_type:
            # ARM架构：不导入任何包
            self.use_perfmonitor = False 
        elif 'aGPU'in product_type:
            # AMD架构：需要perfmonitor和CLR相关依赖
            import perfmonitor
            import clr
            script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
            dll_path = os.path.join(script_dir, 'LibreHardwareMonitorLib.dll')
            clr.AddReference(dll_path)
            from LibreHardwareMonitor import Hardware
            # 初始化硬件监控
            self.computer = Hardware.Computer()
            self.computer.IsCpuEnabled = True
            self.computer.IsGpuEnabled = True
            self.use_perfmonitor = True 
        else:
            # 其他架构（如NVIDIA/x86_64）：仅导入CLR和LibreHardwareMonitor
            self.use_perfmonitor = False 
            import clr
            script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
            dll_path = os.path.join(script_dir, 'LibreHardwareMonitorLib.dll')
            clr.AddReference(dll_path)
            from LibreHardwareMonitor import Hardware
            # 初始化硬件监控
            self.computer = Hardware.Computer()
            self.computer.IsCpuEnabled = True
            self.computer.IsGpuEnabled = True
        if self.use_perfmonitor:
            self.win_monitor = perfmonitor.PerfWinOSMonitor()
            self.amd_monitor = perfmonitor.PerfAMDMonitor()
            self.nvidia_monitor = perfmonitor.PerfNvidiaMonitor()
            self.perfmonitor = perfmonitor

    def start_monitoring_resource(self,write_csv):
        """
        启动资源监控线程，根据产品类型选择对应的监控函数。

        参数:
            write_csv: 输出资源数据的 CSV 文件路径。

        返回:
            threading.Thread: 启动的监控线程对象。
        """
        gpu_type = self.product_type
        # 重置标志并启动新线程（需确保monitor_dGPU/iGPU依赖此标志）
        self.threadFlag = True
        self.logger.info(write_csv)
        self.logger.info(f"Detected GPU type: {gpu_type}")  # 添加调试信息
        if gpu_type == 'dGPU':
            monitor_thread_target = self.monitor_dGPU
        elif gpu_type == 'iGPU':
            monitor_thread_target = self.monitor_iGPU
        elif gpu_type == "aGPU":
            monitor_thread_target = self.monitor_aGPU
            self.check_libraries()
        else:
            monitor_thread_target = self.monitor_qGPU

        self.logger.info(f"Selected monitor method: {monitor_thread_target.__name__}")  # 添加调试信息
        self.monitor_thread = threading.Thread(target=monitor_thread_target, args=(write_csv, self.start_timestamp))
        self.monitor_thread.start()
        self.logger.info(f"Monitor thread started: {self.monitor_thread.is_alive()}")  # 添加调试信息
        return self.monitor_thread 

    def stop_monitoring_resource(self):
        """
        停止正在运行的资源监控线程。

        参数:
            无

        返回:
            无
        """
        try:
            if self.monitor_thread is not None and self.monitor_thread.is_alive():
                self.threadFlag = False
                self.monitor_thread.join()
                self.logger.info(f"Monitor thread stopped: {self.monitor_thread.is_alive()}")  # 添加调试信息
        except Exception as e:
            self.logger.info(f"Error stopping monitor thread: {e}")

    ###============================================资源监控==============================================================
    def get_pid_by_name(self, process_name_list, start_timestamp):
        """
        获取与给定进程名匹配的所有进程 PID。

        参数:
            process_name_list: 需要查找的进程名称列表。
            start_timestamp: 过滤新启动的进程的时间戳。

        返回:
            dict: 进程名到 PID 列表的映射字典。
        """
        pid_dict = dict()
        for proc in psutil.process_iter(['name']):
            for process_name in process_name_list:
                if process_name.lower() in proc.info['name'].lower():
                    pid = proc.pid
                    if process_name == 'Python.exe':
                        process = psutil.Process(pid)
                        create_timestamp = int(process.create_time() * 1000)
                        if create_timestamp > start_timestamp + 1000:
                            if process_name not in pid_dict:
                                pid_dict[process_name] = []
                            if pid not in pid_dict[process_name]:
                                pid_dict[process_name].append(pid)
                    else:
                        if process_name not in pid_dict:
                            pid_dict[process_name] = []
                        if pid not in pid_dict[process_name]:
                            pid_dict[process_name].append(pid)
        return pid_dict
    

    def kill_monitored_processes(self):
        """
        终止所有被监控的进程。

        参数:
            无

        返回:
            无
        """
        # 获取需要监控的进程名对应的 PIDs
        pid_dict = self.get_pid_by_name(self.process_name_list, self.start_timestamp)

        for process_name, pids in pid_dict.items():
            for pid in pids:
                try:
                    # 检查 PID 是否存在
                    if psutil.pid_exists(pid):
                        process = psutil.Process(pid)
                        self.logger.info(f"Killing process: {process_name} with PID: {pid}")
                        process.kill()  # 终止进程
                        process.wait(timeout=3)  # 等待进程结束，最多等待3秒
                        self.logger.info(f"Process {pid} terminated successfully.")
                    else:
                        self.logger.info(f"Process with PID {pid} does not exist anymore.")
                except psutil.NoSuchProcess:
                    self.logger.info(f"Process with PID {pid} no longer exists.")
                except psutil.AccessDenied:
                    self.logger.info(f"Access denied when trying to kill process {pid}.")
                except Exception as e:
                    self.logger.info(f"Failed to kill process {pid}: {e}")

    def get_cpu_memory_disk_info(self):
        """
        获取系统整体 CPU、内存、磁盘使用情况。

        参数:
            无

        返回:
            tuple: (CPU 使用百分比, 内存使用 GB, 磁盘使用百分比)
        """
        cpu = psutil.cpu_percent(interval=1)
        memory_gb = round(psutil.virtual_memory().used / 1024 ** 3, 2)
        disk_usage = psutil.disk_usage('/')
        disk_usage_pect = round(disk_usage.percent, 2)
        return cpu, memory_gb, disk_usage_pect
    
    def get_pid_cpu_memory_info(self, pid_list):
        """
        获取指定 PID 列表中每个进程的 CPU 和内存使用情况。

        参数:
            pid_list: 进程 PID 列表。

        返回:
            tuple: (CPU 使用百分比列表, 内存使用 MB 列表)
        """
        cpu_pid_list = []
        memory_gb_pid_list = []
        for pid in pid_list:
            if pid != -1:
                process = psutil.Process(pid)
                memory_gb_pid = round(process.memory_info().rss / (1024 ** 2), 2)
                cpu_count = psutil.cpu_count()
                cpu_pid = round(process.cpu_percent(interval=1) / cpu_count, 2)
                cpu_pid_list.append(cpu_pid)
                memory_gb_pid_list.append(memory_gb_pid)
            else:
                cpu_pid_list.append(0)
                memory_gb_pid_list.append(0)
        return cpu_pid_list, memory_gb_pid_list
    
    def run_command(self, command):
        """
        执行 PowerShell 命令并返回数值结果。

        参数:
            command: PowerShell 命令字符串。

        返回:
            float: 命令执行结果。
        """
        val = sp.run(['powershell', '-Command', command], capture_output=True).stdout.decode("ascii")
        if val:
            array = val.strip().split('\r\n')
            result = 0
            for item in array:
                result = result + float(item.strip().replace(',', '.'))
            return result
        else:
            return 0
        
    def get_iGPU_info(self):
        """
        获取集成 GPU 使用率和显存占用。

        参数:
            无

        返回:
            tuple: (GPU 使用百分比, 显存使用 GB)
        """
        gpu_usage_total_cmd = r'(((Get-Counter "\GPU Engine(*engtype_3D)\Utilization Percentage").CounterSamples | where CookedValue).CookedValue | measure -sum).sum'
        gpu_pect = round(self.run_command(gpu_usage_total_cmd), 2)

        gpu_mem_total_cmd = r'(((Get-Counter "\GPU Process Memory(*)\Local Usage").CounterSamples | where CookedValue).CookedValue | measure -sum).sum'
        gpu_memory_gb = round(self.run_command(gpu_mem_total_cmd) / (1024 ** 3), 2)
        return gpu_pect,gpu_memory_gb
    
    def get_aGPU_info(self):
        """
        获取 AMD GPU 使用率、显存和功耗。

        参数:
            无

        返回:
            tuple: (GPU 使用百分比, 显存使用 GB, GPU 功耗)
        """
        gpu_info  = self.win_monitor.GetGPUInfo()
        gpu_memory_gb = 0
        gpu_pect = 0
        gpu_power = 0
        # 其次使用 AMD 封装
        if self.is_amd_gpu_exist and self.amd_monitor.InitializeADLX():
            with self.suppress_cpp_output():  # 仅屏蔽C++输出
                metrics = self.amd_monitor.GetAMDGPUCurrentInfo(0)
                gpu_memory_gb = round(metrics.systemGpuMetrics.gpuVRAM/1000.0, 2)
                gpu_pect = round(metrics.systemGpuMetrics.gpuUsage, 2)
                gpu_power = round(metrics.systemGpuMetrics.gpuPower,2)
        return gpu_pect, gpu_memory_gb,gpu_power
    
    @contextmanager
    def suppress_cpp_output(self):
        """
        上下文管理器：临时屏蔽 C++ 输出，不影响 Python print。

        参数:
            无

        返回:
            无
        """
        # 保存原始的stdout文件描述符（C++输出走这里）
        original_stdout_fd = 1  # stdout的文件描述符是1
        # 打开/dev/null（Windows上是nul）
        with open(os.devnull, 'w') as devnull:
            devnull_fd = devnull.fileno()
            # 备份当前stdout文件描述符
            saved_stdout_fd = os.dup(original_stdout_fd)
            try:
                # 重定向C++输出到/dev/null
                os.dup2(devnull_fd, original_stdout_fd)
                yield  # 在此范围内执行C++调用
            finally:
                # 恢复原始stdout
                os.dup2(saved_stdout_fd, original_stdout_fd)
                os.close(saved_stdout_fd)  # 关闭备份的fd

    def monitor_aGPU(self, filename, start_timestamp):
        """
        监控 AMD GPU 资源并周期性写入 CSV 文件。

        参数:
            filename: 输出 CSV 文件路径。
            start_timestamp: 开始时间戳。

        返回:
            无
        """
        process_name_list = self.process_name_list
        while self.threadFlag:
            resource_list = []
            cpu, memory_gb, disk_pect = self.get_cpu_memory_disk_info()
            gpu_pect, gpu_memory_gb,gpu_power = self.get_aGPU_info()
            cpu_power = self.get_amd_power()
            battery = psutil.sensors_battery()
            if battery is None:
                battery_pct = 0
            else:
                battery_pct = battery.percent

            pid_dict = self.get_pid_by_name(process_name_list, start_timestamp)
            pid_list = []
            for process_name in process_name_list:
                if process_name in pid_dict:
                    if len(pid_dict[process_name]) == 2:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                    else:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                            else:
                                pid_list.append(-1)
                else:
                    pid_list.append(-1)
            if pid_list != []:
                try:
                    cpu_pid_list, memory_gb_pid_list = self.get_pid_cpu_memory_info(pid_list)

                except:
                    cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                    memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

            else:
                cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

            cpu_pid = round(sum(cpu_pid_list), 2)
            memory_gb_pid = round(sum(memory_gb_pid_list) / 1024, 2)
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            timestamp = int(time.time() * 1000)
            data = [current_time, timestamp, cpu, memory_gb, gpu_pect, disk_pect,
                    cpu_pid, memory_gb_pid, gpu_memory_gb, cpu_power, gpu_power, battery_pct] + memory_gb_pid_list
            resource_list.append(data)

            result_df = pd.DataFrame(resource_list,
                                     columns=['time', 'timestamp', 'CPU %', 'Memory GB', 'GPU utilization %',
                                              'DiskIO %',
                                              'process CPU %', 'process Memory GB', 'GPU memory GB','CPU power','GPU power',
                                              'Battery %'] + process_name_list)
            if not os.path.exists(filename):
                result_df.to_csv(filename, index=False, mode='a+', header=True)
            else:
                result_df.to_csv(filename, index=False, mode='a+', header=False)


    def monitor_qGPU(self, filename, start_timestamp):
        """
        监控 Qualcomm GPU 资源并周期性写入 CSV 文件。

        参数:
            filename: 输出 CSV 文件路径。
            start_timestamp: 开始时间戳。

        返回:
            无
        """
        process_name_list = self.process_name_list
        while self.threadFlag:
            resource_list = []
            cpu, memory_gb, disk_pect = self.get_cpu_memory_disk_info()
            gpu_pect, gpu_memory_gb = self.get_iGPU_info()
            cpu_power, gpu_power = self.get_arm_power()
            battery = psutil.sensors_battery()
            if battery is None:
                battery_pct = 0
            else:
                battery_pct = battery.percent

            
            pid_dict = self.get_pid_by_name(process_name_list, start_timestamp)

            pid_list = []
            for process_name in process_name_list:
                if process_name in pid_dict:
                    if len(pid_dict[process_name]) == 2:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                    else:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                            else:
                                pid_list.append(-1)
                else:
                    pid_list.append(-1)
            if pid_list != []:
                try:
                    cpu_pid_list, memory_gb_pid_list = self.get_pid_cpu_memory_info(pid_list)

                except:
                    cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                    memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

            else:
                cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

            cpu_pid = round(sum(cpu_pid_list), 2)
            memory_gb_pid = round(sum(memory_gb_pid_list) / 1024, 2)
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            timestamp = int(time.time() * 1000)
            data = [current_time, timestamp, cpu, memory_gb, gpu_pect, disk_pect,
                    cpu_pid, memory_gb_pid, gpu_memory_gb, cpu_power, gpu_power, battery_pct] + memory_gb_pid_list
            resource_list.append(data)

            result_df = pd.DataFrame(resource_list,
                                     columns=['time', 'timestamp', 'CPU %', 'Memory GB', 'GPU utilization %',
                                              'DiskIO %',
                                              'process CPU %', 'process Memory GB', 'GPU memory GB','CPU power','GPU power',
                                              'Battery %'] + process_name_list)
            if not os.path.exists(filename):
                result_df.to_csv(filename, index=False, mode='a+', header=True)
            else:
                result_df.to_csv(filename, index=False, mode='a+', header=False)


    def monitor_iGPU(self, filename, start_timestamp):
        """
        监控 Intel 集成 GPU 资源并周期性写入 CSV 文件。

        参数:
            filename: 输出 CSV 文件路径。
            start_timestamp: 开始时间戳。

        返回:
            无
        """
        process_name_list = self.process_name_list
        while self.threadFlag:
            resource_list = []
            cpu, memory_gb, disk_pect = self.get_cpu_memory_disk_info()
            gpu_pect, gpu_memory_gb = self.get_iGPU_info()
            cpu_power, gpu_power = self.get_power()
            battery = psutil.sensors_battery()
            if battery is None:
                battery_pct = 0
            else:
                battery_pct = battery.percent

            
            pid_dict = self.get_pid_by_name(process_name_list, start_timestamp)
            pid_list = []
            for process_name in process_name_list:
                if process_name in pid_dict:
                    if len(pid_dict[process_name]) == 2:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                    else:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                            else:
                                pid_list.append(-1)
                else:
                    pid_list.append(-1)
            if pid_list != []:
                try:
                    cpu_pid_list, memory_gb_pid_list = self.get_pid_cpu_memory_info(pid_list)

                except:
                    cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                    memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

            else:
                cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

            cpu_pid = round(sum(cpu_pid_list), 2)
            memory_gb_pid = round(sum(memory_gb_pid_list) / 1024, 2)
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            timestamp = int(time.time() * 1000)
            data = [current_time, timestamp, cpu, memory_gb, gpu_pect, disk_pect,
                    cpu_pid, memory_gb_pid, gpu_memory_gb, cpu_power, gpu_power, battery_pct] + memory_gb_pid_list
            resource_list.append(data)

            result_df = pd.DataFrame(resource_list,
                                     columns=['time', 'timestamp', 'CPU %', 'Memory GB', 'GPU utilization %',
                                              'DiskIO %',
                                              'process CPU %', 'process Memory GB', 'GPU memory GB','CPU power','GPU power',
                                              'Battery %'] + process_name_list)
            if not os.path.exists(filename):
                result_df.to_csv(filename, index=False, mode='a+', header=True)
            else:
                result_df.to_csv(filename, index=False, mode='a+', header=False)
          
    def get_dGPU_info(self):
        """
        获取 NVIDIA GPU 显存、利用率、功耗、温度等信息。

        参数:
            无

        返回:
            tuple: (显存使用 GB, GPU 使用百分比, GPU 功耗, CPU 功耗, 温度)
        """
        gpu_power = 0
        cpu_power = 0
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        try:
            gpu_power = round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000, 2)
        except:
            
            self.computer.Open()
            for hardware in self.computer.Hardware:
                hardware.Update()  # 更新硬件信息
                hardware_type = str(hardware.HardwareType)      

                if 'GPU' in hardware_type.upper():
                    for sensor in hardware.Sensors:
                        if hasattr(sensor.SensorType, 'Power') :
                            if sensor.SensorType == sensor.SensorType.Power:
                                if "package" in sensor.Name.lower():   
                                    gpu_power = round(sensor.Value,2)
                                    break
                                elif "core" in sensor.Name.lower():
                                    gpu_power = round(sensor.Value,2)
                                    break
                                elif "power" in sensor.Name.lower():
                                    gpu_power = round(sensor.Value,2)
                                    break
                                else:
                                    gpu_power = 0
                                
                        else:
                            gpu_power = 0
        try:
            self.computer.Open()
            for hardware in self.computer.Hardware:
                hardware.Update()  # 更新硬件信息
                hardware_type = str(hardware.HardwareType)   
                if 'CPU' in hardware_type.upper():
                    for sensor in hardware.Sensors:
                        if hasattr(sensor.SensorType, 'Power') :
                            if sensor.SensorType == sensor.SensorType.Power:
                                if "package" in sensor.Name.lower():                  
                                    # current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                                    cpu_power = round(sensor.Value,2)
                                    break
                            else:
                                cpu_power = 0
                                
                        else:
                            cpu_power = 0
            self.computer.Close()
        except Exception as e:
            self.logger.info(e)
            cpu_power = 0

        try:
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_memory_gb = round(memory_info.used / 1024 ** 3, 2)
        except:
            gpu_memory_gb = 0

        try:
            gpu_utilization = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
        except:
            gpu_utilization = 0

        try:
            gpu_temp = pynvml.nvmlDeviceGetTemperature(handle, 0)
        except:
            gpu_temp = 0

        return gpu_memory_gb, gpu_utilization, gpu_power,cpu_power, gpu_temp
    
    def monitor_dGPU(self, filename, start_time):
        """
        监控 NVIDIA GPU 资源并周期性写入 CSV 文件。

        参数:
            filename: 输出 CSV 文件路径。
            start_time: 开始时间戳。

        返回:
            无
        """
        self.logger.info(f"threadFlag: {self.threadFlag}")
        process_name_list = self.process_name_list
        while self.threadFlag:
            resource_list = []
            cpu, memory_gb, disk_pect = self.get_cpu_memory_disk_info()
            gpu_memory_gb, gpu_utilization, gpu_power,cpu_power, gpu_temp = self.get_dGPU_info()
            battery = psutil.sensors_battery()
            if battery is None:
                battery_pct = 0
            else:
                battery_pct = battery.percent
            pid_dict = self.get_pid_by_name(process_name_list, start_time)
            # self.logger.info('pid_dict',pid_dict)
            pid_list = []
            for process_name in process_name_list:
                if process_name in pid_dict:
                    if len(pid_dict[process_name]) == 2:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                    else:
                        for pid in pid_dict[process_name]:
                            if pid not in pid_list:
                                pid_list.append(pid)
                            else:
                                pid_list.append(-1)
                else:
                    pid_list.append(-1)
            if pid_list != []:
                try:
                    cpu_pid_list, memory_gb_pid_list = self.get_pid_cpu_memory_info(pid_list)
                except:
                    cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                    memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            else:
                cpu_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
                memory_gb_pid_list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            cpu_pid = round(sum(cpu_pid_list), 2)
            memory_gb_pid = round(sum(memory_gb_pid_list) / 1024, 2)
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            timestamp = int(time.time() * 1000)
            data = [current_time, timestamp, cpu, memory_gb, gpu_memory_gb, gpu_utilization, disk_pect,
                    cpu_pid, memory_gb_pid, gpu_power,cpu_power, gpu_temp, battery_pct] + memory_gb_pid_list
            resource_list.append(data)

            result_df = pd.DataFrame(resource_list,
                                     columns=['time', 'timestamp', 'CPU %', 'Memory GB', 'GPU memory GB',
                                              'GPU utilization %', 'DiskIO %',
                                              'process CPU %', 'process Memory GB', 'GPU power',"CPU power",'GPU temp °C',
                                              'Battery %'] + process_name_list)

            if not os.path.exists(filename):
                result_df.to_csv(filename, index=False, mode='a+', header=True)
            else:
                result_df.to_csv(filename, index=False, mode='a+', header=False)

    def get_arm_power(self):
        """
        获取 ARM 平台下的 CPU 和 GPU 功耗。

        参数:
            无

        返回:
            tuple: (CPU 功耗, GPU 功耗)
        """
        cpu_power = 0
        gpu_power = 0

        # try:
        #     if self.search_hardware_gpu:
        #         self.computer.Open()
        #         for hardware in self.computer.Hardware:
        #             hardware.Update()  # 更新硬件信息
        #             hardware_type = str(hardware.HardwareType)   

        #             if 'CPU' in hardware_type.upper():
        #                 for sensor in hardware.Sensors:
        #                     if hasattr(sensor.SensorType, 'Power') :
        #                         if sensor.SensorType == sensor.SensorType.Power:
        #                             if "package" in sensor.Name.lower():                  
        #                                 # current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        #                                 cpu_power = round(sensor.Value,2)
        #                                 break
        #                         else:
        #                             cpu_power = 0
                                    
        #                     else:
        #                         cpu_power = 0

        #             if 'GPU' in hardware_type.upper():
        #                 if 'aGPU' in self.args.product and "AMD" not in hardware_type.upper():
        #                     continue
        #                 for sensor in hardware.Sensors:
        #                     if hasattr(sensor.SensorType, 'Power') :
        #                         if sensor.SensorType == sensor.SensorType.Power:
        #                             if "package" in sensor.Name.lower():   
        #                                 gpu_power = round(sensor.Value,2)
        #                                 break
        #                             elif "core" in sensor.Name.lower():
        #                                 gpu_power = round(sensor.Value,2)
        #                                 break
        #                             elif "power" in sensor.Name.lower():
        #                                 gpu_power = round(sensor.Value,2)
        #                                 break
        #                             else:
        #                                 gpu_power = 0
                                        
        #                     else:
        #                         gpu_power = 0
        #         self.computer.Close()
        # except Exception as e:
        #     self.search_hardware_gpu = False
        return cpu_power, gpu_power
    
    def get_amd_power(self):
        """
        获取 AMD 平台下的 CPU 功耗。

        参数:
            无

        返回:
            float: CPU 功耗
        """
        cpu_power = 0
        try:
            self.computer.Open()
            for hardware in self.computer.Hardware:
                hardware.Update()  # 更新硬件信息
                hardware_type = str(hardware.HardwareType)   

                if 'CPU' in hardware_type.upper():
                    for sensor in hardware.Sensors:
                        if hasattr(sensor.SensorType, 'Power') :
                            if sensor.SensorType == sensor.SensorType.Power:
                                if "package" in sensor.Name.lower():                  
                                    # current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                                    cpu_power = round(sensor.Value,2)
                                    break
                            else:
                                cpu_power = 0
                                
                        else:
                            cpu_power = 0

            self.computer.Close()
        except Exception as e:
            return cpu_power
        return cpu_power
    
    def get_power(self):
        """
        获取通用平台下的 CPU 和 GPU 功耗。

        参数:
            无

        返回:
            tuple: (CPU 功耗, GPU 功耗)
        """
        cpu_power = 0
        gpu_power = 0
        
        self.computer.Open()
        for hardware in self.computer.Hardware:
            hardware.Update()  # 更新硬件信息
            hardware_type = str(hardware.HardwareType)   

            if 'CPU' in hardware_type.upper():
                for sensor in hardware.Sensors:
                    if hasattr(sensor.SensorType, 'Power') :
                        if sensor.SensorType == sensor.SensorType.Power:
                            if "package" in sensor.Name.lower():                  
                                # current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                                cpu_power = round(sensor.Value,2)
                                break
                        else:
                            cpu_power = 0
                            
                    else:
                        cpu_power = 0

            if 'GPU' in hardware_type.upper():
                if 'aGPU' in self.product_type and "AMD" not in hardware_type.upper():
                    continue
                for sensor in hardware.Sensors:
                    if hasattr(sensor.SensorType, 'Power') :
                        if sensor.SensorType == sensor.SensorType.Power:
                            if "package" in sensor.Name.lower():   
                                gpu_power = round(sensor.Value,2)
                                break
                            elif "core" in sensor.Name.lower():
                                gpu_power = round(sensor.Value,2)
                                break
                            elif "power" in sensor.Name.lower():
                                gpu_power = round(sensor.Value,2)
                                break
                            else:
                                gpu_power = 0
                                
                    else:
                        gpu_power = 0


        self.computer.Close()
        return cpu_power, gpu_power


    def check_libraries(self):
        """
        检查相关库是否安装及硬件是否存在（如 DX12、NPU、GPU 类型等）。

        参数:
            无

        返回:
            无
        """
        # 检查相关库是否已安装
        if self.perfmonitor.XPUContextManager.IsLibraryInstalled("DXGI"):
            self.is_dxgi_installed = True

        if self.perfmonitor.XPUContextManager.IsDirectX12Installed():
            self.is_directx12_installed = True

        if self.win_monitor.IsNPUAvailable():
            self.is_npu_exist = True

        if self.win_monitor.IsGPUAvailable():
            self.is_gpu_exist = True

            if self.perfmonitor.XPUContextManager.IsIntelGPUInstalled():
                self.is_intel_gpu_exist = True

            if self.perfmonitor.XPUContextManager.IsQualcommGPUInstalled():
                self.is_qualcomm_gpu_exist = True

            if self.perfmonitor.XPUContextManager.IsNVMLInstalled():
                self.is_nvidia_gpu_exist = True

            if self.perfmonitor.XPUContextManager.IsADLInstalled():
                self.is_amd_gpu_exist = True