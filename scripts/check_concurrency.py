"""并发竞态回归：批量筛选进行中删除简历，不应让整批请求失败。

背景：筛选是并发的，AI 分析一份要几秒。若这期间简历被删除，
      写结果时会违反外键约束。修复前整个 /screen 请求返回 500，
      修复后应返回 200，并把那一份记为失败、给出可读原因。

用法：.venv\\Scripts\\python.exe scripts\\check_concurrency.py
注意：会真实调用大模型 2 次（同时上传两份简历做对比），耗时约 5-10 秒。
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8000"

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail="") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {detail}")


def call(path: str, payload=None, method: str = "POST", timeout: int = 300):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    return json.load(urllib.request.urlopen(request, timeout=timeout))


def upload(job_id: str, path: Path):
    boundary = "----dsh" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{path.name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        BASE + f"/api/jobs/{job_id}/resumes",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return json.load(urllib.request.urlopen(request, timeout=120))


def main() -> int:
    job = call(
        "/api/jobs",
        {
            "title": "并发测试岗位",
            "department": "",
            "jd_text": "任职要求：本科及以上学历，3 年以上 Python 开发经验。",
            "degree": "本科",
            "min_years": 3,
            "required_skills": ["Python"],
            "nice_skills": [],
        },
    )

    victim = upload(job["id"], ROOT / "samples" / "extra" / "resume_赵磊.pdf")["uploaded"][0]
    keeper = upload(job["id"], ROOT / "samples" / "resume_张明远.docx")["uploaded"][0]
    print(f"临时岗位简历：{victim['name']}、{keeper['name']}")

    result: dict = {}

    def run_screen() -> None:
        started = time.time()
        try:
            result["report"] = call(f"/api/jobs/{job['id']}/screen")
            result["status"] = 200
        except urllib.error.HTTPError as exc:
            result["status"] = exc.code
            result["body"] = exc.read().decode("utf-8", "ignore")[:300]
        result["elapsed"] = time.time() - started

    def delete_during_screen() -> None:
        time.sleep(1.5)
        request = urllib.request.Request(f"{BASE}/api/resumes/{victim['id']}", method="DELETE")
        urllib.request.urlopen(request)
        result["deleted"] = True

    threads = [threading.Thread(target=run_screen), threading.Thread(target=delete_during_screen)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    report = result.get("report") or {}
    print(f"screen: HTTP {result.get('status')} 耗时 {result.get('elapsed', 0):.1f}s -> {report}")

    check("删除简历不会让整批请求 500", result.get("status") == 200, result.get("body"))
    check("被删简历记为失败", report.get("failed") == 1, report)
    check("其余简历正常完成", report.get("succeeded") == 1, report)
    check(
        "失败原因可读",
        any("简历或岗位已被删除" in err for err in report.get("errors", [])),
        report.get("errors"),
    )

    remaining = json.load(urllib.request.urlopen(f"{BASE}/api/jobs/{job['id']}/resumes"))
    check("被删简历不再出现在列表中", [r["name"] for r in remaining] == [keeper["name"]], remaining)

    urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/jobs/{job['id']}", method="DELETE"))
    print("\n临时岗位已清理")
    print(f"结果：{PASS} 通过，{FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
