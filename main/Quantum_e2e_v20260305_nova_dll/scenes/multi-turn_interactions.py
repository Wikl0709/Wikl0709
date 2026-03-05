import os
import time
import json
import logging
import re
from typing import List, Dict, Optional
from openai import OpenAI

# Logging config
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ===== Config (DO NOT hardcode API keys) =====
OPENROUTER_API_KEY = "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"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EVAL_MODEL = "deepseek/deepseek-r1"



# ==================== Global Conversation History Manager ====================
class ConversationHistory:
    """Conversation history manager for multi-turn context."""

    def __init__(self):
        self.history: List[Dict] = []
        self.current_session_id = None

    def add_turn(self, question: str, result: str, session_id: str = "default"):
        """Add a turn to history. Clears history if session changes."""
        if self.current_session_id != session_id:
            self.clear_history()
            self.current_session_id = session_id

        turn = {
            "timestamp": time.time(),
            "question": question,
            "result": result,
            "session_id": session_id,
        }
        self.history.append(turn)
        logger.info(f"Saved turn #{len(self.history)} to session '{session_id}'")

    def get_context(self, session_id: str = "default", max_turns: Optional[int] = None) -> str:
        """Get context string for current session."""
        if self.current_session_id != session_id or not self.history:
            return ""

        session_history = [t for t in self.history if t.get("session_id") == session_id]
        recent_history = session_history[-max_turns:] if (max_turns is not None and max_turns > 0) else session_history

        parts = []
        for turn in recent_history:
            parts.append(f"User: {turn['question']}")
            parts.append(f"Assistant: {turn['result']}")
        return "\n".join(parts)

    def get_full_history(self, session_id: str = "default") -> List[Dict]:
        """Get full history for session."""
        if self.current_session_id != session_id:
            return []
        return self.history.copy()

    def clear_history(self, session_id: str = "default"):
        """Clear history for session."""
        if session_id == "all" or self.current_session_id == session_id:
            self.history = []
            self.current_session_id = None
            logger.info(f"Cleared history for session '{session_id}'")

    def get_session_info(self, session_id: str = "default") -> Dict:
        """Get summary info for session."""
        session_turns = [t for t in self.history if t.get("session_id") == session_id]
        return {
            "session_id": session_id,
            "total_turns": len(session_turns),
            "current_turn": len(self.history),
            "has_history": len(session_turns) > 0,
        }


conversation_history = ConversationHistory()


