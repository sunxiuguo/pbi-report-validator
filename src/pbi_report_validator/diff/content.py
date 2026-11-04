"""Diff what matched visuals show and how the report is filtered.

Covers fields per visual, filters at report, page and visual level and
slicer selections. Field keys and conditions on the old side are first
rewritten through the measure rename map, so a renamed measure is not
reported again for every visual or filter that uses it. The new side is
never rewritten: a new visual that still uses a measure's old name is a
broken reference and is reported.
"""

from collections import Counter
from collections.abc import Mapping

from pbi_report_validator.diff.severity import make_finding
from pbi_report_validator.domain.conditions import rename_fields, render
from pbi_report_validator.domain.helpers import aggregated, visual_path
from pbi_report_validator.domain.models import (
    Category,
    ChangeKind,
    Filter,
    Finding,
    FindingScope,
    MeasureRename,
    Projection,
    Report,
    ReportMatch,
    SlicerState,
    SourceLocation,
    VisualMatch,
)
from pbi_report_validator.domain.semantic import renamed_key

REPORT_PATH = "report"


def diff_content(
    old: Report, new: Report, match: ReportMatch, renames: Mapping[str, MeasureRename]
) -> list[Finding]:
    """Compare filters, fields and slicer selections of two report versions.

    Report filters are always compared; page and visual content only for
    pages and visuals the matcher paired.

    Args:
        old: The old report (for report-level filters).
        new: The new report.
        match: Page and visual pairing from the matcher.
        renames: Renamed or moved measures, keyed by old field key.
    """
    findings = [
        f.model_copy(update={"scope": FindingScope.REPORT})
        for f in _diff_filters(REPORT_PATH, old.filters, new.filters, renames)
    ]
    for page_match in match.pages:
        page = page_match.old.name
        findings += _diff_filters(
            page, page_match.old.filters, page_match.new.filters, renames
        )
        for visual_match in page_match.visuals:
            findings += _diff_visual(
                visual_path(page, visual_match.old.name), visual_match, renames
            )
    return findings


def _diff_visual(
    path: str, match: VisualMatch, renames: Mapping[str, MeasureRename]
) -> list[Finding]:
    findings = _diff_fields(path, match.old.projections, match.new.projections, renames)
    findings += _diff_filters(path, match.old.filters, match.new.filters, renames)
    slicer = _diff_slicer(path, match.old.slicer, match.new.slicer, renames)
    return findings + ([slicer] if slicer else [])


def _diff_slicer(
    path: str,
    old: SlicerState | None,
    new: SlicerState | None,
    renames: Mapping[str, MeasureRename],
) -> Finding | None:
    """Compare slicer selections of a matched visual.

    A slicer appearing or disappearing (the visual changed to or from a
    slicer) is only reported if it carried a selection.
    """
    old_condition = _definition(old, renames) if old else None
    new_condition = _definition(new, {}) if new else None
    if old_condition == new_condition:
        return None
    if old and new:
        change, message = ChangeKind.MODIFIED, "Slicer selection changed"
    elif new:
        change, message = ChangeKind.ADDED, "Slicer selection added"
    else:
        change, message = ChangeKind.REMOVED, "Slicer selection removed"
    return make_finding(
        Category.SLICER,
        change,
        path=path,
        message=message,
        old=old_condition,
        new=new_condition,
        old_location=old.location if old else None,
        new_location=new.location if new else None,
    )


def _diff_fields(
    path: str,
    old: tuple[Projection, ...],
    new: tuple[Projection, ...],
    renames: Mapping[str, MeasureRename],
) -> list[Finding]:
    old_roles = _roles_by_field(old, renames)
    new_roles = _roles_by_field(new, {})
    old_at, new_at = _first_locations(old, renames), _first_locations(new, {})
    findings = []
    for key in sorted(old_roles.keys() | new_roles.keys()):
        before, after = old_roles.get(key), new_roles.get(key)
        if before == after:
            continue
        if after is None:
            change, message = ChangeKind.REMOVED, f"Field {key} removed"
        elif before is None:
            change, message = ChangeKind.ADDED, f"Field {key} added"
        else:
            change, message = ChangeKind.MODIFIED, f"Field {key} moved to another role"
        findings.append(
            make_finding(
                Category.FIELD,
                change,
                path=f"{path}/fields/{key}",
                message=message,
                old=before,
                new=after,
                old_location=old_at.get(key),
                new_location=new_at.get(key),
            )
        )
    return findings


