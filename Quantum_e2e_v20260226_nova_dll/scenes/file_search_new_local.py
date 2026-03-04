# scenes/file_search.py
import time
from typing import Dict
import os
from openai import AzureOpenAI
from datetime import datetime
import pandas as pd
import json
import re
def type_id_check(result_text):
    f_list=[]
    resp = json.loads(result_text)

    # data= resp["data"]
    # content_dict = json.loads(data)
    content = resp["results"]
    total_text = resp["total_count"]
    # result_str=resp['results']
    for filename in content:
        f_list.append(filename['file_name'])

    return f_list,total_text


def main(row: Dict):
    scene = row.get('scene', '').strip().lower()
    id_num = row.get('label_judge', '')
    id_num=str(id_num)
    result_text = str(row.get('result', '')).strip()
    result_text = str(result_text).replace("_x000D_", "")
    GT = str(row.get('gt', '')).strip()
    GT = str(GT).replace(", ", ",")
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

    if 'local_agent_file_seach_raw_data' in result_text:
        message = 'Local file search success.'
    else:
        message = 'error'
    print(message)
    if str(result_text) == 'CTTVError: Empty response from server':
        print({"Result": 0, "Reason": ""})
        return {"Result": 0, "Reason": "CTTVError"}
    elif str(message) == 'Local file search success.':
        try:
            r_list, total_count = type_id_check(result_text)
        except:
            result_text = str(result_text).replace("'", "").replace('"', '').strip(" ").replace("\\\\", "\\")
            result_text = re.sub(r'\\u([0-9a-fA-F]{4})',
                                 lambda m: chr(int(m.group(1), 16)), result_text)
            pat = re.compile(r'file_name:\s*(.*?),\s*file_path', re.DOTALL)
            r_list = pat.findall(result_text)
            total_count = len(r_list)
        print(r_list)
        print(total_count)
        print(type(r_list))
        if total_count == 0 and str(GT) == 'nan':
            print({"Result": 1, "Reason": ""})
            return {"Result": 1, "Reason": ""}
        elif total_count == 0 and str(GT) != 'nan':
            print({"Result": 0, "Reason": "正样本返回为空"})
            return {"Result": 0, "Reason": "正样本返回为空"}
        elif total_count != 0 and str(GT) == 'nan':
            print({"Result": 0, "Reason": "负样本错误回答"})
            return {"Result": 0, "Reason": "负样本错误回答"}
        else:
            suffixes = id_map.get(id_num, [])  # 找不到返回 None
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
    else:
        print({"Result": 0, "Reason": "意图错误"})
        return {"Result": 0, "Reason": "意图错误"}
