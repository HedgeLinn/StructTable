from abc import ABC, abstractmethod


class ConverterAdapter(ABC):
    """PDF 转换工具/OCR 模型的统一接口。新增工具只需实现此类并放入 adapters/ 目录。"""

    # 仅参与这些评测维度，默认全部。子类可覆盖以限制评测范围。
    enabled_evaluators: list[str] | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """唯一标识，如 'opendataloader', 'markitdown', 'paddleocr'"""
        ...

    @abstractmethod
    def convert(self, pdf_path: str, output_dir: str) -> str:
        """转换单个 PDF → Markdown，返回生成的 .md 文件路径"""
        ...
