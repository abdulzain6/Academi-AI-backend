from langchain.document_loaders.base import BaseLoader
from extractous import Extractor, TesseractOcrConfig, PdfOcrStrategy, PdfParserConfig
from langchain.schema import Document
class ExtractousLoader(BaseLoader):
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self):
        pdf_config = PdfParserConfig().set_ocr_strategy(PdfOcrStrategy.NO_OCR)
        extractor = Extractor().set_ocr_config(TesseractOcrConfig().set_language("eng")).set_pdf_config(pdf_config)
        data = extractor.extract_file_to_string(self.file_path)
        return [Document(
            page_content=data[0]
        )]


print(ExtractousLoader("azure.py").load())
