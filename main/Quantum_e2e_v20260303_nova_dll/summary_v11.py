# summary_v9.py
# -*- coding: utf-8 -*-
"""
功能：结果汇总与时间统计（含 timestatv2、E2E 指标、memory 注册成功率、failed_input_safety_count）

基于 summary_v8.py 的结构整理 + 新增指标：
新增（Conditional Pass Probability）：
- 在 PassRate 表格新增一列：P(Result=pass | RetrievalCheck=pass)
  * Memory：P(Result=pass | memoryRetrieval_check=pass)
  * KBQA：  P(Result=pass | kbRetrieval_check=pass)
  * 仅在 memory/kbqa 行（domain+secondary 以及 domain 汇总行）有值，其它行为空
  * 插入位置：Final_Answer 列之后、Result 列之前

1) PassRate 中 “final_answer_check” 重命名为 “Result”
2) Tool Calling/Retrieval 后插入 Final_Answer，并按规则填充，TOTAL 重聚合
3) Memory 行的 Tool Calling/Retrieval 用 memoryRetrieval_check，但分母剔除 Memory_reg_success == N
"""

from __future__ import annotations

import math
import sys
from typing import Tuple, Dict, List, Iterator, Any, Optional

import pandas as pd


# -------------------- Constants --------------------
DOMAIN_COL = "domain"
SECONDARY_COL = "secondary"

DOMAIN_CHECK_COL = "domain_check"         # pass/pass*/pass**/fail/(可能空)
MAPPING_CHECK_COL = "mapping_check"       # pass/pass*/fail/(可能空)
INTENT_CHECK_COL = "intent_check"         # pass/fail/(可能空)
SLOT_RESULT_COL = "slot_Result"           # pass/pass*/fail/(可能空)
TOOL_CHECK_COL = "tool_check"             # pass/fail/(可能空)

FINAL_ANSWER_COL = "Result"               # 输入明细表中的最终结果列（原始明细列名）
RAW_RESULT_COL = "result"                 # 用于 CTTVError 过滤

MEMORY_RETRIEVAL_CHECK_COL = "memoryRetrieval_check"
KB_RETRIEVAL_CHECK_COL = "kbRetrieval_check"
MEMORY_REG_SUCCESS_COL = "Memory_reg_success"

WARMUP_DOMAIN_VALUES = {"warm-up", "warmup", "warm up"}

TIME_COLS = [
    "DomainClassifierNode",
    "IntentMappingNode",
    "IntentUnderstandingNode",
    "TaskExecutionNode",
    "SearchMemory",
    "SearchKnowledge",
    "GeneralGenerationNode",
    "ttft",
    "response_time",
    "generation_speed",
]
NO_SCALE_TIME_COLS = {"ttft", "response_time", "generation_speed"}

SUMMARY_SHEET_NAME = "PassRate"
TIME_STATS_SHEET_NAME = "TimeStats"
TIME_STATS_V2_SHEET_NAME = "timestatv2"

PERCENT_DECIMALS = 1
TIME_DECIMALS = 2

EMPTY_STRINGS = {
    "", " ", "　", "nan", "NaN", "NAN", "none", "None", "NONE",
    "null", "Null", "NULL", "nil", "Nil", "NIL",
    "[]", "{}", "N/A", "n/a", "-", "--"
}

# 固定行顺序
DOMAIN_ORDER = [
    "general qa",
    "kbqa",
    "memory",
    "file search",
    "app control",
    "device setting",
]
SECONDARY_ORDER = {
    "app control": ["app_control_open_app", "app_control_close_app"],
    "device setting": ["device_slot", "device_w/o_slot"],
}

# 时间列对应的检查列（用于 v2 过滤）
TIME_TO_CHECK_COL_MAP: Dict[str, str] = {
    "DomainClassifierNode": DOMAIN_CHECK_COL,
    "IntentMappingNode": MAPPING_CHECK_COL,
    "IntentUnderstandingNode": INTENT_CHECK_COL,
    "TaskExecutionNode": TOOL_CHECK_COL,
    "ttft": FINAL_ANSWER_COL,
    "response_time": FINAL_ANSWER_COL,
}


# -------------------- Utils --------------------
def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str):
        s = val.strip()
        if s in EMPTY_STRINGS:
            return True
        s_unq = s.strip('"').strip("'")
        return s_unq in EMPTY_STRINGS
    return False


def _norm_str(val: Any) -> str:
    """去空白并转为小写，空值返回空串。"""
    if _is_empty(val):
        return ""
    return str(val).strip().lower()


def _trim_str(val: Any) -> str:
    """去空白，空值返回空串（大小写保持）。"""
    if _is_empty(val):
        return ""
    return str(val).strip()


def _fmt_rate(numer: int, denom: int, decimals: int = PERCENT_DECIMALS) -> str:
    pct = (numer / denom * 100.0) if denom > 0 else 0.0
    return f"{numer}/{denom} = {pct:.{decimals}f}%"


def _parse_xy(rate_str: str) -> Tuple[int, int]:
    """解析 'x/y = z%' -> (x,y)，失败返回 (0,0)"""
    s = (rate_str or "").strip()
    if not s:
        return 0, 0
    try:
        left = s.split("=", 1)[0].strip()  # 'x/y'
        x_str, y_str = left.split("/", 1)
        return int(x_str.strip()), int(y_str.strip())
    except Exception:
        return 0, 0


def _series_to_numeric_nonempty(series: pd.Series) -> pd.Series:
    """仅保留非空值并转为数字，无法转换的视为 NaN 并剔除。"""
    vals = series.apply(lambda x: None if _is_empty(x) else x)
    nums = pd.to_numeric(vals, errors="coerce")
    return nums.dropna()


def _to_numeric_keep_na(series: pd.Series) -> pd.Series:
    """把非空值转为数值，空或不可转为 NaN（不在此处 drop）。"""
    vals = series.apply(lambda x: None if _is_empty(x) else x)
    return pd.to_numeric(vals, errors="coerce")

