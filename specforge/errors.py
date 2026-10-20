"""Exception types shared by SpecForge modules."""

from __future__ import annotations


class SpecForgeError(RuntimeError):
    """Base class for all SpecForge failures."""


class BriefError(SpecForgeError):
    """Brief is missing required data or is internally inconsistent."""

    def __init__(self, problems: list[str], source: str = "<brief>") -> None:
        self.problems = list(problems)
        self.source = source
        detail = "; ".join(self.problems) if self.problems else "invalid brief"
        super().__init__(f"{source}: {detail}")


class NebiusError(SpecForgeError):
    """Nebius Token Factory call failed or returned unusable content."""

    def __init__(
        self,
        message: str,
        *,
        kind: str = "error",
        status: int | None = None,
        attempts: int = 0,
    ) -> None:
        self.kind = kind
        self.status = status
        self.attempts = attempts
        super().__init__(message)


class NebiusConfigError(NebiusError):
    """Live mode requested without usable configuration (for example no key)."""


class FixtureError(NebiusError):
    """Offline fixture is missing or does not cover the requested task."""
