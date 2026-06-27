"""Compare — side-by-side run comparison."""
import streamlit as st
from app.utils import scan_runs, get_items, parse_quota_id, status_icon


def show():
    st.title("⚖️ 运行对比")
    runs = scan_runs(limit=50)

    if len(runs) < 2:
        st.info("至少需要 2 条记录。")
        return

    labels = [f"{status_icon(r['status'])} {r['created'][:16]} | {r['project']} | {r['total_items']}条" for r in runs]
    c1, c2 = st.columns(2)
    with c1:
        ia = st.selectbox("运行 A", range(len(runs)), format_func=lambda i: labels[i])
    with c2:
        ib = st.selectbox("运行 B", range(len(runs)), format_func=lambda i: labels[i], index=min(1, len(runs)-1))

    if ia == ib:
        st.warning("请选择不同的运行")
        return

    ra, rb = runs[ia], runs[ib]
    items_a = get_items(ra["run_id"])
    items_b = get_items(rb["run_id"])

    ids_a = set(parse_quota_id(i) for i in items_a)
    ids_b = set(parse_quota_id(i) for i in items_b)

    st.subheader("📊 指标对比")
    rows = [
        ("总条目", len(items_a), len(items_b)),
        ("转换器", ra["converter"], rb["converter"]),
        ("后端", ra["backend"], rb["backend"]),
    ]
    for label, va, vb in rows:
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.markdown(f"**{label}**")
        c2.metric("A", va)
        c3.metric("B", vb, delta=vb - va if isinstance(va, int) else None)

    st.divider()
    st.subheader("🔍 ID 覆盖")
    both, only_a, only_b = ids_a & ids_b, ids_a - ids_b, ids_b - ids_a
    c1, c2, c3 = st.columns(3)
    c1.metric("🟢 共有", len(both))
    c2.metric("🟡 仅 A", len(only_a))
    c3.metric("🔴 仅 B", len(only_b))

    if only_a:
        with st.expander(f"仅 A 的 ID ({len(only_a)})"):
            st.text(", ".join(sorted(only_a)))
    if only_b:
        with st.expander(f"仅 B 的 ID ({len(only_b)})"):
            st.text(", ".join(sorted(only_b)))