# ==================== Core Functions ====================
def generate(messages):
    """
    Call OpenRouter API.
    """
    starttime = time.time()

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

    try:
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "",
                "X-Title": "",
            },
            extra_body={},
            model=EVAL_MODEL,
            messages=messages,
            seed=10000,
        )

        output_text = completion.choices[0].message.content
        ori_response = completion

        if hasattr(completion, "usage") and completion.usage:
            prompt_tokens = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens
            total_tokens = completion.usage.total_tokens
        else:
            prompt_tokens = completion_tokens = total_tokens = 0

    except Exception as e:
        completion = ""
        output_text = ""
        ori_response = f"Error: {e}"
        prompt_tokens = completion_tokens = total_tokens = 0
        logger.error(f"API call failed: {e}")

    duration = round(time.time() - starttime, 2)
    logger.info(
        f"API completed in {duration}s, tokens: {total_tokens} (prompt={prompt_tokens}, completion={completion_tokens})"
    )

    return {
        "completion": completion,
        "output_text": output_text,
        "prompt_or_messages": messages,
        "response": ori_response,
        "duration": duration,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def create_evaluation_prompt_multi_turn(question, result, context_info=None):
    context_part = ""
    if context_info:
        context_part = f"\n[Conversation Context]\n{context_info}\n"

    prompt = f"""You are a quality evaluation expert.
Your task is to judge whether the assistant's answer in the CURRENT turn is correct and acceptable.

[Evaluation Rules]
1. Factual questions: verify factual accuracy.
2. Translation tasks: verify accuracy and naturalness.
3. Coding tasks: verify syntax correctness and logical correctness.
4. Math tasks: verify the reasoning/calculation and the final result.
5. Instruction following: verify whether the instruction is followed completely and accurately.
6. Multi-turn dialogue: verify whether the assistant understands the context and stays coherent and consistent.

[Important Requirements]
- Output JSON ONLY. Do not include any other text, explanation outside JSON, or markers.
- The JSON MUST strictly follow the schema below.
- Do NOT use markdown code fences.
- Ensure the JSON is valid and directly parsable.

[Output JSON Schema]
{{
  "is_correct": true/false,
  "confidence": "high/medium/low",
  "explanation": "Detailed explanation",
  "correct_answer": "If incorrect, provide the correct answer"
}}

[Data to Evaluate]{context_part}
Current Question: {question}
Current Answer: {result}

Now output JSON only:"""

    return prompt


def parse_evaluation_result(output_text):
    """
    Parse evaluation JSON. If parsing fails, attempt cleanup and extraction.
    Returns a dict with keys: is_correct, confidence, explanation, correct_answer.
    """
    # First attempt
    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        logger.warning("First JSON parse failed; attempting cleanup.")

    cleaned_text = output_text.strip()

    # Remove markdown fences if any
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]

    cleaned_text = cleaned_text.strip()

    # Fix double quotes issues
    cleaned_text = cleaned_text.replace('""', '"')

    # Second attempt
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse still failed after cleanup: {e}")

    # Extract JSON object between first { and last }
    try:
        start = cleaned_text.find("{")
        end = cleaned_text.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = cleaned_text[start:end].replace('""', '"')
            return json.loads(json_str)
    except Exception as e:
        logger.warning(f"JSON object extraction failed: {e}")

    # Regex-based light fixes
    try:
        fixed_text = re.sub(r":\s*true\b", ": true", cleaned_text, flags=re.IGNORECASE)
        fixed_text = re.sub(r":\s*false\b", ": false", fixed_text, flags=re.IGNORECASE)
        fixed_text = re.sub(r":\s*null\b", ": null", fixed_text, flags=re.IGNORECASE)
        fixed_text = re.sub(r"(\w+)\s*:", r'"\1":', fixed_text)
        return json.loads(fixed_text)
    except Exception as e:
        logger.warning(f"Regex fix parse failed: {e}")

    # All failed
    logger.error("All JSON parsing attempts failed.")
    return {
        "is_correct": None,
        "confidence": "unknown",
        "explanation": "JSON parsing failed.",
        "correct_answer": "",
    }


def evaluate_single_qa_multi_turn(question, result, context_info=None, max_retries=2):
    """
    Evaluate a single QA turn with retries.
    """
    prompt = create_evaluation_prompt_multi_turn(question, result, context_info)
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(max_retries + 1):
        api_result = generate(messages)
        output_text = api_result["output_text"]

        eval_data = parse_evaluation_result(output_text)

        if eval_data.get("is_correct") is not None:
            return {**api_result, "eval_data": eval_data, "attempts": attempt + 1}

        if attempt == max_retries:
            logger.error(f"Still cannot parse JSON after {max_retries + 1} attempts.")
            return {
                **api_result,
                "eval_data": {
                    "is_correct": None,
                    "confidence": "parse_failed",
                    "explanation": f"JSON parsing failed after {max_retries + 1} attempts.",
                    "correct_answer": "",
                },
                "attempts": attempt + 1,
            }

        logger.info(f"Attempt {attempt + 1} failed; retrying...")
        time.sleep(1)


def create_error_result(error_message):
    """
    Create standardized error result.
    """
    return {
        "eval_context": "",
        "eval_prompt": "",
        "eval_result": "",
        "eval_is_correct": "",
        "eval_confidence": "",
        "eval_explanation": "",
        "eval_correct_answer": "",
        "eval_output_text": "",
        "eval_prompt_tokens": 0,
        "eval_completion_tokens": 0,
        "eval_total_tokens": 0,
        "eval_duration": 0.0,
        "eval_attempts": 0,
        "error": error_message,
    }


