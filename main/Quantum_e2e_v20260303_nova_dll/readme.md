# 🚀 Quantum E2E 测试工具 (v20260227 / v20260303)

基于量子 SDK 的端到端测试工具，支持文档注册、主 Excel 查询、Memory 数据处理、云端/本地双模式及资源监控。  
**v20260303 起**：主逻辑已拆分为 `common/` 多模块 + `main.py` 入口，便于维护与扩展。

## 📋 功能特性

- ✅ **文档注册**: 扫描并注册指定目录下的文档，支持完成率轮询与注册时长分析
- ✅ **主 Excel 查询**: 支持文本与图像查询，按 `new_session` 列复用会话
- ✅ **Memory 数据处理**: 处理 Memory_data.xlsx（add_memory），支持重跑失败 case 与统计重算
- ✅ **云端/本地模式**: `test_mode` / `test_mode_config` 区分运行与配置；本地模式自动关/开 WiFi
- ✅ **资源监控**: 按场景启动监控，资源数据写入结果 Excel 的 resource sheet
- ✅ **性能指标**: TTFT、首字/首文本响应时间、Token 数、生成速度、响应时间
- ✅ **Tool 名提取**: 从流式响应中提取 tool 类型并写入结果列 `toolname`
- ✅ **失败重跑**: 主 Excel 中 Request/Stream Timeout、Task failed（排除 failed_input_safety）自动重跑
- ✅ **日志与打包**: 日志写入本次运行目录，打包 PackageAllLogs.zip；主流程可生成 TestResult_{version}_{mode}_{timestamp}.zip
- ✅ **配置生成**: 根据 `version_config`、`test_mode_config` 及 C:\config.json 在输出目录生成 config.json
- ✅ **DLL 自动发现**: 自动查找 quantum-sdk-*.dll，无需手动指定路径

## 🛠️ 环境要求

```bash
# 建议使用清华源: pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
pandas
openpyxl
psutil
pynvml
colorama
pywin32
loguru
mimetypes
# 以及项目内模块: utils (monitor_util, start_stop_services), close_openwifi, packageLog,
# combined_analysis, analysis_log_0130_cloud, analysis_log_local, Auto_Judge 等
```

## 📁 目录结构

```
.
├── outputs/
│   └── run_{RUN_ID}/              # 本次运行输出（RUN_ID 来自 version_config）
│       ├── logs/                  # 日志
│       ├── resource/              # 资源监控 CSV
│       ├── testresult/            # 测试结果 Excel、文档注册详情等
│       ├── config.json            # 生成的配置
│       ├── registered_docs.json   # 已注册文档缓存
│       ├── PackageAllLogs.zip     # 日志打包
│       └── TestResult_{version}_{mode}_{ts}.zip  # 主流程总包（仅 process_main/process_all）
├── dataset/                       # 测试数据（Excel、图片、文档等）
├── utils/
│   ├── monitor_util.py
│   └── start_stop_services.py
├── common/                        # 公共模块（重构后拆分）
│   ├── __init__.py
│   ├── run_context.py             # 运行上下文、输出目录、日志、运行时配置
│   ├── quantum_sdk.py             # 加载 DLL 与 ctypes 绑定
│   ├── quantum_client_manager.py  # 量子客户端管理器（单例 + QuantumClientManager）
│   ├── bundle.py                  # 输出目录打包 zip
│   ├── paths.py                   # DLL/quantum_core 路径查找
│   ├── resource_monitor.py        # 资源监控启停与结果写入 Excel
│   ├── multimodal_api.py         # MultimodalAPI 类（会话/文档/Memory/主 Excel）
│   └── main_process.py            # run_quantum_e2e_process、merge_and_analyze_output_files
├── main.py                         # 主入口：参数解析、初始化、执行流程、收尾
└── readme.md
```

