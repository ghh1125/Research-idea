# Advanced usage and implementation notes

**English** | [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue)](advanced-usage.zh-CN.md)

[Back to README](../README.md). Start with installation, startup, and CLI usage there. This page covers literature sources, skills, backend protocols, budgets, and reports in more detail.

> For the current v1.0.0 research flow, see [Workflow](workflow.md). This page also preserves early implementation details: references to a second technical-design stage, the two-thirds initial reading allocation, and report schema 14 describe historical compatibility. The current workflow uses broad reading and two discussions, ends with problems and motivation, and uses report schema 18. It no longer reserves initial reading capacity for technical design.

## Virtual environment installation

For source development or a manually managed Python environment, install from the cloned repository.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
research-idea
```

On Windows PowerShell, call the virtual environment's executables directly without changing script execution policy:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\research-idea.exe
```

The short command in this setup depends on an activated virtual environment. To launch directly from any terminal, follow the platform-specific pipx steps in the README. PDF reading still requires Poppler, and model backends still need local authentication.

## Using your own topic and papers

Create a separate project and choose a backend. CLI backends must already be installed and authenticated locally.

```bash
research-idea init "Conflicting evidence in long contexts" \
  --project ./research-projects/evidence-conflict --backend codex

research-idea add --project ./research-projects/evidence-conflict ./papers/paper.pdf
research-idea add --project ./research-projects/evidence-conflict ./notes/reading.md

research-idea run --project ./research-projects/evidence-conflict --no-search
```

You can provide full text for papers you already consider central. The default full-text paper limit is 6 across the workflow. Without local papers, discover abstracts automatically from the topic:

```bash
research-idea run "Conflicting evidence in long contexts" \
  --project ./research-projects/conflict --backend claude

research-idea search "conflicting evidence language models" \
  --project ./research-projects/conflict --source arxiv --limit 10
```

`search` supports arXiv and OpenAlex; venue searches also use OpenReview acceptance records for COLM. Network access, index coverage, and API quotas depend on the environment. For OpenAlex, `search_api_key_env` names the environment variable holding a key. The first stage forms `research_routes` from possible explanations and existing approaches: usually three routes, at most four, explored through up to six English queries linked by `route_ids`.

In the historical two-stage workflow, the second stage searched for transferable mechanisms and technical approaches through up to three queries tied to the idea's two design angles. Queries did not all need to name the original application domain. Planned and executed searches were recorded separately. The initial reading allocation was `ceil(2 × max_papers / 3)`, reserving the rest for technical exploration. Resuming with identical requirements reused search checkpoints; changed requirements, scope, or reading limits triggered rediscovery and further reading within the remaining project budget. Existing papers were retained and cumulative usage was not reset. `--no-search` skipped online retrieval while the historical second stage still organized two design angles using existing materials. See the current workflow linked above for the replacement flow.

### Conference papers and full text

Start with the recent AI/CS scope:

```bash
research-idea start "Designing evolving environments for LLM agents" \
  --project ./research-projects/agent-environment \
  --backend codex --model gpt-6.1-sol \
  --literature-preset ai-recent
```

`ai-recent` searches the 20 venues and corresponding publication series listed below, then supplements them with arXiv CS preprints. Coverage includes AI/NLP/agents, data mining and databases, retrieval and the Web, and vision and multimodal research. Selection still follows the research topic. Hybrid retrieval initially allocates about two-thirds of result slots to conference sources and the remainder to preprints. More CS preprints can fill gaps when conference indexes fail or return too few results. Limited slots are prioritized by relevance and date while balancing venues, so venues at the end of the list are not always excluded.

New projects default to CS-only retrieval with rolling dates: 12 months for background and strategy exploration, and 6 months for motivation and contribution comparison. Dates are recalculated on each run. Projects with fixed dates retain those settings. Use `/date` to switch modes, or specify exact limits:

```bash
research-idea start "Your research direction" \
  --project ./research-projects/scoped --backend codex \
  --literature-preset ai-recent \
  --since 2025-01-01 --until 2026-10-23 \
  --venues NeurIPS ICML ICLR ACL EMNLP \
  --arxiv-categories cs.AI cs.CL cs.LG cs.MA
```

