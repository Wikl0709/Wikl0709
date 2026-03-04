# 🚀 Quantum E2E 测试框架 🌟

## 📋 项目概述

这是一个功能强大的 **量子AI测试框架**，用于执行端到端（End-to-End）测试，支持多种测试模式、资源监控、性能分析和自动化判断等功能。 🧪

该项目是专门针对联想Quantum AI系统开发的测试框架，具有高度的自动化和智能化特性，能够全面测试系统的各项功能和性能指标。

---

## ✨ 主要特性

### 🔧 功能特性

- 📊 **多模式测试**: Memory测试、文档注册、主Excel处理
- 📈 **性能监控**: 实时CPU/GPU/内存监控
- 📁 **批处理支持**: 支持多文件循环处理
- 📚 **资源管理**: 自动清理和状态管理
- 🔐 **安全可靠**: 异常处理和资源清理
- 🌐 **网络管理**: 自动WiFi开关控制
- 📋 **详细日志**: 彩色日志输出，支持文件和控制台
- 📊 **数据持久化**: JSON和Excel格式数据存储
- 🔄 **状态追踪**: 任务状态管理和进度跟踪

### 🎯 测试类型

- 🧠 **Memory数据处理**: 批量处理Memory Excel文件
- 📄 **文档注册**: 自动文档上传和注册
- 💬 **交互式查询**: 文本和图片混合查询测试
- 📊 **主Excel处理**: 大规模Excel文件批量处理
- 🔍 **OCR Memory测试**: OCR特定Memory数据处理
- 🧮 **性能基准测试**: 响应时间、吞吐量、稳定性测试
- 📈 **压力测试**: 长时间运行和高负载测试

---

## 🛠️ 环境要求

### 🧮 Python版本

- Python 3.8+ 🐍
- Windows 10/11 操作系统 💻

### 📦 必需依赖包

```bash
# 数据处理
pip install pandas openpyxl loguru requests

# 图像和文件处理
pip install python-docx matplotlib seaborn numpy

# 系统监控
pip install py-cpuinfo psutil

# 网络和通信
pip install requests

# 其他工具
pip install mimetypes queue threading subprocess
```

### 🔧 系统要求

- **内存**: 至少8GB RAM（建议16GB+）
- **存储**: 至少10GB可用空间（建议50GB+用于长期测试）
- **网络**: 稳定的互联网连接（某些测试需要）
- **硬件**: 支持Intel/AMD处理器，GPU显存至少2GB
- **权限**: 需要管理员权限以访问系统资源

### 📁 软件依赖

- **Lenovo Quantum AI System**: 1.0.8+ 版本
- **Microsoft Office**: 2016+ (Excel支持)
- **Visual C++ Redistributable**: 2015-2022

---

## 📦 安装指南

### 3️⃣ 安装依赖

```bash
pip install -r requirements.txt

# 或者手动安装
pip install pandas openpyxl loguru requests python-docx matplotlib seaborn numpy py-cpuinfo psutil
```

### 4️⃣ 验证安装

```bash
python main.py --help
```

### 5️⃣ 初始化项目结构

```bash
# 创建必要的目录结构
mkdir -p dataset Image Reg_Documents Memory_data_*
```

---

## ⚙️ 配置说明

### 🔧 配置文件格式

创建 `quantum_e2e_test.json` 配置文件：

```json
{
  "node_type": "iGPU",
  "task_id": "test_001",
  "test_object": "Quantum E2E",
  "model_version_name": "v1016",
  "version": "20260119",
  "optional": {
    "process": ["Memory", "Document", "Main"],
    "cycle": "1",
    "test_mode": "cloud",
    "filter_local_brain": false,
    "min_wait_time": 1.0,
    "max_wait_time": 10.0,
    "enable_random_wait": true,
    "cleanup_after_run": false
  }
}
```

### 📁 目录结构详解

