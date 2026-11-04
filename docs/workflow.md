# Research problem and motivation workflow · v1.0.0

**English** | [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue)](workflow.zh-CN.md)

The product has one focus: derive meaningful, insightful research problems from literature; explain the background, existing approaches, problem, and motivation; and summarize the research idea in one sentence. The workflow ends there, without generating solutions, technical routes, experiment plans, or papers.

## Understand what the user is trying to advance

Before searching, one model call distinguishes open exploration, refinement of an existing idea, and assessment of a specific problem. It saves the user's goal, hypotheses to examine, core concerns, and original-message provenance, and explains whether the concerns are alternatives, joint requirements, dependencies, or possible consequences of a shared cause. The user can correct this directly in discussion without an extra confirmation step.

Initial searches and later targeted reading consider both the individual concerns and their relationships: does the closest work address these needs together, and does success on one depend on another condition? They share the existing query, selection, and call budgets. Related problems remain available during deeper analysis; reading them separately does not predetermine that only one can survive.

## Understand existing progress in the broader context

Input may be a research direction, an existing idea, or papers; resources and scope follow what the user provides. Search across different major approaches and possible causes, then use titles and abstracts to select complementary full-text readings. Surveys, systematic comparisons, introductions, and related-work sections establish the field; methods and results explain what an approach actually achieves.

Search supports CS arXiv, relevant conferences, and local materials. Rolling windows distinguish background/existing approaches from recent problem and contribution comparisons. Conferences use the latest available edition, preferring newer editions when relevance is comparable. Similar titles do not establish that a specific problem is solved; missing sources do not prove novelty.

`max_papers` controls initial full-text slots. Before the first discussion, `orientation` gives each selected paper one background reading, prioritizing introduction, related work, and conclusion excerpts with a total length of at most `min(source_chars, 12000)`. If headings are unrecognized, it reads the opening passage and records that selection. Citations are validated against source locations; quotations cannot splice separate windows. This stage does not automatically produce complete paper cards, audits, or repeated follow-up reading. A paper's future-work section is a reference, not a substitute for discovering problems from the user's broader goal.

Search planning decomposes reading questions into short concepts and synonyms rather than requiring every word of a long conjecture to match. If a long natural-language arXiv query returns too little, it may expand keywords once within the same search timeout while preserving CS and date restrictions. Expanded results still undergo keyword association and model relevance screening. Original and expanded queries and coverage are saved; explicit Boolean expressions and complete titles are not expanded.

## First discussion: which directions deserve deeper analysis?

`explore_problems` first summarizes effective progress by the main approaches. A broad direction normally explores three, at most four, problems with different causes. A coherent existing idea can instead be examined through different explanations and interactions. A clearly focused user request does not require filling a quota. At this point the system explains why the problems matter without preselecting techniques.

`cross_paper_synthesis` saves connections across papers: major approaches, shared premises, progress, changing conditions, possible consequences, and source references. This enters each direction's analysis, comparison, and final framing. It can remain empty when no real connection exists; there is no requirement to invent a common weakness.

The interactive CLI saves a discussion version with `kind=direction` and pauses. Users can correct the background, add concerns, adjust scope, or merge directions. Ordinary messages discuss; `/continue` advances. `/run` cannot bypass a saved pause.

## Analyze different problems before comparing their research value

For each direction, first decide whether the current material is sufficient. When an information gap affects the judgment, `plan_problem_reading` proposes a specific reading question. The controller searches, selects, and reads at most two supplementary sources. Exhausting initial reading slots does not block this purposeful follow-up, but all operations share the same call and runtime budgets. Not every direction must search again.

Targeted reading extracts evidence and, in the same call, creates a transferable understanding of the paper: its problem, core causal explanation, sources of inputs and key feedback, actual processing, and judgments its outputs support. It explains how the paper changes, supports, or redefines the current difficulty, feeding later analysis and synthesis. Author claims, accounts of prior work, our inferences, and conjectures stay distinct. Papers need not each have a defect. When helpful, source examples explain the process; illustrations are not treated as real results, nor does a small example automatically define the research scope.

Methods and results absent from orientation are read here as needed. Selection receives all reading questions together, considering both the closest existing response and possible new difficulties. Each paper is read for its own question so both slots are not spent only seeking support for the conjecture.

Planning also receives related-work and bibliography excerpts from the current research papers, totaling at most 12,000 characters. `citation_targets` selects representative originals only when a complete title and source location are available. The program checks title provenance, the paper library, and retrieved records; existing records are reused, otherwise titles are searched. Tracing uses the `lineage` time scope and respects explicit user dates. It shares the two reading slots with ordinary requests. Resolved requests are saved before execution, so an interrupted download or read does not change the request or repeat selection because new papers have entered storage.

After targeted reading, `reconsider_problems` performs one cacheable reconsideration: retain, reword, merge, split, or replace directions, recording old/new IDs, evidence, and reasons. It is skipped when there was no actual reading. No automatic search loop or acceptance stage is added. New directions continue with available material and can be supplemented in later discussion.

