from flask import Blueprint, request, jsonify
from app.services.knowledge_graph_service import knowledge_graph_service
from app.utils.auth import login_required

knowledge_graph_bp = Blueprint("knowledge_graph", __name__)


@knowledge_graph_bp.route("/api/knowledge-graph/entities", methods=["GET"])
def get_entities():
    """获取知识库实体列表"""
    kb_id = request.args.get("kb_id")
    if not kb_id:
        # 返回400错误（请求参数错误），并提示缺失参数
        return jsonify({"error": "缺少必要参数: kb_id"}), 400
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 10))

    # 这里简化处理，实际应用中可能需要分页查询
    entities = knowledge_graph_service.search_entities(
        kb_id, "", limit=page_size * page
    )

    return jsonify(
        {
            "entities": entities[(page - 1) * page_size : page * page_size],
            "total": len(entities),
        }
    )


@knowledge_graph_bp.route("/api/knowledge-graph/relationships", methods=["GET"])
def get_relationships():
    """获取知识库关系列表"""
    kb_id = request.args.get("kb_id")
    if not kb_id:
        # 返回400错误（请求参数错误），并提示缺失参数
        return jsonify({"error": "缺少必要参数: kb_id"}), 400
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 10))
    relationships, total = knowledge_graph_service.get_relationships(
        kb_id, skip=(page - 1) * page_size, limit=page_size
    )

    return jsonify({"relationships": relationships, "total": total})


@knowledge_graph_bp.route("/api/knowledge-graph/search", methods=["GET"])
def search_knowledge_graph():
    """知识图谱检索"""
    kb_id = request.args.get("kb_id")
    if not kb_id:
        # 返回400错误（请求参数错误），并提示缺失参数
        return jsonify({"error": "缺少必要参数: kb_id"}), 400
    query = request.args.get("query", "")

    entities = knowledge_graph_service.search_entities(kb_id, query)

    return jsonify({"results": entities})


@knowledge_graph_bp.route("/api/knowledge-graph/visualize", methods=["GET"])
def get_visualization_data():
    """获取知识图谱可视化数据"""
    kb_id = request.args.get("kb_id")
    if not kb_id:
        # 返回400错误（请求参数错误），并提示缺失参数
        return jsonify({"error": "缺少必要参数: kb_id"}), 400
    limit = int(request.args.get("limit", 50))

    graph_data = knowledge_graph_service.get_graph_data(kb_id, limit=limit)

    return jsonify(graph_data)