def _safe_series(gdf: pd.DataFrame, col: str) -> pd.Series:
    """安全取列：若不存在则返回与 gdf 同索引、值为 None 的列"""
    if col in gdf.columns:
        return gdf[col]
    return pd.Series([None] * len(gdf), index=gdf.index)

def _ensure_columns(df: pd.DataFrame, cols: List[str], fill=None) -> pd.DataFrame:
    """若 df 缺列则以 fill 值补出同名列（原地修改并返回）"""
    for c in cols:
        if c not in df.columns:
            df[c] = fill
    return df

def ensure_norm_domain_secondary(df: pd.DataFrame) -> pd.DataFrame:
    """修剪 domain/secondary 的首尾空白（不改变大小写），并返回副本。"""
    out = df.copy()
    if DOMAIN_COL in out.columns:
        out[DOMAIN_COL] = out[DOMAIN_COL].apply(_trim_str)
    if SECONDARY_COL in out.columns:
        out[SECONDARY_COL] = out[SECONDARY_COL].apply(_trim_str)
    return out


# -------------------- Group Iteration --------------------
def iter_groups_by_domain_secondary(df: pd.DataFrame) -> Iterator[Tuple[str, str, str, pd.DataFrame]]:
    """
    先按 secondary 非空的 (domain+secondary) 分组；
    再按 secondary 为空的 domain 分组（保持与原脚本一致的口径）。
    产出: (GroupType, domain, secondary, group_df)
    """
    df_nonempty = df[df[SECONDARY_COL] != ""]
    if len(df_nonempty) > 0:
        for (dom, sec), g in df_nonempty.groupby([DOMAIN_COL, SECONDARY_COL], dropna=False):
            yield "domain+secondary", dom, sec, g

    df_empty = df[df[SECONDARY_COL] == ""]
    if len(df_empty) > 0:
        for dom, g in df_empty.groupby(DOMAIN_COL, dropna=False):
            yield "domain", dom, "", g


# -------------------- Pass-rate Counters --------------------
def _counts_domain(series: pd.Series) -> Tuple[int, int]:
    """(pass + pass* + pass**) / (pass + pass* + pass** + fail)，空白不计入分母"""
    vals = series.dropna().apply(_norm_str)
    p = int((vals == "pass").sum())
    ps = int((vals == "pass*").sum())
    pss = int((vals == "pass**").sum())
    f = int((vals == "fail").sum())
    numer = p + ps + pss
    denom = numer + f
    return numer, denom


def _counts_pass_fail(series: pd.Series) -> Tuple[int, int]:
    """通用口径：pass/(pass+fail)，忽略其他取值与空白。"""
    vals = series.dropna().apply(_norm_str)
    p = int((vals == "pass").sum())
    f = int((vals == "fail" ).sum())
    return p, p + f

def _counts_result(series: pd.Series) -> Tuple[int, int]:
    vals = series.dropna().apply(_norm_str)
    pass_like = {"pass", "1"}
    fail_like = {"fail", "0"}
    p = int(vals.isin(pass_like).sum())
    f = int(vals.isin(fail_like).sum())
    return p, p + f

def _filtered_slot_series(slot_series: pd.Series, intent_series: pd.Series) -> pd.Series:
    """intent==pass 且 slot 非空 的样本上评估 slot_Result。"""
    intent_vals = intent_series.dropna().apply(_norm_str)
    slot_vals_raw = slot_series.apply(lambda x: None if _is_empty(x) else x)
    slot_vals_raw = pd.Series(slot_vals_raw)

    common_idx = intent_vals.index.intersection(slot_vals_raw.index)
    intent_pass = (intent_vals == "pass").reindex(common_idx, fill_value=False)
    slot_nonempty = (~slot_vals_raw.reindex(common_idx).isna())

    mask = intent_pass & slot_nonempty
    filtered = slot_vals_raw.reindex(common_idx)[mask]
    return filtered.apply(_norm_str)


def _counts_slot_with_intent_filter(slot_series: pd.Series, intent_series: pd.Series) -> Tuple[int, int]:
    f = _filtered_slot_series(slot_series, intent_series)
    numer = int((f == "pass").sum())
    denom = int(len(f))
    return numer, denom


def _counts_slot_star_with_intent_filter(slot_series: pd.Series, intent_series: pd.Series) -> Tuple[int, int]:
    f = _filtered_slot_series(slot_series, intent_series)
    numer = int((f == "pass*").sum())
    denom = int(len(f))
    return numer, denom


def _compute_group_rates(gdf: pd.DataFrame) -> Dict[str, str]:
    d_n, d_d = _counts_domain(_safe_series(gdf, DOMAIN_CHECK_COL))
    m_n, m_d = _counts_pass_fail(_safe_series(gdf, MAPPING_CHECK_COL))
    i_n, i_d = _counts_pass_fail(_safe_series(gdf, INTENT_CHECK_COL))
    s_n, s_d = _counts_slot_with_intent_filter(
        _safe_series(gdf, SLOT_RESULT_COL),
        _safe_series(gdf, INTENT_CHECK_COL)
    )
    ss_n, ss_d = _counts_slot_star_with_intent_filter(
        _safe_series(gdf, SLOT_RESULT_COL),
        _safe_series(gdf, INTENT_CHECK_COL)
    )
    t_n, t_d = _counts_pass_fail(_safe_series(gdf, TOOL_CHECK_COL))
    fa_n, fa_d = _counts_result(_safe_series(gdf, FINAL_ANSWER_COL))
    out = {
        "domain_check": _fmt_rate(d_n, d_d),
        "mapping_check": _fmt_rate(m_n, m_d),
        "intent_check": _fmt_rate(i_n, i_d),
        "slot_check": _fmt_rate(s_n, s_d),
        "slot_star_check": _fmt_rate(ss_n, ss_d),
        "tool_check": _fmt_rate(t_n, t_d),
        "final_answer_check": _fmt_rate(fa_n, fa_d),
    }
    # 这两个列延续原来的“存在才计算”的策略
    if MEMORY_RETRIEVAL_CHECK_COL in gdf.columns:
        mr_n, mr_d = _counts_pass_fail(gdf[MEMORY_RETRIEVAL_CHECK_COL])
        out[MEMORY_RETRIEVAL_CHECK_COL] = _fmt_rate(mr_n, mr_d)
    else:
        out.setdefault(MEMORY_RETRIEVAL_CHECK_COL, "")
    if KB_RETRIEVAL_CHECK_COL in gdf.columns:
        kb_n, kb_d = _counts_pass_fail(gdf[KB_RETRIEVAL_CHECK_COL])
        out[KB_RETRIEVAL_CHECK_COL] = _fmt_rate(kb_n, kb_d)
    else:
        out.setdefault(KB_RETRIEVAL_CHECK_COL, "")
    return out


