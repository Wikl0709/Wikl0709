# scenes/file_search.py
import time
from typing import Dict
import os
from openai import AzureOpenAI
from datetime import datetime
import pandas as pd
import json
import re

def type_id_check_cloud(result_text):
    """云端模式的结果解析"""
    f_list = []
    resp = json.loads(result_text)
    
    data = resp["results"]
    total_text = resp["total_count"]
    for filename in data:
        f_list.append(filename['file_name'])
    return f_list, total_text


def type_id_check_local(result_text):
    """本地模式的结果解析"""
    f_list = []
    resp = json.loads(result_text)
    
    total_text = resp["total_count"]
    result_str = resp['results']
    for filename in result_str:
        f_list.append(filename['file_name'])
    
    return f_list, total_text


def main(row: Dict):
    scene = row.get('scene', '').strip().lower()
    id_num = row.get('label_judge', '')
    id_num = str(id_num)
    result_text = str(row.get('result', '')).strip()
    GT = str(row.get('gt', '')).strip()
    GT = str(GT).replace(", ", ",")
    test_mode = row.get('test_mode', 'local').strip().lower()  # 默认为 local
    
    if str(GT) != 'nan':
        GT = str(GT).split(",")
    
    id_map = {
        'type1': ['.ppt', '.pptx'],
        'type2': ['.ppt', '.pptx'],
        'type3': ['.xlsx'],
        'type4': ['.csv'],
        'type5': ['.xls'],
        'type6': ['.pdf'],
        'type7': ['.txt'],
        'type8': ['.md']
    }
    
    # 根据 test_mode 选择不同的成功标识和解析函数
    if test_mode == 'cloud':
        success_flag = '"note":"local_agent_file_seach_raw_data"'
        success_message = 'local_agent_file_seach_raw_data'
        type_id_check_func = type_id_check_cloud
        error_reason = "工具调用错误"
    else:  # local
        success_flag = '"note": "local_agent_file_seach_raw_data"'
        success_message = 'Local file search success.'
        type_id_check_func = type_id_check_local
        error_reason = "意图错误"
    
    # 检查是否包含成功标识
    if success_flag in result_text:
        message = success_message
    else:
        message = 'error'
    
    print(message)
    
    # CTTVError 检查
    if str(result_text) == 'CTTVError: Empty response from server':
        print({"Result": 0, "Reason": ""})
        return {"Result": 0, "Reason": "CTTVError"}
    
    # 成功情况的处理
    elif str(message) == success_message:
        try:
            r_list, total_count = type_id_check_func(result_text)
        except:
            # 异常情况下的正则解析
            result_text = str(result_text).replace("'", "").replace('"', '').strip(" ").replace("\\\\", "\\")
            result_text = re.sub(r'\\u([0-9a-fA-F]{4})',
                                 lambda m: chr(int(m.group(1), 16)), result_text)
            pat = re.compile(r'file_name:\s*(.*?),\s*file_path', re.DOTALL)
            r_list = pat.findall(result_text)
            total_count = len(r_list)
        
        print(r_list)
        print(total_count)
        print(type(r_list))
        
        # 结果为空且GT为空 - 正确
        if total_count == 0 and str(GT) == 'nan':
            print({"Result": 1, "Reason": ""})
            return {"Result": 1, "Reason": ""}
        # 结果为空但GT不为空 - 正样本返回为空
        elif total_count == 0 and str(GT) != 'nan':
            print({"Result": 0, "Reason": "正样本返回为空"})
            return {"Result": 0, "Reason": "正样本返回为空"}
        # 结果不为空但GT为空 - 负样本错误回答
        elif total_count != 0 and str(GT) == 'nan':
            print({"Result": 0, "Reason": "负样本错误回答"})
            return {"Result": 0, "Reason": "负样本错误回答"}
        # 结果不为空且GT不为空 - 需要进一步验证
        else:
            suffixes = id_map.get(id_num, [])  # 找不到返回空列表
            if suffixes != []:
                print(f'{id_num} 对应后缀 {suffixes}')
                if any(file.endswith(s) for file in r_list for s in suffixes):
                    print({"Result": 1, "Reason": ""})
                    return {"Result": 1, "Reason": ""}
                else:
                    print({"Result": 0, "Reason": "文件类型错误"})
                    return {"Result": 0, "Reason": "文件类型错误"}
            else:
                print('id 不在列表里')
                if any(str(x) == str(p) for p in r_list for x in GT):
                    print({"Result": 1, "Reason": ""})
                    return {"Result": 1, "Reason": ""}
                else:
                    print({"Result": 0, "Reason": "均不符合GT"})
                    return {"Result": 0, "Reason": "均不符合GT"}
    # 错误情况
    else:
        print({"Result": 0, "Reason": error_reason})
        return {"Result": 0, "Reason": error_reason}