# PDF2json

将工程预算定额 PDF 转换为结构化 JSON 数据。使用 LLM 自动发现表格结构，
无需预设字段名，支持定额表、全费用清单、区域定价表等多种格式。

## 快速开始

```bash
# 1. 安装依赖
pip install -e .

# 2. 配置环境变量
cp .env.example .env   # 编辑 .env 填入 API key 和 MinerU token

# 3. 运行
python -m pipeline.main convert input.md --output output.json
python -m pipeline.main convert input.pdf --converter mineru --output output.json
python -m pipeline.main batch input_dir/ --output output_dir/
```

## 架构

```
PDF ──┬──[OCR_VL]──→ Markdown (HTML 表格 + 上下文)
      │                    │
      │                    └──[opendataloader]──→ GFM Markdown (条目边界参考)
      │                                                    │
      │                                          [postprocess.py] 融合
      │                                                    │
      └──[MinerU]──→ Markdown (干净 HTML 表格 + 上下文)    │
                                          │                 │
                                          └─────┬───────────┘
                                                │
                                    [llm_extractor.py] LLM 提取
                                                │
                                              JSON
```

### PDF 转换器选择

| 转换器 | 命令 | 特点 |
|--------|------|------|
| **MinerU** (推荐) | `--converter mineru` | 干净表格 + 材料行天然分离 + 完整上下文，无需后处理 |
| OCR_VL | `--converter ocr_vl` (默认) | 有上下文但合并单元格内多条目，需 ODL 融合修复 |

```bash
# 通过 .env 设置默认值
CONVERTER=mineru

# 或 CLI 显式指定
python -m pipeline.main convert input.pdf --converter mineru
python -m pipeline.main batch PDF_DIR/ --converter mineru
```

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
├── postprocess.py       # OCR_VL + ODL 融合修复 (仅 OCR_VL 路径需要)
├── utils.py             # 通用工具 (解析器 / 校验器)
└── pdf2markdown/
    ├── base.py          #   ConverterAdapter 抽象基类
    ├── ocr_vl.py        #   OCR_VL HTTP API 适配器
    ├── mineru.py        #   MinerU 云端适配器 (新增)
    └── batch_convert.py #   批量转换脚本
```

## 配置

所有配置通过环境变量管理，参见 `.env.example`。

### MinerU 配置

```ini
CONVERTER=mineru
MINERU_TOKEN=your-token              # 从 mineru.net API 管理页面获取
MINERU_URL=https://mineru.net/api/v4
MINERU_MODEL_VERSION=vlm             # vlm | pipeline
MINERU_POLL_MAX=600                  # 最长等待（秒）
MINERU_BATCH_WORKERS=3
```

## 许可

内部项目
