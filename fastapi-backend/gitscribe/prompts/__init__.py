"""Versioned prompt templates.

Each `<name>.md` file has YAML-ish frontmatter (`version: N`) followed by a
`## System` and a `## User` section. Placeholders use `{{name}}` so that code
and diffs containing braces pass through untouched. Bump `version` whenever a
prompt changes meaningfully: it is part of the analysis cache key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user: str

    @property
    def id(self) -> str:
        return f"{self.name}@v{self.version}"

    def render(self, **values: object) -> tuple[str, str]:
        def sub(m: re.Match[str]) -> str:
            if m.group(1) not in values:
                raise KeyError(f"prompt {self.name} missing value for {{{{{m.group(1)}}}}}")
            return str(values[m.group(1)])

        return self.system, _PLACEHOLDER.sub(sub, self.user)

    def messages(self, **values: object) -> list[tuple[str, str]]:
        system, user = self.render(**values)
        return [("system", system), ("human", user)]


@lru_cache
def load_prompt(name: str) -> Prompt:
    text = (_DIR / f"{name}.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"prompt {name} is missing frontmatter")
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    sections = re.split(r"(?m)^## (System|User)\s*$", m.group(2))
    parts = {sections[i]: sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    return Prompt(name=name, version=meta["version"], system=parts["System"], user=parts["User"])
