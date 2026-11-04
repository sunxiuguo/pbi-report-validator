# Test fixtures

Synthetic Power BI Projects (PBIP, PBIR report format + TMDL semantic model)
used by the tests and the demo. All names and values are made up; no real
report, tenant, workspace or customer data may be added here.

## `sales_v1/` – the "old" report

Semantic model `Sales.SemanticModel` (inline `#table` data, so no data source):

| Table | Columns | Measures |
|---|---|---|
| `Sales` | ProductKey, DateKey, Region, Amount, Cost | `Total Sales`, `Margin %` (multi-line) |
| `Product` | ProductKey, Product, Category | – |
| `Date` | DateKey, Year, Month | – |

Report `Sales.Report`:

- **Report filter** `report_filter_year`: `Date[Year]` in 2024, 2025
- **Page `overview`** (Overview), page filter `page_filter_category`:
  `Product[Category]` not in Accessories
  - `card_total_sales` – card, `Total Sales`
  - `card_margin` – card, `Margin %`
  - `slicer_year` – slicer on `Date[Year]`, selection 2025
  - `chart_sales_by_month` – clustered column chart, `Total Sales` by `Date[Month]`
- **Page `details`** (Details)
  - `table_product_sales` – table, Category, Product, `Total Sales`, `Margin %`;
    visual filter `visual_filter_category`: `Product[Category]` in Bikes, Clothing
  - `chart_sales_by_region` – clustered bar chart, `Total Sales` by `Sales[Region]`

Page and visual folder names are readable on purpose, so tests and
expected-change lists can refer to them directly.

## `sales_v2/` – the "new" report

A copy of `sales_v1` with seven deliberate changes, listed with old and new
values in [`EXPECTED_CHANGES.md`](EXPECTED_CHANGES.md). Keep that file in sync
whenever either fixture changes.

## `recorded/` – real API responses

`sales_v1` and `sales_v2` were published as two semantic models, and
`tests/integrations/test_recorded_powerbi.py` replays the answers of the real
`executeQueries` endpoint through the real client:

- `sales_v1_v2.json`: every query `--data` runs for the pair
- `api_behaviour.json`: empty results, value types, errors and the row, value
  and size limits. The partial rows of a failed result are cut to two rows

Replies are looked up by their exact DAX, so a change to the DAX builder fails
these tests until the recordings are updated. Record them again with
`tests/record_powerbi_responses.py`, which replaces the dataset ids with
placeholders and refuses any other id. If no published models exist any more,
edit the `query` by hand, but only for a change that can't affect the result.
Only ever record the synthetic sample reports.

## `sales_v3/` – field and parse issue

A copy of `sales_v2` with two deliberate changes, so the `field` and
`parse_issue` categories also have a fixture pair (`sales_v2` → `sales_v3`):
`Sales[Region]` is added to `table_product_sales`, and
`overview/card_total_sales/visual.json` is invalid JSON on purpose. Details in
[`EXPECTED_CHANGES.md`](EXPECTED_CHANGES.md).

## Finding scope fixtures

`finding_scope_v1` and `finding_scope_v2` are synthetic PBIR reports with
pages named `report`, `model`, `old`, `new` and `ai`. Every page and the report
itself has a filter called `f`, with identical conditions changing between
versions. The report filter and the filter on page `report` therefore have
the identical path `report/filters/f`, category, message and old/new values.
Schema 1.10 distinguishes them with `scope`. Each visual also moves, and the
synthetic measure changes, exercising page and model paths together.
