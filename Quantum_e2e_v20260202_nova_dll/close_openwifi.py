#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WiFi控制工具
功能：通过Python脚本控制Windows系统的WiFi开关（需要管理员权限）
用法：
    python close_openwifi.py on   # 打开WiFi
    python close_openwifi.py off  # 关闭WiFi
"""

import subprocess
import ctypes
import sys
import argparse
import os
import time
from typing import Optional
from loguru import logger

# ===== 配置编码 =====
sys.stdout.reconfigure(encoding='utf-8')


# ===== 配置 logger =====
logger.remove()  # 移除默认配置
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
    colorize=True
)

# ===== 常量定义 =====
COMMON_INTERFACE_NAMES = [
    "WLAN", 
    "Wi-Fi", 
    "Wireless Network Connection",
    "无线网络连接", 
    "WIRELESS", 
    "wireless", 
    "WiFi"
]

POWERSHELL_TIMEOUT = 30  # PowerShell 命令超时时间（秒）
NETSH_TIMEOUT = 10       # netsh 命令超时时间（秒）


def is_admin() -> bool:
    """检查脚本是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_as_admin() -> None:
    """以管理员权限重新启动当前脚本"""
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, 
            "runas", 
            sys.executable, 
            " ".join([f'"{arg}"' if " " in arg else arg for arg in sys.argv]),
            None, 
            1
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"请求管理员权限失败: {e}")
        sys.exit(1)


def get_wifi_interface_name() -> Optional[str]:
    """
    获取WiFi接口名称
    
    Returns:
        str: WiFi接口名称，如果未找到返回 None
    """
    try:
        result = subprocess.run(
            "netsh wlan show interfaces",
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=NETSH_TIMEOUT,
            check=False
        )
        
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                # 支持中英文系统
                if "名称" in line or "Name" in line:
                    if ":" in line:
                        interface_name = line.split(":", 1)[1].strip()
                        if interface_name:
                            logger.debug(f"检测到WiFi接口: {interface_name}")
                            return interface_name
    except subprocess.TimeoutExpired:
        logger.warning("获取WiFi接口名称超时")
    except Exception as e:
        logger.debug(f"获取WiFi接口名称失败: {e}")
    
    return None


def toggle_wifi_netsh(state: str) -> bool:
    """
    使用netsh命令切换WiFi状态（方法1：尝试常见接口名）
    
    Parameters:
        state (str): "on" 或 "off"
        
    Returns:
        bool: 是否成功
    """
    status = "enabled" if state == "on" else "disabled"
    action_cn = "打开" if state == "on" else "关闭"
    
    # 首先尝试获取实际接口名
    actual_interface = get_wifi_interface_name()
    if actual_interface:
        interface_names = [actual_interface] + COMMON_INTERFACE_NAMES
    else:
        interface_names = COMMON_INTERFACE_NAMES
    
    for interface_name in interface_names:
        command = f'netsh interface set interface "{interface_name}" {status}'
        
        logger.debug(f"尝试接口: {interface_name}")
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                encoding="utf-8",
                timeout=NETSH_TIMEOUT,
                check=False
            )
            
            if result.returncode == 0:
                logger.success(f"✓ WiFi已{action_cn} (接口: {interface_name})")
                return True
            else:
                logger.debug(f"接口 {interface_name} 失败: 错误代码 {result.returncode}")
                
        except subprocess.TimeoutExpired:
            logger.warning(f"接口 {interface_name} 操作超时")
        except Exception as e:
            logger.debug(f"接口 {interface_name} 异常: {e}")
    
    return False


