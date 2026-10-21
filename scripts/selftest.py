"""端到端自测：不依赖浏览器与真实 API Key，直接走一遍 HTTP 流程。

用法：.venv\\Scripts\\python.exe scripts\\selftest.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "selftest.db")
os.environ["DEEPSEEK_API_KEY"] = ""  # 强制规则模式，保证离线可测

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {detail}")


def main() -> int:
    with TestClient(app) as client:
        # 1. 状态
        status = client.get("/api/status").json()
        check("状态接口为规则模式", status["mode"] == "rule", str(status))

        # 2. 首页
        page = client.get("/")
        check("首页可访问", page.status_code == 200 and "AI 招聘简历智能筛选助手" in page.text)

        # 3. JD 解析
        jd_text = (ROOT / "samples" / "jd_ai_engineer.md").read_text(encoding="utf-8")
        parsed = client.post("/api/parse-jd", json={"jd_text": jd_text}).json()
        print("  parsed jd:", json.dumps(parsed, ensure_ascii=False))
        check("JD 识别学历为本科", parsed["degree"] == "本科", parsed["degree"])
        check("JD 识别年限为 5", parsed["min_years"] == 5, parsed["min_years"])
        check("JD 识别必备技能", len(parsed["required_skills"]) >= 4, parsed["required_skills"])

        # 4. 创建岗位
        created = client.post(
            "/api/jobs",
            json={
                "title": parsed["title"] or "高级 AI 应用工程师",
                "department": "智能应用中心",
                "jd_text": jd_text,
                "degree": parsed["degree"],
                "min_years": parsed["min_years"],
                "required_skills": parsed["required_skills"],
                "nice_skills": parsed["nice_skills"],
            },
        )
        check("创建岗位", created.status_code == 201, created.text)
        job_id = created.json()["id"]

        # 5. 上传简历
        files = [
            (
                "files",
                (
                    path.name,
                    path.read_bytes(),
                    "application/octet-stream",
                ),
            )
            for path in sorted((ROOT / "samples").glob("resume*"))
        ]
        uploaded = client.post(f"/api/jobs/{job_id}/resumes", files=files)
        payload = uploaded.json()
        print("  uploaded:", json.dumps(payload, ensure_ascii=False))
        check("上传并解析 4 份简历", len(payload["uploaded"]) == 4, payload)
        check("上传无错误", payload["errors"] == [], payload["errors"])

        # 6. 批量筛选
        report = client.post(f"/api/jobs/{job_id}/screen", json={"resume_ids": []}).json()
        check("筛选全部成功", report["succeeded"] == 4 and report["failed"] == 0, report)

        # 7. 结果
        results = client.get(f"/api/jobs/{job_id}/results").json()
        check("返回 4 条结果", len(results) == 4)
        scores = [r["score"] for r in results]
        check("结果按分数降序", scores == sorted(scores, reverse=True), scores)
        for r in results:
            profile = r["profile"]
            print(
                f"  {r['resume_name']:<6} {r['score']:>3} 分  {r['verdict']:<8}"
                f" {profile.get('highest_degree')}/{(profile.get('years_of_experience'))}年"
                f"  matched={len(r['matched'])} uncertain={len(r['uncertain'])}"
            )
            print(f"        {r['summary']}")

        # 8. 详情 + 原文
        detail = client.get(f"/api/results/{results[0]['id']}")
        check("结果详情可访问", detail.status_code == 200)
        resume_detail = client.get(f"/api/resumes/{results[0]['resume_id']}").json()
        check("简历原文可读取", "Python" in resume_detail["text"] or "Vue" in resume_detail["text"])

        # 9. 统计
        stats = client.get(f"/api/jobs/{job_id}/stats").json()
        check("统计口径一致", stats["total"] == 4 and stats["advance"] + stats["hold"] == 4, stats)

        # 10. 导出
        exported = client.get(f"/api/jobs/{job_id}/export.csv")
        check("CSV 导出成功", exported.status_code == 200 and "候选人" in exported.text)
        check("CSV 包含人工决策列", "人工决策" in exported.text)

        # 11. 演示数据接口
        seeded = client.post("/api/demo/seed")
        check("示例数据接口可用", seeded.status_code == 200, seeded.text)

        # 12. 人工标注：备注、快捷标注、批量、跨岗位隔离
        target = results[0]
        decided = client.patch(
            f"/api/results/{target['id']}/decision",
            json={"decision": "accepted", "note": "沟通后确认 2 周内到岗"},
        )
        check(
            "标注并保存备注",
            decided.status_code == 200 and decided.json()["decision_note"] == "沟通后确认 2 周内到岗",
            decided.json(),
        )
        check("记录标注时分数", decided.json()["decision_score"] == target["score"], decided.json())

        quick = client.patch(f"/api/results/{target['id']}/decision", json={"decision": "accepted"})
        check("快捷标注不清空备注", quick.json()["decision_note"] == "沟通后确认 2 周内到岗", quick.json())

        stats_after = client.get(f"/api/jobs/{job_id}/stats").json()
        check("统计包含采纳数", stats_after["accepted"] == 1, stats_after)

        others = [r["id"] for r in results[1:]]
        batch = client.patch(
            f"/api/jobs/{job_id}/decisions",
            json={"result_ids": others, "decision": "rejected"},
        ).json()
        check("批量标注生效", batch["updated"] == 3, batch)
        stats_batch = client.get(f"/api/jobs/{job_id}/stats").json()
        check(
            "统计反映批量结果",
            stats_batch["accepted"] == 1 and stats_batch["rejected"] == 3,
            stats_batch,
        )

        other_job = client.post(
            "/api/jobs",
            json={
                "title": "隔离测试岗位",
                "department": "",
                "jd_text": "任职要求：本科及以上学历，3 年以上 Python 开发经验。",
                "degree": "本科",
                "min_years": 3,
                "required_skills": ["python"],
                "nice_skills": [],
            },
        ).json()
        isolated = client.patch(
            f"/api/jobs/{other_job['id']}/decisions",
            json={"result_ids": [target["id"]], "decision": "accepted"},
        ).json()
        check("批量标注不跨岗位生效", isolated["updated"] == 0, isolated)
        client.delete(f"/api/jobs/{other_job['id']}")

        # 13. 改 JD → 结果过期 → 重新筛选，标注、备注、标注时分数都要保留
        updated = client.put(
            f"/api/jobs/{job_id}",
            json={
                "title": parsed["title"],
                "department": "智能应用中心",
                "jd_text": jd_text,
                "degree": parsed["degree"],
                "min_years": 8,
                # 日期冲突时年限已保守封顶；增加明确未覆盖技能来验证变化追踪。
                "required_skills": parsed["required_skills"] + ["测试缺失技能A", "测试缺失技能B", "测试缺失技能C"],
                "nice_skills": parsed["nice_skills"],
            },
        )
        check("修改岗位条件", updated.status_code == 200, updated.text)

        stale_results = client.get(f"/api/jobs/{job_id}/results").json()
        check("改 JD 后结果标记为过期", all(r["stale"] for r in stale_results), stale_results)
        check(
            "改 JD 后人工标注保留",
            any(r["decision"] == "accepted" for r in stale_results),
            stale_results,
        )

        rescreeened = client.post(f"/api/jobs/{job_id}/screen", json={"resume_ids": []}).json()
        check("重新筛选成功", rescreeened["succeeded"] == 4, rescreeened)
        refreshed = client.get(f"/api/jobs/{job_id}/results").json()
        check("重新筛选后过期标记清除", all(not r["stale"] for r in refreshed))
        kept = next((r for r in refreshed if r["id"] == target["id"]), None)
        check("重新筛选后结果 id 保持稳定", kept is not None, [r["id"] for r in refreshed])
        check("重新筛选后人工标注保留", kept is not None and kept["decision"] == "accepted", kept)
        check(
            "重新筛选后备注保留",
            kept is not None and kept["decision_note"] == "沟通后确认 2 周内到岗",
            kept,
        )
        check(
            "重新筛选后仍保留标注时分数",
            kept is not None and kept["decision_score"] == target["score"],
            kept,
        )
        check(
            "重新筛选后记录上次分数",
            kept is not None and kept["previous_score"] is not None,
            kept,
        )
        stats_changed = client.get(f"/api/jobs/{job_id}/stats").json()
        check("统计能反映变化人数", stats_changed["changed"] >= 1, stats_changed)

        # 14. 简历去重：同一份内容再次上传应被拦截
        sample_resume = sorted((ROOT / "samples").glob("resume*"))[0]
        duplicate = client.post(
            f"/api/jobs/{job_id}/resumes",
            files=[("files", (sample_resume.name, sample_resume.read_bytes(), "application/octet-stream"))],
        ).json()
        check(
            "重复简历被拦截",
            duplicate["uploaded"] == [] and "完全一致" in duplicate["errors"][0]["message"],
            duplicate,
        )

        cleared = client.patch(f"/api/results/{target['id']}/decision", json={"decision": None})
        check("撤销标注", cleared.status_code == 200 and cleared.json()["decision"] is None)
        check("撤销后备注一并清空", cleared.json()["decision_note"] is None, cleared.json())

        # 15. PDF 解析（样例在 samples/extra，不参与「载入示例数据」）
        pdf_path = ROOT / "samples" / "extra" / "resume_赵磊.pdf"
        check("PDF 样例存在", pdf_path.exists(), str(pdf_path))
        if pdf_path.exists():
            pdf_job = client.post(
                "/api/jobs",
                json={
                    "title": "PDF 解析验证岗位",
                    "department": "",
                    "jd_text": "任职要求：本科及以上学历，3 年以上 Python 开发经验，熟悉 Flask。",
                    "degree": "本科",
                    "min_years": 3,
                    "required_skills": ["Python", "Flask"],
                    "nice_skills": [],
                },
            ).json()
            pdf_upload = client.post(
                f"/api/jobs/{pdf_job['id']}/resumes",
                files=[("files", (pdf_path.name, pdf_path.read_bytes(), "application/pdf"))],
            ).json()
            check("PDF 简历可解析", len(pdf_upload["uploaded"]) == 1, pdf_upload)
            if pdf_upload["uploaded"]:
                check(
                    "PDF 中姓名提取正确",
                    pdf_upload["uploaded"][0]["name"] == "赵磊",
                    pdf_upload["uploaded"][0],
                )
                pdf_detail = client.get(f"/api/resumes/{pdf_upload['uploaded'][0]['id']}").json()
                check(
                    "PDF 正文包含关键经历",
                    "深圳大学" in pdf_detail["text"] and "Flask" in pdf_detail["text"],
                    pdf_detail["text"][:120],
                )
            client.delete(f"/api/jobs/{pdf_job['id']}")

        # 15.1 扫描件（图片型 PDF）应被识别并给出处理建议
        scanned_path = ROOT / "samples" / "extra" / "resume_扫描件示例.pdf"
        check("扫描件样例存在", scanned_path.exists(), str(scanned_path))
        if scanned_path.exists():
            scanned = client.post(
                f"/api/jobs/{job_id}/resumes",
                files=[("files", (scanned_path.name, scanned_path.read_bytes(), "application/pdf"))],
            ).json()
            check(
                "扫描件被识别并给出处理建议",
                scanned["uploaded"] == [] and "扫描件" in scanned["errors"][0]["message"],
                scanned,
            )

        # 16. 不支持的文件类型
        bad = client.post(
            f"/api/jobs/{job_id}/resumes",
            files=[("files", ("a.doc", b"xx", "application/octet-stream"))],
        )
        check("旧版 doc 有友好提示", bad.json()["errors"][0]["message"].startswith("暂不支持"))

        # 16. 删除岗位级联
        deleted = client.delete(f"/api/jobs/{job_id}")
        check("删除岗位返回 204", deleted.status_code == 204)
        check("岗位删除后结果清空", client.get(f"/api/jobs/{job_id}").status_code == 404)

    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
