# FileProcessor class for handling file operations

import winreg
import base64
import sys
import os
import json
import pandas as pd
import datetime
import subprocess as sp
import statistics
import logging
sys.path.insert(0,os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8')


def get_doc_path():
    """
    从注册表中读取指定键值，并解码为 UTF-8 格式的文档路径。

    参数:
        无

    返回:
        str: 解码后的文档路径字符串。
    """
    doc_path = ''
    try:
        key_path = r'Software\JavaSoft\Prefs\ai.service'
        key_name = r'monitor.directory'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        doc_path_base64, reg_type = winreg.QueryValueEx(key, key_name)
        winreg.CloseKey(key)
        doc_path_base64 = doc_path_base64.replace('/', '')
        doc_path = base64.b64decode(doc_path_base64).decode('utf-8')
        return doc_path
    except:
        return doc_path
    
def load_query(path,log_path):
    """
    加载 Excel 文件中的 'questions' sheet，过滤出包含必要字段的数据并返回。

    参数:
        path: Excel 文件路径。
        log_path: 日志文件路径。

    返回:
        list: 包含问题数据的字典列表。
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(level = logging.INFO)
    handler = logging.FileHandler(log_path,encoding="utf-8")
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    query_list = []
    data = pd.read_excel(path, sheet_name='questions')
    length = len(data)
    for i in range(length):
        # for i in range(15):
        item = data.iloc[i]
        if 'type' in item and 'question' in item and 'pathList' in item:
            item_dict = item.to_dict()
            query_list.append(item_dict)
        else:
            logger.info('type,question and pathList column must in xlsx')
    return query_list

def parse_event_stream(data):
    """
    解析事件流数据，提取有效的 responseBody 内容并转换为字典列表。

    参数:
        data: 事件流数据列表。

    返回:
        list: 解析后的事件字典列表。
    """
    events = []
    for event_data in data:
        event = json.dumps(event_data)
        if 'status\\":\\"running\\' in event or 'responseBody' not in event:
            continue
        try:
            event = event.replace("false", "False")
            event = event.replace("true", "True")
            event_dict = json.loads(event)
            body = json.loads(event_dict["responseBody"])
            events.append(body)
        except Exception as e:
            event = event.replace("False", "false")
            event = event.replace("True", "true")
            event_dict = json.loads(event)
            try:
                body = json.loads(event_dict["responseBody"])
            except Exception as e:
                body = event_dict["responseBody"]
            events.append(body)
    return events

def get_vector_info(log_path):
    """
    从日志文件中提取向量化阶段的时间戳信息。

    参数:
        log_path: 日志文件路径。

    返回:
        list: 向量化时间戳列表。
    """
    vector_list = []
    key_word = 'begin map phase'
    log_list = os.listdir(log_path)
    for log in log_list:
        if '.log' in log:
            log_file = os.path.join(log_path, log)
            txt_log = open(log_file, encoding='utf-8')
            lines = txt_log.readlines()
            txt_log.close()
            lt = len(lines)
            for i in range(lt):
                line = lines[i]
                if key_word in line:
                    vector_year = line.split()[0]
                    vector_s = line.split()[1]
                    vector_time = vector_year + ' ' + vector_s
                    vector_datetime = datetime.datetime.strptime(vector_time, '%Y-%m-%d %H:%M:%S.%f')
                    vector_list.append(vector_datetime)
    return vector_list

def get_map_reduce_info(log_path,logging_file_path):
    """
    从日志文件中提取 MapReduce 阶段的输入内容，并构建时间戳映射字典。

    参数:
        log_path: 日志文件路径。
        logging_file_path: 日志记录文件路径。

    返回:
        dict: 时间戳到 MapReduce 输入内容的映射字典。
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(level = logging.INFO)
    handler = logging.FileHandler(logging_file_path,encoding='utf-8')
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    map_reduce_info = dict()
    key_word = ' - send request to llm with question:'
    log_list = os.listdir(log_path)
    for log in log_list:
        if '.log' in log:
            logger.info(log)
            log_file = os.path.join(log_path, log)
            txt_log = open(log_file, encoding='utf-8')
            lines = txt_log.readlines()
            txt_log.close()
            lt = len(lines)
            for i in range(lt):
                line = lines[i]
                if key_word in line:
                    map_reduce_year = line.split()[0]
                    map_reduce_s = line.split()[1]
                    map_reduce_time = map_reduce_year + ' ' + map_reduce_s
                    map_reduce_datetime = datetime.datetime.strptime(map_reduce_time, '%Y-%m-%d %H:%M:%S.%f')
                    system_input = ''
                    system_input = system_input + line.split(key_word)[1]
                    for j in range(i + 1, lt):
                        line_next = lines[j]
                        if '.\n' != line_next:
                            system_input = system_input + line_next
                        else:
                            break
                    if map_reduce_datetime not in map_reduce_info:
                        map_reduce_info[map_reduce_datetime] = system_input
    return map_reduce_info

def get_llm_info(log_path,logging_file_path):
    """
    从日志文件中提取 LLM 请求内容，并构建时间戳映射字典。

    参数:
        log_path: 日志文件路径。
        logging_file_path: 日志记录文件路径。

    返回:
        dict: 时间戳到 LLM 请求内容的映射字典。
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(level = logging.INFO)
    handler = logging.FileHandler(logging_file_path,encoding="utf-8")
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    llm_info_dict = dict()
    key_word_1 = '[getStreamAnswer]'
    key_word_2 = '- Send request:'
    log_list = os.listdir(log_path)
    for log in log_list:
        if '.log' in log:
            logger.info(log)
            log_file = os.path.join(log_path, log)
            txt_log = open(log_file, encoding='utf-8')
            lines = txt_log.readlines()
            txt_log.close()
            lt = len(lines)
            for i in range(lt):
                line = lines[i]
                if key_word_1 in line and key_word_2 in line:
                    llm_year = line.split()[0]
                    llm_s = line.split()[1]
                    llm_time = llm_year + ' ' + llm_s
                    llm_datetime = datetime.datetime.strptime(llm_time, '%Y-%m-%d %H:%M:%S.%f')
                    prompt_str = line.split(key_word_2)[1].strip()
                    prompt_str = prompt_str.replace('false', 'False').replace('true', 'True')
                    prompt_dict = eval(prompt_str)
                    system_input = prompt_dict['prompt']
                    if llm_datetime not in llm_info_dict:
                        llm_info_dict[llm_datetime] = system_input
    return llm_info_dict

def get_llm_time(start_time, end_time, llm_info_dict):
    """
    获取在指定时间段内的 LLM 请求时间与内容。

    参数:
        start_time: 开始时间戳。
        end_time: 结束时间戳。
        llm_info_dict: LLM 请求信息字典。

    返回:
        tuple: (匹配的 LLM 时间戳, LLM 请求内容)
    """
    llm_time = 0
    llm_prompt = ''
    key_list = sorted(llm_info_dict.keys())
    for datetime in key_list:
        if datetime > start_time and datetime < end_time:
            llm_time = datetime
            llm_prompt = llm_info_dict[llm_time]
            return llm_time, llm_prompt
    return llm_time, llm_prompt

def get_map_reduce_prompt_list(start_time, end_time, map_reduce_info_dict):
    """
    获取在指定时间段内的 MapReduce 提示词列表。

    参数:
        start_time: 开始时间戳。
        end_time: 结束时间戳。
        map_reduce_info_dict: MapReduce 输入信息字典。

    返回:
        list: 匹配时间段的提示词列表。
    """
    map_reduce_prompt_list = []
    datetime_list = sorted(map_reduce_info_dict.keys())
    for datetime in datetime_list:
        if datetime > start_time and datetime < end_time:
            map_reduce_prompt = map_reduce_info_dict[datetime]
            map_reduce_prompt_list.append(map_reduce_prompt)
    return map_reduce_prompt_list

def get_vector_time(start_time, end_time, vector_time_list):
    """
    获取在指定时间段内的向量化处理时间戳。

    参数:
        start_time: 开始时间戳。
        end_time: 结束时间戳。
        vector_time_list: 向量化时间戳列表。

    返回:
        datetime: 匹配的时间戳。
    """
    vector_time = 0
    for datetime in vector_time_list:
        if datetime > start_time and datetime < end_time:
            vector_time = datetime
            return vector_time
    return vector_time

def write_result_by_case(query_info, result, output_path):
    """
    将查询结果写入 CSV 文件。

    参数:
        query_info: 查询信息字典。
        result: 结果字典。
        output_path: 输出文件路径。

    返回:
        无
    """
    query_info.update(result)
    result_df = pd.DataFrame.from_dict(query_info, orient='index').T
    if not os.path.exists(output_path):
        result_df.to_csv(output_path, index=False, mode='a+', header=True, encoding="utf_8_sig",errors='surrogatepass')
    else:
        result_df.to_csv(output_path, index=False, mode='a+', header=False, encoding="utf_8_sig",
                        errors='surrogatepass')

def run_command(command):
    """
    执行 PowerShell 命令并返回数值结果。

    参数:
        command: PowerShell 命令字符串。

    返回:
        float: 命令执行结果。
    """
    val = sp.run(['powershell', '-Command', command], capture_output=True).stdout.decode("ascii")
    if val:
        array = val.strip().split('\r\n')
        result = 0
        for item in array:
            result = result + float(item.strip().replace(',', '.'))
        return result
    else:
        return 0
    
def get_files_in_directory(directory):
    """
    遍历目录，生成所有文件的完整路径。

    参数:
        directory: 目录路径。

    返回:
        generator: 文件路径生成器。
    """
    # 获取目录下的所有文件和目录名
    for root, dirs, files in os.walk(directory):
        for file in files:
            # 拼接完整的文件路径
            yield os.path.join(root, file)

def get_file_list(directory):
    """
    获取目录下所有文件的完整路径列表。

    参数:
        directory: 目录路径。

    返回:
        list: 文件路径列表。
    """
    file_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            file_list.append(file_path)
    return file_list

def save_data(file, name, data_list):
    """
    将数据列表保存到 Excel 文件的指定 sheet 中。

    参数:
        file: Excel 文件路径。
        name: sheet 名称。
        data_list: 数据列表。

    返回:
        无
    """
    variable_list = []
    for data in data_list:
        for key in data:
            if key not in variable_list:
                variable_list.append(key)
    data_df = pd.DataFrame(data_list, columns=variable_list)
    with pd.ExcelWriter(file, engine='openpyxl', mode='a') as writer:
        data_df.to_excel(writer, sheet_name=name, index=False)

def parse_data(data, key):
    """
    过滤 DataFrame 中指定字段值大于 0.1 的数据项。

    参数:
        data: 输入 DataFrame。
        key: 过滤字段名。

    返回:
        list: 过滤后的数据字典列表。
    """
    data_list = []
    length = len(data)
    for i in range(length):
        item = data.iloc[i]
        item_dict = item.to_dict()
        time = item_dict[key]
        if time > 0.1:
            data_list.append(item_dict)
    return data_list

def group_by_key(data_list, keys):
    """
    按照指定字段对数据进行分组，并计算平均值。

    参数:
        data_list: 数据字典列表。
        keys: 分组依据字段列表。

    返回:
        list: 分组后的统计结果字典列表。
    """
    results = []
    item = {}
    count = 0
    group_key = keys[0]
    current_value = ''
    data_list.sort(key=lambda item_1: float(item_1[group_key]))
    for i in range(len(data_list)):
        data = data_list[i]
        if data[group_key] == current_value:
            for key in keys:
                item[key] = float(item[key]) + float(data[key])
            count = count + 1
        else:
            result = {}
            for key in keys:
                if count > 0:
                    result[key] = round(float(item[key]) / count, 2)
                item[key] = data[key]
                current_value = item[group_key]
            if count > 0:
                results.append(result)
            count = 1

    if count > 0:
        result = {}
        for key in keys:
            result[key] = round(float(item[key]) / count, 2)
            item[key] = data[key]

        results.append(result)

    return results

def cal_avg_time(data):
    """
    计算各类时间指标的平均值及 TP50/TP90/TP95 百分位数。

    参数:
        data: 输入 DataFrame。

    返回:
        list: 时间类型与统计结果的字典列表。
    """
    time_dict = dict(e2e=[], intent=[], vector=[], map_reduce=[], device=[], model=[])
    lt = len(data)
    for i in range(lt):
        item = data.iloc[i]
        e2e_s = item['total_s']
        intent_s = round(item['intent_ms'] / 1000, 2)
        vector_s = round(item['vector_ms'] / 1000, 2)
        map_reduce_s = round(item['map_reduce_ms'] / 1000, 2)
        device_s = round(item['device_ms'] / 1000, 2)
        first_token_s = item['first_token_s']
        generation_s = item['generation_s']
        response_content = item['response_content']
        intent_category = item['intent_category']

        time_dict['e2e'].append(e2e_s)
        time_dict['intent'].append(intent_s)
        if vector_s > 0:
            time_dict['vector'].append(vector_s)

        if response_content != 'Unsupported type for current.' and first_token_s > 0:
            model_s = first_token_s + generation_s
            time_dict['model'].append(model_s)
        if map_reduce_s > 0:
            time_dict['map_reduce'].append(map_reduce_s)
        if pd.isna(intent_category):
            continue
        elif 'DEVICE' in intent_category:
            time_dict['device'].append(device_s)

    time_result_list = []
    key_list = ['e2e', 'intent', 'vector', 'map_reduce', 'device', 'model']
    for key in key_list:
        time_result_dict = dict()
        time_list = time_dict[key]
        time_list.sort()
        lt_time = len(time_list)
        if lt_time > 0:
            avg_time = round(statistics.mean(time_list), 2)
            time_result_dict['time_type'] = key
            time_result_dict['avg_time'] = avg_time
            # if lt_time>=100:#去掉该限制条件，95分位数值即可
            tp50_time = round(time_list[int(lt_time * 0.5)], 2)
            tp90_time = round(time_list[int(lt_time * 0.9)], 2)
            tp95_time = round(time_list[int(lt_time * 0.95)], 2)
            time_result_dict['TP50'] = tp50_time
            time_result_dict['TP90'] = tp90_time
            time_result_dict['TP95'] = tp95_time
        else:
            time_result_dict['time_type'] = key
        time_result_list.append(time_result_dict)

    return time_result_list