def _roles_by_field(
    projections: tuple[Projection, ...], renames: Mapping[str, MeasureRename]
) -> dict[str, str]:
    """Map each field (with aggregation) to its comma-separated roles."""
    roles: dict[str, set[str]] = {}
    for projection in projections:
        roles.setdefault(_projection_key(projection, renames), set()).add(
            projection.role
        )
    return {key: ", ".join(sorted(r)) for key, r in roles.items()}


def _first_locations(
    projections: tuple[Projection, ...], renames: Mapping[str, MeasureRename]
) -> dict[str, SourceLocation | None]:
    """Where each field (with aggregation) is first placed in the visual."""
    locations: dict[str, SourceLocation | None] = {}
    for projection in projections:
        locations.setdefault(_projection_key(projection, renames), projection.location)
    return locations


def _projection_key(
    projection: Projection, renames: Mapping[str, MeasureRename]
) -> str:
    """The field's key after renames, with its aggregation if it has one."""
    field = projection.field
    key = renamed_key(field.key, renames)
    return f"{key} ({field.aggregation})" if field.aggregation else key


def _diff_filters(
    owner: str,
    old: tuple[Filter, ...],
    new: tuple[Filter, ...],
    renames: Mapping[str, MeasureRename],
) -> list[Finding]:
    old_by_name, new_by_name = _by_label(old), _by_label(new)
    findings = []
    for name in sorted(old_by_name.keys() | new_by_name.keys()):
        path = f"{owner}/filters/{name}"
        before, after = old_by_name.get(name), new_by_name.get(name)
        finding = _filter_finding(path, name, before, after, renames)
        if finding is not None:
            findings.append(finding)
    return findings


def _by_label(filters: tuple[Filter, ...]) -> dict[str, Filter]:
    """Filters by name; repeats get ``name#2``, ``name#3``, unnamed ``#1``, ``#2``.

    Every filter keeps its own entry, so a repeated or missing name does not
    hide the others from the diff.
    """
    labelled: dict[str, Filter] = {}
    seen: Counter[str] = Counter()
    for item in filters:
        seen[item.name] += 1
        count = seen[item.name]
        label = item.name if count == 1 and item.name else f"{item.name}#{count}"
        labelled[label] = item
    return labelled


def _filter_finding(
    path: str,
    name: str,
    old: Filter | None,
    new: Filter | None,
    renames: Mapping[str, MeasureRename],
) -> Finding | None:
    before = _definition(old, renames) if old else None
    after = _definition(new, {}) if new else None
    if old is None or new is None:
        change = ChangeKind.ADDED if old is None else ChangeKind.REMOVED
        message = f"Filter {name} {change.value}"
    elif before != after:
        change, message = ChangeKind.MODIFIED, f"Filter {name} changed"
    elif (key := _field_key(old, renames)) != _field_key(new, {}):
        change = ChangeKind.MODIFIED
        message = f"Filter {name} uses another field"
        before, after = key, _field_key(new, {})
    elif old.filter_type != new.filter_type:
        change, message = ChangeKind.RETYPED, f"Filter {name} changed type"
        before, after = old.filter_type, new.filter_type
    else:
        return None
    return make_finding(
        Category.FILTER,
        change,
        path=path,
        message=message,
        old=before,
        new=after,
        old_location=old.location if old else None,
        new_location=new.location if new else None,
    )


def _definition(
    item: Filter | SlicerState, renames: Mapping[str, MeasureRename]
) -> str | None:
    """What a filter or slicer selects: its condition or unread definition.

    Renames are applied to the parsed condition, so a key is only replaced
    where it is a field reference (not inside a text literal or a longer
    table name).
    """
    if item.condition is None:
        return item.unread
    if item.expression is None or not renames:
        return item.condition
    return render(rename_fields(item.expression, renames))


def _field_key(item: Filter, renames: Mapping[str, MeasureRename]) -> str | None:
    if item.field is None:
        return None
    key = renamed_key(item.field.key, renames)
    return aggregated(key, item.field.aggregation)
