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
    ctypes.windll.shell32.ShellExecuteW(
        None, 
        "runas", 
        sys.executable, 
        " ".join(sys.argv),
        None, 
        1
    )
    sys.exit(0)  # 确保原始进程退出

def toggle_wifi(state):
    """
    切换WiFi状态
    
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

def main():
    parser = argparse.ArgumentParser(description='WiFi控制工具')
    parser.add_argument('action', choices=['on', 'off'], help='操作: 打开或关闭')
    
    args = parser.parse_args()
    toggle_wifi(args.action)

if __name__ == "__main__":
    main()