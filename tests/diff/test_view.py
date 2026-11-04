import shutil
from pathlib import Path

from pbi_report_validator.diff.structural import diff_pages_and_visuals
from pbi_report_validator.diff.view import build_page_views
from pbi_report_validator.domain.models import (
    Category,
    ChangeKind,
    Finding,
    FindingScope,
    ItemStatus,
    Page,
    Severity,
    Visual,
)
from pbi_report_validator.matching.matcher import match_reports
from pbi_report_validator.services.validate import validate
from tests import factories
from tests.factories import FIXTURES


def visual(name: str, x: float = 0) -> Visual:
    return factories.visual(name, x=x)


def page(name: str, ordinal: int, *visuals: Visual) -> Page:
    return factories.page(name, *visuals, ordinal=ordinal)


def statuses(
    old: list[Page], new: list[Page]
) -> list[tuple[str, str, list[tuple[str, str]]]]:
    match = match_reports(old, new, threshold=1.0)
    views = build_page_views(match, diff_pages_and_visuals(match))
    return [
        (p.name, p.status.value, [(v.name, v.status.value) for v in p.visuals])
        for p in views
    ]


def test_fixture_pages_and_visuals_have_expected_status() -> None:
    result = validate(FIXTURES / "sales_v1", FIXTURES / "sales_v2")

    summary = [
        (p.name, p.status, {v.name: v.status for v in p.visuals}) for p in result.pages
    ]
    assert summary == [
        (
            "overview",
            ItemStatus.MODIFIED,
            {
                "card_margin": ItemStatus.UNCHANGED,
                "card_total_sales": ItemStatus.UNCHANGED,
                "chart_sales_by_month": ItemStatus.MODIFIED,
                "slicer_year": ItemStatus.MODIFIED,
            },
        ),
        (
            "details",
            ItemStatus.MODIFIED,
            {
                "chart_sales_by_region": ItemStatus.MODIFIED,
                "table_product_sales": ItemStatus.MODIFIED,
            },
        ),
        ("trends", ItemStatus.ADDED, {"chart_margin_by_month": ItemStatus.ADDED}),
    ]


def test_moved_visual_keeps_both_positions() -> None:
    result = validate(FIXTURES / "sales_v1", FIXTURES / "sales_v2")

    details = next(p for p in result.pages if p.name == "details")
    moved = next(v for v in details.visuals if v.name == "chart_sales_by_region")
    assert moved.old_position is not None
    assert moved.new_position is not None
    assert (moved.old_position.y, moved.new_position.y) == (40, 360)


def test_identical_reports_are_unchanged() -> None:
    result = validate(FIXTURES / "sales_v1", FIXTURES / "sales_v1")

    assert {p.status for p in result.pages} == {ItemStatus.UNCHANGED}
    assert {v.status for p in result.pages for v in p.visuals} == {ItemStatus.UNCHANGED}


def test_added_removed_visuals_and_removed_page() -> None:
    old = [
        page("a", 0, visual("keep"), visual("gone", x=900)),
        page("b", 1, visual("x")),
    ]
    new = [page("a", 0, visual("keep"), visual("fresh", x=500))]

    assert statuses(old, new) == [
        (
            "a",
            "modified",
            [("fresh", "added"), ("gone", "removed"), ("keep", "unchanged")],
        ),
        ("b", "removed", [("x", "removed")]),
    ]


def test_removed_and_added_visuals_carry_one_position() -> None:
    old = [page("a", 0, visual("gone", x=900))]
    new = [page("a", 0, visual("fresh", x=0))]
    match = match_reports(old, new, threshold=1.0)

    views = build_page_views(match, diff_pages_and_visuals(match))

    by_name = {v.name: v for v in views[0].visuals}
    assert by_name["gone"].new_position is None and by_name["gone"].old_position
    assert by_name["fresh"].old_position is None and by_name["fresh"].new_position


def test_unparseable_visual_is_modified_not_removed(tmp_path: Path) -> None:
    new = tmp_path / "new"
    shutil.copytree(FIXTURES / "sales_v1", new)
    broken = (
        new / "Sales.Report/definition/pages/overview/visuals/card_margin/visual.json"
    )
    broken.write_text("{")

    result = validate(FIXTURES / "sales_v1", new)

    overview = next(p for p in result.pages if p.name == "overview")
    card = next(v for v in overview.visuals if v.name == "card_margin")
    assert card.status == ItemStatus.MODIFIED


def test_page_level_change_marks_only_the_page() -> None:
    old = [page("a", 0, visual("v"))]
    new = [
        Page(
            name="a",
            display_name="Renamed",
            ordinal=0,
            width=1000,
            height=1000,
            visuals=(visual("v"),),
        )
    ]

    assert statuses(old, new) == [("a", "modified", [("v", "unchanged")])]


def test_unparseable_page_is_modified_not_removed(tmp_path: Path) -> None:
    new = tmp_path / "new"
    shutil.copytree(FIXTURES / "sales_v1", new)
    (new / "Sales.Report/definition/pages/details/page.json").write_text("{")

    result = validate(FIXTURES / "sales_v1", new)

    assert [(f.category, f.path) for f in result.findings] == [
        ("parse_issue", "new/Sales.Report/definition/pages/details/page.json")
    ]
    details = next(p for p in result.pages if p.name == "details")
    assert details.status == ItemStatus.MODIFIED
    assert {v.status for v in details.visuals} == {ItemStatus.MODIFIED}


def finding(category: Category, path: str, report_level: bool = False) -> Finding:
    item = Finding(
        category=category,
        change=ChangeKind.MODIFIED,
        severity=Severity.WARNING,
        path=path,
        message="m",
    )
    return (
        item.model_copy(update={"scope": FindingScope.REPORT}) if report_level else item
    )


def test_pages_named_like_fixed_prefixes_ignore_findings_outside_pages() -> None:
    pages = [
        page(name, i, visual("v"))
        for i, name in enumerate(("model", "report", "old", "ai"))
    ]
    match = match_reports(pages, pages, threshold=1.0)
    findings = [
        finding(Category.MEASURE, "model/v/Total Sales"),
        finding(Category.FILTER, "report/filters/f", report_level=True),
        finding(Category.PARSE_ISSUE, "old/v/visual.json"),
        finding(Category.AI, "ai/explanations"),
    ]

    views = build_page_views(match, findings)

    assert {(p.name, p.status) for p in views} == {
        (name, ItemStatus.UNCHANGED) for name in ("model", "report", "old", "ai")
    }
    assert all(v.status == ItemStatus.UNCHANGED for p in views for v in p.visuals)


def test_filter_on_a_page_named_report_still_marks_the_page() -> None:
    pages = [page("report", 0, visual("v"))]
    match = match_reports(pages, pages, threshold=1.0)

    views = build_page_views(match, [finding(Category.FILTER, "report/filters/f")])

    assert views[0].status == ItemStatus.MODIFIED
