"""PDF2json Web UI — 与 Claude Code Agent 协作的前端."""
import streamlit as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(
    page_title="PDF2json — 定额表结构化",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    with st.sidebar:
        st.markdown("## 📊 PDF2json")
        st.caption("工程预算定额 PDF → 结构化 JSON")

        # Quick status
        from app.utils import count_runs_by_status, count_projects
        n_proj = count_projects()
        n_done = count_runs_by_status("completed") + count_runs_by_status("extracted")
        st.markdown(f"📄 {n_proj} 项目  |  ✅ {n_done} 完成")

        st.divider()

        pages = {
            "🏠 仪表盘": "dashboard",
            "📤 上传与运行": "upload",
            "📋 结果浏览": "results",
            "📜 历史": "history",
            "⚖️ 对比": "compare",
        }

        if "page" not in st.session_state:
            st.session_state.page = "dashboard"

        for label, pid in pages.items():
            st.button(
                label, key=f"nav_{pid}", use_container_width=True,
                type="primary" if st.session_state.page == pid else "secondary",
                on_click=lambda p=pid: _nav(p),
            )

        st.divider()
        st.caption("💡 Web UI 管可视化\n🤖 Claude Code Agent 管智能校验")
        st.caption(f"工作区: `workspace/`")

    # Route
    page = st.session_state.get("page", "dashboard")
    if page == "dashboard":
        from app.pages import dashboard; dashboard.show()
    elif page == "upload":
        from app.pages import upload_run; upload_run.show()
    elif page == "results":
        from app.pages import results; results.show()
    elif page == "history":
        from app.pages import history; history.show()
    elif page == "compare":
        from app.pages import compare; compare.show()


def _nav(p: str):
    st.session_state.page = p


if __name__ == "__main__":
    main()
