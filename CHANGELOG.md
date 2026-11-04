# Changelog

**English** | [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue)](CHANGELOG.zh-CN.md)

## v1.0.0 documentation update · 2026-11-04

- Public user and developer documentation now has English default pages and complete Simplified Chinese counterparts. Each page offers a language switch, and internal documentation links stay in the selected language. Built-in skill instructions and application behavior are unchanged.
- Added a documentation index and marked the early Web preview and historical implementation details clearly, with links to the current workflow.

## v1.0.0 · 2026-11-03

- Added Web controls for dates and venues, model refresh and sign-in information, attachments, conversation-history search, and a Web-specific user guide. Common operations work through buttons. Optional shortcuts reuse CLI logic and do not enter research conversations. Fixed collapsing paper details after refresh, missing citation locations, incorrect report disclosure markers, and incomplete settings inheritance for new research.
- Positioned the release as a literature reading, analysis, and ideation tool: multi-source search, batched broad reading, approach synthesis, targeted full-text analysis, source quotations, multi-turn discussion, research propositions, and report export form a complete workflow.
- Unified new-project defaults at 200 model calls and 300 minutes (18000 seconds) of cumulative runtime across CLI, interactive setup, and Web. Existing explicit budgets remain unchanged and can be adjusted through `/budget` or Web settings.
- Retained two discussion pauses and explicit Continue. Corrections to research intent update the current problem draft and reuse existing reading first, with targeted reading or search for specific gaps.
- Placed the version beside the main heading in both READMEs; updated product descriptions, installation/upgrades, budget examples, and command explanations. CLI and Web startup commands remain separate.

## v0.8.0 follow-up improvements · 2026-11-03

- Expanded abstract selection into resumable batched broad reading and approach synthesis: up to 40 papers initially, with up to 2 extra queries and 16 candidates for coverage. All short notes and original abstracts are retained; full-text selection no longer determines the literature available to discussion.
- Discussion receives approach overviews and paper notes, with original abstracts selected for the current question. It can request targeted reading of sources not initially selected for full text. CLI, Web, and reports expose broad-reading sources; Web can expand notes.
- Open directions compare important problems; specific questions compare existing responses, explanations, and research angles without forcing a topic change. Similar titles or names do not establish overlap; substantive comparison requires problems, mechanism conditions, and actual scope of resolution.
- Literature overviews retain their original goals and query scope. Discussion feedback reuses records, requests named passages, or searches specific gaps, avoiding stale coverage judgments after a goal change.
- Corrections to an overextended direction revise both intent and the problem draft. Discussion after same-turn reading uses the updated goal's reasoning mode rather than the old open-exploration mode.
- Removed the two-thirds initial full-text allocation in the current problem workflow; the default limit is 6 papers. Preserved two discussions, targeted reading, quotation validation, cumulative budgets, and old-project recovery.
- Updated both READMEs, research skills, and regression tests. Contributors had connected Web to real projects and the research worker; the November 1 preview notes below describe its earlier state.

## v0.8.0 · 2026-11-01

- Added the `research-idea web` local service. The model dropdown reads the local Codex catalog with caching, refresh, pagination, and model-specific reasoning options, without inference. Failed refreshes retain the catalog and selection and show the data source.
- Simplified the main Web interface to conversation and system settings. Configuration, literature, history, and step details open in dialogs; unsent drafts survive closing them.
- Added a conversation list and New conversation in the sidebar; removed the preview-stage control at the top. The stage appears above the input, explaining that sending discusses/revises while Continue advances.
- Step details show queries and sources, paper locations, skill rationale, comparisons with existing responses, revisions, and call records. Research logs were still examples; a read-only endpoint loaded built-in skill text from the installed version.
- Added a locally viewable Web interaction preview with a simple conversation home and expandable literature, research propositions, notes, and history.
- Used model dropdowns designed for automatic backend discovery and refresh, with reasoning-depth dropdowns and advanced options under additional settings.
- Retained preview states for creation, discussion, continuation, running, stopping/resuming, and retrying errors. Updated both READMEs and local-preview startup instructions.
- At this release, Web research content still used sample data and was not connected to account checks, the research engine, or project storage. Codex model discovery was live; other providers were not connected. Real research still used the CLI, with its core workflow unchanged.

## v0.7.0 follow-up improvements · 2026-11-01