```
📁 quantum-e2e/
├── 📄 main.py                    # 🔧 主程序入口
├── 📄 quantum_e2e_test.json      # ⚙️ 配置文件
├── 📄 README.md                 # 📖 本文档
├── 📄 requirements.txt          # 📦 依赖包列表
├── 📄 LICENSE                   # 🛡️ 许可证文件
├── 📁 dataset/                  # 📊 Excel数据文件夹
│   ├── 📄 test.xlsx            # 📋 主测试Excel文件
│   └── 📄 other_test.xlsx      # 📋 其他测试文件
├── 📁 Image/                   # 🖼️ 图片文件夹  
│   ├── 🖼️ image1.jpg          # 📷 测试图片1
│   ├── 🖼️ image2.png          # 📷 测试图片2
│   └── 📁 subfolder/           # 📂 图片子目录
├── 📁 Reg_Documents/           # 📄 文档注册文件夹
│   ├── 📄 doc1.pdf            # 📄 PDF文档
│   ├── 📄 doc2.docx           # 📄 Word文档
│   └── 📄 doc3.xlsx           # 📄 Excel文档
├── 📁 Memory_data_*/           # 🧠 Memory数据文件夹
│   ├── 📄 Memory_data.xlsx    # 🧠 Memory主数据文件
│   ├── 📄 user_content.txt    # 🧠 用户内容文件
│   └── 📁 memory_images/      # 🖼️ Memory相关图片
├── 📁 utils/                   # 🛠️ 工具模块
│   ├── 📄 monitor_util.py     # 📊 监控工具
│   ├── 📄 start_stop_services.py # 🔄 服务启停工具
│   └── 📄 other_utils.py      # 🛠️ 其他工具
├── 📁 output/                  # 📤 输出目录（自动生成）
│   ├── 📁 logs/               # 📋 日志文件
│   ├── 📁 resource/           # 📊 资源监控数据
│   ├── 📁 testresult/         # 📊 测试结果
│   └── 📁 reports/            # 📊 报告文件
├── 📁 tests/                   # 🧪 测试用例
│   ├── 📄 unit_tests.py       # 🔬 单元测试
│   └── 📄 integration_tests.py # 🔬 集成测试
└── 📁 docs/                    # 📚 文档
    ├── 📄 api_docs.md         # 📖 API文档
    └── 📄 user_guide.md        # 📖 用户指南
```

---

## 🚀 使用方法

### 1️⃣ 基础运行

```bash
# 🔧 使用默认配置
python main.py

# 📁 指定配置文件
python main.py -c my_config.json

# 📦 指定输出目录
python main.py -o ./my_output

# 🔧 完整参数示例
python main.py -c config.json -o ./results --process_all --cycle 3
```

### 2️⃣ 测试模式运行

```bash
# 🧠 只运行Memory测试
python main.py --process_memory

# 📄 只运行文档注册
python main.py --process_document

# 💬 只运行主Excel处理
python main.py --process_main

# 🔄 执行完整流程
python main.py --process_all

# 🧠 + 📄 组合测试
python main.py --process_memory --process_document

# 🧠 + 💬 组合测试
python main.py --process_memory --process_main
```

### 3️⃣ 高级参数

```bash
# 🎯 循环执行
python main.py --cycle 3

# ⏱️ 自定义等待时间
python main.py --min_wait_time 2.0 --max_wait_time 15.0

# 🧹 运行后清理数据
python main.py --cleanup_after_run

# 📊 禁用随机等待
python main.py --enable_random_wait False

# 🧠 过滤Local Brain数据
python main.py --filter_local_brain yes

# 🖥️ 指定GPU类型
python main.py --gpu_type dGPU

# 🏠 本地测试模式
python main.py --test_mode local
```

### 4️⃣ 测试模式

```bash
# ☁️ 云端模式（默认）
python main.py --test_mode cloud

# 🏠 本地模式
python main.py --test_mode local

# 🧠 智能过滤模式
python main.py --filter_local_brain auto
```

---

## 📊 参数详解

