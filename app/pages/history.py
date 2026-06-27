"""History — browse all runs with filters."""
import streamlit as st
from app.utils import scan_runs, status_icon, status_label


def show():
    st.title("📜 运行历史")
    runs = scan_runs(limit=200)

    if not runs:
        st.info("还没有运行记录。")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        projs = sorted(set(r["project"] for r in runs if r["project"]))
        pf = st.selectbox("项目", ["全部"] + projs)
    with c2:
        sts = sorted(set(r["status"] for r in runs))
        sf = st.selectbox("状态", ["全部"] + sts)
    with c3:
        convs = sorted(set(r["converter"] for r in runs if r["converter"] != "?"))
        cf = st.selectbox("转换器", ["全部"] + convs)

    filtered = [r for r in runs
                if (pf == "全部" or r["project"] == pf)
                and (sf == "全部" or r["status"] == sf)
                and (cf == "全部" or r["converter"] == cf)]

    st.caption(f"{len(filtered)} / {len(runs)} 条")

    for r in filtered:
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([0.5, 2.5, 1, 1, 1.5])
            c1.markdown(f"### {status_icon(r['status'])}")
            c2.markdown(f"**{r['project'] or r['run_id'][:30]}**")
            c2.caption(r["run_id"][:50])
            c3.caption(f"{r['converter']} / {r['backend']}")
            c4.metric("条目", str(r.get("total_items") or "?"))
            c5c = c5.columns(2)
            c5c[0].button("📋", key=f"rh_{r['run_id'][:20]}", help="查看",
                          on_click=lambda rid=r["run_id"]: _nav(rid, "results"))
            c5c[1].button("🤖", key=f"rv_{r['run_id'][:20]}", help="校验",
                          on_click=lambda rid=r["run_id"]: _nav(rid, "upload"))
        st.divider()


def _nav(rid, page):
    import streamlit as st
    st.session_state.selected_run = rid
    st.session_state.page = page
