"""Validated Phase 2 model action tools."""

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from wingman.models import User
from wingman.services import (
    confirm_memory,
    create_memory,
    delete_memory,
    record_tool_execution,
    update_memory,
)


class CreateMemoryInput(BaseModel):
    statement: str = Field(min_length=1, max_length=4000)
    memory_type: str = Field(default="fact", max_length=40)
    status: str = Field(default="confirmed", max_length=20)
    confidence: float = Field(default=1.0, ge=0, le=1)
    importance: int = Field(default=3, ge=1, le=5)


class UpdateMemoryInput(BaseModel):
    memory_id: str
    statement: str | None = Field(default=None, min_length=1, max_length=4000)
    memory_type: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)
    importance: int | None = Field(default=None, ge=1, le=5)


class MemoryToolExecutor:
    def __init__(self, session: Session, user: User, agent_run_id: str | None = None) -> None:
        self.session = session
        self.user = user
        self.agent_run_id = agent_run_id

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "create_memory":
                create_data = CreateMemoryInput.model_validate(arguments)
                memory = create_memory(self.session, self.user, **create_data.model_dump())
            elif name == "update_memory":
                update_data = UpdateMemoryInput.model_validate(arguments)
                fields = update_data.model_dump(exclude_none=True)
                memory_id = fields.pop("memory_id")
                if "memory_type" in fields:
                    fields["type"] = fields.pop("memory_type")
                memory = update_memory(self.session, self.user, memory_id, **fields)
            elif name == "delete_memory":
                memory = delete_memory(self.session, self.user, str(arguments["memory_id"]))
            elif name == "confirm_memory":
                memory = confirm_memory(self.session, self.user, str(arguments["memory_id"]))
            else:
                raise ValueError("Unknown tool")
            output = {"memory_id": memory.id, "status": memory.status}
            record_tool_execution(
                self.session,
                self.user,
                name,
                arguments,
                output_data=output,
                agent_run_id=self.agent_run_id,
            )
            return output
        except Exception as exc:
            record_tool_execution(
                self.session,
                self.user,
                name,
                arguments,
                status="failed",
                error=str(exc),
                agent_run_id=self.agent_run_id,
            )
            raise
