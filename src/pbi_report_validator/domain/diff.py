"""Matching, findings, page views and the diff result (the JSON root)."""

from collections import Counter
from enum import StrEnum
from typing import Final, Literal

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    field_validator,
    model_serializer,
    model_validator,
)

from pbi_report_validator.domain.ai import AiMode
from pbi_report_validator.domain.base import DomainModel, SourceLocation
from pbi_report_validator.domain.data_validation import DataSummary
from pbi_report_validator.domain.report import (
    Page,
    Position,
    Visual,
)
from pbi_report_validator.domain.semantic import MeasureRename

SCHEMA_VERSION: Final = "1.10"


class MatchMethod(StrEnum):
    """How an old object was paired with a new one."""

    ID = "id"
    DISPLAY_NAME = "display_name"
    SIMILARITY = "similarity"


class VisualMatch(DomainModel):
    """An old visual paired with its counterpart in the new version."""

    old: Visual
    new: Visual
    method: MatchMethod
    score: float = Field(ge=0, le=1)


class PageMatch(DomainModel):
    """An old page paired with a new page, with its visuals matched."""

    old: Page
    new: Page
    method: MatchMethod
    visuals: tuple[VisualMatch, ...] = ()
    removed_visuals: tuple[Visual, ...] = ()
    added_visuals: tuple[Visual, ...] = ()


class ReportMatch(DomainModel):
    """Pairing of all pages and visuals between two report versions."""

    pages: tuple[PageMatch, ...] = ()
    removed_pages: tuple[Page, ...] = ()
    added_pages: tuple[Page, ...] = ()


# --- Diff side ---------------------------------------------------------------


class Category(StrEnum):
    """What kind of object a finding is about."""

    PAGE = "page"
    VISUAL = "visual"
    FIELD = "field"
    FILTER = "filter"
    SLICER = "slicer"
    MEASURE = "measure"
    PARSE_ISSUE = "parse_issue"
    DATA = "data"
    AI = "ai"


class ChangeKind(StrEnum):
    """How the object changed between the old and new version."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"
    RETYPED = "retyped"
    RENAMED = "renamed"
    REORDERED = "reordered"
    ERROR = "error"


class Severity(StrEnum):
    """How much a finding matters, from least to most."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AiExplanation(DomainModel):
    """A plain-language explanation of a finding, written by the AI layer."""

    source: Literal["ai"] = "ai"
    text: str


class FindingScope(StrEnum):
    """The namespace of a finding's path, independent of page names."""

    REPORT = "report"
    PAGE = "page"
    MODEL = "model"
    PARSE = "parse"
    AI = "ai"


