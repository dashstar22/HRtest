"""可信度回归：合成异常输出、固定日期、独立临时库；不调用真实模型。"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "credibility.db")

from fastapi.testclient import TestClient
from app import analyzer, config, policies, prompts, rule_engine
from app.main import app

JD = {"title": "Python工程师", "jd_text": "原始要求：20年经验，必须Django和PostgreSQL。",
      "degree": "本科", "min_years": 3,
      "required_skills": ["Python", "FastAPI 或 Django", "PostgreSQL 或 MySQL"], "nice_skills": []}
TEXT = "姓名：测试甲\n学历：本科\n自述：3年后端开发经验\n技能：Python、FastAPI、MySQL。"
RAW = {"score": 90, "verdict": "advance", "summary": "符合所有要求",
       "highest_degree": "本科", "years_of_experience": 99,
       "matched": [{"requirement": "Python", "evidence": "技能：Python、FastAPI、MySQL。"}],
       "uncertain": [], "strengths": [], "risks": []}


class CredibilityTests(unittest.TestCase):
    def result(self):
        return analyzer.normalize_result(copy.deepcopy(RAW), "测试甲")

    def test_fabricated_suffix_rejected(self):
        r = self.result()
        r["matched"] = [{"requirement": "Kubernetes", "evidence": "负责Python后端开发与接口实现，并主导生产集群建设"}]
        r = analyzer.verify_evidence(r, "负责Python后端开发与接口实现，未接触Kubernetes")
        self.assertEqual(r["matched"], [])
        self.assertEqual(r["verdict"], "hold")
        self.assertLessEqual(r["score"], 74)

        self.assertNotIn("符合所有要求", r["summary"])

    def test_located_quote_restores_original(self):
        r = self.result()
        r["matched"] = [{"requirement": "Python", "evidence": "python后端开发"}]
        r = analyzer.verify_evidence(r, "负责 Python 后端\n开发。")
        self.assertEqual(r["matched"][0]["evidence"], "Python 后端\n开发")

    def test_punctuation_cannot_invert_quote(self):
        r = self.result()
        r["matched"] = [{"requirement": "Python", "evidence": "不会Python"}]
        self.assertFalse(analyzer.verify_evidence(r, "不会，Python？")["matched"])

    def test_negative_and_unknown_verdicts(self):
        for verdict in ["不推荐", "无需复核", "not recommended", "bypass", "not advance", "未知"]:
            with self.subTest(verdict=verdict):
                r = analyzer.normalize_result({**RAW, "verdict": verdict}, "测试")
                self.assertEqual(r["verdict"], "hold")
                self.assertLessEqual(r["score"], 74)

    def test_low_score_cannot_advance(self):
        r = analyzer.normalize_result({**RAW, "score": 10}, "测试")
        self.assertEqual(r["verdict"], "hold")
        self.assertNotIn("符合所有要求", r["summary"])

    def test_negative_low_score_rewrites_conflicting_summary(self):
        r = analyzer.normalize_result({**RAW, "score": 20, "verdict": "不推荐"}, "测试")
        self.assertEqual(r["score"], 20)
        self.assertEqual(r["verdict"], "hold")
        self.assertNotIn("符合所有要求", r["summary"])

    def test_rule_or_requires_only_one_member(self):
        r = rule_engine.analyze(JD, "测试", TEXT)
        self.assertEqual(r["verdict"], "advance")
        self.assertFalse(r["uncertain"])
        self.assertTrue(all(m["evidence"] in TEXT for m in r["matched"]))

    def test_or_neither_member_is_uncertain(self):
        r = rule_engine.analyze(JD, "测试", TEXT.replace("FastAPI", "Flask"))
        self.assertEqual(r["verdict"], "hold")
        self.assertTrue(any("FastAPI 或 Django" in u["requirement"] for u in r["uncertain"]))

    def test_rule_parsing_preserves_groups_and_bonus(self):
        p = rule_engine.parse_jd("岗位名称：后端工程师\n要求：本科，3年开发经验，Python，FastAPI或Django，PostgreSQL/MySQL。Redis为加分项。")
        self.assertIn("FastAPI 或 Django", p["required_skills"])
        self.assertIn("PostgreSQL 或 MySQL", p["required_skills"])
        self.assertNotIn("redis", p["required_skills"])
        self.assertIn("redis", p["nice_skills"])

    def test_group_does_not_override_saved_conditions(self):
        r = rule_engine.analyze({**JD, "required_skills": ["FastAPI", "Django"]}, "测试", TEXT)
        self.assertEqual(r["verdict"], "hold")
        msg = prompts.build_analysis_messages(JD, "虚构.txt", TEXT)[1]["content"]
        self.assertIn("与原JD冲突时以上述条件为准", msg)

    def test_ci_cd_is_not_an_or_group(self):
        self.assertEqual(policies.group_alternatives(["ci/cd"], "熟悉CI/CD"), ["ci/cd"])

    def test_stated_and_dates_conflict(self):
        f = policies.experience_facts("8年后端开发经验\n工作经历\n2016.07 - 至今 公司A\n专业技能\nPython", date(2026, 10, 21))
        self.assertTrue(f["experience_conflict"])
        self.assertIsNone(f["years_of_experience"])
        self.assertEqual(f["evaluated_on"], "2026-10-21")
        self.assertEqual(f["stated_years"], 8)
        self.assertEqual(f["calculated_work_years"], 10.25)

    def test_overlapping_jobs_are_not_double_counted(self):
        f = policies.experience_facts("3年工作经验\n工作经历\n2020.01 - 2021.12 公司A\n2021.01 - 2022.12 公司B\n专业技能", date(2023, 1, 1))
        self.assertEqual(f["calculated_work_years"], 3)
        self.assertEqual(f["years_of_experience"], 3)

    def test_education_dates_do_not_count(self):
        f = policies.experience_facts("教育背景\n2010.01 - 2020.01 学校", date(2026, 10, 21))
        self.assertIsNone(f["calculated_work_years"])
        self.assertIsNone(f["years_of_experience"])

    def test_model_years_cannot_override_conflict(self):
        text = "本科，Python、FastAPI、MySQL，3年后端经验\n工作经历\n2010.01 - 至今 公司A\n专业技能"
        facts = policies.experience_facts(text, date(2026, 10, 21))
        r = analyzer.enforce_conditions(self.result(), JD, text, facts)
        self.assertIsNone(r["profile"]["years_of_experience"])
        self.assertEqual(r["verdict"], "hold")
        self.assertNotIn("符合所有要求", r["summary"])

    def test_unknown_years_and_degree_cannot_advance(self):
        text = "熟悉Python、FastAPI、MySQL。"
        r = analyzer.enforce_conditions(self.result(), JD, text, policies.experience_facts(text))
        self.assertEqual(r["verdict"], "hold")
        self.assertGreaterEqual(len(r["uncertain"]), 2)

    def test_hard_uncertainty_cannot_keep_high_score(self):
        r = self.result()
        r["uncertain"] = [{"requirement": "Python精通程度", "reason": "只有技能罗列"}]
        r = analyzer.enforce_conditions(r, JD, TEXT, policies.experience_facts(TEXT))
        self.assertEqual(r["verdict"], "hold")
        self.assertLessEqual(r["score"], 74)
        self.assertFalse(any("Python" in m["requirement"] for m in r["matched"]))

    def test_http_persistence_priority_stats_and_rescreen(self):
        with TestClient(app) as c, patch.object(config, "AI_MODE", "deepseek"), patch.object(analyzer, "_call_deepseek", AsyncMock(return_value=copy.deepcopy(RAW))):
            job = c.post("/api/jobs", json=JD).json()
            jid = job["id"]
            c.post(f"/api/jobs/{jid}/resumes", files=[("files", ("虚构.txt", TEXT.encode(), "text/plain"))])
            stats = c.get(f"/api/jobs/{jid}/stats").json()
            self.assertEqual((stats["total"], stats["screened"]), (1, 0))
            c.post(f"/api/jobs/{jid}/screen")
            first = c.get(f"/api/jobs/{jid}/results").json()[0]
            self.assertEqual(first["verdict"], "advance")
            self.assertEqual(first["profile"]["years_of_experience"], 3)
            self.assertEqual(first["score"], 90)
            self.assertIsNone(first["previous_score"])
            c.patch(f"/api/results/{first['id']}/decision", json={"decision": "accepted", "note": "回归验证备注"})
            c.put(f"/api/jobs/{jid}", json={**JD, "min_years": 20})
            stale = c.get(f"/api/jobs/{jid}/results").json()[0]
            self.assertTrue(stale["stale"])
            c.post(f"/api/jobs/{jid}/screen")
            final = c.get(f"/api/jobs/{jid}/results").json()[0]
            self.assertEqual(final["verdict"], "hold")
            self.assertLessEqual(final["score"], 74)
            self.assertEqual(final["id"], first["id"])
            self.assertEqual(final["previous_score"], 90)
            self.assertEqual(final["decision_score"], 90)
            self.assertEqual(final["decision_note"], "回归验证备注")
            self.assertFalse(final["stale"])
            self.assertIn("回归验证备注", c.get(f"/api/jobs/{jid}/export.csv").text)
            self.assertTrue(final["profile"]["experience_basis"])
            self.assertEqual(c.get(f"/api/jobs/{jid}/stats").json()["changed"], 1)

    def test_mock_jd_parser_preserves_or(self):
        import asyncio
        raw = {"title": "测试", "required_skills": ["FastAPI", "Django", "PostgreSQL", "MySQL"]}
        with patch.object(config, "AI_MODE", "deepseek"), patch.object(analyzer, "_call_deepseek", AsyncMock(return_value=raw)):
            parsed = asyncio.run(analyzer.parse_jd("熟悉FastAPI或Django，以及PostgreSQL/MySQL"))
        self.assertEqual(parsed["required_skills"], ["FastAPI 或 Django", "PostgreSQL 或 MySQL"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
