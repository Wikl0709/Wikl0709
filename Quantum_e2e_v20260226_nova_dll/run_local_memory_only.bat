@echo off
:: 切换到批处理文件所在目录
cd /d "%~dp0"

:: 执行Python命令
python main.py -c exec_json/quantum_e2e_test_loca_Memory_only.json

pause
