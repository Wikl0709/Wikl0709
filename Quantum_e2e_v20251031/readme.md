# 🚀 Quantum Core Brain KMP 接口测试工具

![Python](https://img.shields.io/badge/python-3.7%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-windows-lightgrey)

## 📖 项目简介

这是一个用于测试 Quantum Core Brain KMP 系统的自动化接口测试工具。该工具支持多模态数据处理，包括文档注册、图像查询、内存数据处理等功能，能够对系统进行全面的端到端测试。

## ✨ 主要功能

- 📄 **文档注册测试** - 自动注册并处理多种格式文档
- 🖼️ **图像查询测试** - 支持带图像的多模态查询测试
- 💾 **内存数据处理** - 处理Memory数据Excel文件中的测试用例
- 📊 **资源监控** - 实时监控系统资源使用情况
- 🔁 **循环测试** - 支持多轮循环测试以验证稳定性
- 📈 **结果统计** - 自动生成详细的测试结果报告

## 🛠️ 环境要求

- 🐍 Python 3.7+
- 📦 依赖包:
  - pandas
  - requests
  - openpyxl
  - argparse

## 🚀 使用方法

### 基本用法

```bash
python Quantum_e2e_20251027.py [--参数]
```

### 常用参数

| 参数               | 说明                    | 默认值                                                                                            |
| ------------------ | ----------------------- | ------------------------------------------------------------------------------------------------- |
| `--excel_dir`    | Excel文件目录路径       | `C:\Users\Lenovo Yanglei AFR\Desktop\LRIA_llm_eval\eval\20251021\bvt\dataset`                   |
| `--image_dir`    | 图像文件目录路径        | `C:\Users\Lenovo Yanglei AFR\Desktop\LRIA_llm_eval\eval\20251021\bvt\images`                    |
| `--doc_dir`      | 文档目录路径            | `C:\Users\Lenovo Yanglei AFR\Desktop\LRIA_llm_eval\eval\20251021\bvt\files`                     |
| `--memory_excel` | Memory Excel文件路径    | `C:\Users\Lenovo Yanglei AFR\Desktop\LRIA_llm_eval\eval\20251021\bvt\Memory_data _v3_1016.xlsx` |
| `--cycle`        | 循环测试轮数            | `1`                                                                                             |
| `--gpu_type`     | GPU类型(dGPU/iGPU/aGPU) | `dGPU`                                                                                          |

### 功能开关参数

- `--process_memory` - 处理Memory数据
- `--process_document` - 处理文档注册
- `--process_main` - 处理主Excel文件
- `--process_all` - 执行完整流程(默认)

### 使用示例

```bash
# 执行完整测试流程
python Quantum_e2e_20251027.py --process_all

# 只处理文档注册
python Quantum_e2e_20251027.py --process_document

# 执行3轮循环测试
python Quantum_e2e_20251027.py --process_all --cycle 3

# 指定不同的GPU类型
python Quantum_e2e_20251027.py --process_all --gpu_type iGPU
```

## 📁 项目结构

```
Quantum_e2e_20251027.py
├── 📦 主程序文件
├── 📂 testresult/          # 测试结果输出目录
├── 📂 logs/                # 日志文件目录
├── 📂 resource/            # 资源监控数据目录
├── registered_docs.json    # 已注册文档记录文件
└── Memory_data_with_responses.xlsx  # Memory测试结果文件
```

## 🔧 核心功能模块

### 🤖 MultimodalAPI 类

主要的API接口类，包含以下方法：

- `create_session()` - 创建会话
- `register_document()` - 注册文档
- `send_query_with_image()` - 发送带图像的查询
- `get_response_content()` - 获取响应内容
- `process_document_registration_only()` - 仅处理文档注册
- `process_main_excel_only()` - 仅处理主Excel文件测试
- `process_memory_data_only()` - 仅处理Memory数据

### 📊 资源监控

- `start_resource_monitoring()` - 启动资源监控
- `stop_resource_monitoring()` - 停止资源监控
- `add_resource_data_to_results()` - 将资源数据添加到结果文件

## 📈 输出结果

测试完成后会在 `testresult/` 目录下生成:

- 📄 `test_results_*.xlsx` - 主要测试结果文件
- 📄 `document_registration_*.xlsx` - 文档注册详情文件
- 📄 `Memory_data_with_responses.xlsx` - Memory测试结果文件
- 📊 `resource_*.csv` - 系统资源监控数据

## ⚠️ 注意事项

- 🌐 确保 Quantum Core Brain 服务在 `http://127.0.0.1:35253` 正常运行
- 📂 确保指定的Excel、图像和文档目录路径正确
- 🔐 某些操作可能需要管理员权限
- ⏱️ 文档注册过程可能需要较长时间，请耐心等待
