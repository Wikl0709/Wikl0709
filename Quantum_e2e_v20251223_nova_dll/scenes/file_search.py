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
    1. File address containing a slash
    2. A name part (alphanumeric characters, underscores, hyphens)
    3. An extension part (e.g., .jpg, .png, .docx)

    Examples:
    - "The file I found is C:\\Users\\Lenovo Yanglei AFR\\Desktop\\LRIA_llm_eval\\eval\\20250917\\files\\wangty19_work_2.jpg" → "C:\\Users\\Lenovo Yanglei AFR\\Desktop\\LRIA_llm_eval\\eval\\20250917\\files\\wangty19_work_2.jpg"
    - "The address of the file is image_search_results/sales_report.pdf" → "image_search_results/sales_report.pdf"

    Rules:
    1. ONLY extract file path that are explicitly mentioned in the text.
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

def main():
    file_path = r'test_file.xlsx'
    df_query = pd.read_excel(file_path, sheet_name='Sheet2')
    for index, rows in df_query.iterrows():
        scene=rows['scene']
        result_text=rows['result']
        GT = rows['gt']
        print(result_text)
        if scene=='File search':
            result_list = []
            reason_list = []
            path_list = []
            result=all_details_check(result_text)
            result=str(result).strip("[]")
            path_list.append(result)
            for filepath in result.split(','):
                filepath = str(filepath).replace("'", "").replace('"', '').strip(" ").replace("\\\\","\\")
                print("===PATH==="+str(filepath))
                path=os.path.join(filepath)
                if os.path.exists(path):
                    result_list.append(1)
                else:
                    result_list.append(0)
            if "0" in str(result_list):
                if str(GT)=='':
                    return {"Result": 1, "Reason": "负样本拒答"}
                else:
                    return {"Result": 0, "Reason": "有不存在路径"}
            else:
                if str(GT) in str(result):
                    return {"Result": 1, "Reason": ""}
                else:
                    return {"Result": 0, "Reason": "与GT答案不符"}
    #         df_query.loc[index, 'GT_judge_result'] = GT_judge_result
    #         df_query.loc[index, 'path_judge_result'] =final_result
    #         df_query.loc[index,'path_judge_result_list'] = str(result_list)
    #         df_query.loc[index,'reason_result'] = str(reason_list)
    #         df_query.loc[index,'path_result'] = str(path_list)
    # df_query.to_excel('RESULT_file_search2.xlsx',index=False)

main()
