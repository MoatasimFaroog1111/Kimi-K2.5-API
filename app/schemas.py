from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


class ChatResponse(BaseModel):
    response: str
    model: str


class AgentRequest(ChatRequest):
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    auto_model: bool = True


class FileApprovalRequest(BaseModel):
    paths: list[str] = Field(default_factory=list, max_length=20)


class CiRepairRequest(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=100)
    auto_model: bool = True


class ProposalResponse(BaseModel):
    proposal: dict
