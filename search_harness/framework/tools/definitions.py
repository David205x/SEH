"""Declarative tool definitions shared by runtime and prompt renderers."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Annotated, Literal, Protocol, TypeVar, get_args, get_origin, get_type_hints

from .types import ToolResult


_MISSING = object()
_F = TypeVar("_F", bound=Callable[..., Any])


@dataclass(frozen=True)
class ToolArg:
    """Model-facing metadata for one callable parameter."""

    description: str
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: tuple[str | int | float | bool, ...] | None = None

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("tool argument description must not be empty")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("tool argument minimum cannot exceed maximum")


@dataclass(frozen=True)
class ToolParameter:
    """One normalized parameter in a tool definition."""

    name: str
    annotation: Any
    description: str
    required: bool
    default: Any = _MISSING
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: tuple[str | int | float | bool, ...] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Serialize this parameter to the JSON Schema fragment used by adapters."""

        schema = _annotation_to_json_schema(self.annotation)
        schema["description"] = self.description
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        if self.choices is not None:
            schema["enum"] = list(self.choices)
        if not self.required:
            schema["default"] = self.default
        return schema

    def with_default(self, default: Any) -> "ToolParameter":
        """Return an optional version of this parameter with a runtime default."""

        if not _is_json_value(default):
            raise ValueError("tool parameter default must be JSON-serializable")
        _validate_value(default, self, tool_name="definition")
        return replace(self, required=False, default=default)


@dataclass(frozen=True)
class ToolDefinition:
    """Prompt- and transport-neutral declaration for a callable tool."""

    name: str
    description: str
    parameters: tuple[ToolParameter, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.description.strip():
            raise ValueError("tool description must not be empty")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError(f"tool '{self.name}' has duplicate parameter names")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "description", self.description.strip())

    @classmethod
    def from_callable(
        cls,
        func: Callable[..., Any],
        *,
        name: str | None = None,
    ) -> "ToolDefinition":
        """Build a definition from a typed function and its docstring."""

        target = getattr(func, "__func__", func)
        signature = inspect.signature(target)
        hints = get_type_hints(target, include_extras=True)
        parameters: list[ToolParameter] = []

        for parameter in signature.parameters.values():
            if parameter.name in {"self", "cls"}:
                continue
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                raise ValueError(
                    f"tool '{target.__name__}' parameter '{parameter.name}' "
                    "must be a named parameter"
                )

            annotation = hints.get(parameter.name, parameter.annotation)
            value_type, metadata = _split_tool_annotation(annotation)
            if metadata is None:
                raise ValueError(
                    f"tool '{target.__name__}' parameter '{parameter.name}' "
                    "must use Annotated[..., ToolArg(...)]"
                )

            default = parameter.default
            required = default is inspect.Parameter.empty
            if not required and not _is_json_value(default):
                raise ValueError(
                    f"tool '{target.__name__}' parameter '{parameter.name}' "
                    "has a non-JSON default"
                )

            _annotation_to_json_schema(value_type)
            parameters.append(
                ToolParameter(
                    name=parameter.name,
                    annotation=value_type,
                    description=metadata.description,
                    required=required,
                    default=_MISSING if required else default,
                    minimum=metadata.minimum,
                    maximum=metadata.maximum,
                    choices=metadata.choices,
                )
            )

        description = inspect.getdoc(target) or ""
        return cls(
            name=name or target.__name__,
            description=description,
            parameters=tuple(parameters),
        )

    def to_json_schema(self) -> dict[str, Any]:
        """Return an object schema suitable for native tool-calling adapters."""

        return {
            "type": "object",
            "properties": {
                parameter.name: parameter.to_json_schema()
                for parameter in self.parameters
            },
            "required": [
                parameter.name for parameter in self.parameters if parameter.required
            ],
            "additionalProperties": False,
        }

    def with_default(self, parameter_name: str, default: Any) -> "ToolDefinition":
        """Return a definition with one runtime-specific optional default."""

        updated = False
        parameters: list[ToolParameter] = []
        for parameter in self.parameters:
            if parameter.name == parameter_name:
                parameters.append(parameter.with_default(default))
                updated = True
            else:
                parameters.append(parameter)
        if not updated:
            raise ValueError(
                f"tool '{self.name}' has no parameter named '{parameter_name}'"
            )
        return replace(self, parameters=tuple(parameters))

    def bind_arguments(self, arguments: dict[str, object]) -> dict[str, Any]:
        """Validate model arguments and fill callable defaults without coercion."""

        if not isinstance(arguments, dict):
            raise ValueError(f"tool '{self.name}' arguments must be an object")

        declared = {parameter.name for parameter in self.parameters}
        unexpected = sorted(set(arguments) - declared)
        if unexpected:
            raise ValueError(
                f"tool '{self.name}' received unexpected arguments: {', '.join(unexpected)}"
            )

        bound: dict[str, Any] = {}
        for parameter in self.parameters:
            if parameter.name not in arguments:
                if parameter.required:
                    raise ValueError(
                        f"tool '{self.name}' is missing required argument: {parameter.name}"
                    )
                bound[parameter.name] = parameter.default
                continue

            value = arguments[parameter.name]
            _validate_value(value, parameter, tool_name=self.name)
            bound[parameter.name] = value
        return bound


