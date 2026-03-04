import json
import wmi
import ctypes
import locale
import socket

def getDeviceInfo():
    c = wmi.WMI()
    system_info = {}

    system_info["Language"] = locale.getdefaultlocale()[0]
    # 获取系统名字
    system_info["DeviceName"] = c.Win32_ComputerSystem()[0].Name

    # 获取所有MAC地址和IP地址
    mac_addresses = []
    ip_addresses = []
    
    for nic in c.Win32_NetworkAdapterConfiguration(IPEnabled=True):
        if nic.MACAddress:
            mac_addresses.append(nic.MACAddress)
        if nic.IPAddress:
            # IPAddress可能是一个列表，包含IPv4和IPv6地址
            for ip in nic.IPAddress:
                if ip not in ip_addresses:
                    ip_addresses.append(ip)
    
    system_info["IPAddresses"] = ip_addresses
    system_info["MACAddresses"] = mac_addresses
    
    # 也可以获取主机名对应的IP地址作为补充
    try:
        hostname = socket.gethostname()
        host_ip = socket.gethostbyname(hostname)
        system_info["HostIP"] = host_ip
    except Exception as e:
        system_info["HostIP"] = "Unable to get host IP"

    # 获取计算机序列号
    bios = c.Win32_BIOS()[0]
    # Better SN retrieval with validation
    try:
        bios = c.Win32_BIOS()[0]
        sn = bios.SerialNumber.strip() if bios.SerialNumber else ""
        
        # Check for invalid default values
        invalid_values = ["invalid", "to be filled by o.e.m.", "default string", "0", ""]
        if sn.lower() in invalid_values or len(sn) < 3:
            # Try alternative sources
            baseboard = c.Win32_BaseBoard()[0]
            sn = baseboard.SerialNumber.strip()
            
            if sn.lower() in invalid_values or len(sn) < 3:
                # Use combination of values or device name as fallback
                system_info["SN"] = system_info["DeviceName"]
            else:
                system_info["SN"] = sn
        else:
            system_info["SN"] = sn
        if sn == "INVALID":
            # Fallback to device name if SN is invalid
            system_info["SN"] = system_info["DeviceName"]
    except Exception as e:
        # Fallback to device name if any error occurs
        system_info["SN"] = system_info["DeviceName"]
    
    # 获取CPU信息
    cpu = c.Win32_Processor()[0]
    system_info["CPU"] = {
        "Name": cpu.Name.strip(),
        "NumberOfCores": cpu.NumberOfCores,
        "NumberOfLogicalProcessors": cpu.NumberOfLogicalProcessors
    }

    # 获取内存信息
    os = c.Win32_OperatingSystem()[0]
    total_memory_gb = round(float(os.TotalVisibleMemorySize) / 1024 / 1024, 2)
    free_memory_gb = round(float(os.FreePhysicalMemory) / 1024 / 1024, 2)
    system_info["Memory"] = {
        "Total": f"{total_memory_gb} GB"
    }

    # 获取显卡信息
    gpu_info = []
    for gpu in c.Win32_VideoController():
        if gpu.Name != 'OrayIddDriver Device':
            gpu_info.append({
                "Name": gpu.Name,
                "DriverVersion": gpu.DriverVersion,
                "AdapterRAM": f"{abs(float(ctypes.c_uint(gpu.AdapterRAM).value)) / 1024 / 1024 / 1024:.2f} GB" if gpu.AdapterRAM else "N/A"
            })
    system_info["GPU"] = gpu_info
    
    # 获取NPU信息
    npu_info = []
    # 检查设备管理器中的所有PCI设备
    for device in c.Win32_PnPEntity():

        device_name = device.Name if device.Name else ""
        # print(device_name)
        # 检查常见的NPU设备名称
        if any(npu_keyword in device_name.lower() for npu_keyword in [
            "neural", " npu "," ai ", "ai accelerator", "neural engine",
            "intel npu", "qualcomm ai engine", "neural processing",
            "microsoft pluton", "apple neural engine"
        ]):
            # print(device)
            npu_info.append({
                "Name": device_name,
                # "DeviceID": device.DeviceID if device.DeviceID else "N/A",
                "Status": device.Status if device.Status else "N/A"
            })
        device_Service = device.Service if device.Service else ""
        # print(device_Service)
        # 检查常见的NPU设备名称
        if any(npu_keyword in device_Service.lower() for npu_keyword in [
            "npu"
        ]):
            # print(device)
            npu_info.append({
                "Name": device.Name,
                # "DeviceID": device.DeviceID if device.DeviceID else "N/A",
                "Status": device.Status if device.Status else "N/A"
            })
    
    def remove_duplicates(dict_list):
        # 使用集合来存储唯一的字典
        seen = set()
        unique_dicts = []
        
        for d in dict_list:
            # 将字典转换为元组（可哈希类型）
            # 这里假设字典中的键值对顺序一致且键是字符串
            dict_tuple = tuple(sorted(d.items()))
            
            if dict_tuple not in seen:
                seen.add(dict_tuple)
                unique_dicts.append(d)
        
        return unique_dicts
    
    npu_info = remove_duplicates(npu_info)
    system_info["NPU"] = npu_info if npu_info else [{"Name": "No NPU detected", "Status": "N/A"}]

    return json.dumps(system_info, indent=2)


if __name__ == "__main__":
    print(getDeviceInfo())
