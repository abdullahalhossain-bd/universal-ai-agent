from app.query_engine.tools.product_search import ProductSearchTool
from app.query_engine.tools.stock_tool import StockTool
from app.query_engine.tools.knowledge_search import KnowledgeSearchTool
from app.query_engine.tools.image_analysis import ImageAnalysisTool


TOOLS = {
    "product_search": ProductSearchTool(),
    "stock": StockTool(),
    "knowledge_search": KnowledgeSearchTool(),
    "image_analysis": ImageAnalysisTool(),
}