Acquire the sources needed by all directions before independently running `deepen_problem`, avoiding an advantage for later directions merely because more material has accumulated. The analysis asks what the major methods solve when functioning normally, how a remaining difficulty arises, what causes it, and why it still obstructs the original goal. A new problem can be a reasonable conjecture; explain the inference without presenting it as an existing experimental result.

`explanation_comparison` compares possible causes of the same difficulty, the strongest existing responses, remaining obstacles, and implications for the research's necessity. It does not require a fixed number of explanations. The problem-origin category can change with understanding; `revision_reason` records why. Original directions and deeper analyses are both retained. `map` receives every direction's argument and cause comparison; final framing receives the selected argument and cross-paper synthesis.

Discussion `reasoning_notes` are stored separately from user requirements. User objections cite that turn's wording; assistant revisions and open questions are attributed to analysis. Replaced records preserve earlier versions, message provenance, and conditions for reconsideration. Successful discussion commits these records with the current version; interruptions leave no partial memory update. Active records follow the topic into later ideation instead of being displaced by recent-message limits. `/memory` shows active records; complete history and report JSON preserve versions.

The built-in motivation skill has a short shared description and task-selected reference files. Their contents enter cache fingerprints, so changes to relevant guidance recompute the corresponding task. Background orientation loads evidence-reading guidance without prematurely loading claim auditing or method comparison. Explicitly selected external guidance retains its existing phase configuration.

Problems arise through only two routes:

1. An important need remains inadequately met by the main approaches. Explain why the closest responses still cannot cross the key obstacle.
2. Existing methods effectively solve their original problem but expose a new difficulty in use or development. Explain how it arises, what it affects, and why the original approach does not naturally handle it.

Acknowledge existing contributions. Do not manufacture motivation by doubting a paper's contribution, pointing to a missing ablation, or renaming concepts. Consider the state after the original method has adapted normally; do not keep treating an already eliminated difficulty as unsolved.

“Failure occurs without the key capability” merely repeats the difficulty. Explain how ordinary use produces the obstacle and why existing information acquisition, feedback, and updates may leave it in place, then derive the need for research. This is an argumentative requirement, not an extra experiment or pass/fail gate.

`map` receives each problem's full argument, compares its value and insight, and explains priority. Unselected directions retain their original analyses rather than being rewritten as weaker alternatives. Selection uses neither a score threshold nor ease of technical implementation as its rationale.

`discussion_focus` contains zero or one consequential follow-up question, saved in the current checkpoint with assistant attribution and this turn's message provenance. The question appears in the CLI reply and full transcript; `previous_discussion_focus` carries it into the next turn. A new question replaces the old one; no question clears it. It is not a user requirement, does not gate `/continue`, and is cleared on confirmation rather than carried into the next stage. Failed replies do not commit it; the final post-reading reply commits it together with the rest. Only one question of up to 400 characters and a purpose of up to 300 characters are retained, without accumulating context.

Explanations of narrowing or redirecting a problem reuse `reasoning_updates`, `changes.reason`, `revision_reason`, and selection rationale. They identify the closest work's actual coverage and the important difficulty that remains, instead of repeatedly adding special conditions to manufacture novelty or adding a fixed review stage.

## Second discussion: is the problem clear, and why prioritize it?

Save a version with `kind=problem` and pause. Users can ask further questions, correct reasoning, change emphasis, or introduce a new problem. A specific information gap may trigger new search or rereading: at most two reading questions and two sources per turn, followed by a reply and an updated research judgment. Without a necessary gap, discuss directly.

Source work and model replies are saved separately. Resending the same message after failure reuses its ID and selected material to finish the incomplete work. New corrections remain in the original conversation. `/continue` cannot skip an unprocessed message. Asking whether something is reasonable is not recorded as user approval.

`/problems` shows a concise current version; `/problems detail` shows the full derivation. Paragraphs use paper titles and links; `/evidence` exposes source pages and lines.

## Frame the final problem and motivation

After `/continue`, `frame_question` uses the discussed problem, priority rationale, and active user notes to write:

- **Background:** the real need in the broader research area.
- **Existing approaches:** what the main families of methods do and have achieved, supported by representative papers.
- **Problem:** how difficulties can still arise after that progress, why, and how they affect the original goal.
- **Motivation:** why this deserves priority and what important understanding it could provide.
- **One-sentence research idea:** the question and new understanding to pursue, without specifying a solution.

The text is detailed and plain, with each section building on the previous one. Avoid jargon piles, local patches, generic trade-offs, and defensive disclaimers. The final report presents this argument and its paper evidence. Ordinary follow-up after completion returns to the current problem discussion; another `/continue` updates the report.

## Original dialogue, active requirements, and research versions

SQLite stores:

| Record | Purpose |
| --- | --- |
| `chat_messages` | Complete original wording, stable message IDs, timestamps, and discussion stage |
| `conversation_memory` | Active requirements with user-message provenance; replacement and withdrawal links for older requirements |
| `last_turn_changes` | Actual changes in the latest successful discussion, retained parts, current focus, and message provenance |
| `problem_checkpoint` / `discussion_checkpoints` | Current direction/problem version, revisions, and historical stages |
| `question_cycle` / `question_brief_provenance` | Current execution stage, confirmed version, and provenance for final framing |

