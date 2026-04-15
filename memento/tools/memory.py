import json
import os
import logging
from mcp.types import Tool, TextContent
from memento.registry import registry
from memento.tools.utils import get_active_goals

logger = logging.getLogger("memento-mcp")

@registry.register(Tool(
    name="memento_add_memory",
    description="Add a new memory to the Memento provider",
    inputSchema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The free text memory to add"
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata for the memory",
                "additionalProperties": True
            },
            "active_context": {
                "type": "string",
                "description": "Optional active contextual metadata (e.g. current file, active task) to frame the memory."
            }
        },
        "required": ["text"]
    }
))
async def memento_add_memory(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Cannot add memory. Current access state is: {access_manager.state}")
        
    text = arguments.get("text")
    if not text:
        raise ValueError("Text is required")
        
    metadata = arguments.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        
    active_context = arguments.get("active_context")
    if active_context:
        from memento.ontology import extract_logical_namespace
        namespace = extract_logical_namespace(active_context, ctx.workspace_root)
        if namespace and "module" not in metadata:
            metadata["module"] = namespace
            
    try:
        result = await ctx.provider.add(text, user_id=metadata.get("user_id", "default"), metadata=metadata)
        return [TextContent(type="text", text=f"Successfully added memory: {result}")]
    except Exception as e:
        logger.error(f"Error adding memory: {e}")
        return [TextContent(type="text", text=f"Error adding memory: {str(e)}")]

@registry.register(Tool(
    name="memento_search_memory",
    description="Search memories in the Memento provider",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query"
            },
            "active_context": {
                "type": "string",
                "description": "Optional active contextual metadata (e.g. current file, active task) to filter or contextualize the search."
            }
        },
        "required": ["query"]
    }
))
async def memento_search_memory(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Cannot search memory. Current access state is: {access_manager.state}")
        
    query = arguments.get("query")
    active_context = arguments.get("active_context")
    if not query:
        raise ValueError("Query is required")
        
    try:
        filters = {}
        if active_context:
            from memento.ontology import extract_logical_namespace
            namespace = extract_logical_namespace(active_context, ctx.workspace_root)
            if namespace:
                filters["module"] = namespace
                
        res = await ctx.provider.search(query, user_id="default", filters=filters)
        
        if not res:
            return [TextContent(type="text", text="No memories found.")]
        
        formatted_results = json.dumps(res, indent=2, ensure_ascii=False)
        injection = await get_active_goals(ctx, context=active_context) if ctx.enforcement_config.get("level1") else ""
        return [TextContent(type="text", text=f"{injection}Search results:\n{formatted_results}")]
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        return [TextContent(type="text", text=f"Error searching memory: {str(e)}")]

@registry.register(Tool(
    name="memento_migrate_workspace_memories",
    description="Copy-only migration: redistribute memories from a source DB into per-workspace DBs using deterministic text heuristics. Produces a JSON report.",
    inputSchema={
        "type": "object",
        "properties": {
            "source_db_path": {"type": "string"},
            "workspace_roots": {"type": "array", "items": {"type": "string"}},
            "report_path": {"type": "string"},
        },
        "required": ["source_db_path", "workspace_roots"],
    }
))
async def memento_migrate_workspace_memories(arguments: dict, ctx, access_manager) -> list[TextContent]:
    source_db_path = arguments.get("source_db_path")
    workspace_roots = arguments.get("workspace_roots")
    report_path = arguments.get("report_path") or os.path.join(ctx.workspace_root, ".memento", "migration_report.json")

    if not source_db_path or not isinstance(source_db_path, str):
        raise ValueError("source_db_path is required")
    if not isinstance(workspace_roots, list) or not workspace_roots:
        raise ValueError("workspace_roots must be a non-empty list")

    from memento.migration import migrate_memories_copy_only

    report = migrate_memories_copy_only(
        source_db_path=source_db_path,
        workspace_roots=workspace_roots,
        report_path=report_path,
    )

    return [
        TextContent(
            type="text",
            text=json.dumps(report["summary"], indent=2, ensure_ascii=False),
        )
    ]
