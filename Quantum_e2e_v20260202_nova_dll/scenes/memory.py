# scenes/memory.py
import time
import logging
import requests
from typing import Dict
import pandas as pd
import threading
from openai import AzureOpenAI
import os
import json
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

logging.basicConfig(level=logging.INFO)

# ===== 配置区域 =====
# Azure OpenAI 配置
AZURE_ENDPOINT = "https://llm-east-us2-test.openai.azure.com/"
AZURE_KEY = "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY"
DEPLOYMENT_NAME = "gpt-4.1"
API_VERSION = "2024-12-01-preview"

COLUMNS = ["Result", "Reason", "cost_sec"]

FILE_PREFIX = "Memory_data_with_responses"
FAIL_RESULT = "failed_input_invalid, no input data"
CORE_COLS = ["user_content_1_result", "user_content_1_response_time"]
RATE_LIMIT_DELAY = 0.2

# Global lock for logging across threads
LOG_LOCK = threading.Lock()


# ===== Azure client + retry wrapper =====
def create_azure_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_KEY,
        api_version=API_VERSION
    )


def chat_completion_with_retry(messages, max_retry=5, sleep_base=1):
    """
    Azure OpenAI ChatCompletion retry wrapper (minimal intrusion).
    """
    for attempt in range(1, max_retry + 1):
        try:
            client = create_azure_client()
            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.1,              # keep as original to reduce behavioral drift
                max_completion_tokens=500,    # keep as original
                timeout=30
            )
            return response
        except Exception as e:
            logging.error(f"GPT call failed, retry {attempt}/{max_retry}. Error: {str(e)}")
            time.sleep(sleep_base * attempt)
    return None


# ===== Judge 1: Answer consistency (English prompt + English output labels) =====
def verify_answer_consistency(question: str, real_answer: str, model_response: str) -> tuple[int, str]:
    # Model request messages
    messages = [
        {
            "role": "system",
            "content": """
You are an answer consistency verification expert.

Task:
First, fully understand the question.
Then determine whether the model-generated response is semantically consistent with the real_answer.

Scoring criteria:
1) Output Score = 1 if the core meaning of the response matches the real_answer.
   Differences in wording or minor details are allowed.
2) Output Score = 0 if the core meaning differs, the response is irrelevant,
   or key information is missing.

Output requirements:
- You MUST follow the exact output format below.
- Output EXACTLY two lines.
- Do NOT output any extra text.

Exact output format:
Score: 0 or 1
Reason: A brief explanation based on the question context
"""
        },
        {
            "role": "user",
            "content": f"question: {question}\nreal_answer: {real_answer}\nresponse: {model_response}"
        }
    ]

    try:
        response = chat_completion_with_retry(messages, max_retry=5, sleep_base=1)
        if response is None:
            raise Exception("GPT call failed: no response after retries")

        content = (response.choices[0].message.content or "").strip()

        with LOG_LOCK:
            logging.info(f"Judge response: {content}")

        # Parse Score / Reason (tolerant to minor format variations)
        score = 0
        reason = "Failed to parse model response"

        # Score: supports extra spaces, but must be 0/1
        m_score = re.search(r"Score\s*:\s*([01])\b", content)
        if m_score:
            score = int(m_score.group(1))

        # Reason: allow multiline
        m_reason = re.search(r"Reason\s*:\s*(.*)", content, flags=re.S)
        if m_reason:
            reason = m_reason.group(1).strip()

        return score, reason

    except Exception as e:
        error_msg = f"Judge call failed: {str(e)}"
        with LOG_LOCK:
            logging.error(f"Data processing failed: {error_msg}")
        return 0, error_msg


# ===== Helpers for merging input files =====
def is_numeric_sid(sid: str) -> bool:
    """Check whether session_id is numeric."""
    try:
        float(str(sid).strip())
        return True
    except Exception:
        return False


def load_entries(json_path: str) -> list[dict]:
    """Load entries data from JSON."""
    if not os.path.exists(json_path):
        logging.warning(f"JSON not found: {json_path}")
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    memory_data = data.get("memory_data", {})
    entries_str = memory_data.get("entries", "[]")
    try:
        return json.loads(entries_str)
    except Exception:
        return ast.literal_eval(entries_str)