The corresponding settings are `search_source = "hybrid"`, `search_since`, `search_until`, `search_cs_only = true`, `arxiv_categories`, and `search_venues`. arXiv requests include categories and initial submission dates. OpenAlex uses publication dates and source IDs, or its Computer Science field when no venues are specified. Returned records are checked again for dates and fields; records missing required metadata are excluded with a reason. A new revision of an old paper does not pass the date filter merely because it was updated recently. Ordinary keywords use AND; quoted phrases and native Boolean queries are preserved.

These limits apply to newly executed online searches. Existing materials and explicitly imported classic papers remain project context. Use a new project directory for a corpus governed entirely by the new scope. Scope and venue changes are part of search cache identity, so old results cannot stand in for a new search. `--no-cs-only` disables the CS field check; `--arxiv-categories` still controls arXiv categories separately. Passing `--venues` without values clears the saved venue scope.

```bash
research-idea venues
research-idea init "Conflicting evidence in long contexts" --project ./research-projects/venues
research-idea search "conflicting evidence language models" \
  --project ./research-projects/venues \
  --venues ACL EMNLP NAACL COLM --full-text --limit 12
research-idea run --project ./research-projects/venues --no-search
```

Or start in one command:

```bash
research-idea start "conflicting evidence in language models" \
  --project ./research-projects/conflict-venues --backend codex \
  --venues ACL EMNLP NAACL COLM
```

- `--venues` selects the OpenAlex route automatically. Venue identity comes from publication-source metadata, not paper titles. COLM uses accepted OpenReview `venueid` records from at most the three latest editions, with bounded pagination per edition, then ranks English keyword matches in titles and abstracts. This is not full semantic retrieval.
- `ai-recent` / `ai-recommended` includes NeurIPS, ICML, ICLR, ACL, EMNLP, NAACL, COLM, AAAI, IJCAI, AAMAS, KDD, ICDM, ICDE, SIGMOD, VLDB, ACM MM, CVPR, ICCV, SIGIR, and WWW by default. ICAPS, KR, and UAI are excluded. Papers are still selected by topic, relevance, and date; `/budget max_papers` controls the full-text reading limit.
- `ACM MM`, `ACMMM`, and `MM` identify the same venue. WWW recognizes both The Web Conference and ACM Web Conference; VLDB retrieval includes PVLDB. SIGMOD retrieval includes PACMMOD, retaining the actual series name because it also publishes PODS papers. Ranking categories are stored separately from the research scope.
- Existing projects keep their saved venues. Use `/scope ai-recent` or `/venues ai-recommended` to enable the expanded scope.
- Ratings retain separate CCF 2026, ICORE2026, and TH-CPL 2019 sources. CCF 2026 lists ICLR as A and IJCAI as B; COLM is an independently selected venue. The Tsinghua version refers to the verified university-hosted document, not a claimed 2026 revision. Versioned presets are `ccf-a-ai-2026`, `tsinghua-a-ai-2019`, and `core-astar-ai-2026`; `core-astar-2026` offers all 62 A* venues for explicit selection. `ccf-a-ai-2022` remains only for old configurations.
- Explicit venue filters target the main conference. Findings, workshops, demos, and industry tracks are not mislabeled as the main track. Unresolved sources, truncated pagination, and service failures appear in `coverage.gaps`; an unfiltered fallback is not presented as matching the requested venue.
- `search --full-text` downloads PDFs from public academic sources and extracts text. Without it, manual search imports only metadata and abstracts. Poppler's `pdftotext` is required. After a download failure, the system searches arXiv by full title, checks the title and known authors, and reads a matching preprint while preserving the venue identity and actual full-text version. PMLR uses PDF links from paper pages, including the official `mlresearch` repository. If public full text is still unavailable, import a local PDF with `add`.
- `start/run` attempts full-text retrieval for abstract records by default. `--no-fetch-full-text` disables downloading; `--no-search` uses imported materials only and also disables automatic full-text downloads.
- A source becomes `full_text` only after nonempty text is downloaded and extracted. Failed downloads, scanned PDFs, and unsupported sites retain their abstracts and specific gaps. Downloaded papers still follow reading budgets; reports distinguish full supplied text from partial excerpts.

`report.json` retains automatic/manual search records, venue scope, index coverage gaps, and full-text retrieval records. Model search suggestions are not treated as executed searches.

