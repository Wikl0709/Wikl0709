# scenes/file_search.py
import time
from typing import Dict
import os
from openai import AzureOpenAI
from datetime import datetime
import pandas as pd
import json
import re

endpoint = 'https://llm-east-us2-test.openai.azure.com/'
subscription_key = 'A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY'

def askGPT_agent(prompt):
    deployment = "o4-mini"
    print(deployment)

    client = AzureOpenAI(
        api_version="2024-12-01-preview",
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )

    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant.",
            },
            {
                "role": "user",
                "content": prompt,
            }
        ],
        max_completion_tokens=100000,
        model=deployment
    )
    # res1 = str(response).replace("```json", "").replace("```", "").strip()
    answer = response.choices[0].message.content
    return answer  # ast.literal_eval(res1)

def all_details_check(result_text):
    prompt_2 =f"""
    You are an expert in extracting file path from text. Your task is to carefully analyze the given text and extract ONLY the file path that are explicitly mentioned. 

    A file path typically has:
    1. File address containing a slash or Folder address and file name
    2. A name part (alphanumeric characters, underscores, hyphens)
    3. An extension part (e.g., .jpg, .png, .docx)

    Examples:
    - "The file I found is C:\\Users\\Lenovo Yanglei AFR\\Desktop\\LRIA_llm_eval\\eval\\20250917\\files\\wangty19_work_2.jpg" → "C:\\Users\\Lenovo Yanglei AFR\\Desktop\\LRIA_llm_eval\\eval\\20250917\\files\\wangty19_work_2.jpg"
    - "The address of the file is image_search_results/sales_report.pdf" → "image_search_results/sales_report.pdf"
    - "The .docx file "PROJECT LEAD THE WAY" by Peggy Billittier was successfully located. It is named "pltw_18-19.docx" and is stored in the folder "D:\\zbw\\Local_solution\\FILE-SEARCH-100-1225"." → "D:\\zbw\\Local_solution\\FILE-SEARCH-100-1225\\pltw_18-19.docx"

    Rules:
    1. Extract only file paths explicitly mentioned in the text or file paths that can be concatenated with filenames.
    2. Return the file path in a JSON array format: ["D:\\text\\20251212\\filename1.ext", "image_search_results/filename2.ext"]
    3. If no file paths can be found, return an empty array: []
    4. Do NOT include any other information, only the file path
    5. Do NOT make up file path that are not explicitly mentioned
    6. Do NOT include any explanations or additional text

    Now, analyze the following text and extract the file path:
    {result_text}
    """
    if_details_in_chunk = askGPT_agent(prompt_2)
    return str(if_details_in_chunk)

def refuse_check(result_text):
    prompt_1 = f"""
            "Task: evaluate the relationship between the provided contents.\nProcess: Use the following step-by-step thinking sequence to respond. Please respond in English.\n\n"
            "Step 1: The user will send you the input using the format: <content>.\n"
            "Step 2: You need to judge if the <content> refuses to give the answer like the following examples:\n"
            "1) Apologize, I cannot give the answer of this question.\n"
            "2) This question includes information I should not provide.\n"
            "3) Sure, please give me your questions.\n"
            "4) no files were found,There are no files matching,There are no results\n"
            "5) I can't find any file\n"
            "6) The file search was successful, and no files were found in the specified location.\n"
            "If so, please give the response: <Result: Yes>, otherwise: <Result: No>.\n",

            "If the answers are inconsistent with each other (for example, stating 
            that the file was found earlier but then saying it couldn't be found later), return "failed".
            examples:"The file containing the code submission can be found in a local file search,
             specifically named "local_agent_file_seach_raw_data". There are no results or files returned 
             in this search."
            Note: Only return one of the three words "Yes", "No" and "failed", and do not return any other content.
    Now, analyze the following text:
    {result_text}
    """
    if_details_in_chunk = askGPT_agent(prompt_1)
    return str(if_details_in_chunk)

def main(row: Dict) -> Dict:
    scene = row.get('scene', '').strip().lower()
    result_text = str(row.get('result', '')).strip()
    GT = str(row.get('gt', '')).strip()
    if str(GT) != 'nan':
        GT = str(GT).split(",")
    # if scene == 'File search':
    result_list = []

    result2 = refuse_check(result_text)
    print(result2)
    if "Yes" in str(result2):
        if str(GT) == 'nan':
            return {"Result": 1, "Reason": "负样本正确拒答"}
        else:
            return {"Result": 0, "Reason": "正样本错误拒答"}
    elif "No" in str(result2):
        if str(GT) == 'nan':
            return {"Result": 0, "Reason": "负样本错误回答"}
        result = all_details_check(result_text)
        result = str(result).strip("[]")
        path_list=result.split(',')
        path_list2 = []
        for filepath in path_list:
            filepath = str(filepath).replace("'", "").replace('"', '').strip(" ").replace("\\\\", "\\")
            real_path = re.sub(r'\\u([0-9a-fA-F]{4})',
                               lambda m: chr(int(m.group(1), 16)), filepath)
            # real_path = json.loads(f'"{real_path}"')
            print("===PATH===" + str(real_path))
            path_list2.append(real_path)
            path = os.path.join(real_path)
            if os.path.exists(path):
                result_list.append(1)
            else:
                result_list.append(0)
        if any(x in str(path_list2) for x in GT):
            return {"Result": 1, "Reason": ""}
        else:
            if "0" in str(result_list) and str(result) != '':
                return {"Result": 0, "Reason": "有不存在路径"+str(path_list2)}
            elif "0" not in str(result_list):
                return {"Result": 0, "Reason": "与GT答案不符"}
            else:
                return {"Result": 0, "Reason": "无效回答"}
    elif "failed" in str(result2):
        return {"Result": 0, "Reason": "回答前后矛盾"}
    # else:
    #     # 所有不支持的场景都返回默认值
    #     return {"Result": 0, "Reason": "不支持的场景"}
    
# if __name__ == "__main__":
#     test_row = {
#         'scene': 'File search',
#         'result': 'The file is at C:\\Users\\test\\file.jpg',
#         'gt': 'C:\\Users\\test\\file.jpg'
#     }
#     print(main(test_row))