class Finding(DomainModel):
    """One difference (or parse problem) between the old and new report.

    ``path`` locates the object, e.g. ``details/table_product_sales/filters/
    visual_filter_category`` or ``model/Sales/Total Sales``. ``severity`` is
    required; ``diff.severity.make_finding`` sets the usual level.
    ``explanation`` is set only with ``--ai-explain`` and left out of the JSON
    otherwise. ``old_location`` and ``new_location`` say where the object is
    defined in each version; ``None`` on a side where it does not exist,
    and for findings without a single source (data, AI, parse issues).
    ``scope`` distinguishes report, page, model, parse and AI paths without
    changing the paths themselves, even when a page has a reserved name.
    """

    category: Category
    scope: FindingScope = FindingScope.PAGE
    change: ChangeKind
    severity: Severity
    path: str
    message: str
    old: str | None = None
    new: str | None = None
    old_location: SourceLocation | None = None
    new_location: SourceLocation | None = None
    # The ``page/visual`` a parse issue belongs to. Used to show the issue on
    # its visual in the HTML report; remains internal to the validation run.
    visual_path: str | None = Field(default=None, exclude=True)
    explanation: AiExplanation | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_scope(cls, data: object) -> object:
        """Infer unambiguous scopes from category, never from path prefixes."""
        if not isinstance(data, dict) or "scope" in data:
            return data
        category = data.get("category")
        if not isinstance(category, str):
            return data
        scopes: dict[str, FindingScope] = {
            Category.MEASURE: FindingScope.MODEL,
            Category.PARSE_ISSUE: FindingScope.PARSE,
            Category.AI: FindingScope.AI,
        }
        return {**data, "scope": scopes.get(category, FindingScope.PAGE)}

    @model_serializer(mode="wrap")
    def _without_empty_explanation(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        data: dict[str, object] = handler(self)
        if self.explanation is None:
            data.pop("explanation", None)
        return data

    @property
    def report_level(self) -> bool:
        """Whether this finding belongs to the report rather than a page."""
        return self.scope == FindingScope.REPORT

    @property
    def page_path(self) -> str | None:
        """The ``page`` or ``page/...`` path the finding is inside, if any.

        Measures, parse issues, AI notes and report filters have paths with
        a fixed prefix (``model``, ``old``, ``new``, ``ai``, ``report``) that
        a page can share as its name, so they belong to no page.
        """
        if self.scope != FindingScope.PAGE:
            return None
        return self.path

    @property
    def sort_key(self) -> tuple[str, str, str, str, str, str, str]:
        """Key giving a total, readable order of findings."""
        return (
            self.path,
            self.category.value,
            self.change.value,
            self.message,
            self.old or "",
            self.new or "",
            self.scope.value,
        )


class ItemStatus(StrEnum):
    """Overall status of a page or visual in the comparison."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class VisualView(DomainModel):
    """A visual as shown in reports: both positions and a status.

    ``name`` is the old name for matched and removed visuals and the new
    name for added ones, so it matches the paths used in findings. For
    matched visuals, ``visual_type`` and ``title`` come from the new version.
    """

    name: str
    visual_type: str
    title: str | None = None
    status: ItemStatus
    old_position: Position | None = None
    new_position: Position | None = None


class PageView(DomainModel):
    """A page as shown in reports, with every visual of both versions."""

    name: str
    display_name: str
    status: ItemStatus
    ordinal: int = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    visuals: tuple[VisualView, ...] = ()


class RowComparison(DomainModel):
    """The outcome of comparing the aligned rows of one visual.

    ``rows_differing`` counts rows present in both versions with at least
    one differing value; ``deltas`` are all numeric differences, including
    those within the tolerance.
    """

    findings: tuple[Finding, ...] = ()
    rows_differing: int = Field(default=0, ge=0)
    deltas: tuple[float, ...] = ()


class DataComparison(DomainModel):
    """Summary and findings from comparing one visual's data."""

    summary: DataSummary
    findings: tuple[Finding, ...] = ()


class MeasureDiff(DomainModel):
    """Measure findings plus the renames found, keyed by old field key."""

    findings: tuple[Finding, ...] = ()
    renames: dict[str, MeasureRename] = Field(default_factory=dict)


class AiSuggestion(DomainModel):
    """A rename the AI layer suggests for a removed and an added object.

    Pairs the ``path`` of a removed finding with that of an added finding of
    the same category. A suggestion never changes findings or severities;
    ``source`` labels it as AI output in the JSON.
    """

    source: Literal["ai"] = "ai"
    category: Category
    old_path: str
    new_path: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class SeverityCounts(DomainModel):
    """Number of findings per severity."""

    critical: int = Field(default=0, ge=0)
    warning: int = Field(default=0, ge=0)
    info: int = Field(default=0, ge=0)


class DiffResult(DomainModel):
    """The result of comparing two report versions; the JSON output root.

    Schema history: 1.0 had sources and findings; 1.1 added ``pages``;
    1.2 added the ``data`` category and per-visual ``data`` summaries;
    1.3 added ``severity`` on findings and ``severity_counts``; 1.4 added
    ``data_values_shown`` (row keys and values are masked unless it is true);
    1.5 added the ``ai`` category, ``ai_mode`` and ``ai_model``; 1.6 added
    ``ai_suggestions`` (``--ai-match``); 1.7 added the optional
    ``explanation`` on findings (``--ai-explain``); 1.8 added ``attribution``
    and ``attribution_reason`` on data summaries (``--attribute``); 1.9
    added ``old_location`` and ``new_location`` on findings; 1.10 added
    ``scope`` on findings to disambiguate page paths from fixed prefixes.
    """

    # Keep the Literal in sync with SCHEMA_VERSION (enforced by a test).
    schema_version: Literal["1.10"] = SCHEMA_VERSION
    old_source: str
    new_source: str
    findings: tuple[Finding, ...] = ()
    # Always derived from ``findings``; any value passed in is replaced.
    severity_counts: SeverityCounts = Field(default_factory=SeverityCounts)
    pages: tuple[PageView, ...] = ()
    data: tuple[DataSummary, ...] = ()
    data_values_shown: bool = False
    ai_mode: AiMode = AiMode.OFF
    ai_model: str | None = None
    ai_suggestions: tuple[AiSuggestion, ...] = ()

    @field_validator("findings")
    @classmethod
    def _sort_findings(cls, findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
        return tuple(sorted(findings, key=lambda f: f.sort_key))

    @field_validator("ai_suggestions")
    @classmethod
    def _sort_suggestions(
        cls, suggestions: tuple[AiSuggestion, ...]
    ) -> tuple[AiSuggestion, ...]:
        return tuple(sorted(suggestions, key=lambda s: (s.old_path, s.new_path)))

    @model_validator(mode="before")
    @classmethod
    def _count_severities(cls, data: object) -> object:
        """Replace ``severity_counts`` with the counts of ``findings``."""
        if not isinstance(data, dict):
            return data
        findings = _FINDINGS.validate_python(data.get("findings", ()))
        counts = Counter(f.severity for f in findings)
        severity_counts = SeverityCounts(**{s.value: counts[s] for s in Severity})
        return {**data, "severity_counts": severity_counts}


_FINDINGS: Final = TypeAdapter(tuple[Finding, ...])
