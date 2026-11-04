import pytest

from pbi_report_validator.diff.severity import make_finding
from pbi_report_validator.domain.models import (
    Category,
    ChangeKind,
    DataStatus,
    DataSummary,
    DiffResult,
)
from pbi_report_validator.reporting.ai_payload import build_payload
from pbi_report_validator.services.validate import validate
from tests.factories import FIXTURES
from tests.services.test_data_validation import KEY_VALUES, SETTINGS, FakeRunner

# Row keys and values the fake runner returns. Bikes and Clothing are left
# out: they are also filter values in the report definition (metadata).
ROW_KEYS = [
    value
    for column, values in KEY_VALUES.items()
    if column != "Product[Category]"
    for value in values
]
ROW_VALUES = ["120", "100.0"]


@pytest.fixture(scope="module")
def unmasked() -> DiffResult:
    """A --data --show-data-values run: findings carry keys and values."""
    settings = SETTINGS.model_copy(update={"show_values": True})
    return validate(
        FIXTURES / "sales_v1",
        FIXTURES / "sales_v2",
        settings,
        FakeRunner(fail_on="'Sales'[Region]"),
    )


def test_no_result_values_reach_the_payload_without_allow_data(
    unmasked: DiffResult,
) -> None:
    text = build_payload(unmasked, allow_data=False).model_dump_json()

    assert any(key in unmasked.model_dump_json() for key in ROW_KEYS)
    for secret in [*ROW_KEYS, *ROW_VALUES, "Column not found"]:
        assert secret not in text


def test_allow_data_keeps_values(unmasked: DiffResult) -> None:
    payload = build_payload(unmasked, allow_data=True)

    assert payload.data_included
    assert "2025-02" in payload.model_dump_json()
    assert [f.path for f in payload.findings] == [f.path for f in unmasked.findings]


def test_data_findings_keep_their_visual_and_kind_only(unmasked: DiffResult) -> None:
    payload = build_payload(unmasked, allow_data=False)

    data = [f for f in payload.findings if f.category is Category.DATA]
    assert data
    for finding in data:
        assert finding.path.endswith("/data")
        assert finding.path.count("/") == 2
        assert finding.message == f"Data {finding.change.value} (details withheld)"
        assert (finding.old, finding.new) == (None, None)
    assert not payload.data_included


def test_metadata_findings_are_kept_as_they_are(unmasked: DiffResult) -> None:
    payload = build_payload(unmasked, allow_data=False)

    kept = [f for f in unmasked.findings if f.category is not Category.DATA]
    sent = [f for f in payload.findings if f.category is not Category.DATA]
    assert kept
    assert [f.model_dump() for f in sent] == [
        f.model_dump(exclude={"visual_path", "scope", "old_location", "new_location"})
        for f in kept
    ]


def test_summaries_keep_counts_but_not_delta_or_reason() -> None:
    summary = DataSummary(
        path="p/v",
        status=DataStatus.NOT_VALIDATED,
        rows_old=3,
        rows_only_new=1,
        max_abs_delta=876.5,
        reason="engine said 'secret'",
    )
    result = DiffResult(
        old_source="o",
        new_source="n",
        data=(summary,),
        findings=(
            make_finding(
                Category.DATA, ChangeKind.ERROR, path="p/v/data", message="secret"
            ),
        ),
    )

    sent = build_payload(result, allow_data=False).data[0]

    assert (sent.path, sent.status, sent.rows_old, sent.rows_only_new) == (
        "p/v",
        DataStatus.NOT_VALIDATED,
        3,
        1,
    )
    assert (sent.max_abs_delta, sent.reason) == (None, None)
    assert build_payload(result, allow_data=True).data[0].reason == summary.reason