## ⚙️ 参数说明

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--excel_dir` | string | 见示例路径 | 主 Excel 文件或所在目录路径 |
| `--image_dir` | string | 见示例 | 图像资源目录（pathlist 中的文件名在此目录下查找） |
| `--doc_dir` | string | 见示例 | 文档注册目录 |
| `--memory_excel` | string | 见示例 | Memory 注册用 Excel 路径 |
| `--process_memory` | flag | True | 是否处理 Memory 数据 |
| `--process_document` | flag | True | 是否处理文档注册 |
| `--process_main` | flag | False | 是否处理主 Excel 文件 |
| `--process_all` | flag | False | 是否执行完整流程（Memory + 文档注册 + 主 Excel） |
| `--cycle` | int | 1 | 主 Excel 循环轮数 |
| `--gpu_type` | string | "iGPU" | GPU 类型：dGPU / iGPU / aGPU |
| `--test_mode` | string | "cloud" | 运行模式：cloud / local（本地会关/开 WiFi） |
| `--version_config` | string | "v20260226_1120-R73.25" | 输出目录名与 config.json 的 version |
| `--test_mode_config` | string | "cloud" | 写入 config.json 的 test_mode |
| `--filter_local_brain` | string | "yes" | 是否过滤 "Local Brain with"：auto / yes / no |
| `--min_wait_time` | float | 5.0 | 随机等待最小时间（秒） |
| `--max_wait_time` | float | 10.0 | 随机等待最大时间（秒） |
| `--enable_random_wait` | bool | True | 是否启用随机等待 |
| `--cleanup_after_run` | flag | False | 运行结束后是否清理 Memory 与文档数据 |

> 说明：DLL 路径已改为自动发现（用户目录及 Program Files 下 Lenovo Qira），无需 `--dll_path`。

## ▶️ 使用方法

### 基本使用

推荐在项目根目录执行（以下两种方式等价）：

```bash
python main.py
```

### 常用示例

```bash
# 完整流程（Memory + 文档注册 + 主 Excel）
python main.py --process_all

# 仅主 Excel，循环 3 轮
python main.py --process_main --cycle 3

# 仅文档注册
python main.py --process_document

# 仅 Memory 数据
python main.py --process_memory

# 本地模式（会自动关/开 WiFi）
python main.py --test_mode local --process_main

