"""Structured outputs for each pipeline layer.

Field descriptions are sent to the model as part of the JSON schema, so they
double as instructions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChangeType = Literal["feature", "bugfix", "refactor", "docs", "test", "chore", "perf", "style", "build", "ci"]

ChangeCategory = Literal["added", "changed", "fixed", "removed", "deprecated", "security"]


# --- layer 1: per-file diff analysis ---------------------------------------


class FileChange(BaseModel):
    summary: str = Field(description="One or two sentences on what changed in this file and why it matters.")
    change_type: ChangeType = Field(description="The single best classification of this change.")
    breaking: bool = Field(
        description="True only if existing callers, users, configs or data would break without changes on their side."
    )
    public_api_changes: list[str] = Field(
        default_factory=list,
        description="Public functions, classes, endpoints, CLI flags or config keys added/removed/changed. Empty if none.",
    )


# --- layer 2: per-batch synthesis ------------------------------------------


class ChangeNote(BaseModel):
    category: ChangeCategory
    description: str = Field(
        description="One concise, user-facing changelog sentence, e.g. 'Support for exporting reports as CSV.'"
    )


class BatchSummary(BaseModel):
    title: str = Field(description="Short title for this group of changes (max ~10 words).")
    narrative: str = Field(description="2-4 sentences explaining what this group of changes accomplishes as a whole.")
    notes: list[ChangeNote] = Field(
        description="Deduplicated, user-facing changelog notes. Merge related file changes into a single note."
    )
    breaking_changes: list[str] = Field(
        default_factory=list, description="Each breaking change and what users must do about it. Empty if none."
    )


# --- layer 3: changelog -----------------------------------------------------


class ChangelogEntry(BaseModel):
    # Required (no defaults) so the JSON schema forces the model to fill every list.
    added: list[str] = Field(description="New features, endpoints, commands, options or docs.")
    changed: list[str] = Field(description="Changes to existing behavior, defaults or dependencies.")
    fixed: list[str] = Field(description="Bug fixes.")
    removed: list[str] = Field(description="Removed features.")
    deprecated: list[str] = Field(description="Features marked for future removal.")
    security: list[str] = Field(description="Security fixes.")
    breaking: list[str] = Field(description="Changes requiring user action, and what to do.")

    @classmethod
    def empty(cls) -> "ChangelogEntry":
        return cls(**{name: [] for name in cls.model_fields})

    def is_empty(self) -> bool:
        return not any(getattr(self, name) for name in type(self).model_fields)


class ModuleDoc(BaseModel):
    """Layer 3 output for module docs (pipeline node not implemented yet)."""

    module: str
    purpose: str
    public_api: list[str]
    dependencies: list[str]
    recent_changes: list[str]
