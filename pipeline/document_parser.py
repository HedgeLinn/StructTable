"""
Document parsing — split a Markdown file (with embedded HTML tables) into sections.

Consolidates parse_sections / merge_duplicate_sections from
extract_html_pipeline.py and extract_all_formats.py.
"""
import re

from .utils import read_file


def parse_sections(md_content: str) -> list[dict]:
    """Parse markdown content into sections.

    Each section contains a chapter title, section headers, work content,
    unit, and the raw HTML table. Handles OCR_VL page-split artefacts
    by merging duplicate sections.

    Returns: [{chapter, h2, h3, work_content, unit, html_table}, ...]
    """
    chapter_pattern = r'^(第[一二三四五六七八九十]+章\s+.+)$'
    chapter_matches = list(re.finditer(chapter_pattern, md_content, re.MULTILINE))

    sections = []

    if not chapter_matches:
        sec = _parse_section_body(md_content, '')
        if sec:
            sections.append(sec)
        return sections

    for ci, cm in enumerate(chapter_matches):
        chap_title = cm.group(1).strip()
        chap_start = cm.end()
        chap_end = chapter_matches[ci + 1].start() if ci + 1 < len(chapter_matches) else len(md_content)
        chap_body = md_content[chap_start:chap_end]

        sec_parts = re.split(r'\n(?=## )', chap_body)
        for part in sec_parts:
            if not part.strip():
                continue
            sub_parts = re.split(r'\n(?=### )', part)
            for sub in sub_parts:
                if not sub.strip():
                    continue
                sec = _parse_section_body(sub, chap_title)
                if sec:
                    sections.append(sec)

    sections = _merge_duplicate_sections(sections)
    return sections


def _parse_section_body(text: str, chapter_title: str) -> dict | None:
    """Parse a single section's body for metadata + HTML table."""
    lines = text.strip().split('\n')

    h2_title = ''
    h3_title = ''
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith('## '):
            h2_title = line[3:].strip()
            body_start = i + 1
        elif line.startswith('### '):
            h3_title = line[4:].strip()
            body_start = i + 1
        elif not line.startswith('#') and not line.startswith('<table'):
            break

    body_lines = lines[body_start:]

    work_content = ''
    unit = ''
    table_start = -1
    for i, line in enumerate(body_lines):
        if line.strip().startswith('<table'):
            table_start = i
            break
        stripped = line.strip()
        if stripped.startswith('工作内容'):
            m = re.match(r'工作内容[：:]\s*(.+?)(?:\s*计量单位[：:]\s*(.+))?$', stripped)
            if m:
                work_content = m.group(1).strip().rstrip(',').strip()
                if m.group(2):
                    unit = m.group(2).strip()
        elif stripped.startswith('计量单位'):
            m = re.search(r'计量单位[：:]\s*(.+)', stripped)
            if m:
                unit = m.group(1).strip()

    html_table = ''
    if table_start >= 0:
        table_text = '\n'.join(body_lines[table_start:])
        # Capture ALL tables, not just the first one
        # (LNG documents often split one logical table across 2+ HTML tables)
        tables = re.findall(r'(<table[^>]*>.*?</table>)', table_text, re.DOTALL)
        if tables:
            html_table = '\n'.join(tables)

    if not html_table:
        return None

    unit = re.sub(r'\$\s*([^$]+)\s*\$', r'\1', unit).strip()

    return {
        'chapter': chapter_title,
        'h2': h2_title,
        'h3': h3_title,
        'work_content': work_content,
        'unit': unit,
        'html_table': html_table,
    }


def _merge_duplicate_sections(sections: list[dict]) -> list[dict]:
    """Merge consecutive sections with identical h2+h3 (page-split artefacts)."""
    if not sections:
        return sections

    merged = []
    for sec in sections:
        if merged:
            prev = merged[-1]
            same_title = (sec['h2'] == prev['h2'] and sec['h3'] == prev['h3'])
            if same_title and sec['h2']:
                prev['html_table'] += '\n' + sec['html_table']
                if len(sec.get('work_content', '')) > len(prev.get('work_content', '')):
                    prev['work_content'] = sec['work_content']
                if sec.get('unit') and not prev.get('unit'):
                    prev['unit'] = sec['unit']
                continue

        merged.append(dict(sec))

    return merged