def merge_match_files(root_path: str) -> pd.DataFrame:
    """
    Merge Excel + match all JSON files in root_path.
    Returns DataFrame with Memory columns.
    """
    excel_files = [
        f for f in os.listdir(root_path)
        if f.startswith(FILE_PREFIX) and f.endswith(".xlsx") and f != "result.xlsx"
    ]
    if not excel_files:
        logging.warning("No matching Excel files")
        return pd.DataFrame()

    all_df = pd.concat(
        [pd.read_excel(os.path.join(root_path, f)) for f in excel_files],
        ignore_index=True
    )

    for col in CORE_COLS:
        if col not in all_df.columns:
            all_df[col] = None

    # Deduplicate by session_id
    final_data = []
    for sid, group in all_df.groupby("session_id"):
        if is_numeric_sid(sid):
            def is_fail(row):
                res = row[CORE_COLS[0]]
                t = row[CORE_COLS[1]]
                res_fail = pd.isna(res) or res == FAIL_RESULT
                t_fail = pd.isna(t) or t in (0, 0.0, "")
                return (pd.isna(res) and pd.isna(t)) or (res_fail and t_fail)

            valid_rows = group[~group.apply(is_fail, axis=1)]
            final_row = valid_rows.iloc[0].copy() if not valid_rows.empty else group.iloc[0].copy()
        else:
            normal_rows = group[~(group[CORE_COLS[0]] == FAIL_RESULT)]
            final_row = normal_rows.iloc[0].copy() if not normal_rows.empty else group.iloc[0].copy()

        final_data.append(final_row)

    merged_df = pd.DataFrame(final_data)

    excel_output_path = os.path.join(root_path, "memory_data_result_all.xlsx")
    merged_df.to_excel(excel_output_path, index=False)
    logging.info(f"Merged Excel saved to: {excel_output_path}")

    # Build id -> content mapping from all JSON files under root_path
    id2content = {}
    all_json_files = [f for f in os.listdir(root_path) if f.endswith(".json")]
    if not all_json_files:
        logging.warning("No JSON files found under root_path")
        merged_df["session_id"] = merged_df["session_id"].astype(str)
        return merged_df

    for json_file in all_json_files:
        json_path = os.path.join(root_path, json_file)
        try:
            entries = load_entries(json_path)
            valid_entries = {item["id"]: item["content"] for item in entries if "id" in item and "content" in item}
            id2content.update(valid_entries)
            logging.info(f"Parsed JSON: {json_file}, valid entries: {len(valid_entries)}")
        except Exception as e:
            logging.warning(f"Skip non-target JSON {json_file} (parse failed): {str(e)[:80]}...")
            continue

    if not id2content:
        logging.warning("No valid id-content mapping from JSON files")
        merged_df["session_id"] = merged_df["session_id"].astype(str)
        return merged_df

    # Fill Memory columns
    def extract_ids(cell):
        if pd.isna(cell):
            return []
        try:
            return json.loads(cell).get("entries", [])
        except Exception:
            return []

    merged_df["user_content_1_result_id"] = merged_df["user_content_1_result"].apply(extract_ids)
    merged_df["Memory_list"] = merged_df["user_content_1_result_id"].apply(lambda x: [id2content.get(i, "") for i in x])
    merged_df["session_id"] = merged_df["session_id"].astype(str)
    return merged_df


# ===== Judge 2: Memory answer supported by matched_content (English-only prompt, English JSON output) =====
def gpt_judge_memory_answer(matched_content_all: str, question: str, answer: str) -> Dict[str, any]:
    matched_content_all = matched_content_all.encode("utf-8", errors="replace").decode("utf-8")
    question = question.encode("utf-8", errors="replace").decode("utf-8")
    answer = answer.encode("utf-8", errors="replace").decode("utf-8")

    time.sleep(RATE_LIMIT_DELAY)

    system_prompt = """
You are a strict memory-judging assistant.

Your task:
Given matched_content, determine whether it can answer the question,
and whether the supported answer is semantically consistent with the provided answer.

Decision criteria:
1) Exact wording match is NOT required. Semantic meaning, facts, and conclusion consistency are required.
2) If matched_content explicitly contains, or directly supports (via straightforward inference) the answer, output "yes".
3) If information is missing, irrelevant, contradictory, or cannot support the answer, output "no".
4) Special case (negative attribute check):
   If the question asks whether an attribute/object/structure exists, and matched_content provides a complete or reasonable
   description of the object but does not mention that attribute, AND the answer is negative (e.g., "no/none/does not exist"),
   then output "yes" because the content supports the negative conclusion.

Do not use external knowledge. Base the judgment strictly on matched_content.
"""

    user_prompt = f"""
matched_content:
{matched_content_all}

question:
{question}

answer:
{answer}

Return JSON only:
{{
  "judge_memory_answer": "yes" or "no",
  "reason": "Briefly explain why it can or cannot answer/support the answer"
}}
"""

    try:
        response = chat_completion_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        content = (response.choices[0].message.content or "")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())

        return {"judge_memory_answer": "no", "reason": "Failed to parse judge JSON output"}

    except Exception as e:
        return {"judge_memory_answer": "no", "reason": f"Judge call failed: {str(e)}"}


