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
    command = f'netsh interface set interface "WLAN" {status}'
    
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
            print(f"WiFi 已 {state}。")
            return True
        else:
            print(f"命令执行失败，错误代码 {result.returncode}")
            if result.stderr:
                print(f"错误详情: {result.stderr}")
            if result.stdout:
                print(f"命令输出: {result.stdout}")
            
            # 尝试使用"Wi-Fi"作为备选接口名
            if "WLAN" in command:
                print("\n尝试使用备选接口名: Wi-Fi")
                command = f'netsh interface set interface "Wi-Fi" {status}'
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
                    print(f"WiFi 已 {state} (使用Wi-Fi接口名)。")
                    return True
                else:
                    print(f"命令执行失败，错误代码 {result.returncode}")
                    if result.stderr:
                        print(f"错误详情: {result.stderr}")
                    if result.stdout:
                        print(f"命令输出: {result.stdout}")
                    return False
            return False
    except Exception as e:
        print(f"执行过程中发生异常: {str(e)}")
        return False

def toggle_wifi_powershell(state):
    """
    使用PowerShell命令切换WiFi状态
    
    Parameters:
        state (str): "on" 或 "off"
    """
    action = "Enable-NetAdapter" if state == "on" else "Disable-NetAdapter"
    
    # PowerShell命令：查找并控制无线网卡
    ps_command = f'''
    $interface = Get-NetAdapter | Where-Object {{ $_.InterfaceDescription -like "*Wireless*" -or $_.Name -like "*Wi-Fi*" }}
    if ($interface) {{
        $interface | {action} -Confirm:$false
        Write-Output "Success"
    }} else {{
        Write-Output "No wireless adapter found"
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

def toggle_wifi(state):
    """
    切换WiFi状态，优先使用netsh，失败后尝试PowerShell
    
    Parameters:
        state (str): "on" 或 "off"
    """
    if state not in ["on", "off"]:
        print("错误：无效的状态。请使用'on'或'off'。")
        return False
    
    # 检查是否需要管理员权限
    if not is_admin():
        print("需要管理员权限，正在请求...")
        run_as_admin()
        # 注意：到这里代码不会继续执行，因为原始进程已退出
    
    # 首先尝试使用netsh
    print("尝试使用netsh控制WiFi...")
    if toggle_wifi_netsh(state):
        return True
    
    # 如果netsh失败，则尝试使用PowerShell
    print("\nnetsh方式失败，尝试使用PowerShell控制WiFi...")
    if toggle_wifi_powershell(state):
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