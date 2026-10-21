"""SQLite 持久化层：单文件数据库，零额外部署成本。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT '',
    jd_text TEXT NOT NULL,
    degree TEXT NOT NULL DEFAULT '不限',
    min_years REAL NOT NULL DEFAULT 0,
    required_skills TEXT NOT NULL DEFAULT '[]',
    nice_skills TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resumes (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    file_name TEXT NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id TEXT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    matched TEXT NOT NULL DEFAULT '[]',
    uncertain TEXT NOT NULL DEFAULT '[]',
    strengths TEXT NOT NULL DEFAULT '[]',
    risks TEXT NOT NULL DEFAULT '[]',
    profile TEXT NOT NULL DEFAULT '{}',
    mode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decision TEXT,
    decision_at TEXT,
    decision_score INTEGER,
    decision_note TEXT,
    stale INTEGER NOT NULL DEFAULT 0,
    previous_score INTEGER,
    previous_verdict TEXT,
    UNIQUE (job_id, resume_id)
);

CREATE INDEX IF NOT EXISTS idx_resumes_job ON resumes(job_id);
CREATE INDEX IF NOT EXISTS idx_results_job ON results(job_id);
"""


def _connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # 批量筛选时多个请求会并发写；WAL + busy_timeout 避免 database is locked
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """为旧版本数据库补齐新增列（Demo 升级时不丢已有数据）。"""
    result_columns = {row["name"] for row in conn.execute("PRAGMA table_info(results)")}
    result_additions = {
        "decision": "TEXT",
        "decision_at": "TEXT",
        "decision_score": "INTEGER",
        "decision_note": "TEXT",
        "stale": "INTEGER NOT NULL DEFAULT 0",
        "previous_score": "INTEGER",
        "previous_verdict": "TEXT",
    }
    for name, ddl in result_additions.items():
        if name not in result_columns:
            conn.execute(f"ALTER TABLE results ADD COLUMN {name} {ddl}")

    resume_columns = {row["name"] for row in conn.execute("PRAGMA table_info(resumes)")}
    if "content_hash" not in resume_columns:
        conn.execute("ALTER TABLE resumes ADD COLUMN content_hash TEXT")
        _backfill_hashes(conn)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_resumes_hash ON resumes(job_id, content_hash)")


def _backfill_hashes(conn: sqlite3.Connection) -> None:
    """给历史简历补内容指纹，让升级后的去重也能生效。"""
    rows = conn.execute("SELECT id, text FROM resumes WHERE content_hash IS NULL").fetchall()
    for row in rows:
        conn.execute(
            "UPDATE resumes SET content_hash = ? WHERE id = ?", (text_hash(row["text"]), row["id"])
        )


def text_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _json_load(value: str, fallback):
    try:
        return json.loads(value) if value else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def _job_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["required_skills"] = _json_load(data["required_skills"], [])
    data["nice_skills"] = _json_load(data["nice_skills"], [])
    data.setdefault("resume_count", 0)
    data.setdefault("screened_count", 0)
    return data


# --------------------------------------------------------------------------- jobs


def create_job(job_id: str, payload: dict) -> dict:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, title, department, jd_text, degree, min_years, "
            "required_skills, nice_skills, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                payload["title"],
                payload.get("department", ""),
                payload["jd_text"],
                payload.get("degree", "不限"),
                payload.get("min_years", 0),
                json.dumps(payload.get("required_skills", []), ensure_ascii=False),
                json.dumps(payload.get("nice_skills", []), ensure_ascii=False),
                now(),
            ),
        )
    return get_job(job_id)  # type: ignore[return-value]


def list_jobs() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT j.*,
                   (SELECT COUNT(*) FROM resumes r WHERE r.job_id = j.id) AS resume_count,
                   (SELECT COUNT(*) FROM results s WHERE s.job_id = j.id) AS screened_count
            FROM jobs j ORDER BY j.created_at DESC
            """
        ).fetchall()
    return [_job_row(r) for r in rows]


def get_job(job_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT j.*,
                   (SELECT COUNT(*) FROM resumes r WHERE r.job_id = j.id) AS resume_count,
                   (SELECT COUNT(*) FROM results s WHERE s.job_id = j.id) AS screened_count
            FROM jobs j WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
    return _job_row(row) if row else None


def update_job(job_id: str, payload: dict) -> dict | None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET title=?, department=?, jd_text=?, degree=?, min_years=?, "
            "required_skills=?, nice_skills=? WHERE id=?",
            (
                payload["title"],
                payload.get("department", ""),
                payload["jd_text"],
                payload.get("degree", "不限"),
                payload.get("min_years", 0),
                json.dumps(payload.get("required_skills", []), ensure_ascii=False),
                json.dumps(payload.get("nice_skills", []), ensure_ascii=False),
                job_id,
            ),
        )
    return get_job(job_id)


def delete_job(job_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return cur.rowcount > 0


# ------------------------------------------------------------------------ resumes


def add_resume(resume_id: str, job_id: str, name: str, file_name: str, text: str) -> dict:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO resumes (id, job_id, name, file_name, text, content_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (resume_id, job_id, name, file_name, text, text_hash(text), now()),
        )
    return get_resume(resume_id)  # type: ignore[return-value]


def find_resume_by_hash(job_id: str, content_hash: str) -> dict | None:
    """同一岗位下内容完全一致的简历视为重复投递。"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE job_id = ? AND content_hash = ?", (job_id, content_hash)
        ).fetchone()
    return dict(row) if row else None


