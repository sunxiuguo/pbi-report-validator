# pbi-report-validator

[![CI](https://github.com/m-c-v-k/pbi-report-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/m-c-v-k/pbi-report-validator/actions/workflows/ci.yml)
[![Demo](https://img.shields.io/badge/demo-live%20report-2457c5)](https://m-c-v-k.github.io/pbi-report-validator/)
[![Coverage](https://img.shields.io/endpoint?url=https://m-c-v-k.github.io/pbi-report-validator/coverage-badge.json)](https://m-c-v-k.github.io/pbi-report-validator/coverage/)

> Compare two versions of a Power BI report and find out what changed — visuals,
> filters, slicers and the numbers themselves.

**Status:** v0.5.0 – structural diff and data validation (`--data`, values masked by default, `--attribute` tells report changes from model changes), JSON, Markdown and HTML reports (JSON and HTML say in which file and where each change is), a GitHub Action with PR comments and `--fail-on`, and an optional AI layer (`--ai api`). See the [roadmap](docs/PROJECT.md#milestones-6-weeks-part-time).

**Live:** [demo report](https://m-c-v-k.github.io/pbi-report-validator/report.html) for the sample reports in this repository · [latest release](https://github.com/m-c-v-k/pbi-report-validator/releases/latest)

## Why

Validating a migrated or refactored Power BI report usually means opening the
old and new versions side by side and clicking through every page and slicer.
`pbi-report-validator` automates that:

- **Structure** – visuals added, removed, moved or changed; fields and measures used
- **Filter context** – report, page and visual filters, plus slicer selections
- **Data** – each visual re-run as a DAX query against both models and compared
- **Report** – JSON for CI, Markdown for pull requests, and an HTML report with
  page wireframes coloured by status
- **Explanations (optional)** – AI-written summaries of why numbers differ

## Requirements

What you need depends on what you run. The structural diff needs no account,
credentials or network access once installed.

| To run | You need |
|---|---|
| The diff (`pbi-validate diff`) | [uv](https://docs.astral.sh/uv/), which installs Python 3.12 for you, or Docker |
| Input reports | Power BI Desktop to save both versions as Power BI Projects (`.pbip`) in the PBIR format ([Quick start](#quick-start)) |
| Data validation (`--data`) | A Microsoft Entra service principal with access to both published semantic models through the Power BI REST API ([setup](#data-validation-optional---data)) |
| AI options (`--ai api`) | An Anthropic API key, and the `ai` extra or the `-ai` Docker image ([setup](#ai-options-optional---ai)) |
| The GitHub Action | A Linux runner with Docker, such as `ubuntu-latest` ([GitHub Action](#github-action)) |

## Install

Install the latest release as a command-line tool:

```bash
uv tool install git+https://github.com/m-c-v-k/pbi-report-validator@v0.5.0
```

Or run it once without installing:

```bash
uvx --from git+https://github.com/m-c-v-k/pbi-report-validator@v0.5.0 pbi-validate --help
```

Each [GitHub release](https://github.com/m-c-v-k/pbi-report-validator/releases)
also has the wheel attached, which `pip install` or `uv tool install` accept
directly.

### Docker

Each release is also published as an image on GitHub Container Registry.
Mount the folder that holds both reports at `/work`:

```bash
docker run --rm -v "$PWD:/work" ghcr.io/m-c-v-k/pbi-report-validator diff old new
```

To write `--json`, `--markdown` or `--html` files into the mounted folder on Linux,
add `--user "$(id -u):$(id -g)"` so the files are owned by you.

The image does not include the optional AI extra. From v0.3.0, releases also
publish a variant with it, tagged with the suffix `-ai` (`<version>-ai` and
`latest-ai`); see [AI options](#ai-options-optional---ai).

## Configuration

The diff needs no configuration. Data validation and the AI options read
their settings from environment variables only; there are no config files.
[`.env.example`](.env.example) lists every variable:

| Variable | Used by |
|---|---|
| `PBI_TENANT_ID`, `PBI_CLIENT_ID`, `PBI_CLIENT_SECRET` | `--data`: the service principal |
| `ANTHROPIC_API_KEY` | `--ai api` |
| `PBI_VALIDATE_AI` | Default for `--ai` (`off` or `api`); `disabled` blocks AI |
| `PBI_VALIDATE_AI_MODEL` | Overrides the Claude model |

Copy it to `.env` (which git ignores) and fill in what you need:

```bash
cp .env.example .env
```

The tool does not read `.env` by itself, so load it into your shell before
running `pbi-validate`. In bash or zsh:

```bash
set -a; . ./.env; set +a
```

In PowerShell:

```powershell
Get-Content .env | Where-Object { $_ -match '^\s*[^#\s][^=]*=' } | ForEach-Object { $name, $value = $_ -split '=', 2; Set-Item "env:$($name.Trim())" $value }
```

In CI, set the same variables from secrets, as shown under
[GitHub Action](#github-action). Never commit `.env`.

## Quick start

1. Save both report versions as Power BI Projects (*File → Save as → Power BI
   project (.pbip)*) in the **PBIR** report format. If your Power BI Desktop
   version does not use PBIR by default, enable it under *Options → Preview
   features* first.
2. Compare them:

```bash
pbi-validate diff ./old ./new --html report.html
```

Each argument is a PBIP project folder (containing one `<Name>.Report` folder)
or the `.Report` folder itself. The terminal always shows a summary; add any of:

| Option | Output |
|---|---|
| `--html PATH` | Self-contained HTML report: summary, page wireframes coloured by status, a drill-down per visual that shows the file (and JSON Pointer) where each finding is defined. Works offline. [Example](https://m-c-v-k.github.io/pbi-report-validator/report.html) |
| `--markdown PATH` | Summary for a pull request comment, kept under GitHub's size limit |
| `--json PATH` | Every finding with old and new values, an explicit `scope` and where the object is defined in each version (`old_location` / `new_location`: the file in the project and a JSON Pointer, or the TMDL object for measures), plus every page and visual with its status, and counts per severity (`schema_version` 1.10) |

JSON schema **1.10** adds `scope` to every finding. Use `(scope, path)` to
identify the object's namespace; page names may be `report`, `model`, `old`,
`new` or `ai`, so the path prefix alone is not enough.

| `scope` | Findings | Example `path` |
|---|---|---|
| `report` | Report-level filters | `report/filters/f` |
| `page` | Pages, visuals, fields, page/visual filters, slicers and data | `report/filters/f` (a filter on a page named `report`) |
| `model` | Measures | `model/Sales/Total Sales` |
| `parse` | Parse issues and missing-model warnings | `new/model` |
| `ai` | AI failure notes | `ai/explanations` |

Existing paths, categories, severities and values are unchanged. CI readers
that ignore unknown fields can keep reading the output; readers that validate
the schema version or forbid unknown fields must accept version 1.10 and the
new field. Update path-prefix routing to use `scope` before handling page
names that collide with fixed prefixes. Older JSON cannot reliably distinguish
same-name report and page filters; regenerate it with schema 1.10 when that
distinction is needed.

Running it on the sample reports in this repository gives:

```text
Compared tests/fixtures/sales_v1 -> tests/fixtures/sales_v2
7 findings (3 critical, 2 warning, 2 info):
  page         1
  visual       2
  filter       1
  slicer       1
  measure      2

  info     [moved] details/chart_sales_by_region: clusteredBarChart 'Sales by region' (chart_sales_by_region) moved
  critical [removed] details/table_product_sales/filters/visual_filter_category: Filter visual_filter_category removed
  warning  [renamed] model/Sales/Margin %: Measure Sales[Margin %] renamed to Sales[Gross Margin %]
  critical [modified] model/Sales/Total Sales: Expression of measure Sales[Total Sales] changed
  warning  [retyped] overview/chart_sales_by_month: clusteredColumnChart 'Sales by month' (chart_sales_by_month) changed type to lineChart
  critical [modified] overview/slicer_year: Slicer selection changed
  info     [added] trends: Page 'Trends' added with 1 visual
```

No credentials or environment variables are needed.

To fail a CI job on important changes, add `--fail-on` with a severity
(`info`, `warning` or `critical`; the default `none` never fails). Output
files are still written, and the run ends with, for example:

```text
Failed: 3 findings at critical or above (--fail-on critical)
```

With `--data`, a visual whose data could not be compared (for example a
failed query) is a `warning`, so `--fail-on critical` does not catch it. Add
`--fail-on-data-error` to also fail when the data of any visual was not
fully validated.

| Exit code | Meaning |
|---|---|
| `0` | The comparison ran (with or without differences), and neither `--fail-on` nor `--fail-on-data-error` was triggered |
| `1` | A project could not be loaded, an output file could not be written, or data validation could not run |
| `2` | Invalid options, including `--ai api` when AI is disabled or not set up |
| `3` | At least one finding at or above the `--fail-on` severity, or (with `--fail-on-data-error`) data that was not fully validated |

### What it compares

- Pages: added, removed, renamed, reordered
- Visuals: added, removed, moved/resized, type changed, title changed
- Fields per visual, including role and aggregation
- Filters at report, page and visual level; slicer selections
- Measures in the semantic model (TMDL, or `model.bim` for models saved
  without the TMDL format): added, removed, expression changed, renamed
  (detected by identical expression) and moved to another table (same name
  and expression). When a version has no model to read (a report connected
  to a published model with no model folder next to it, or a missing model
  folder), a warning says measures were not compared and why.
- Files that cannot be parsed, `.tmdl` files included, are reported as
  findings instead of stopping the run

Every finding has a severity:

| Severity | Findings |
|---|---|
| `critical` | Data differences, removed pages and visuals, added/removed/changed filters and slicer selections, changed measure expressions |
| `warning` | Changed visual type, changed fields, renamed or removed measures, parse issues, visuals whose data could not be validated |
| `info` | Added pages, visuals and measures, moved or reordered pages and visuals, renamed pages, changed titles, filters that only changed type |

### Data validation (optional, `--data`)

The structural diff tells you what changed in the report definition. With
`--data` the tool also checks whether the **numbers** are the same: each
visual is turned into a DAX query (with its report, page and visual filters
and the slicer selections on its page), run against the old and the new
**published** semantic model, and the results are compared row by row.

```bash
pbi-validate diff ./old ./new --data \
  --old-dataset <dataset id> --new-dataset <dataset id> --html report.html
```

- Numbers are equal when they differ by at most `--abs-tol` (default 0) or
  `--rel-tol` times the larger value (default 1e-9); text must match exactly.
- Findings show rows that exist in only one version and values that differ.
  The HTML drill-down shows a per-visual summary; the JSON has a `data`
  summary per visual (schema 1.2).
- **Row-level data is masked by default.** Rows are named by position
  (`row 3`) and values show as `(masked)`, so reports, job summaries and
  pull request comments never contain the keys or numbers of your data.
  Counts and the largest difference per visual are still shown.
- `--show-data-values` shows the row keys and old/new values instead. Every
  output then carries a warning (stderr, a banner in the Markdown and HTML,
  `data_values_shown: true` in the JSON, schema 1.4). Only use it where
  everyone who can read the output may see the data.
- Visuals whose query cannot be built faithfully (custom visuals, hierarchy
  levels, filters on measures, ...) or fails are reported as
  "not validated" with the reason. Slicers are skipped: they only filter. So are
  visuals without fields in either version (text boxes, images, shapes,
  buttons, groups), since they show no data.
- Also "not validated": visuals that could not be fully parsed, visuals on a
  page where another visual could not be parsed (it may have been a slicer),
  visuals or pages that could not be parsed in one version, and visuals that
  are a slicer in only one version. All of these count for
  `--fail-on-data-error`.
- `--attribute` tells you, for each visual whose numbers differ, whether the
  **report** or the **semantic model** caused it. The new report's query is
  also run against the old model (one extra query per differing visual,
  nothing is written or rebound). If that already gives the new numbers, the
  report changed; if it still gives the old numbers, the model changed; if
  it gives neither, both did. When this cannot be told (for example the new
  query uses a measure the old model does not have), the cause is `unknown`
  with the reason. The cause is listed under the data summary in the
  terminal and Markdown, in the HTML drill-down, and as `attribution` /
  `attribution_reason` on each `data` summary in the JSON (schema 1.8).

**Setup (one time).** Data validation signs in as a Microsoft Entra
service principal and uses the Power BI REST API `executeQueries` endpoint,
so it runs in CI without Windows-only drivers:

1. Register an app in Microsoft Entra ID and create a client secret.
2. In the Power BI admin portal, enable *Service principals can call Fabric
   public APIs* (Developer settings) and *Semantic Model Execute Queries REST
   API* (Integration settings). Older portals call them *Allow service
   principals to use Power BI APIs* and *Dataset Execute Queries REST API*.
   If you limit a setting to a security group, the service principal itself
   must be a member of that group. Changes can take about 15 minutes to apply.
3. Add the app to the workspace(s) that hold both semantic models, with at
   least Contributor rights (it needs read and build permission). This can't
   be *My workspace*, because an app can't be added to it.
4. Provide the credentials as environment variables (`.env.example` lists
   them; never commit them):

   ```bash
   export PBI_TENANT_ID=...  PBI_CLIENT_ID=...  PBI_CLIENT_SECRET=...
   ```

The dataset id is the GUID in the semantic model's URL in the Power BI
service: `.../datasets/<id>/...`, `.../modeling/<id>/...` or
`.../dataset/<id>/overview`.

If sign-in fails or a dataset id is wrong, the run stops with exit code 1
and no output files are written; fix the setup and run it again. A `401
Unauthorized` after a successful sign-in usually means the tenant setting
from step 2 blocks the app: the setting is off, it hasn't applied yet, or
the app is not in the allowed group. The API then sends
`ServicePrincipalIsNotAllowedByTenantAdminSwitch` in the
`x-powerbi-error-info` response header; the error message shows that value
and what to check.

Limitations: models with row-level security can't be queried by a service
principal; slicer interactions edited in Power BI and slicers synced from
other pages are not taken into account; the API allows about 120 queries a
minute (40 on Pro/PPU), and each visual needs two; a query returns at most
100,000 rows, 1,000,000 values or 15 MB. Over a limit the API still answers
with HTTP 200 and partial rows, with the error inside the response, so a
visual whose result reaches a limit (or comes within 10% of 15 MB), or whose
response carries an error, is reported as "not validated".

### AI options (optional, `--ai`)

The AI layer is **off by default**, and nothing in the tool needs it.
`--ai api` checks the setup and records in every output that AI was on;
the features below each need their own flag, and they can be combined.

| Flag (with `--ai api`) | What it adds |
|---|---|
| `--ai-match` | Rename suggestions: for removed and added pages, visuals and measures that the deterministic matcher could not pair (for example a measure that was renamed *and* edited), the model suggests which one probably became which. Each suggestion shows next to both findings as `AI-generated: probably renamed to …` with a confidence and a reason, and is listed in `ai_suggestions` in the JSON with `"source": "ai"`. Findings and severities never change. One request per run, and none when nothing can be paired. |
| `--ai-explain` | Plain-language explanations: each finding at or above `--ai-explain-from` (`info`, `warning` or `critical`; default `warning`) gets one or two sentences a tester understands, shown under the finding as `AI-generated: …` and stored as `explanation` with `"source": "ai"` on the finding in the JSON. One request per run for at most 50 findings, the most severe first. Findings and severities never change. |

| `--ai` | What happens |
|---|---|
| `off` (default) | No AI. Nothing is imported, read or sent. |
| `api` | Uses the Anthropic API with **your own key**. The key owner pays for use; this project never calls the API itself. |

Setup for `api`:

```bash
uv tool install "pbi-report-validator[ai] @ git+https://github.com/m-c-v-k/pbi-report-validator@v0.5.0"
export ANTHROPIC_API_KEY=...
pbi-validate diff ./old ./new --ai api
```

- The model defaults to the latest Claude model (`claude-opus-5-5`). Set
  `PBI_VALIDATE_AI_MODEL` to use another one.
- **What is sent:** metadata only, such as page and visual names, field
  references, filter definitions, measure expressions and counts from the
  data comparison. Row keys and values from `--data` are never sent unless
  you also pass `--allow-data-to-llm` (stderr then shows a warning): data
  findings go out as "visual X: data modified", without row keys, values or
  engine messages, even when `--show-data-values` is on.
- **Labelling:** every report made with `--ai api` says so and names the
  model (`ai_mode` and `ai_model` in the JSON). AI-written text is marked
  `AI-generated`; the findings themselves always come from the
  deterministic comparison.
- **Errors:** `--ai api` without the extra or without `ANTHROPIC_API_KEY`
  stops before the run with exit code 2 and a setup hint. If an AI call
  fails during a run (network, rate limit, a refused or empty answer), that
  becomes an `info` finding in the `ai` category, and the rest of the
  result is produced as usual. Findings in the `ai` category never count
  for `--fail-on`, so an outage cannot fail a CI run.
- **Default and kill switch:** `PBI_VALIDATE_AI=off|api` sets the default
  when `--ai` is not given. `PBI_VALIDATE_AI=disabled` blocks AI whatever
  the flags say: `--ai api` then fails with exit code 2. Set it in a CI
  template or a machine's environment to enforce "no AI".
- The default Docker image does not include the AI extra; use the `-ai`
  image variant (see [Docker](#docker)) or the action input `ai: api`.

## GitHub Action

Run the diff in any repository's workflow, with no Python setup. The
Markdown summary appears on the job's summary page. The action is available
from v0.2.0:

```yaml
- uses: actions/checkout@v4
- uses: m-c-v-k/pbi-report-validator@v0.5.0
  with:
    old: reports/v1        # paths relative to the workspace
    new: reports/v2
    html: out/report.html  # optional; also json and markdown
- uses: actions/upload-artifact@v4
  with:
    name: report-diff
    path: out/report.html
```

For data validation, add `data: true`, `old-dataset` and `new-dataset`, and
pass the credentials as environment variables (never as inputs). Values stay
masked unless you set `show-data-values: true`; the job summary and any pull
request comment then contain row-level data, which is public on a public
repository.

```yaml
  env:
    PBI_TENANT_ID: ${{ secrets.PBI_TENANT_ID }}
    PBI_CLIENT_ID: ${{ secrets.PBI_CLIENT_ID }}
    PBI_CLIENT_SECRET: ${{ secrets.PBI_CLIENT_SECRET }}
```

To show the summary on the pull request, set `comment: true` and give the
job `pull-requests: write`. The action posts one comment per compared pair
of reports and updates it on later pushes (two steps with the same `old` and
`new` share one comment, so the last one wins); very long summaries are cut,
with a link to the run. Without write permission (for example on a pull
request from a fork) the comment is skipped with a warning:

```yaml
permissions:
  contents: read
  pull-requests: write
# ...
    with:
      old: reports/v1
      new: reports/v2
      comment: true
```

To fail the step, set `fail-on` (`info`, `warning` or `critical`) and, with
`data: true`, `fail-on-data-error: true`; they work as the CLI options of the
same name. Outputs are still set when the step fails.

To turn on the AI layer, set `ai: api` and pass your key as an environment
variable (never as an input); the key owner pays for use. The action then
runs the `-ai` image variant. `allow-data-to-llm: true` works as the CLI
option and needs `ai: api`. `PBI_VALIDATE_AI` and `PBI_VALIDATE_AI_MODEL`
are passed on too, so `PBI_VALIDATE_AI: disabled` (for example from an
organisation variable) blocks `ai: api`:

```yaml
- uses: m-c-v-k/pbi-report-validator@v0.5.0
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  with:
    old: reports/v1
    new: reports/v2
    ai: api
    ai-match: true
    ai-explain: true
    ai-explain-from: warning
```

The `ai-match`, `ai-explain` and `ai-explain-from` inputs map to the matching
CLI options and require `ai: api`. `ai-explain-from` accepts `info`, `warning`
or `critical`, and only applies when `ai-explain: true`.

Outputs: `json`, `html` and `markdown` (paths), `findings`, and the counts
`critical`, `warning` and `info`. All inputs are listed in
[`action.yml`](action.yml).

The action needs a Linux runner with Docker (such as `ubuntu-latest`) and
cannot run inside a job `container:`. Input and output paths must be
relative to the workspace or lie inside it or `$RUNNER_TEMP`.

**Versions.** Pin a full version tag such as `@v0.5.0`; it runs the
published image of that version. Before 1.0, minor versions can change the
output, so there is no moving `@v0` tag. Dependabot (`package-ecosystem:
github-actions`) can keep the tag up to date. Organisations that require it
can pin a commit SHA instead; the action then builds the image from that
commit, which takes about a minute longer.

## Data handling

- Runs locally or in your own CI; nothing is sent anywhere by default.
- Only files inside the project folder are read: a `definition.pbir` that
  points to a semantic model outside it is rejected with an error.
- With `--data`, queries go only to the Power BI API of your own tenant.
  Query results stay in memory and are never logged or sent anywhere else.
  The output files contain only masked rows unless you pass
  `--show-data-values` (action input `show-data-values: true`).
- The optional AI layer (`--ai api`, off by default) sends only metadata
  (names, field references, filter definitions, counts) to the Anthropic
  API with your own key. Row-level data is sent only with
  `--allow-data-to-llm` (action input `allow-data-to-llm: true`).
  `PBI_VALIDATE_AI=disabled` blocks AI entirely.

## Architecture

The tool is a layered Python package in which dependencies only point
inwards. `cli/` parses the arguments and hands over to `services/`, which
runs one comparison: load both projects, parse them, pair old and new
pages and visuals, diff them, optionally query the data, and render the
reports. Parsing, matching, diffing, DAX building and rendering are pure
functions on Pydantic models in `domain/`. All file, network and API access
sits in `integrations/`, so the core is tested without credentials and
works with the AI layer switched off.

```text
src/pbi_report_validator/
├── cli/           # Typer commands: parse arguments, call services, print
├── services/      # One validation run, data validation, AI steps, fail-on rules
├── parsers/       # PBIR report definition and TMDL / model.bim semantic model → domain models
├── matching/      # Pair old and new pages and visuals (deterministic, AI suggestions)
├── diff/          # Findings: structure, fields, filters, measures, query results
├── dax/           # A visual and its filter context → DAX query
├── reporting/     # JSON, Markdown, HTML and terminal output
├── domain/        # Pydantic models and pure helpers; no I/O
└── integrations/  # Files, Power BI REST API, Anthropic API, environment
tests/             # Mirrors src/, plus sample reports in fixtures/ and expected output in snapshots/
```

[CLAUDE.md](CLAUDE.md) has the full rules for each layer.

## Tech stack

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Strong data tooling, and the Power BI/Fabric ecosystem is Python-first |
| Packaging | uv, hatchling | Fast and reproducible; installs with `uv tool` or `uvx` |
| CLI | Typer | Typed commands with little boilerplate |
| Domain models | Pydantic v2 | Validated, serialisable models of reports and findings |
| Data comparison | pandas | Tabular diffs with tolerances, familiar to BI developers |
| HTML report | Jinja2 | One self-contained file that works offline, as a CI artifact and on GitHub Pages |
| Power BI access | httpx, MSAL | REST `executeQueries` with a service principal, so it runs in CI without Windows-only drivers |
| AI layer (optional) | Anthropic SDK | Rename suggestions and explanations; the tool works without it |
| Quality | pytest, ruff, mypy `--strict`, gitleaks | Fast feedback on every pull request |
| Distribution | GitHub Releases, GHCR, GitHub Action, GitHub Pages | Install, run in Docker or CI, or look at the demo without installing |

## Limitations

- Only the PBIR report format; the legacy `report.json` and `.pbix` files are
  not supported (save as `.pbip` with PBIR enabled)
- Data validation (`--data`) has been run against live published models with
  the sample reports, and CI replays the recorded API responses. See
  [its own limitations](#data-validation-optional---data)
- Comparing published reports needs local copies, saved as `.pbip` from Power
  BI Desktop ([#232](https://github.com/m-c-v-k/pbi-report-validator/issues/232)
  would fetch them through the API). A report with a `byConnection` reference
  in `definition.pbir` uses the `<Name>.SemanticModel` folder next to it;
  without one, measures are not compared (the run says so), and with
  `--data` a renamed measure can't be paired
- A visual moved to a different page shows as removed on one page and added
  on the other
- Filters the parser cannot read (such as relative date or "contains") are
  compared on their raw definition, so findings show JSON, and a renamed
  measure inside one shows as a change. With `--data`, every visual such a
  filter applies to is `not_validated`: one at report level covers the whole
  report, and fails the run with `--fail-on warning`
- The GitHub Action has no input for `--attribute` yet; use the CLI or the
  Docker image for it

## Development

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you).

```bash
uv sync                        # install runtime and dev dependencies
uv run pbi-validate --version  # run the CLI
uv run pytest                  # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

Every CI run shows the test results and a coverage table in its summary
and attaches the HTML coverage report. The coverage report of the latest
release is on the [demo site](https://m-c-v-k.github.io/pbi-report-validator/coverage/);
CI fails if coverage drops below 95%.

See [CLAUDE.md](CLAUDE.md) for contribution rules and
[docs/PROJECT.md](docs/PROJECT.md) for scope and milestones.

## Branching

- `develop` is the default branch where work is integrated.
- Feature branches (`feat/<issue>-slug`, `fix/<issue>-slug`) start from
  `develop`, and pull requests target `develop`.
- `main` holds released versions only. It is updated by a release PR from
  `develop`, followed by a version tag.
- Both branches are protected: changes go through pull requests and need
  green CI.

## Built with Claude Code

This project was developed with Claude Code (agent-driven development) as
part of the course *Next-Generation Software Development with AI*.

Issues and pull requests can be handed to [Claude Code](https://github.com/anthropics/claude-code-action):

- Mention `@claude` in an issue or PR comment to have it implement or change
  something. It follows [CLAUDE.md](CLAUDE.md) (feature branch, one issue per PR).
- New non-draft PRs get one automated review.

Only the repository owner can trigger these runs. They authenticate with the
owner's Claude subscription (`CLAUDE_CODE_OAUTH_TOKEN`), not an API key, so
they cost nothing extra.

## License

MIT — see [LICENSE](LICENSE).

This is an independent project and is not affiliated with or endorsed by
Microsoft. Power BI is a trademark of Microsoft Corporation.