# 指定版本与等待时间
python main.py --version_config v20260227 --min_wait_time 1 --max_wait_time 5
```

## 📊 输出文件说明

### 主测试结果（process_main / process_all）

- **路径**: `outputs/run_{RUN_ID}/testresult/test_results_{excel_stem}_{timestamp}.xlsx`
- **按轮次**: 同名前缀 + `_cycle1.xlsx`, `_cycle2.xlsx` ...
- **Sheet 'result'**: question、result、response_time、ttft、token_count、generation_speed、start_time、end_time、first_word_time、first_text_response_time、data_json_list、**toolname** 等
- **Sheet 'resource'**: 资源监控数据（若已启用监控）

### 文档注册

- `testresult/document_registration_{timestamp}.xlsx`
- `testresult/document_registration_{timestamp}_document.xlsx`：文档注册详情
- `registered_docs.json`：已注册文档列表（用于跳过重复注册）

### Memory 数据处理

- `Memory_data_with_responses_{timestamp}.xlsx`：每列 user_content 的 result、response_time、ttft、data_json_list、toolname 及平均值行
- 同前缀 `_get_all_memory.json`、`_get_all_ocr_memory.json`

### 日志与打包

- `logs/Quantum_api_{timestamp}.log`
- `logs/resource_monitor_{timestamp}.log`
- `resource/resource_{timestamp}.csv`
- 运行结束后打包为 **PackageAllLogs.zip**
- 若执行了主 Excel 流程，会生成 **TestResult_{version}_{mode}_{timestamp}.zip**（不含 PackageAllLogs.zip）

## 📈 性能指标说明

| 指标 | 含义 |
|------|------|
| 响应时间 | 从发送请求到任务完成/失败的时间 |
| TTFT | 首字时间（Time To First Token），从请求开始到首个 token/tool 响应 |
| 首字/首文本响应时间 | 第一个 text 或 tool 类型响应的时间点 |
| Token 数量 | 流式 text 类型消息计数 |
| 生成速度 | token_count / (结束时间 - 首字时间)，单位 tokens/秒 |

## 🔧 核心组件与代码结构（重构后）

### 入口与公共包

| 文件 | 说明 |
|------|------|
| `main.py` | 主入口：解析参数、初始化运行上下文、生成 config.json、加载 SDK、创建并设置 QuantumClientManager、执行主流程、打包与收尾 |
| `common/run_context.py` | 运行目录（OUTPUT_ROOT、LOGS_DIR、TEST_RESULTS_DIR 等）、`init_run_context`、`setup_logging`、运行时配置 `set_runtime_config` / `get_config`、`doc_details_path` 的 get/set |
| `common/quantum_sdk.py` | 加载 quantum-sdk DLL，定义 ctypes 回调与函数，`load_quantum_sdk(dll_path)` 返回 sdk 对象 |
| `common/quantum_client_manager.py` | **QuantumClientManager(sdk)**：连接与命令发送、回调解析、job 映射；单例 `get_quantum_client_manager()` / `set_quantum_client_manager(manager)` |
| `common/bundle.py` | `create_output_bundle_zip`：将输出目录打为 TestResult 总包 zip |
| `common/paths.py` | `find_quantum_sdk_dll_simple`、`get_quantum_core_path` |
| `common/resource_monitor.py` | `start_resource_monitoring`、`stop_resource_monitoring`、`add_resource_data_to_results` |
| `common/multimodal_api.py` | **MultimodalAPI**：会话、文档注册、Memory、主 Excel 处理等，通过 `get_quantum_client_manager()` 与 `get_config()` 获取客户端与配置 |
| `common/main_process.py` | `run_quantum_e2e_process(args)`、`merge_and_analyze_output_files(output_files)` |

### QuantumClientManager（common/quantum_client_manager.py）

- 连接量子 SDK、发送命令、回调中解析 type（handler/text/tool）、维护 job_id 与 MultimodalAPI 映射
- 模式识别（Local Brain / Azure Agent）、首字时间与 token 计数、结果队列与超时处理
- 依赖由 `main.py` 传入的 sdk 对象（`load_quantum_sdk` 返回），所有 SDK 调用通过 `self.sdk.xxx` 完成

### MultimodalAPI（common/multimodal_api.py）

- 会话创建、文档注册与状态轮询、Memory（add_memory / get_all_memory / get_all_ocr_memory）
- 主 Excel 行处理、new_session 复用、超时/失败重跑、toolname 提取（extract_toolname_from_data_json_list）
- 文档注册完成后调用注册时长分析（get_regist_duration_single_file）
- 路径与客户端来自 `common.run_context` 的 `get_config()` 与 `common.quantum_client_manager` 的 `get_quantum_client_manager()`

### 资源监控（common/resource_monitor.py）

- 按场景启动：仅 Memory 或仅文档注册、Memory+文档、或与主 Excel 一起时的预处理阶段与主 Excel 阶段
- 监控进程含 LenovoQiraCore、mcpMgmtService、lenovo.pfm.pipe、file-index-service、file-search-service 等
- 结果写入各阶段对应的 Excel 的 resource sheet

## 📝 Excel 格式要求

### 主测试 Excel

| 列名 | 必需 | 说明 |
|------|------|------|
| question | ✅ | 查询文本 |
| pathlist | ❌ | 图片文件名，逗号或分号分隔，在 image_dir 下查找 |
| new_session | ❌ | Y=新会话，N=复用上一行会话，默认 Y |

### Memory Excel

| 列名 | 说明 |
|------|------|
| 含 `user_content` 的列 | 会执行 add_memory，并输出 result、response_time、ttft、data_json_list、toolname |
| pathlist | 可选，图片文件名列表 |

## 🔄 主流程概览

1. **初始化**: 解析参数 → 初始化运行目录（outputs/run_{RUN_ID}）→ 生成 config.json → 加载 quantum-sdk DLL（自动查找）→ 可选关 WiFi（local）
2. **Memory（可选）**: 读 Memory_data.xlsx → 每行新会话 → 每列 add_memory → 写 Excel → 失败重跑（2 轮）→ 重算平均值 → get_all_memory / get_all_ocr_memory 并保存 JSON
3. **文档注册（可选）**: 创建会话 → 注册 doc_dir 下全部文档 → 轮询 get_register_document 直至完成率≥95% → 保存注册详情 → 注册时长分析（doc_details_path + quantum_core 日志）
4. **主 Excel（可选）**: 按 excel_dir 下 xlsx 逐个 → 每文件独立资源监控 → 按行执行 run_query_only（按 new_session 复用会话）→ 写 result/response_time/ttft/toolname 等 → 对超时与可重跑失败 case 再跑一轮 → 资源数据写入各 cycle 的 Excel
5. **收尾**: 云端模式可执行 combined_analysis（process_excel）；可选 cleanup_after_run；打包日志 → 本地模式执行 analysis_log_local → 若为主流程则生成 TestResult 总包 → 可选开 WiFi（local）→ 清理量子客户端

## 🐛 常见问题

- **连接失败**: 确认量子服务与 Lenovo Qira 环境正常；DLL 会在用户目录及 `C:\Program Files\Lenovo\Lenovo Qira\QuantumApp` 下自动查找。
- **文档注册卡住**: 查看 testresult 下文档注册详情表与日志中的完成率；确认 doc_dir 路径与文件可访问。
- **主 Excel 超时**: 脚本会自动重跑 “CTTVError: Request Timeout”“CTTVError: Stream timeout” 及部分 “CTTVError: Task failed”（排除 failed_input_safety）；若仍失败可检查网络与服务负载。
- **本地模式**: 需管理员或允许修改网络适配器；关 WiFi 后等待约 60 秒再跑用例。

## 📋 日志位置

- 主日志: `outputs/run_{RUN_ID}/logs/Quantum_api_{timestamp}.log`
- 资源监控: `logs/resource_monitor_{timestamp}.log`，数据 `resource/resource_{timestamp}.csv`

---

📝 **提示**: 首次使用请确认 dataset、image_dir、doc_dir、memory_excel 等路径正确，且量子 SDK 与 Lenovo Qira 服务已就绪。
