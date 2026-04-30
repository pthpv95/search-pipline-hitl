"""
Typed request/response models for the local web API bridge.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from state import ReportFormat, RunMode


class CreateRunRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=400)
    mode: RunMode = RunMode.DEV
    report_format: ReportFormat = ReportFormat.DEEP_DIVE
    max_loops: int = Field(default=2, ge=1, le=5)

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        topic = value.strip()
        if not topic:
            raise ValueError("topic must not be empty")
        return topic


class ReviewDecisionRequest(BaseModel):
    action: Literal["approve", "edit", "reject"] = "approve"
    additional_queries: list[str] = Field(default_factory=list)
    edited_draft: str | None = None
    notes: str = ""
    rejection_reason: str = ""

    @field_validator("additional_queries")
    @classmethod
    def normalize_queries(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for query in value:
            normalized = query.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        if len(out) > 10:
            raise ValueError("additional_queries may contain at most 10 entries")
        return out

    @field_validator("edited_draft")
    @classmethod
    def normalize_edited_draft(cls, value: str | None) -> str | None:
        if value is None:
            return value
        draft = value.strip()
        return draft or None

    @field_validator("notes", "rejection_reason")
    @classmethod
    def strip_strings(cls, value: str) -> str:
        return value.strip()

    def to_human_input(self) -> dict:
        if self.action == "edit" and not self.edited_draft:
            raise ValueError("edited_draft is required when action=edit")
        return {
            "action": self.action,
            "additional_queries": self.additional_queries,
            "edited_draft": self.edited_draft,
            "notes": self.notes,
            "rejection_reason": self.rejection_reason,
        }


class ErrorResponse(BaseModel):
    detail: str
    code: str
    retryable: bool = False
