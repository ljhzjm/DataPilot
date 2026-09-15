import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ConfigDict, create_model
from pydantic_core import PydanticUndefined

from app.tools.definitions import FunctionDefinition, ToolDefinition

ToolHandler = Callable[..., Any]
ToolFunction = TypeVar("ToolFunction", bound=ToolHandler)


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    description: str
    input_model: type[BaseModel] | None
    handler: ToolHandler
    parallel_safe: bool = True
    input_schema: dict[str, Any] | None = None

    @property
    def definition(self) -> ToolDefinition:
        if self.input_model is not None:
            schema = self.input_model.model_json_schema()
        elif self.input_schema is not None:
            schema = self.input_schema
        else:
            raise ValueError(f"Tool '{self.name}' has no input schema.")
        schema.setdefault("additionalProperties", False)
        return ToolDefinition(
            function=FunctionDefinition(
                name=self.name,
                description=self.description,
                parameters=schema,
            )
        )

    async def invoke(self, arguments: dict[str, Any]) -> Any:
        if self.input_model is not None:
            validated = self.input_model.model_validate(arguments)
            kwargs = {name: getattr(validated, name) for name in self.input_model.model_fields}
        else:
            if self.input_schema is None:
                raise ValueError(f"Tool '{self.name}' has no input schema.")
            try:
                Draft202012Validator(self.input_schema).validate(arguments)
            except JsonSchemaValidationError as exc:
                raise ValueError(
                    f"Invalid arguments for tool '{self.name}': {exc.message}"
                ) from exc
            kwargs = arguments
        result = self.handler(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


def tool(
    *,
    name: str,
    description: str,
    parallel_safe: bool = True,
) -> Callable[[ToolFunction], RegisteredTool]:
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("Tool name must contain only letters, numbers, and underscores.")
    if not description.strip():
        raise ValueError("Tool description must not be empty.")

    def decorator(func: ToolFunction) -> RegisteredTool:
        input_model = _build_input_model(func, name)
        return RegisteredTool(
            name=name,
            description=description,
            input_model=input_model,
            handler=cast(ToolHandler, func),
            parallel_safe=parallel_safe,
        )

    return decorator


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, registered_tool: RegisteredTool) -> None:
        if registered_tool.name in self._tools:
            raise ValueError(f"Tool already registered: {registered_tool.name}")
        self._tools[registered_tool.name] = registered_tool

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        return [registered_tool.definition for registered_tool in self._tools.values()]


def _build_input_model(func: ToolHandler, tool_name: str) -> type[BaseModel]:
    signature = inspect.signature(func)
    try:
        type_hints = inspect.get_annotations(func, eval_str=True)
    except Exception as exc:
        raise TypeError(f"Unable to resolve annotations for tool '{tool_name}'.") from exc

    fields: dict[str, Any] = {}
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            raise TypeError(f"Tool '{tool_name}' contains unsupported parameter: {parameter.name}")

        annotation = type_hints.get(parameter.name, parameter.annotation)
        if annotation is inspect.Parameter.empty:
            raise TypeError(f"Tool parameter '{parameter.name}' must have a type annotation.")

        default = (
            PydanticUndefined if parameter.default is inspect.Parameter.empty else parameter.default
        )
        fields[parameter.name] = (annotation, default)

    model_name = "".join(part.capitalize() for part in tool_name.split("_")) + "Arguments"
    model = create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return cast(type[BaseModel], model)