def toggle_wifi_powershell(state: str) -> bool:
    """
    使用PowerShell命令切换WiFi状态（方法2：通过网卡类型识别）
    
    Parameters:
        state (str): "on" 或 "off"
        
    Returns:
        bool: 是否成功
    """
    action = "Enable-NetAdapter" if state == "on" else "Disable-NetAdapter"
    action_cn = "打开" if state == "on" else "关闭"
    
    # 优化的PowerShell命令
    ps_command = f'''
    $ErrorActionPreference = 'Stop'
    try {{
        # 方法1: 通过InterfaceType查找 (71 = Wireless80211)
        $adapter = Get-NetAdapter | Where-Object {{ $_.InterfaceType -eq 71 -and $_.Status -ne 'Not Present' }} | Select-Object -First 1
        
        # 方法2: 如果方法1失败，通过名称和描述查找
        if (-not $adapter) {{
            $adapter = Get-NetAdapter | Where-Object {{ 
                ($_.Name -like "*Wi-Fi*" -or 
                 $_.Name -like "*WLAN*" -or 
                 $_.Name -like "*Wireless*" -or
                 $_.InterfaceDescription -like "*Wireless*" -or
                 $_.InterfaceDescription -like "*802.11*") -and
                $_.Status -ne 'Not Present'
            }} | Select-Object -First 1
        }}
        
        if ($adapter) {{
            $adapter | {action} -Confirm:$false
            Write-Output "SUCCESS:$($adapter.Name)"
        }} else {{
            Write-Output "ERROR:No wireless adapter found"
        }}
    }} catch {{
        Write-Output "ERROR:$($_.Exception.Message)"
    }}
    '''
    
    logger.debug("使用PowerShell方法")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=POWERSHELL_TIMEOUT,
            check=False
        )
        
        output = result.stdout.strip()
        
        if result.returncode == 0 and output.startswith("SUCCESS:"):
            interface_name = output.split(":", 1)[1]
            logger.success(f"✓ WiFi已{action_cn} (接口: {interface_name})")
            return True
        else:
            if "ERROR:" in output:
                error_msg = output.split(":", 1)[1]
                logger.debug(f"PowerShell失败: {error_msg}")
            else:
                logger.debug(f"PowerShell失败: {output}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.warning("PowerShell操作超时")
        return False
    except Exception as e:
        logger.debug(f"PowerShell异常: {e}")
        return False


def toggle_wifi_netsh_wlan(state: str) -> bool:
    """
    使用netsh wlan命令切换WiFi状态（方法3：先查询再操作）
    
    Parameters:
        state (str): "on" 或 "off"
        
    Returns:
        bool: 是否成功
    """
    action_cn = "打开" if state == "on" else "关闭"
    
    # 获取接口名称
    interface_name = get_wifi_interface_name()
    
    if not interface_name:
        logger.debug("未找到无线接口")
        return False
    
    # 执行启用/禁用操作
    action = "enable" if state == "on" else "disable"
    command = f'netsh interface set interface "{interface_name}" {action}'
    
    logger.debug(f"使用netsh wlan方法，接口: {interface_name}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=NETSH_TIMEOUT,
            check=False
        )
        
        if result.returncode == 0:
            logger.success(f"✓ WiFi已{action_cn} (接口: {interface_name})")
            return True
        else:
            logger.debug(f"netsh wlan失败: 错误代码 {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.warning("netsh wlan操作超时")
        return False
    except Exception as e:
        logger.debug(f"netsh wlan异常: {e}")
        return False


def verify_wifi_state(expected_state: str, max_retries: int = 3) -> bool:
    """
    验证WiFi状态是否符合预期
    
    Parameters:
        expected_state (str): 期望的状态 "on" 或 "off"
        max_retries (int): 最大重试次数
        
    Returns:
        bool: 状态是否符合预期
    """
    for i in range(max_retries):
        try:
            result = subprocess.run(
                "netsh wlan show interfaces",
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
                check=False
            )
            
            if result.returncode == 0:
                output = result.stdout.lower()
                
                if expected_state == "off":
                    # 检查是否没有活动连接
                    if "there is no wireless interface" in output or \
                       "没有无线接口" in output or \
                       not any(keyword in output for keyword in ["state", "状态"]):
                        return True
                else:  # expected_state == "on"
                    # 检查是否有活动接口
                    if "state" in output or "状态" in output:
                        return True
            
            if i < max_retries - 1:
                time.sleep(1)
                
        except Exception:
            if i < max_retries - 1:
                time.sleep(1)
    
    return False


def toggle_wifi(state: str) -> bool:
    """
    切换WiFi状态，按优先级尝试多种方法
    
    Parameters:
        state (str): "on" 或 "off"
        
    Returns:
        bool: 是否成功
    """
    if state not in ["on", "off"]:
        logger.error("错误：无效的状态。请使用 'on' 或 'off'")
        return False
    
    # 检查管理员权限
    if not is_admin():
        logger.warning("需要管理员权限，正在请求...")
        run_as_admin()
        return False  # 不会执行到这里
    
    action_cn = "打开" if state == "on" else "关闭"
    logger.info(f"正在{action_cn}WiFi...")
    
    # 方法列表
    methods = [
        ("增强netsh方法", toggle_wifi_netsh),
        ("PowerShell方法", toggle_wifi_powershell),
        ("netsh wlan方法", toggle_wifi_netsh_wlan)
    ]
    
    # 依次尝试各种方法
    for method_name, method_func in methods:
        logger.info(f"尝试使用{method_name}...")
        try:
            if method_func(state):
                # 验证状态
                logger.info("验证WiFi状态...")
                time.sleep(1)  # 等待状态更新
                
                if verify_wifi_state(state):
                    logger.success(f"✓ WiFi已成功{action_cn}！")
                    return True
                else:
                    logger.warning(f"{method_name}执行成功，但状态验证失败")
        except Exception as e:
            logger.error(f"{method_name}发生异常: {e}")
    
    logger.error(f"✗ 所有方法都未能成功{action_cn}WiFi")
    logger.info("建议：")
    logger.info("  1. 确认已以管理员权限运行")
    logger.info("  2. 检查设备管理器中WiFi适配器是否正常")
    logger.info("  3. 尝试手动在网络设置中操作")
    
    return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='WiFi控制工具 - 控制Windows系统WiFi开关',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python close_openwifi.py on   # 打开WiFi
  python close_openwifi.py off  # 关闭WiFi
  
注意: 需要管理员权限运行
        """
    )
    parser.add_argument(
        'action', 
        choices=['on', 'off'], 
        help='操作: on=打开WiFi, off=关闭WiFi'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细日志'
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{function}</cyan> | <level>{message}</level>",
            level="DEBUG",
            colorize=True
        )
    
    # 执行操作
    success = toggle_wifi(args.action)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
