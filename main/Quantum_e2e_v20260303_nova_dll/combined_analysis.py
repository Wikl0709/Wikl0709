import pandas as pd
import os
import re
import json
import glob
from datetime import datetime, timedelta
import argparse
from loguru import logger  # 导入主程序使用的loguru logger
from pathlib import Path


def extract_by_find(s, start, mid, end):
    """
    在字符串 s 中查找模式：start + 任意字符(最短) + mid + 至少一个空白 + end
    返回中间部分（不含start和mid）或 None
    """
    pos_start = s.find(start)
    if pos_start == -1:
        return None

    # 从 start 之后找第一个 mid
    search_start = pos_start + len(start)
    pos_mid = s.find(mid, search_start)
    if pos_mid == -1:
        return None

    # 检查 mid 之后是否有至少一个空白，然后紧接 end
    after_mid = pos_mid + len(mid)
    # 跳过连续空白，并记录跳过的个数
    whitespace_count = 0
    i = after_mid
    while i < len(s) and s[i].isspace():
        i += 1
        whitespace_count += 1
    # 必须至少有一个空白，且后面紧跟 end
    if whitespace_count >= 1 and s.startswith(end, i):
        # 返回中间部分
        return s[search_start:pos_mid]
    return None
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
def debug_time(element,list):
    debug_time_pat = re.compile(r' (.*) \[DEBUG\]')
    for ele in element:
        time = debug_time_pat.findall(ele)
        # print(time)
        list.append(time)
        if time==[]:
            print("=============error========"+str(element))
    return list

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


def parse_log_files(log_dir):
    """
    Parses all log files in the directory and returns a sorted list of events.
    Event format: {'timestamp': datetime, 'ts_str': str, 'type': 'START'|'END', 'memories': dict|None, 'line': str}
    START: FkbToolExecutor: search_knowledge
    END: {"success": true, "memories":
    """
    events = []
    
    # Timestamp pattern: 2026-01-15 15:11:36.197
    ts_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})')
    
    # Search patterns
    start_pattern = "FkbToolExecutor: search_knowledge"
    # This pattern covers both requirements (it identifies the line for latency end time, and contains the JSON for memories extraction)
    end_pattern = '{"success": true, "memories":'
    
    # 只处理以 qtcore 开头的日志文件
    log_files = glob.glob(os.path.join(log_dir, "qtcore*.log"))
    logger.info(f"Found {len(log_files)} qtcore* log files.")
    
    for log_file in log_files:
        logger.info(f"Processing {log_file}...")
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    event_type = None
                    memories_content = None
                    kbqa_content=None
                    
                    if start_pattern in line:
                        event_type = 'START'
                    elif end_pattern in line:
                        event_type = 'END'
                        # Try to extract memories JSON
                        start_idx = line.find('{')
                        if start_idx != -1:
                            json_str = line[start_idx:].strip()
                            try:
                                data = json.loads(json_str)
                                if "memories" in data:
                                    memories_content = data["memories"]
                                if "chunksDocuments" in data:
                                    kbqa_content = data["chunksDocuments"]
                            except json.JSONDecodeError:
                                pass
                    
                    if event_type:
                        match = ts_pattern.match(line)
                        if match:
                            ts_str = match.group(1)
                            try:
                                timestamp = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
                                events.append({
                                    'timestamp': timestamp,
                                    'ts_str': ts_str,
                                    'type': event_type,
                                    'KB': kbqa_content,
                                    'memories': memories_content,
                                    'line': line.strip()
                                })
                            except ValueError:
                                continue
        except Exception as e:
            logger.error(f"Error reading {log_file}: {e}")
            
    # Sort by timestamp
    events.sort(key=lambda x: x['timestamp'])
    logger.info(f"Total extracted events: {len(events)}")
    return events

