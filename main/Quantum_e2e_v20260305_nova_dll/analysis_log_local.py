import pandas as pd
import re
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
import sys
from datetime import date
import difflib
import glob
import zipfile
import shutil


def extract_zip_if_needed(folder_path):
    """
    检查并解压 PackageAllLog.zip 文件
    
    Args:
        folder_path: 根文件夹路径
    
    Returns:
        解压后的文件夹路径，如果不需要解压则返回None
    """
    zip_path = os.path.join(folder_path, "PackageAllLogs.zip")
    extract_path = os.path.join(folder_path, "PackageAllLogs")
    
    if os.path.exists(extract_path):
        print(f"✓ PackageAllLog 文件夹已存在: {extract_path}")
        return extract_path
    
    if os.path.exists(zip_path):
        print(f"📦 发现 PackageAllLogs.zip，开始解压...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(folder_path)
            print(f"✓ 解压完成: {extract_path}")
            return extract_path
        except Exception as e:
            print(f"✗ 解压失败: {e}")
            return None
    
    print(f"⚠️ 未找到 PackageAllLogs 文件夹或 PackageAllLogs.zip 文件")
    return None



def find_log_path(folder_path):
    """
    查找日志文件夹路径,支持多层级递归查找
    优先查找 pod7_10_28 文件夹下的 quantum_core 开头的日志文件
    如果没有,则查找 pod1_20_QiraApp 文件夹下的 qtcore 开头的日志文件
    
    Args:
        folder_path: 根文件夹路径
    
    Returns:
        日志文件夹路径,如果未找到返回None
    """
    # 首先检查是否需要解压
    package_all_log_path = extract_zip_if_needed(folder_path)
    
    if not package_all_log_path:
        return None
    
    def check_for_log_files(target_folder, log_prefix):
        """
        检查目标文件夹中是否有指定前缀的日志文件
        
        Args:
            target_folder: 目标文件夹路径
            log_prefix: 日志文件前缀(如 'quantum_core' 或 'qtcore')
        
        Returns:
            如果找到日志文件返回True,否则返回False
        """
        log_extensions = ['.log', '.txt', '']  # 空字符串用于匹配无扩展名的文件
        
        for ext in log_extensions:
            pattern = os.path.join(target_folder, f'{log_prefix}*{ext}')
            if glob.glob(pattern):
                return True
        
        return False
    
    def find_target_folder(root_path, target_name, max_depth=5, current_depth=0):
        """
        递归查找目标文件夹
        
        Args:
            root_path: 搜索根路径
            target_name: 目标文件夹名称
            max_depth: 最大搜索深度
            current_depth: 当前深度
        
        Returns:
            找到的路径或None
        """
        if current_depth > max_depth:
            return None
        
        try:
            for item in os.listdir(root_path):
                item_path = os.path.join(root_path, item)
                
                if not os.path.isdir(item_path):
                    continue
                
                # 检查是否是目标文件夹
                if item == target_name:
                    return item_path
                
                # 递归搜索子文件夹
                result = find_target_folder(item_path, target_name, max_depth, current_depth + 1)
                if result:
                    return result
        except PermissionError:
            pass
        
        return None
    
    # 第一步: 查找 pod7_10_28 文件夹
    print(f"🔍 递归查找 pod7_10_28 文件夹...")
    pod7_path = find_target_folder(package_all_log_path, "pod7_10_28")
    
    if pod7_path:
        print(f"✓ 找到 pod7_10_28 文件夹: {pod7_path}")
        # 检查是否有 quantum_core 开头的日志文件
        if check_for_log_files(pod7_path, "quantum_core"):
            print(f"✓ 找到 quantum_core 开头的日志文件")
            return pod7_path
        else:
            print(f"✗ pod7_10_28 文件夹中未找到 quantum_core 开头的日志文件")
    else:
        print(f"✗ 未找到 pod7_10_28 文件夹")
    
    # 第二步: 如果第一步失败,查找 pod1_20_QiraApp 文件夹
    print(f"🔍 递归查找 pod1_20_QiraApp 文件夹...")
    pod1_path = find_target_folder(package_all_log_path, "pod1_20_QiraApp")
    
    if pod1_path:
        print(f"✓ 找到 pod1_20_QiraApp 文件夹: {pod1_path}")
        # 检查是否有 qtcore 开头的日志文件
        if check_for_log_files(pod1_path, "qtcore"):
            print(f"✓ 找到 qtcore 开头的日志文件")
            return pod1_path
        else:
            print(f"✗ pod1_20_QiraApp 文件夹中未找到 qtcore 开头的日志文件")
    else:
        print(f"✗ 未找到 pod1_20_QiraApp 文件夹")
    
    # 如果都没找到
    print(f"✗ 未找到符合条件的日志文件夹")
    return None

def find_latest_excel(folder_path, subfolder, prefix):
    """
    在指定子文件夹中查找最新的以指定前缀开头的Excel文件
    
    Args:
        folder_path: 根文件夹路径
        subfolder: 子文件夹名称
        prefix: 文件名前缀
    
    Returns:
        找到的Excel文件路径，如果未找到返回None
    """
    search_path = os.path.join(folder_path, subfolder)
    
    if not os.path.exists(search_path):
        print(f"⚠️ 文件夹不存在: {search_path}")
        return None
    
    # 查找所有匹配的Excel文件
    pattern = os.path.join(search_path, f"{prefix}*.xlsx")
    matching_files = glob.glob(pattern)
    
    if not matching_files:
        print(f"⚠️ 未找到匹配的文件: {pattern}")
        return None
    
    # 按修改时间排序，获取最新的文件
    latest_file = max(matching_files, key=os.path.getmtime)
    print(f"✓ 找到文件: {os.path.basename(latest_file)}")
    
    return latest_file

def auto_locate_files(root_folder):
    """
    自动定位所需的所有文件
    
    Args:
        root_folder: 根文件夹路径
    
    Returns:
        dict: 包含所有文件路径的字典
    """
    print("" + "="*60)
    print("自动定位文件")
    print("="*60)
    print(f"根目录: {root_folder}")
    
    result = {
        'log_path': None,
        'input_path': None,
        'regist_path': None
    }
    
    # 1. 查找日志路径
    print("[1/3] 查找日志路径...")
    result['log_path'] = find_log_path(root_folder)
    
    # 2. 查找输入Excel文件
    print("[2/3] 查找输入Excel文件...")
    result['input_path'] = find_latest_excel(root_folder, "testresult", "test")
    
    # 3. 查找注册Excel文件
    print("[3/3] 查找注册Excel文件...")
    result['regist_path'] = find_latest_excel(root_folder, "testresult", "document_registration")
    
    # 打印结果摘要
    print("" + "="*60)
    print("文件定位结果")
    print("="*60)
    for key, value in result.items():
        status = "✓" if value else "✗"
        print(f"{status} {key}: {value if value else '未找到'}")
    
    return result


def alike(a: str, b: str, threshold: float = 0.9) -> bool:
    """相似度≥threshold返回True"""
    score = difflib.SequenceMatcher(None, a, b).ratio()
    print(f'相似度={score:.3f}')
    return score >= threshold

def get_span_name(trace_data):
    """提取并标准化 span 名称"""
    name_value = trace_data.get('name', '')
    
    # $Proxy 开头的统一命名为 TaskExecutionNode
    if str(name_value).startswith("$Proxy"):
        return "TaskExecutionNode"
    
    # 使用 name
    if name_value:
        return name_value
    
    # 都没有则返回默认值
    return "Unknown"


def extract_node_info(trace_data):
    """从不同节点的 attributes 中提取信息"""
    node_name = trace_data.get('name', '')
    attributes = trace_data.get('attributes', {})
    completion_str = attributes.get('gen_ai.completion', '')
    
    result = {
        'FINAL_ANSWER': None,
        'LOCAL_TOOL_RETURN': None,
        'NEED_REWRITE': None,
        'REWRITE_QUERY': None,
        'CURRENT_INTENT_MAPPING': None,
        'CURRENT_INTENT_RECOGNITION': None,
        'DOMAIN': None,
        'Retrieval_start_time': None,
        'MemoryRetrievalTop3': None,
        'search_file_list': None,
        'search_text_list': None,
    }
    
    if not completion_str:
        return result
    
    
    # 从 SearchMemory 提取答案
    if node_name == 'SearchMemory':
        MemoryRetrievalTop3_list = str(completion_str).split('\n')
        if MemoryRetrievalTop3_list:
            result['MemoryRetrievalTop3'] = str(MemoryRetrievalTop3_list)
    
    # 从SearchKnowledge提取答案
    if node_name == 'SearchKnowledge':
        KB_line = completion_str
        print("==============================")
        file_name_pat = re.compile(r'<document_title>(.*?)</document_title>', re.DOTALL)
        file_name = file_name_pat.findall(KB_line)
        result['search_file_list'] = str(file_name)
        print(file_name[:3])
        # if file_name==[]:
        #     print(line)
        text_list_pat = re.compile(r'<context>(.*?)</context>', re.DOTALL)
        text_list = text_list_pat.findall(KB_line)
        result['search_text_list'] = str(text_list)
        # print(len(text_list))

    
    try:
        completion_data = json.loads(completion_str)
        
        # 从 LocalGraph 节点提取 FINAL_ANSWER 和 LOCAL_TOOL_RETURN
        if node_name == 'LocalGraph':
            final_answer_raw = completion_data.get('FINAL_ANSWER', '')
            if final_answer_raw:
                result['FINAL_ANSWER'] = final_answer_raw
            
            local_tool_raw = completion_data.get('LOCAL_TOOL_RETURN', '')
            if local_tool_raw:
                try:
                    local_tool = json.loads(local_tool_raw)
                    result['LOCAL_TOOL_RETURN'] = str(local_tool)
                except:
                    result['LOCAL_TOOL_RETURN'] = local_tool_raw
        
        # 从 RewriteJudgeNode 提取 NEED_REWRITE 和 REWRITE_QUERY
        elif node_name == 'RewriteJudgeNode':
            need_rewrite = str(completion_data.get('NEED_REWRITE', ''))
            if need_rewrite:
                result['NEED_REWRITE'] = str(need_rewrite)
            
            rewrite_query = completion_data.get('REWRITE_QUERY', '')
            if rewrite_query:
                result['REWRITE_QUERY'] = str(rewrite_query)
        
        # 从 IntentMappingNode 提取 CURRENT_INTENT_MAPPING
        elif node_name == 'IntentMappingNode':
            intent_mapping = completion_data.get('CURRENT_INTENT_MAPPING', '')
            if intent_mapping:
                try:
                    intent_mapping_data = json.loads(intent_mapping)
                    result['CURRENT_INTENT_MAPPING'] = str(intent_mapping_data)
                except:
                    result['CURRENT_INTENT_MAPPING'] = intent_mapping
        
        # 从 IntentUnderstandingNode 提取 CURRENT_INTENT_RECOGNITION
        elif node_name == 'IntentUnderstandingNode':
            intent_recognition = completion_data.get('CURRENT_INTENT_RECOGNITION', '')
            if intent_recognition:
                try:
                    intent_data = json.loads(intent_recognition)
                    result['CURRENT_INTENT_RECOGNITION'] = str(intent_data)
                except:
                    result['CURRENT_INTENT_RECOGNITION'] = intent_recognition
        
        # 从 DomainClassifierNode 提取 DOMAIN
        elif node_name == 'DomainClassifierNode':
            domain_raw = completion_data.get('DOMAIN', '')
            if domain_raw:
                try:
                    domain_data = json.loads(domain_raw)
                    domain_confidence = domain_data.get('domainConfidence', {})
                    result['DOMAIN'] = str(domain_confidence)
                except:
                    result['DOMAIN'] = domain_raw
        elif node_name == 'GeneralGenerationNode':
            retrieval_start_time_raw = trace_data.get('start_time', '')
            # 1766299497552128500转成时间格式
            if retrieval_start_time_raw:
                try:
                    # 将纳秒时间戳转换为秒
                    timestamp_seconds = int(retrieval_start_time_raw) / 1_000_000_000
                    # 转换为 datetime 对象
                    retrieval_start_time_dt = datetime.fromtimestamp(timestamp_seconds)
                    # 格式化为字符串（保留毫秒）
                    retrieval_start_time = retrieval_start_time_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    result['Retrieval_start_time'] = retrieval_start_time
                except (ValueError, TypeError) as e:
                    # 如果转换失败，保留原始值
                    result['Retrieval_start_time'] = str(retrieval_start_time_raw)
    
    except Exception as e:
        pass
    
    return result


def parse_quantum_log(log_file_path):
    """解析Quantum Core日志文件，提取Span Trace信息"""
    log_entries = []
    time_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})'
    
    print(f"📄 正在解析: {os.path.basename(log_file_path)}")
    
    try:
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # 只处理包含 [Span Trace] 的行
                if '[Span Trace]' not in line:
                    continue
                
                time_match = re.search(time_pattern, line)
                if not time_match:
                    continue
                
                timestamp_str = time_match.group(1)
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                
                # 提取JSON部分
                json_match = re.search(r'\[Span Trace\]:(\{.+\})', line)
                if json_match:
                    try:
                        trace_data = json.loads(json_match.group(1))
                        
                        # 提取节点信息
                        node_info = extract_node_info(trace_data)
                        
                        log_entries.append({
                            'timestamp': timestamp,
                            'trace_id': trace_data.get('trace_id', ''),
                            'span_id': trace_data.get('span_id', ''),
                            'name': get_span_name(trace_data),
                            'duration_ms': trace_data.get('duration_ms', 0),
                            'source_file': os.path.basename(log_file_path),
                            **node_info  # 展开节点信息
                        })
                    except json.JSONDecodeError as e:
                        continue
    except Exception as e:
        print(f"⚠️ 读取文件 {log_file_path} 时出错: {e}")
    
    print(f"   ✓ 找到 {len(log_entries)} 条 Span Trace 记录")
    return log_entries



