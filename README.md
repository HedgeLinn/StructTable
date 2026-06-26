# PDF2json

将工程预算定额 PDF 转换为结构化 JSON 数据。使用 LLM 自动发现表格结构，
无需预设字段名，支持定额表、全费用清单、区域定价表等多种格式。

## 快速开始

```bash
# 1. 安装依赖
pip install -e .

# 2. 配置环境变量
cp .env.example .env   # 编辑 .env 填入 API key

# 3. 运行
python -m pipeline.main convert input.md --output output.json
python -m pipeline.main batch input_dir/ --output output_dir/
```

## 架构

```
PDF ──[OCR_VL]──→ Markdown (HTML 表格)
        │
        └──[opendataloader]──→ GFM Markdown (条目边界参考)
                                        │
                              [postprocess.py] 融合
                                        │
                              [llm_extractor.py] LLM 提取
                                        │
                                     JSON
```

### 核心原则

OCR_VL 和 opendataloader 必须配合使用：

| 工具 | 优势 | 盲区 |
|------|------|------|
| OCR_VL | 复杂结构还原（rowspan/colspan） | 单元格内独立条目合并 |
| ODL | 独立条目分辨（cell 天然分隔） | 复杂合并结构还原差 |

### 管线组件

```
pipeline/
├── main.py              # CLI 入口 (convert / batch / validate)
├── config.py            # 基础设施配置 (从 .env 读取)
├── document_parser.py   # 文档解析 + 多表捕获 + 重复段合并
├── llm_extractor.py     # LLM 提取引擎 (自动发现结构)
│                        #   - 续表识别与合并
│                        #   - Token 估计与智能拆分
│                        #   - 后处理孤立条目归附
│                        #   - 异常输出自动重试
│                        #   - 健康监控面板
├── postprocess.py       # OCR_VL + ODL 融合修复
└── utils.py             # 通用工具 (解析器 / 校验器)
```

## 配置

所有配置通过环境变量管理，参见 `.env.example`。

## 许可

内部项目
