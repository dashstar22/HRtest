"""生成一份「扫描件」PDF（只有图片、没有文字层），用于验证扫描件识别与提示。

产物放在 samples/extra/ 下，不参与「载入示例数据」。
用法：.venv\\Scripts\\python.exe scripts/make_scanned_sample.py
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "samples" / "extra" / "resume_扫描件示例.pdf"

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
]

LINES = [
    ("周晓彤", 44, True),
    ("女 | 27 岁 | 广州 | 135-0000-0007 | zhouxiaotong@example.com", 24, False),
    ("", 24, False),
    ("求职意向：AI 应用工程师", 26, False),
    ("", 24, False),
    ("教育背景", 30, True),
    ("2015.09 - 2019.06  华南理工大学  计算机科学与技术  本科", 24, False),
    ("", 24, False),
    ("工作经历", 30, True),
    ("2021.03 - 至今   某人工智能公司   Python 开发工程师", 24, False),
    ("- 负责智能客服后端开发，技术栈 Python + FastAPI + PostgreSQL；", 22, False),
    ("- 参与 RAG 知识库项目，使用 pgvector 做向量检索；", 22, False),
    ("- 使用 Docker 部署服务，日均处理对话 5 万次。", 22, False),
    ("", 24, False),
    ("专业技能", 30, True),
    ("Python、FastAPI、PostgreSQL、Redis、Docker、RAG、pgvector", 22, False),
    ("", 24, False),
    ("自我评价", 30, True),
    ("4 年开发经验，有完整的 RAG 项目落地经历，学习能力强。", 22, False),
]


def pick_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    raise SystemExit("未找到可用的中文字体")


def render_image(font_path: str) -> Image.Image:
    width, height = 1240, 1754  # 约 150 DPI 的 A4
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    y = 110
    for text, size, bold in LINES:
        if not text:
            y += size
            continue
        font = ImageFont.truetype(font_path, size, index=0)
        draw.text((110, y), text, fill=(20, 20, 20), font=font)
        y += int(size * 1.7)
        if bold:
            y += 6
    return image


def build(font_path: str) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image = render_image(font_path)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    pdf = canvas.Canvas(str(OUTPUT), pagesize=A4)
    pdf.setTitle("扫描件示例")
    pdf.drawImage(ImageReader(buffer), 0, 0, width=A4[0], height=A4[1])
    pdf.save()

    print(f"generated {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build(pick_font())
