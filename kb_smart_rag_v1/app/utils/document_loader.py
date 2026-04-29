from app.utils.logger import get_logger
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_core.documents import Document
from tempfile import NamedTemporaryFile
import os
import chardet

logger = get_logger(__name__)

class DocumentLoader:
    @staticmethod
    def load_pdf(file_data):
        try:
            with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name
            try:
                loader = PyPDFLoader(tmp_path)
                documents = loader.load()
                return documents
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"加载PDF时出错:{e}")
            raise ValueError(f"加载PDF时出错:{e}")

    @staticmethod
    def load_docx(file_data):
        try:
            with NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name
            try:
                loader = Docx2txtLoader(tmp_path)
                documents = loader.load()
                return documents
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"加载docx时出错:{e}")
            raise ValueError(f"加载docx时出错:{e}")

    @staticmethod
    def load_text(file_data):
        tmp_path = None
        try:
            # 1. 自动检测编码
            detected = chardet.detect(file_data)
            encoding = detected.get('encoding', 'utf-8')
            
            # 2. 增强处理：将常见的中文简码升级为 gb18030（兼容性最强）
            if encoding and encoding.lower() in ['gb2312', 'gbk', 'ascii']:
                encoding = 'gb18030'
            
            # 创建临时文件
            with NamedTemporaryFile(delete=False, suffix=".txt", mode="wb") as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name
            
            try:
                # 3. 尝试使用 LangChain 默认加载器
                loader = TextLoader(tmp_path, encoding=encoding)
                return loader.load()
            except Exception as e:
                logger.warning(f"使用 {encoding} 编码加载失败，尝试强行读取: {e}")
                # 4. 保底方案：手动读取并忽略错误字符，确保不中断
                try:
                    with open(tmp_path, 'r', encoding='gb18030', errors='ignore') as f:
                        content = f.read()
                    # 封装为 LangChain 文档对象
                    return [Document(page_content=content, metadata={"source": "local_upload"})]
                except Exception as final_e:
                    raise final_e
        except Exception as e:
            logger.error(f"加载text时出错:{e}")
            raise ValueError(f"加载text时出错:{e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @staticmethod
    def load(file_data, file_type):
        file_type = file_type.lower()
        if file_type == "pdf":
            return DocumentLoader.load_pdf(file_data)
        if file_type == "docx":
            return DocumentLoader.load_docx(file_data)
        if file_type in ["txt", "md"]:
            return DocumentLoader.load_text(file_data)
        else:
            raise ValueError(f"不支持的文件类型:{file_type}")