- Fixed old selection questions overriding targeted reading. Current questions are passed per paper, preserving query phrases and prioritizing requested algorithms, sections, figures/tables, and appendix identifiers, including long algorithm titles and wrapped lines.
- Passed the current problem's rationale and strongest existing response into paper selection, distinguishing work explaining a phenomenon from work that may solve the difficulty. Reused existing follow-up capacity without a mandatory new review step.
- Later model inputs share exactly duplicated materials through recoverable references, without deleting or rewriting evidence or active user requirements, or changing storage, reports, or output schemas. Updated offline demos and recovery, reading, and research-frame tests.
- Discussion can ask one consequential follow-up as needed. The previous question is retained to interpret short replies, but assistant questions are not user decisions. Summaries, retrieval, and analysis do not require an answer first; unanswered questions do not block `/continue`.
- When related work narrows or changes a problem, existing revision records explain covered scope and remaining research value, avoiding novelty manufactured through repeated special conditions.
- Updated built-in skills and bilingual instructions; added follow-up recovery, failure retry, stage isolation, and an entry point for real multi-turn discussion evaluation.

## v0.7.0 · 2026-10-31

This release addressed coherent initial ideas being fragmented during problem selection and core concerns being silently dropped. Delivery remained research problems, motivation, and a research proposition.

- Strengthened targeted reading. The same call saves a paper's problem, core intuition, inputs and key information sources, processing, outputs, and implications for the current research. These feed ideation and discussion; CLI prioritizes implications. Paper claims, cited prior findings, inferences, and hypotheses remain separate. Interpretations tied to invalid quotes are removed too, without fixed extra calls or an experiment workflow.
- Gave new explanations a separate context budget, balancing paper coverage and preventing duplicate injection through follow-up results without truncating judgments or quotations. Fixed explanation ownership when changing goals and reading in one turn; retries preserve atomic goal updates and reuse reading.
- Before search, distinguishes open exploration, developing an existing idea, and examining a given problem. Records goals, hypotheses, original-message provenance, and relationships among concerns. New research usually adds one model call.
- Search planning and targeted reading consider different needs and their relationships within existing query, reading, and overall budgets, without a mandatory new novelty-search round.
- Problem analysis retains related seeds. Comparison supports selection, synthesis, or evidence-based reframing. Original cases are preserved; final framing records source members, the disposition of concerns, and scope-change reasons.
- Users can revise the research frame during discussion. Original wording, before/after versions, and reasons persist. Papers can revise hypotheses without fabricating user decisions. Temporary presentation requests do not become lasting research requirements.
- CLI shows relationships among difficulties and reasons for focus. `/memory` shows the current frame and provenance; report JSON adds the frame and revision history. Old paused projects remain resumable, and new logic does not overwrite user-confirmed problems automatically.
- Updated stage-loaded skills, bilingual READMEs, framework diagrams, call estimates, and implementation docs. Structural validation checks provenance, links, and complete handoffs, without scientific scoring or publication gates.

Upgrade from the repository with `git pull --ff-only`, then `pipx reinstall research-idea` (Windows: `py -3 -m pipx reinstall research-idea`). For this release, `research-idea --version` should show `0.7.0`. Use `/open PROJECT_DIR` to resume a discussion, or enter a topic for new research.

## v0.6.0 · 2026-10-30

This release focused on multi-turn discussion of one research question, memory retrieval, and CLI usability. Delivery remained background, existing approaches, problem, motivation, and a research proposition.

- Supports Codex configurations with MCP normally enabled. Overrides and verifies services only for the research inference call without changing global configuration or authentication; no manual profile switch is needed.
- Added turn-only memory scope, expiring after a successful reply. Local length and formatting requests do not become long-term preferences by default. Original wording helps handle older misclassified records, while explicit lasting requirements remain active.
- Multi-turn discussion displays `[update] Changes this turn`, comparing actually saved versions and notes. Verbal promises do not count as edits, failed turns do not publish partial updates, and `/memory` shows complete changes.
- History retrieval combines the current question and recent reply, retaining explicit keyword priority and message-count limits. Vague follow-ups can recover relevant corrections without another model call.
- Made the default README English, with a complete Chinese version and reciprocal switches at the top.
- `/help` groups all interactive commands by purpose. `/help COMMAND`, `/COMMAND --help`, and `-h` explain purpose, arguments, and examples; `/help all` expands all instructions.
- Completion menus explain commands. Date, budget, and recovery commands describe argument meanings, units, and effects.
- Added descriptions, argument help, and examples to every terminal subcommand and skill subcommand; both READMEs list all commands.
- Documented repeated discussion of one problem: follow-ups and corrections, current-version inspection, targeted reading, `/continue`, revisions after delivery, and reopening projects.