# ===== Judge 3: Image-text registration success (English-only prompt, English JSON output) =====
def judge_image_text(matched_content_all: str, register_text: str) -> Dict[str, any]:
    time.sleep(RATE_LIMIT_DELAY)

    system_prompt = """
You are judging whether the Image-dimension registration was successful.

Background:
- register_text is the user's original text they wanted the system to remember.
- matched_content is what the model generated from the image and stored as memory.

Goal:
Determine whether matched_content semantically expresses the key information or factual relations in register_text.

Important rules:
Rule 1 (basic): If register_text is only objective facts (no subjective intent), matched_content must express those facts semantically to count as success.
Rule 2 (general): If matched_content only describes visual appearance (color, shape, material, pattern, etc.) but does NOT express the core facts/semantics in register_text, it is ALWAYS a failure.
Rule 3 (negative attribute check): If register_text asks whether an attribute/object exists, matched_content provides a complete description but does not include the attribute, AND the correct answer is negative, then judge as "yes".
Supplement: Always prioritize checking whether matched_content contains the core semantics/key information of register_text, even if embedded among other information.
"""

    user_prompt = f"""
register_text:
{register_text}

matched_content:
{matched_content_all}

Return JSON only:
{{
  "judge_image_register": "yes" or "no",
  "reason": "Explain in English whether the key text information was truly registered"
}}
"""

    try:
        response = chat_completion_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        content = (response.choices[0].message.content or "")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())

        return {"judge_image_register": "no", "reason": "Failed to parse image registration judge JSON output"}

    except Exception as e:
        logging.error(f"Image registration judge failed: {str(e)}")
        return {"judge_image_register": "no", "reason": f"Image registration judge failed: {str(e)}"}


