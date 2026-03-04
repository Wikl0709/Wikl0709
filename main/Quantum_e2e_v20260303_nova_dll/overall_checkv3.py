
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改动：修改了抽槽判决的逻辑（file type）
功能：
- 读取 Excel（.xlsx/.xls）
- 封装并执行四项检查，分别新增以下列：
 1) domain_check —— 域判断（pass / fail / pass* / pass** / 空白）
 2) mapping_check —— 映射判断（pass / fail / pass* / 空白）当走到此node才判断
 3) intent_check —— 意图识别判断（pass / fail / 空白）当走到此node才判断
 4) slot_Result、slot_Correct_Count、slot_Error_Reasons —— 槽位判断结果/统计/原因
 5) tool_check —— 解析 LOCAL_TOOL_RETURN 的 status（success→pass；error→fail；空白→不判断）
说明：
- 完全沿用原始四段脚本的判断逻辑与默认输出取值，仅做小幅度整合与工具函数复用；
- 输入为含有 label 和模型输出的 Excel；输出同样为一张 Excel。
"""
# =========================
# 参数区（按需修改）
# =========================
# --- I/O 参数 ---
INPUT_EXCEL_PATH = r"D:\4_local_solution\20251223_xudong\NV\out_nv_test_results_local_solution_case_bvt_1223.xlsx"  # 输入 Excel 路径
OUTPUT_EXCEL_PATH = r"D:\4_local_solution\20251223_xudong\NV\out_out_nv_test_results_local_solution_case_bvt_1223.xlsx"  # 输出 Excel 路径（会创建/覆盖）
SHEET_NAME = 0  # 读取的工作表；可用表名或索引（0 表示第一个）

# --- 业务列名设置（域判断） ---
DOMAIN_COLUMN_NAME = "DOMAIN"  # 自动忽略列名中的 \r/\n 与首尾空白
DOMAIN_LABEL_COLUMN_NAME = "domain_label"
CURRENT_INTENT_MAPPING_COLUMN_NAME = "CURRENT_INTENT_MAPPING"
DOMAIN_NEW_COLUMN_NAME = "domain_check"

# --- 业务列名设置（映射判断） ---
MAPPING_COL = CURRENT_INTENT_MAPPING_COLUMN_NAME
INTENT_MAPPING_LABEL_COL = "intent_mapping_label"
MAPPING_NEW_COLUMN_NAME = "mapping_check"

# --- 业务列名设置（意图识别判断） ---
CURRENT_INTENT_RECOGNITION_COL = "CURRENT_INTENT_RECOGNITION"
INTENT_RECOGNITION_LABEL_COL = "intent_recognition_label"
INTENT_NEW_COLUMN_NAME = "intent_check"

# --- 业务列名设置（槽位判断） ---
SLOT_LABEL_COL = "slot_label"
SLOT_RESULT_COL = "slot_Result"
SLOT_CORRECT_COUNT_COL = "slot_Correct_Count"
SLOT_ERROR_REASONS_COL = "slot_Error_Reasons"

# --- [新增] 业务列名设置（工具返回判断） ---
LOCAL_TOOL_RETURN_COL = "LOCAL_TOOL_RETURN"
TOOL_CHECK_NEW_COLUMN_NAME = "tool_check"

# --- 通用输出值 ---
PASS_VALUE = "pass"
FAIL_VALUE = "fail"
PASS_STAR_VALUE = "pass*"
PASS_DOUBLE_STAR_VALUE = "pass**"  # [新增] 其它情形的兜底

# --- 域判断参数（保持原逻辑的可配置项） ---
CONFIDENCE_THRESHOLD = 0.9  # 严格大于/小于此值（等于 0.9 不入高/低）
CASE_SENSITIVE_INTENT_MATCH = True  # intent 与 domain_label 比较是否大小写敏感

# --- 映射 & 意图判断参数（保持原逻辑） ---
STRIP_WHITESPACE = True  # 比较前是否去掉前后空白
CASE_INSENSITIVE = False  # 是否大小写不敏感（True 则统一按小写比较）

# --- 槽位判断参数（保持原逻辑） ---
SLOT_KEYWORDS_SIM_THRESHOLD = 0.8  # keywords 模糊匹配相似度阈值
SLOT_VERBOSE_PRINT = False  # 控制台是否打印槽位逐行详细信息

# =========================
# 代码区（一般不需要修改）
# =========================
import os
import sys
import re
import ast
import json
import math
from difflib import SequenceMatcher
from typing import Any, Dict, Optional, Tuple
import pandas as pd

# ---- 空值/占位识别（沿用域判断脚本） ----
_EMPTY_STRINGS = {
    "", " ", "　", "nan", "NaN", "NAN", "none", "None", "NONE",
    "null", "Null", "NULL", "nil", "Nil", "NIL",
    "[]", "{}", "N/A", "n/a", "-", "--"
}

def _sanitize_col_name(name: str) -> str:
    """去除列名中的回车/换行并去掉首尾空白。"""
    if not isinstance(name, str):
        name = str(name)
    name = re.sub(r"[\r\n]+", "", name)
    return name.strip()

def _find_actual_col_name(df: pd.DataFrame, target: str) -> str:
    """在 DataFrame 中找到与目标列名（忽略 \r\n 和空白）匹配的真实列名。"""
    target_norm = _sanitize_col_name(target)
    for col in df.columns:
        if _sanitize_col_name(col) == target_norm:
            return col
    raise KeyError(
        f"未找到列名：{target}（脚本忽略列名中的回车/换行与空白；请检查实际表头）"
    )

def _is_empty_cell(val: Any) -> bool:
    """判断单元格是否为空（NaN 或占位空字符串）。"""
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str):
        s = val.strip()
        if s in _EMPTY_STRINGS:
            return True
        # 形如 '"[]"' 或 "'{}'" 也视为空
        s_unquoted = s.strip('"').strip("'")
        if s_unquoted in _EMPTY_STRINGS:
            return True
    return False

def _to_stripped(val: Any) -> str:
    """将单元格转为去掉首尾空白的字符串（NaN/占位 -> ''）。"""
    if _is_empty_cell(val):
        return ""
    return str(val).strip()

def _read_excel(file_path: str, sheet_name=0) -> pd.DataFrame:
    """
    读取 Excel（.xlsx/.xls）；
    - .xlsx 使用 engine='openpyxl'
    - .xls 使用 engine='xlrd'
    - 其他扩展名尝试 openpyxl
    """
    lower = file_path.lower()
    if lower.endswith(".xlsx"):
        return pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
    elif lower.endswith(".xls"):
        return pd.read_excel(file_path, sheet_name=sheet_name, engine="xlrd")
    else:
        return pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")

# ---- intent/domain 辅助 ----
def _to_float_if_number(val: Any) -> Optional[float]:
    """若 val 可安全转为浮点数，返回 float；否则返回 None。"""
    if val is None:
        return None
    if isinstance(val, str) and _is_empty_cell(val):
        return None
    try:
        f = float(val)
        if math.isnan(f):
            return None
        return f
    except Exception:
        return None

def _equals_intent(a: str, b: str, case_sensitive: bool = True) -> bool:
    """比较 intent 与 domain_label 是否相等，支持大小写敏感配置。"""
    if a is None or b is None:
        return False
    a_s = a.strip()
    b_s = b.strip()
    if case_sensitive:
        return a_s == b_s
    else:
        return a_s.lower() == b_s.lower()

def _normalize_value_generic(s: Any) -> Optional[str]:
    """
    映射/意图比较使用的规范化（可选去空白与大小写处理），保持与原映射/意图脚本一致。
    """
    if s is None:
        return None
    if isinstance(s, float) and pd.isna(s):
        return None
    if not isinstance(s, str):
        s = str(s)
    if STRIP_WHITESPACE:
        s = s.strip()
    if CASE_INSENSITIVE:
        s = s.lower()
    return s

# =========================
# 功能一：域判断（新增 domain_check）
# —— 按新规则：仅比较 DOMAIN.intent / confidence 与 domain_label
# =========================
def _parse_domain_first_dict(cell: Any) -> Optional[Dict[str, Any]]:
    """
    解析 DOMAIN 单元格并返回第一个字典：
    支持 list[dict] / dict / JSON 字符串 / Python 字面量字符串（literal_eval）
    返回：第一个 dict 或 None（不可解析或为空）
    """
    if _is_empty_cell(cell):
        return None
    # 直接为 dict 的情况
    if isinstance(cell, dict):
        return cell
    # list[dict] 的情况
    if isinstance(cell, list):
        if len(cell) == 0:
            return None
        first = cell[0]
        return first if isinstance(first, dict) else None
    # 字符串：尝试 JSON / Python 字面量
    if isinstance(cell, str):
        s = cell.strip()
        if s == "":
            return None
        # 优先尝试 JSON
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list) and parsed:
                return parsed[0] if isinstance(parsed[0], dict) else None
        except Exception:
            pass
        # 再尝试 Python 字面量（支持单引号等）
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list) and parsed:
                return parsed[0] if isinstance(parsed[0], dict) else None
        except Exception:
            pass
    return None

def domain_check(df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """
    计算 domain_check 列：依据 DOMAIN.intent 与 confidence 以及 domain_label：
    - pass  : intent == domain_label 且 intent != 'ood' 且 confidence > 0.9
    - fail  : intent != domain_label 且 intent != 'ood' 且 confidence > 0.9
    - pass* : domain_label != 'ood' 且 intent == 'ood'；或 domain_label != 'ood'、intent != 'ood' 且 confidence < 0.9
    - pass**: 其余所有情况（例如 confidence 缺失；或 domain_label == 'ood' 等）
    注：intent 指的是从 DOMAIN 列解析出的 intent。
    """
    domain_col = _find_actual_col_name(df, DOMAIN_COLUMN_NAME)
    domain_label_col = _find_actual_col_name(df, DOMAIN_LABEL_COLUMN_NAME)
    # 保留对 CURRENT_INTENT_MAPPING 的列定位，但逻辑不再使用（为小幅改动、结构最小调整）
    current_mapping_col = _find_actual_col_name(df, CURRENT_INTENT_MAPPING_COLUMN_NAME)

    # 初始化新列为空字符串（表示“未判断”）
    df[DOMAIN_NEW_COLUMN_NAME] = ""

    pass_count = 0
    pass_star_count = 0
    pass_double_star_count = 0
    fail_count = 0

    for idx, row in df.iterrows():
        domain_cell = row[domain_col]
        domain_label = _to_stripped(row[domain_label_col])
        current_mapping = _to_stripped(row[current_mapping_col])  # 未使用，仅保留

        # 解析 DOMAIN 的第一个字典（兼容 dict / list[dict] / 字符串）
        first_dict = _parse_domain_first_dict(domain_cell)

        # 若 DOMAIN 与 label 均为空，保持空白不判断
        if first_dict is None and _is_empty_cell(domain_label):
            continue

        # 提取 intent / confidence（若存在）
        intent = ""
        confidence_val = None
        if isinstance(first_dict, dict):
            intent = _to_stripped(first_dict.get("intent", ""))
            confidence_val = _to_float_if_number(first_dict.get("confidence", None))

        # 标准化判断
        label_is_ood = (domain_label.strip().lower() == "ood") if domain_label else False
        intent_is_ood = intent.strip().lower() == "ood"
        intent_matches_label = _equals_intent(intent, domain_label, case_sensitive=CASE_SENSITIVE_INTENT_MATCH)

        conf_high = (confidence_val is not None) and (confidence_val > CONFIDENCE_THRESHOLD)
        conf_low  = (confidence_val is not None) and (confidence_val < CONFIDENCE_THRESHOLD)

        # 新规则判断
        result = ""
        if (not intent_is_ood) and conf_high:
            # 高置信度且 intent 非 ood：按匹配/不匹配判定通过或失败
            if intent_matches_label:
                result = PASS_VALUE
            else:
                result = FAIL_VALUE
        elif (not label_is_ood and intent_is_ood) or (not label_is_ood and (not intent_is_ood) and conf_low):
            # 路走长了 或 label 非 ood 但识别为 ood
            result = PASS_STAR_VALUE
        else:
            # 其它所有情况归为 pass**
            result = PASS_DOUBLE_STAR_VALUE

        if result:
            df.at[idx, DOMAIN_NEW_COLUMN_NAME] = result
            pass_count += int(result == PASS_VALUE)
            pass_star_count += int(result == PASS_STAR_VALUE)
            pass_double_star_count += int(result == PASS_DOUBLE_STAR_VALUE)
            fail_count += int(result == FAIL_VALUE)

    stats = {
        "PASS": pass_count,
        "PASS*": pass_star_count,
        "PASS**": pass_double_star_count,
        "FAIL": fail_count,
        "BLANK": len(df) - pass_count - pass_star_count - pass_double_star_count - fail_count
    }
    return df, stats

# =========================
# 功能二：映射判断（新增 mapping_check）
# —— 修改点：仅当 CURRENT_INTENT_MAPPING 有值时才判断；为空则留空（不判）
# 原先的“label 为空留空”规则保留，其余逻辑不变
# =========================
def mapping_check(df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """
    映射判断（修改后）：
    - 当 CURRENT_INTENT_MAPPING 为空：不判断，结果留空；
    - 当 CURRENT_INTENT_MAPPING 非空：
        * 若 intent_mapping_label 为空：不判断，结果留空；
        * 若二者均非空且值相等 -> pass；否则 -> fail。
    """
    mapping_col = _find_actual_col_name(df, MAPPING_COL)
    label_col = _find_actual_col_name(df, INTENT_MAPPING_LABEL_COL)

    results = []
    pass_cnt = 0
    fail_cnt = 0
    pass_star_cnt = 0  # 保持原统计结构（可能为 0）

    mapping_series = df[mapping_col]
    label_series = df[label_col]

    for mapping_val, label_val in zip(mapping_series, label_series):
        # 仅当 CURRENT_INTENT_MAPPING 有值时才判断；为空 -> 留空
        if _is_empty_cell(mapping_val):
            results.append("")  # 不参与统计
            continue

        # 保留原逻辑：label 为空则也不判断
        if _is_empty_cell(label_val):
            results.append("")  # 不参与统计
            continue

        n_map = _normalize_value_generic(mapping_val)
        n_lab = _normalize_value_generic(label_val)

        # 两者均非空且值相等 -> pass；否则 -> fail
        if n_map is not None and n_lab is not None and n_map == n_lab:
            results.append(PASS_VALUE)
            pass_cnt += 1
        else:
            results.append(FAIL_VALUE)
            fail_cnt += 1

    df[MAPPING_NEW_COLUMN_NAME] = results
    stats = {"PASS": pass_cnt, "FAIL": fail_cnt, "PASS*": pass_star_cnt, "TOTAL": len(df)}
    return df, stats

# =========================
# 功能三：意图识别判断（新增 intent_check）
# —— 修改点：仅当 CURRENT_INTENT_RECOGNITION 有值时才判断；为空则留空（不判）
# 原先的“label 为空留空”规则保留，其余逻辑不变
# =========================
def _parse_intent_from_recognition(cell: Any) -> Optional[str]:
    """
    从 CURRENT_INTENT_RECOGNITION 的单元格中解析 intent。
    支持：
    - dict: {"intent": "...", "slot": [...]}
    - JSON 字符串 / Python 字面量字符串
    - 解析失败时用正则提取 "intent" 值（双/单引号）
    """
    if pd.isna(cell):
        return None
    if isinstance(cell, dict):
        return cell.get("intent")
    if isinstance(cell, str):
        s = cell.strip()
        # 1) 标准 JSON
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj.get("intent")
        except Exception:
            pass
        # 2) Python 字面量（支持单引号等）
        try:
            obj = ast.literal_eval(s)
            if isinstance(obj, dict):
                return obj.get("intent")
        except Exception:
            pass
        # 3) 正则提取（双引号）
        m = re.search(r'"intent"\s*:\s*"([^"]+)"', s)
        if m:
            return m.group(1)
        # 4) 正则提取（单引号）
        m2 = re.search(r"'intent'\s*:\s*'([^']+)'", s)
        if m2:
            return m2.group(1)
    return None

def intent_check(df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """
    意图识别判断（修改后）：
    - 当 CURRENT_INTENT_RECOGNITION 为空：不判断，结果留空；
    - 当 CURRENT_INTENT_RECOGNITION 非空：
        * 若 intent_recognition_label 为空：不判断，结果留空；
        * 解析 intent，与 label 比较；相同 -> pass，否则 -> fail。
    """
    curr_col = _find_actual_col_name(df, CURRENT_INTENT_RECOGNITION_COL)
    label_col = _find_actual_col_name(df, INTENT_RECOGNITION_LABEL_COL)

    raw_rec_series = df[curr_col]
    intents = raw_rec_series.apply(_parse_intent_from_recognition)
    norm_intents = intents.apply(_normalize_value_generic)

    raw_labels = df[label_col]
    norm_labels = raw_labels.apply(_normalize_value_generic)

    results = []
    pass_cnt = 0
    fail_cnt = 0

    for i_val, l_val, raw_l, raw_rec in zip(norm_intents, norm_labels, raw_labels, raw_rec_series):
        # 新增条件：仅当 CURRENT_INTENT_RECOGNITION 有值时才判断；为空 -> 留空
        if _is_empty_cell(raw_rec):
            results.append("")  # 不参与统计
            continue

        # 保留原逻辑：label 为空 -> 留空
        if _is_empty_cell(raw_l):
            results.append("")  # 不参与统计
            continue

        if i_val is not None and l_val is not None and i_val == l_val:
            results.append(PASS_VALUE)
            pass_cnt += 1
        else:
            results.append(FAIL_VALUE)
            fail_cnt += 1

    df[INTENT_NEW_COLUMN_NAME] = results
    stats = {"PASS": pass_cnt, "FAIL": fail_cnt, "TOTAL": len(df)}
    return df, stats

# =========================
# 功能四：槽位判断（新增 slot_* 三列）
# —— 保持 4_eval_slot.py 的逻辑 + [MOD] 解析增强
# =========================
def _normalize_slot_value(value: Any):
    """标准化槽位值：转小写，去除空格；list/dict 递归处理。"""
    if isinstance(value, str):
        return value.lower().strip()
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, list):
        return [_normalize_slot_value(v) for v in value]
    elif isinstance(value, dict):
        return {k: _normalize_slot_value(v) for k, v in value.items()}
    return value

def _pred_slot_deal(pred_norm_list):
    """将预测的 slot 列表转换为字典格式（沿用原脚本的日期特殊处理与 normalized 取第一值）。"""
    pred_dict = {}
    for slot in pred_norm_list:
        arg_name = slot.get("arguments")
        if not arg_name:
            continue
        if arg_name in ["start_date", "end_date"]:
            pred_dict[arg_name] = slot.get("normalized", "")
        elif arg_name == "keywords":
            # keywords字段使用normalized的所有值，空格分隔
            normalized = slot.get("normalized", [])
            if isinstance(normalized, list):
                pred_dict[arg_name] = " ".join([str(n) for n in normalized])
            elif isinstance(normalized, (str, int, float)):
                pred_dict[arg_name] = str(normalized)
            else:
                pred_dict[arg_name] = ""
        elif arg_name == "file_types":
            # file_types字段使用normalized的所有值，逗号分隔
            normalized = slot.get("normalized", [])
            if isinstance(normalized, list):
                pred_dict[arg_name] = ",".join([str(n) for n in normalized])
            elif isinstance(normalized, (str, int, float)):
                pred_dict[arg_name] = str(normalized)
            else:
                pred_dict[arg_name] = ""
        else:
            normalized = slot.get("normalized", [])
            if isinstance(normalized, list) and len(normalized) > 0:
                pred_dict[arg_name] = str(normalized[0])
            elif isinstance(normalized, (str, int, float)):
                pred_dict[arg_name] = str(normalized)
            else:
                pred_dict[arg_name] = ""
    return pred_dict

def compare_slot_json(ground_truth, prediction, verbose=False, keywords_sim_threshold=SLOT_KEYWORDS_SIM_THRESHOLD):
    """
    比较两份槽位 JSON（沿用原脚本规则 + [MOD] 解析增强）：
    1) keywords 字段模糊匹配，相似度 >= 阈值即算对；
    2) 其它字段严格匹配（大小写不敏感，已标准化）；
    3) GT 为 "unknown" 的字段：预测缺失或为 "unknown" 也算对，但不计入统计分母。

    解析兼容：
    - 支持标准 JSON 字符串；
    - [MOD] 支持 Python 字面量字符串（例如使用单引号）；
    - [MOD] 支持 prediction 为 dict 且含 "slot" 列表的结构，如：
      {'intent': 'app_control_open_app', 'slot': [{'normalized': ['Chrome'], 'raw': ['Chrome'], 'arguments': 'appnames'}]}

    返回: result("pass"/"pass*"/"fail"), correct_count, total_count, error_reasons(list)
    """
    error_reasons = []
    correct_count = 0
    total_count = 0

    def _parse_str_obj(obj):
        """字符串解析：优先 JSON，其次 Python 字面量；失败则抛出以进入外层异常。"""
        if not isinstance(obj, str):
            return obj
        s = obj.strip()
        # 尝试 JSON
        try:
            return json.loads(s)
        except Exception:
            pass
        # 兜底：Python 字面量（兼容单引号）
        try:
            return ast.literal_eval(s)
        except Exception:
            # 原脚本行为为 json 解析失败直接异常，这里保持一致进入异常分支
            raise

    try:
        # 解析 GT 与 Pred（新增对 Python 字面量的兼容）
        
        if isinstance(ground_truth, str):
            ground_truth = ground_truth.replace("“","\"")
            gt = ast.literal_eval(ground_truth)
            # gt = json.loads(ground_truth)
        else:
            gt = ground_truth
            
        if isinstance(prediction, str):
            pred = ast.literal_eval(prediction)
            # pred = json.loads(prediction)
        else:
            pred = prediction
        
        # gt = _parse_str_obj(ground_truth)
        # pred = _parse_str_obj(prediction)

        gt_norm = _normalize_slot_value(gt)

        # [MOD] 兼容 prediction 为 dict 且含 "slot" 列表
        if isinstance(pred, dict) and "slot" in pred:
            pred_slots = pred.get("slot", [])
            pred_slot_dict = _pred_slot_deal(pred_slots)
            pred_norm = _normalize_slot_value(pred_slot_dict)
        else:
            pred_norm = _normalize_slot_value(pred)

        # 遍历 GT 的每个字段
        for key, gt_value in gt_norm.items():
            pred_value = pred_norm.get(key, None)

            # 规则3：GT=unknown，不计入统计分母，但记为“算对”
            if gt_value == "unknown":
                continue  # 视作“算对”但不计入分母

            total_count += 1

            # 预测缺失（GT 非 unknown）
            if pred_value is None:
                error_reasons.append(f"{key}: 预测值缺失 (GT='{gt_value}')")
                continue

            # 规则1：keywords 模糊匹配
            if key == "keywords":
                sim = SequenceMatcher(None, str(gt_value).lower(), str(pred_value).lower()).ratio()
                if sim >= keywords_sim_threshold:
                    correct_count += 1
                else:
                    error_reasons.append(
                        f"{key}: 模糊匹配失败 (相似度={sim:.2f}) GT='{gt_value}' vs Pred='{pred_value}'"
                    )
            # 规则2：其它字段严格匹配（已标准化为小写）
            else:
                if gt_value == pred_value:
                    correct_count += 1
                else:
                    error_reasons.append(f"{key}: 不匹配 GT='{gt_value}' vs Pred='{pred_value}'")

        # 判定结果
        if total_count == 0:
            result = PASS_VALUE  # 全是 unknown → 视作全对
        elif correct_count == total_count:
            result = PASS_VALUE  # 全对
        elif correct_count == 0:
            result = FAIL_VALUE  # 全错
        else:
            result = PASS_STAR_VALUE  # 部分对

        if verbose:
            print("Slot统计: {}/{} 正确".format(correct_count, total_count))
            print("结果: {}".format(result))

    except json.JSONDecodeError as e:
        result = FAIL_VALUE
        error_reasons = ["JSON解析错误: {}".format(str(e))]
        if verbose:
            print("JSON解析错误: {}".format(str(e)))
    except Exception as e:
        # 包含 ast.literal_eval 失败等情况
        result = FAIL_VALUE
        error_reasons = ["比较出错: {}".format(str(e))]
        if verbose:
            print("比较出错: {}".format(str(e)))

    return result, correct_count, total_count, error_reasons

def slot_check(df: pd.DataFrame, verbose=False, keywords_sim_threshold=SLOT_KEYWORDS_SIM_THRESHOLD) -> Tuple[pd.DataFrame, dict]:
    """
    按原脚本规则对每行进行槽位比较，并写出三列：
      - slot_Result: "pass"/"pass*"/"fail"
      - slot_Correct_Count: "X/Y"
      - slot_Error_Reasons: "; " 分隔的错误原因
    """
    slot_label_col = _find_actual_col_name(df, SLOT_LABEL_COL)
    curr_rec_col = _find_actual_col_name(df, CURRENT_INTENT_RECOGNITION_COL)

    # 预创建列，避免多次扩容
    if SLOT_RESULT_COL not in df.columns:
        df[SLOT_RESULT_COL] = ""
    if SLOT_CORRECT_COUNT_COL not in df.columns:
        df[SLOT_CORRECT_COUNT_COL] = ""
    if SLOT_ERROR_REASONS_COL not in df.columns:
        df[SLOT_ERROR_REASONS_COL] = ""

    pass_cnt = 0
    pass_star_cnt = 0
    fail_cnt = 0
    total_rows_evaluated = 0

    for i in range(len(df)):
        gt_json = df.loc[i, slot_label_col]
        if pd.isna(gt_json):
            # 与原脚本一致：GT 为空则跳过，不写结果
            continue

        pred_json = df.loc[i, curr_rec_col]

        result, correct, total, errors = compare_slot_json(
            gt_json, pred_json, verbose=verbose, keywords_sim_threshold=keywords_sim_threshold
        )
        # 修正变量名的小笔误，不影响逻辑
        df.loc[i, SLOT_RESULT_COL] = result
        df.loc[i, SLOT_CORRECT_COUNT_COL] = f"{correct}/{total}"
        df.loc[i, SLOT_ERROR_REASONS_COL] = "; ".join(errors)

        total_rows_evaluated += 1
        if result == PASS_VALUE:
            pass_cnt += 1
        elif result == PASS_STAR_VALUE:
            pass_star_cnt += 1
        elif result == FAIL_VALUE:
            fail_cnt += 1

    stats = {
        "PASS": pass_cnt,
        "PASS*": pass_star_cnt,
        "FAIL": fail_cnt,
        "EVALUATED_ROWS": total_rows_evaluated
    }
    return df, stats

# =========================
# [修改点] 功能五：工具返回判断（tool_check）
# —— 只要 LOCAL_TOOL_RETURN 不为空就执行判断；
#    code=OK→pass，code≠OK→fail；
#    无法解析时新增正则兜底提取 "code"：
#       * 若提取到 OK → pass
#       * 若提取到其他值 → fail
#       * 若仍无法提取 → pass*
#    为空 → 留空（不判断）。
# =========================
def _parse_tool_code(cell: Any) -> Optional[str]:
    """
    解析 LOCAL_TOOL_RETURN 单元格中的 code。
    支持 dict / list[dict] / JSON 字符串 / Python 字面量字符串。
    返回：code（大写）或 None（不可解析/无 code/空）。
    """
    if _is_empty_cell(cell):
        return None

    def _extract_code_from_obj(obj) -> Optional[str]:
        if isinstance(obj, dict):
            val = obj.get("code")
            if val is None:
                return None
            if isinstance(val, str):
                return val.strip().upper()  # 统一转大写
            return str(val).strip().upper()
        if isinstance(obj, list) and obj:
            # 取第一个元素，若为 dict 则尝试读取 code
            first = obj[0]
            if isinstance(first, dict) and "code" in first:
                v = first.get("code")
                if isinstance(v, str):
                    return v.strip().upper()
                return str(v).strip().upper()
        return None

    # dict / list 直接处理
    if isinstance(cell, (dict, list)):
        return _extract_code_from_obj(cell)

    # 字符串：先 JSON，再 literal_eval
    if isinstance(cell, str):
        s = cell.strip()
        # JSON
        try:
            obj = json.loads(s)
            code = _extract_code_from_obj(obj)
            if code is not None:
                return code
        except Exception:
            pass
        # Python 字面量
        try:
            obj = ast.literal_eval(s)
            code = _extract_code_from_obj(obj)
            if code is not None:
                return code
        except Exception:
            pass

    return None

def _extract_code_via_regex(text: str) -> Optional[str]:
    """
    在无法解析的情况下，使用正则从原始文本中兜底提取 code。
    支持双引号与单引号形式；大小写不敏感；返回大写的 code。
    例如：{"status":"Success","code":"OK","message":"..."} -> 'OK'
    """
    if text is None:
        return None
    try:
        s = str(text).strip()
    except Exception:
        return None

    patterns = [
        r'"code"\s*:\s*"([^"]+)"',
        r"'code'\s*:\s*'([^']+)'",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().upper()  # 统一转大写
    return None

def tool_check(df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """
    判断 LOCAL_TOOL_RETURN 的 code：
      - 只要 LOCAL_TOOL_RETURN 非空就执行判断：
          * code 为 OK -> 写入 'pass'
          * code 为其他值 -> 写入 'fail'
          * 无法解析 -> 使用正则兜底提取 'code'：
                - 提取到 OK -> 'pass'
                - 提取到其他值 -> 'fail'
                - 仍无法提取 -> 'pass*'
      - 单元格为空 -> 留空（不判断）
    若不存在 LOCAL_TOOL_RETURN 列：不报错，整列留空。
    """
    # 预创建新列
    if TOOL_CHECK_NEW_COLUMN_NAME not in df.columns:
        df[TOOL_CHECK_NEW_COLUMN_NAME] = ""

    # 尝试定位源列；不存在则跳过
    try:
        tool_col = _find_actual_col_name(df, LOCAL_TOOL_RETURN_COL)
        col_exists = True
    except KeyError:
        col_exists = False

    pass_cnt = 0
    fail_cnt = 0
    pass_star_cnt = 0

    if col_exists:
        for idx, cell in df[tool_col].items():
            # 空白：不判断，留空
            if _is_empty_cell(cell):
                df.at[idx, TOOL_CHECK_NEW_COLUMN_NAME] = ""
                continue

            code = _parse_tool_code(cell)  # 已大写或 None

            # 优先使用结构化解析结果
            if code == "OK":
                df.at[idx, TOOL_CHECK_NEW_COLUMN_NAME] = PASS_VALUE
                pass_cnt += 1
                continue
            elif code is not None:  # code 存在但不是 OK
                df.at[idx, TOOL_CHECK_NEW_COLUMN_NAME] = FAIL_VALUE
                fail_cnt += 1
                continue

            # [新增] 无法解析时，用正则兜底提取 code
            # 支持字符串原文，也尽量兼容非字符串对象的 str(...) 表示
            code_regex = None
            if isinstance(cell, str):
                code_regex = _extract_code_via_regex(cell)
            else:
                try:
                    code_regex = _extract_code_via_regex(str(cell))
                except Exception:
                    code_regex = None

            if code_regex == "OK":
                df.at[idx, TOOL_CHECK_NEW_COLUMN_NAME] = PASS_VALUE
                pass_cnt += 1
            elif code_regex is not None:  # 提取到了 code 但不是 OK
                df.at[idx, TOOL_CHECK_NEW_COLUMN_NAME] = FAIL_VALUE
                fail_cnt += 1
            else:
                # 仍无法提取 -> 记为 pass*
                df.at[idx, TOOL_CHECK_NEW_COLUMN_NAME] = PASS_STAR_VALUE
                pass_star_cnt += 1

        not_evaluated = 0
    else:
        # 源列不存在：整列保持空白，不报错
        not_evaluated = len(df)

    blank_cnt = len(df) - pass_cnt - fail_cnt - pass_star_cnt
    stats = {
        "PASS": pass_cnt,
        "FAIL": fail_cnt,
        "PASS*": pass_star_cnt,
        "BLANK": blank_cnt,
        "NOT_EVALUATED": not_evaluated
    }
    return df, stats


# =========================
# 主函数
# =========================
def get_check_result(input_path: str, output_path: str):
    # 读取 Excel
    df = _read_excel(input_path, sheet_name=SHEET_NAME)

    # 顺序执行四项检查 + [新增]工具返回判断
    df, domain_stats = domain_check(df)
    df, mapping_stats = mapping_check(df)
    df, intent_stats = intent_check(df)
    df, slot_stats = slot_check(df, verbose=SLOT_VERBOSE_PRINT, keywords_sim_threshold=SLOT_KEYWORDS_SIM_THRESHOLD)
    df, tool_stats = tool_check(df)  # [修改后的逻辑]

    # 写出结果到 Excel（使用 openpyxl）
    df.to_excel(output_path, index=False, engine="openpyxl")

    # 统计与路径提示
    print("已写出到：", os.path.abspath(output_path))
    print("[domain_check ] PASS={}, PASS*={}, PASS**={}, FAIL={}, BLANK={}".format(
        domain_stats['PASS'], domain_stats['PASS*'], domain_stats['PASS**'], domain_stats['FAIL'], domain_stats['BLANK']))
    print("[mapping_check] PASS={}, FAIL={}, PASS*={}, TOTAL={}".format(
        mapping_stats['PASS'], mapping_stats['FAIL'], mapping_stats['PASS*'], mapping_stats['TOTAL']))
    print("[intent_check ] PASS={}, FAIL={}, TOTAL={}".format(
        intent_stats['PASS'], intent_stats['FAIL'], intent_stats['TOTAL']))
    print("[slot_check   ] PASS={}, PASS*={}, FAIL={}, EVALUATED_ROWS={}".format(
        slot_stats['PASS'], slot_stats['PASS*'], slot_stats['FAIL'], slot_stats['EVALUATED_ROWS']))
    print("[tool_check   ] PASS={}, FAIL={}, PASS*={}, BLANK={}, NOT_EVALUATED={}".format(
        tool_stats['PASS'], tool_stats['FAIL'], tool_stats['PASS*'], tool_stats['BLANK'], tool_stats['NOT_EVALUATED']))
    return df

# 主程序
if __name__ == '__main__':
    INPUT_EXCEL_PATH = r"D:\00work\AIPC\Intent\20251223\1out_out_nv_test_results_local_solution_case_bvt_1223.xlsx"  # 输入 Excel 路径
    input_excel_path = INPUT_EXCEL_PATH
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        input_excel_path = sys.argv[1].strip()

    root_dir = os.path.dirname(os.path.abspath(__file__))
    result_dir = os.path.join(root_dir, "Results")
    os.makedirs(result_dir, exist_ok=True)
    OUTPUT_Result_EXCEL_PATH = os.path.join(result_dir, os.path.basename(input_excel_path).replace(".xlsx", "_result_duration.xlsx"))  # 输出 Excel 路径
    OUTPUT_Check_EXCEL_PATH = os.path.join(result_dir, os.path.basename(input_excel_path).replace(".xlsx", "_check.xlsx"))  # 输出 Excel 路径

    # 执行精度检查
    df = get_check_result(OUTPUT_Result_EXCEL_PATH, OUTPUT_Check_EXCEL_PATH)
