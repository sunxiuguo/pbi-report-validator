"""Turn a ``DiffResult`` into the payload the AI layer may send.

By default the payload is metadata only: names, field references, filter
definitions, measure expressions and counts. Data findings lose their
message, values and row keys, and data summaries their largest difference
and reason (an engine message can quote data). Row-level values are kept
only when data is explicitly allowed (``--allow-data-to-llm``).
"""

from pbi_report_validator.domain.helpers import visual_path_of
from pbi_report_validator.domain.models import (
    AiDataSummary,
    AiFinding,
    AiPayload,
    Category,
    DataSummary,
    DiffResult,
    Finding,
)

SOURCE_LOCATIONS: set[str] = {"old_location", "new_location"}


def build_payload(result: DiffResult, allow_data: bool) -> AiPayload:
    """The findings and data summaries of ``result`` that may leave the machine.

    Args:
        result: The diff result.
        allow_data: Keep row keys and values (``--allow-data-to-llm``).

    Returns:
        The payload, in the result's stable order.
    """
    return AiPayload(
        findings=tuple(_finding(f, allow_data) for f in result.findings),
        data=tuple(_summary(s, allow_data) for s in result.data),
        data_included=allow_data,
    )


def _finding(finding: Finding, allow_data: bool) -> AiFinding:
    # Source locations are file paths in the project; the model needs none.
    fields = finding.model_dump(exclude=SOURCE_LOCATIONS | {"scope"})
    payload = AiFinding.model_validate(fields)
    if allow_data or finding.category is not Category.DATA:
        return payload
    return payload.model_copy(
        update={
            "path": f"{visual_path_of(finding.path)}/data",
            "message": f"Data {finding.change.value} (details withheld)",
            "old": None,
            "new": None,
        }
    )


def _summary(summary: DataSummary, allow_data: bool) -> AiDataSummary:
    payload = AiDataSummary.model_validate(summary.model_dump())
    if allow_data:
        return payload
    withheld = {"max_abs_delta": None, "reason": None, "attribution_reason": None}
    return payload.model_copy(update=withheld)
