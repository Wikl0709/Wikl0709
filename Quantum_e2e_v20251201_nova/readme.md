# Quantum API 自动化测试脚本 🚀

这是一个用于自动化测试 Quantum 多模态 API 的 Python 脚本。它可以处理文档注册、内存数据处理、Excel 测试用例执行，并支持资源监控和循环测试。

## 📋 功能特性

- 📁 **文档注册**: 自动扫描并注册指定目录中的文档文件
- 💾 **Memory 数据处理**: 处理包含用户内容的 Excel 文件
- 📊 **Excel 测试执行**: 执行 Excel 中定义的测试用例，支持图片附件
- 🔁 **循环测试**: 支持多次循环执行测试用例
- 📈 **资源监控**: 监控系统资源使用情况（CPU、内存、GPU）
- 🧹 **环境清理**: 自动备份和清理相关目录
- ⚙️ **服务管理**: 自动启动和停止相关服务

## 🛠️ 环境要求

### Python 版本

- Python 3.7+

### 依赖包

请查看 `requirements.txt` 文件获取完整依赖列表。

## 📦 安装依赖

```bash
pip install -r requirements.txt

pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple   (全局定义清华源)
```

## 🚀 使用方法

### 基本用法

```bash
python Quantum_e2e_20251127_nova_z_R18all.py
```

### 参数说明

| 参数                   | 类型   | 默认值            | 说明                             |
| ---------------------- | ------ | ----------------- | -------------------------------- |
| `--excel_dir`        | string | `dataset` 目录  | Excel 文件目录路径或具体文件路径 |
| `--image_dir`        | string | `images` 目录   | 图片文件目录路径                 |
| `--doc_dir`          | string | `bvtfiles` 目录 | 文档目录路径                     |
| `--memory_excel`     | string | 默认 Memory 文件  | Memory Excel 文件路径            |
| `--process_memory`   | flag   | False             | 处理 Memory 数据                 |
| `--process_document` | flag   | True              | 处理文档注册                     |
| `--process_main`     | flag   | True              | 处理主 Excel 文件                |
| `--process_all`      | flag   | False             | 执行完整流程                     |
| `--cycle`            | int    | 1                 | 循环轮数                         |
| `--gpu_type`         | string | "iGPU"            | GPU 类型 (dGPU/iGPU/aGPU)        |
| `--service_path`     | string | 默认服务路径      | 服务目录路径                     |

### 使用示例

1. **执行完整流程**:

   ```bash
   python Quantum_e2e_20251127_nova_z_R18all.py --process_all
   ```
2. **处理特定文档目录**:

   ```bash
   python Quantum_e2e_20251127_nova_z_R18all.py --doc_dir /path/to/documents --process_document
   ```
3. **执行多次循环测试**:

   ```bash
   python Quantum_e2e_20251127_nova_z_R18all.py --cycle 3 --process_all
   ```
4. **指定 GPU 类型**:

   ```bash
   python Quantum_e2e_20251127_nova_z_R18all.py --gpu_type dGPU --process_all
   ```

## 📁 目录结构

```
.
├── dataset/                 # 默认 Excel 测试文件目录
├── images/                  # 默认图片文件目录
├── bvtfiles/               # 默认文档文件目录
├── testresult/             # 测试结果输出目录
├── logs/                   # 日志文件目录
├── resource/               # 资源监控数据目录
├── utils/                  # 工具模块目录
│   ├── monitor_util.py     # 资源监控工具
│   └── start_stop_services.py  # 服务管理工具
├── Quantum_e2e_20251127_nova_z_R18all.py # 主程序文件
├── requirements.txt        # Python 依赖包列表
└── README.md              # 说明文档
```

## 📊 输出文件

- **测试结果**: `testresult/test_results_{filename}_{timestamp}_cycle{number}.xlsx`
- **文档注册详情**: `testresult/document_registration_{timestamp}.xlsx`
- **Memory 处理结果**: `Memory_data_with_responses.xlsx`
- **日志文件**: `logs/Quantum_api_{timestamp}.log`
- **资源监控数据**: `resource/resource_{timestamp}.csv`

## 🔧 配置说明

### 默认配置

- **API 基础 URL**: `http://127.0.0.1:35253`
- **默认处理器**: `aaitc-graph-brain`
- **默认模型**: `gpt` (版本 `gpt-4.1`)

### 可配置目录

脚本会自动处理以下用户目录的备份和清理:

- `AppData\Local\mcp_mgmt_service`
- `AppData\Local\quantum_core`
- `.quantum`
- `Documents\QTCore`
- `AppData\Quantum`
- `AppData\Local\Lenovo\QuantumAI`

## 📈 资源监控

脚本会自动监控以下进程:

- `com.lenovo.quantum.exe`
- `mcpMgmtService.exe`
- `lenovo.pfm.pipe.exe`

监控数据包括 CPU、内存、GPU 使用情况，并保存为 CSV 文件。

## ⚠️ 注意事项

1. 确保 Quantum 服务正在运行且可通过 `http://127.0.0.1:35253` 访问
2. 运行前请确认指定的目录路径存在且有适当权限
3. 脚本会自动备份和清理相关目录，请确保重要数据已备份
4. 根据系统性能，处理大量文档时可能需要较长时间
5. 循环测试时，每轮结果会保存在独立的文件中
