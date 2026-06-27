"""Upload & Run — PDF upload + pipeline execution + agent handoff."""
import streamlit as st
import os, json, subprocess, shutil
from datetime import datetime
from pathlib import Path
from app.utils import PROJECT_ROOT, WORKSPACE


def show():
    st.title("📤 上传与运行")
    st.caption("Web UI 执行管线 → Claude Code Agent 做智能校验")

    # ── Upload ──
    st.subheader("1️⃣ 选择 PDF")
    files = st.file_uploader("拖拽 PDF（支持批量）", type=["pdf"], accept_multiple_files=True,
                             label_visibility="collapsed")

    project = st.text_input("项目名称", placeholder="自动从文件名推断", key="prj")
    if files and not project:
        project = Path(files[0].name).stem[:25]
        st.caption(f"💡 自动推断项目名: **{project}**")

    if files:
        for f in files:
            st.caption(f"📄 {f.name}  ({f.size/1024:.0f} KB)")

    # ── Config ──
    st.subheader("2️⃣ 配置")
    st.radio("PDF 转换器", ["mineru", "ocr_vl"],
             format_func=lambda x: f"🌟 MinerU (推荐)" if x == "mineru" else "OCR_VL",
             index=0, horizontal=True, key="converter")
    converter = st.session_state.converter
    backend = "llm_direct"  # Web UI 仅支持 llm_direct；llm_codegen 由 Agent Skill 执行

    # ── Run ──
    st.subheader("3️⃣ 执行")
    if st.button("🚀 开始运行", disabled=not files or not project, type="primary", use_container_width=True):
        _run(files, project, converter, backend)


def _run(files, project, converter, backend):
    # Save uploads
    up_dir = WORKSPACE / "uploads" / project
    up_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for uf in files:
        dest = up_dir / uf.name
        dest.write_bytes(uf.getbuffer())
        saved.append(dest)
    st.success(f"✅ {len(saved)} 文件已保存")

    # Create run dir
    now = datetime.now()
    run_id = f"{now.strftime('%Y%m%d_%H%M')}_{project[:20]}_{converter}_{backend}"
    run_dir = WORKSPACE / "runs" / run_id
    for sub in ["markdown", "extracted", "verified", "reports", "logs"]:
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    # Write run.json
    meta = {
        "run_id": run_id, "project": project, "created": now.isoformat(),
        "status": "running",
        "config": {"converter": converter, "backend": backend, "model": os.getenv("LLM_MODEL", "?")},
        "results": {}, "timing": {"started": now.isoformat()},
    }
    (run_dir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Process each PDF
    log_path = run_dir / "logs" / "run.log"
    status_placeholder = st.empty()

    for pdf_path in saved:
        status_placeholder.info(f"⏳ 处理中: {pdf_path.name}...")

        try:
            # Step A: PDF → Markdown
            r = subprocess.run([
                "python", "-m", "pipeline.main", "convert",
                str(pdf_path), "--converter", converter,
                "--output", str(run_dir / "extracted" / f"{pdf_path.stem}_temp.json"),
            ], cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=600)

            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"=== CONVERT {pdf_path.name} ===\n{r.stdout}\n{r.stderr}\n")

            # Move generated markdown
            md_src = up_dir / f"{pdf_path.stem}.md"
            if md_src.exists():
                shutil.move(str(md_src), str(run_dir / "markdown" / md_src.name))
            else:
                # MinerU might output elsewhere
                for alt in up_dir.glob("*.md"):
                    shutil.move(str(alt), str(run_dir / "markdown" / alt.name))

            # Step B: Markdown → JSON
            md_dest = run_dir / "markdown" / f"{pdf_path.stem}.md"
            if md_dest.exists():
                r2 = subprocess.run([
                    "python", "-m", "pipeline.main", "convert",
                    str(md_dest), "--output", str(run_dir / "extracted" / f"{pdf_path.stem}.json"),
                ], cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=600)

                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"\n=== EXTRACT {pdf_path.stem}.md ===\n{r2.stdout}\n{r2.stderr}\n")

            status_placeholder.success(f"✅ {pdf_path.name} 完成")

        except subprocess.TimeoutExpired:
            status_placeholder.error(f"⏰ {pdf_path.name} 超时")
            meta["status"] = "failed"; (run_dir / "run.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            return
        except Exception as e:
            status_placeholder.error(f"❌ {pdf_path.name}: {e}")
            meta["status"] = "failed"; (run_dir / "run.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            return

    # Count results
    total = 0
    for jf in (run_dir / "extracted").glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                total += len(data)
        except Exception:
            pass

    meta["status"] = "extracted"
    meta["results"]["total_items"] = total
    meta["timing"]["extraction_done"] = datetime.now().isoformat()
    (run_dir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Agent handoff ──
    st.success(f"🎉 管线完成: **{total} 条** 数据已提取")
    st.divider()
    st.markdown("### 🤖 下一步：Agent 智能校验")

    st.markdown(f"""
    在 **Claude Code** 对话中运行：

    **校验数据**（推荐）：
    ```
    /pdf2json-verify {run_id}
    ```
    Agent 将对比原始 Markdown 逐条校验，修复 6 类常见问题。

    **或用代码提取**（省钱，省 token）：
    ```
    /pdf2json-codegen {run_id}
    ```
    Agent 将读表结构 → 生成解析代码 → 批量执行，1 次 LLM 调用替代 N 次。
    """)

    st.info("💡 **提示**：Agent 校验完成后，回到本页面刷新即可在「📋 结果浏览」中查看修复结果。")

    # Navigate
    if st.button("📋 查看提取结果", use_container_width=True):
        st.session_state.selected_run = run_id
        st.session_state.page = "results"
        st.rerun()