def parse_all_logs_in_folder(log_folder_path):
    """解析文件夹中所有以quantum_core开头的日志文件"""
    all_entries = []
    
    # 支持的日志文件扩展名
    log_extensions = ['.log', '.txt']
    
    # 如果传入的文件夹名是pod7_10_28，获取所有以quantum_core开头的日志文件，如果传入的是pod1_20_QiraApp，获取所有以qtcore开头的日志文件
    folder_name = os.path.basename(log_folder_path)
    if folder_name.startswith("pod7_10_28"):
        prefix = "quantum_core"
    elif folder_name.startswith("pod1_20_QiraApp"):
        prefix = "qtcore"
    else:
        prefix = "quantum_core"
    
    log_files = []
    for ext in log_extensions:
        log_files.extend(Path(log_folder_path).glob(f'{prefix}*{ext}'))
    
    if not log_files:
        print(f"⚠️ 在文件夹 {log_folder_path} 中没有找到以 '{prefix}' 开头的日志文件")
        return []
    
    # 排序：quantum_core.log 放最后
    sorted_log_files = sorted(log_files, key=lambda f: (f.name == f'{prefix}.log', f.name))
    
    print(f"\n📂 找到 {len(sorted_log_files)} 个 {prefix} 日志文件")
    print("=" * 60)
    print("文件处理顺序:")
    for i, log_file in enumerate(sorted_log_files, 1):
        print(f"  {i}. {log_file.name}")
    print("=" * 60)
    
    # 解析每个日志文件
    for log_file in sorted_log_files:
        print(f"\n📄 正在解析: {log_file.name}")
        entries = parse_quantum_log(str(log_file))
        all_entries.extend(entries)
        print(f"   ✓ 解析到 {len(entries)} 条记录")
    
    print("=" * 60)
    print(f"📊 总共解析到 {len(all_entries)} 条 Span Trace 记录")
    
    return all_entries

