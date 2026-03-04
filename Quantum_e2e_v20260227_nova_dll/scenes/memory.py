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

IMPORTANT: URL validation has absolute priority and must be performed before any semantic evaluation.

Step 1 — Strict URL Validation (Highest Priority):
If the real_answer contains any complete URL (i.e., starting with "http://" or "https://"):
1. The response MUST contain the EXACT same URL string, matched character-by-character.
2. Domain-only matches, partial URLs, reformatted URLs, inferred URLs, or descriptive references are NOT acceptable.
3. If the exact URL string is absent or differs in any way:
   - You MUST assign Score = 0.
   - Provide a brief justification.
   - Terminate the evaluation immediately.
   - Do NOT perform any semantic or contextual analysis.
**Example Reference**:
- Q: "Which site has recipes?" | real_answer: "https://home.meishi.com." | response: [home.meishi.com.] -> **Score = 0** (Not provide the complete URL "https://home.meishi.com.")
- Q: "Which website hosts programming resources?" | real_answer: "https://github.com/" | response: [GitHub] -> **Score = 0** (Not provide the complete URL, only domain name)

Step 2 — Semantic Consistency Evaluation:
Proceed to this step ONLY if Step 1 is fully satisfied.
Scoring criteria:
1) Output Score = 1:if the response core meaning of the response matches the real_answer.
   Differences in wording/Conceptually equivalent expressions(e.g., work report presentation = work report PPT)  or minor details are allowed.
2) Output Score = 0:if the response contradicts the real_answer, or the response provides only real_answer partial information. If the real_answer contains a negation PLUS any explicit alternative or additional factual statement, the response MUST address BOTH; otherwise Score = 0.
3)If the real_answer contains NO time information, any added time references MUST be ignored for scoring.
  If the real_answer explicitly specifies the time granularity (e.g., real_answer provides only a month without a specific day or year), the response MUST NOT add finer or broader time details; otherwise Score = 0.
4)ID card and passport shall be regarded as the same type of identification document.
5) Special case (negative existence check ONLY):
   -If the real_answer contains ANY concrete factual value (including an explicit alternative fact), a response that only expresses uncertainty, lack of information, or inability to determine MUST be scored 0.
   This Specialrule applies ONLY if ALL conditions below are met(If the real_answer contains any concrete factual value, this Special case MUST NOT be applied):
   - The question is a pure existence-check question (yes/no about whether something exists).
   - The real_answer is explicitly contains only negation(e.g., "no", "not exist"), with NO additional facts, NO reasons.
   - The response indicates that the attribute is NOT mentioned, NOT specified, unknown, or cannot be determined.
   In this case, Output Score = 1.
   
**Example Reference**:
- Q: "Can I go to the flower field with Andy?" | real_answer: "No, Andy is allergic to pollen." | response: [No] -> **Score = 0** (because it omits the real_answer key alternative fact "Andy is allergic to pollen.)
- Q: "Do I have any memories of gym?" | real_answer: "NO." | response: [I do not have this information/data.] -> **Score = 1** (The real_answer is a 'negative conclusion' (explicitly states real_answer='NO' = no gym memories exist); 
The response ('no information') indicates the model cannot find any gym-related memories, which directly supports real_answer that 'gym memories do not exist' → consistent, so Score=1.")


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

IMPORTANT: URL validation has absolute priority and must be performed before any semantic evaluation.

Step 1 — Strict URL Validation (Highest Priority):
If the answer contains any complete URL (i.e., starting with "http://" or "https://"):

1. The matched_content MUST contain the EXACT same URL string, matched character-by-character.
2. Domain-only matches, partial URLs, reformatted URLs, inferred URLs, or descriptive references are NOT acceptable.
3. If the exact URL string is absent or differs in any way:
   - You MUST output "no".
   - Provide a brief justification.
   - Terminate the evaluation immediately.
   - Do NOT perform any semantic or contextual analysis.
**Example Reference**:
- Q: "Which site has recipes?" | answer: "https://home.meishi.com." | matched_content: [home.meishi.com.]-> **output "no"** (Not provide the complete URL "https://home.meishi.com.")
- Q: "Which website hosts programming resources?" | answer: "https://github.com/" | matched_content: [GitHub] -> **output "no"** (Not provide the complete URL, only domain name)

Step 2 — semantic analysis decision criteria:
Proceed to this step ONLY if Step 1 is fully satisfied.
1) Exact wording match is NOT required. Semantic meaning, facts, and conclusion consistency are required.
2) If matched_content explicitly contains, or directly supports (via straightforward inference) the answer, output "yes".
3) If matched_content information is missing, irrelevant, contradictory, or cannot support the answer, output "no".
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
        return "", "Root path does not exist", ""

    matched_df = merge_match_files(root_path)
    if matched_df.empty:
        return "", "No valid data", ""

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

