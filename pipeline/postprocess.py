"""
OCR_VL HTML table post-processing — fixes two systematic OCR errors.

Fix 1 — Header rowspan truncation (fatal):
  OCR_VL sometimes sets rowspan=2 instead of 3 on the "项目名称" cell,
  pushing the diameter-spec row (300|400|500...) out of the merged region
  and shifting all data rows upward. Detection is structural, no reference needed.

Fix 2 — Material/mechanical detail row merging:
  OCR_VL merges separate material names into a single cell.
  Strategy: use opendataloader's GFM output as reference for where the
  split points should be (LCS matching + whitespace-free anchoring).

Usage:
    from postprocess import postprocess
    fixed_md = postprocess(ocr_md_content, odl_md_content)
"""
import re

from bs4 import BeautifulSoup


# ── GFM name splitting ──────────────────────────────────────────

def smart_split_gfm_names(raw_str: str, unit_count: int) -> list[str]:
    """Split a GFM material-name string into unit_count independent names.

    GFM separates names with spaces, but some names contain internal spaces
    (e.g. '溶剂汽油 200#', '柴油发电机 50kW'). Two-pass strategy:
    1. Split on whitespace that precedes a Chinese character
    2. If token count > unit_count, merge suspected suffix tokens
    """
    raw = raw_str.strip()
    if not raw:
        return []

    parts = re.split(r"\s+(?=[一-鿿])", raw)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) <= unit_count:
        return parts

    while len(parts) > unit_count:
        merged = False

        # Pass a: merge non-Chinese-starting tokens
        for i in range(len(parts) - 1):
            if re.match(r"^[^一-鿿]", parts[i + 1]):
                parts[i] = parts[i] + " " + parts[i + 1]
                parts.pop(i + 1)
                merged = True
                break
        if merged:
            continue

        # Pass b: merge brand/model suffix tokens
        for i in range(len(parts) - 1):
            if re.match(r"^[一-鿿]{1,4}[A-Za-z0-9\-/]", parts[i + 1]):
                parts[i] = parts[i] + " " + parts[i + 1]
                parts.pop(i + 1)
                merged = True
                break
        if merged:
            continue

        # Pass c: force merge from left
        parts[0] = parts[0] + " " + parts[1]
        parts.pop(1)

    return parts


def parse_gfm_material_lists(gfm_text: str) -> list[dict]:
    """Extract material/mechanical row names from GFM markdown tables.

    Returns: [{"label": "材料"|"机械", "names": [...], "raw": "original string"}, ...]
    """
    lines = gfm_text.split("\n")
    results = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|") or not line.endswith("|"):
            i += 1
            continue

        table_lines = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            table_lines.append(lines[i].strip())
            i += 1

        if len(table_lines) < 3:
            continue

        for row in table_lines:
            cells = [c.strip() for c in row.split("|")[1:-1]]
            if not cells or cells[0] not in ("材料", "机械"):
                continue

            label = cells[0]
            name_str = cells[1] if len(cells) > 1 else ""
            unit_str = cells[2] if len(cells) > 2 else ""

            unit_count = len(unit_str.split())
            if unit_count < 2:
                continue

            names = smart_split_gfm_names(name_str, unit_count)
            if len(names) >= 3:
                results.append({
                    "label": label,
                    "names": names,
                    "raw": name_str,
                })

    return results


# ── OCR text splitting ──────────────────────────────────────────

def split_ocr_by_gfm_names(ocr_text: str, gfm_names: list[str]) -> list[str]:
    """Use GFM names as anchors to split a merged OCR text cell.

    Matches whitespace-removed versions and extracts OCR-text segments.
    Falls back to GFM names when OCR text can't be cleanly matched.
    """
    ocr_ns = re.sub(r"\s+", "", ocr_text)
    gfm_ns_names = [re.sub(r"\s+", "", n) for n in gfm_names]

    pos = 0
    result = []
    for gfm_n in gfm_ns_names:
        idx = ocr_ns.find(gfm_n, pos)
        if idx >= 0:
            result.append(ocr_ns[idx:idx + len(gfm_n)])
            pos = idx + len(gfm_n)
        else:
            result.append(gfm_n)

    return result


# ── Fix 1: Header rowspan truncation ────────────────────────────