def time_gap(time1,time2):
    if "." in str(time1):
        t1 = datetime.strptime(str(time1), '%H:%M:%S.%f')
    else:
        t1 = datetime.strptime(str(time1) + '.000000', '%H:%M:%S.%f')
    if "." in str(time2):
        t2 = datetime.strptime(str(time2), '%H:%M:%S.%f')
    else:
        t2 = datetime.strptime(str(time2) + '.000000', '%H:%M:%S.%f')
    delta = t2 - t1  # 得到 timedelta 对象
    print(delta.total_seconds())  # 62.12 秒
    return delta.total_seconds()
def debug_time(element,list):
    debug_time_pat = re.compile(r' (.*) \[DEBUG\]')
    for ele in element:
        time = debug_time_pat.findall(ele)
        # print(time)
        list.append(time)
        if time==[]:
            print("=============error========"+str(element))
    return list

def info_time(element,list):
    debug_time_pat = re.compile(r' (.*) \[INFO\]')
    for ele in element:
        time = debug_time_pat.findall(ele)
        # print(time)
        list.append(time)
        if time==[]:
            print("=============error========"+str(element))
    return list


def extract_model_service_timings(df, log_folder_path, output_file):
    """
    从日志中提取 model_service response 的 timings 信息
    并添加到 DataFrame 的新列中
    """
    # 初始化新列
    df['prompt_n'] = None
    df['prompt_ms'] = None
    df['prompt_per_token_ms'] = None
    df['prompt_per_second'] = None
    df['predicted_n'] = None
    df['predicted_ms'] = None
    df['predicted_per_token_ms'] = None
    df['predicted_per_second'] = None
    df['model_service_model'] = ''
    df['model_service_total_tokens'] = None
    
    # 读取所有日志文件
    all_log_lines = []
    for log_file in Path(log_folder_path).rglob('*.log'):
        try:
            with log_file.open('r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'model_service response' in line:
                        all_log_lines.append(line)
        except Exception as e:
            print(f"⚠️ 读取文件 {log_file} 时出错: {e}")
    
    print(f"\n📊 找到 {len(all_log_lines)} 条 model_service response 记录")
    
    # 时间戳正则表达式
    time_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})')
    
    # 对每一行 DataFrame 进行处理
    for idx in range(len(df)):
        start_time_obj = df.loc[idx, 'start_time']
        end_time_obj = df.loc[idx, 'end_time']
        
        # 转换时间格式
        if isinstance(start_time_obj, pd.Timestamp):
            start_time = start_time_obj.to_pydatetime()
        elif isinstance(start_time_obj, str):
            try:
                start_time = datetime.strptime(start_time_obj, '%Y-%m-%d %H:%M:%S.%f')
            except:
                continue
        else:
            continue
        
        if isinstance(end_time_obj, pd.Timestamp):
            end_time = end_time_obj.to_pydatetime()
        elif isinstance(end_time_obj, str):
            try:
                end_time = datetime.strptime(end_time_obj, '%Y-%m-%d %H:%M:%S.%f')
            except:
                continue
        else:
            continue
        
        # 在时间范围内查找 model_service response
        matched_responses = []
        for line in all_log_lines:
            time_match = time_pattern.search(line)
            if time_match:
                log_time_str = time_match.group(1)
                try:
                    log_time = datetime.strptime(log_time_str, '%Y-%m-%d %H:%M:%S.%f')
                    if start_time <= log_time <= end_time:
                        matched_responses.append(line)
                except:
                    continue
        
        if not matched_responses:
            continue
        
        print(f"\n🔍 第 {idx+1} 行找到 {len(matched_responses)} 条匹配记录")
        
        # 解析最后一条匹配的响应（通常是最相关的）
        for response_line in reversed(matched_responses):  # 从最后一条开始
            try:
                # 提取 model_service response 后的内容
                response_match = re.search(r'model_service response = (.+)$', response_line)
                if not response_match:
                    continue
                
                response_str = response_match.group(1)
                
                # 尝试解析为 JSON（可能是嵌套列表格式）
                # 格式: [["key1", value1], ["key2", value2], ...]
                response_data = json.loads(response_str)  # 使用 eval 因为格式不是标准 JSON
                
                # 转换为字典
                response_dict = {}
                for item in response_data:
                    if isinstance(item, list) and len(item) >= 2:
                        key = item[0]
                        value = item[1] if len(item) == 2 else item[1:]
                        response_dict[key] = value
                
                # 提取 timings 信息
                if 'timings' in response_dict:
                    
                    # 将这个response_dict的内容保存成json文件，保存在model_service_logs文件夹中,excel保存json文件名
                    # 在output_file同级目录创建model_service_logs文件夹
                    output_dir = os.path.join(os.path.dirname(output_file), "model_service_responses")
                    os.makedirs(output_dir, exist_ok=True)
                    json_filename = os.path.join(output_dir, f"response_{idx+1}.json")
                    with open(json_filename, "w", encoding="utf-8") as json_file:
                        json.dump(response_dict, json_file, ensure_ascii=False, indent=4)
                    
                    timings = response_dict['timings']
                    if isinstance(timings, dict):
                        df.loc[idx, 'prompt_n'] = timings.get('prompt_n')
                        df.loc[idx, 'prompt_ms'] = timings.get('prompt_ms')
                        df.loc[idx, 'prompt_per_token_ms'] = timings.get('prompt_per_token_ms')
                        df.loc[idx, 'prompt_per_second'] = timings.get('prompt_per_second')
                        df.loc[idx, 'predicted_n'] = timings.get('predicted_n')
                        df.loc[idx, 'predicted_ms'] = timings.get('predicted_ms')
                        df.loc[idx, 'predicted_per_token_ms'] = timings.get('predicted_per_token_ms')
                        df.loc[idx, 'predicted_per_second'] = timings.get('predicted_per_second')
                        df.loc[idx, 'model_service_responses_json_name'] = os.path.basename(json_filename)
                        
                        print(f"  ✓ 提取 timings: prompt={timings.get('prompt_ms')}ms, predicted={timings.get('predicted_ms')}ms")
                
                # # 提取 model 信息
                # if 'model' in response_dict:
                #     model_path = response_dict['model']
                #     # 只保留文件名
                #     if isinstance(model_path, str):
                #         model_name = Path(model_path).name
                #         df.loc[idx, 'model_service_model'] = model_name
                
                # # 提取 usage 信息
                # if 'usage' in response_dict:
                #     usage = response_dict['usage']
                #     if isinstance(usage, dict):
                #         df.loc[idx, 'model_service_total_tokens'] = usage.get('total_tokens')
                
                # 找到一条有效记录后跳出
                break
                
            except Exception as e:
                print(f"  ⚠️ 解析响应时出错: {e}")
                continue
    
    return df