DEFAULT_TEST_MODE = "cloud"
REQUEST_DELAY = 0.1
def verify_memory_retrieval(question, gt_answer, retrieval, test_mode="cloud"):
    """
    独立的 RAG 检索质量验证函数。
    
    Args:
        question: 问题文本
        gt_answer: 真实答案 (Ground Truth)
        retrieval: 模型检索内容 (Pre)
        test_mode: "local" 或 "cloud" (默认使用全局配置 DEFAULT_TEST_MODE)
        
    Returns:
        tuple: (result, reason)
               local模式: result 为 "pass"/"fail" 或 "" (若检索为空), reason 为字符串
               cloud模式: result 为 1/0, reason 为字符串
    """
    # 确定运行模式
    mode = test_mode if test_mode else DEFAULT_TEST_MODE
    
    # Local模式特殊逻辑：如果检索内容为空，直接返回空结果
    if mode == "local" and (not retrieval or not str(retrieval).strip()):
        return "", ""

    # 构建 Prompt (保持与原脚本一致的英文 Prompt)
    messages = [
        {
            "role": "system",
            "content": """You are a retrieval quality evaluation expert for a Retrieval-Augmented Generation (RAG) system.
Your task is to judge whether the user's Question can be correctly answered solely based on the context information (Pre) recalled by the model, and whether the derived answer is consistent with the Ground Truth (GT).

Please strictly follow this judgment logic:
1. **Independent Inference**: Ignore your own external knowledge and attempt to answer the Question **solely based on the information provided in Pre**.
2. **Consistency Check**: Compare the answer you derived based on Pre with the GT.

Judgment Rules:

**Pass (Qualified)**:
1. **Completely Consistent**: Pre contains the key information needed to answer the Question, and the answer derived from this information is consistent with the core content (including factual details) of the GT.
2. **Pure Negation/No Memory/Fact Correction**:
   - When GT indicates "no relevant information" or "No", or GT makes a **fact correction** (e.g., "Not A, only B"), and this correction is based on the non-existence of the fact.
   - **Criteria**:
     - If Pre indeed **does not contain** the incorrect object asked in the question (e.g., asked "Father", Pre only has "Mother"), corroborating "no information on father", matching the first part of GT -> **Pass**.
     - If Pre further contains the correct object mentioned in GT (e.g., GT says "actually it's mother", Pre indeed has "Mother" info), it is a perfect **Pass**.
     - If Pre is empty or contains only irrelevant information, as long as the core meaning of GT is "No/None/Don't know", it is considered consistent, judge **Pass**.

**Fail (Unqualified)**:
1. **Information Missing/Reason Unsupported**:
   - If GT contains specific facts or reasons (even if GT starts with "No", e.g., "No, because Andy is allergic").
   - At this time, if Pre **lacks** key information supporting this reason (e.g., Pre is completely irrelevant), making it impossible to derive the specific reason in GT, it must be judged as **Fail**.
2. **Contradiction**: The answer derived based on Pre contradicts GT.
   - Example: GT says "None", but Pre contains the exact memory referred to in the question.
3. **Pre is Empty but GT Contains Specific Facts**:
   - **Important**: If GT is "No" or negative, but implies facts that need confirmation (e.g., asking "Is the store open in the morning?", GT says "No" implying knowledge of store hours but not including morning).
   - At this time, if **Pre is empty**, it means the system retrieved absolutely no information about the store, cannot judge its opening hours, and thus cannot confidently answer "No" (can only answer "Don't know").
   - This case is judged as **Fail** (because possibility cannot be excluded based on Pre, classifying as retrieval failure).
   - *Exception*: If GT explicitly says "No record of the store", then Pre being empty is Pass. But if GT is answering a factual question (like "It's not open"), Pre being empty is Fail.
4. **URL Inconsistency or Incompleteness**:
   - If GT contains a complete URL (starting with "http://" or "https://"):
     - Pre must contain the EXACT same complete URL string(starting with "http://" or "https://").
     - If Pre only contains a domain name, partial URL, reformatted URL, inferred URL, or descriptive reference,
       it must be judged as Fail, regardless of semantic similarity.
       
**Ownership/Subject Matching Principle**:
- If the question specifies "my/User's" item (e.g., "my company's gym"), Pre must explicitly contain the item belonging to the user to count as "present".
- If Pre only has generic info (e.g., "Power Pulse Gym") without attribution, treat as "no relevant information".
- In this case, if GT is "No/None", it matches GT, judge **Pass**.

**Example Reference**:
- Q: "Father jogging?" | GT: "No info on father, mother jogs." | Pre: ["Mother jogs"] -> **Pass** (Pre confirms no father and has mother)
- Q: "My company's gym?" | GT: "No." | Pre: ["Power Pulse Gym" (generic)] -> **Pass** (No attribution = No relevant info = Matches No)
- Q: "Is store open morning?" | GT: "No" (implied: it's open at other times) | Pre: [] -> **Fail** (No info cannot judge hours, cannot derive No)
- Q: "Go to flower sea?" | GT: "No, Andy is allergic." | Pre: [Irrelevant] -> **Fail** (Cannot derive allergy reason)
- Q: "Which site has recipes?" | GT: "https://home.meishi.com." | Pre: [home.meishi.com.] -> **Fail** (Not provide the complete URL "https://home.meishi.com.")
- Q: "Which website hosts programming resources?" | GT: "https://github.com/" | Pre: [GitHub] -> **Fail** (Not provide the complete URL, only domain name)

Note: Pre might describe in third person (User/He/She), please treat as user's memory.
Must strictly return in the following format, no extra content allowed:
Judgment Result: [pass or fail]
Judgment Reason: [Brief explanation of conclusion derived from Pre and its relation to GT]"""
        },
        {
            "role": "user",
            "content": f"Question: {question}\nGround Truth (GT): {gt_answer}\nModel Prediction (Pre): {retrieval}"
        }
    ]

    try:
        # 简单的延时，避免触发限流
        if REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)
            
        response = chat_completion_with_retry(messages, max_retry=5, sleep_base=1)
        if response is None:
            raise Exception("GPT call failed: no response after retries")
        
        content = response.choices[0].message.content.strip()
        logging.info(f"Model Response: {content}")

        # 解析模型返回结果
        result = "fail"  # 默认 fail
        reason = "Failed to parse model response"
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            # 兼容中英文标签
            if line.startswith("Judgment Result:") or line.startswith("判决结果:"):
                result_str = line.split(':', 1)[1].strip().lower()
                if "pass" in result_str:
                    result = "pass"
                elif "fail" in result_str:
                    result = "fail"
            elif line.startswith("Judgment Reason:") or line.startswith("判决原因:"):
                reason = line.split(':', 1)[1].strip()

        # 根据模式返回不同格式
        if mode == "cloud":
            final_result = 1 if result == "pass" else 0
            return final_result, reason
        else:
            return result, reason

    except Exception as e:
        error_msg = f"Failed to call GPT model: {str(e)}"
        logging.error(error_msg)
        
        if mode == "cloud":
            return 0, error_msg
        else:
            return "fail", error_msg



