import argparse
import os
import re
from datetime import datetime
from typing import Optional, Tuple
import pandas as pd


ROW_CONFIGS = [
    # POD 28 Orchestration
    dict(
        pod="POD 28 Orchestration",
        feature_left="General QA",
        feature_right="",
        domain="General QA",
        secondary=None,
    ),
    # POD10 Fused Knowledge
    dict(
        pod="POD10 Fused Knowledge",
        feature_left="KBQA",
        feature_right="",
        domain="KBQA",
        secondary=None,
    ),
    dict(
        pod="POD10 Fused Knowledge",
        feature_left="Memory QA",
        feature_right="",
        domain="Memory",
        secondary=None,
    ),
    # POD1 Local Agent
    dict(
        pod="POD1 Local Agent",
        feature_left="File Search",
        feature_right="",
        domain="File Search",
        secondary=None,
    ),
    dict(
        pod="POD1 Local Agent",
        feature_left="App Control",
        feature_right="Open App",
        domain="App Control",
        secondary="app_control_open_app",
    ),
    dict(
        pod="POD1 Local Agent",
        feature_left="App Control",
        feature_right="Close App",
        domain="App Control",
        secondary="app_control_close_app",
    ),
    dict(
        pod="POD1 Local Agent",
        feature_left="Device Setting",
        feature_right="Slotting",
        domain="Device setting",
        secondary="device_slot",
    ),
    dict(
        pod="POD1 Local Agent",
        feature_left="Device Setting",
        feature_right="No-Slotting",
        domain="Device setting",
        secondary="device_w/o_slot",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从本地 Excel 结果文件生成统计表。"
    )
    parser.add_argument(
        "--file",
        default=(
            r"C:\Users\weiyb2\Downloads\temp\20260226"
            r"\test_results_local_solution_case_EN_0127_NV_Auto_Judge_Final_summary.xlsx"
        ),
        help="输入的 Excel 文件路径（包含 PassRate 与 timestatv2 两个 sheet）。",
    )
    parser.add_argument(
        "--output",
        default="summary.xlsx",
        help="输出汇总结果 Excel 的基础名（实际会自动加时间戳后缀）。",
    )
    return parser.parse_args()


def _filter_by_domain_secondary(
    df: pd.DataFrame, domain: str, secondary: Optional[str]
) -> pd.DataFrame:
    dom_series = df["domain"].astype(str).str.strip()
    cond = dom_series == domain
    if secondary is None:
        return df[cond]
    sec_series = df["secondary"].astype(str).str.strip()
    return df[cond & (sec_series == secondary)]


def _parse_final_answer_percent(value: str) -> Optional[float]:
    """
    解析 PassRate 里 Final_Answer 文本，例如：
    - '41/53 = 77.4%' -> 77.4
    - '41/53' -> 77.4
    """
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return None

    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", value)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass

    frac = re.search(r"(\d+)\s*/\s*(\d+)", value)
    if frac:
        num = int(frac.group(1))
        den = int(frac.group(2))
        if den != 0:
            return num / den * 100.0

    return None


def calc_success_rate(
    passrate_df: pd.DataFrame, domain: str, secondary: Optional[str]
) -> Optional[float]:
    sub = _filter_by_domain_secondary(passrate_df, domain, secondary)
    if sub.empty:
        return None
    val = sub.iloc[0]["Final_Answer"]
    return _parse_final_answer_percent(str(val))


def calc_ttft(
    timestat_df: pd.DataFrame, domain: str, secondary: Optional[str]
) -> Tuple[Optional[float], Optional[float]]:
    sub = _filter_by_domain_secondary(timestat_df, domain, secondary)
    if sub.empty:
        return None, None

    tp50 = pd.to_numeric(sub["ttft_tp50"], errors="coerce").dropna()
    tp95 = pd.to_numeric(sub["ttft_tp95"], errors="coerce").dropna()
    if tp50.empty or tp95.empty:
        return None, None
    return float(tp50.mean()), float(tp95.mean())


def build_summary_table(
    passrate_df: pd.DataFrame, timestat_df: pd.DataFrame
) -> pd.DataFrame:
    """根据 PassRate 与 timestatv2 生成最终的数据行。"""
    rows = []

    for cfg in ROW_CONFIGS:
        success = calc_success_rate(
            passrate_df, cfg["domain"], cfg["secondary"]
        )
        tp50, tp95 = calc_ttft(
            timestat_df, cfg["domain"], cfg["secondary"]
        )

        success_str = f"{success:.0f}%" if success is not None else ""
        ttft_str = (
            f"{tp50:.2f} / {tp95:.2f}"
            if tp50 is not None and tp95 is not None
            else ""
        )

        rows.append(
            {
                "POD": cfg["pod"],
                "Feature_left": cfg["feature_left"],
                "Feature_right": cfg["feature_right"],
                "Metric": "Accuracy",
                "": success_str,
            }
        )
        rows.append(
            {
                "POD": cfg["pod"],
                "Feature_left": cfg["feature_left"],
                "Feature_right": cfg["feature_right"],
                "Metric": "TTFT (Median/P95, s)",
                "": ttft_str,
            }
        )

    return pd.DataFrame(rows)


def _merge_same_blocks(
    ws, col_letter: str, start_row: int, values: pd.Series
) -> None:
    """将一列中连续相同的非空值纵向合并。"""
    if values.empty:
        return

    current = values.iloc[0]
    block_start = start_row

    for i in range(1, len(values)):
        v = values.iloc[i]
        if v != current:
            block_end = start_row + i - 1
            if block_end > block_start and current != "":
                ws.merge_cells(f"{col_letter}{block_start}:{col_letter}{block_end}")
            current = v
            block_start = start_row + i

    block_end = start_row + len(values) - 1
    if block_end > block_start and current != "":
        ws.merge_cells(f"{col_letter}{block_start}:{col_letter}{block_end}")


def _format_feature_region(ws, df: pd.DataFrame, start_row: int) -> None:
    """
    根据 Feature_left / Feature_right 合并 B、C 两列：
    - General QA / KBQA / Memory QA / File Search：整个块 B..C 合并成一块
    - App Control / Device Setting：
      - B 列按块纵向合并
      - C 列对 Open App / Close App / Slotting / No-Slotting 各自纵向合并
    """
    n_rows = len(df)

    # 先按 Feature_left 分块，决定 B/C 合并方式
    i = 0
    while i < n_rows:
        feature_val = df["Feature_left"].iloc[i]
        block_start = i
        j = i + 1
        while j < n_rows and df["Feature_left"].iloc[j] == feature_val:
            j += 1
        block_end = j - 1

        excel_start = start_row + block_start
        excel_end = start_row + block_end

        block_right = df["Feature_right"].iloc[block_start : block_end + 1]
        if (block_right == "").all():
            ws.merge_cells(f"B{excel_start}:C{excel_end}")
        else:
            if excel_end > excel_start and feature_val != "":
                ws.merge_cells(f"B{excel_start}:B{excel_end}")

        i = j

    i = 0
    while i < n_rows:
        val = df["Feature_right"].iloc[i]
        if val == "":
            i += 1
            continue

        block_start = i
        j = i + 1
        while j < n_rows and df["Feature_right"].iloc[j] == val:
            j += 1
        block_end = j - 1

        excel_start = start_row + block_start
        excel_end = start_row + block_end
        if excel_end > excel_start:
            ws.merge_cells(f"C{excel_start}:C{excel_end}")

        i = j


def write_summary_excel(summary_df: pd.DataFrame, output_path: str) -> None:
    """写出 Excel 并做单元格合并，生成最终表格效果。"""
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        ws = writer.sheets["summary"]

        # 表头：合并 B1、C1 -> Feature
        ws["B1"].value = "Feature"
        ws["C1"].value = ""
        ws.merge_cells("B1:C1")

        start_row = 2  # 数据从第 2 行开始

        _merge_same_blocks(ws, "A", start_row, summary_df["POD"])
        _format_feature_region(ws, summary_df, start_row)


def main() -> None:
    args = parse_args()
    input_path = args.file

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"输入文件不存在：{input_path}")

    passrate_df = pd.read_excel(input_path, sheet_name="PassRate")
    timestat_df = pd.read_excel(input_path, sheet_name="timestatv2")

    summary_df = build_summary_table(passrate_df, timestat_df)

    input_dir = os.path.dirname(os.path.abspath(input_path))
    base_name, ext = os.path.splitext(args.output)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{base_name}_{timestamp}{ext or '.xlsx'}"
    output_path = os.path.join(input_dir, output_filename)

    write_summary_excel(summary_df, output_path)
    print(f"汇总完成，已生成：{output_path}")

def generate_summary(input_file: str, output_file: str = "summary.xlsx") -> str:
    """
    生成汇总表格
    
    Args:
        input_file: 输入的 Excel 文件路径（必须包含 PassRate 和 timestatv2 两个 sheet）
        output_file: 输出文件的基础名（默认 "summary.xlsx"）
    
    Returns:
        生成的输出文件完整路径
    """
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"输入文件不存在：{input_file}")

    # 读取数据
    passrate_df = pd.read_excel(input_file, sheet_name="PassRate")
    timestat_df = pd.read_excel(input_file, sheet_name="timestatv2")

    # 构建汇总表
    summary_df = build_summary_table(passrate_df, timestat_df)

    # 生成输出路径
    input_dir = os.path.dirname(os.path.abspath(input_file))
    base_name, ext = os.path.splitext(output_file)
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{base_name}{ext or '.xlsx'}"
    output_path = os.path.join(input_dir, output_filename)

    # 写入 Excel
    write_summary_excel(summary_df, output_path)
    print(f"汇总完成，已生成：{output_path}")
    
    return output_path

if __name__ == "__main__":
    main()