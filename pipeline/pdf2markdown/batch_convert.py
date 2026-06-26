"""批量 PDF → Markdown 转换。5 并发 + 可选的钉钉通知。"""
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ocr_vl import OCRVLAdapter

# Default paths — override via environment or .env file
try:
    from ..config import OCR_CONFIG
    INPUT_DIR = Path(OCR_CONFIG["batch"]["input_dir"] or ".")
    OUTPUT_DIR = Path(OCR_CONFIG["batch"]["output_dir"] or "./markdown_output")
    WORKERS = OCR_CONFIG["batch"]["workers"]
except Exception:
    INPUT_DIR = Path(".")
    OUTPUT_DIR = Path("./markdown_output")
    WORKERS = 5

print_lock = threading.Lock()
start_time = time.time()


def convert_one(pdf_path, adapter=None):
    name = pdf_path.name
    size_mb = pdf_path.stat().st_size / 1024 / 1024
    t0 = time.time()
    try:
        if adapter is None:
            adapter = OCRVLAdapter()
        md_path = adapter.convert(str(pdf_path), str(OUTPUT_DIR))
        elapsed = time.time() - t0
        return name, str(md_path), None, elapsed, size_mb
    except Exception as e:
        elapsed = time.time() - t0
        return name, None, str(e), elapsed, size_mb


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    total = len(pdfs)
    if total == 0:
        print(f"No PDF files found in {INPUT_DIR}")
        return

    print(f"Processing {total} PDF files -> {OUTPUT_DIR}")
    print(f"Concurrency: {WORKERS} workers")
    print("=" * 60)

    adapter = OCRVLAdapter()
    completed = 0
    failed_list = []

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(convert_one, p, adapter): p for p in pdfs}
        for future in as_completed(futures):
            name, md_path, err, elapsed, size_mb = future.result()
            completed += 1
            with print_lock:
                if err:
                    failed_list.append((name, err))
                    tag = "FAILED"
                else:
                    tag = "OK"
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                print(f"[{completed}/{total}] {tag} {name} ({size_mb:.1f}MB) {mins}m{secs}s")

    elapsed_total = time.time() - start_time
    print(f"\n===== {'ALL OK' if not failed_list else f'FAILED: {len(failed_list)}/{total}'} =====")
    print(f"Total time: {elapsed_total/60:.1f} minutes")
    if failed_list:
        for name, err in failed_list:
            print(f"  FAILED: {name} — {err[:100]}")


if __name__ == "__main__":
    main()
