"""AI 分析层：DeepSeek 调用 + 结果归一化 + 失败兜底。"""

from __future__ import annotations

import asyncio
import json
import re

import httpx

from . import config, prompts, rule_engine


class AIError(Exception):
    pass


def _strip_code_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.MULTILINE)
    return content.strip()


def extract_json(content: str) -> dict:
    text = _strip_code_fence(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise AIError("模型返回的内容不是合法 JSON")


def _as_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _normalize_list(items, requirement_key: str, second_key: str) -> list[dict]:
    """兼容模型把结构化列表写成纯字符串数组的情况。"""
    normalized: list[dict] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if isinstance(item, dict):
            first = _as_text(item.get(requirement_key))
            second = _as_text(item.get(second_key))
            if first or second:
                normalized.append({requirement_key: first, second_key: second})
        elif isinstance(item, str) and item.strip():
            normalized.append({requirement_key: item.strip(), second_key: ""})
    return normalized


def _normalize_text_list(items, limit: int) -> list[str]:
    if not isinstance(items, list):
        return []
    result = [_as_text(i) for i in items]
    return [i for i in result if i][:limit]


def _normalize_verdict(value) -> str:
    text = _as_text(value).lower()
    if any(token in text for token in ("advance", "复核", "推进", "推荐", "pass", "yes")):
        return "advance"
    return "hold"


def normalize_result(raw: dict, resume_name: str) -> dict:
    try:
        score = int(round(float(raw.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    years = raw.get("years_of_experience")
    try:
        years = float(years) if years is not None else None
    except (TypeError, ValueError):
        years = None

    key_skills = _normalize_text_list(raw.get("key_skills"), 8)
    degree = _as_text(raw.get("highest_degree")) or "未知"
    title = _as_text(raw.get("current_title"))
    name = _as_text(raw.get("candidate_name")) or resume_name

    profile = {
        "current_title": title,
        "years_of_experience": years,
        "highest_degree": degree,
        "key_skills": key_skills,
    }

    return {
        "candidate_name": name,
        "current_title": title,
        "years_of_experience": years,
        "highest_degree": degree,
        "key_skills": key_skills,
        "score": score,
        "verdict": _normalize_verdict(raw.get("verdict")),
        "summary": _as_text(raw.get("summary")) or "模型未给出结论摘要",
        "matched": _normalize_list(raw.get("matched"), "requirement", "evidence"),
        "uncertain": _normalize_list(raw.get("uncertain"), "requirement", "reason"),
        "strengths": _normalize_text_list(raw.get("strengths"), 3),
        "risks": _normalize_text_list(raw.get("risks"), 3),
        "profile": profile,
    }


PUNCT_RE = re.compile(r"[\s\u3000，。；：、,.;:!?！？（）()【】\[\]{}“”\"'‘’·\-—–_/\\|]+")


def _squash(text: str) -> str:
    return PUNCT_RE.sub("", text or "").lower()


def verify_evidence(result: dict, resume_text: str) -> dict:
    """核对模型给出的「原文引用」是否真的出现在简历里。

    提示词要求逐字引用，但模型仍可能改写或凭空生成。这里做一次程序化校验，
    把对不上原文的条目降级为待确认，避免 HR 被看似可信的假证据误导。
    """
    haystack = _squash(resume_text)
    verified: list[dict] = []
    rejected: list[dict] = []

    for item in result.get("matched", []):
        needle = _squash(item.get("evidence", ""))
        # 长引用允许只匹配前 12 个字，容忍模型省略后半句
        if needle and (needle in haystack or (len(needle) >= 12 and needle[:12] in haystack)):
            verified.append(item)
        else:
            rejected.append(item)

    if not rejected:
        return result

    result["matched"] = verified
    uncertain = result.setdefault("uncertain", [])
    existing = {entry.get("requirement") for entry in uncertain}
    for item in rejected:
        requirement = item.get("requirement") or "未命名的岗位要求"
        if requirement in existing:
            continue
        uncertain.append(
            {
                "requirement": requirement,
                "reason": "模型给出的引用未能在简历原文中定位，需人工核对",
            }
        )
        existing.add(requirement)
    result["evidence_rejected"] = len(rejected)
    return result


async def _call_deepseek(messages: list[dict], temperature: float = 0.0) -> dict:
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "max_tokens": 1600,
    }
    headers = {
        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{config.DEEPSEEK_BASE_URL}/chat/completions"

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 401:
                raise AIError("API Key 校验失败（401），请检查 .env 中的 DEEPSEEK_API_KEY")
            if response.status_code == 429:
                raise AIError("DeepSeek 接口限流（429），请稍后重试")
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return extract_json(content)
        except AIError:
            raise
        except Exception as exc:  # 网络抖动给一次重试
            last_error = exc
            if attempt == 0:
                await asyncio.sleep(1.2)
    raise AIError(f"调用 DeepSeek 失败：{last_error}")


async def analyze_resume(job: dict, resume: dict) -> dict:
    """单份简历分析。返回结构含 candidate_name 等展示字段与 mode。"""
    if config.AI_MODE == "deepseek":
        try:
            messages = prompts.build_analysis_messages(job, resume["file_name"], resume["text"])
            raw = await _call_deepseek(messages)
            result = normalize_result(raw, resume["name"])
            result = verify_evidence(result, resume["text"])
            result["mode"] = "deepseek"
            return result
        except AIError as exc:
            # 单份失败不中断整批，降级规则引擎并在 UI 标注原因。
            result = rule_engine.analyze(job, resume["name"], resume["text"])
            result["mode"] = "rule-fallback"
            result["error"] = str(exc)
            return result

    result = rule_engine.analyze(job, resume["name"], resume["text"])
    result["mode"] = "rule"
    return result


async def parse_jd(jd_text: str) -> dict:
    if config.AI_MODE == "deepseek":
        try:
            raw = await _call_deepseek(prompts.build_jd_messages(jd_text), temperature=0.0)
            return {
                "title": _as_text(raw.get("title")),
                "department": _as_text(raw.get("department")),
                "degree": _as_text(raw.get("degree")) or "不限",
                "min_years": float(raw.get("min_years") or 0),
                "required_skills": _normalize_text_list(raw.get("required_skills"), 10),
                "nice_skills": _normalize_text_list(raw.get("nice_skills"), 10),
            }
        except (AIError, ValueError, TypeError):
            return rule_engine.parse_jd(jd_text)
    return rule_engine.parse_jd(jd_text)
