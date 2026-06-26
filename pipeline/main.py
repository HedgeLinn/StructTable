"""
Unified PDF-to-JSON extraction pipeline.

LLM-based extraction — auto-discovers table structure without preset schemas.

Usage:
  python -m pipeline.main convert input.md --output output.json
  python -m pipeline.main convert input.pdf --output output.json
  python -m pipeline.main batch input_dir/ --output output_dir/
"""
import argparse
import os
import sys
from pathlib import Path

from .document_parser import parse_sections
from .config import OCR_CONFIG, ODL_CONFIG, LLM_CONFIG
from .utils import read_file, write_json, validate_all, print_validation_report

_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        from .llm_extractor import LLMClient
        _llm_client = LLMClient(
            api_url=LLM_CONFIG["url"],
            api_key=LLM_CONFIG["api_key"],
            model=LLM_CONFIG["model"],
            temperature=LLM_CONFIG["temperature"],
            max_tokens=LLM_CONFIG["max_tokens"],
            timeout=LLM_CONFIG["timeout_seconds"],
            max_retries=LLM_CONFIG["max_retries"],
        )
    return _llm_client


# ── Pipeline ───────────────────────────────────────────────────

def run_pipeline(md_content: str, dry_run: bool = False) -> list[dict]:
    """Parse → extract → validate."""
    sections = parse_sections(md_content)
    print(f'  Parsed {len(sections)} sections')

    if dry_run:
        for i, sec in enumerate(sections):
            h = sec['h2'] or sec['h3'] or '(no title)'
            print(f'    [{i+1}] {h[:50]} — table: {len(sec.get("html_table", ""))} chars')
            if sec.get('work_content'):
                print(f'         工作内容: {sec["work_content"][:60]}')
            if sec.get('unit'):
                print(f'         单位: {sec["unit"]}')
        return []

    from .llm_extractor import extract_with_llm
    client = _get_llm_client()
    print(f'  Backend: LLM ({LLM_CONFIG["model"]})')
    items = extract_with_llm(sections, client, workers=LLM_CONFIG["workers"])
    print(f'  Extracted {len(items)} items')
    return items


# ── PDF conversion ─────────────────────────────────────────────

def convert_pdf_to_md(pdf_path: str, output_dir: str,
                      skip_fusion: bool = False) -> str:
    """Convert PDF to markdown using OCR_VL (+ opendataloader fusion)."""
    from .pdf2markdown.ocr_vl import OCRVLAdapter

    adapter = OCRVLAdapter(
        api_url=OCR_CONFIG["api_url"],
        prompt=OCR_CONFIG["prompt"],
    )
    print(f'  OCR_VL: {pdf_path}')
    ocr_md_path = adapter.convert(pdf_path, output_dir)
    print(f'  → {ocr_md_path}')

    if skip_fusion:
        return ocr_md_path

    try:
        pkg = ODL_CONFIG["import"]
        fn = ODL_CONFIG["function"]
        mod = __import__(pkg, fromlist=[fn])
        odl_convert = getattr(mod, fn)
        odl_content = odl_convert(pdf_path)
        odl_md_path = os.path.join(output_dir, Path(pdf_path).stem + '_odl.md')
        with open(odl_md_path, 'w', encoding='utf-8') as f:
            f.write(odl_content)
        print(f'  ODL → {odl_md_path}')
    except (ImportError, Exception) as e:
        print(f'  [WARNING] ODL unavailable ({e}), skipping fusion')
        return ocr_md_path

    from .postprocess import postprocess
    fixed = postprocess(read_file(ocr_md_path), read_file(odl_md_path))
    fixed_path = os.path.join(output_dir, Path(pdf_path).stem + '_fixed.md')
    with open(fixed_path, 'w', encoding='utf-8') as f:
        f.write(fixed)
    print(f'  Fused → {fixed_path}')
    return fixed_path


# ── CLI ────────────────────────────────────────────────────────

def cmd_convert(args):
    input_path = args.input
    if input_path.lower().endswith('.pdf'):
        out_dir = os.path.dirname(args.output) if args.output else 'output5'
        os.makedirs(out_dir, exist_ok=True)
        md_path = convert_pdf_to_md(input_path, out_dir, args.skip_fusion)
        md_content = read_file(md_path)
    else:
        md_content = read_file(input_path)

    items = run_pipeline(md_content, args.dry_run)

    if not args.dry_run and items:
        out = args.output or os.path.join('output5', Path(input_path).stem + '.json')
        write_json(items, out)
        print(f'  → {out} ({len(items)} items)')


def cmd_batch(args):
    md_files = sorted(Path(args.input).glob('*.md'))
    if not md_files:
        print(f'No .md files in: {args.input}')
        return
    out_dir = args.output or 'output5'

    print(f'=== Batch Pipeline ===')
    print(f'Input:  {args.input} ({len(md_files)} files)')
    print(f'Output: {out_dir}')
    print(f'Model:  {LLM_CONFIG["model"]}')
    print('=' * 60)

    total, skipped = 0, 0
    for i, fp in enumerate(md_files):
        print(f'\n[{i+1}/{len(md_files)}] {fp.name}')
        try:
            items = run_pipeline(read_file(str(fp)))
            if items:
                out_path = os.path.join(out_dir, f'{fp.stem}.json')
                write_json(items, out_path)
                print(f'  → {out_path} ({len(items)} items)')
                total += len(items)
        except Exception as e:
            print(f'  [ERROR] {e}')
            import traceback; traceback.print_exc()
            skipped += 1

    print(f'\n===== Done: {total} items, {skipped} skipped =====')


def cmd_validate(args):
    import json
    data = json.loads(read_file(args.input))
    if not isinstance(data, list):
        print(f'ERROR: expected JSON array, got {type(data).__name__}')
        sys.exit(1)
    print(f'Validating {len(data)} entries...')
    data = validate_all(data)
    print_validation_report(data)
    if args.output:
        write_json(data, args.output)


def main():
    p = argparse.ArgumentParser(description='PDF-to-JSON extraction pipeline')
    sub = p.add_subparsers(dest='command')

    pc = sub.add_parser('convert', help='Convert a single file')
    pc.add_argument('input', help='PDF or Markdown file')
    pc.add_argument('--output', '-o', help='Output JSON path')
    pc.add_argument('--skip-fusion', action='store_true')
    pc.add_argument('--dry-run', action='store_true')

    pb = sub.add_parser('batch', help='Batch process a directory')
    pb.add_argument('input', help='Directory with .md files')
    pb.add_argument('--output', '-o', help='Output directory')

    pv = sub.add_parser('validate', help='Validate JSON output')
    pv.add_argument('input', help='JSON file')
    pv.add_argument('--output', '-o', help='Annotated output path')

    args = p.parse_args()
    if args.command == 'convert': cmd_convert(args)
    elif args.command == 'batch': cmd_batch(args)
    elif args.command == 'validate': cmd_validate(args)
    else: p.print_help()


if __name__ == '__main__':
    main()