TXT/Markdown defaults to `notes`; text extracted from PDF becomes `full_text`. If a TXT/Markdown file contains an entire paper, specify `--kind full_text`. This declares the source type; it does not certify authenticity.

JSON accepts one paper object, an array, or `{"papers": [...]}`. For example:

```json
{
  "id": "local-paper-001",
  "title": "Actual paper title",
  "authors": ["Author"],
  "year": 2026,
  "url": "https://example.org/paper",
  "content_kind": "full_text",
  "text": "Actual paper text..."
}
```

`example.org` illustrates the format and is not a paper source.

## Selection and question-focused reading

The original selection flow retrieved up to 20 metadata records per query. Up to six first-stage queries recorded provenance by route, then deduplicated and interleaved results into at most 40 candidates. One model call selected relevant, complementary papers. Within routes, term relevance and publication date informed ranking; semantic selection focused on the user's problem, motivation, and mechanism, preferring newer work when relevance was equal. Sharing a word such as “agent” or “adaptation” was not enough to fill a route. Each selected paper received a reading reason and a question for its full text. `reading_question` and route information continued into reading and analysis-card tasks. Title-only records could be selected for checking; missing methodological details still required full text. Selection counted toward the call budget, could be cached, and did not judge novelty. In v1.0.0, all initial candidate abstracts participate in broad reading and synthesis before full-text selection; see [Workflow](workflow.md).

Only selected top-k papers receive full-text retrieval. The historical default was 6 papers overall: up to 4 initially for the problem, motivation, and basic idea, with the rest reserved for technical design. The initial quota rounded two-thirds of `max_papers` upward. Papers were not added simply to fill slots, and known older neighbors were not deleted because of rolling dates. Reading retained per-paper chunk and follow-up limits. Without new text, the original analysis card was kept and the handling of the follow-up request recorded, rather than regenerating the card. The current problem-focused flow no longer uses the two-thirds reservation.

Historical first-stage reading compared phenomena, motivation, conditions, explanations, and research claims. The second stage reused evidence and looked for transferable strategies for specific design questions. Similar methods did not eliminate candidates; a new framing still needed a different research question or testable prediction. Output prioritized the problem, motivation, existing limitations, core insight, and contribution before technical references. Internal review states remained in detailed records.

HTTP 429 follows `Retry-After`. Long quota waits suspend that service for the run and use alternatives rather than blocking the whole run. HTTP 403 is not repeatedly retried. Successful metadata is cached for 24 hours, and repeated project queries reuse venue catalogs. If OpenAlex/OpenReview indexes are unavailable, alternatives include ACL Anthology, PMLR, the NeurIPS main-track directory, ICLR paper lists, and COLM's official acceptance list. Only selected ICLR/COLM papers have full-text links resolved; COLM preprints require equal normalized titles. Catalog dates retain their original month/year precision rather than inventing a day.

If a selected conference paper's PDF fails to download, the same retrieval time budget includes a title search for an arXiv preprint. Normalized titles must match; when both sources list authors, they must overlap too. Reports retain venue metadata separately from the preprint URL and version actually read. Completing a PDF URL does not trigger repeated downloads of the same failed paper within a round.

## How papers are analyzed

Full-text reading is enabled by default. The detailed reading path locates sections and figure/table/equation markers, reads methods, experiments, and available appendices in chunks, and forms a nine-part card: **problem, motivation, insight, method, differences from prior work, experimental design, results, conclusion boundaries, and research implications**. Each part distinguishes source support, model analysis, missing evidence, and non-applicability; theoretical papers need not supply nonexistent experiments. The current workflow first reads background material and uses detailed reading when the research question needs it.

Method analysis explains inputs, outputs, necessity, and tests that isolate a module's contribution. Experiment analysis connects author claims, actual settings, results, and supported conclusions. Author-acknowledged limitations, model concerns, and opportunities to investigate are stored separately. Specific gaps can trigger reading of previously unseen sections or figure/table IDs and an updated card. Follow-up is one budgeted cycle, not an unbounded effort to fill every field.

By default, initial detailed reading uses at most 3 consecutive chunks per paper, each limited to `source_chars`, followed by up to 2 additional chunks as needed. Each chunk yields at most 6 source quotations. Reading, card creation, and follow-up all share the call budget. Abstracts and notes retain their limited source status and cannot be promoted to full-text analysis.