Upgrade from the repository with `git pull --ff-only`, then `pipx reinstall research-idea` (Windows: `py -3 -m pipx reinstall research-idea`). For this release, `research-idea --version` should show `0.6.0`; `/open PROJECT_DIR` resumes existing discussion. See the [README](README.md) for full installation and upgrade instructions.

## v0.5.0 · 2026-10-26

- Connected cross-paper synthesis and competing explanations of the same difficulty to persistent state and subsequent problem selection. Background understanding no longer relies solely on individual abstracts.
- Reopened ideation once after targeted reading, supporting retained, rephrased, merged, or replaced directions with before/after versions and reasons, without another search loop.
- Traced representative originals through related work and references, checked existing retrieval, and searched missing titles within the shared follow-up budget, with recovery support.
- Discussion saves specific objections, research judgments, and reconsideration conditions with original-message provenance. Records can supersede older ones and are visible through `/memory`.
- Split the motivation skill into task-loaded references whose changes affect cache fingerprints. Initial background reading does not load method-comparison or claim-audit guidance.
- Moved direction discussion earlier: initial full-text reading covers introductions, related work, and conclusions; methods and results are read after discussion for specific questions, rather than completing every card and audit before the first interaction.
- Added one bounded keyword expansion when long natural-language arXiv queries return few results. Follow-up considers both the closest existing response and new difficulties; named papers are no longer blocked by initial reading quotas.
- Replaced large contents lists in ideation context with coverage summaries, preserving full quotations, conditions, and citation locations. Improved PDF small-cap heading and body-noise handling.
- Strengthened explanations of how difficulties arise and why existing responses leave them unresolved. Reduced repeated CLI output and stopped labeling problem-focused reading as design work.
- Focused delivery on important literature-grounded problems and motivation: background, existing approaches, problem, motivation, and a one-sentence research proposition. Removed default proposal generation, technical routes, and experiment design.
- Pauses after direction mapping and after deeper problem comparison. `/continue` advances using the current version; ordinary messages can revise directions, arguments, and selection.
- Discussions with specific information gaps can search/read and then update judgments. Each turn permits up to two follow-up papers; successful steps are resumable.
- Retained complete conversations. Active notes have original-user provenance; old requirements can be superseded or withdrawn, and temporary requirements belong to the current discussion. Earlier messages are retrievable by content.
- `/history [KEYWORDS]` searches original dialogue, `/memory` shows active notes, and `/problems detail` expands full problem reasoning.
- Restarting restores the discussion. Follow-ups after completion still revise problems and motivation. Model/effort changes preserve user selections.

Upgrade from the repository with `git pull --ff-only`, then `pipx reinstall research-idea`. For this release, `research-idea --version` should show `0.5.0`.

## v0.4.0 · 2026-10-25

### Discuss the problem before forming the idea

- The first stage maps major approaches around the background goal, analyzes several important problems separately, and compares their value and priority.
- Explains what existing approaches solve when working normally, then derives possible remaining or newly introduced difficulties, motivation, and a core idea.
- Interactive CLI pauses after forming problems for questions, corrections, or direction changes. `/continue` uses the revised problem to generate an idea and technical references.
- The second stage derives two design angles, including methods from other fields, and explains adaptation to the current problem. It does not expand experiment plans by default.

### Continue conversations and progress

- Saves complete dialogue and active requirements with original-message provenance. Revised requirements preserve old records while later work uses the updated version.
- Distinguishes lasting research requirements from temporary discussion requests. `/continue` ends the temporary pause and retains ongoing scope requirements.
- Saves problem versions and discussion state for restart. `/problems` shows the current problem; `/memory` shows active requirements.

### CLI, retrieval, and reading

- Launch directly with `research-idea`; adjust model, reasoning effort, date range, budget, and output directory inside the conversation.
- Displays stages, running status, paper links, and source locations. Results use `idea-TIMESTAMP` folders.
- Separates recent-work and technical-source date windows; venues use the latest available edition. Full-text retrieval supports alternative sources and title-based arXiv search.
- Improved quotation location, text decoding, and Windows temporary-directory cleanup; added model-call error messages and retries.

### Upgrade

If installed through pipx as described in the README, run from the repository:

```bash
git pull --ff-only
pipx reinstall research-idea
research-idea --version
```

For this release, the version command should print `0.4.0`. On Windows without pipx on PATH, replace `pipx` with `py -3 -m pipx`.
