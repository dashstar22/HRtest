"""两种分析模式共用的条件表示、年限依据和保守一致性处理。"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone


def evaluation_date() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def alternatives(skill: str) -> list[str]:
    # ci/cd 是技能名，不是任选条件；斜杠仅对本 Demo 支持的数据库写法解释为或。
    skill = re.sub(r"(?i)\b(PostgreSQL)\s*/\s*(MySQL)\b", r"\1 或 \2", skill)
    return [s.strip() for s in re.split(r"或者|或", skill) if s.strip()]


def group_alternatives(skills: list[str], jd_text: str) -> list[str]:
    """解析阶段合并原 JD 中明确的技术任选关系；保存后不再按旧 JD 改写。"""
    groups = re.findall(
        r"[A-Za-z][A-Za-z0-9+#.-]*(?:\s*(?:或者|或|/)\s*[A-Za-z][A-Za-z0-9+#.-]*)+",
        jd_text,
    )
    output = list(dict.fromkeys(s.strip() for s in skills if s.strip()))
    for group in groups:
        parts = re.split(r"\s*(?:或者|或|/)\s*", group)
        if len(parts) < 2 or group.lower() == "ci/cd":
            continue
        members = {p.casefold() for p in parts}
        indexes = [i for i, s in enumerate(output)
                   if s.casefold() in members or s.casefold() == group.casefold()
                   or {p.casefold() for p in alternatives(s)} == members]
        if indexes:
            first = indexes[0]
            output = [s for i, s in enumerate(output) if i not in indexes]
            output.insert(first, " 或 ".join(parts))
    return output


def experience_facts(text: str, as_of: date | None = None) -> dict:
    """日期只推算工作区间总长，不将它自动等同于岗位相关经验。"""
    as_of = as_of or evaluation_date()
    claims = [float(n) for n in re.findall(
        r"(\d+(?:\.\d+)?)\s*年(?:以上)?(?:的)?[^\n，。;；]{0,12}?经验", text
    )]
    stated = max(claims) if claims else None
    work = re.search(r"(?:工作经历|工作经验|职业经历)(.*?)(?=专业技能|技能清单|教育背景|自我评价|$)", text, re.S)
    intervals = []
    if work:
        for sy, sm, ey, em, present in re.findall(
            r"((?:19|20)\d{2})[./年-](\d{1,2})\s*月?\s*[-—–~至]+\s*"
            r"(?:(20\d{2})[./年-](\d{1,2})|((?:至今|现在)))", work.group(1)
        ):
            start = int(sy) * 12 + int(sm) - 1
            end = as_of.year * 12 + as_of.month - 1 if present else int(ey) * 12 + int(em)
            if not 1 <= int(sm) <= 12 or (em and not 1 <= int(em) <= 12):
                continue
            if start < end <= as_of.year * 12 + as_of.month:
                intervals.append((start, end))
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    calculated = round(sum(b - a for a, b in merged) / 12, 2) if merged else None
    # 自述通常取整，容许不足一年差值；不把模型自己的推算作为证据。
    conflict = stated is not None and calculated is not None and abs(stated - calculated) >= 1
    basis = f"评估日期 {as_of.isoformat()}；自述经验：{stated:g} 年" if stated is not None else f"评估日期 {as_of.isoformat()}；未找到明确自述年限"
    if calculated is not None:
        basis += f"；工作区间合并去重约 {calculated:g} 年（不代表均为岗位相关经验）"
    basis += "；口径冲突，需人工确认" if conflict else "；以明确自述为初筛依据，需人工核实相关性"
    return {"evaluated_on": as_of.isoformat(), "stated_years": stated,
            "calculated_work_years": calculated, "experience_conflict": conflict,
            "experience_basis": basis,
            "years_of_experience": None if conflict else stated}


def conservative_hold(result: dict, reason: str) -> dict:
    result["score"] = min(result["score"], 74)
    result["verdict"] = "hold"
    result["summary"] = "暂缓自动推荐，需人工核实：" + reason
    warnings = result.setdefault("profile", {}).setdefault("review_warnings", [])
    if reason not in warnings:
        warnings.append(reason)
    return result