def process_excel(excel_path, log_dir, output_path, scene_filter=None):
    logger.info(f"Reading Excel: {excel_path}")
    
    # 读取所有工作表
    try:
        all_sheets = pd.read_excel(excel_path, sheet_name=None)  # 读取所有工作表
    except Exception as e:
        logger.error(f"Error reading Excel file: {e}")
        return

    # 获取工作表名称
    sheet_names = list(all_sheets.keys())
    logger.info(f"Found sheets: {sheet_names}")
    
    # 创建一个字典存储处理后的工作表
    processed_sheets = {}
    
    # 处理 result 工作表
    if 'result' in all_sheets:
        df = all_sheets['result'].copy()
        
        # Check scene column for filtering
        has_scene_col = 'scene' in df.columns
        if scene_filter and not has_scene_col:
            logger.warning("Warning: 'scene' column not found in Excel. Skipping filter.")
            scene_filter = None
                
        if df.empty:
            logger.info("No data to process in 'result' sheet.")
            processed_sheets['result'] = df
        else:
            # 记录原始时间列的格式（假设第一行为代表）
            original_start_format = df['start_time'].iloc[0] if not df.empty else None
            original_end_format = df['end_time'].iloc[0] if not df.empty else None

            # 第一次转换为 datetime 以便后续处理
            df['start_time'] = pd.to_datetime(df['start_time'], errors='coerce')
            df['end_time'] = pd.to_datetime(df['end_time'], errors='coerce')


            # Parse logs
            log_data = parse_log_files(log_dir)

            results = []
            file_result = []
            tool_result = []

            start_times_list_kbqa = []
            end_times_list_kbqa = []
            latencies_list_kbqa = []
            print("Matching logs to Excel rows...")

            # Ensure time columns are datetime（第二次转换）

            # Parse logs once
            events = parse_log_files(log_dir)
            
            # Lists to store results
            memories_list = []
            start_times_list = []
            end_times_list = []
            latencies_list = []
            
            logger.info("Matching events to Excel rows...")

            matched = (df['scene'] == 'File search').idxmax()
            condition = df['scene'] == 'File search'
            time_value_list = df.loc[condition, 'start_time'].astype(str).tolist()
            fs_start=time_value_list[0]
            fs_end=time_value_list[-1]
            time_format = '%Y-%m-%d %H:%M:%S.%f'  # 根据实际格式调整
            dt1 = str(fs_start).split(".")[0]
            dt2 = datetime.strptime(str(fs_end), time_format)
            dt2 += timedelta(minutes=1)  # 加 1 分钟
            fs_end = dt2.strftime('%H:%M')
            log_path = Path(log_dir)
            log_files = list(log_path.rglob('*.log'))
            # 按顺序读取
            whole_log = ""
            for log_file in log_files:
                whole_log += log_file.read_text(encoding='utf-8', errors='ignore')
            print(len(whole_log))
            print("START===")
            print(fs_start)
            fs_events = whole_log.split(dt1)[-1]
            fs_events = str(fs_events)
            # print(fs_events[500:])
            print(len(fs_events))
            pass_num=0
            for index, row in df.iterrows():
                # Apply scene filter if needed
                if scene_filter and row['scene'] != scene_filter:
                    memories_list.append(None)
                    start_times_list.append(None)
                    end_times_list.append(None)
                    latencies_list.append(None)
                    continue

                start = row['start_time']
                end = row['end_time']

                ###kbqa###
                scene=row['scene']
                start = row['start_time']
                end = row['end_time']
                tool_list = row['toolname']

                #Memory Kbqa File search
                if scene=='Memory' or scene=='Kbqa':
                    if "Searching Knowledge" in tool_list:
                        tool_result.append(1)
                    else:
                        tool_result.append(0)
                else:
                    if "Accessing files" in tool_list:
                        tool_result.append(1)
                    else:
                        tool_result.append(0)
                ###kbqa###
                
                # Find events within [start, end]
                case_events = [e for e in events if start <= e['timestamp'] <= end]
                # --- 1. Extract Memories ---
                # Get all memories content found in this time window
                ###file_search###
                if scene == 'File search':
                    complete_list=[]
                    Received_list=[]
                    datetime_now = str(fs_start).split(" ")[0]
                    # print(fs_start)
                    # print(fs_end)
                    # pattern = rf'{fs_start}(.*?){datetime_now}\s+{fs_end}'
                    parse_pat = re.compile(rf'{datetime_now}(.*?)Complete CallToolRequest: ')
                    parse = parse_pat.findall(fs_events)
                    complete_list = debug_time(parse, complete_list)

                    parse_pat2 = re.compile(rf'{datetime_now}(.*?)- Received JSON message:')
                    parse2 = parse_pat2.findall(fs_events)
                    Received_list = debug_time(parse2, Received_list)

                    parse_pat3 = re.compile(
                        r'{"name":"LocalAgent_filesystem_search_local_file_on_pc","arguments":"(\{.*?\})"(?=,|\})',
                        re.DOTALL
                    )
                    f_type_list = parse_pat3.findall(fs_events)
                    # print(len(complete_list))
                    # print(len(Received_list))
                    # print(len(f_type_list))
                    tool_name = row['toolname']
                    if "Accessing files" in str(tool_name):
                        print(matched)
                        f_index = index - (matched+pass_num)
                        print("INDEX===" + str(f_index))
                        print(complete_list[f_index][0])
                        print(Received_list[f_index][0])
                        print("#######")
                        print(f_type_list[f_index])
                        print("#######")
                        fs_gap_time = time_gap(complete_list[f_index][0], Received_list[f_index][0])
                        # df.loc[index,'Retrieval_latency_ms']=fs_gap_time*1000
                        latencies_list.append(fs_gap_time*1000)
                        df.loc[index,'fs_slot']=f_type_list[f_index]
                    else:
                        pass_num+=1
                        print("JUMP_INDEX===")
                        # df.loc[index,'Retrieval_latency_ms']=""
                        latencies_list.append(None)
                        df.loc[index,'fs_slot']=""

                ####kbqa###
                found_KB = []
                for e in case_events:
                    if e['type'] == 'END' and e['KB'] is not None:
                        found_KB.append(json.dumps(e['KB'], ensure_ascii=False))

                chunk_list = [] if found_KB else None
                file_list = [] if found_KB else None
                for i in range(len(found_KB)):
                    single_chunks = json.loads(found_KB[i])
                    for j in range(len(single_chunks)):
                        chunks = single_chunks[j]['content']
                        chunk_list.append(chunks)
                        try:
                            files = os.path.basename(single_chunks[j]['path'])
                        except:
                            files=''
                        file_list.append(files)
                # print(len(chunk_list))
                results.append(chunk_list)
                file_result.append(file_list)

                # --- 2. CalculKBate Latency ---
                # Strategy: Find the first START event, and the first END event that occurs AFTER that START event.
                found_start = None
                found_end = None

                for i, event in enumerate(case_events):
                    if event['type'] == 'START':
                        found_start = event
                        # Look for the next END event
                        for next_event in case_events[i + 1:]:
                            if next_event['type'] == 'END':
                                found_end = next_event
                                break
                        if found_end:
                            break

                if found_start and found_end:
                    s_time = found_start['timestamp']
                    e_time = found_end['timestamp']
                    latency = (e_time - s_time).total_seconds() * 1000  # ms

                    start_times_list_kbqa.append(found_start['ts_str'])
                    end_times_list_kbqa.append(found_end['ts_str'])
                    latencies_list_kbqa.append(latency)
                else:
                    start_times_list_kbqa.append(None)
                    end_times_list_kbqa.append(None)
                    latencies_list_kbqa.append(None)
                ###kbqa###


                found_memories = []
                for e in case_events:
                    if e['type'] == 'END' and e['memories'] is not None:
                        found_memories.append(json.dumps(e['memories'], ensure_ascii=False))
                
                memories_str = "\n".join(found_memories) if found_memories else None
                memories_list.append(memories_str)
                
                # --- 2. Calculate Latency ---
                # Strategy: Find the first START event, and the first END event that occurs AFTER that START event.
                found_start = None
                found_end = None
                
                for i, event in enumerate(case_events):
                    if event['type'] == 'START':
                        found_start = event
                        # Look for the next END event
                        for next_event in case_events[i+1:]:
                            if next_event['type'] == 'END':
                                found_end = next_event
                                break
                        if found_end:
                            break
                
                if found_start and found_end:
                    s_time = found_start['timestamp']
                    e_time = found_end['timestamp']
                    latency = (e_time - s_time).total_seconds() * 1000  # ms
                    
                    start_times_list.append(found_start['ts_str'])
                    end_times_list.append(found_end['ts_str'])
                    if scene != 'File search':
                        latencies_list.append(latency)
                else:
                    start_times_list.append(None)
                    end_times_list.append(None)
                    if scene != 'File search':
                        latencies_list.append(None)
                    
        # Add new columns to DataFrame
        df['MemoryRetrievalTop10'] = memories_list
        df['Retrieval_Start_FkbToolExecutor: search_knowledge'] = start_times_list
        df['Retrieval_End_{"success": true, "memories"'] = end_times_list
        df['Retrieval_latency_ms'] = latencies_list
        ###kbqa###
        # df['Retrieval_Start_FkbToolExecutor: kbqa'] = start_times_list_kbqa
        # df['Retrieval_End_{"success": true, "kbqa"'] = end_times_list_kbqa
        # df['Retrieval_latency_KB'] = latencies_list_kbqa
        df['search_text_list'] = results
        df['search_file_list'] = file_result
        df['Tool_Check'] = tool_result
        ###kbqa###
        df['search_file_list'] = file_result
        df['Tool_Check'] = tool_result

        # 处理完成后恢复原始时间格式
        if original_start_format:
            df['start_time'] = df['start_time'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]  # 截断微秒部分
        if original_end_format:
            df['end_time'] = df['end_time'].dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]

        processed_sheets['result'] = df
    else:
        logger.warning("Warning: 'result' sheet not found in Excel file.")

    # 复制所有其他工作表（除了result）
    for sheet_name in sheet_names:
        if sheet_name != 'result':  # 只有不是result表才复制
            processed_sheets[sheet_name] = all_sheets[sheet_name]
            logger.info(f"Copied '{sheet_name}' sheet without changes.")
    
    # 保存到新的Excel文件
    logger.info(f"Saving to {output_path}")
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, sheet_df in processed_sheets.items():
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
    logger.info("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process logs and Excel for Memory/Latency analysis.")
    parser.add_argument("--scene", type=str, help="Filter by scene (e.g., Memory, KBQA)", default=None)
    
    args = parser.parse_args()
    
    # Configuration
    # Using ori.xlsx as it's the one currently being used for this workflow in recent context
    excel_file = r"D:\workfile\txtfile\2026\0227\test_results_Memory_v9_KBQA_Filesearch_v20250202_20260209_112933_cycle1.xlsx"
    log_folder = r"D:\workfile\txtfile\2026\0227\PackageAllLogs\pod1_20_QiraApp"
    output_file = excel_file
    
    process_excel(excel_file, log_folder, output_file, args.scene)