def list_resumes(job_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM resumes WHERE job_id = ? ORDER BY created_at ASC", (job_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_resume(resume_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    return dict(row) if row else None


def delete_resume(resume_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
    return cur.rowcount > 0


def resume_inputs(job_id: str, resume_ids: list[str] | None = None) -> list[dict]:
    """取出待筛选简历：指定 id 时按 id 过滤，否则取该岗位全部。"""
    rows = list_resumes(job_id)
    if not resume_ids:
        return rows
    wanted = set(resume_ids)
    return [r for r in rows if r["id"] in wanted]


# ------------------------------------------------------------------------ results


def save_result(result: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO results (id, job_id, resume_id, score, verdict, summary, matched,
                                 uncertain, strengths, risks, profile, mode, created_at, stale,
                                 previous_score, previous_verdict)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,NULL,NULL)
            ON CONFLICT (job_id, resume_id) DO UPDATE SET
                previous_score=score,
                previous_verdict=verdict,
                score=excluded.score, verdict=excluded.verdict,
                summary=excluded.summary, matched=excluded.matched,
                uncertain=excluded.uncertain, strengths=excluded.strengths,
                risks=excluded.risks, profile=excluded.profile, mode=excluded.mode,
                created_at=excluded.created_at, stale=0
            """,
            (
                result["id"],
                result["job_id"],
                result["resume_id"],
                result["score"],
                result["verdict"],
                result["summary"],
                json.dumps(result["matched"], ensure_ascii=False),
                json.dumps(result["uncertain"], ensure_ascii=False),
                json.dumps(result["strengths"], ensure_ascii=False),
                json.dumps(result["risks"], ensure_ascii=False),
                json.dumps(result["profile"], ensure_ascii=False),
                result["mode"],
                now(),
            ),
        )


def _result_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("matched", "uncertain", "strengths", "risks"):
        data[key] = _json_load(data[key], [])
    data["profile"] = _json_load(data["profile"], {})
    data["stale"] = bool(data.get("stale"))
    return data


def list_results(job_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*, r.name AS resume_name, r.file_name AS file_name
            FROM results s JOIN resumes r ON r.id = s.resume_id
            WHERE s.job_id = ? ORDER BY s.score DESC, s.created_at ASC
            """,
            (job_id,),
        ).fetchall()
    return [_result_row(r) for r in rows]


def get_result(result_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT s.*, r.name AS resume_name, r.file_name AS file_name
            FROM results s JOIN resumes r ON r.id = s.resume_id WHERE s.id = ?
            """,
            (result_id,),
        ).fetchone()
    return _result_row(row) if row else None


def clear_results(job_id: str) -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM results WHERE job_id = ?", (job_id,))
    return cur.rowcount


def mark_stale(job_id: str) -> int:
    """岗位条件变更后，把已有结果标记为过期，但保留人工标注。"""
    with _connect() as conn:
        cur = conn.execute("UPDATE results SET stale = 1 WHERE job_id = ?", (job_id,))
    return cur.rowcount


def set_decision(
    result_id: str, decision: str | None, note: str | None = None
) -> dict | None:
    """记录 HR 的人工决策与备注，同时留存决策当时的分数，便于日后对比 AI 判断是否变化。"""
    with _connect() as conn:
        row = conn.execute("SELECT id FROM results WHERE id = ?", (result_id,)).fetchone()
        if row is None:
            return None
        cleaned = (note or "").strip()[:200] or None
        if decision in ("accepted", "rejected"):
            if note is None:
                # 未传备注时保留原备注，避免列表里的快捷标注把已写好的说明冲掉
                conn.execute(
                    "UPDATE results SET decision = ?, decision_at = ?, decision_score = score "
                    "WHERE id = ?",
                    (decision, now(), result_id),
                )
            else:
                conn.execute(
                    "UPDATE results SET decision = ?, decision_at = ?, decision_score = score, "
                    "decision_note = ? WHERE id = ?",
                    (decision, now(), cleaned, result_id),
                )
        else:
            conn.execute(
                "UPDATE results SET decision = NULL, decision_at = NULL, decision_score = NULL, "
                "decision_note = NULL WHERE id = ?",
                (result_id,),
            )
    return get_result(result_id)


def set_decisions(
    job_id: str,
    result_ids: list[str],
    decision: str | None,
    note: str | None = None,
) -> int:
    """批量标注；只影响属于该岗位的结果，避免跨岗位误改。"""
    if not result_ids:
        return 0
    cleaned = (note or "").strip()[:200] or None
    placeholders = ",".join("?" for _ in result_ids)
    with _connect() as conn:
        if decision in ("accepted", "rejected"):
            cur = conn.execute(
                f"UPDATE results SET decision = ?, decision_at = ?, decision_score = score, "
                f"decision_note = COALESCE(?, decision_note) WHERE job_id = ? AND id IN ({placeholders})",
                (decision, now(), cleaned, job_id, *result_ids),
            )
        else:
            cur = conn.execute(
                f"UPDATE results SET decision = NULL, decision_at = NULL, decision_score = NULL, "
                f"decision_note = NULL WHERE job_id = ? AND id IN ({placeholders})",
                (job_id, *result_ids),
            )
    return cur.rowcount


def stats(job_id: str) -> dict:
    results = list_results(job_id)
    total = len(results)
    advance = sum(1 for r in results if r["verdict"] == "advance")
    average = round(sum(r["score"] for r in results) / total, 1) if total else 0
    changed = sum(
        1
        for r in results
        if r["previous_score"] is not None
        and (r["previous_score"] != r["score"] or r["previous_verdict"] != r["verdict"])
    )
    return {
        "total": len(list_resumes(job_id)),
        "screened": total,
        "advance": advance,
        "hold": total - advance,
        "avg_score": average,
        "accepted": sum(1 for r in results if r["decision"] == "accepted"),
        "rejected": sum(1 for r in results if r["decision"] == "rejected"),
        "changed": changed,
    }


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