def enrich_dataframe_with_logs(input_df, log_folder_path):
    """在原 DataFrame 上补充日志信息列"""
    all_entries = parse_all_logs_in_folder(log_folder_path)

    if not all_entries:
        print("⚠️ 日志文件中没有找到有效的 [Span Trace] 日志条目")
        return input_df
    
    # 按时间排序
    all_entries.sort(key=lambda x: x['timestamp'])

    # 先按 trace_id 分组所有日志
    all_trace_groups = defaultdict(list)
    for entry in all_entries:
        all_trace_groups[entry['trace_id']].append(entry)
    
    # 定义 duration 列的顺序
    duration_columns = [
        'DomainClassifierNode',
        'RewriteJudgeNode',
        'IntentMappingNode',
        'IntentUnderstandingNode',
        'TaskExecutionNode',
        'LocalGreetingNode',
        'SearchMemory',
        'SearchKnowledge',
        'GenerateDuration',
        'Unknown',
        'LocalGraph',
        'GeneralGenerationNode'
    ]
    
    # 初始化新列
    input_df['trace_id'] = ''
    input_df['trace_start_time'] = ''
    input_df['trace_end_time'] = ''
    input_df['source_file'] = ''
    input_df['span_count'] = 0
    input_df['DOMAIN'] = ''
    input_df['CURRENT_INTENT_MAPPING'] = ''
    input_df['CURRENT_INTENT_RECOGNITION'] = ''
    input_df['NEED_REWRITE'] = ''
    input_df['REWRITE_QUERY'] = ''
    input_df['FINAL_ANSWER'] = ''
    input_df['LOCAL_TOOL_RETURN'] = ''
    input_df['MemoryRetrievalTop3'] = ''
    input_df['search_file_list'] = ''
    input_df['search_text_list'] = ''
    
    
    
    # 初始化 duration 列
    for col in duration_columns:
        input_df[col] = None
    
    # 🔥 对每一行进行处理
    for idx in range(len(input_df)):
        start_time_obj = input_df.loc[idx, 'start_time']
        end_time_obj = input_df.loc[idx, 'end_time']
        
        print(f"\n{'='*60}")
        print(f"📝 处理第 {idx+1}/{len(input_df)} 行")
        print(f"{'='*60}")
        
        # 处理 start_time
        if isinstance(start_time_obj, pd.Timestamp):
            start_time = start_time_obj.to_pydatetime()
        elif isinstance(start_time_obj, str):
            start_time = datetime.strptime(start_time_obj, '%Y-%m-%d %H:%M:%S.%f')
        else:
            print(f"⚠️ 跳过无效的起始时间格式: {start_time_obj}")
            continue
        
        # 处理 end_time
        if isinstance(end_time_obj, pd.Timestamp):
            end_time = end_time_obj.to_pydatetime()
        elif isinstance(end_time_obj, str):
            end_time = datetime.strptime(end_time_obj, '%Y-%m-%d %H:%M:%S.%f')
        else:
            print(f"⚠️ 跳过无效的结束时间格式: {end_time_obj}")
            continue
        
        # 计算查询结束时间：max(下一行的start_time, 当前行end_time+1s)
        end_time_plus_1s = end_time + timedelta(seconds=1)
        
        if idx + 1 < len(input_df):
            next_start_time_obj = input_df.loc[idx + 1, 'start_time']
            if isinstance(next_start_time_obj, pd.Timestamp):
                next_start_time = next_start_time_obj.to_pydatetime()
            elif isinstance(next_start_time_obj, str):
                next_start_time = datetime.strptime(next_start_time_obj, '%Y-%m-%d %H:%M:%S.%f')
            else:
                next_start_time = end_time_plus_1s
            
            query_end_time = max(end_time_plus_1s, next_start_time)
        else:
            query_end_time = end_time_plus_1s
        
        # 第一步：在时间区间内找到第一个 trace_id
        first_trace_id = None
        for entry in all_entries:
            if start_time <= entry['timestamp'] <= query_end_time:
                first_trace_id = entry['trace_id']
                break
        
        if not first_trace_id:
            print(f"⚠️ 未找到匹配的日志")
            continue
        
        print(f"✓ 找到 trace_id: {first_trace_id}")
        
        # 第二步：获取该 trace_id 在时间区间内的所有节点
        entries_in_range = [
            entry for entry in all_trace_groups[first_trace_id]
            if start_time <= entry['timestamp'] <= query_end_time
        ]
        
        if not entries_in_range:
            print(f"⚠️ trace_id {first_trace_id} 在时间区间内没有节点")
            input_df.loc[idx, 'trace_id'] = first_trace_id
            continue
        
        # 获取该 trace 的时间范围
        timestamps = [e['timestamp'] for e in entries_in_range]
        trace_start = min(timestamps)
        trace_end = max(timestamps)
        
        print(f"✓ 找到 {len(entries_in_range)} 个节点")
        
        # 从不同节点提取信息
        final_answer = ''
        local_tool = ''
        need_rewrite = ''
        rewrite_query = ''
        intent_mapping = ''
        intent_recognition = ''
        domain = ''
        MemoryRetrievalTop3 = ''
        search_file_list = '[]'
        search_text_list = '[]'

        
        for entry in entries_in_range:
            if entry['MemoryRetrievalTop3'] is not None:
                MemoryRetrievalTop3 = entry['MemoryRetrievalTop3']
                print(f"✓ 从 SearchMemory 找到 MemoryRetrievalTop3")
            if entry['search_file_list'] is not None:
                search_file_list = entry['search_file_list']
                print(f"✓ 从 SearchMemory 找到 search_file_list")
            if entry['search_text_list'] is not None:
                search_text_list = entry['search_text_list']
                print(f"✓ 从 SearchMemory 找到 search_text_list")
            # 从 LocalGraph 提取
            if entry['FINAL_ANSWER'] is not None:
                final_answer = entry['FINAL_ANSWER']
                print(f"✓ 从 LocalGraph 找到 FINAL_ANSWER")
            if entry['LOCAL_TOOL_RETURN'] is not None:
                local_tool = entry['LOCAL_TOOL_RETURN']
                print(f"✓ 从 LocalGraph 找到 LOCAL_TOOL_RETURN")
            
            # 从 RewriteJudgeNode 提取
            if entry['NEED_REWRITE'] is not None:
                need_rewrite = entry['NEED_REWRITE']
                print(f"✓ 从 RewriteJudgeNode 找到 NEED_REWRITE")
            if entry['REWRITE_QUERY'] is not None:
                rewrite_query = entry['REWRITE_QUERY']
                print(f"✓ 从 RewriteJudgeNode 找到 REWRITE_QUERY")
            
            # 从 IntentMappingNode 提取
            if entry['CURRENT_INTENT_MAPPING'] is not None:
                intent_mapping = entry['CURRENT_INTENT_MAPPING']
                print(f"✓ 从 IntentMappingNode 找到 CURRENT_INTENT_MAPPING")
            
            # 从 IntentUnderstandingNode 提取
            if entry['CURRENT_INTENT_RECOGNITION'] is not None:
                intent_recognition = entry['CURRENT_INTENT_RECOGNITION']
                print(f"✓ 从 IntentUnderstandingNode 找到 CURRENT_INTENT_RECOGNITION")
            
            # 从 DomainClassifierNode 提取
            if entry['DOMAIN'] is not None:
                domain = entry['DOMAIN']
                print(f"✓ 从 DomainClassifierNode 找到 DOMAIN")
            
        # 填充基本信息列
        input_df.loc[idx, 'trace_id'] = first_trace_id
        input_df.loc[idx, 'trace_start_time'] = trace_start.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        input_df.loc[idx, 'trace_end_time'] = trace_end.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        input_df.loc[idx, 'source_file'] = entries_in_range[0]['source_file']
        input_df.loc[idx, 'span_count'] = len(entries_in_range)
        input_df.loc[idx, 'DOMAIN'] = domain
        input_df.loc[idx, 'CURRENT_INTENT_MAPPING'] = intent_mapping
        input_df.loc[idx, 'CURRENT_INTENT_RECOGNITION'] = intent_recognition
        input_df.loc[idx, 'NEED_REWRITE'] = need_rewrite
        input_df.loc[idx, 'REWRITE_QUERY'] = rewrite_query
        input_df.loc[idx, 'FINAL_ANSWER'] = final_answer
        input_df.loc[idx, 'LOCAL_TOOL_RETURN'] = local_tool
        input_df.loc[idx, 'MemoryRetrievalTop3'] = MemoryRetrievalTop3
        input_df.loc[idx, 'search_file_list'] = search_file_list
        input_df.loc[idx, 'search_text_list'] = search_text_list

        # 处理 duration 列
        duration_dict = {}
        for entry in entries_in_range:
            column_name = entry['name']
            
            # 如果同一个 name 出现多次，取最大值
            if column_name in duration_dict:
                duration_dict[column_name] = max(duration_dict[column_name], entry['duration_ms'])
            else:
                duration_dict[column_name] = entry['duration_ms']
        
        # 填充到 DataFrame
        for col_name, duration_value in duration_dict.items():
            if col_name in duration_columns:
                input_df.loc[idx, col_name] = duration_value
        
        # 计算 GenerateDuration（GeneralGenerationNode - RetrievalDuration）
        general_generation_duration = input_df.loc[idx, 'GeneralGenerationNode']
        SearchKnowledge_duration = input_df.loc[idx, 'SearchKnowledge'] 
        SearchMemory_duration = input_df.loc[idx, 'SearchMemory'] 
        if pd.notna(general_generation_duration) and pd.notna(SearchKnowledge_duration) and pd.notna(SearchMemory_duration):
            generate_duration = general_generation_duration - SearchKnowledge_duration - SearchMemory_duration
            input_df.loc[idx, 'GenerateDuration'] = generate_duration
            print(f"✓ 计算 GenerateDuration: {generate_duration:.3f} 毫秒")
        
        # 计算 Unknown 列（LocalGraph - 其他列）
        local_graph_duration = input_df.loc[idx, 'LocalGraph']
        if pd.notna(local_graph_duration):
            other_columns_sum = 0
            for col in duration_columns:
                if col not in ['Unknown', 'LocalGraph', 'GeneralGenerationNode']:
                    val = input_df.loc[idx, col]
                    if pd.notna(val):
                        other_columns_sum += val
            
            unknown_duration = local_graph_duration - other_columns_sum
            input_df.loc[idx, 'Unknown'] = unknown_duration
            print(f"✓ 计算 Unknown: {unknown_duration:.3f} 毫秒")
        print(f"✅ 第 {idx+1} 行处理完成")

    
    return input_df



