"""FastAPI 入口：岗位管理、简历上传解析、批量筛选、结果导出。"""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import analyzer, config, db, parsers, rule_engine
from .models import (
    AIStatus,
    BatchDecisionReport,
    BatchDecisionRequest,
    DecisionRequest,
    Job,
    JobCreate,
    JobUpdate,
    ParsedJd,
    ParseJdRequest,
    Resume,
    ResumeDetail,
    ScreenReport,
    ScreenRequest,
    ScreeningResult,
    Stats,
)

MAX_FILE_BYTES = 10 * 1024 * 1024
SEMAPHORE = asyncio.Semaphore(config.LLM_CONCURRENCY)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="AI 招聘简历智能筛选助手",
    description="面向 HR 的简历初筛 Demo：JD 结构化、简历解析、AI 匹配、结果可视化。",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


def _require_job(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return job


# ------------------------------------------------------------------- 基础信息


@app.get("/api/status", response_model=AIStatus)
def status() -> dict:
    if config.AI_MODE == "deepseek":
        return {
            "mode": "deepseek",
            "model": config.DEEPSEEK_MODEL,
            "base_url": config.DEEPSEEK_BASE_URL,
            "configured": True,
            "message": f"已连接 {config.DEEPSEEK_MODEL}，由大模型完成语义匹配",
        }
    return {
        "mode": "rule",
        "model": "rule-engine",
        "base_url": "",
        "configured": False,
        "message": "未配置 DEEPSEEK_API_KEY，当前为规则引擎模拟模式（流程可完整演示）",
    }


# ----------------------------------------------------------------------- 岗位


@app.post("/api/parse-jd", response_model=ParsedJd)
async def parse_jd(payload: ParseJdRequest) -> dict:
    """从 JD 文本自动抽取学历/年限/技能等结构化筛选条件。"""
    return await analyzer.parse_jd(payload.jd_text)


@app.get("/api/jobs", response_model=list[Job])
def list_jobs() -> list[dict]:
    return db.list_jobs()


@app.post("/api/jobs", response_model=Job, status_code=201)
def create_job(payload: JobCreate) -> dict:
    job_id = uuid.uuid4().hex[:12]
    return db.create_job(job_id, payload.model_dump())


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> dict:
    return _require_job(job_id)


@app.put("/api/jobs/{job_id}", response_model=Job)
def update_job(job_id: str, payload: JobUpdate) -> dict:
    _require_job(job_id)
    # JD 条件变了：旧结果标记为过期，但人工标注保留，重新筛选时自动沿用。
    db.mark_stale(job_id)
    updated = db.update_job(job_id, payload.model_dump())
    return updated  # type: ignore[return-value]


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> Response:
    if not db.delete_job(job_id):
        raise HTTPException(status_code=404, detail="岗位不存在")
    return Response(status_code=204)


# ----------------------------------------------------------------------- 简历


@app.get("/api/jobs/{job_id}/resumes", response_model=list[Resume])
def list_resumes(job_id: str) -> list[dict]:
    _require_job(job_id)
    return [
        {
            "id": r["id"],
            "job_id": r["job_id"],
            "name": r["name"],
            "file_name": r["file_name"],
            "char_count": len(r["text"]),
            "created_at": r["created_at"],
        }
        for r in db.list_resumes(job_id)
    ]


@app.post("/api/jobs/{job_id}/resumes")
async def upload_resumes(job_id: str, files: list[UploadFile] = File(...)) -> JSONResponse:
    _require_job(job_id)
    uploaded, errors = [], []

    for upload in files:
        file_name = upload.filename or "未命名文件"
        try:
            data = await upload.read()
            if len(data) > MAX_FILE_BYTES:
                raise parsers.ParseError(f"{file_name} 超过 10MB 大小限制")
            name, text = parsers.parse_resume(file_name, data)
            duplicate = db.find_resume_by_hash(job_id, db.text_hash(text))
            if duplicate:
                raise parsers.ParseError(
                    f"内容与已上传的《{duplicate['file_name']}》完全一致，已跳过"
                )
            record = db.add_resume(uuid.uuid4().hex[:12], job_id, name, file_name, text)
            uploaded.append(
                {
                    "id": record["id"],
                    "name": record["name"],
                    "file_name": record["file_name"],
                    "char_count": len(record["text"]),
                }
            )
        except parsers.ParseError as exc:
            errors.append({"file": file_name, "message": str(exc)})
        except Exception as exc:  # 单个文件失败不影响其余文件
            errors.append({"file": file_name, "message": f"处理失败：{exc}"})
        finally:
            await upload.close()

    return JSONResponse(
        status_code=200 if uploaded or not errors else 400,
        content={"uploaded": uploaded, "errors": errors},
    )


@app.get("/api/resumes/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: str) -> dict:
    resume = db.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    return {
        "id": resume["id"],
        "job_id": resume["job_id"],
        "name": resume["name"],
        "file_name": resume["file_name"],
        "char_count": len(resume["text"]),
        "created_at": resume["created_at"],
        "text": resume["text"],
    }


@app.delete("/api/resumes/{resume_id}", status_code=204)
def delete_resume(resume_id: str) -> Response:
    if not db.delete_resume(resume_id):
        raise HTTPException(status_code=404, detail="简历不存在")
    return Response(status_code=204)


# ----------------------------------------------------------------------- 筛选


@app.post("/api/jobs/{job_id}/screen", response_model=ScreenReport)
async def screen(job_id: str, payload: ScreenRequest | None = None) -> dict:
    job = _require_job(job_id)
    requested = payload.resume_ids if payload else []
    resumes = db.resume_inputs(job_id, requested)
    if not resumes:
        raise HTTPException(status_code=400, detail="没有可筛选的简历，请先上传简历")

    async def run_one(resume: dict) -> tuple[dict | None, str | None]:
        async with SEMAPHORE:
            try:
                result = await analyzer.analyze_resume(job, resume)
            except Exception as exc:
                return None, f"{resume['file_name']}：{exc}"

        db.save_result(
            {
                "id": uuid.uuid4().hex[:12],
                "job_id": job_id,
                "resume_id": resume["id"],
                "score": result["score"],
                "verdict": result["verdict"],
                "summary": result["summary"],
                "matched": result["matched"],
                "uncertain": result["uncertain"],
                "strengths": result["strengths"],
                "risks": result["risks"],
                "profile": result["profile"],
                "mode": result["mode"],
            }
        )
        return result, None

    outcomes = await asyncio.gather(*(run_one(r) for r in resumes))
    errors = [err for _result, err in outcomes if err]
    succeeded = len(outcomes) - len(errors)

    mode = config.AI_MODE
    if any(r["mode"] == "rule-fallback" for r, _ in outcomes if r):
        mode = "deepseek (部分降级)"

    return {
        "total": len(resumes),
        "succeeded": succeeded,
        "failed": len(errors),
        "errors": errors,
        "mode": mode,
    }


@app.get("/api/jobs/{job_id}/results", response_model=list[ScreeningResult])
def list_results(job_id: str) -> list[dict]:
    _require_job(job_id)
    return db.list_results(job_id)


@app.get("/api/results/{result_id}", response_model=ScreeningResult)
def get_result(result_id: str) -> dict:
    result = db.get_result(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="筛选结果不存在")
    return result


@app.patch("/api/results/{result_id}/decision", response_model=ScreeningResult)
def set_decision(result_id: str, payload: DecisionRequest) -> dict:
    """记录 HR 的人工决策与备注；重新筛选只更新分数与理由，不会覆盖这里的选择。"""
    result = db.set_decision(result_id, payload.decision, payload.note)
    if not result:
        raise HTTPException(status_code=404, detail="筛选结果不存在")
    return result


@app.patch("/api/jobs/{job_id}/decisions", response_model=BatchDecisionReport)
def set_decisions(job_id: str, payload: BatchDecisionRequest) -> dict:
    """批量标注：HR 一次过完一屏候选人时用。"""
    _require_job(job_id)
    updated = db.set_decisions(job_id, payload.result_ids, payload.decision, payload.note)
    return {"updated": updated}


@app.get("/api/jobs/{job_id}/stats", response_model=Stats)
def stats(job_id: str) -> dict:
    _require_job(job_id)
    return db.stats(job_id)


@app.delete("/api/jobs/{job_id}/results", status_code=204)
def clear_results(job_id: str) -> Response:
    _require_job(job_id)
    db.clear_results(job_id)
    return Response(status_code=204)


@app.get("/api/jobs/{job_id}/export.csv")
def export_csv(job_id: str) -> Response:
    job = _require_job(job_id)
    results = db.list_results(job_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    decision_labels = {"accepted": "已采纳", "rejected": "已拒绝"}
    verdict_labels = {"advance": "进入人工复核", "hold": "暂缓考虑"}
    writer.writerow(
        [
            "候选人", "简历文件", "匹配分", "建议", "人工决策", "人工备注", "标注时分数",
            "上次分数", "分数变化", "建议是否变化", "当前职位", "最高学历", "相关年限",
            "核心技能", "结论摘要", "符合条件", "待确认条件", "优势", "风险",
        ]
    )
    for r in results:
        profile = r.get("profile") or {}
        previous_score = r.get("previous_score")
        score_delta = r["score"] - previous_score if previous_score is not None else None
        previous_verdict = r.get("previous_verdict")
        verdict_changed = bool(previous_verdict and previous_verdict != r["verdict"])
        writer.writerow(
            [
                r["resume_name"],
                r["file_name"],
                r["score"],
                verdict_labels.get(r["verdict"], r["verdict"]),
                decision_labels.get(r.get("decision") or "", "未标注"),
                r.get("decision_note") or "",
                r.get("decision_score") if r.get("decision_score") is not None else "",
                previous_score if previous_score is not None else "",
                f"{score_delta:+d}" if score_delta is not None else "",
                (
                    f"{verdict_labels.get(previous_verdict, previous_verdict)} → "
                    f"{verdict_labels.get(r['verdict'], r['verdict'])}"
                    if verdict_changed
                    else "无"
                ),
                profile.get("current_title", ""),
                profile.get("highest_degree", ""),
                profile.get("years_of_experience") or "",
                "、".join(profile.get("key_skills") or []),
                r["summary"],
                "；".join(f"{m['requirement']}（{m['evidence']}）" for m in r["matched"]),
                "；".join(f"{u['requirement']}（{u['reason']}）" for u in r["uncertain"]),
                "；".join(r["strengths"]),
                "；".join(r["risks"]),
            ]
        )

    # BOM 让 Excel 正确识别 UTF-8 中文
    content = "\ufeff" + buffer.getvalue()
    safe_title = "".join(c for c in job["title"] if c.isalnum() or c in "-_") or "job"
    filename = f"{safe_title}-筛选结果.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote_filename(filename)}"},
    )


def quote_filename(name: str) -> str:
    from urllib.parse import quote

    return quote(name)


# ------------------------------------------------------------------- 演示数据


@app.post("/api/demo/seed")
async def seed_demo(
    screen_after: bool = Query(False, description="创建后是否立即执行筛选"),
) -> dict:
    """一键载入 samples/ 下的示例岗位与简历，方便面试现场演示。"""
    if not config.SAMPLES_DIR.exists():
        raise HTTPException(status_code=404, detail="samples 目录不存在")

    jd_file: Path | None = None
    for suffix in (".md", ".txt"):
        candidates = sorted(config.SAMPLES_DIR.glob(f"jd*{suffix}"))
        if candidates:
            jd_file = candidates[0]
            break
    if not jd_file:
        raise HTTPException(status_code=404, detail="samples 目录缺少 JD 示例文件")

    jd_text = jd_file.read_text(encoding="utf-8")
    parsed = rule_engine.parse_jd(jd_text)
    parsed["jd_text"] = jd_text

    existing = next((j for j in db.list_jobs() if j["title"] == parsed["title"]), None)
    if existing:
        job = existing
    else:
        # 大模型模式下用更准确的 JD 解析结果建岗位，保证技能条件与后续筛选口径一致
        if config.AI_MODE == "deepseek":
            refined = await analyzer.parse_jd(jd_text)
            if refined.get("title"):
                parsed.update(refined)
        job = db.create_job(uuid.uuid4().hex[:12], parsed)

    resume_files = [
        p
        for p in sorted(config.SAMPLES_DIR.glob("resume*"))
        if p.suffix.lower() in parsers.SUPPORTED_EXTENSIONS
    ]
    existing_names = {r["file_name"] for r in db.list_resumes(job["id"])}
    added = 0
    for path in resume_files:
        if path.name in existing_names:
            continue
        name, text = parsers.parse_resume(path.name, path.read_bytes())
        db.add_resume(uuid.uuid4().hex[:12], job["id"], name, path.name, text)
        added += 1

    report = None
    if screen_after and added:
        report = await screen(job["id"], ScreenRequest())

    return {
        "job_id": job["id"],
        "job_title": job["title"],
        "added_resumes": added,
        "total_resumes": len(db.list_resumes(job["id"])),
        "screen_report": report,
    }
