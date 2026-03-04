# scenes/file_search.py
import time
from typing import Dict
import os


def main(row: Dict) -> Dict:
    doc_dir = row.get("doc_dir", "")
    start_time = time.time()
    result_list = []
    for filename in row['gt'].split(','):
        path=os.path.join(doc_dir,filename)
        if path in row['result']:
            result_list.append(1)
        else:
            result_list.append(0)
    if sum(result_list)==0:
        return {"Result": 0, "Reason": "完整路径不在回答中"}
    else:
        return {"Result": 1, "Reason": ""}
