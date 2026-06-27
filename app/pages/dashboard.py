"""Dashboard — workspace overview."""
import streamlit as st
from app.utils import scan_runs, count_projects, count_runs_by_status, status_icon, status_label


def show():
    st.title("🏠 仪表盘")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📄 项目数", count_projects())
    with c2:
        st.metric("✅ 已完成", count_runs_by_status("completed") + count_runs_by_status("extracted"))
    with c3:
        st.metric("⚠️ 待审核", count_runs_by_status("needs_review"))
    with c4:
        st.metric("❌ 失败", count_runs_by_status("failed"))

    st.divider()
    st.subheader("📋 最近运行")
    runs = scan_runs(limit=20)

    if not runs:
        st.info("还没有运行记录。点击左侧 **📤 上传与运行** 开始。")
        return

    for r in runs[:10]:
        icon = status_icon(r["status"])
        with st.container():
            c1, c2, c3, c4 = st.columns([0.5, 3, 1, 1.5])
            with c1:
                st.markdown(f"### {icon}")
            with c2:
                verified_badge = " 🤖已审核" if r["verified"] else ""
                st.markdown(f"**{r['project'] or r['run_id'][:30]}**{verified_badge}")
                st.caption(f"{r['created'][:16]}  |  {r['converter']}  |  {r.get('total_items','?')} 条")
            with c3:
                err = r.get("error_rate")
                if err is not None:
                    st.metric("准确率", f"{(1-err)*100:.0f}%")
            with c4:
                if st.button("📋 查看", key=f"v_{r['run_id'][:20]}", use_container_width=True):
                    st.session_state.selected_run = r["run_id"]
                    st.session_state.page = "results"
                    st.rerun()
            st.divider()
