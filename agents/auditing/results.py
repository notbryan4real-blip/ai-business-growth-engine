"""Evidence-aware website audit result types.

A failed fetch is not evidence that a website has SEO or conversion defects.
Callers should only publish page findings when a page was fetched successfully.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AuditStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class FetchFailureKind(str, Enum):
    DNS = "dns"
    TIMEOUT = "timeout"
    TLS = "tls"
    HTTP = "http"
    INVALID_URL = "invalid_url"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AuditFinding:
    """A finding supported by evidence from a successfully fetched page."""

    category: str
    severity: str
    title: str
    evidence: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.evidence.strip():
            raise ValueError("findings must include evidence")


@dataclass(frozen=True)
class AuditResult:
    """Audit outcome separating fetch reliability from observed site quality."""

    url: str
    status: AuditStatus
    findings: tuple[AuditFinding, ...] = ()
    http_status: Optional[int] = None
    failure_kind: Optional[FetchFailureKind] = None
    failure_message: Optional[str] = None
    attempts: int = 1
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.status == AuditStatus.FAILED and self.findings:
            raise ValueError("failed audits cannot contain verified page findings")
        if self.status == AuditStatus.SUCCESS and self.failure_kind is not None:
            raise ValueError("successful audits cannot have a fetch failure kind")
        if self.status == AuditStatus.FAILED and self.failure_kind is None:
            raise ValueError("failed audits must identify the failure kind")

    @property
    def is_verified(self) -> bool:
        """Whether the page was retrieved sufficiently to support findings."""
        return self.status in (AuditStatus.SUCCESS, AuditStatus.PARTIAL)

    @property
    def confidence_label(self) -> str:
        if self.status == AuditStatus.SUCCESS:
            return "verified"
        if self.status == AuditStatus.PARTIAL:
            return "partial"
        return "unverified"