def get_result_duration(EXCEL_FILE, OUTPUT_FILE, LOG_FOLDER):

    print("=" * 60)
    print("🚀 Quantum Core 日志结果分析工具")
    print("=" * 60)
    
    # 1. 读取输入Excel
    try:
        input_df = pd.read_excel(EXCEL_FILE)
        
        # 检查必需的列
        if 'start_time' not in input_df.columns:
            print("❌ 错误: Excel文件中没有 'start_time' 列")
            exit(1)
        
        if 'end_time' not in input_df.columns:
            print("❌ 错误: Excel文件中没有 'end_time' 列")
            exit(1)
        # 按 start_time 排序
        input_df = input_df.sort_values(by='start_time').reset_index(drop=True)
        
        print(f"\n📊 读取到 {len(input_df)} 行数据")
        print(f"📋 原始列: {list(input_df.columns)}")
        
    except FileNotFoundError:
        print(f"❌ 错误: 找不到文件 '{EXCEL_FILE}'")
        exit(1)
    except Exception as e:
        print(f"❌ 读取Excel文件时出错: {e}")
        exit(1)
    
    # 2. 在原 DataFrame 上补充日志信息
    enriched_df = enrich_dataframe_with_logs(input_df, LOG_FOLDER)
    
    # 3. 提取 model_service timings 信息
    print("\n" + "=" * 60)
    print("🔧 提取 Model Service Timings 信息")
    print("=" * 60)
    enriched_df = extract_model_service_timings(enriched_df, LOG_FOLDER, OUTPUT_FILE)
    
    print(enriched_df)

    
    # 4. 保存结果
    if enriched_df is not None:
        enriched_df.to_excel(OUTPUT_FILE, sheet_name='result', index=False)
        try:
            print("\n" + "=" * 60)
            print(f"✅ 成功处理 {len(enriched_df)} 行记录")
            print(f"📁 结果已保存到: {OUTPUT_FILE}")
            print("=" * 60)
            
            # 显示统计信息
            print("\n📈 统计信息:")
            print(f"   - 总行数: {len(enriched_df)}")
            print(f"   - 匹配到 trace_id 的行数: {(enriched_df['trace_id'] != '').sum()}")
            print(f"   - 找到 DOMAIN 的记录: {(enriched_df['DOMAIN'] != '').sum()}")
            print(f"   - 找到 CURRENT_INTENT_RECOGNITION 的记录: {(enriched_df['CURRENT_INTENT_RECOGNITION'] != '').sum()}")
            print(f"   - 找到 CURRENT_INTENT_MAPPING 的记录: {(enriched_df['CURRENT_INTENT_MAPPING'] != '').sum()}")
            print(f"   - 找到 NEED_REWRITE 的记录: {(enriched_df['NEED_REWRITE'] != '').sum()}")
            print(f"   - 找到 REWRITE_QUERY 的记录: {(enriched_df['REWRITE_QUERY'] != '').sum()}")
            print(f"   - 找到 FINAL_ANSWER 的记录: {(enriched_df['FINAL_ANSWER'] != '').sum()}")
            print(f"   - 找到 LOCAL_TOOL_RETURN 的记录: {(enriched_df['LOCAL_TOOL_RETURN'] != '').sum()}")
            print(f"   - 找到 Model Service Timings 的记录: {enriched_df['prompt_ms'].notna().sum()}")


            print(f"   - 计算出 GenerateDuration 的记录: {(enriched_df['GenerateDuration'] != '').sum()}")
            
            if (enriched_df['trace_id'] != '').sum() > 0:
                print(f"   - 平均 span 数量: {enriched_df[enriched_df['span_count'] > 0]['span_count'].mean():.2f}")
            
            if (enriched_df['SearchMemory'] != '').sum() > 0:
                durations = enriched_df[enriched_df['SearchMemory'] != '']['SearchMemory'].astype(float)
                print(f"   - 平均 SearchMemory: {durations.mean():.3f} 毫秒")
                print(f"   - 最小 SearchMemory: {durations.min():.3f} 毫秒")
                print(f"   - 最大 SearchMemory: {durations.max():.3f} 毫秒")
            if (enriched_df['SearchKnowledge'] != '').sum() > 0:
                durations = enriched_df[enriched_df['SearchKnowledge'] != '']['SearchKnowledge'].astype(float)
                print(f"   - 平均 SearchKnowledge: {durations.mean():.3f} 毫秒")
                print(f"   - 最小 SearchKnowledge: {durations.min():.3f} 毫秒")
                print(f"   - 最大 SearchKnowledge: {durations.max():.3f} 毫秒")
            if (enriched_df['GenerateDuration'] != '').sum() > 0:
                gen_durations = enriched_df[enriched_df['GenerateDuration'] != '']['GenerateDuration'].astype(float)
                print(f"   - 平均 GenerateDuration: {gen_durations.mean():.3f} 毫秒")
                print(f"   - 最小 GenerateDuration: {gen_durations.min():.3f} 毫秒")
                print(f"   - 最大 GenerateDuration: {gen_durations.max():.3f} 毫秒")
            
            # Model Service Timings 统计
            if enriched_df['prompt_ms'].notna().sum() > 0:
                print(f"\n   📊 Model Service Timings 统计:")
                print(f"   - 平均 Prompt 处理时间: {enriched_df['prompt_ms'].mean():.3f} 毫秒")
                print(f"   - 平均 Predicted 生成时间: {enriched_df['predicted_ms'].mean():.3f} 毫秒")
                print(f"   - 平均 Prompt Tokens: {enriched_df['prompt_n'].mean():.1f}")
                print(f"   - 平均 Predicted Tokens: {enriched_df['predicted_n'].mean():.1f}")
                print(f"   - 平均总 Tokens: {enriched_df['model_service_total_tokens'].mean():.1f}")
        except Exception as e:
            print(f"\n⚠️ 统计结果时出错: {e}")
    else:
        print("\n⚠️ 处理失败")
    return enriched_df