# -------------------- Time Stats --------------------
def _compute_group_time_avgs(gdf: pd.DataFrame) -> Dict[str, Any]:
    """原版：仅对非空值取平均；response_time/ttft/generation_speed 不缩放，其余毫秒→秒。"""
    out: Dict[str, Any] = {}
    for col in TIME_COLS:
        if col in gdf.columns:
            s = _series_to_numeric_nonempty(gdf[col])
            if len(s) > 0:
                factor = 1.0 if col in NO_SCALE_TIME_COLS else 0.001
                avg = float(s.mean()) * factor
                out[col] = round(avg, TIME_DECIMALS)
            else:
                out[col] = ""
        else:
            out[col] = ""
    return out


def _compute_group_time_avgs_v2(gdf: pd.DataFrame) -> Dict[str, Any]:
    """
    v2：若某时间列有对应检查列，则筛“检查列非 fail 且非空”后再计算 AVG/TP95/TP50；
    无对应检查列则按非空值计算。除 response_time/ttft/generation_speed 外，其余统一 ms→s。
    """
    out: Dict[str, Any] = {}
    for col in TIME_COLS:
        if col not in gdf.columns:
            out[col] = ""
            out[f"{col}_tp95"] = ""
            out[f"{col}_tp50"] = ""
            continue

        raw = _to_numeric_keep_na(gdf[col])

        if col in TIME_TO_CHECK_COL_MAP and TIME_TO_CHECK_COL_MAP[col] in gdf.columns:
            checks = gdf[TIME_TO_CHECK_COL_MAP[col]].apply(_norm_str)
            mask = (checks != "fail") & (checks != "0") & (checks != "")
            filtered = raw[mask].dropna()
        else:
            filtered = raw.dropna()

        if len(filtered) > 0:
            factor = 1.0 if col in NO_SCALE_TIME_COLS else 0.001
            avg = float(filtered.mean()) * factor
            p95 = float(filtered.quantile(0.95, interpolation="linear")) * factor
            p50 = float(filtered.quantile(0.5, interpolation="linear")) * factor
            out[col] = round(avg, TIME_DECIMALS)
            out[f"{col}_tp95"] = round(p95, TIME_DECIMALS)
            out[f"{col}_tp50"] = round(p50, TIME_DECIMALS)
        else:
            out[col] = ""
            out[f"{col}_tp95"] = ""
            out[f"{col}_tp50"] = ""
    return out


