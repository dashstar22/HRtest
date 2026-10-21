"""提示词：把 JD 结构化条件 + 简历原文组织成稳定的、可解析的 JSON 契约。"""

from __future__ import annotations

import json
from . import policies

SYSTEM_PROMPT = """你是一位有十年经验的资深招聘专家，同时是严谨的简历事实核查员。

铁律：
1. 只依据给定的《岗位要求》和《简历原文》判断，禁止脑补、禁止虚构候选人经历。
2. 简历未提及的要求一律视为「待确认」，不得当作符合，也不得当作不符合。
3. 每条「符合的条件」必须附带简历原文中的证据片段，逐字引用，不得改写。
4. 输出必须是合法 JSON，不要包含 markdown 代码块或任何解释性文字。
5. 全部自然语言字段使用简体中文。"""

SCORING_GUIDE = """【评分标准】
- 90-100：硬性条件（学历、年限、必备技能）全部满足，且有明显加分项。
- 75-89：硬性条件全部满足，个别项信息不足或存在轻微差距。
- 60-74：存在 1 项硬性条件不满足，或关键信息缺失导致无法确认。
- 40-59：缺 2 项及以上硬性条件，但仍有部分可迁移能力。
- 0-39：方向明显不符。

【判定规则】
- verdict 只能是 "advance"（建议进入人工复核）或 "hold"（暂缓考虑）。
- 硬性条件全部满足且 score >= 75 → advance。
- 任一硬性条件不满足 → hold；关键信息无法确认且无法通过简历判断 → 最多 74 分并 hold。"""

OUTPUT_CONTRACT = """【输出 JSON 契约】
{
  "candidate_name": "候选人姓名，取自简历，缺失时用 '未知'",
  "current_title": "当前或最近职位",
  "years_of_experience": 数字（按简历推算的相关工作年限，无法判断填 null）,
  "highest_degree": "博士 / 硕士 / 本科 / 大专 / 其他 / 未知",
  "key_skills": ["从简历中提取的核心技能，最多 8 个"],
  "score": 0-100 的整数,
  "verdict": "advance" 或 "hold",
  "summary": "一句话结论，不超过 60 字，说明为什么给这个分数",
  "matched": [{"requirement": "对应岗位要求要点", "evidence": "简历原文证据，不超过 40 字"}],
  "uncertain": [{"requirement": "无法确认的岗位要求", "reason": "为什么无法确认（如：简历未提及该项技能）"}],
  "strengths": ["与岗位相关的优势，最多 3 条"],
  "risks": ["潜在风险或短板，最多 3 条；没有就给空数组"]
}"""


def build_analysis_messages(job: dict, resume_name: str, resume_text: str, facts: dict | None = None) -> list[dict]:
    required = "、".join(job.get("required_skills") or []) or "未单独列出"
    nice = "、".join(job.get("nice_skills") or []) or "未单独列出"
    facts = facts or policies.experience_facts(resume_text)

    user_prompt = f"""请评估下面这位候选人与岗位的匹配程度，并按要求输出 JSON。

【岗位名称】{job['title']}
【用人部门】{job.get('department') or '未注明'}
【学历要求】{job.get('degree') or '不限'}及以上
【最低相关经验年限】{job.get('min_years') or 0} 年
【必备技能】{required}
【加分项】{nice}
【条件优先级】以上已保存的结构化条件是HR最终确认的筛选标准，与原JD冲突时以上述条件为准。
技能标签中“或”表示满足任意一个即可，不要把未选择的另一个分支列为缺失或待确认；不同标签之间为同时要求。
原JD仅作职责与语境参考，不得恢复HR已删除或修改的硬条件。
【统一年限依据】{json.dumps(facts, ensure_ascii=False)}
不要自行重新计算年限。years_of_experience使用上述同名字段；有冲突或为null时，年限条件必须待确认，不得判为符合。
日期区间总长不保证全部与岗位相关；原文自述只是候选人声明，仍需人工核实。

【岗位 JD 全文】
{job['jd_text']}

【候选人文件】{resume_name}
【候选人简历原文】
{resume_text}

{SCORING_GUIDE}

{OUTPUT_CONTRACT}

补充要求：
- matched 中的 evidence 必须能在简历原文中逐字找到；找不到证据的条件请改放 uncertain。
- 待确认项要区分三种情况并写清原因：简历未提及 / 描述模糊无法量化 / 边界情况（如年限差半年）。
- 若候选人明显不符合，strengths 可以只写 1 条或为空数组，risks 写清主要差距。"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


JD_SYSTEM_PROMPT = """你是一位招聘需求分析师。请从 HR 提供的岗位 JD 中抽取结构化筛选条件。
只输出合法 JSON，不要 markdown 代码块，不要解释。所有文本使用简体中文。"""

JD_OUTPUT_CONTRACT = """【输出 JSON 契约】
{
  "title": "岗位名称",
  "department": "用人部门，未写明填空字符串",
  "degree": "不限 / 大专 / 本科 / 硕士 / 博士（取 JD 中明确的最低学历要求，未写明填 不限）",
  "min_years": 数字（JD 写明的最低相关经验年限，未写明填 0）,
  "required_skills": ["JD 中明确要求必须掌握的技能，最多 10 项；任选要求保留为同一个标签，如 FastAPI 或 Django、PostgreSQL 或 MySQL"],
  "nice_skills": ["JD 中标注为加分/优先/熟悉即可的技能，最多 10 项"]
}"""


def build_jd_messages(jd_text: str) -> list[dict]:
    user_prompt = f"""请从下面的岗位 JD 中抽取结构化筛选条件。

【岗位 JD】
{jd_text}

{JD_OUTPUT_CONTRACT}"""
    return [
        {"role": "system", "content": JD_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