def evaluate_single_turn(input_data, session_id="default", use_history=True, max_context_turns=None):
    """
    Evaluate a single turn, optionally using accumulated conversation history.
    """
    try:
        question = input_data.get("question", "")
        result = input_data.get("result", "")

        if not question or not result:
            logger.error("Input data missing 'question' or 'result'.")
            return create_error_result("Input data missing 'question' or 'result'.")

        context_info = None
        if use_history:
            context_info = conversation_history.get_context(session_id, max_context_turns)

        logger.info(f"Starting evaluation for turn #{len(conversation_history.get_full_history(session_id)) + 1} (session={session_id})")
        logger.info(f"Question preview: {question[:80]}")

        eval_result = evaluate_single_qa_multi_turn(question, result, context_info)
        eval_prompt = create_evaluation_prompt_multi_turn(question, result, context_info)

        eval_data = eval_result["eval_data"]
        eval_result_json = json.dumps(eval_data, ensure_ascii=False)

        evaluation_result = {
            "eval_context": context_info or "",
            "eval_prompt": eval_prompt,
            "eval_result": eval_result_json,
            "eval_is_correct": eval_data.get("is_correct", ""),
            "eval_confidence": eval_data.get("confidence", ""),
            "eval_explanation": eval_data.get("explanation", ""),
            "eval_correct_answer": eval_data.get("correct_answer", ""),
            "eval_output_text": eval_result["output_text"],
            "eval_prompt_tokens": eval_result["prompt_tokens"],
            "eval_completion_tokens": eval_result["completion_tokens"],
            "eval_total_tokens": eval_result["total_tokens"],
            "eval_duration": eval_result["duration"],
            "eval_attempts": eval_result.get("attempts", 1),
            "session_id": session_id,
            "turn_number": len(conversation_history.get_full_history(session_id)) + 1,
            "context_turns_used": len(conversation_history.get_full_history(session_id)),
            "session_info": conversation_history.get_session_info(session_id),
        }

        conversation_history.add_turn(question, result, session_id)

        logger.info(f"Evaluation done: is_correct={eval_data.get('is_correct')}, confidence={eval_data.get('confidence')}")
        return evaluation_result

    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        return create_error_result(str(e))


def main(input_data, session_id="default", use_history=True, max_context_turns=None):
    """
    Main entry: Evaluate a single input dict or a list of dict turns.
    """
    logger.info("Starting multi-turn evaluation...")

    if isinstance(input_data, dict):
        logger.info(f"Input type: single dict (session={session_id})")
        return evaluate_single_turn(input_data, session_id, use_history, max_context_turns)

    if isinstance(input_data, list) and all(isinstance(item, dict) for item in input_data):
        logger.info(f"Input type: list of dicts, {len(input_data)} turns")
        all_results = []
        for turn in input_data:
            all_results.append(evaluate_single_turn(turn, session_id, use_history, max_context_turns))
            time.sleep(1)
        final_result = all_results
    else:
        logger.error(f"Unsupported input type: {type(input_data)}")
        final_result = [create_error_result(f"Unsupported input type: {type(input_data)}. Provide a dict or list[dict].")]

    if final_result and "error" not in final_result[0]:
        correct_count = sum(1 for r in final_result if r.get("eval_is_correct") is True)
        total_count = len(final_result)
        accuracy = correct_count / total_count if total_count > 0 else 0

        print(f"Evaluation finished: {total_count} turns, accuracy: {accuracy:.2%}")
        print(f"Session ID: {session_id}")
        print(f"Total turns stored: {conversation_history.get_session_info(session_id)['total_turns']}")

    return final_result


# ==================== Utility helpers ====================
def get_conversation_history(session_id="default"):
    return conversation_history.get_full_history(session_id)


def clear_conversation_history(session_id="default"):
    conversation_history.clear_history(session_id)


def get_current_context(session_id="default", max_turns=None):
    return conversation_history.get_context(session_id, max_turns)


# ==================== Quick smoke test ====================
if __name__ == "__main__":
    # Simple English-only test to ensure prompts + parsing are working
    turn1 = {"question": "What is Python?", "result": "Python is a high-level programming language."}
    result1 = main(turn1, session_id="python_session")
    print(f"result1: {result1}")