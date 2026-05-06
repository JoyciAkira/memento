import logging

from mcp.types import Tool, TextContent

from memento.registry import registry

logger = logging.getLogger("memento-mcp")


@registry.register(
    Tool(
        name="memento_pmg_add_entity",
        description=(
            "Add an entity to the Project Memory Graph. Entity types: file, component, decision, "
            "bug_fix, feature, session, module, api. Entities enable semantic relationships."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entity name (e.g. AuthModule, login_page.tsx)"},
                "entity_type": {
                    "type": "string",
                    "description": "Entity type: file, component, decision, bug_fix, feature, session, module, api",
                },
                "properties": {"type": "string", "description": "JSON string of additional properties"},
                "workspace_root": {"type": "string"},
            },
            "required": ["name", "entity_type"],
        },
    )
)
async def memento_pmg_add_entity(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Access: {access_manager.state}")
    name = arguments.get("name", "")
    entity_type = arguments.get("entity_type", "")
    props = None
    raw_props = arguments.get("properties")
    if raw_props:
        import json
        try:
            props = json.loads(raw_props)
        except Exception:
            props = {"raw": raw_props}
    ok = await ctx.project_memory_graph.add_entity(name=name, entity_type=entity_type, properties=props)
    return [TextContent(type="text", text=f"Entity '{name}' ({entity_type}) {'added' if ok else 'failed to add'}.")]


@registry.register(
    Tool(
        name="memento_pmg_add_relation",
        description=(
            "Add a relation between entities. Predicates: depends_on, blocks, implements, "
            "breaks, supersedes, relates_to, part_of, uses."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Source entity name"},
                "predicate": {
                    "type": "string",
                    "description": "Relation: depends_on, blocks, implements, breaks, supersedes, relates_to, part_of, uses",
                },
                "object": {"type": "string", "description": "Target entity name"},
                "workspace_root": {"type": "string"},
            },
            "required": ["subject", "predicate", "object"],
        },
    )
)
async def memento_pmg_add_relation(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_write():
        raise PermissionError(f"Access: {access_manager.state}")
    subject = arguments.get("subject", "")
    predicate = arguments.get("predicate", "")
    object_ = arguments.get("object", "")
    ok = await ctx.project_memory_graph.add_relation(subject=subject, predicate=predicate, object_=object_)
    return [TextContent(type="text", text=f"Relation '{subject} --{predicate}--> {object_}' {'added' if ok else 'failed'}.")]


@registry.register(
    Tool(
        name="memento_pmg_entity_context",
        description="Get semantic context for an entity including its relationships (what it depends on, what depends on it, etc.).",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Entity name to look up"},
                "depth": {"type": "integer", "description": "Traversal depth (1=direct, 2=one hop further)", "default": 1},
                "workspace_root": {"type": "string"},
            },
            "required": ["entity_name"],
        },
    )
)
async def memento_pmg_entity_context(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Access: {access_manager.state}")
    entity = arguments.get("entity_name", "")
    depth = int(arguments.get("depth") or 1)
    context = await ctx.project_memory_graph.get_entity_context(entity_name=entity, depth=depth)
    return [TextContent(type="text", text=context)]


@registry.register(
    Tool(
        name="memento_pmg_what_might_break",
        description="Find all entities that depend on the given entity (impact analysis).",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Entity to check"},
                "workspace_root": {"type": "string"},
            },
            "required": ["entity_name"],
        },
    )
)
async def memento_pmg_what_might_break(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Access: {access_manager.state}")
    entity = arguments.get("entity_name", "")
    dependents = await ctx.project_memory_graph.get_what_might_break(entity_name=entity)
    if not dependents:
        return [TextContent(type="text", text=f"No entities depend on '{entity}'.")]
    lines = [f"Entities that depend on '{entity}':"]
    for d in dependents:
        lines.append(f"  - {d}")
    return [TextContent(type="text", text="\n".join(lines))]


@registry.register(
    Tool(
        name="memento_pmg_summary",
        description="Get a summary of the entire Project Memory Graph (all entities and recent relations).",
        inputSchema={"type": "object", "properties": {"workspace_root": {"type": "string"}}},
    )
)
async def memento_pmg_summary(arguments: dict, ctx, access_manager) -> list[TextContent]:
    if not access_manager.can_read():
        raise PermissionError(f"Access: {access_manager.state}")
    summary = await ctx.project_memory_graph.get_project_summary()
    return [TextContent(type="text", text=summary)]
