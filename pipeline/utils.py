"""
Shared utilities for the PDF-to-JSON extraction pipeline.

Centralises functions that were previously duplicated across
extract_html_pipeline.py, extract_all_formats.py, and extract_pipeline.py.
"""
import json
import os
import re


# ── I/O ─────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# ── Numeric parsing ─────────────────────────────────────────────

def parse_number(val: str) -> float:
    """Parse a numeric value. Handles Chinese parentheses (negatives).

    （0.200） → -0.200
    (0.200)  → -0.200
    123.45   → 123.45
    """
    val = val.strip()
    if not val:
        return 0.0
    # Normalise Chinese full-width parentheses to ASCII
    val = val.replace('（', '(').replace('）', ')')
    if val.startswith('(') and val.endswith(')'):
        inner = val[1:-1].strip()
        try:
            return -float(inner)
        except ValueError:
            return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def is_float_str(s: str) -> bool:
    """Check whether a string represents a valid numeric value."""
    s = s.strip()
    if not s:
        return True
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
    try:
        float(s)
        return True
    except ValueError:
        return False


# ── Text / HTML helpers ─────────────────────────────────────────

def clean_text(td) -> str:
    """Get stripped text from a BeautifulSoup tag."""
    return td.get_text(strip=True)


def clean_cell_text(td) -> str:
    """Alias for clean_text for backwards compatibility."""
    return clean_text(td)


# ── JSON formatting ─────────────────────────────────────────────

def _is_leaf_obj(obj) -> bool:
    """Return True if obj is a dict whose values are all scalars."""
    if not isinstance(obj, dict):
        return False
    for v in obj.values():
        if isinstance(v, (dict, list)):
            return False
    return True


def format_json_custom(obj, level=0, in_array=False) -> str:
    """Custom JSON formatter: leaf objects inline, nested structures indented."""
    sp = '  '
    cur = sp * level
    nxt = sp * (level + 1)

    if isinstance(obj, list):
        if not obj:
            return '[]'
        items = [format_json_custom(it, level + 1, True) for it in obj]
        return '[\n' + ',\n'.join(items) + '\n' + cur + ']'

    if isinstance(obj, dict):
        if _is_leaf_obj(obj) and in_array:
            compact = json.dumps(obj, ensure_ascii=False, separators=(', ', ': '))
            return cur + '{ ' + compact[1:-1] + ' }'
        if not obj:
            return '{}'
        lines = [f'{nxt}"{k}": {format_json_custom(v, level + 1)}' for k, v in obj.items()]
        return '{\n' + ',\n'.join(lines) + '\n' + cur + '}'

    return json.dumps(obj, ensure_ascii=False)


def write_json(data, path: str) -> None:
    """Write formatted JSON to file, creating parent directories as needed."""
    formatted = format_json_custom(data)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(formatted)
        f.write('\n')


# ── Smart name / unit / price splitting ─────────────────────────

KNOWN_UNITS = [
    '台班', '工日', 'm³', 'm²', 'kWh', 'kW', 'kg', 'km',
    '把', '个', '套', '块', '张', '片', '根', '台', '次',
    '处', 'm',  't',  'L',  'h',  'W',
]

_SUFFIX_PATTERN = re.compile(
    r'^(DN\d+|'                             # DN300, DN400
    r'[0-9]+#|'                              # 1#, 5# (battery model)
    r'\d+\.?\d*t\b|'                         # 2.5t, 8t, 12t
    r'\d+kW\b|'                              # 50kW
    r'[一-鿿]*[A-Z]+[-\d][\w/.#-]*|'     # brand+model: 林肯DC-400
    r'\d+m³|'                           # 11m³
    r'载重量[\d.]+t?|'                       # 载重量2.5t
    r'φ\d+mm|'                          # φ10mm
    r'\d+mm|'                                # 150mm
    r'[（(][^)）]+[)）]'         # (综合), （规格同主管）
    r')$')


def split_units(unit_str: str) -> list[str]:
    """Split a concatenated unit string into individual unit tokens.

    e.g. '把kg' → ['把', 'kg']
    """
    if not unit_str:
        return []
    result = []
    i = 0
    while i < len(unit_str):
        matched = False
        for u in KNOWN_UNITS:
            if unit_str[i:i + len(u)] == u:
                result.append(u)
                i += len(u)
                matched = True
                break
        if not matched:
            result.append(unit_str[i])
            i += 1
    return result


def split_prices(prices_raw: str, n: int) -> list[str]:
    """Split a concatenated price string into n individual prices.

    e.g. '6.067.743.0926.65' → ['6.06', '7.74', '3.09', '26.65']
    """
    if not prices_raw:
        return ['0'] * n
    s = prices_raw.strip()
    tokens = s.split()
    if len(tokens) == n:
        return tokens
    prices = re.findall(r'\d+\.\d{1,2}', s)
    if len(prices) == n:
        return prices
    while len(prices) < n:
        prices.append('0')
    return prices[:n]