| 🔧 参数                   | 📝 描述           | 🎯 默认值                 | 💡 示例                        | 🧠 适用场景   |
| ------------------------- | ----------------- | ------------------------- | ------------------------------ | ------------- |
| `-c`, `--config_path` | 📄 配置文件路径   | `quantum_e2e_test.json` | `-c custom_config.json`      | 🏢 生产环境   |
| `-o`, `--output`      | 📁 输出目录       | `./output`              | `-o ./results`               | 📊 数据隔离   |
| `--process_memory`      | 🧠 运行Memory测试 | `False`                 | `--process_memory`           | 🧠 记忆测试   |
| `--process_document`    | 📄 运行文档注册   | `False`                 | `--process_document`         | 📄 文档处理   |
| `--process_main`        | 💬 运行主处理     | `True`                  | `--process_main`             | 💬 交互测试   |
| `--process_all`         | 🔄 完整流程       | `False`                 | `--process_all`              | 🧪 完整测试   |
| `--cycle`               | 🔁 循环次数       | `1`                     | `--cycle 5`                  | 📈 性能测试   |
| `--min_wait_time`       | ⏱️ 最小等待时间 | `5.0`                   | `--min_wait_time 2.0`        | ⏰ 速率控制   |
| `--max_wait_time`       | ⏰ 最大等待时间   | `10.0`                  | `--max_wait_time 20.0`       | ⏰ 速率控制   |
| `--gpu_type`            | 🖥️ GPU类型      | `iGPU`                  | `--gpu_type dGPU`            | 🧮 硬件适配   |
| `--test_mode`           | 🧪 测试模式       | `cloud`                 | `--test_mode local`          | 🌐 网络环境   |
| `--filter_local_brain`  | 🧠 过滤模式       | `no`                    | `--filter_local_brain yes`   | 🤖 AI过滤     |
| `--enable_random_wait`  | 🎲 随机等待       | `True`                  | `--enable_random_wait False` | ⏱️ 速率控制 |
| `--cleanup_after_run`   | 🧹 自动清理       | `False`                 | `--cleanup_after_run`        | 🧹 资源管理   |

---

## 🎯 工作流程

### 📋 Memory数据处理流程

```
📊 Excel文件 → 🧠 逐行处理 → 🖼️ 图片上传 → 💬 查询发送 → 📈 结果收集 → 📊 报告生成
     ↓
   📄 Memory_data.xlsx
     ↓
   🧠 user_content处理
     ↓
   🖼️ pathlist图片
     ↓
   💬 Nova API调用
     ↓
   📈 性能指标计算(TTFT, Latency, Speed)
     ↓
   📊 Excel结果保存
```

### 📄 文档注册流程

```
📁 文档目录 → 📦 分批注册 → 🔄 状态检查 → ✅ 完成标记 → 📊 详细记录
     ↓
   📄 Reg_Documents/
     ↓
   📦 每批4个文档
     ↓
   🔄 状态轮询
     ↓
   ✅ 95%完成率
     ↓
   📊 详细信息保存
     ↓
   📄 JSON记录
```

### 💬 主Excel处理流程

```
📋 Excel文件 → 🧪 数据解析 → 📝 查询执行 → 📊 结果保存 → 📈 性能分析 → 🤖 自动判断
     ↓
   📄 dataset/test.xlsx
     ↓
   🧪 question解析
     ↓
   🖼️ pathlist处理
     ↓
   🔄 new_session控制
     ↓
   💬 API调用
     ↓
   📈 性能计算
     ↓
   📊 结果保存
     ↓
   🤖 AI判断
```

### 📊 自动判断流程

```
📊 结果文件 → 🤖 AI分析 → 📈 性能评估 → 📊 报告生成 → 📤 结果上传
     ↓
   📄 test_results_*.xlsx
     ↓
   🤖 Auto_Judge.run()
     ↓
   📈 指标计算
     ↓
   📊 Latency_*.xlsx
     ↓
   📤 上传服务器
```

---

## 📈 性能指标

### 📊 关键性能指标详解

#### 1️⃣ **TTFT** (Time To First Token) ⏰

- **定义**: 从请求发送到接收第一个token的时间
- **重要性**: 反映系统的响应速度
- **目标值**: < 1秒
- **影响因素**: 网络延迟、模型推理速度

#### 2️⃣ **延迟时间** (Response Time) 🕐

- **定义**: 从请求发送到接收完整响应的时间
- **重要性**: 反映整体处理效率
- **目标值**: < 10秒
- **影响因素**: 文本长度、复杂度

