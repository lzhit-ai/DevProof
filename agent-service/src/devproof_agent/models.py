"""Vendor-neutral messages, tools and completion protocol."""

from dataclasses import dataclass
from typing import Protocol


class AgentError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict

    def wire(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.input_schema,
        }}


@dataclass(frozen=True)
class Completion:
    message: dict
    usage: dict


class Model(Protocol):
    async def complete(self, messages: list[dict], tools: list[ToolSpec], timeout: float) -> Completion: ...