# ===== Judge 4: Negative-case memory judge (English-only prompt, English JSON output) =====
def gpt_judge_negative_with_content(matched_content_all: str, question: str, answer: str) -> Dict[str, any]:
    """
    Negative-case Memory Judge:
    Determine whether matched_content supports the given answer to the question,
    even in negative samples.
    """
    matched_content_all = matched_content_all.encode("utf-8", errors="replace").decode("utf-8")
    question = question.encode("utf-8", errors="replace").decode("utf-8")
    answer = answer.encode("utf-8", errors="replace").decode("utf-8")

    time.sleep(RATE_LIMIT_DELAY)

    system_prompt = """
You are a strict "negative-case memory judge".

This is a negative-case sample, but "negative-case" does NOT guarantee matched_content lacks relevant information.

Core question:
Does matched_content support the answer to the question?

Decision logic:
1) If matched_content contains explicit facts and the answer is a correct yes/no conclusion based on those facts, output "yes".
2) If matched_content does NOT contain relevant information, but the answer is a reasonable negative answer, output "yes".
3) If matched_content contradicts the answer or cannot support it, output "no".

Special note:
- If the question conflicts with matched_content facts, and the answer is a corrective denial based on matched_content
  (e.g., fact is Dec 2 but question asks Dec 3), output "yes".
- Do not use external knowledge. Judge strictly based on matched_content.
"""

    user_prompt = f"""
matched_content:
{matched_content_all}

question:
{question}

answer:
{answer}

Return JSON only:
{{
  "judge_memory_answer": "yes" or "no",
  "reason": "Briefly explain why the negative-case answer is correct or incorrect"
}}
"""

    try:
        response = chat_completion_with_retry([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        content = (response.choices[0].message.content or "")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())

        return {"judge_memory_answer": "no", "reason": "Failed to parse negative-case judge JSON output"}

    except Exception as e:
        return {"judge_memory_answer": "no", "reason": f"Negative-case judge call failed: {str(e)}"}


# ===== Main business function =====
def verify_Memory_reg_success(
    question: str,
    answer: str,
    session_id_list: str,
    dimension: str,
    root_path: str
) -> tuple[str, str, str]:
    """
    Reuse original dual-judgment logic but with English-only prompts and English yes/no values.
    Returns:
      final_flag: "Y" or "N"
      final_reason: combined reason text
      matched_content_all: concatenated memory
    """
    if not root_path or not os.path.exists(root_path):
        return "N", "Root path does not exist", ""

    matched_df = merge_match_files(root_path)
    if matched_df.empty:
        return "N", "No valid data", ""

    contents = []
    register_texts = []
    if session_id_list:
        sids = [s.strip() for s in session_id_list.split(",") if s.strip()]
        for sid in sids:
            mask = matched_df["session_id"] == sid
            if mask.any():
                row = matched_df[mask].iloc[0]
                contents.extend([c for c in row["Memory_list"] if c.strip()])
                if pd.notna(row.get("user_content_1")):
                    register_texts.append(str(row["user_content_1"]).strip())

    matched_content_all = "\n".join(contents)
    register_text = "\n".join(register_texts)

    if not matched_content_all:
        return "N", "No matched memory content", ""

    is_negative_case = False
    if session_id_list:
        sids = [s.strip() for s in session_id_list.split(",") if s.strip()]
        for sid in sids:
            mask = matched_df["session_id"] == sid
            if mask.any():
                row = matched_df[mask].iloc[0]
                sub_dim = str(row.get("Sub-dimension-1", "")).strip()
                if sub_dim in ["反例"]:  # data value is from files; keep as-is
                    is_negative_case = True

    # Image judgment
    img_flag = "yes"
    img_reason = ""

    if dimension == "Image" and matched_content_all:
        if register_text:
            judgment_uc1 = judge_image_text(
                matched_content_all=matched_content_all,
                register_text=register_text
            )
            img_flag = judgment_uc1.get("judge_image_register", "no")
            img_reason = judgment_uc1.get("reason", "")
        else:
            img_flag = "no"
            img_reason = "No register_text (user_content_1) available for judgment"

    # Memory answer judgment
    if matched_content_all and question and answer:
        if is_negative_case:
            judgment = gpt_judge_negative_with_content(matched_content_all, question, answer)
        else:
            judgment = gpt_judge_memory_answer(matched_content_all, question, answer)
    else:
        judgment = {"judge_memory_answer": "no", "reason": "matched_content or question/answer is empty"}

    memory_flag = judgment.get("judge_memory_answer", "no")
    memory_reason = judgment.get("reason", "")

    # Final decision
    final_flag = "Y" if (memory_flag == "yes" and img_flag == "yes") else "N"
    final_reason = f"memory_answer: {memory_reason}\nimage_text (user_content_1 judge): {img_reason}"

    return final_flag, final_reason, matched_content_all


def main(row: Dict) -> Dict:
    start_time = time.time()

    question = str(row["question"]).strip() if pd.notna(row.get("question")) else "No question"
    real_answer = str(row["answer"]).strip() if pd.notna(row.get("answer")) else "No real_answer"
    model_response = str(row["result"]).strip() if pd.notna(row.get("result")) else "No model_response"
    session_id_list = str(row["session_id_list"]).strip() if pd.notna(row.get("session_id_list")) else ""
    dimension = str(row["dimension"]).strip() if pd.notna(row.get("dimension")) else ""
    root_path = str(row["root_path"]).strip() if pd.notna(row.get("root_path")) else ""
    if model_response == "CTTVError: Empty response from server":
        score = 0
        reason = '接口返回为空'
    elif model_response == "CTTVError: Request Timeout":
        score = 0
        reason = '接口返回超时'
    elif str(model_response).startswith("CTTVError: Task failed -"):
        score = 0
        reason = '接口返回failed错误'
    else:
        score, reason = verify_answer_consistency(question, real_answer, model_response)

    memory_reg_success, memory_reg_reason, matched_content_all = verify_Memory_reg_success(
        question=question,
        answer=real_answer,
        session_id_list=session_id_list,
        dimension=dimension,
        root_path=root_path
    )

    cost_time = time.time() - start_time
    return {"Result": score, "Reason":reason, "matched_content_all":matched_content_all,"Memory_reg_success":memory_reg_success,"Memory_reg_reason":memory_reg_reason}