#### 3️⃣ **生成速度** (Generation Speed) ⚡

- **定义**: tokens/秒的生成速率
- **重要性**: 反映文本生成效率
- **目标值**: > 20 tokens/秒
- **影响因素**: 模型大小、硬件性能

#### 4️⃣ **令牌计数** (Token Count) 🔢

- **定义**: 生成的token总数
- **重要性**: 反映响应长度和完整性
- **影响因素**: prompt长度、响应策略

#### 5️⃣ **完成率** (Completion Rate) ✅

- **定义**: 成功完成的请求数量比例
- **重要性**: 反映系统稳定性
- **目标值**: > 95%

### 📈 输出报告详解

- 📊 **性能统计报告** (`Latency_*.xlsx`): 按场景分组的性能指标统计
- 📈 **资源监控图表**: CPU、内存、GPU使用率图表
- 📋 **详细日志文件**: 完整的执行过程日志
- 📊 **Memory数据报告**: 记忆系统性能分析
- 📄 **文档注册报告**: 文档处理效率统计

---

## 🛡️ 错误处理

### ⚠️ 常见错误及解决方案

#### 1️⃣ DLL加载错误

```
❌ Error: Failed to load DLL
✅ Solution: 检查quantum-sdk DLL文件是否存在
   - 检查路径: %USERPROFILE%\AppData\Local\Lenovo\Qira\QuantumApp\
   - 检查版本: quantum-sdk-*.dll
   - 权限问题: 以管理员身份运行
```

#### 2️⃣ 会话创建失败

```
❌ Error: Session creation failed  
✅ Solution: 重启量子服务，检查网络连接
   - 重启服务: restart_services()
   - 检查网络: ping localhost
   - 重试机制: 最多3次重试
```

#### 3️⃣ 文件路径错误

```
❌ Error: File not found
✅ Solution: 检查配置文件中的路径设置
   - 绝对路径 vs 相对路径
   - 文件权限检查
   - 目录结构验证
```

#### 4️⃣ 超时错误

```
❌ CTTVError: Request Timeout
✅ Solution: 网络连接检查，自动重试机制
   - 重试策略: 指数退避算法
   - 超时重试: 自动重新处理
   - 网络诊断: 自动检查连接状态
```

#### 5️⃣ 内存不足错误

```
❌ MemoryError: Out of memory
✅ Solution: 内存管理优化
   - 批处理: 减少单次处理数量
   - 内存清理: 定期释放资源
   - 监控: 实时内存使用监控
```

#### 6️⃣ 网络连接错误

```
❌ ConnectionError: Network unavailable
✅ Solution: 网络连接管理
   - WiFi控制: 自动开关WiFi
   - 重连机制: 自动重连
   - 本地模式: 离线测试选项
```

### 🚨 调试技巧

- 📋 **查看日志文件**: `./output/logs/` 目录下的详细日志
- 🔍 **使用 `--test_mode local`**: 进行本地调试，减少网络依赖
- 📊 **启用资源监控**: 观察系统状态变化
- 🐛 **断点调试**: 在关键位置设置断点
- 📈 **性能分析**: 使用内置性能监控工具

### 🛠️ 错误处理机制

```python
# 🔄 自动重试机制
max_retries = 3
retry_delay = 5  # 秒

# 🛡️ 异常捕获和处理
try:
    # 主要逻辑
    pass
except SpecificError as e:
    # 特定错误处理
    logger.error(f"Specific error occurred: {e}")
except Exception as e:
    # 通用错误处理
    logger.error(f"General error occurred: {e}")
finally:
    # 资源清理
    cleanup_resources()
```

---

## 🧪 测试用例

### 📊 基础测试用例

```python
# 🧪 测试Memory数据处理
python main.py --process_memory --cycle 1

# 🧪 测试文档注册
python main.py --process_document --cycle 1

# 🧪 测试主流程
python main.py --process_main --cycle 1

# 🧪 测试完整流程
python main.py --process_all --cycle 1

# 🧪 测试单个Excel文件
python main.py --process_main --cycle 1 -c single_file_config.json
```

### 🧠 高级测试用例

