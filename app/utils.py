"""Shared utils: workspace scanning, run metadata, Markdown search."""
import json, os, re
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = PROJECT_ROOT / "workspace"
RUNS = WORKSPACE / "runs"
UPLOADS = WORKSPACE / "uploads"


def scan_runs(limit: int = 50, project: str = "", status: str = "") -> list[dict]:
    results = []
    if not RUNS.exists():
        return results
    for d in sorted(RUNS.iterdir(), key=os.path.getmtime, reverse=True):
        rj = d / "run.json"
        meta = {}
        if rj.exists():
            try:
                meta = json.loads(rj.read_text(encoding="utf-8"))
            except Exception:
                pass
        p = meta.get("project", "")
        s = meta.get("status", "unknown")
        if project and project != p:
            continue
        if status and status != s:
            continue
        n = 0
        ed = d / "extracted"
        if ed.exists():
            for jf in ed.glob("*.json"):
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        n += len(data)
                except Exception:
                    pass
        verified = (d / "verified").exists() and any((d / "verified").glob("*.json"))
        results.append({
            "run_id": d.name,
            "project": p,
            "status": s,
            "converter": meta.get("config", {}).get("converter", "?"),
            "backend": meta.get("config", {}).get("backend", "?"),
            "model": meta.get("config", {}).get("model", "?"),
            "total_items": n or meta.get("results", {}).get("total_items"),
            "error_rate": meta.get("results", {}).get("error_rate"),
            "fixed_count": meta.get("results", {}).get("fixed_count"),
            "unresolved_count": meta.get("results", {}).get("unresolved_count"),
            "verified": verified or meta.get("results", {}).get("verified", False),
            "created": meta.get("created", ""),
            "path": str(d),
        })
        if len(results) >= limit:
            break
    return results


def get_run(run_id: str) -> dict | None:
    d = RUNS / run_id
    if not d.exists():
        return None
    rj = d / "run.json"
    meta = {}
    if rj.exists():
        try:
            meta = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            pass
    meta["run_id"] = run_id
    meta["path"] = str(d)
    return meta


def get_items(run_id: str, verified: bool = False) -> list[dict]:
    d = RUNS / run_id
    if not d.exists():
        return []
    sub = "verified" if verified else "extracted"
    sd = d / sub
    if not sd.exists():
        return []
    for jf in sorted(sd.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            continue
    return []


def get_markdown(run_id: str) -> str | None:
    md_dir = RUNS / run_id / "markdown"
    if not md_dir.exists():
        return None
    for mf in sorted(md_dir.glob("*.md")):
        try:
            return mf.read_text(encoding="utf-8")
        except Exception:
            continue
    return None


def count_projects() -> int:
    if not UPLOADS.exists():
        return 0
    return len([d for d in UPLOADS.iterdir() if d.is_dir()])


def count_runs_by_status(status: str) -> int:
    if not RUNS.exists():
        return 0
    n = 0
    for d in RUNS.iterdir():
        rj = d / "run.json"
        if rj.exists():
            try:
                if json.loads(rj.read_text(encoding="utf-8")).get("status") == status:
                    n += 1
            except Exception:
                pass
    return n


def parse_quota_id(item: dict) -> str:
    for k in ("定额编号", "清单编码", "清单编号", "指标编号"):
        if k in item:
            return str(item[k])
    return "?"


def extract_markdown_context(md: str, quota_id: str) -> str:
    if not md:
        return ""
    pat = re.compile(r'(<table\b[^>]*>.*?</table>)', re.DOTALL)
    for m in pat.finditer(md):
        if quota_id in m.group(0):
            return m.group(0)[:3000]
    idx = md.find(quota_id)
    if idx < 0:
        return ""
    return md[max(0, idx - 500):min(len(md), idx + 3000)]


def status_icon(s: str) -> str:
    return {"running": "⏳", "extracted": "✅", "completed": "✅",
            "needs_review": "⚠️", "failed": "❌"}.get(s, "⬜")


def status_label(s: str) -> str:
    return {"running": "运行中", "extracted": "已提取", "completed": "已完成",
            "needs_review": "待审核", "failed": "失败"}.get(s, s)
