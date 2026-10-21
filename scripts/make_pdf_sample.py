"""生成一份中文 PDF 简历，用于验证 PDF 解析链路与现场演示。

产物放在 samples/extra/ 下：该目录不会被「载入示例数据」自动载入，
需要演示 PDF 支持时手动上传即可。

用法：.venv\\Scripts\\python.exe scripts\\make_pdf_sample.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "samples" / "extra" / "resume_赵磊.pdf"

FONT_CANDIDATES = [
    ("MSYH", "C:/Windows/Fonts/msyh.ttc"),
    ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
]

RESUME = {
    "name": "赵磊",
    "meta": "男 | 28 岁 | 深圳 | 186-0000-0005 | zhaolei@example.com",
    "intent": "求职意向：Python 后端开发工程师",
    "sections": [
        (
            "教育背景",
            [
                "2014.09 - 2018.06  深圳大学  软件工程  本科",
            ],
        ),
        (
            "工作经历",
            [
                "2020.05 - 至今   某数据服务公司   Python 开发工程师",
                "- 负责数据采集与清洗平台，技术栈 Python + Flask + MySQL + Redis；",
                "- 使用 Pandas 处理日均 200 万条日志数据，报表产出时间缩短 40%；",
                "- 使用 Docker 部署服务，GitLab CI 完成自动化发布。",
                "2018.07 - 2020.04   某互联网公司   Java 开发工程师",
                "- 参与订单系统开发，技术栈 Spring Boot + MySQL。",
            ],
        ),
        (
            "专业技能",
            [
                "- 熟练 Python、Flask、MySQL、Redis、Docker、Pandas；",
                "- 了解 Kubernetes 基本概念；",
                "- 英语 CET-6，可阅读英文技术文档。",
            ],
        ),
        (
            "自我评价",
            [
                "5 年后端开发经验，偏数据处理方向，做事踏实，正在学习大模型应用开发。",
            ],
        ),
    ],
}


def register_fonts() -> str:
    for name, path in FONT_CANDIDATES:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
            return name
    raise SystemExit("未找到可用的中文字体，无法生成 PDF 样例")


def build(font_name: str) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="赵磊-简历",
        author="赵磊",
    )

    base = ParagraphStyle("base", fontName=font_name, fontSize=10.5, leading=17, alignment=TA_LEFT)
    title = ParagraphStyle("title", parent=base, fontSize=20, leading=28, spaceAfter=4)
    meta = ParagraphStyle("meta", parent=base, fontSize=9.5, textColor="#555555", spaceAfter=10)
    heading = ParagraphStyle("heading", parent=base, fontSize=12, leading=20, spaceBefore=10, spaceAfter=4)

    story = [
        Paragraph(RESUME["name"], title),
        Paragraph(RESUME["meta"], meta),
        Paragraph(RESUME["intent"], base),
    ]
    for section, lines in RESUME["sections"]:
        story.append(Paragraph(section, heading))
        for line in lines:
            story.append(Paragraph(line, base))
    story.append(Spacer(1, 6))

    document.build(story)
    print(f"generated {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build(register_fonts())
