"""规则引擎：未配置大模型 API Key 时的兜底实现。

它不追求语义理解，只保证「上传 -> 解析 -> 打分 -> 展示」链路完整可演示，
输出结构与 AI 模式完全一致，因此前端与数据结构无需区分两种模式。
"""

from __future__ import annotations

import re

# 技能别名表：值统一小写，用于大小写无关的子串匹配。
SKILL_ALIASES: dict[str, list[str]] = {
    "python": ["python"],
    "java": ["java"],
    "go": ["golang", "go语言"],
    "javascript": ["javascript", "js"],
    "typescript": ["typescript"],
    "sql": ["sql"],
    "mysql": ["mysql"],
    "postgresql": ["postgresql", "postgres"],
    "redis": ["redis"],
    "mongodb": ["mongodb"],
    "linux": ["linux"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "git": ["git"],
    "fastapi": ["fastapi"],
    "django": ["django"],
    "flask": ["flask"],
    "spring boot": ["spring boot", "springboot", "spring cloud"],
    "react": ["react"],
    "vue": ["vue"],
    "机器学习": ["机器学习", "machine learning"],
    "深度学习": ["深度学习", "deep learning"],
    "自然语言处理": ["自然语言处理", "nlp"],
    "大模型": ["大模型", "llm", "gpt", "aigc", "transformer"],
    "rag": ["rag", "检索增强"],
    "向量数据库": ["向量数据库", "向量检索", "milvus", "pgvector", "faiss"],
    "prompt engineering": ["prompt", "提示词"],
    "数据分析": ["数据分析", "data analysis"],
    "pandas": ["pandas"],
    "spark": ["spark"],
    "hadoop": ["hadoop", "hive"],
    "kafka": ["kafka"],
    "微服务": ["微服务", "microservice"],
    "ci/cd": ["ci/cd", "cicd", "jenkins", "gitlab ci"],
    "自动化测试": ["自动化测试", "pytest", "selenium"],
    "产品设计": ["产品设计", "prd", "需求分析"],
    "项目管理": ["项目管理", "pmp", "scrum", "敏捷"],
    "英语": ["英语", "english", "cet-6", "雅思", "托福"],
}

DEGREE_LEVEL = {"不限": 0, "大专": 1, "本科": 2, "硕士": 3, "博士": 4}
DEGREE_WORDS = [
    ("博士", "博士", 4),
    ("硕士", "硕士", 3),
    ("研究生", "硕士", 3),
    ("本科", "本科", 2),
    ("学士", "本科", 2),
    ("大专", "大专", 1),
    ("专科", "大专", 1),
]

EXPERIENCE_RES = [
    re.compile(r"(\d+(?:\.\d+)?)\s*年(?:以上)?(?:的)?(?:[^\n，。;；]{0,12})?经验"),
    re.compile(r"(?:工作|从业|相关)(?:年限|经验)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*年"),
]
HIGHLIGHT_KEYWORDS = [
    "团队管理", "带团队", "团队负责人", "技术负责人", "从 0 到 1", "从0到1",
    "高并发", "架构设计", "性能优化", "开源", "论文", "专利", "跨部门",
    "字节跳动", "腾讯", "阿里巴巴", "美团", "百度", "京东", "拼多多", "网易",
]

TITLE_RE = re.compile(
    r"(?:当前职位|现任职位|求职意向|应聘职位|期望职位|职位|岗位|职务)\s*[:：]\s*([^\n|，。]{2,24})"
)
SENTENCE_SPLIT_RE = re.compile(r"[。；;\n]")


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def find_skills(text: str) -> list[str]:
    """返回简历中命中的技能名（规范名，保留原始大小写风格）。"""
    haystack = _squash(text)
    hits: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(_squash(alias) in haystack for alias in aliases):
            hits.append(canonical)
    return hits


def match_skill(requirement: str, text: str) -> bool:
    """判断岗位要求里的某一项技能是否出现在简历中。"""
    normalized = _squash(requirement)
    if not normalized:
        return False
    aliases = SKILL_ALIASES.get(normalized)
    if aliases:
        return any(_squash(a) in _squash(text) for a in aliases)
    return normalized in _squash(text)


def extract_degree(text: str) -> str:
    for word, canonical, _level in DEGREE_WORDS:
        if word in text:
            return canonical
    return "未知"


def extract_years(text: str) -> float | None:
    found: list[float] = []
    for pattern in EXPERIENCE_RES:
        found.extend(float(m) for m in pattern.findall(text))
    return max(found) if found else None


def extract_title(text: str) -> str:
    match = TITLE_RE.search(text)
    if match:
        return match.group(1).strip()
    return ""


def evidence_for(text: str, keyword: str, limit: int = 40) -> str:
    """从简历里截取包含关键词的原文片段作为证据（大小写不敏感）。"""
    if not keyword:
        return ""
    needle = keyword.lower()
    for sentence in SENTENCE_SPLIT_RE.split(text):
        if needle in sentence.lower():
            cleaned = sentence.strip(" 　|")
            if not cleaned:
                continue
            return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"
    return ""


def first_evidence(text: str, candidates: list[str], limit: int = 40) -> str:
    for candidate in candidates:
        found = evidence_for(text, candidate, limit)
        if found:
            return found
    return ""


def _degree_level(name: str) -> int:
    for _word, canonical, level in DEGREE_WORDS:
        if name == canonical:
            return level
    return -1


def analyze(job: dict, resume_name: str, text: str) -> dict:
    """规则模式下的匹配分析，输出结构与 AI 模式一致。"""
    required_skills: list[str] = [s for s in (job.get("required_skills") or []) if s]
    nice_skills: list[str] = [s for s in (job.get("nice_skills") or []) if s]
    needed_degree = job.get("degree") or "不限"
    needed_years = float(job.get("min_years") or 0)

    degree = extract_degree(text)
    years = extract_years(text)
    title = extract_title(text)
    matched: list[dict] = []
    uncertain: list[dict] = []
    strengths: list[str] = []
    risks: list[str] = []

    score = 100
    hard_failures = 0

    # --- 学历 ---
    if needed_degree != "不限":
        need_level = DEGREE_LEVEL.get(needed_degree, 0)
        have_level = _degree_level(degree)
        if have_level < 0:
            score -= 10
            uncertain.append(
                {"requirement": f"学历要求：{needed_degree}及以上", "reason": "简历中未写明学历"}
            )
        elif have_level < need_level:
            score -= 25
            hard_failures += 1
            risks.append(f"学历为{degree}，低于岗位要求的{needed_degree}")
        else:
            matched.append(
                {
                    "requirement": f"学历要求：{needed_degree}及以上",
                    "evidence": evidence_for(text, degree) or f"已获得{degree}学历",
                }
            )

    # --- 经验年限 ---
    if needed_years > 0:
        if years is None:
            score -= 8
            uncertain.append(
                {"requirement": f"相关经验 {needed_years:g} 年以上", "reason": "简历未量化工作年限"}
            )
        elif years < needed_years:
            score -= 20
            hard_failures += 1
            risks.append(f"相关经验约 {years:g} 年，未达到 {needed_years:g} 年要求")
        else:
            matched.append(
                {
                    "requirement": f"相关经验 {needed_years:g} 年以上",
                    "evidence": first_evidence(text, [f"{years:g} 年", f"{years:g}年", "经验"])
                    or f"简历显示约 {years:g} 年经验",
                }
            )

    # --- 必备技能 ---
    skill_hits = 0
    for skill in required_skills:
        if match_skill(skill, text):
            skill_hits += 1
            matched.append(
                {
                    "requirement": f"必备技能：{skill}",
                    "evidence": evidence_for(text, skill) or f"简历中出现 {skill}",
                }
            )
        else:
            uncertain.append(
                {"requirement": f"必备技能：{skill}", "reason": "简历中未出现相关描述"}
            )
    if required_skills:
        missing = len(required_skills) - skill_hits
        if missing:
            score -= min(12 * missing, 40)
            if missing >= max(2, len(required_skills) / 2):
                hard_failures += 1
            risks.append(f"缺少必备技能描述：{missing}/{len(required_skills)} 项")

    # --- 加分项 ---
    nice_hits = [s for s in nice_skills if match_skill(s, text)]
    if nice_hits:
        score += min(3 * len(nice_hits), 9)
        strengths.append(f"额外具备加分技能：{'、'.join(nice_hits[:4])}")

    detected = find_skills(text)
    extra = [s for s in detected if s not in required_skills and s not in nice_skills]
    if extra:
        strengths.append(f"技能栈还包括：{'、'.join(extra[:4])}")

    highlights = [kw for kw in HIGHLIGHT_KEYWORDS if kw in text]
    if highlights:
        strengths.append(f"履历亮点：{'、'.join(highlights[:3])}")

    if not strengths:
        strengths.append("简历信息较简，暂无明显额外亮点")

    score = max(0, min(100, int(round(score))))
    # 与提示词中的判定口径保持一致：75 分以上且无硬性条件缺口才建议复核
    verdict = "advance" if score >= 75 and hard_failures == 0 else "hold"

    profile = {
        "current_title": title,
        "years_of_experience": years,
        "highest_degree": degree,
        "key_skills": detected[:8],
    }

    if verdict == "advance":
        summary = f"规则初筛得分 {score} 分：硬性条件基本满足，建议人工复核其经历真实性。"
    elif hard_failures:
        summary = f"规则初筛得分 {score} 分：存在 {hard_failures} 项硬性条件不满足，建议暂缓。"
    else:
        summary = f"规则初筛得分 {score} 分：部分必备技能未覆盖或信息不足，建议暂缓并补充核实。"

    return {
        "candidate_name": resume_name,
        "current_title": title,
        "years_of_experience": years,
        "highest_degree": degree,
        "key_skills": detected[:8],
        "score": score,
        "verdict": verdict,
        "summary": summary,
        "matched": matched,
        "uncertain": uncertain,
        "strengths": strengths[:3],
        "risks": risks[:3],
        "profile": profile,
    }


TITLE_IN_JD_RE = re.compile(r"(?:岗位名称|职位名称|招聘岗位)\s*[:：]\s*([^\n]{2,30})")
DEPARTMENT_RE = re.compile(r"用人部门\s*[:：]\s*([^\n]{2,20})")
DEGREE_IN_JD_RE = re.compile(r"(博士|硕士|研究生|本科|大专|专科)(?:及以上|以上|学历)")
YEARS_IN_JD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*年(?:以上)?(?:的)?(?:[^\n，。;；]{0,12})?经验")

REQUIREMENT_MARKERS = ("任职要求", "岗位要求", "任职资格", "职位要求", "我们希望你")


def requirement_section(jd_text: str) -> str:
    """优先只在「任职要求」段落里抽取技能，避免职责描述里的连带词汇被误判为要求。"""
    best = -1
    for marker in REQUIREMENT_MARKERS:
        index = jd_text.find(marker)
        if index >= 0 and (best < 0 or index < best):
            best = index
    return jd_text[best:] if best >= 0 else jd_text


def parse_jd(jd_text: str) -> dict:
    """规则模式下的 JD 结构化抽取。"""
    degree = "不限"
    match = DEGREE_IN_JD_RE.search(jd_text)
    if match:
        raw = match.group(1)
        degree = "硕士" if raw == "研究生" else raw

    years = 0.0
    found = YEARS_IN_JD_RE.findall(jd_text)
    if found:
        years = max(float(v) for v in found)

    title_match = TITLE_IN_JD_RE.search(jd_text)
    title = title_match.group(1).strip() if title_match else ""
    if not title:
        first_line = next((line.strip(" #\t") for line in jd_text.splitlines() if line.strip()), "")
        title = first_line[:30]

    department_match = DEPARTMENT_RE.search(jd_text)
    department = department_match.group(1).strip() if department_match else ""

    # 按行判断技能属于「必备」还是「加分」：带「优先/加分」字样的行归入加分项。
    required: list[str] = []
    nice: list[str] = []
    for line in requirement_section(jd_text).splitlines():
        hits = find_skills(line)
        if not hits:
            continue
        is_nice = "优先" in line or "加分" in line or "plus" in line.lower()
        for skill in hits:
            if skill in required or skill in nice:
                continue
            (nice if is_nice else required).append(skill)

    if not required:
        required = [s for s in find_skills(jd_text) if s not in nice][:8]

    return {
        "title": title,
        "department": department,
        "degree": degree,
        "min_years": years,
        "required_skills": required[:10],
        "nice_skills": nice[:10],
    }
