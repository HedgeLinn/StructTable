"""OCR VL adapter — calls OCR vision-language model via HTTP API.

Input: page-by-page PNG images (multipart/form-data)
Output: Markdown text
"""

import io
from pathlib import Path

import fitz
import requests

from .base import ConverterAdapter


class OCRVLAdapter(ConverterAdapter):
    name = "ocr_vl"
    enabled_evaluators = ["表格评测"]

    def __init__(self, api_url: str = "", prompt: str = ""):
        self.api_url = api_url
        self.prompt = prompt

    def convert(self, pdf_path: str, output_dir: str) -> str:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        md_lines: list[str] = []
        last_report = 0

        for page_num in range(total_pages):
            page = doc[page_num]

            # pymupdf 渲染页面为 PNG
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")

            files = {"file": (f"page_{page_num + 1}.png", img_bytes, "image/png")}
            data = {}
            if self.prompt:
                data["prompt"] = self.prompt

            resp = requests.post(self.api_url, files=files, data=data, timeout=300)

            if resp.status_code != 200:
                detail = resp.text[:500]
                doc.close()
                raise RuntimeError(
                    f"第 {page_num + 1}/{total_pages} 页 HTTP {resp.status_code}: {detail}"
                )

            # 响应可能是纯文本 Markdown 或 JSON
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                data = resp.json()
                if isinstance(data, str):
                    page_text = data
                elif isinstance(data, dict):
                    page_text = (
                        data.get("markdown")
                        or data.get("text")
                        or data.get("content")
                        or data.get("result")
                        or str(data)
                    )
                else:
                    page_text = str(data)
            else:
                page_text = resp.text

            md_lines.append(page_text)

            # 每页或每 10 页报告一次进度
            current = page_num + 1
            pct = current * 100 / total_pages
            if current == total_pages or current - last_report >= 10 or current == 1:
                print(f"[{current}/{total_pages} {pct:.0f}%]", end=" ", flush=True)
                last_report = current

        doc.close()

        stem = Path(pdf_path).stem
        md_file = out / f"{stem}.md"
        md_file.write_text("\n\n".join(md_lines), encoding="utf-8")
        return str(md_file)
