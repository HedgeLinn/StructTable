"""Results Viewer — browse items with Markdown cross-reference + agent fix display."""
import streamlit as st
from app.utils import (
    scan_runs, get_items, get_markdown, get_run,
    parse_quota_id, extract_markdown_context, status_icon, status_label,
)


def show():
    st.title("📋 结果浏览")

    runs = scan_runs(limit=30)
    if not runs:
        st.info("还没有运行记录。")
        return

    # Run selector
    selected = st.session_state.get("selected_run")
    labels = [f"{status_icon(r['status'])} {r['created'][:16]} | {r['project']} | {r['total_items']}条" for r in runs]
    default = 0
    if selected:
        for i, r in enumerate(runs):
            if r["run_id"] == selected:
                default = i; break

    chosen = st.selectbox("选择运行", labels, index=default, label_visibility="collapsed")
    run = runs[labels.index(chosen)]
    run_id = run["run_id"]
    st.session_state.selected_run = run_id

    # Detect if agent verification has been done
    verified_items = get_items(run_id, verified=True)
    has_verified = len(verified_items) > 0

    if has_verified:
        st.success(f"🤖 Agent 已校验此运行 — {len(verified_items)} 条修复后数据可用")

    # Load data
    items = verified_items if has_verified else get_items(run_id)
    md = get_markdown(run_id)
    meta = get_run(run_id) or {}

    if not items:
        st.warning("没有数据。")
        return

    # Stats
    n_id = sum(1 for i in items if any(k in i for k in ("定额编号", "清单编码", "清单编号", "指标编号")))
    n_fix = sum(1 for i in items if "_fix_log" in i)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总条目", len(items))
    c2.metric("含编号", n_id)
    c3.metric("Agent 修复", n_fix)
    c4.metric("状态", status_label(meta.get("status", "?")))

    st.divider()

    # Filters
    cf1, cf2 = st.columns(2)
    with cf1:
        h2s = sorted(set(i.get("_source", {}).get("h2", "")[:40] for i in items if i.get("_source", {}).get("h2")))
        h2f = st.selectbox("章节", ["全部"] + h2s)
    with cf2:
        id_s = st.text_input("ID 搜索", placeholder="如 9-1")

    filtered = items
    if h2f != "全部":
        filtered = [i for i in filtered if i.get("_source", {}).get("h2", "")[:40] == h2f]
    if id_s:
        filtered = [i for i in filtered if id_s in parse_quota_id(i)]

    st.caption(f"{len(filtered)} / {len(items)} 条")

    # Layout
    left, right = st.columns([1, 1.6])

    with left:
        st.subheader("条目列表")
        for idx, item in enumerate(filtered):
            qid = parse_quota_id(item)
            name = item.get("项目名称", "?")[:25]
            spec = item.get("规格", "")
            base = item.get("基价", "?")
            fixed = "🔧 " if "_fix_log" in item else ""
            if st.button(f"{fixed}{qid}  {name}", key=f"it_{idx}", use_container_width=True,
                         help=f"规格:{spec}  基价:{base}"):
                st.session_state.detail_item = item

    with right:
        st.subheader("条目详情")
        detail = st.session_state.get("detail_item")
        if detail:
            _render_detail(detail, md)
        else:
            st.info("← 点击左侧条目查看详情")

    # JSON export
    if detail:
        with st.expander("📄 原始 JSON"):
            st.json(detail)


def _render_detail(item: dict, md: str | None):
    qid = parse_quota_id(item)
    st.markdown(f"### {qid}")
    st.caption(item.get("项目名称", item.get("清单名称", "?")))

    for k, v in item.items():
        if k.startswith("_") or k in ("人工", "材料", "机械", "费用构成"):
            continue
        st.markdown(f"- **{k}**: {v}")

    fee = item.get("费用构成")
    if fee:
        st.markdown("**费用构成**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("人工费", fee.get("人工费", 0))
        c2.metric("材料费", fee.get("材料费", 0))
        c3.metric("机械费", fee.get("机械费", 0))
        c4.metric("合计", fee.get("人工费", 0) + fee.get("材料费", 0) + fee.get("机械费", 0))

    for cat in ("人工", "材料", "机械"):
        rows = item.get(cat, [])
        if rows:
            with st.expander(f"{cat} ({len(rows)})", expanded=len(rows) <= 5):
                for r in rows:
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                    c1.markdown(f"**{r.get('名称','?')}**")
                    c2.caption(r.get("单位", "?"))
                    c3.caption(f"¥{r.get('单价',0)}")
                    c4.caption(f"×{r.get('数量',0)}")

    # Agent fix log
    fixes = item.get("_fix_log", [])
    if fixes:
        st.divider()
        st.markdown("### 🤖 Agent 修复记录")
        for fix in fixes:
            conf = fix.get("confidence", "?")
            color = {"high": "green", "medium": "orange", "low": "red"}.get(conf, "grey")
            st.markdown(f":{color}[{conf}] **{fix.get('action','?')}**: "
                        f"`{fix.get('original_value','?')}` → `{fix.get('corrected_value','?')}`")
            st.caption(f"依据: {fix.get('evidence','?')}")

    # Markdown cross-ref
    if md:
        st.divider()
        st.markdown("### 📝 Markdown 原文对照")
        ctx = extract_markdown_context(md, qid)
        if ctx:
            with st.container(height=300):
                st.code(ctx, language="html")