def tool(*, name: str | None = None) -> Callable[[_F], _F]:
    """Attach a generated ``ToolDefinition`` to a typed callable."""

    def decorate(func: _F) -> _F:
        definition = ToolDefinition.from_callable(func, name=name)
        setattr(func, "__tool_definition__", definition)
        return func

    return decorate


def get_tool_definition(func: Callable[..., Any]) -> ToolDefinition:
    """Return a definition attached by :func:`tool`."""

    target = getattr(func, "__func__", func)
    definition = getattr(target, "__tool_definition__", None)
    if not isinstance(definition, ToolDefinition):
        raise ValueError(
            f"callable '{getattr(target, '__name__', type(target).__name__)}' "
            "is not decorated with @tool"
        )
    return definition


@dataclass(frozen=True)
class CallableTool:
    """Core-loop tool adapter backed by an annotated callable."""

    definition: ToolDefinition
    func: Callable[..., ToolResult | str]

    @classmethod
    def from_callable(cls, func: Callable[..., ToolResult | str]) -> "CallableTool":
        """Bind an ``@tool`` callable for use by the core tool runtime."""

        return cls(definition=get_tool_definition(func), func=func)

    @property
    def name(self) -> str:
        return self.definition.name

    def run(self, arguments: dict[str, object]) -> ToolResult:
        try:
            bound_arguments = self.definition.bind_arguments(arguments)
        except ValueError as exc:
            return ToolResult(
                name=self.name,
                content=f"TOOL_INPUT_ERROR: {exc}",
                metadata={"error": str(exc), "error_type": "input_validation"},
            )
        result = self.func(**bound_arguments)
        if isinstance(result, ToolResult):
            return result
        return ToolResult(name=self.name, content=str(result))


class DefinedTool(Protocol):
    """A runtime tool exposing the definition that describes it."""

    definition: ToolDefinition
    name: str

    def run(self, arguments: dict[str, object]) -> ToolResult:
        """Execute one validated tool call."""


class ToolSet:
    """One immutable enabled-tool set shared by prompt and runtime wiring."""

    def __init__(self, tools: Iterable[DefinedTool]) -> None:
        items = tuple(tools)
        names = [item.name for item in items]
        if len(names) != len(set(names)):
            raise ValueError("tool set contains duplicate tool names")
        self._tools = items

    @property
    def tools(self) -> tuple[DefinedTool, ...]:
        """Return runtime tools in deterministic registration order."""

        return self._tools

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Return prompt-facing declarations for the same enabled tools."""

        return tuple(item.definition for item in self._tools)


def _split_tool_annotation(annotation: Any) -> tuple[Any, ToolArg | None]:
    if get_origin(annotation) is not Annotated:
        return annotation, None
    value_type, *items = get_args(annotation)
    metadata = next((item for item in items if isinstance(item, ToolArg)), None)
    return value_type, metadata


def _annotation_to_json_schema(annotation: Any) -> dict[str, Any]:
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal and args:
        literal_type = type(args[0])
        if literal_type is bool:
            schema_type = "boolean"
        elif literal_type is int:
            schema_type = "integer"
        elif literal_type is float:
            schema_type = "number"
        elif literal_type is str:
            schema_type = "string"
        else:
            raise ValueError(
                f"unsupported Literal value type: {literal_type!r}"
            )
        if any(type(value) is not literal_type for value in args):
            raise ValueError("Literal tool values must share one JSON type")
        return {"type": schema_type, "enum": list(args)}
    if origin is list and len(args) == 1:
        return {"type": "array", "items": _annotation_to_json_schema(args[0])}
    if origin is dict and args == (str, object):
        return {"type": "object"}

    raise ValueError(f"unsupported tool parameter annotation: {annotation!r}")


def _validate_value(value: object, parameter: ToolParameter, *, tool_name: str) -> None:
    if not _matches_annotation(value, parameter.annotation):
        expected = _annotation_to_json_schema(parameter.annotation)["type"]
        raise ValueError(
            f"tool '{tool_name}' argument '{parameter.name}' must be a {expected}"
        )

    if parameter.minimum is not None and value < parameter.minimum:  # type: ignore[operator]
        raise ValueError(
            f"tool '{tool_name}' argument '{parameter.name}' must be >= {parameter.minimum}"
        )
    if parameter.maximum is not None and value > parameter.maximum:  # type: ignore[operator]
        raise ValueError(
            f"tool '{tool_name}' argument '{parameter.name}' must be <= {parameter.maximum}"
        )
    if parameter.choices is not None and value not in parameter.choices:
        raise ValueError(
            f"tool '{tool_name}' argument '{parameter.name}' must be one of "
            f"{list(parameter.choices)}"
        )


def _matches_annotation(value: object, annotation: Any) -> bool:
    if annotation is str:
        return isinstance(value, str)
    if annotation is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if annotation is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if annotation is bool:
        return isinstance(value, bool)

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal and args:
        return value in args
    if origin is list and len(args) == 1:
        return isinstance(value, list) and all(
            _matches_annotation(item, args[0]) for item in value
        )
    if origin is dict and args == (str, object):
        return isinstance(value, dict) and all(isinstance(key, str) for key in value)
    return False


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False