# -------------------- Sorting --------------------
def _sort_by_domain_secondary_order(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return df

    def to_pos(row):
        gt = str(row.get("GroupType", ""))
        d = _norm_str(row.get("domain", ""))
        s = _norm_str(row.get("secondary", ""))
        if gt in {"TOTAL", "TOTAL_AVG"}:
            return (len(DOMAIN_ORDER) + 1, 999, d, s)

        try:
            d_pos = DOMAIN_ORDER.index(d)
        except ValueError:
            d_pos = len(DOMAIN_ORDER)

        if d in SECONDARY_ORDER:
            sec_list = SECONDARY_ORDER[d]
            try:
                s_pos = sec_list.index(s)
            except ValueError:
                s_pos = len(sec_list)
        else:
            s_pos = 999

        return (d_pos, s_pos, d, s)

    temp = df.apply(to_pos, axis=1, result_type="expand")
    df = (
        df.assign(_k0=temp[0], _k1=temp[1], _k2=temp[2], _k3=temp[3])
        .sort_values(by=["_k0", "_k1", "_k2", "_k3"], kind="mergesort")
        .drop(columns=["_k0", "_k1", "_k2", "_k3"])
        .reset_index(drop=True)
    )
    return df


# -------------------- Builders --------------------
def read_excel(file_path: str, sheet_name=0) -> pd.DataFrame:
    lower = file_path.lower()
    if lower.endswith(".xlsx"):
        return pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
    if lower.endswith(".xls"):
        return pd.read_excel(file_path, sheet_name=sheet_name, engine="xlrd")
    return pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_norm_domain_secondary(df)
    rows: List[Dict[str, Any]] = []

    for gt, dom, sec, g in iter_groups_by_domain_secondary(df):
        rates = _compute_group_rates(g)
        rows.append({
            "GroupType": gt,
            "domain": dom,
            "secondary": sec,
            **rates,
        })

    out_df = pd.DataFrame(rows)
    out_df = _sort_by_domain_secondary_order(out_df)

    # TOTAL 行（基于全表）
    total_rows = len(df)
    d_n, d_d = _counts_domain(_safe_series(df, DOMAIN_CHECK_COL))
    m_n, m_d = _counts_pass_fail(_safe_series(df, MAPPING_CHECK_COL))
    i_n, i_d = _counts_pass_fail(_safe_series(df, INTENT_CHECK_COL))
    s_n, s_d = _counts_slot_with_intent_filter(
        _safe_series(df, SLOT_RESULT_COL),
        _safe_series(df, INTENT_CHECK_COL)
    )
    ss_n, ss_d = _counts_slot_star_with_intent_filter(
        _safe_series(df, SLOT_RESULT_COL),
        _safe_series(df, INTENT_CHECK_COL)
    )
    t_n, t_d = _counts_pass_fail(_safe_series(df, TOOL_CHECK_COL))
    fa_n, fa_d = _counts_result(_safe_series(df, FINAL_ANSWER_COL))

    total_row: Dict[str, Any] = {
        "GroupType": "TOTAL",
        "domain": "",
        "secondary": "",
        "domain_check": _fmt_rate(d_n, d_d),
        "mapping_check": _fmt_rate(m_n, m_d),
        "intent_check": _fmt_rate(i_n, i_d),
        "slot_check": _fmt_rate(s_n, s_d),
        "slot_star_check": _fmt_rate(ss_n, ss_d),
        "tool_check": _fmt_rate(t_n, t_d),
        "final_answer_check": _fmt_rate(fa_n, fa_d),
        "TOTAL_ROWS": total_rows,
    }

    if MEMORY_RETRIEVAL_CHECK_COL in df.columns:
        mr_n, mr_d = _counts_pass_fail(df[MEMORY_RETRIEVAL_CHECK_COL])
        total_row[MEMORY_RETRIEVAL_CHECK_COL] = _fmt_rate(mr_n, mr_d)
    else:
        total_row.setdefault(MEMORY_RETRIEVAL_CHECK_COL, "")

    if KB_RETRIEVAL_CHECK_COL in df.columns:
        kb_n, kb_d = _counts_pass_fail(df[KB_RETRIEVAL_CHECK_COL])
        total_row[KB_RETRIEVAL_CHECK_COL] = _fmt_rate(kb_n, kb_d)
    else:
        total_row.setdefault(KB_RETRIEVAL_CHECK_COL, "")

    out_df = pd.concat([out_df, pd.DataFrame([total_row])], ignore_index=True)
    return out_df


def build_time_stats(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_norm_domain_secondary(df)
    rows: List[Dict[str, Any]] = []

    for gt, dom, sec, g in iter_groups_by_domain_secondary(df):
        avgs = _compute_group_time_avgs(g)
        rows.append({"GroupType": gt, "domain": dom, "secondary": sec, **avgs})

    out_df = pd.DataFrame(rows)
    out_df = _sort_by_domain_secondary_order(out_df)

    overall = {"GroupType": "TOTAL_AVG", "domain": "", "secondary": ""}
    for col in TIME_COLS:
        if col in df.columns:
            s = _series_to_numeric_nonempty(df[col])
            if len(s) > 0:
                factor = 1.0 if col in NO_SCALE_TIME_COLS else 0.001
                avg = float(s.mean()) * factor
                overall[col] = round(avg, TIME_DECIMALS)
            else:
                overall[col] = ""
        else:
            overall[col] = ""

    out_df = pd.concat([out_df, pd.DataFrame([overall])], ignore_index=True)
    return out_df


def build_time_stats_v2(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_norm_domain_secondary(df)
    rows: List[Dict[str, Any]] = []

    for gt, dom, sec, g in iter_groups_by_domain_secondary(df):
        stats = _compute_group_time_avgs_v2(g)
        rows.append({"GroupType": gt, "domain": dom, "secondary": sec, **stats})

    out_df = pd.DataFrame(rows)
    out_df = _sort_by_domain_secondary_order(out_df)

    overall = {"GroupType": "TOTAL_AVG", "domain": "", "secondary": ""}
    overall_stats = _compute_group_time_avgs_v2(df)
    overall.update(overall_stats)

    out_df = pd.concat([out_df, pd.DataFrame([overall])], ignore_index=True)
    return out_df


# -------------------- Memory Tool Calling Special Rate (exclude Memory_reg_success == N) --------------------
def compute_memory_tool_calling_rate_map(df_clean: pd.DataFrame) -> Dict[Tuple[str, str], str]:
    """
    Memory 行的 Tool Calling/Retrieval 口径：
    - 使用 memoryRetrieval_check 统计 pass/(pass+fail)
    - 但分母剔除 Memory_reg_success == 'n' 的样本
    输出：
      ("memory", secondary_norm) -> rate
      ("memory", "__DOMAIN__") -> domain 聚合 rate
    """
    out: Dict[Tuple[str, str], str] = {}
    required = {DOMAIN_COL, SECONDARY_COL, MEMORY_RETRIEVAL_CHECK_COL, MEMORY_REG_SUCCESS_COL}
    if not required.issubset(df_clean.columns):
        return out

    tmp = df_clean.copy()
    tmp["_domain_norm"] = tmp[DOMAIN_COL].apply(_norm_str)
    tmp["_secondary_norm"] = tmp[SECONDARY_COL].apply(_norm_str)

    is_memory = tmp["_domain_norm"] == "memory"
    reg_is_n = tmp[MEMORY_REG_SUCCESS_COL].apply(_norm_str) == "n"
    scope = tmp[is_memory & (~reg_is_n)]

    def _count_pf(series: pd.Series) -> Tuple[int, int]:
        v = series.dropna().apply(_norm_str)
        p = int((v == "pass").sum())
        f = int((v == "fail").sum())
        return p, p + f

    if len(scope) == 0:
        out[("memory", "__DOMAIN__")] = _fmt_rate(0, 0)
        return out

    for (dn, sn), g in scope.groupby(["_domain_norm", "_secondary_norm"], dropna=False):
        p, d = _count_pf(g[MEMORY_RETRIEVAL_CHECK_COL])
        out[(dn, sn)] = _fmt_rate(p, d)

    p_all, d_all = _count_pf(scope[MEMORY_RETRIEVAL_CHECK_COL])
    out[("memory", "__DOMAIN__")] = _fmt_rate(p_all, d_all)
    return out


# -------------------- PassRate Post-process --------------------
def _postprocess_passrate_df(summary_df: pd.DataFrame, df_clean: pd.DataFrame) -> pd.DataFrame:
    """
    - 用 memory/kb 的检索列替换对应行的 tool_check
      * Memory：Tool Calling/Retrieval 采用 memoryRetrieval_check，但分母剔除 Memory_reg_success==N
      * KBQA：Tool Calling/Retrieval 采用 kbRetrieval_check
    - 基于替换后的行重算 TOTAL 的 tool_check（避免重复计数）
    - 重命名表头；删除 memory/kb 检索列与 TOTAL_ROWS；将 slot_star_check 移到最后
    """
    mem_tool_map = compute_memory_tool_calling_rate_map(df_clean)

    # 1) 替换 Memory/KBQA 行的 tool_check
    if "tool_check" in summary_df.columns:
        domain_norm = summary_df["domain"].apply(_norm_str)
        sec_norm = summary_df["secondary"].apply(_norm_str)

        # Memory：用 mem_tool_map 覆盖
        mask_mem = (domain_norm == "memory") & (summary_df["GroupType"] != "TOTAL")
        if mask_mem.any():
            mask_mem_ds = mask_mem & (summary_df["GroupType"] == "domain+secondary")
            for idx in summary_df.index[mask_mem_ds]:
                key = ("memory", sec_norm.loc[idx])
                summary_df.at[idx, "tool_check"] = mem_tool_map.get(key, "")

            mask_mem_d = mask_mem & (summary_df["GroupType"] == "domain")
            for idx in summary_df.index[mask_mem_d]:
                summary_df.at[idx, "tool_check"] = mem_tool_map.get(("memory", "__DOMAIN__"), "")

        # KBQA：直接用 kbRetrieval_check 替换
        if KB_RETRIEVAL_CHECK_COL in summary_df.columns:
            mask_kb = (domain_norm == "kbqa") & (summary_df["GroupType"] != "TOTAL")
            summary_df.loc[mask_kb, "tool_check"] = summary_df.loc[mask_kb, KB_RETRIEVAL_CHECK_COL]

    # 2) 重算 TOTAL 的 tool_check（聚合 domain+secondary 行 + 纯 domain 且该 domain 未出现在前者中）
    df_tmp = summary_df.copy()
    dom_with_sec = set(df_tmp.loc[df_tmp["GroupType"] == "domain+secondary", "domain"].apply(_norm_str))
    agg_mask = (
        (df_tmp["GroupType"] == "domain+secondary") |
        ((df_tmp["GroupType"] == "domain") & (~df_tmp["domain"].apply(_norm_str).isin(dom_with_sec)))
    )
    agg_rows = df_tmp[agg_mask & (df_tmp["GroupType"] != "TOTAL")]
    if "tool_check" in agg_rows.columns and len(agg_rows) > 0:
        total_numer, total_denom = 0, 0
        for val in agg_rows["tool_check"].fillna(""):
            n, d = _parse_xy(str(val))
            total_numer += n
            total_denom += d
        summary_df.loc[summary_df["GroupType"] == "TOTAL", "tool_check"] = _fmt_rate(total_numer, total_denom)

    # 3) 表头重命名（关键：final_answer_check -> Result）
    rename_map = {
        "domain_check": "Domain Classification",
        "mapping_check": "Intent Mapping",
        "intent_check": "Intent Classification",
        "slot_check": "Slot Filling",
        "tool_check": "Tool Calling/Retrieval",
        "final_answer_check": "Result",
    }
    summary_df = summary_df.rename(columns=rename_map)

    # 4) 删除指定列
    for col in [MEMORY_RETRIEVAL_CHECK_COL, KB_RETRIEVAL_CHECK_COL, "TOTAL_ROWS"]:
        if col in summary_df.columns:
            summary_df = summary_df.drop(columns=[col])

    # 5) 将 slot_star_check 列移动到最后（若存在）
    cols = list(summary_df.columns)
    if "slot_star_check" in cols:
        cols = [c for c in cols if c != "slot_star_check"] + ["slot_star_check"]
        summary_df = summary_df[cols]

    return summary_df


# -------------------- Extra Metrics: E2E --------------------
def compute_e2e_scope_map(df_clean: pd.DataFrame) -> Dict[Tuple[str, str], str]:
    """仅对 open_app/close_app/device_slot 计算 E2E_scope（分母=Result 的 pass+fail；分子=slot 与 tool 同时 pass）。"""
    allowed_pairs = {
        ("app control", "app_control_open_app"),
        ("app control", "app_control_close_app"),
        ("device setting", "device_slot"),
    }
    e2e_map: Dict[Tuple[str, str], str] = {}
    if len(df_clean) == 0:
        return e2e_map

    grp = df_clean.groupby([DOMAIN_COL, SECONDARY_COL], dropna=False)
    for (dom, sec), gdf in grp:
        dnorm = _norm_str(dom)
        snorm = _norm_str(sec)
        if (dnorm, snorm) not in allowed_pairs:
            continue

        vals_fa = gdf[FINAL_ANSWER_COL].apply(_norm_str)
        denom = int(((vals_fa == "pass") | (vals_fa == "fail")).sum())

        intent_vals = gdf[INTENT_CHECK_COL].apply(_norm_str)
        slot_raw = gdf[SLOT_RESULT_COL]
        slot_nonempty = ~slot_raw.apply(_is_empty)
        slot_vals = slot_raw.apply(_norm_str)

        cond_slot_pass = (intent_vals == "pass") & slot_nonempty & (slot_vals == "pass")
        cond_tool_pass = (gdf[TOOL_CHECK_COL].apply(_norm_str) == "pass")

        numer = int((cond_slot_pass & cond_tool_pass).sum())
        e2e_map[(dnorm, snorm)] = _fmt_rate(numer, denom)

    return e2e_map


def compute_memory_e2e_map(df_clean: pd.DataFrame) -> Dict[Tuple[str, str], str]:
    """
    Memory 的 E2E_scope：
    分母：domain=memory 且 Memory_reg_success=='y' 的全部样本
    分子：在上述分母范围内，Result ∈ {1, pass, true} 的样本计数
    """
    mem_e2e_map: Dict[Tuple[str, str], str] = {}
    required = {DOMAIN_COL, SECONDARY_COL, MEMORY_REG_SUCCESS_COL, FINAL_ANSWER_COL}
    if not required.issubset(df_clean.columns):
        return mem_e2e_map

    dfm = df_clean.copy()
    dfm["_domain_norm"] = dfm[DOMAIN_COL].apply(_norm_str)
    dfm["_secondary_norm"] = dfm[SECONDARY_COL].apply(_norm_str)

    is_memory = dfm["_domain_norm"] == "memory"
    memreg_y = dfm[MEMORY_REG_SUCCESS_COL].apply(_norm_str) == "y"
    fa_vals = dfm[FINAL_ANSWER_COL].apply(_norm_str)
    cond_pass = (fa_vals.isin({"1", "pass", "true"}))

    scope = dfm[is_memory & memreg_y]
    if len(scope) == 0:
        mem_e2e_map[("memory", "__DOMAIN__")] = _fmt_rate(0, 0)
        return mem_e2e_map

    grp_total = scope.groupby(["_domain_norm", "_secondary_norm"], dropna=False).size().to_dict()
    grp_num = scope[cond_pass.reindex(scope.index, fill_value=False)].groupby(
        ["_domain_norm", "_secondary_norm"], dropna=False
    ).size().to_dict()

    for k, denom in grp_total.items():
        numer = int(grp_num.get(k, 0))
        mem_e2e_map[k] = _fmt_rate(numer, int(denom))

    mem_e2e_map[("memory", "__DOMAIN__")] = _fmt_rate(int(cond_pass.reindex(scope.index, fill_value=False).sum()), int(len(scope)))
    return mem_e2e_map


def attach_e2e_scope(summary_df: pd.DataFrame, df_clean: pd.DataFrame) -> pd.DataFrame:
    e2e_map = compute_e2e_scope_map(df_clean)
    mem_e2e_map = compute_memory_e2e_map(df_clean)

    def _fill(row) -> str:
        gt = row.get("GroupType")
        dnorm = _norm_str(row.get("domain", ""))
        snorm = _norm_str(row.get("secondary", ""))

        if gt == "domain+secondary":
            v = e2e_map.get((dnorm, snorm), "")
            if v:
                return v

        if dnorm == "memory":
            if gt == "domain+secondary":
                return mem_e2e_map.get((dnorm, snorm), "")
            if gt == "domain":
                return mem_e2e_map.get(("memory", "__DOMAIN__"), "")
        return ""

    summary_df["E2E_scope"] = summary_df.apply(_fill, axis=1)
    return summary_df


# -------------------- Extra Metrics: Memory reg success rate --------------------
def compute_memory_reg_success_maps(df_full: pd.DataFrame) -> Dict[str, Any]:
    """
    在未剔除 CTTVError 的原始 df 上，统计 Memory_reg_success=='y' 的比例（用于展示，不影响 tool 口径）。
    """
    res = {
        "available": (MEMORY_REG_SUCCESS_COL in df_full.columns),
        "total_all": (0, 0),
        "by_domain": {},
        "by_pair": {},
    }
    if not res["available"]:
        return res

    tmp = df_full.copy()
    tmp["_domain_norm"] = tmp[DOMAIN_COL].apply(_norm_str)
    tmp["_secondary_norm"] = tmp[SECONDARY_COL].apply(_norm_str)

    is_mem = tmp["_domain_norm"] == "memory"
    mem_success = tmp[MEMORY_REG_SUCCESS_COL].apply(_norm_str) == "y"

    y_all = int((is_mem & mem_success).sum())
    t_all = int(is_mem.sum())

    res["total_all"] = (y_all, t_all)
    res["by_domain"]["memory"] = (y_all, t_all)

    grp_all = tmp[is_mem].groupby(["_domain_norm", "_secondary_norm"], dropna=False).size().to_dict()
    grp_y = tmp[is_mem & mem_success].groupby(["_domain_norm", "_secondary_norm"], dropna=False).size().to_dict()

    for k, total in grp_all.items():
        y = int(grp_y.get(k, 0))
        res["by_pair"][k] = (y, int(total))

    return res


def attach_memory_reg_success_rate(summary_df: pd.DataFrame, mem_maps: Dict[str, Any]) -> pd.DataFrame:
    def _map_rate(row) -> str:
        if not mem_maps.get("available", False):
            return ""
        gt = row.get("GroupType")
        dnorm = _norm_str(row.get("domain", ""))
        if dnorm != "memory":
            return ""

        if gt == "TOTAL":
            y, t = mem_maps["total_all"]
            return _fmt_rate(int(y), int(t))

        if gt == "domain+secondary":
            snorm = _norm_str(row.get("secondary", ""))
            y, t = mem_maps["by_pair"].get((dnorm, snorm), (0, 0))
            return _fmt_rate(int(y), int(t))

        y, t = mem_maps["by_domain"].get(dnorm, (0, 0))
        return _fmt_rate(int(y), int(t))

    summary_df["memory_reg_success_rate"] = summary_df.apply(_map_rate, axis=1)
    return summary_df


# -------------------- Excluded (CTTVError) Counting --------------------
def compute_excluded_counts(df_full: pd.DataFrame, result_col: str, prefix: str = "CTTVError: Task failed") -> Dict[str, Any]:
    result_as_str = df_full[result_col].astype(str)
    mask_exclude = result_as_str.str.startswith(prefix, na=False)

    excluded_dom = df_full.loc[mask_exclude, DOMAIN_COL].apply(lambda x: "" if _is_empty(x) else str(x).strip())
    excluded_dom_norm = excluded_dom.str.lower()
    by_domain = excluded_dom_norm.value_counts().to_dict()

    pair_df = df_full.loc[mask_exclude, [DOMAIN_COL, SECONDARY_COL]].copy()
    pair_df["domain_norm"] = pair_df[DOMAIN_COL].apply(_norm_str)
    pair_df["secondary_norm"] = pair_df[SECONDARY_COL].apply(_norm_str)
    by_pair = pair_df.groupby(["domain_norm", "secondary_norm"]).size().to_dict() if len(pair_df) > 0 else {}

    total_count = int(mask_exclude.sum())
    return {
        "mask_exclude": mask_exclude,
        "by_domain": by_domain,
        "by_pair": by_pair,
        "total": total_count,
    }


def attach_failed_input_safety_count(summary_df: pd.DataFrame, excluded: Dict[str, Any]) -> pd.DataFrame:
    def _map(row) -> int:
        gt = row.get("GroupType")
        if gt == "TOTAL":
            return int(excluded["total"])
        dnorm = _norm_str(row.get("domain", ""))
        if gt == "domain+secondary":
            snorm = _norm_str(row.get("secondary", ""))
            return int(excluded["by_pair"].get((dnorm, snorm), 0))
        return int(excluded["by_domain"].get(dnorm, 0))

    summary_df["failed_input_safety_count"] = summary_df.apply(_map, axis=1)
    return summary_df


# -------------------- Final_Answer column + TOTAL recompute --------------------
def _attach_final_answer_column_and_recalc_total(summary_df: pd.DataFrame) -> pd.DataFrame:
    """
    在 PassRate 输出中：
    1) 在 Tool Calling/Retrieval 之后插入 Final_Answer 列
    2) 填充规则：
       - domain in {general qa, kbqa, file search} -> Result
       - memory -> E2E_scope
       - app control (open/close) -> E2E_scope
       - device setting (device_slot) -> E2E_scope
       - device setting (device_w/o_slot) -> Tool Calling/Retrieval
    3) TOTAL 行：按原聚合口径（避免重复计数）对 Final_Answer 重新汇总 x/y
    """
    needed_cols = {"domain", "secondary", "GroupType", "Tool Calling/Retrieval", "Result", "E2E_scope"}
    if not needed_cols.issubset(set(summary_df.columns)):
        return summary_df

    def pick_final_answer(row) -> str:
        gt = row.get("GroupType")
        if gt == "TOTAL":
            return ""
        dnorm = _norm_str(row.get("domain", ""))
        snorm = _norm_str(row.get("secondary", ""))

        if dnorm in {"general qa", "kbqa", "file search"}:
            return str(row.get("Result", "") or "")
        if dnorm == "memory":
            return str(row.get("E2E_scope", "") or "")
        if dnorm == "app control" and snorm in {"app_control_open_app", "app_control_close_app"}:
            return str(row.get("E2E_scope", "") or "")
        if dnorm == "device setting" and snorm == "device_slot":
            return str(row.get("E2E_scope", "") or "")
        if dnorm == "device setting" and snorm == "device_w/o_slot":
            return str(row.get("Tool Calling/Retrieval", "") or "")
        return ""

    final_series = summary_df.apply(pick_final_answer, axis=1)

    cols = list(summary_df.columns)
    if "Final_Answer" in cols:
        summary_df["Final_Answer"] = final_series
    else:
        try:
            insert_at = cols.index("Tool Calling/Retrieval") + 1
        except ValueError:
            insert_at = len(cols)
        summary_df.insert(insert_at, "Final_Answer", final_series)

    # 重算 TOTAL 的 Final_Answer
    df_tmp = summary_df.copy()
    dom_with_sec = set(df_tmp.loc[df_tmp["GroupType"] == "domain+secondary", "domain"].apply(_norm_str))
    agg_mask = (
        (df_tmp["GroupType"] == "domain+secondary") |
        ((df_tmp["GroupType"] == "domain") & (~df_tmp["domain"].apply(_norm_str).isin(dom_with_sec)))
    )
    agg_rows = df_tmp[agg_mask & (df_tmp["GroupType"] != "TOTAL")]

    total_numer, total_denom = 0, 0
    for val in agg_rows["Final_Answer"].fillna(""):
        n, d = _parse_xy(str(val))
        total_numer += n
        total_denom += d

    summary_df.loc[summary_df["GroupType"] == "TOTAL", "Final_Answer"] = _fmt_rate(total_numer, total_denom)
    return summary_df


# -------------------- NEW: Conditional Probability Column --------------------
def compute_retrieval_pass_then_result_pass_map(df_clean: pd.DataFrame) -> Dict[Tuple[str, str, str], str]:
    """
    计算条件概率并返回映射：
      key = (domain_norm, group_level, secondary_norm)
      - group_level: "pair" (domain+secondary) 或 "domain" (secondary 为空的 domain 汇总口径)
      value = "x/y = z%"

    只计算：
      - memory: P(Result=pass | memoryRetrieval_check=pass)
      - kbqa:  P(Result=pass | kbRetrieval_check=pass)
    """
    required_base = {DOMAIN_COL, SECONDARY_COL, FINAL_ANSWER_COL}
    if not required_base.issubset(df_clean.columns):
        return {}

    dfc = df_clean.copy()
    dfc["_domain_norm"] = dfc[DOMAIN_COL].apply(_norm_str)
    dfc["_secondary_norm"] = dfc[SECONDARY_COL].apply(_norm_str)
    dfc["_result_norm"] = dfc[FINAL_ANSWER_COL].apply(_norm_str)

    out: Dict[Tuple[str, str, str], str] = {}

    def _calc(scope: pd.DataFrame, retrieval_col: str) -> str:
        if retrieval_col not in scope.columns:
            return ""
        r = scope[retrieval_col].apply(_norm_str)
        cond = (r == "pass")
        denom = int(cond.sum())
        if denom == 0:
            return _fmt_rate(0, 0)
        numer = int((cond & (scope["_result_norm"] == "pass")).sum())
        return _fmt_rate(numer, denom)

    # memory - pair
    mem = dfc[dfc["_domain_norm"] == "memory"]
    if len(mem) > 0:
        for sec, g in mem.groupby("_secondary_norm", dropna=False):
            out[("memory", "pair", sec)] = _calc(g, MEMORY_RETRIEVAL_CHECK_COL)
        # memory - domain (secondary 空)
        out[("memory", "domain", "")] = _calc(mem[mem["_secondary_norm"] == ""], MEMORY_RETRIEVAL_CHECK_COL)

    # kbqa - pair
    kb = dfc[dfc["_domain_norm"] == "kbqa"]
    if len(kb) > 0:
        for sec, g in kb.groupby("_secondary_norm", dropna=False):
            out[("kbqa", "pair", sec)] = _calc(g, KB_RETRIEVAL_CHECK_COL)
        # kbqa - domain (secondary 空)
        out[("kbqa", "domain", "")] = _calc(kb[kb["_secondary_norm"] == ""], KB_RETRIEVAL_CHECK_COL)

    return out


def attach_conditional_prob_column(summary_df: pd.DataFrame, df_clean: pd.DataFrame) -> pd.DataFrame:
    """
    在 PassRate 表插入新列：
      P(Result=pass | RetrievalCheck=pass)
    仅在 memory/kbqa 行填值。
    插入位置：Final_Answer 之后、Result 之前（若 Result 不存在则放在 Final_Answer 后）。
    """
    needed_summary = {"domain", "secondary", "GroupType", "Final_Answer"}
    if not needed_summary.issubset(set(summary_df.columns)):
        return summary_df

    prob_map = compute_retrieval_pass_then_result_pass_map(df_clean)
    col_name = "P(Result=pass | RetrievalCheck=pass)"

    def _fill(row) -> str:
        gt = row.get("GroupType")
        if gt == "TOTAL":
            return ""
        dnorm = _norm_str(row.get("domain", ""))
        snorm = _norm_str(row.get("secondary", ""))

        if dnorm not in {"memory", "kbqa"}:
            return ""

        if gt == "domain+secondary":
            return prob_map.get((dnorm, "pair", snorm), "")
        if gt == "domain":
            return prob_map.get((dnorm, "domain", ""), "")
        return ""

    new_series = summary_df.apply(_fill, axis=1)

    # 如果已存在则覆盖
    if col_name in summary_df.columns:
        summary_df[col_name] = new_series
        return summary_df

    cols = list(summary_df.columns)

    # 插入位置：Final_Answer 后，且尽量放到 Result 前
    try:
        idx_final = cols.index("Final_Answer")
    except ValueError:
        idx_final = None

    try:
        idx_result = cols.index("Result")
    except ValueError:
        idx_result = None

    if idx_result is not None:
        insert_at = idx_result  # 直接插到 Result 前
    elif idx_final is not None:
        insert_at = idx_final + 1
    else:
        insert_at = len(cols)

    summary_df.insert(insert_at, col_name, new_series)
    return summary_df


# -------------------- Pipeline --------------------
def summarize(
    in_path: str,
    out_path: str,
    sheet_name=0,
    log: bool = False
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = read_excel(in_path, sheet_name=sheet_name)

    required_cols = [
        DOMAIN_COL, SECONDARY_COL,
        DOMAIN_CHECK_COL, MAPPING_CHECK_COL, INTENT_CHECK_COL,
        SLOT_RESULT_COL, TOOL_CHECK_COL, FINAL_ANSWER_COL,
        RAW_RESULT_COL,
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing and log:
        print(f"[Warning] 输入表缺少列：{missing}；将以空值补列后继续计算。")
    # 以 None 补出缺失列，保证后续统计不因 KeyError 终止
    for c in missing:
        df[c] = None


    # --- 剔除 Warm-up ---
    before_n = len(df)
    dom_norm = df[DOMAIN_COL].apply(_norm_str)
    df = df.loc[~dom_norm.isin(WARMUP_DOMAIN_VALUES)].copy()
    if log:
        print(f"[PreFilter] drop Warm-up rows: {before_n - len(df)} (remain {len(df)})")

    # 1) 过滤 CTTVError
    excluded = compute_excluded_counts(df, result_col=RAW_RESULT_COL, prefix="CTTVError: Task failed")
    mask_exclude = excluded["mask_exclude"]

    # 2) memory 注册成功率（基于原始 df）
    mem_maps = compute_memory_reg_success_maps(df)

    # 3) 基于剔除后的 df_clean 统计
    df_clean = df.loc[~mask_exclude].copy()

    summary_df = build_summary(df_clean)

    # ★ v8 的 postprocess：替换 Memory/KBQA 的 Tool Calling/Retrieval + 重算 TOTAL + 列名重命名等
    summary_df = _postprocess_passrate_df(summary_df, df_clean)

    time_stats_df = build_time_stats(df_clean)
    time_stats_v2_df = build_time_stats_v2(df_clean)

    # 4) E2E_scope
    summary_df = attach_e2e_scope(summary_df, df_clean)

    # 5) memory_reg_success_rate
    summary_df = attach_memory_reg_success_rate(summary_df, mem_maps)

    # 6) failed_input_safety_count
    summary_df = attach_failed_input_safety_count(summary_df, excluded)

    # 7) Final_Answer（依赖 E2E_scope / Tool Calling/Retrieval / Result）
    summary_df = _attach_final_answer_column_and_recalc_total(summary_df)

    # 8) NEW：条件概率列（插在 Final_Answer 后，Result 前）
    summary_df = attach_conditional_prob_column(summary_df, df_clean)

    # 9) 写 Excel
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name=SUMMARY_SHEET_NAME)
        time_stats_df.to_excel(writer, index=False, sheet_name=TIME_STATS_SHEET_NAME)
        time_stats_v2_df.to_excel(writer, index=False, sheet_name=TIME_STATS_V2_SHEET_NAME)

    if log:
        print("已写出三张表到：", out_path)
        print(f"被过滤（failed_input_safety）样本总数：{int(excluded['total'])}")
        print(f"Summary 行数（含 TOTAL 行）：{len(summary_df)}")
        print(summary_df.head(12).to_string(index=False))

    return summary_df, time_stats_df


# -------------------- CLI --------------------
if __name__ == "__main__":
    # 用法：python summary_v9.py <输入Excel> <输出Excel> [sheet_name]
    in_path = r"D:\4_local_solution\20260128_zhaojia\Results_20260129_175323\test_results_local_solution_case_EN_0127_NV_Auto_Judge_Final.xlsx"
    out_path = r"D:\4_local_solution\20260128_zhaojia\Results_20260129_175323\test_results_local_solution_case_EN_0127_NV_Auto_Judge_Final_s22.xlsx"
    sheet_name = 0

    if len(sys.argv) >= 3:
        in_path = sys.argv[1].strip()
        out_path = sys.argv[2].strip()
        if len(sys.argv) >= 4 and sys.argv[3].strip():
            try:
                sheet_name = int(sys.argv[3].strip())
            except ValueError:
                sheet_name = sys.argv[3].strip()

    if not in_path or not out_path:
        print("用法：python summary_v9.py <输入Excel> <输出Excel> [sheet_name]")
        sys.exit(1)

    summarize(in_path, out_path, sheet_name=sheet_name, log=True)