def fix_time(timestamp_ms):
    timestamp_s = int(timestamp_ms) / 1000  # 转成秒\
    dt = datetime.fromtimestamp(timestamp_s)
    return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def sort_key(path):
    name = path.name

    # 匹配 .n.log 格式（n为数字）
    match = re.match(r'(.+)\.(\d+)\.log$', name)
    if match:
        return (0, int(match.group(2)), name)  # (优先级, 数字序号, 文件名)

    # core.log 最后
    if name == 'core.log':
        return (1, 0, name)

    # 其他未知格式
    return (2, 0, name)

def enrich_regist_dataframe_with_logs(input_df, log_folder_path):
    # all_entries = parse_all_logs_in_folder(log_folder_path)

    # if not all_entries:
    #     print("⚠️ 日志文件中没有找到有效的 [Span Trace] 日志条目")
    #     return input_df

    input_df['parse_gap_time'] = ''
    input_df['me5s_gap_time'] = ''
    # input_df['metrics_gap_time'] = ''
    input_df['insert_gap_time'] = ''
    input_df['Finished_parsing_document_time'] = ''
    input_df['total_gap_time'] = ''

    parse_list = []
    parse_response_list = []
    execute_list = []
    Finished_list = []
    model_list = []
    MetricsPlugin_list = []
    insert_list = []
    #datetime_now = date.today().strftime('%Y-%m-%d')
    out_path = Path(log_folder_path)
    log_files = list(out_path.rglob('*.log'))
    log_files.sort(key=sort_key)
    # 按顺序读取
    whole_log = ""
    for log_file in log_files:
        whole_log += log_file.read_text(encoding='utf-8', errors='ignore')
    # whole_log = ''
    # for log_file in out_path.rglob('*.log'):
    #     with log_file.open('r', encoding='utf-8', errors='ignore') as f:
    #         whole_log += log_file.read_text(encoding='utf-8', errors='ignore')
    completed_series = input_df.loc[input_df['status'] == 'COMPLETED', 'createTime']
    time_value_list = completed_series.astype(str).tolist()
    try:
        dt=fix_time(time_value_list[0])
    except:
        dt =time_value_list[0]
    dt=dt.replace("T"," ")
    datetime_now=str(dt).split(" ")[0]
    print(datetime_now)
    time_st=dt.replace(" ","T")
    try:
        time_value2 = fix_time(time_value_list[-1])
    except:
        time_value2 = time_value_list[-1]
    time_value2=time_value2.replace("T"," ")
    time_format = '%Y-%m-%d %H:%M:%S.%f'  # 根据实际格式调整
    dt2 = datetime.strptime(time_value2, time_format)
    dt2 += timedelta(minutes=1)  # 加 1 分钟
    time_end = dt2.strftime('%H:%M')
    st_esc = re.escape(time_st)
    end_esc = re.escape(time_end)
    print(time_st)
    print(time_end)
    print(datetime_now)
    # pattern = rf'{st_esc}(.*){datetime_now}\s+{end_esc}'
    # wanted = re.search(pattern, str(whole_log),flags=re.S).group(1)
    print("==DATE===")
    print(datetime_now)
    #segments = wanted.split("- Start to processing document with id")
    parts = whole_log.rsplit('Finished parsing', 1)
    parts=str(parts[0]+'Finished parsing')
    pattern = r'(?=2026-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}.*Start to processing document with)'
    segments = re.split(pattern, parts)
    segments = segments[1:]
    print(len(segments))
    wanted = ''.join(segments)
    parse_pat = re.compile(rf'{datetime_now}(.*?)- Start to processing document with')
    parse = parse_pat.findall(wanted)
    parse_list = debug_time(parse, parse_list)
    print("=====parse_Document======")
    print(parse_list[0])

    res_pat = re.compile(rf'{datetime_now}(.*?)File parse response:')
    response = res_pat.findall(wanted)
    parse_response_list = debug_time(response, parse_response_list)
    print("=====parse response======")
    print(parse_response_list[0])
    print(len(parse_response_list))
    Finished_pat = re.compile(rf'{datetime_now}(.*?)Finished parsing')
    Finished = Finished_pat.findall(wanted)
    Finished_list = debug_time(Finished, Finished_list)
    print("=====Finished======")
    print(Finished_list[0])
    print(len(Finished_list))
    for line in segments:
        m_list=[]
        i_list=[]
        # print(line)
        execute_pat = re.compile(rf'{datetime_now}(.*?)begin use model ME5S')
        execute = execute_pat.findall(line)
        # print(execute)
        execute_list2 = info_time(execute, [])
        print("====beginME5S====")
        try:
            print(execute_list2[0])
            execute_list.append(execute_list2[0])
        except:
            print(line)
            break

        # model_pat = re.compile(rf'{datetime_now}(.*?)- Save pdf document')
        model_pat = re.compile(rf'{datetime_now}(.*?)- end use model ME5S')
        model = model_pat.findall(line)
        model_list2 = info_time(model, [])
        print("====endME5S====")
        print(model_list2[-1])

        model_list.append(model_list2[-1])

        print(datetime_now)
        insert_pat = re.compile(rf"{datetime_now}(.*?) - insert document list into")
        insert = insert_pat.findall(str(line))
        insert_list2 = debug_time(insert, [])
        try:
            i_list.append(model_list2[-1])
        except:
            print(line)
        i_list.append(insert_list2[-1])
        print("====INSERT====")
        print(i_list)
        insert_list.append(i_list)
    num_id=0
    for idx in range(len(input_df)):
        if input_df.loc[idx, 'status'] == 'COMPLETED':
            print("=====JIESHU=====")
            print(idx)
            print(parse_list[idx])
            print(parse_response_list[idx][0])
            pare_gap=time_gap(parse_list[idx][0],parse_response_list[idx][0])
            input_df.loc[idx, 'parse_gap_time'] = pare_gap
            me5s_gap=time_gap(execute_list[idx][0],model_list[idx][0])
            input_df.loc[idx, 'me5s_gap_time'] = me5s_gap
            # metrics_gap=time_gap(MetricsPlugin_list[idx][0][0],MetricsPlugin_list[idx][1][0])
            # input_df.loc[idx, 'metrics_gap_time'] = metrics_gap
            insert_gap=time_gap(insert_list[idx][0][0],insert_list[idx][1][0])
            input_df.loc[idx, 'insert_gap_time'] = insert_gap
            input_df.loc[idx, 'Finished_parsing_document_time'] = str(Finished_list[idx][0])
            total_gap=time_gap(parse_list[idx][0],Finished_list[idx][0])
            input_df.loc[idx, 'total_gap_time'] = total_gap
            num_id+=1

    return input_df

