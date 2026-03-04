# scenes/file_search.py
import time
from typing import Dict
import os
from openai import AzureOpenAI
from datetime import datetime
import pandas as pd

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

def main(row: Dict) -> Dict:
    scene = row.get('scene', '').strip().lower()
    result_text = str(row.get('result', '')).strip()
    GT = str(row.get('gt', '')).strip()
    if str(GT) != 'nan':
        GT = str(GT).split(",")
    # if scene == 'File search':
    result_list = []
    path_list = []

    result = all_details_check(result_text)
    result = str(result).strip("[]")
    path_list.append(result)

    for filepath in result.split(','):
        filepath = str(filepath).replace("'", "").replace('"', '').strip(" ").replace("\\\\", "\\")
        print("===PATH==="+str(filepath))
        path = os.path.join(filepath)
        if os.path.exists(path):
            result_list.append(1)
        else:
            result_list.append(0)

    if "0" in str(result_list) and str(filepath) == '':
        if str(GT) == 'nan':
            return {"Result": 1, "Reason": "负样本正确拒答"}
        else:
            return {"Result": 0, "Reason": ""}
    elif "0" in str(result_list) and str(filepath) != '':
        return {"Result": 0, "Reason": "有不存在路径"}
    elif "0" not in str(result_list):
        if str(GT) == 'nan':
            return {"Result": 0, "Reason": "负样本错误回答"}
        elif any(x in str(result) for x in GT):
            return {"Result": 1, "Reason": ""}
        else:
            return {"Result": 0, "Reason": "与GT答案不符"}
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