Section and figure detection is heuristic. Coverage measures text supplied to successful reading tasks, not completeness of model understanding. Analysis currently uses extracted text without visual verification of images, table layout, or equations. Unread material, retrieval failures, and missing controls are questions to investigate, not proof that something is absent or infeasible.

In the historical two-stage flow, first-stage ideation and contribution comparison used a snapshot of initial reading materials; old projects could recover their initial batch sources. The snapshot preserved source methods, experiments, results, conditions, concerns, and quotations, while excluding reader-generated opportunities, idea suggestions, proposed experiments from concerns, and interpretations targeted at old candidates. Full cards and evidence remained in the project. The second stage reused them and extracted design references from up to three papers: the original method, shared structure, conditions, adaptation, and simple alternatives. Existing evidence was reused first; specific questions triggered follow-up without automatically regenerating full cards. The final proposal recorded design choices and reasons. Current delivery stops at problems and motivation.

Quotation matching handles PDF ligatures, typographic quotes, soft hyphens, and line-end hyphenation while preserving the unchanged source and exact character offsets. Changed words, numbers, negation, or noncontiguous splicing do not pass. If a quote cannot be located, the controller supplies it and nearby source text for one targeted repair. Remaining failed observations are excluded individually and recorded in `quote_gaps`; other valid evidence remains usable. Excluded quotes do not enter the evidence store and cannot reject a candidate. Matching verifies that text exists, not that its interpretation or a novelty judgment is correct.

PDF extraction uses Poppler's default reading order and retains page boundaries. It avoids physical-layout extraction that can interleave two-column lines. Tables and equations still require attention to reading gaps. Old projects do not automatically rewrite stored text; reimport corrected full text if needed. Explicitly imported nonempty full text updates the source even when shorter, invalidating old evidence and candidate batches. An ordinary abstract update does not overwrite full text.

Research review uses a separate task on the same configured backend by default, not independent cross-model validation. Blockers, revisions, and exhausted rounds are recorded separately. A model's recommendation to continue does not establish experimental evidence; unexecuted proposals remain `untested`.

## Built-in and local skills

**Built-in CLI skills are enabled by default**, including in installed wheels. They load by stage rather than all entering every prompt:

| Skill | Research responsibility |
| --- | --- |
| `research-idea-analyze-paper` | Analyze problems, methods, and experiments with the nine-part framework; follow up on consequential gaps |
| `research-idea-read-evidence` | Extract methods, conditions, limitations, and source quotations |
| `research-idea-audit-claims` | Compare author claims with experimental support, retaining tested scope, confounds, and unread appendices |
| `research-idea-motivation` | Build Background → Existing approaches → Possible remaining problems → Motivation → Idea; examine significance and the core idea |
| `research-idea-compare-methods` | Compare nearby work along six dimensions to locate substantive differences in core claims |
| `research-idea-build-mechanism` | Clarify interventions, information flow, mechanisms, and testable predictions |
| `research-idea-check-feasibility` | Check signals, interfaces, data, learning paths, and resource assumptions |
| `research-idea-design-falsification` | Examine the core explanation and weakest assumptions without expanding an experiment plan by default |

**Locally installed skills can be selected additionally.** Discovery covers `.agents/skills`, `.codex/skills`, and `.claude/skills` in common project/user locations, plus `CODEX_HOME/skills`. Use `--root` or `--skill-root` for custom locations. This is bounded directory discovery, not a full reproduction of Codex's global plugin discovery.

```bash
research-idea skills list
research-idea skills list --root ~/code/CCFA-Skills
research-idea skills show research-idea-motivation

research-idea skills use ccf-idea-optimizer ccf-idea-reviewer \
  --project ./research-projects/conflict --root ~/code/CCFA-Skills
research-idea resume --project ./research-projects/conflict --no-search
```

`skills use` saves explicit external skill paths; `skills clear --project PATH` clears only external selections. Repeatable `--skill NAME_OR_PATH` and `--skill-root DIRECTORY` also work with `start/run/resume/init`. Ambiguous paths produce an error instead of silently selecting a same-named skill. A symlinked skill directory can supply its direct `SKILL.md`.

```bash
research-idea start "Your research topic" --project ./research-projects/my-idea \
  --papers ./papers --no-search \
  --codex-bin /absolute/path/to/codex --codex-profile research \
  --skill ~/code/CCFA-Skills/ccf-idea-optimizer/SKILL.md
```