def get_regist_duration(EXCEL_FILE, OUTPUT_FILE, LOG_FOLDER):

    print("=" * 60)
    print("🚀 Quantum Core 日志注册分析工具")
    print("=" * 60)

    # 1. 读取输入Excel
    try:
        input_df = pd.read_excel(EXCEL_FILE)

        # 检查必需的列
        if 'createTime' not in input_df.columns:
            print("❌ 错误: Excel文件中没有 'start_time' 列")
            exit(1)

        if 'editTime' not in input_df.columns:
            print("❌ 错误: Excel文件中没有 'end_time' 列")
            exit(1)

        print(f"\n📊 读取到 {len(input_df)} 行数据")
        print(f"📋 原始列: {list(input_df.columns)}")

    except FileNotFoundError:
        print(f"❌ 错误: 找不到文件 '{EXCEL_FILE}'")
        exit(1)
    except Exception as e:
        print(f"❌ 读取Excel文件时出错: {e}")
        exit(1)
    try:
        enriched_regist_df = enrich_regist_dataframe_with_logs(input_df, LOG_FOLDER)
    except Exception as e:
        print(f"❌ 处理注册日志时出错: {e}")
        enriched_regist_df = None
    if enriched_regist_df is not None:
        enriched_regist_df.to_excel(OUTPUT_FILE, index=False)

        print("\n" + "=" * 60)
        print(f"✅ 成功处理 {len(enriched_regist_df)} 行记录")
        print(f"📁 结果已保存到: {OUTPUT_FILE}")
        print("=" * 60)
    return enriched_regist_df