```python
# 🔄 完整端到端测试
python main.py --process_all --cycle 3 --enable_random_wait True

# 📊 性能压力测试
python main.py --process_main --cycle 10 --min_wait_time 0.5 --max_wait_time 1.0

# 🧠 记忆系统深度测试
python main.py --process_memory --cycle 5 --min_wait_time 2.0 --max_wait_time 5.0

# 📄 文档注册批量测试
python main.py --process_document --cycle 1 --enable_random_wait False

# 🧪 混合场景测试
python main.py --process_memory --process_main --cycle 2

# 🧹 清理测试
python main.py --cleanup_after_run --process_all --cycle 1
```

### 🧪 单元测试用例

```python
# 🧪 测试会话管理
python -m pytest tests/test_session.py

# 🧪 测试文档注册
python -m pytest tests/test_document_registration.py

# 🧪 测试Memory处理
python -m pytest tests/test_memory_processing.py

# 🧪 测试查询功能
python -m pytest tests/test_query.py

# 🧪 测试性能指标
python -m pytest tests/test_performance.py
```

---

## 🚀 高级功能

### 📊 资源监控

- 🧮 **CPU/内存使用率监控**: 实时监控系统资源使用情况
- 🖥️ **GPU状态监控**: 监控GPU使用率、温度、显存
- 📈 **实时性能图表**: 动态显示性能指标变化
- 📊 **资源使用报告**: 生成详细的资源使用分析报告
- ⚠️ **阈值警告**: 资源使用过高时发出警告

### 🤖 自动化判断

- 📊 **AI辅助结果分析**: 使用机器学习算法分析测试结果
- 📋 **自动报告生成**: 一键生成完整的测试报告
- 📈 **性能趋势分析**: 分析性能变化趋势和模式
- 🤖 **智能异常检测**: 自动识别异常性能指标
- 📊 **基准对比**: 与历史数据和基准数据对比

### 🔁 循环执行

- 🔄 **支持多次循环测试**: 可配置循环次数
- 📊 **自动统计平均性能**: 计算多轮测试的平均值
- 📈 **生成对比报告**: 对比不同轮次的性能差异
- 🧪 **稳定性测试**: 长时间运行验证系统稳定性
- 📊 **性能回归检测**: 检测性能下降趋势

### 🧹 自动清理

- 📂 **自动清理临时文件**: 删除测试产生的临时文件
- 🧠 **清理Memory数据**: 清除测试产生的记忆数据
- 📄 **清理文档注册记录**: 清除文档注册痕迹
- 🧮 **资源回收**: 释放占用的系统资源
- 🔄 **状态重置**: 重置系统到初始状态

### 🌐 网络管理

- 📶 **WiFi自动控制**: 根据测试模式自动开关WiFi
- 🌐 **网络状态监控**: 监控网络连接状态
- 🔄 **自动重连**: 网络中断时自动重连
- 🛡️ **离线模式**: 支持无网络环境测试
- 📊 **网络性能监控**: 监控网络延迟和带宽

---

## 📁 输出文件说明

### 📊 主要输出文件详解

#### 1️⃣ **测试结果文件** (`📊 test_results_*.xlsx`)

- **内容**: 完整的测试结果数据
- **结构**: 包含question、response、response_time等列
- **功能**: 记录每次查询的详细结果和性能指标
- **用途**: 用于结果分析和报告生成

#### 2️⃣ **性能统计报告** (`📈 Latency_*.xlsx`)

- **内容**: 按场景分组的性能统计数据
- **指标**: TTFT、延迟时间、生成速度等
- **格式**: 按scene分组的平均值统计
- **用途**: 性能趋势分析和对比

#### 3️⃣ **文档注册详情** (`📚 document_registration_*.xlsx`)

- **内容**: 文档注册过程的详细信息
- **字段**: id、status、fileName、createTime等
- **功能**: 记录每个文档的处理状态和详细信息
- **用途**: 文档处理审计和故障排查

#### 4️⃣ **Memory测试结果** (`🧠 Memory_data_with_responses_*.xlsx`)

- **内容**: Memory数据处理的完整结果
- **包含**: user_content、response、response_time、TTFT等
- **功能**: Memory系统性能评估
- **用途**: 记忆系统效果分析