def split_material_names(text: str, target_n: int) -> list[str]:
    """Split concatenated material names at Chinese bracket + space boundaries.

    Multi-strategy fallback chain:
    1. Split at ) or ） followed by space and Chinese/latin char
    2. Space split within remaining groups
    3. Latin/Chinese boundary split
    4. Known material suffix boundary split

    Returns exactly target_n items (padded or merged as needed).
    """
    if not text:
        return [''] * target_n

    # Strategy 1: split on bracket + space boundaries
    parts = re.split(r'(?<=[)）])\s+(?=[一-鿿\w])', text)

    if len(parts) == target_n:
        return [p.strip() for p in parts]

    # Strategy 2: space split within each part
    if len(parts) < target_n:
        new_parts = []
        for p in parts:
            new_parts.extend(p.strip().split())
        parts = new_parts

    # Strategy 3: split at Latin→Chinese boundaries within parts
    if len(parts) < target_n:
        new_parts = []
        for p in parts:
            sub = re.split(r'(?<=[a-zA-Z0-9#%φ°/.-])(?=[一-鿿])', p)
            new_parts.extend([s for s in sub if s])
        parts = new_parts

    # Strategy 4: split at known material-name suffix boundaries
    if len(parts) < target_n:
        new_parts = []
        for p in parts:
            sub = re.split(
                r'(?<=[刷片油气筒架机头布刀表门网管板漆剂囊罩])'
                r'(?=[一-鿿])', p)
            merged = []
            for s in sub:
                if merged and len(s) <= 2:
                    merged[-1] = merged[-1] + s
                else:
                    merged.append(s)
            new_parts.extend(merged)
        parts = new_parts

    while len(parts) < target_n:
        parts.append('')

    if len(parts) > target_n:
        parts = parts[:target_n - 1] + [' '.join(parts[target_n - 1:])]

    return [p.strip() for p in parts[:target_n]]


def smart_split_names_units_prices(names_raw: str, units_raw: str, prices_raw: str):
    """Intelligently split concatenated name/unit/price cells.

    Uses unit token count N as the alignment anchor, then
    aligns names and prices to match.
    Returns: (names: list[str], unit_tokens: list[str], price_tokens: list[str])
    """
    if not names_raw or not units_raw:
        return [], [], []

    # Step 1: unit tokens → N
    unit_tokens = split_units(units_raw.strip())
    if not unit_tokens:
        return [], [], []

    N = len(unit_tokens)

    # Step 2: align prices to N
    price_tokens = split_prices(prices_raw, N)

    # Step 3: split names
    names = split_material_names(names_raw.strip(), N)

    # Check if strategy A produced suspicious isolated suffix tokens
    needs_fallback = len(names) != N
    if not needs_fallback:
        for n in names:
            if _SUFFIX_PATTERN.match(n):
                needs_fallback = True
                break

    if needs_fallback:
        # Strategy B: space split + merge suffix tokens
        raw_tokens = names_raw.strip().split()
        if len(raw_tokens) >= N:
            merged = []
            i = 0
            while i < len(raw_tokens) and len(merged) < N - 1:
                tok = raw_tokens[i]
                if (i + 1 < len(raw_tokens)
                        and _SUFFIX_PATTERN.match(raw_tokens[i + 1])):
                    merged.append(tok + ' ' + raw_tokens[i + 1])
                    i += 2
                else:
                    merged.append(tok)
                    i += 1
            if i < len(raw_tokens):
                merged.append(' '.join(raw_tokens[i:]))
            while len(merged) < N:
                merged.append('')
            names = merged[:N]
        else:
            names = raw_tokens + [''] * (N - len(raw_tokens))

    return names, unit_tokens, price_tokens


# ── Validation ──────────────────────────────────────────────────

def validate_entry(entry: dict, tolerance: float = 1.0) -> dict:
    """Generic structural validation. No hardcoded field names.

    - Error: entry is completely empty
    - Warning: any string field with an empty value
    - Fee-sum check: only when both 基价 and 费用构成 are present
    """
    validation = {'warnings': [], 'errors': []}

    # Only error on truly empty objects
    if not entry or (isinstance(entry, dict) and len(entry) <= 1
                     and '_source' in entry):
        validation['errors'].append('Entry is empty')

    # Warn on empty string values (whatever the field name)
    for key, val in entry.items():
        if key.startswith('_'):
            continue
        if isinstance(val, str) and not val.strip():
            validation['warnings'].append(f'Empty field: {key}')

    # Fee-sum check (only when both fields exist in this entry)
    if '基价' in entry and '费用构成' in entry:
        base_price = entry.get('基价', 0) or 0
        fees = entry.get('费用构成') or {}
        if fees and base_price:
            fee_sum = (fees.get('人工费', 0) or 0) + \
                      (fees.get('材料费', 0) or 0) + \
                      (fees.get('机械费', 0) or 0)
            diff = abs(base_price - fee_sum)
            if diff > tolerance and base_price != 0:
                validation['warnings'].append(
                    f'Fee sum mismatch: 基价={base_price}, '
                    f'人工+材料+机械={fee_sum}, diff={round(diff, 2)}')

    entry['_validation'] = validation
    return entry


def validate_all(entries: list[dict], tolerance: float = 1.0) -> list[dict]:
    """Validate all entries. Returns entries with _validation fields added."""
    return [validate_entry(e, tolerance) for e in entries]


def print_validation_report(entries: list[dict]) -> None:
    """Print a human-readable validation report."""
    total = len(entries)
    errors = sum(1 for e in entries if e.get('_validation', {}).get('errors'))
    warnings = sum(1 for e in entries if e.get('_validation', {}).get('warnings'))
    clean = total - errors - warnings
    print(f'Validation: {total} entries — {clean} clean, {warnings} warnings, {errors} errors')
    if errors:
        print('  Errors:')
        for e in entries:
            for err in e.get('_validation', {}).get('errors', []):
                print(f'    [{e.get("定额编号", "?")}] {err}')
    if warnings:
        print('  Warnings:')
        for e in entries:
            for warn in e.get('_validation', {}).get('warnings', []):
                print(f'    [{e.get("定额编号", "?")}] {warn}')