def main(root_folder):

    root_folder = root_folder
    output_dir = os.path.join(root_folder, "Results")
    
    if not os.path.exists(root_folder):
        print(f"❌ 错误: 根文件夹不存在: {root_folder}")
        sys.exit(1)
    
    # 自动定位文件
    file_paths = auto_locate_files(root_folder)
    
    log_folder_path = file_paths['log_path']
    input_excel_path = file_paths['input_path']
    input_regist_excel_path = file_paths['regist_path']
    
    # 验证必需文件
    if not log_folder_path:
        print("❌ 错误: 无法找到日志文件夹")
        sys.exit(1)
    
    if not input_excel_path:
        print("❌ 错误: 无法找到输入Excel文件")
        sys.exit(1)
    # 注册文件不是必需的，只在执行KBQA模块时需要
    
    if not input_regist_excel_path:
        print("⚠️ 警告: KBQA模块需要注册文件，但未找到")
        print("   将跳过注册文件处理")
    
    os.makedirs(output_dir, exist_ok=True)
    OUTPUT_Result_EXCEL_PATH = os.path.join(output_dir, os.path.basename(input_excel_path))
    OUTPUT_register_EXCEL_PATH = os.path.join(output_dir, os.path.basename(input_regist_excel_path)) if input_regist_excel_path else None

    try:
        get_result_duration(input_excel_path, OUTPUT_Result_EXCEL_PATH, log_folder_path)
    except Exception as e:
        print(f"❌ 处理日志时出错: {e}")
    try:
        get_regist_duration(input_regist_excel_path, OUTPUT_register_EXCEL_PATH, log_folder_path)
    except Exception as e:
        print(f"❌ 处理注册日志时出错: {e}")

    # 如果有解压后的日志文件夹，直接删除
    
    PackAllLog = os.path.join(root_folder, "PackageAllLogs")
    if os.path.exists(PackAllLog) and os.path.isdir(PackAllLog):
        try:
            shutil.rmtree(PackAllLog)
            print(f"🧹 已删除临时日志文件夹: {PackAllLog}")
        except Exception as e:
            print(f"⚠️ 删除日志文件夹时出错: {e}")

# 主程序
if __name__ == '__main__':
    ROOT_FOLDER = r"D:\00work\AIPC\EdgeTool\BackEnd\UPLOAD\Quantum_E2E\Qira_E2E_TOOL\Local_TestDIR"
    main(ROOT_FOLDER)