`--codex-profile` names a profile already configured in Codex; omission uses its defaults. `--codex-bin` is an executable path or a name on PATH, not a shell command. This program does not read or rewrite global authentication files.

A local launch script can set `RESEARCH_IDEA_CODEX_BIN` as the default executable. It replaces only the default project name `codex`, preserving saved custom paths. An explicit `--codex-bin` takes precedence.

Corresponding project configuration:

```toml
codex_bin = "codex"
codex_profile = ""
builtin_skills = true
skill_paths = []
skill_roots = []
skill_max_chars = 48000
```

Set `builtin_skills = false` or pass `--no-builtin-skills` for customization or comparison. External skills are not automatically enabled merely because they are installed. Each file is limited to 32 KiB and combined text to `skill_max_chars`; exceeding a limit raises an error instead of silently truncating.

The loader reads selected Markdown text. External reference files must be selected explicitly. Skill scripts, network access, and tools do not execute automatically or change task output formats, evidence rules, or budgets. Source evidence stays separate from skill guidance. Each load records name, source, stage, path, and SHA-256. Changed skills invalidate relevant tasks and candidate batches while preserving history.

CCFA idea optimizer/reviewer and experiment designer can be explicit supplements, including their relevant reference files as needed. The eight built-in skills were written for this project; third-party code and documents are not bundled. Design influences from ARIS, Supervisor-Skills, IdeaScientist, research-idea-explorer, and others are listed in [Sources](sources.md).

## Backend configuration

Each project has its own `research.toml`. Keys are read only from environment variables; keep them out of configuration, papers, and Git.

### Codex CLI

```toml
backend = "codex"
model = ""
```

An empty model inherits the CLI's selection. You can also use `research-idea run --project PATH --model MODEL_ID`. The adapter uses non-interactive execution, a read-only sandbox, and structured output, disabling built-in execution/search capabilities unnecessary for research inference. Your normal configuration can enable MCP: the adapter reads the service list, overrides each with `enabled=false` for this call, and checks the effective list before sending materials. Desktop-injected services receive valid but inactive transport configuration without copying service addresses, environment variables, or credentials. No global configuration change or separate profile is needed. See the [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). Incompatible CLI versions prompt an update rather than returning fabricated results.

### Claude Code CLI

```toml
backend = "claude"
model = ""
```

The adapter uses `claude --safe-mode -p`, JSON Schema, and settings disabling built-in tools and MCP. A version supporting these arguments is required; existing authentication is retained. The Research-idea controller handles literature retrieval and text reading; Claude receives the materials needed for each analysis task.

### OpenAI-compatible API

This is a complete minimal project configuration; unspecified options use defaults:

```toml
backend = "api"
api_provider = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "RESEARCH_API_KEY"
model = "YOUR_SUPPORTED_MODEL_ID"
max_output_tokens = 8192
api_max_tokens_field = "max_completion_tokens"
```

Set `RESEARCH_API_KEY` in the terminal, then run `research-idea run --project PATH`. The adapter uses `/chat/completions` and strict `json_schema` output; custom services must support them. Change `api_max_tokens_field` for older services using `max_tokens`. Unsupported strict schemas produce an explicit error rather than silently falling back to free text.

For a local compatible service, use `base_url = "http://127.0.0.1:8000/v1"` and `api_key_env = ""`. Remote services require HTTPS. Credentials do not belong in URLs.

### Native Anthropic API

```toml
backend = "api"
api_provider = "anthropic"
base_url = "https://api.anthropic.com/v1"
api_key_env = "ANTHROPIC_API_KEY"
model = "YOUR_STRUCTURED_OUTPUT_MODEL_ID"
max_output_tokens = 8192
```

This uses native `/messages` and structured output. When changing providers, also update an explicitly configured endpoint and key variable; explicit values are preserved.

## Budgets and recovery

On Windows, `[WinError 32] ... research-codex-...` usually means the model CLI or another program still holds the temporary directory, preventing cleanup after the call. Updated versions briefly retry cleanup; persistent locks display `[cleanup]` and retain the directory without replacing a successful model result or the original call error. Timeout/interruption handling also attempts to terminate the Windows CLI process tree. For a project interrupted by this in an older version, update, restart the CLI, and use `/run` to reuse checkpoints. Leftover directories are in the system Temp folder and can be removed after the related processes exit.

