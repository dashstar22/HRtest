"""AI 模式自测：用本地 mock 的 OpenAI 兼容服务验证 DeepSeek 调用链路与降级逻辑。

用法：.venv\\Scripts\\python.exe scripts\\selftest_ai.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MOCK_ANALYSIS = {
    "candidate_name": "张明远",
    "current_title": "高级 AI 应用工程师",
    "years_of_experience": 8,
    "highest_degree": "硕士",
    "key_skills": ["Python", "FastAPI", "RAG"],
    "score": 88,
    "verdict": "advance",
    "summary": "后端经验扎实，RAG 落地经验与岗位高度契合，建议进入复核。",
    "matched": [
        {"requirement": "5 年以上后端经验", "evidence": "8 年后端开发经验"},
        {"requirement": "熟悉 FastAPI", "evidence": "基于 FastAPI + PostgreSQL 搭建服务"},
        # 故意给一条简历里不存在的“证据”，用于验证程序化核验
        {"requirement": "团队管理经验", "evidence": "带领 20 人团队完成平台重构"},
    ],
    "uncertain": [{"requirement": "团队管理经验", "reason": "简历未提及带团队规模"}],
    "strengths": ["有 RAG 线上落地经验", "大厂项目背景"],
    "risks": ["简历未说明离职原因"],
}

MOCK_JD = {
    "title": "高级 AI 应用工程师",
    "degree": "本科",
    "min_years": 5,
    "required_skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "Kubernetes"],
    "nice_skills": ["大模型", "RAG", "向量数据库"],
}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # 静默
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        prompt = "\n".join(message["content"] for message in payload.get("messages", []))
        content = MOCK_JD if "抽取结构化筛选条件" in prompt else MOCK_ANALYSIS

        body = json.dumps(
            {
                "id": "mock-completion",
                "object": "chat.completion",
                "model": payload.get("model", "mock"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)},
                        "finish_reason": "stop",
                    }
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "ai-test.db")
    os.environ["DEEPSEEK_API_KEY"] = "test-key"
    os.environ["DEEPSEEK_BASE_URL"] = f"http://127.0.0.1:{port}"
    os.environ["DEEPSEEK_MODEL"] = "mock-model"

    from fastapi.testclient import TestClient  # noqa: E402

    from app import config  # noqa: E402
    from app.main import app  # noqa: E402

    with TestClient(app) as client:
        status = client.get("/api/status").json()
        check("状态仅表示已配置大模型", status["mode"] == "deepseek" and status["configured"] and "已配置" in status["message"], status)

        jd_text = (ROOT / "samples" / "jd_ai_engineer.md").read_text(encoding="utf-8")
        parsed = client.post("/api/parse-jd", json={"jd_text": jd_text}).json()
        check("AI 解析 JD 走模型返回", parsed["min_years"] == 5 and "RAG" in parsed["nice_skills"], parsed)

        job = client.post(
            "/api/jobs",
            json={
                "title": parsed["title"],
                "department": "智能应用中心",
                "jd_text": jd_text,
                "degree": parsed["degree"],
                "min_years": parsed["min_years"],
                "required_skills": parsed["required_skills"],
                "nice_skills": parsed["nice_skills"],
            },
        ).json()

        resume_path = ROOT / "samples" / "resume_张明远.docx"
        upload = client.post(
            f"/api/jobs/{job['id']}/resumes",
            files=[("files", (resume_path.name, resume_path.read_bytes(), "application/octet-stream"))],
        ).json()
        check("上传成功", len(upload["uploaded"]) == 1, upload)

        report = client.post(f"/api/jobs/{job['id']}/screen", json={"resume_ids": []}).json()
        check("AI 筛选成功", report["succeeded"] == 1, report)

        results = client.get(f"/api/jobs/{job['id']}/results").json()
        result = results[0]
        check("结果标记为 deepseek 模式", result["mode"] == "deepseek", result["mode"])
        check("虚假证据触发保守分数", result["score"] <= 74, result["score"])
        check("虚假证据不保留推荐", result["verdict"] == "hold", result["verdict"])
        check("匹配项带完整原文证据", any(m["evidence"] == "基于 FastAPI + PostgreSQL 搭建服务" for m in result["matched"]), result["matched"])
        check("待确认项被保留", result["uncertain"][0]["reason"] == "简历未提及带团队规模", result["uncertain"])
        check("编造的证据被拦截", all(m["requirement"] != "团队管理经验" for m in result["matched"]), result["matched"])
        check(
            "被拦截的条目降级为待确认",
            any(u["requirement"] == "团队管理经验" for u in result["uncertain"]),
            result["uncertain"],
        )
        check("档案包含统一年限依据", result["profile"]["stated_years"] == 8.0 and bool(result["profile"]["evaluated_on"]), result["profile"])

        # 降级：把地址指向一个关闭的端口，应回退规则引擎且不中断
        config.DEEPSEEK_BASE_URL = "http://127.0.0.1:1"
        report2 = client.post(f"/api/jobs/{job['id']}/screen", json={"resume_ids": []}).json()
        check("接口异常时仍返回成功", report2["succeeded"] == 1 and report2["failed"] == 0, report2)
        fallback = client.get(f"/api/jobs/{job['id']}/results").json()[0]
        check("降级结果为 rule-fallback", fallback["mode"] == "rule-fallback", fallback["mode"])
        check("降级后仍有分数", isinstance(fallback["score"], int) and fallback["score"] > 0, fallback["score"])

    server.shutdown()
    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