#### 5️⃣ **资源监控数据** (`📊 resource_*.csv`)

- **内容**: CPU、内存、GPU使用率数据
- **格式**: 按时间戳记录的资源使用情况
- **功能**: 系统性能监控和分析
- **用途**: 资源瓶颈识别和优化

### 📁 输出目录结构详解

```
📁 output/
├── 📁 logs/                    # 📋 日志文件
│   ├── 📄 Quantum_api_*.log   # 📋 主程序日志
│   ├── 📄 resource_monitor_*.log # 📋 资源监控日志
│   └── 📄 detailed_*.log      # 📋 详细调试日志
├── 📁 resource/               # 📊 资源监控数据
│   ├── 📄 resource_*.csv     # 📊 CSV格式资源数据
│   └── 📄 resource_*.xlsx    # 📊 Excel格式资源数据
├── 📁 testresult/             # 📊 测试结果
│   ├── 📄 test_results_*.xlsx # 📊 主测试结果
│   ├── 📄 document_registration_*.xlsx # 📊 文档注册结果
│   └── 📄 Memory_data_with_responses_*.xlsx # 🧠 Memory结果
├── 📁 reports/                # 📊 报告文件
│   ├── 📄 Latency_*.xlsx     # 📈 性能统计报告
│   └── 📄 summary_*.pdf      # 📄 摘要报告
└── 📄 registered_docs.json    # 📄 注册文档记录
```

### 📊 文件命名规则

- **时间戳格式**: `YYYYMMDD_HHMMSS`
- **循环标识**: `_cycleN` (N为循环编号)
- **功能标识**: `test_results_`, `Latency_`, `document_registration_`
- **版本标识**: `v20260119` 等版本号

---

## 🔧 自定义配置

### 📄 配置可选项详解

#### 🧠 **Filter Local Brain 配置**

```json
{
  "filter_local_brain": "auto"  // "auto", "yes", "no"
}
```

- **auto**: 根据test_mode自动判断
- **yes**: 总是过滤Local Brain相关数据
- **no**: 从不过滤，保留所有数据
- **用途**: 针对不同AI模型的测试结果过滤

#### ⏱️ **等待时间配置**

```json
{
  "min_wait_time": 1.0,    // 最小等待时间（秒）
  "max_wait_time": 10.0,   // 最大等待时间（秒）
  "enable_random_wait": true  // 是否启用随机等待
}
```

- **最小等待**: 防止请求过于频繁
- **最大等待**: 控制最长等待时间
- **随机等待**: 模拟真实用户行为

#### 🏠 **测试模式配置**

```json
{
  "test_mode": "cloud",    // "cloud" 或 "local"
  "cleanup_after_run": false  // 运行后是否清理
}
```

- **cloud模式**: 需要网络连接，测试在线功能
- **local模式**: 离线测试，适合调试
- **自动清理**: 测试完成后自动清理数据

#### 🔄 **流程控制配置**

```json
{
  "process": ["Memory", "Document", "Main"],  // 执行流程
  "cycle": "1"  // 循环次数
}
```

- **Memory**: Memory数据处理流程
- **Document**: 文档注册流程
- **Main**: 主Excel处理流程
- **All**: 执行所有流程

### 🎛️ 高级配置选项

```json
{
  "advanced_options": {
    "batch_size": 4,           // 批处理大小
    "timeout": 180,            // 请求超时时间
    "retry_count": 3,          // 重试次数
    "concurrent_limit": 10,    // 并发限制
    "log_level": "DEBUG",      // 日志级别
    "save_intermediate": true, // 保存中间结果
    "validate_responses": true // 验证响应数据
  }
}
```

## 📚 附录

### 📋 常用命令速查

```bash
# 🧪 基础测试
python main.py --process_all --cycle 1

# 📊 性能测试
python main.py --process_main --cycle 5 --enable_random_wait False

# 🧠 记忆测试
python main.py --process_memory --min_wait_time 2.0

# 📄 文档测试
python main.py --process_document --cycle 1

# 🧹 清理测试
python main.py --cleanup_after_run --process_all
```