Each model input reads active requirements, their original wording, recent dialogue, and relevant earlier messages rather than including all history. `/history [keyword]` searches original dialogue; `/memory` shows active requirements. Originals remain stored; retrieving an old requirement does not reactivate it.

Automatic recall reserves priority for the top three matches to this turn's keywords, then alternates relevant user messages located through the current problem, latest assistant reply, and other direct matches, for at most six messages overall. Clues are separately attributed and each limited to 1,200 characters. Long-message excerpts also use those clues so retrieval does not cut off the correction itself. Assistant replies are clues, not provenance for user memory. Manual `/history keyword` searches only the supplied keywords.

After each successful reply, the program compares the committed before/after problem drafts, user notes, and reasoning to generate `[update]` turn-change output. It is saved with that turn's memory and research version and displayed only after commit; the assistant's wording does not determine whether a change occurred. Explanation-only turns retain the draft and explicitly show no modification. Actual updates show changes and current focus. `/memory` expands the latest full record, also retained in report JSON. These operations add no model calls.

Requirements have `turn`, `discussion`, or `research` scope. Turn requirements expire in the same transaction as a successful reply; `/continue` ends discussion-scoped requirements. Lasting research scope and explicit long-term preferences remain active. Local length and formatting requests have their lifetime corrected from the original wording instead of defaulting to permanent preferences. Expired items are marked `turn_expired` in context so history retrieval cannot revive them. Older misclassified presentation requests receive the same correction; original dialogue is unchanged. Closing the window or changing models preserves scope and provenance. Older stage requirements are first bound to their original stage to avoid entering a new discussion.

## Execution, recovery, and delivery

The interactive interface pauses twice. For new projects, batch `start/run/resume` automatically completes the same research-question workflow. Pauses and interaction mode established through an interactive session persist; batch commands cannot bypass them on the user's behalf.

Successful model tasks are cached by relevant inputs and backend configuration. Source or scope changes reopen direction discussion; completed reading remains reusable. Budget exhaustion, interruption, and model errors retain completed work. Research, discussion, output repair, and service retries share the budget; waiting for user input does not count as runtime.

Reports are Markdown and JSON in an `idea-TIMESTAMP` folder; `/output` changes its parent directory. Older technical proposals remain readable but are neither regenerated nor included in new reports.

## Form a coherent problem from different analyses

Comparison may select an independent problem, synthesize related difficulties, or reframe a problem based on the material. Explain their actual relationship, how each user concern enters the current problem, and the reason for focusing or revising. Progress can change a hypothesis without eliminating the goal. Do not isolate one difficulty by assuming another key difficulty is already solved.

Selection records and all independent analyses are saved together. The final proposition follows the original goal, current problem, core relationship, and discussion revisions rather than simply expanding a selected local case. The same two discussion pauses remain; `/memory` shows the current research intent. Final output remains background, existing approaches, problem, motivation, and research proposition.

## Abstract coverage and specific questions (2026-11-03)

The question workflow first runs `skim_papers`, covering at most 40 initial papers in batches of eight, then `synthesize_landscape` integrates major approaches and relationships. Records without abstracts remain title clues only. When the overview identifies a missing approach that could change the understanding, it may add at most two queries and 16 candidates within the total budget, then synthesize once more. There is no unbounded loop.

Supplementary queries distinguish recent `strategy` from foundational `lineage` and reuse existing dynamic date rules. Tracing representative originals in adjacent fields is not mechanically limited to one year; explicit user dates still take precedence.

`literature_landscape` stores original metadata, per-paper short notes, and the overview independently of the `papers` collection selected for body reading. `landscape_work` retains initial sources and completion status; model-task caching resumes each batch. `max_papers` bounds background body reading without reserving old technical-design slots. Papers not selected for body reading still inform discussion and citation resolution; explicit follow-up adds them to the body collection when needed.

`research_mode` follows `research_intent.mode`: explore compares important problems; refine/assess compares explanations and existing responses for a specific problem. Ordinary discussion still does not advance the stage. Context contains all compact notes and the overview, plus up to six original abstract excerpts selected for the current question. Complete abstracts and text citations are not truncated in storage.

Similar titles and names are retrieval clues, not overlap verdicts. Broad reading acknowledges author progress and permits reasonable new conjectures. Substantive coverage depends on goals, mechanisms, available information, conditions, and contributions. Existing targeted reading supplies decisive missing details. No new scientific score, approval step, or experiment-plan stage is introduced.

`coverage_basis` saves the goal and queries used to form the overview; ordinary feedback does not automatically rewrite it. Discussion also receives the current intent, allowing a new goal to be distinguished from old search coverage. Existing `research_requests` determine action: empty requests reuse material; `paper_ids` alone read existing sources; a `query` triggers search. The request's question explains the disagreement to resolve. Reading results return to the same discussion turn, and judgment changes are saved in existing `reasoning_updates` and discussion versions.
