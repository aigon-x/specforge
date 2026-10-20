"""SpecForge: brief -> OpenAPI 3.1 contract, validator and contract tests."""

from .brief import Brief, FieldSpec, Requirement, Resource, load_brief, parse_brief
from .errors import (
    BriefError,
    FixtureError,
    NebiusConfigError,
    NebiusError,
    SpecForgeError,
)
from .validator import Finding, ValidationReport, validate_spec

__version__ = "1.0.0"
__all__ = [
    "Brief",
    "BriefError",
    "FieldSpec",
    "Finding",
    "FixtureError",
    "NebiusConfigError",
    "NebiusError",
    "Requirement",
    "Resource",
    "SpecForgeError",
    "ValidationReport",
    "__version__",
    "load_brief",
    "parse_brief",
    "validate_spec",
]
