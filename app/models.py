"""API 出入参的数据契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["advance", "hold"]
Decision = Literal["accepted", "rejected"]


class JobCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=80, description="岗位名称")
    department: str = Field("", max_length=40, description="用人部门")
    jd_text: str = Field(..., min_length=10, description="JD 全文")
    degree: str = Field("不限", description="学历要求：不限/大专/本科/硕士/博士")
    min_years: float = Field(0, ge=0, le=40, description="最低相关经验年限")
    required_skills: list[str] = Field(default_factory=list, description="必备技能")
    nice_skills: list[str] = Field(default_factory=list, description="加分项")


class JobUpdate(JobCreate):
    pass


class Job(JobCreate):
    id: str
    created_at: str
    resume_count: int = 0
    screened_count: int = 0


class Resume(BaseModel):
    id: str
    job_id: str
    name: str
    file_name: str
    char_count: int
    created_at: str


class ResumeDetail(Resume):
    text: str


class MatchedItem(BaseModel):
    requirement: str
    evidence: str


class UncertainItem(BaseModel):
    requirement: str
    reason: str


class CandidateProfile(BaseModel):
    current_title: str = ""
    years_of_experience: float | None = None
    highest_degree: str = ""
    key_skills: list[str] = Field(default_factory=list)
    evaluated_on: str = ""
    stated_years: float | None = None
    calculated_work_years: float | None = None
    experience_conflict: bool = False
    experience_basis: str = ""
    review_warnings: list[str] = Field(default_factory=list)


class ScreeningResult(BaseModel):
    id: str
    job_id: str
    resume_id: str
    resume_name: str
    file_name: str
    score: int
    verdict: Verdict
    summary: str
    matched: list[MatchedItem] = Field(default_factory=list)
    uncertain: list[UncertainItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    profile: CandidateProfile = Field(default_factory=CandidateProfile)
    mode: str
    created_at: str
    decision: Decision | None = None
    decision_at: str | None = None
    decision_score: int | None = None
    decision_note: str | None = None
    previous_score: int | None = None
    previous_verdict: Verdict | None = None
    stale: bool = False


class DecisionRequest(BaseModel):
    """人工决策：accepted=采纳并进入沟通，rejected=拒绝；null 表示撤销标注。"""

    decision: Decision | None = None
    note: str | None = Field(None, max_length=200, description="人工备注，仅在有决策时保存")


class BatchDecisionRequest(BaseModel):
    result_ids: list[str] = Field(..., min_length=1)
    decision: Decision | None = None
    note: str | None = Field(None, max_length=200)


class BatchDecisionReport(BaseModel):
    updated: int


class ParseJdRequest(BaseModel):
    jd_text: str = Field(..., min_length=10)


class ParsedJd(BaseModel):
    title: str = ""
    department: str = ""
    degree: str = "不限"
    min_years: float = 0
    required_skills: list[str] = Field(default_factory=list)
    nice_skills: list[str] = Field(default_factory=list)


class ScreenRequest(BaseModel):
    """resume_ids 为空时表示筛选该岗位下所有简历。"""

    resume_ids: list[str] = Field(default_factory=list)


class ScreenReport(BaseModel):
    total: int
    succeeded: int
    failed: int
    errors: list[str] = Field(default_factory=list)
    mode: str


class AIStatus(BaseModel):
    mode: Literal["deepseek", "rule"]
    model: str
    base_url: str
    configured: bool
    message: str


class Stats(BaseModel):
    total: int
    screened: int = 0
    advance: int
    hold: int
    avg_score: float
    accepted: int = 0
    rejected: int = 0
    changed: int = 0
