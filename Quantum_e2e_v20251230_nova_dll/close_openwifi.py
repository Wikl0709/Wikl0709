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

def is_admin():
    """检查脚本是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """以管理员权限重新启动当前脚本"""
    # 重新启动当前脚本，以管理员权限运行
    ctypes.windll.shell32.ShellExecuteW(
        None, 
        "runas", 
        sys.executable, 
        " ".join(sys.argv),
        None, 
        1
    )
    sys.exit(0)  # 确保原始进程退出

def toggle_wifi_netsh(state):
    """
    使用netsh命令切换WiFi状态
    
    Parameters:
        state (str): "on" 或 "off"
    """
    status = "enabled" if state == "on" else "disabled"
    
    # 尝试多种可能的WiFi接口名称
    common_interface_names = [
        "WLAN", "Wi-Fi", "Wireless Network Connection", 
        "无线网络连接", "WIRELESS", "wireless", "WiFi"
    ]
    
    for interface_name in common_interface_names:
        command = f'netsh interface set interface "{interface_name}" {status}'
        
        print(f"执行命令: {command}")
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                encoding="utf-8",
                check=False
            )
            
            if result.returncode == 0:
                print(f"WiFi 已 {state} (接口名: {interface_name})。")
                return True
            else:
                print(f"命令执行失败，错误代码 {result.returncode}")
                if result.stderr:
                    print(f"错误详情: {result.stderr}")
                if result.stdout:
                    print(f"命令输出: {result.stdout}")
                
        except Exception as e:
            print(f"执行过程中发生异常: {str(e)}")
            continue
    
    print("所有netsh接口名称尝试均失败")
    return False

def toggle_wifi_powershell(state):
    """
    使用PowerShell命令切换WiFi状态
    
    Parameters:
        state (str): "on" 或 "off"
    """
    action = "Enable-NetAdapter" if state == "on" else "Disable-NetAdapter"
    
    # PowerShell命令：通过InterfaceType查找并控制无线网卡 (71 = Wireless80211)
    ps_command = f'''
    $wirelessAdapters = Get-NetAdapter | Where-Object {{ $_.InterfaceType -eq 71 }}
    if ($wirelessAdapters) {{
        $wirelessAdapters | {action} -Confirm:$false
        Write-Output "Success"
    }} else {{
        # 如果通过InterfaceType没找到，再尝试通过名称查找
        $wirelessAdapters = Get-NetAdapter | Where-Object {{ 
            $_.Name -like "*Wi-Fi*" -or 
            $_.Name -like "*WLAN*" -or 
            $_.Name -like "*Wireless*" -or
            $_.InterfaceDescription -like "*Wireless*" -or
            $_.InterfaceDescription -like "*Wi-Fi*"
        }}
        if ($wirelessAdapters) {{
            $wirelessAdapters | {action} -Confirm:$false
            Write-Output "Success"
        }} else {{
            Write-Output "No wireless adapter found"
        }}
    }}
    '''
    
    print(f"使用PowerShell执行WiFi {state}操作")
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            errors="ignore",
            check=False
        )
        
        if result.returncode == 0 and "Success" in result.stdout:
            print(f"WiFi 已 {state} (通过PowerShell)。")
            import time
            # time.sleep(20)
            return True
        else:
            print(f"PowerShell命令执行失败，错误代码 {result.returncode}")
            if result.stderr:
                print(f"错误详情: {result.stderr}")
            if result.stdout:
                print(f"命令输出: {result.stdout}")
            return False
    except Exception as e:
        print(f"执行过程中发生异常: {str(e)}")
        return False

def toggle_wifi_netsh_wlan(state):
    """
    使用netsh wlan命令切换WiFi状态
    
    Parameters:
        state (str): "on" 或 "off"
    """
    # 首先获取无线接口名称
    show_interfaces_cmd = "netsh wlan show interfaces"
    try:
        result = subprocess.run(
            show_interfaces_cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False
        )
        
        if result.returncode != 0:
            print("无法获取无线接口信息")
            return False
            
        # 从输出中提取接口名称
        output_lines = result.stdout.split('\n')
        interface_name = None
        for line in output_lines:
            if "名称" in line or "Name" in line:  # 支持中英文系统
                if ":" in line:
                    interface_name = line.split(":")[1].strip()
                    break
        
        if not interface_name:
            print("未找到无线接口")
            return False
            
        print(f"检测到无线接口: {interface_name}")
        
        # 根据请求的状态启用或禁用接口
        if state == "on":
            command = f'netsh interface set interface "{interface_name}" enable'
        else:
            command = f'netsh interface set interface "{interface_name}" disable'
            
        print(f"执行命令: {command}")
        
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False
        )
        
        if result.returncode == 0:
            print(f"WiFi 已 {state} (通过netsh interface)。")
            return True
        else:
            print(f"netsh interface 命令执行失败，错误代码 {result.returncode}")
            if result.stderr:
                print(f"错误详情: {result.stderr}")
            if result.stdout:
                print(f"命令输出: {result.stdout}")
            return False
            
    except Exception as e:
        print(f"执行过程中发生异常: {str(e)}")
        return False

def toggle_wifi(state):
    """
    切换WiFi状态，按优先级尝试多种方法
    1. 首先尝试增强的netsh方法（支持多种接口名称）
    2. 然后尝试增强的PowerShell方法（使用InterfaceType）
    3. 最后尝试netsh wlan方法
    """
    if state not in ["on", "off"]:
        print("错误：无效的状态。请使用'on'或'off'。")
        return False
    
    # 检查是否需要管理员权限
    if not is_admin():
        print("需要管理员权限，正在请求...")
        run_as_admin()
        # 注意：到这里代码不会继续执行，因为原始进程已退出
    
    print("尝试使用增强的netsh方法控制WiFi...")
    if toggle_wifi_netsh(state):
        return True
    
    print("\nnetsh方法失败，尝试使用增强的PowerShell方法控制WiFi...")
    if toggle_wifi_powershell(state):
        return True
    
    print("\nPowerShell方法失败，尝试使用netsh wlan方法控制WiFi...")
    if toggle_wifi_netsh_wlan(state):
        return True
    
    print(f"\n所有方法都未能成功{state}WiFi。")
    return False

def main():
    parser = argparse.ArgumentParser(description='WiFi控制工具')
    parser.add_argument('action', choices=['on', 'off'], help='操作: 打开或关闭')
    
    args = parser.parse_args()
    
    # 执行请求的操作
    toggle_wifi(args.action)

if __name__ == "__main__":
    main()