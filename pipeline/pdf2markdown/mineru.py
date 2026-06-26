"""MinerU adapter — async batch-job PDF-to-Markdown via MinerU cloud API.

Flow: POST file-urls/batch → PUT presigned URL → poll extract-results → download ZIP → extract full.md

Compared to OCR_VL: cleaner HTML tables, better row separation (no cell-merging issue),
but loses document context (chapter headers, work content, unit).
"""

import time
import zipfile
import tempfile
from pathlib import Path

import requests

from .base import ConverterAdapter


class MinerUAdapter(ConverterAdapter):
    name = "mineru"
    enabled_evaluators = ["表格评测"]

    def __init__(
        self,
        token: str = "",
        api_url: str = "https://mineru.net/api/v4",
        model_version: str = "vlm",
        language: str = "ch",
        enable_table: bool = True,
        poll_interval: int = 10,
        poll_max: int = 600,
    ):
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.model_version = model_version
        self.language = language
        self.enable_table = enable_table
        self.poll_interval = poll_interval
        self.poll_max = poll_max

    def convert(self, pdf_path: str, output_dir: str) -> str:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        stem = Path(pdf_path).stem
        md_path = out / f"{stem}.md"

        # Step 1: request upload URL
        print(f"  [MinerU] Requesting upload URL for {Path(pdf_path).name}")
        batch_id, upload_url = self._request_upload_url(pdf_path)
        print(f"  [MinerU] batch_id={batch_id}")

        # Step 2: upload file
        print(f"  [MinerU] Uploading file...")
        self._upload_file(upload_url, pdf_path)

        # Step 3: poll until done
        print(f"  [MinerU] Waiting for extraction (poll every {self.poll_interval}s, max {self.poll_max}s)...")
        full_zip_url = self._wait_for_result(batch_id)

        # Step 4: download & extract
        print(f"  [MinerU] Downloading result...")
        self._download_and_extract(full_zip_url, md_path)

        print(f"  [MinerU] Done -> {md_path}")
        return str(md_path)

    def _request_upload_url(self, pdf_path: str) -> tuple[str, str]:
        url = f"{self.api_url}/file-urls/batch"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        payload = {
            "files": [{"name": Path(pdf_path).name}],
            "model_version": self.model_version,
            "language": self.language,
            "enable_table": self.enable_table,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(
                f"MinerU request upload URL failed: HTTP {resp.status_code}: {resp.text[:500]}"
            )

        result = resp.json()
        if result.get("code") != 0:
            raise RuntimeError(
                f"MinerU request upload URL error: code={result.get('code')}, "
                f"msg={result.get('msg')}"
            )

        data = result["data"]
        batch_id = data["batch_id"]
        file_urls = data["file_urls"]
        if not file_urls:
            raise RuntimeError("MinerU returned empty file_urls list")

        return batch_id, file_urls[0]

    def _upload_file(self, upload_url: str, pdf_path: str) -> None:
        with open(pdf_path, "rb") as f:
            resp = requests.put(upload_url, data=f, timeout=300)

        if resp.status_code != 200:
            raise RuntimeError(
                f"MinerU upload failed: HTTP {resp.status_code}: {resp.text[:500]}"
            )

    def _wait_for_result(self, batch_id: str) -> str:
        url = f"{self.api_url}/extract-results/batch/{batch_id}"
        headers = {"Authorization": f"Bearer {self.token}"}

        deadline = time.time() + self.poll_max
        last_state = ""

        while time.time() < deadline:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"MinerU poll failed: HTTP {resp.status_code}: {resp.text[:500]}"
                )

            result = resp.json()
            if result.get("code") != 0:
                raise RuntimeError(
                    f"MinerU poll error: code={result.get('code')}, msg={result.get('msg')}"
                )

            extract_results = result.get("data", {}).get("extract_result", [])
            for er in extract_results:
                state = er.get("state", "")

                if state != last_state:
                    print(f"  [MinerU] state={state}")
                    last_state = state

                if state == "done":
                    zip_url = er.get("full_zip_url", "")
                    if not zip_url:
                        raise RuntimeError("MinerU done but no full_zip_url in response")
                    return zip_url

                if state == "failed":
                    err = er.get("err_msg", "unknown")
                    raise RuntimeError(f"MinerU extraction failed: {err}")

            time.sleep(self.poll_interval)

        raise RuntimeError(
            f"MinerU extraction timed out after {self.poll_max}s (batch_id={batch_id})"
        )

    def _download_and_extract(self, zip_url: str, md_path: Path) -> None:
        resp = requests.get(zip_url, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(
                f"MinerU download ZIP failed: HTTP {resp.status_code}"
            )

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "result.zip"
            zip_path.write_bytes(resp.content)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)

            # MinerU outputs full.md in the archive root
            full_md = Path(tmp) / "full.md"
            if not full_md.exists():
                # Search for it (might be nested)
                candidates = list(Path(tmp).rglob("full.md"))
                if not candidates:
                    raise RuntimeError(
                        "MinerU ZIP does not contain full.md. "
                        f"Archive contents: {[f.name for f in Path(tmp).iterdir()][:20]}"
                    )
                full_md = candidates[0]

            md_content = full_md.read_text(encoding="utf-8")
            md_path.write_text(md_content, encoding="utf-8")
