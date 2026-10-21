"""生成 samples/ 下的示例 Word 简历（可重复执行，覆盖同名文件）。

用法：.venv\\Scripts\\python.exe scripts\\make_samples.py
"""

from pathlib import Path

import docx
from docx.shared import Pt

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

RESUMES = {
    "resume_张明远.docx": {
        "header": ["姓名：张明远", "男 | 31 岁", "上海", "138-0000-0000"],
        "intent": "高级 AI 应用工程师",
        "sections": [
            (
                "教育背景",
                [
                    "2013.09 - 2016.06  华东师范大学  计算机技术  硕士",
                    "2009.09 - 2013.06  华东师范大学  软件工程  本科",
                ],
            ),
            (
                "工作经历",
                [
                    "2021.07 - 至今   某互联网科技有限公司   高级后端工程师",
                    "- 负责企业知识库问答产品后端，基于 FastAPI + PostgreSQL 搭建服务，QPS 峰值 3000；",
                    "- 主导 RAG 检索增强链路设计，接入 Milvus 向量数据库，答案准确率从 61% 提升到 84%；",
                    "- 使用 Docker + Kubernetes 完成服务容器化与灰度发布，发布耗时下降 70%；",
                    "- 负责 Prompt Engineering 规范制定，沉淀 30+ 业务提示词模板。",
                    "2016.07 - 2021.06   某金融科技公司   Python 后端工程师",
                    "- 使用 Django 开发信贷审批系统，服务日均 20 万笔申请；",
                    "- 负责 MySQL 慢查询治理，核心接口 P99 从 800ms 降到 120ms；",
                    "- 引入 Redis 缓存与 Kafka 消息队列，支撑大促流量。",
                ],
            ),
            (
                "专业技能",
                [
                    "- 精通 Python，熟悉 FastAPI、Django、Flask；",
                    "- 熟悉 PostgreSQL、MySQL、Redis、Kafka；",
                    "- 熟悉 Docker、Kubernetes、GitLab CI；",
                    "- 熟悉大模型应用开发：RAG、Agent、Prompt Engineering、向量数据库（Milvus、pgvector）。",
                ],
            ),
            ("自我评价", ["8 年后端开发经验，其中 3 年 AI 应用落地经验；带过 4 人小组，沟通与推进能力强。"]),
        ],
    },
    "resume_王浩.docx": {
        "header": ["姓名：王浩", "男 | 25 岁", "上海", "199-0000-0003"],
        "intent": "前端开发工程师",
        "sections": [
            ("教育背景", ["2019.09 - 2022.06  上海某职业技术学院  计算机应用技术  大专"]),
            (
                "工作经历",
                [
                    "2022.07 - 至今   某广告营销公司   前端开发工程师",
                    "- 使用 Vue3 + TypeScript 开发营销活动页面，累计上线 40+ 活动；",
                    "- 负责 H5 性能优化，首屏加载从 3.2s 降到 1.4s；",
                    "- 使用 Node.js 编写活动抽奖接口，配合 Redis 做库存扣减。",
                ],
            ),
            (
                "专业技能",
                [
                    "- 熟练掌握 Vue、TypeScript、JavaScript、HTML、CSS；",
                    "- 了解 Node.js、Express，能独立完成小型全栈项目。",
                ],
            ),
            ("自我评价", ["3 年前端开发经验，学习能力强，对 AI 产品有浓厚兴趣。"]),
        ],
    },
}


def build(resume: dict, path: Path) -> None:
    document = docx.Document()

    title = document.add_heading(resume["header"][0], level=1)
    for run in title.runs:
        run.font.size = Pt(20)

    table = document.add_table(rows=1, cols=len(resume["header"]))
    table.style = "Table Grid"
    for index, text in enumerate(resume["header"]):
        table.rows[0].cells[index].text = text

    if resume.get("intent"):
        document.add_paragraph(f"求职意向：{resume['intent']}")

    for heading, lines in resume["sections"]:
        paragraph = document.add_paragraph()
        run = paragraph.add_run(heading)
        run.bold = True
        run.font.size = Pt(13)
        for line in lines:
            document.add_paragraph(line)

    document.save(path)


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    for file_name, resume in RESUMES.items():
        target = SAMPLES / file_name
        build(resume, target)
        print(f"generated {target.name} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
