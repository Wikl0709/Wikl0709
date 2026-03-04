# Quantum API 自动化测试工具 🧪

这是一个用于测试 Quantum 多模态 API 的自动化测试工具，支持文档注册、解析、查询和删除等完整流程的测试。

## 📦 依赖包

以下是在使用本工具时需要安装的 Python 包：

```bash
pip install pandas
pip install requests
pip install openpyxl
pip install numpy
```

还需要 `utils.start_stop_services` 模块，用于启动和停止服务。

## 🚀 快速开始

### 1. 基本用法

```bash
python Quantum_Bvt_v20251110.py
```

### 2. 带参数运行

```bash
python Quantum_Bvt_v20251110.py --doc_dir "文档目录路径" --input_path "Excel测试用例文件路径" --image_dir "图片目录路径" --service_path "服务目录路径"
```

### 3. 默认参数

- `--doc_dir`: `C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_Bvt_20251110\bvtfiles`
- `--input_path`: `C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_Bvt_20251110\Pod7_Multimodal_cases_bvtall.xlsx`
- `--image_dir`: `C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\eval\Quantum_Bvt_20251110\images`
- `--service_path`: `C:\Users\XiaoXinPro 16 IAH\Desktop\LRIA_llm_eval\version\LATC_Brain_20251031\Lenovo_Quantum_Core_V20251030_R8_226`

## 🧠 主要功能

### 测试流程

1. **环境准备** 🛠️

   - 备份和清理相关目录
   - 启动 Quantum 服务
2. **基础接口测试** 🧪

   - `create_session` - 创建会话
   - [get_session_info](file://c:\Users\XiaoXinPro%2016%20IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251106\bvt1106\test_tool.py#L134-L201) - 获取会话信息
   - [register_document](file://c:\Users\XiaoXinPro%2016%20IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251106\bvt1106\test_tool.py#L271-L338) - 注册文档
   - [get_register_document](file://c:\Users\XiaoXinPro%2016%20IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251106\bvt1106\test_tool.py#L339-L511) - 查询注册文档
   - [delete_register_documnet](file://c:\Users\XiaoXinPro%2016%20IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251106\bvt1106\test_tool.py#L513-L580) - 删除注册文件
3. **文档处理测试** 📄

   - [add_and_parse_document](file://c:\Users\XiaoXinPro%2016%20IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251106\bvt1106\test_tool.py#L768-L858) - 上传并立即解析文档
   - [parse_document](file://c:\Users\XiaoXinPro%2016%20IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251106\bvt1106\test_tool.py#L695-L766) - 立即解析指定文档
4. **查询接口测试** 🔍

   - [query](file://c:\Users\XiaoXinPro%2016%20IAH\Desktop\LRIA_llm_eval\eval\Quantum_e2e_v20251106\bvt1106\test_tool.py#L582-L693) - 对话查询接口
   - 批量查询测试（从 Excel 文件读取测试用例）
5. **验证测试** ✅

   - 验证文档删除是否成功

## 🧪 测试用例详情

### 1. 基础接口测试用例

| 测试用例名称             | 描述                               | 是否必选 |
| ------------------------ | ---------------------------------- | -------- |
| create_session           | 创建一个新的会话                   | 是       |
| get_session_info         | 获取会话信息，提取sessionID和jobId | 是       |
| register_document        | 注册文档到会话                     | 是       |
| get_register_document    | 查询注册文档                       | 是       |
| delete_register_documnet | 删除注册文件                       | 是       |

### 2. 文档处理测试用例

| 测试用例名称           | 描述               | 是否必选 |
| ---------------------- | ------------------ | -------- |
| add_and_parse_document | 上传并立即解析文档 | 是       |
| parse_document         | 立即解析指定文档   | 是       |

### 3. 查询接口测试用例

| 测试用例名称  | 描述                        | 是否必选 |
| ------------- | --------------------------- | -------- |
| query         | 对话查询接口                | 是       |
| query_batch_* | 批量查询（从Excel文件读取） | 否       |

### 4. 批量测试用例（从Excel文件读取）

批量测试用例从Excel文件中读取，每行包含以下字段：

- `question`: 查询问题文本
- `pathlist`: 图片路径列表（可选）

测试时会为每个问题创建新的会话并执行查询。

### 5. 验证测试用例

| 测试用例名称  | 描述               | 是否必选 |
| ------------- | ------------------ | -------- |
| verify_delete | 验证文档是否已删除 | 是       |

## 📊 输出结果

测试结果将保存在 `testresult` 目录下的 Excel 文件中，包含以下信息：

- 接口名称
- 接口描述
- 测试时间
- 测试结果 (pass/fail/跳过)
- 响应时间(秒)
- 状态码
- 返回内容
- 详细信息

## 📁 目录结构

```
├── Quantum_Bvt_v20251110.py          # 主测试脚本
├── logs/                     # 日志文件目录
├── testresult/               # 测试结果目录
├── bvtfiles/                 # 测试文档目录
├── images/                   # 测试图片目录
└── Pod7_Multimodal_cases_bvtall.xlsx  # 测试用例文件
```

## ⚙️ 配置说明

### 日志配置

- 日志文件保存在 `logs` 目录下
- 文件名格式: `Bvt_Quantum_api_YYYYMMDD_HHMMSS.log`

### 测试结果配置

- 测试结果保存在 `testresult` 目录下
- 文件名格式: `test_results_YYYYMMDD_HHMMSS.xlsx`

## 🛡️ 注意事项

1. 确保 Quantum 服务可以正常启动
2. 确保测试文档和图片路径正确
3. 确保有足够的磁盘空间用于日志和结果文件
4. 运行前会自动备份和清理相关目录

## 📈 测试报告

测试完成后会输出统计信息：

- 总测试用例数
- 通过(pass)的用例数
- 失败(fail)的用例数
- 跳过的用例数

## 🤖 自动化特性

- ✅ 自动启动和停止服务
- ✅ 自动备份和清理环境
- ✅ 实时写入测试结果
- ✅ 异常处理和错误记录
- ✅ 批量测试用例执行
