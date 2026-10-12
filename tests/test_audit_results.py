import pytest

from agents.auditing.results import (
    AuditFinding,
    AuditResult,
    AuditStatus,
    FetchFailureKind,
)


def test_dns_failure_is_unverified_and_has_no_page_findings():
    result = AuditResult(
        url="https://example.invalid",
        status=AuditStatus.FAILED,
        failure_kind=FetchFailureKind.DNS,
        failure_message="Name or service not known",
        attempts=2,
    )

    assert result.is_verified is False
    assert result.confidence_label == "unverified"
    assert result.findings == ()
    assert result.attempts == 2


def test_failed_audit_cannot_claim_verified_seo_findings():
    finding = AuditFinding(
        category="seo",
        severity="high",
        title="Missing title",
        evidence="Fetched HTML had no title element",
    )

    with pytest.raises(ValueError, match="cannot contain verified page findings"):
        AuditResult(
            url="https://example.invalid",
            status=AuditStatus.FAILED,
            findings=(finding,),
            failure_kind=FetchFailureKind.DNS,
        )


def test_successful_audit_can_report_evidence_backed_findings():
    finding = AuditFinding(
        category="seo",
        severity="medium",
        title="Missing meta description",
        evidence="Fetched HTML has no meta[name=description] element",
        confidence=0.95,
    )
    result = AuditResult(
        url="https://example.com",
        status=AuditStatus.SUCCESS,
        findings=(finding,),
        http_status=200,
    )

    assert result.is_verified is True
    assert result.confidence_label == "verified"
    assert result.findings[0].confidence == 0.95


def test_finding_requires_evidence():
    with pytest.raises(ValueError, match="must include evidence"):
        AuditFinding(
            category="conversion",
            severity="high",
            title="No phone number",
            evidence=" ",
        )


def test_confidence_must_be_between_zero_and_one():
    with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
        AuditFinding(
            category="seo",
            severity="low",
            title="Short title",
            evidence="Observed title length: 8 characters",
            confidence=1.1,
        )


def test_failed_audit_must_include_failure_kind():
    with pytest.raises(ValueError, match="must identify the failure kind"):
        AuditResult(url="https://example.invalid", status=AuditStatus.FAILED)