def main(row: Dict) -> Dict:
    start_time = time.time()

    question = str(row["question"]).strip() if pd.notna(row.get("question")) else "No question"
    real_answer = str(row["answer"]).strip() if pd.notna(row.get("answer")) else "No real_answer"
    model_response = str(row["result"]).strip() if pd.notna(row.get("result")) else "No model_response"
    session_id_list = str(row["session_id_list"]).strip() if pd.notna(row.get("session_id_list")) else ""
    dimension = str(row["dimension"]).strip() if pd.notna(row.get("dimension")) else ""
    root_path = str(row["root_path"]).strip() if pd.notna(row.get("root_path")) else ""
    memory_retrieval_topk = str(row["memory_retrieval_topk"]).strip() if pd.notna(row.get("memory_retrieval_topk")) else ""
    test_mode = str(row["test_mode"]).strip() if pd.notna(row.get("test_mode")) else ""
    
    
    
    if model_response == "CTTVError: Empty response from server":
        score = 0
        reason = '接口返回为空'
    elif model_response == "CTTVError: Request Timeout":
        score = 0
        reason = '接口返回超时'
    elif str(model_response).startswith("CTTVError: Task failed -"):
        score = 0
        reason = '接口返回failed错误'
    # root_path = r"/home/taas/yangzy26/Benchmark/duanyy5/Memory_judge/result/"
    else:
        score, reason = verify_answer_consistency(question, real_answer, model_response)

    memory_reg_success, memory_reg_reason, matched_content_all = verify_Memory_reg_success(
        question=question,
        answer=real_answer,
        session_id_list=session_id_list,
        dimension=dimension,
        root_path=root_path
    )


    memory_retrieval_result = ""    
    memory_retrieval_reason = ""

    if test_mode == "cloud":
        memory_retrieval_result, memory_retrieval_reason = verify_memory_retrieval(
            question=question,
            gt_answer=real_answer,
            retrieval=memory_retrieval_topk,
            test_mode=test_mode
        )
        return {"Result": score, "Reason":reason, "matched_content_all":matched_content_all,"Memory_reg_success":memory_reg_success,"Memory_reg_reason":memory_reg_reason,"Retrieval_Check":memory_retrieval_result,"Retrieval_Reason":memory_retrieval_reason}
    else:
        return {"Result": score, "Reason":reason, "matched_content_all":matched_content_all,"Memory_reg_success":memory_reg_success,"Memory_reg_reason":memory_reg_reason}
    cost_time = time.time() - start_time
