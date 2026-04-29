import logging
import tempfile
import os
from pdfplumber import PDFPlumber
import pytesseract
from PIL import Image
import layoutparser as lp
import camelot
from pdf2image import convert_from_bytes
from typing import Dict, List, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentPipeline:
    def __init__(self):
        """初始化文档处理流水线，加载布局分析模型"""
        try:
            # 这里的模型加载可能比较慢，取决于你的 5070 Ti 和网络状态
            self.layout_model = lp.Detectron2LayoutModel(
                "lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config",
                extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.8],
            )
            logger.info("布局分析模型初始化成功")
        except Exception as e:
            logger.warning(f"布局分析模型初始化失败: {str(e)}, 将使用默认处理流程")
            self.layout_model = None

    def process(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        处理入口：根据后缀名分发到不同的处理函数
        """
        file_ext = os.path.splitext(filename)[1].lower()
        logger.info(f"🚀 开始处理文档: {filename}, 格式: {file_ext}")

        # 1. 处理 PDF
        if file_ext == ".pdf":
            return self._process_pdf(file_content)
        
        # 2. 处理 TXT (显式支持)
        elif file_ext == ".txt":
            logger.info(f"检测到纯文本格式，进入通用文本处理流程")
            return self._process_generic_text(file_content)
            
        # 3. 处理图片 (OCR)
        elif file_ext in [".png", ".jpg", ".jpeg", ".tiff"]:
            return self._process_image(file_content)
            
        # 4. 其他格式兜底
        else:
            logger.warning(f"⚠️ 遇到未知格式 {file_ext}，尝试作为通用文本解析")
            return self._process_generic_text(file_content)

    def _process_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """处理PDF文件，结合 pdfplumber、Camelot 和 LayoutParser"""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                temp_pdf.write(pdf_content)
                temp_pdf_path = temp_pdf.name

            text = []
            # 基础文本提取
            with PDFPlumber.open(temp_pdf_path) as pdf:
                for page in pdf.pages:
                    content = page.extract_text()
                    if content:
                        text.append(content)
            full_text = "\n".join(text)

            # 表格解析
            table_data = []
            try:
                tables = camelot.read_pdf(temp_pdf_path, flavor="lattice", pages="all")
                for table in tables:
                    table_data.append(table.df.to_dict("records"))
            except Exception as e:
                logger.warning(f"表格提取跳过: {str(e)}")

            # 布局分析 (利用你的显卡能力)
            layout_data = []
            if self.layout_model:
                try:
                    images = convert_from_bytes(pdf_content)
                    for image in images:
                        layout = self.layout_model.detect(image)
                        layout_data.append([
                            {"type": block.type, "coordinates": block.coordinates}
                            for block in layout
                        ])
                except Exception as e:
                    logger.warning(f"布局分析失败: {str(e)}")

            chunks = self._chunk_text(full_text, table_data, layout_data)
            os.unlink(temp_pdf_path) # 清理临时文件

            return {
                "text": full_text,
                "layout": layout_data,
                "tables": table_data,
                "chunks": chunks,
            }
        except Exception as e:
            logger.error(f"❌ PDF处理失败: {str(e)}", exc_info=True)
            return self._process_image(pdf_content) # PDF 挂了就转 OCR 试试

    def _process_image(self, image_content: bytes) -> Dict[str, Any]:
        """图片处理逻辑：使用 Tesseract OCR"""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_img:
                temp_img.write(image_content)
                temp_img_path = temp_img.name

            text = pytesseract.image_to_string(Image.open(temp_img_path), lang='chi_sim+eng')
            chunks = self._chunk_text(text, [], [])
            os.unlink(temp_img_path)

            return {"text": text, "layout": [], "tables": [], "chunks": chunks}
        except Exception as e:
            logger.error(f"❌ 图片处理失败: {str(e)}", exc_info=True)
            return {"text": "", "layout": [], "tables": [], "chunks": []}

    def _process_generic_text(self, text_content: bytes) -> Dict[str, Any]:
        """
        通用文本处理：增加了自动编码识别逻辑
        """
        try:
            # 尝试多种编码，解决 Windows 常见的 GBK/UTF-8 冲突
            text = None
            for encoding in ['utf-8', 'gbk', 'utf-16', 'ansi']:
                try:
                    text = text_content.decode(encoding)
                    logger.info(f"成功使用 {encoding} 编码解码文本")
                    break
                except UnicodeDecodeError:
                    continue
            
            if text is None:
                # 最后的倔强：带错误替换的解码
                text = text_content.decode("utf-8", errors="replace")
                logger.warning("所有已知编码尝试失败，已使用强制替换模式解码")

            chunks = self._chunk_text(text, [], [])
            return {"text": text, "layout": [], "tables": [], "chunks": chunks}
        except Exception as e:
            logger.error(f"❌ 文本处理彻底失败: {str(e)}", exc_info=True)
            return {"text": "", "layout": [], "tables": [], "chunks": []}

    def _chunk_text(self, text: str, tables: List[Any] = None, layouts: List[Any] = None) -> List[str]:
        """分块逻辑：按段落切分，保持语义相对完整"""
        chunks = []
        current_chunk = []
        chunk_size = 0
        MAX_CHUNK_SIZE = 800 # 你可以根据需求调整分块大小

        for paragraph in text.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            if chunk_size + len(paragraph) > MAX_CHUNK_SIZE:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                current_chunk = [paragraph]
                chunk_size = len(paragraph)
            else:
                current_chunk.append(paragraph)
                chunk_size += len(paragraph)

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        # 将表格也转为文本块
        for table in (tables or []):
            chunks.append(f"表格内容摘要: {str(table)}")

        return chunks