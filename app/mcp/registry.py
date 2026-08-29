"""The tool registry.

One definition per tool -- name, JSON schema, handler -- consumed by three
callers that must never disagree:

  * app/mcp/server.py     registers each entry with the MCP server at /mcp
  * app/mcp/client.py     dispatches in-process calls against the same entries
  * openai_tool_specs()   renders them as OpenAI function-calling specs

Handlers are plain synchronous functions that open their own database session.
They are invoked off the event loop (see ``call_tool_async``), which keeps the
sync/async split this codebase relies on intact.
"""

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.mcp.context import ANONYMOUS, ToolContext

logger = logging.getLogger(__name__)

Handler = Callable[..., Any]


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Handler
    # Tenant-scoped tools read the caller's own company data and must never be
    # served to an anonymous context.
    tenant_scoped: bool = False
    # Tools whose results are large enough to be worth truncating before they
    # reach a model context.
    max_result_chars: int = 24_000

    def to_openai_spec(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: Dict[str, Tool] = {}


def register(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    tenant_scoped: bool = False,
) -> Callable[[Handler], Handler]:
    """Decorator registering a function as a tool.

    The handler receives keyword arguments matching the schema, plus ``ctx``.
    """

    def decorator(func: Handler) -> Handler:
        if name in _REGISTRY:
            raise ValueError(f"Duplicate tool registration: {name}")
        _REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=func,
            tenant_scoped=tenant_scoped,
        )
        return func

    return decorator


def unregister(name: str) -> None:
    """Remove a tool. Used when a tool's preconditions are not met at startup."""
    _REGISTRY.pop(name, None)


def get_tool(name: str) -> Optional[Tool]:
    return _REGISTRY.get(name)


def all_tools() -> List[Tool]:
    return sorted(_REGISTRY.values(), key=lambda t: t.name)


def openai_tool_specs(include_tenant_scoped: bool = True) -> List[Dict[str, Any]]:
    return [
        tool.to_openai_spec()
        for tool in all_tools()
        if include_tenant_scoped or not tool.tenant_scoped
    ]


def _coerce_arguments(tool: Tool, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Drop arguments the handler does not accept.

    Models routinely invent a plausible extra parameter. Passing it straight
    through would raise TypeError and turn a slightly-wrong call into a hard
    failure, so unknown keys are dropped with a log line instead.
    """
    signature = inspect.signature(tool.handler)
    accepts_kwargs = any(
        param.kind is inspect.Parameter.VAR_KEYWORD
        for param in signature.parameters.values()
    )

    # `ctx` is supplied by the dispatcher from a verified token. A model that
    # invents one would both collide with that keyword and, if it somehow got
    # through, be claiming an identity. Drop it before anything else.
    arguments = {k: v for k, v in arguments.items() if k != "ctx"}

    if accepts_kwargs:
        return arguments

    known = set(signature.parameters) - {"ctx"}
    cleaned = {}
    for key, value in arguments.items():
        if key in known:
            cleaned[key] = value
        else:
            logger.info("Dropping unknown argument %r for tool %s", key, tool.name)
    return cleaned


def call_tool(
    name: str, arguments: Optional[Dict[str, Any]] = None, ctx: Optional[ToolContext] = None
) -> Any:
    """Invoke a tool synchronously. Raises KeyError for an unknown tool."""
    tool = _REGISTRY.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")

    context = ctx or ANONYMOUS
    if tool.tenant_scoped and not context.is_authenticated:
        raise PermissionError(f"Tool {name} requires an authenticated caller.")

    kwargs = _coerce_arguments(tool, arguments or {})
    return tool.handler(ctx=context, **kwargs)


def serialise_result(tool_name: str, result: Any) -> str:
    """Render a tool result as JSON for a model, truncating if oversized.

    Truncation is announced in the payload rather than silent: a model that can
    see it only got part of the answer will narrow its query instead of
    confidently reporting a partial total as the total.
    """
    tool = _REGISTRY.get(tool_name)
    limit = tool.max_result_chars if tool else 24_000

    try:
        payload = json.dumps(result, default=str, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        logger.error("Tool %s returned unserialisable result: %s", tool_name, exc)
        return json.dumps({"error": "Result could not be serialised."})

    if len(payload) <= limit:
        return payload

    return json.dumps(
        {
            "truncated": True,
            "note": (
                f"Result exceeded {limit} characters and was cut off. "
                "Narrow the filters or lower the limit for a complete answer."
            ),
            "partial": payload[:limit],
        },
        ensure_ascii=False,
    )