def _is_diameter_sequence(values: list[int]) -> bool:
    """Heuristic: do values look like pipe diameter specs? (increasing, reasonable range)"""
    if len(values) < 3:
        return False
    if not all(25 <= v <= 2000 for v in values):
        return False
    if not all(values[i] < values[i + 1] for i in range(len(values) - 1)):
        return False
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    if not all(10 <= d <= 500 for d in diffs):
        return False
    median_diff = sorted(diffs)[len(diffs) // 2]
    if median_diff <= 0:
        return False
    if not all(0.2 <= d / median_diff <= 5.0 for d in diffs):
        return False
    return True


def _get_data_cells(row) -> list:
    """Get cells without colspan/rowspan (pure data cells)."""
    cells = []
    for td in row.find_all("td"):
        if td.get("colspan") or td.get("rowspan"):
            continue
        cells.append(td)
    return cells


def _is_text_header_row(row) -> bool:
    """Check if a row is a text header (not numeric data)."""
    data_cells = _get_data_cells(row)
    if not data_cells:
        return True
    numeric_count = 0
    for cell in data_cells:
        text = cell.get_text(strip=True)
        if not text:
            continue
        try:
            float(text)
            numeric_count += 1
        except ValueError:
            pass
    return numeric_count < len(data_cells) * 0.5


def fix_header_rowspan(html_table: str) -> tuple[str, bool]:
    """OCR_VL fix: detect truncated header rowspan using structural heuristics.

    Looks for: rowspan cell → text-only row at span boundary →
    followed by a "price/fee indicator" row whose values are small params.
    Fix: expand rowspan, insert missing row, shift data, estimate gap.
    (OCR_VL-specific — not used in MinerU path.)
    """
    soup = BeautifulSoup(html_table, "html.parser")
    rows = soup.find_all("tr")
    modified = False

    for i, row in enumerate(rows):
        for td in row.find_all("td"):
            if "项目名称" not in td.get_text(strip=True):
                continue
            rowspan = int(td.get("rowspan", 1))
            if rowspan < 2:
                continue

            last_span_idx = i + rowspan - 1
            if last_span_idx >= len(rows):
                continue
            if not _is_text_header_row(rows[last_span_idx]):
                continue

            jijia_idx = i + rowspan
            if jijia_idx >= len(rows):
                continue
            jijia_text = re.sub(r"\s+", "", rows[jijia_idx].get_text(strip=True))
            if "基价" not in jijia_text:
                continue

            data_cells = _get_data_cells(rows[jijia_idx])
            param_values = []
            for cell in data_cells:
                try:
                    param_values.append(int(cell.get_text(strip=True)))
                except ValueError:
                    pass
            if not _is_diameter_sequence(param_values):
                continue

            # --- Execute fix ---
            td["rowspan"] = str(rowspan + 1)

            new_tr = soup.new_tag("tr")
            for val in param_values:
                new_td = soup.new_tag("td")
                new_td["style"] = "text-align: center;"
                new_td.string = str(val)
                new_tr.append(new_td)
            rows[jijia_idx].insert_before(new_tr)
            rows = soup.find_all("tr")

            ji_jia_row_idx = labor_row_idx = material_row_idx = machine_row_idx = None
            for r_idx, r in enumerate(rows):
                r_text = re.sub(r"\s+", "", r.get_text(strip=True))
                if "基价" in r_text and ji_jia_row_idx is None:
                    ji_jia_row_idx = r_idx
                elif "人工费" in r_text and labor_row_idx is None:
                    labor_row_idx = r_idx
                elif "材料费" in r_text and material_row_idx is None:
                    material_row_idx = r_idx
                elif "机械费" in r_text and machine_row_idx is None:
                    machine_row_idx = r_idx

            if ji_jia_row_idx is None or labor_row_idx is None:
                continue

            ji_jia_data = _get_data_cells(rows[ji_jia_row_idx])
            labor_data = _get_data_cells(rows[labor_row_idx])
            material_data = _get_data_cells(rows[material_row_idx]) if material_row_idx is not None else []
            machine_data = _get_data_cells(rows[machine_row_idx]) if machine_row_idx is not None else []
            n_cols = len(ji_jia_data)

            if len(labor_data) >= n_cols:
                for j in range(n_cols):
                    ji_jia_data[j].string = labor_data[j].get_text(strip=True)
            if len(material_data) >= n_cols:
                for j in range(n_cols):
                    labor_data[j].string = material_data[j].get_text(strip=True)
            if len(machine_data) >= n_cols:
                for j in range(n_cols):
                    material_data[j].string = machine_data[j].get_text(strip=True)
                for j in range(n_cols):
                    try:
                        jj = float(ji_jia_data[j].get_text(strip=True))
                        lb = float(labor_data[j].get_text(strip=True))
                        mt = float(material_data[j].get_text(strip=True))
                        estimated = round(jj - lb - mt, 2)
                        machine_data[j].string = str(estimated)
                    except (ValueError, IndexError):
                        pass

            modified = True
            break

    return str(soup), modified


# ── Fix 2: Material/mechanical row merging ──────────────────────

def _lcs_ratio(a: str, b: str) -> float:
    """Longest common subsequence similarity ratio (0~1)."""
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0.0
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    return prev[n] / max(m, n)


def _match_html_to_gfm(merged_text: str, gfm_lists: list[dict]) -> dict | None:
    """Find the best-matching GFM material list for a merged OCR cell."""
    ocr_ns = re.sub(r"\s+", "", merged_text)

    best = None
    best_score = 0
    for gfm_entry in gfm_lists:
        gfm_concat = re.sub(r"\s+", "", "".join(gfm_entry["names"]))
        if ocr_ns == gfm_concat:
            return gfm_entry
        score = _lcs_ratio(ocr_ns, gfm_concat)
        if score > best_score:
            best_score = score
            best = gfm_entry

    return best if best_score > 0.6 else None


def fix_html_table_with_gfm(html_table: str, gfm_lists: list[dict]) -> tuple[str, bool]:
    """Fix merged material rows in an HTML table using GFM reference lists.

    Finds <td> cells with rowspan >= 5 and long text, matches against
    GFM material lists, then splits the merged cell into individual rows.
    """
    soup = BeautifulSoup(html_table, "html.parser")
    modified = False

    for td in soup.find_all("td"):
        rowspan = int(td.get("rowspan", 1))
        if rowspan < 5:
            continue

        text = td.get_text(strip=True)
        if len(text) < 20:
            continue

        gfm_entry = _match_html_to_gfm(text, gfm_lists)
        if not gfm_entry:
            continue

        gfm_names = gfm_entry["names"]
        if abs(rowspan - len(gfm_names)) > 3:
            continue

        ocr_names = split_ocr_by_gfm_names(text, gfm_names)
        if len(ocr_names) != len(gfm_names):
            ocr_names = gfm_names

        parent_tr = td.find_parent("tr")
        parent_table = td.find_parent("table")
        if not parent_tr or not parent_table:
            continue

        rows = parent_table.find_all("tr")
        try:
            tr_idx = rows.index(parent_tr)
        except ValueError:
            continue

        td["rowspan"] = "1"
        td.string = ocr_names[0]

        for i in range(1, len(ocr_names)):
            if tr_idx + i >= len(rows):
                break
            new_cell = soup.new_tag("td")
            new_cell.string = ocr_names[i]
            rows[tr_idx + i].insert(0, new_cell)

        modified = True

    return str(soup), modified


# ── Main entry ──────────────────────────────────────────────────

def postprocess(ocr_content: str, odl_content: str) -> str:
    """Fuse OCR_VL HTML output with opendataloader GFM reference.

    Applies two sequential fixes:
    1. Header rowspan truncation (no reference needed)
    2. Material/mechanical row merging (uses GFM reference)

    Args:
        ocr_content: Markdown string from OCR_VL (contains HTML tables)
        odl_content: Markdown string from opendataloader (contains GFM tables)

    Returns:
        Fixed markdown string with corrected HTML tables.
    """
    table_re = re.compile(r"<table\b[^>]*>.*?</table>", re.DOTALL)
    html_tables = table_re.findall(ocr_content)

    # Phase 1: fix header rowspan (no ODL dependency)
    modified = ocr_content
    header_fixed = 0
    for html_table in html_tables:
        fixed_html, changed = fix_header_rowspan(html_table)
        if changed:
            modified = modified.replace(html_table, fixed_html)
            header_fixed += 1

    # Phase 2: fix material row merging (uses GFM reference)
    gfm_lists = parse_gfm_material_lists(odl_content)
    html_tables_after = table_re.findall(modified)
    material_fixed = 0
    for html_table in html_tables_after:
        fixed_html, changed = fix_html_table_with_gfm(html_table, gfm_lists)
        if changed:
            modified = modified.replace(html_table, fixed_html)
            material_fixed += 1

    return modified