Example configuration, including fields retained for older workflows:

```toml
max_candidates = 3
max_rounds = 2
max_papers = 6
search_results_per_query = 20
search_date_mode = "rolling"
strategy_months = 12
novelty_months = 6
max_calls = 200
max_seconds = 18000
timeout_s = 180
source_chars = 24000
deep_reading = true
max_paper_read_chunks = 3
max_followup_reads = 2
auto_search = true
constraints = "One 24 GB GPU; two weeks; small-scale fine-tuning allowed; no ground-truth answers at inference"
```

- New projects default to 200 calls and 300 minutes of cumulative runtime. Existing explicit limits are preserved. Limits are ceilings, not targets. `max_followup_reads = 0` disables extra reading; `deep_reading = false` uses brief evidence extraction.
- `max_calls` persistently counts backend `generate` calls, including structured-output repairs. API requests use at most three HTTP attempts and record known attempts; request counts internal to CLI backends are unknown.
- `max_seconds` counts cumulative controller runtime, checked and saved at task boundaries. Force-killing a process may lose time since the last checkpoint. It is not an operating-system-wide billing limit.
- Each backend call has a local timeout. API requests run in a terminable subprocess. Disconnecting cannot guarantee immediate termination of remote inference or billing.
- Successful tasks are cached by inputs, prompts, and backend settings. Existing candidate batches are retained; internal supplementary literature does not regenerate the entire batch.
- Explicit corpus changes through `add/search`, or `run --replan`, establish a new candidate batch; old batches remain in event history.
- Budget exhaustion returns exit code `3` and exports the current report. Raise the configured limit and `resume`. Ordinary errors return `1`.

```bash
research-idea status --project ./research-projects/conflict
research-idea resume --project ./research-projects/conflict
research-idea inspect --project ./research-projects/conflict
research-idea inspect --project ./research-projects/conflict EVIDENCE_OR_IDEA_ID
research-idea inspect --project ./research-projects/conflict PAPER_ID --paper-card
research-idea inspect --project ./research-projects/conflict --events
research-idea export --project ./research-projects/conflict
```

`status` and `inspect` use read-only SQLite snapshots and can show progress during research. Mutating commands remain protected by a single-writer process lock.

By default, results are saved under the source repository in an automatically named `idea-TIMESTAMP/` folder, containing `report.md`, `report.json`, candidate Markdown, and `papers/` analysis cards. `/output PATH` or `--output PATH` changes only the parent directory; the folder name stays fixed and resumption reuses it. `output_dir` in `research.toml` stores the parent. Manually entered relative paths resolve against the project directory; CLI paths become absolute when entered.

Historical JSON report `schema_version` `14` included background/problem/motivation arguments, research-route/query associations, problem exploration, independently analyzed `problem_cases`, the full problem pool and comparative selection reasons, first-stage `positioning`, `idea_core.information_path`, `idea_neighborhoods`, `feasibility_sketch`, two `design_axes`, query/method `axis_ids`, second-stage `design_transfers` and `design_decisions`, contribution claims, per-paper six-dimensional comparisons, seven-dimensional feasibility checks, required signals and stages, and compatibility fields `validation` (no experiment plan by default), `feasibility_status`, `comparison_gaps`, and `feasibility_assessment`. It also retained `paper_cards` with reading coverage and follow-up records, `search_plans`, `paper_claim_audits`, and each version's `revision_record`. Claim audits are source-grounded model judgments, not independent replications. Current schema and fields are documented in [Architecture](architecture.md). The runtime database is `research.sqlite3`; research materials and run directories should stay out of the source repository.

## Development and testing

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests cover quotation location, citation consistency, recovery, budgets, CLI protocols, local HTTP APIs, timeouts, literature parsing, local skills, scope filtering, and cache invalidation. Earlier integration checks on macOS used Codex CLI with `gpt-6.1-sol` for structured output and recovery, and retrieved real arXiv CS papers. Those checks encountered OpenAlex HTTP 429 and OpenReview HTTP 403, recorded as coverage gaps. They did not establish Claude/API account coverage, GPU execution, or systematic idea quality. Offline tests alone do not establish research effectiveness.

Further evaluation should focus on whether real topics produce worthwhile research ideas. See [Architecture](architecture.md) and [Sources](sources.md).
