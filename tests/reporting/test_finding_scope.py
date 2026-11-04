import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from pbi_report_validator.cli.main import app
from pbi_report_validator.diff.severity import make_finding
from pbi_report_validator.domain.models import Category, ChangeKind, DiffResult, Finding
from pbi_report_validator.integrations.templates import read_template
from pbi_report_validator.reporting.ai_payload import build_payload
from pbi_report_validator.reporting.html import REPORT_TEMPLATE, to_html, visual_key
from pbi_report_validator.reporting.json_out import to_json
from pbi_report_validator.services.validate import validate
from tests.factories import FIXTURES

OLD = FIXTURES / "finding_scope_v1"
NEW = FIXTURES / "finding_scope_v2"
RESERVED_NAMES = ("report", "model", "old", "new", "ai")


def test_cli_json_disambiguates_same_name_filters_and_reserved_pages(
    tmp_path: Path,
) -> None:
    target = tmp_path / "diff.json"

    result = CliRunner().invoke(
        app, ["diff", str(OLD), str(NEW), "--json", str(target)]
    )

    assert result.exit_code == 0, result.output
    output = json.loads(target.read_text(encoding="utf-8"))
    assert output["schema_version"] == "1.10"
    collision = [f for f in output["findings"] if f["path"] == "report/filters/f"]
    assert len(collision) == 2
    assert {f["scope"] for f in collision} == {"report", "page"}
    assert {f["category"] for f in collision} == {"filter"}
    assert len({(f["old"], f["new"]) for f in collision}) == 1
    for name in RESERVED_NAMES:
        page_findings = [
            f
            for f in output["findings"]
            if f["path"] in (f"{name}/filters/f", f"{name}/v") and f not in collision
        ]
        assert page_findings
        assert all(f["scope"] == "page" for f in page_findings)
    measure = next(f for f in output["findings"] if f["category"] == "measure")
    assert (measure["scope"], measure["path"]) == ("model", "model/Synthetic/Value")


@pytest.mark.parametrize("category", list(Category))
def test_every_category_has_scope_independent_of_path_prefix(
    category: Category,
) -> None:
    # A page may have any reserved prefix: category, never path text, sets scope.
    expected = {"measure": "model", "parse_issue": "parse", "ai": "ai"}.get(
        category.value, "page"
    )
    for prefix in RESERVED_NAMES:
        finding = make_finding(
            category, ChangeKind.MODIFIED, path=f"{prefix}/v", message="synthetic"
        )
        assert json.loads(finding.model_dump_json())["scope"] == expected


def test_report_scope_survives_json_round_trip_and_keeps_html_grouping() -> None:
    result = validate(OLD, NEW)

    restored = DiffResult.model_validate_json(to_json(result))

    assert restored == result
    report_filter = next(f for f in restored.findings if f.report_level)
    assert report_filter.page_path is None
    assert visual_key(report_filter, {"report/filters"}) is None
    page_filter = next(
        f
        for f in restored.findings
        if f.path == "report/filters/f" and not f.report_level
    )
    assert page_filter.page_path == "report/filters/f"
    template = read_template(REPORT_TEMPLATE)
    assert to_html(restored, template, "test") == to_html(result, template, "test")


def test_colliding_findings_have_deterministic_order() -> None:
    result = validate(OLD, NEW)
    reversed_result = DiffResult(
        old_source=result.old_source,
        new_source=result.new_source,
        findings=tuple(reversed(result.findings)),
        pages=result.pages,
    )

    assert to_json(result) == to_json(reversed_result)


def test_scope_keeps_the_existing_ai_payload_contract() -> None:
    result = validate(OLD, NEW)

    payload = build_payload(result, allow_data=False)

    assert len(payload.findings) == len(result.findings)
    assert "scope" not in payload.model_dump_json()
    assert [f.path for f in payload.findings] == [f.path for f in result.findings]


@pytest.mark.parametrize("category", [None, [], {}])
def test_invalid_category_is_still_a_validation_error(category: object) -> None:
    fields = make_finding(
        Category.PAGE, ChangeKind.ADDED, path="report", message="synthetic"
    ).model_dump(exclude={"scope"})
    fields["category"] = category

    with pytest.raises(ValidationError):
        Finding.model_validate(fields)


def test_parse_issues_keep_their_legacy_path_and_have_parse_scope() -> None:
    result = validate(FIXTURES / "sales_v2", FIXTURES / "sales_v3")
    [issue] = [
        f
        for f in json.loads(to_json(result))["findings"]
        if f["category"] == "parse_issue"
    ]

    assert issue["scope"] == "parse"
    assert issue["path"] == (
        "new/Sales.Report/definition/pages/overview/visuals/card_total_sales/visual.json"
    )
