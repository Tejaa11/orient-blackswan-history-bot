"""The LLM selects evidence; the backend owns all page references."""
from dataclasses import asdict, dataclass, field

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str = Field(description="An exact ID from a supplied passage")
    quote: str = Field(description="A short verbatim excerpt including the fact and its context")


class GroundedDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported: bool = Field(description="Whether the retrieved catalogue explicitly answers the exact question")
    answer: str = Field(description="A concise direct answer, or Not found")
    evidence: list[Evidence] = Field(description="Supporting excerpts, empty if unsupported")


class SupportCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fully_supported: bool = Field(description="All claims answer the precise question and follow from the quoted evidence")


@dataclass
class Answer:
    question: str
    answer: str
    supported: bool
    citations: list[dict] = field(default_factory=list)
    retrieved: list[dict] = field(default_factory=list)
    elapsed_seconds: float = 0

    def as_dict(self):
        return asdict(self)

