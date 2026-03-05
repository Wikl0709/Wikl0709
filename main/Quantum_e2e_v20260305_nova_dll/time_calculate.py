
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
功能：
1) 读取 Excel 表
2) accuracy 列为 'xx/xx' 形式，累计分子与分母，计算总分与百分比
3) time 列为时间（支持 HH:MM:SS、MM:SS、SS、小数秒、Timedelta、Excel 时间戳），
   按 accuracy 的分母做加权，计算加权平均时间
4) 可选：将统计结果写回同一 Excel 的新工作表

使用方式：
- 直接在脚本顶部修改参数，然后运行：python calc_accuracy_time.py
"""

# ======= 可配置参数（在这里修改） =======
EXCEL_PATH = r"C:\Users\liuzm16\OneDrive - Lenovo\桌面\data.xlsx"          # Excel 文件路径（支持 .xlsx/.xls）
SHEET_NAME = 0                  # 工作表名；None 表示读取首个工作表
ACCURACY_COL = "accuracy"          # accuracy 列名（内容形如 'xx/xx'）
TIME_COL = "time"                  # time 列名（时间/秒）
WRITE_BACK_SUMMARY = False         # 是否将统计结果写回 Excel（仅支持 .xlsx）
SUMMARY_SHEET_NAME = "Summary"     # 写回时的工作表名
# ======================================

import re
from pathlib import Path

import numpy as np
import pandas as pd


def parse_accuracy(acc):
    """
    解析 'xx/xx' 字符串为 (num, den)。
    返回 (np.nan, np.nan) 表示无法解析。
    """
    if pd.isna(acc):
        return (np.nan, np.nan)
    s = str(acc).strip()
    m = re.match(r'^\s*(\d+)\s*/\s*(\d+)\s*$', s)
    if not m:
        return (np.nan, np.nan)
    num = int(m.group(1))
    den = int(m.group(2))
    return (num, den)


def timestamp_to_seconds(ts):
    """
    将 pandas.Timestamp（可能由 Excel 日期/时间解析而来）转换为“当日秒数”。
    例如 1900-01-01 00:01:30 -> 90 秒。
    """
    try:
        return (
            ts.hour * 3600
            + ts.minute * 60
            + ts.second
            + ts.microsecond / 1e6
        )
    except Exception:
        return np.nan


def parse_time_to_seconds(t):
    """
    将 time 列转换为秒（float）。
    支持：
    - 字符串：'HH:MM:SS', 'MM:SS', 'SS', '0:00:01.234' 等（交给 pandas.to_timedelta 处理）
    - 数值：直接视为秒
    - pandas.Timedelta：total_seconds()
    - pandas.Timestamp/Datetime：取当日秒数
    """
    if pd.isna(t):
        return np.nan

    # 数值直接当秒
    if isinstance(t, (int, float, np.number)):
        return float(t)

    # Timedelta
    if isinstance(t, pd.Timedelta):
        return t.total_seconds()

    # Timestamp（可能是 Excel 时间戳或日期时间）
    if isinstance(t, pd.Timestamp):
        return timestamp_to_seconds(t)

    # 其他类型转字符串，用 to_timedelta 尝试解析
    s = str(t).strip()
    if s == "":
        return np.nan

    # 优先尝试 to_timedelta（支持 'HH:MM:SS', 'MM:SS', 'SS', 'X days HH:MM:SS', '0:00:01.234' 等）
    try:
        td = pd.to_timedelta(s)
        return td.total_seconds()
    except Exception:
        pass

    # 尝试直接转为数字秒
    try:
        return float(s)
    except Exception:
        return np.nan


def format_seconds_to_hms(seconds):
    """
    将秒（float）格式化为 'HH:MM:SS.sss'（保留毫秒）。
    """
    if pd.isna(seconds):
        return "NaN"
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{sign}{h:02d}:{m:02d}:{s:06.3f}"  # SS.sss 保留 3 位小数


def read_excel(excel_path, sheet_name=None):
    """
    根据扩展名选择适当 engine 读取 Excel。
    """
    ext = Path(excel_path).suffix.lower()
    if ext == ".xlsx":
        return pd.read_excel(excel_path, sheet_name=sheet_name, engine="openpyxl")
    elif ext == ".xls":
        return pd.read_excel(excel_path, sheet_name=sheet_name, engine="xlrd")
    else:
        # 尝试默认引擎（可能仍能读）
        return pd.read_excel(excel_path, sheet_name=sheet_name)


def compute_statistics(df, accuracy_col, time_col):
    """
    执行计算：总分、百分比、加权平均时间（按分母加权）。
    返回字典结果。
    """
    # 列校验
    if accuracy_col not in df.columns:
        raise KeyError(f"找不到 accuracy 列：'{accuracy_col}'，现有列：{list(df.columns)}")
    if time_col not in df.columns:
        raise KeyError(f"找不到 time 列：'{time_col}'，现有列：{list(df.columns)}")

    # 解析 accuracy
    acc_pairs = df[accuracy_col].apply(parse_accuracy)
    df["__num"] = acc_pairs.apply(lambda x: x[0])
    df["__den"] = acc_pairs.apply(lambda x: x[1])

    # 累计分子与分母（忽略 NaN）
    total_num = pd.to_numeric(df["__num"], errors="coerce").sum(min_count=1)
    total_den = pd.to_numeric(df["__den"], errors="coerce").sum(min_count=1)

    # 计算百分比
    if pd.isna(total_num) or pd.isna(total_den) or total_den == 0:
        total_ratio = np.nan
        total_pct = np.nan
    else:
        total_ratio = total_num / total_den
        total_pct = total_ratio * 100.0

    # 解析 time 为秒，并按分母做加权平均
    df["__time_sec"] = df[time_col].apply(parse_time_to_seconds)

    # 只对有有效权重（分母 > 0）且时间不为 NaN 的行进行加权
    valid_mask = (~pd.isna(df["__time_sec"])) & (~pd.isna(df["__den"])) & (df["__den"] > 0)
    if valid_mask.any():
        w = df.loc[valid_mask, "__den"].astype(float)
        t = df.loc[valid_mask, "__time_sec"].astype(float)
        weighted_time_sec = (t * w).sum() / w.sum()
    else:
        weighted_time_sec = np.nan

    return {
        "total_num": int(total_num) if not pd.isna(total_num) else 0,
        "total_den": int(total_den) if not pd.isna(total_den) else 0,
        "total_ratio": float(total_ratio) if not pd.isna(total_ratio) else np.nan,
        "total_pct": float(total_pct) if not pd.isna(total_pct) else np.nan,
        "weighted_time_sec": float(weighted_time_sec) if not pd.isna(weighted_time_sec) else np.nan,
        "weighted_time_hms": format_seconds_to_hms(weighted_time_sec),
    }


def write_summary_to_excel(excel_path, summary_df, sheet_name="Summary"):
    """
    将 summary_df 写回到 Excel 的新工作表（仅支持 .xlsx）。
    如果工作表已存在，覆盖该工作表。
    """
    ext = Path(excel_path).suffix.lower()
    if ext != ".xlsx":
        print(f"[提示] 写回仅支持 .xlsx，当前为 {ext}，跳过写回。")
        return

    # 以追加模式写入并覆盖同名工作表
    with pd.ExcelWriter(excel_path, mode="a", engine="openpyxl", if_sheet_exists="replace") as writer:
        summary_df.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"[已写回] 统计结果写入工作表：{sheet_name}")


def main():
    # 读取数据
    df = read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)

    # 计算统计
    stats = compute_statistics(df, ACCURACY_COL, TIME_COL)

    # 输出结果
    print("=== 统计结果 ===")
    print(f"分子总和：{stats['total_num']}")
    print(f"分母总和：{stats['total_den']}")
    if np.isnan(stats["total_ratio"]):
        print("总分（分子/分母）：NaN")
        print("百分比：NaN")
    else:
        print(f"总分（分子/分母）：{stats['total_num']}/{stats['total_den']} = {stats['total_ratio']:.6f}")
        print(f"百分比：{stats['total_pct']:.3f}%")
    print(f"加权平均时间（按分母加权）：{stats['weighted_time_hms']}")
    if not np.isnan(stats["weighted_time_sec"]):
        print(f"(约 {stats['weighted_time_sec']:.6f} 秒)")

    # 写回（可选）
    if WRITE_BACK_SUMMARY:
        summary_df = pd.DataFrame([{
            "分子总和": stats["total_num"],
            "分母总和": stats["total_den"],
            "总分比值": stats["total_ratio"] if not np.isnan(stats["total_ratio"]) else None,
            "百分比(%)": stats["total_pct"] if not np.isnan(stats["total_pct"]) else None,
            "加权平均时间(秒)": stats["weighted_time_sec"] if not np.isnan(stats["weighted_time_sec"]) else None,
            "加权平均时间(HH:MM:SS.sss)": stats["weighted_time_hms"],
        }])
        write_summary_to_excel(EXCEL_PATH, summary_df, sheet_name=SUMMARY_SHEET_NAME)


if __name__ == "__main__":
    main()
