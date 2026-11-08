# Workflow influences and interface references

**English** | [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue)](sources.zh-CN.md)

## ScientistTwo: diagnosis before feedback-driven revision (2026-11-08)

[ScientistTwo v1, §3.1–3.4 and Appendix C](https://arxiv.org/pdf/2609.19644v1) motivates examining how existing methods work and which conditions they rely on, then revising candidates using subsequent feedback. This adaptation uses the paper description, not its system source code. Here, complete problem arguments guide targeted reading, and new material updates only affected analyses. Existing evidence and reasoned conjectures can both motivate candidates. Experiment execution, performance-based acceptance, fixed novelty scores, and repeated automated reviews were not ported. Literature and discussion feedback are not experimental validation.

## K-Dense scientific-agent-skills: synthesis, ideation, and discussion

These working methods informed state handoffs and recovery in the existing controller, without adding a framework dependency:

- [scientific-brainstorming](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-brainstorming/SKILL.md) and [facilitation_workflows](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-brainstorming/references/facilitation_workflows.md): separate generation from selection, reconsider after new material, and retain merge/revision reasons. Implemented as independent problem analysis, one `reconsider_problems` step, and before/after versions.
- [hypothesis-generation](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/hypothesis-generation/SKILL.md): distinguish observations from explanations and compare possible causes. Implemented as `explanation_comparison`, passed to selection together with existing responses and research significance.
- [literature_search_strategies](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/hypothesis-generation/references/literature_search_strategies.md): trace citations to representative originals. Implemented through title provenance, retrieval checks, and title search when needed, sharing the existing follow-up budget.
- [literature-review core_workflow](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/literature-review/references/core_workflow.md): synthesize research around themes. Implemented through cross-paper premises, progress, changing conditions, and possible consequences, rather than turning each abstract directly into a local improvement.

The motivation skill loads separate guidance for synthesis, cause comparison, reconsideration, discussion, and framing. Discussion reasoning and user decisions persist separately. Delivery remains problems and motivation, without score-based elimination, experiment registration, or extra approval stages.

> The current workflow uses literature reading and analysis to develop research questions and motivations. This page retains historical design references; early technical-design entries describe historical implementations no longer executed by the main workflow. Discussion and memory sources appear in the v0.5.0 section below; interaction and memory updates are in the [Changelog](../CHANGELOG.md).


The controller, storage, adapters, eight built-in skills, and tests were independently implemented for this project. No source code from the projects below was copied or bundled. They inform workflow design and do not establish this project's research effectiveness.

- [ARIS / Auto-Research-In-Sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep): research decomposition, iteration, and state persistence.
- [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-creator/SKILL.md): generation followed by verification, candidate pilots, and interpretation of positive, negative, and ambiguous outcomes.
- [ARIS research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-refine/SKILL.md): problem anchoring, implementation specifications, and avoiding unnecessary modules.
- [ARIS experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/experiment-bridge/SKILL.md): checking implementation against plans, sanity checks, and result collection.
- [Karpathy autoresearch program.md](https://github.com/karpathy/autoresearch/blob/master/program.md): fixed evaluation, runtime budgets, and experiment/code version records.
- [CCFA Skills](https://github.com/mikubaka88/CCFA-Skills): problem–mechanism–evidence relationships, closest-work comparison, and boundaries between experiments and claims.

Research-idea adopted the parts supporting ideation: preserve the original question and hypotheses with candidates; record each revision, review, and unresolved premise; explain information sources and causal rationale around key assumptions; and keep technical choices in service of the core idea. Negative comments or missing material do not automatically eliminate a direction. Training, experiment execution, and paper-writing loops from these frameworks were not integrated.

Records include the original problem anchor, prior revision requests, field-level changes, new evidence, and unresolved objections. Revision stops when the key content and evidence repeat exactly. `max_rounds` and call budgets still bound iteration; the program cannot automatically determine whether two versions represent semantic research progress.

Interface references:

- [Codex non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat/create)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)
- [OpenAlex API](https://developers.openalex.org/)
- [OpenAlex authentication](https://help.openalex.org/api/authentication/): an environment-variable key can be sent in a Bearer header rather than a query URL.
- [OpenAlex filtering](https://help.openalex.org/api/filtering/) / [publication sources](https://help.openalex.org/data/sources/): filter by publication-source IDs instead of inferring venues from paper titles.
- [OpenReview accepted-note retrieval](https://docs.openreview.net/how-to-guides/data-retrieval-and-modification/how-to-get-all-notes-for-submissions-reviews-rebuttals-etc) / [API v2](https://docs.openreview.net/reference/api-v2/openapi-definition): COLM uses accepted `content.venueid`, retaining years and bounded pagination coverage.
- [COLM 2026](https://colm.cc/Conferences/2026/CallForPapers): official conference and OpenReview entry points.
- [ACL Anthology metadata example](https://aclanthology.org/2025.naacl-long.1/): relationships among publication sources, the full NAACL name, DOI, and PDF.
- [CCF AI directory](https://www.ccf.org.cn/Academic_Evaluation/AI/): defaults use the seventh edition, CCF 2026. ICLR is A and IJCAI is B; the 2022 preset remains for compatibility only.

Backends use interfaces checked against their documentation. On 2026-10-23, live Codex CLI calls with `gpt-6.1-sol` checked structured output and reconnection recovery. Live Claude/API account compatibility still requires verification. Any future copying of third-party code requires a separate license check, pinned version, and required notices.

- [Codex local skills](https://developers.openai.com/codex/skills): local SKILL.md format and path conventions. This CLI explicitly loads and assigns guidance by stage; it does not claim to reproduce every native plugin mechanism.

## OpenResearch: local Codex and skill integration

The following implementations in [alphaXiv/OpenResearch，commit fe36f7424855d7218e64812c5fec6f7db955586f](https://github.com/alphaXiv/OpenResearch/tree/fe36f7424855d7218e64812c5fec6f7db955586f) were examined on 2026-10-23:

- [`src/local/harness/codex.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/local/harness/codex.rs): newer versions primarily use local `codex app-server`, retaining a legacy `codex exec` path. Detection of the configured provider and authentication type does not require ChatGPT login. Native skills target the user's `.agents/skills/orx/SKILL.md`; session skills also use `.agents/skills`.
- [`src/local/native_store.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/local/native_store.rs): recognizes an existing `CODEX_HOME` and prepares links to existing authentication, configuration, plugins, and skills for isolated sessions. This describes source-code behavior; this project did not read user credentials.
- [`src/commands/install_skills.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/commands/install_skills.rs) and [`src/local/user_skills.rs`](https://github.com/alphaXiv/OpenResearch/blob/fe36f7424855d7218e64812c5fec6f7db955586f/src/local/user_skills.rs): install module skills and discover/mirror skills from local coding-agent and plugin directories.

This project adopts the division of responsibility: the local model client handles authentication, the controller handles research, and built-in modules can combine with user skills. It currently invokes `codex exec` per task and inherits the existing login environment without creating or copying authentication files. Skills are explicitly selected and their Markdown contents frozen per stage. It does not reproduce OpenResearch's complete native skills, plugin mirroring, or interactive app-server sessions. Loading guidance text is not execution of skill scripts.

Account usage follows [Codex authentication](https://developers.openai.com/codex/auth) and [non-interactive mode](https://developers.openai.com/codex/non-interactive-mode): `codex exec` normally reuses saved CLI authentication; ChatGPT and API-key logins have different billing paths. Users should verify their actual local login and environment. This program does not query remaining quota.


## Paper-analysis framework

The installed `nature-paper-card` informed source scope, reading coverage, module necessity, and experiment-to-claim evidence chains. Research-idea independently implements bounded nine-dimension cards and targeted follow-up reading. It does not bundle that skill's text or require a full-length Paper Card. Analysis supports the idea's value, differences, and initial validation path.

## Literature retrieval in automated research systems

Pinned source versions were examined on 2026-10-23. The ideas were independently implemented without copying third-party code:

| System and source | Observed behavior | Adopted here |
| --- | --- | --- |
| [AutoResearchClaw，be4ba47](https://github.com/aiming-lab/AutoResearchClaw/blob/be4ba4755bf1b52220f25e13b2293b5956590070/researchclaw/literature/search.py) | Combines OpenAlex, Semantic Scholar, and arXiv; passes a minimum year; deduplicates and sorts by citations and year. The main entry point does not uniformly enforce CS/venue scope. | Multi-source merging and deduplication; this project keeps query relevance and date filters rather than citation-count priority. |
| [ARIS research-lit，23745b6](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/research-lit/SKILL.md) | Guidance prioritizes the last two years with classic-work exceptions; the example arXiv helper call does not directly pass dates. | Recent-work priority and explicit classics, with dates implemented as program parameters. |
| [AI-Scientist，1de1dbc](https://github.com/SakanaAI/AI-Scientist/blob/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb/ai_scientist/generate_ideas.py) | Requests title, year, venue, abstract, and other metadata; that entry point's S2 request has no date or subject filter. | Structured metadata, plus server-side filters and checks on returned records. |
| [Karpathy autoresearch，228791f](https://github.com/karpathy/autoresearch/blob/228791fb499afffb54b46200aca536f79142f117/program.md) | Specifies fixed training, evaluation, and experiment loops; that file has no literature-search workflow. | The experiment-budget concept, not a literature-search implementation. |

Reading source code does not establish these systems' overall research quality. Retrieval recall, conference coverage, full-text reading, and actual idea quality still need evaluation here.


## Ideation and paper-selection improvements (2026-10-23)

The following pinned versions were read as design references; their skills were not executed and their code was not copied. The focus was problems and motivation rather than more roles or longer output.

| Reference | Examined mechanism | Implementation in this iteration |
| --- | --- | --- |
| [IdeaScientist roles，82a98a0](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/harness/roles.py) and [gap rubric](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/rewards/gap_finder/rubric.py) | Same-problem neighbors identify specific gaps; methods from other problems support transfer. Reading summaries form role interfaces; gap value and evidence are examined individually. | Problem diagnosis precedes method combination, with concrete failure conditions, the strongest existing alternative, and consequences; evidence cards are reused across stages. No RL training or outcome-masked corpus was ported. |
| [ResearchStudio IdeaSpark，063f100](https://github.com/microsoft/ResearchStudio/blob/063f10088af49909e1a4a7ea8d29efe19633f34e/ResearchStudio-Idea/skills/idea_spark/SKILL.md) | Ideate, check prior work and implementation coherence, revise, and recheck; independent simple baselines; review does not change resource limits. | Motivation-first candidate reconsideration and necessity checks; reports show problem and method first with audit details folded. Text review is not described as execution of its formula/implementation checks. |
| [Supervisor-Skills idea-evaluator，a20d76e](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/SKILL.md) and [search strategy](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/deep-research/references/search-strategy.md) | Assess value, resources, and methods by research paradigm and stage; use different keyword perspectives and clues in unselected material. | Retain the metadata pool and selection reasons; unselected material is not treated as nonexistent. Examine problem value and causes rather than merely table completeness. |
| [ARIS research-lit，23745b6](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/research-lit/SKILL.md) | Multiple sources, recent and classic work, and new queries for specific gaps. | Dynamic 12/6-month windows, candidate-specific searches, and retained older neighbors; continued use of gpt-6.1-sol without silently introducing other models. |

## Two-round ideation and technical exploration (2026-10-24)

Further mechanisms were checked in the pinned code and skill texts above and implemented for this project's then-current two-round goals. References informed design, not paper evidence or direct third-party skill execution.

| Reference mechanism | Implementation here |
| --- | --- |
| IdeaScientist's gap_finder distinguishes problem gaps, innovator seeks transferable mechanisms in other subfields, and reader follows explicit questions and reuses answered ones. | First-round `positioning` compares motivation and contributions during ideation. Second-round technical queries can leave the original application field; `design_transfer` records shared structure, original conditions, and adaptation. Evidence is reused and reading follows specific gaps. |
| ResearchStudio IdeaSpark separates concepts from technical elaboration and requires independently explainable simple baselines. | The first round states value, basic intervention, and a feasible path; the second offers reference routes, necessity, and simple alternatives, without copying additional review gates. |
| Supervisor-Skills assesses contribution by stage and value type, allowing reasoned but untested mechanisms to proceed to experiments. | Problem value and method necessity form one argument. Efficiency gains explain the constraint removed; cross-field transfer explains added capability or understanding. No fixed-score elimination was introduced. |
| ARIS research-lit reuses knowledge, organizes method clues, and explains a paper's relation to the current question. | Technical reading informs design decisions; final `design_decisions` records why a technique is adopted or adapted. Unselected techniques do not automatically become modules. |

These behaviors use this project's stage routing, structured outputs, caching, and regression tests; external training or experiment-execution workflows were not ported.

### Mapping ideation and technical-design references to code

| Pinned reference | Implementation and behavior | Verification |
| --- | --- | --- |
| [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/idea-creator/SKILL.md): ideation perspectives and core mechanisms | `map/propose` in [idea_instructions.py](../src/research_idea/idea_instructions.py) uses these perspectives as literature clues, organizing them as an unresolved important problem or a new problem exposed by existing methods. Motivation and ideas follow root causes; known motivation/contribution comparisons occur when the idea is proposed, as requested. | [test_idea_workflow.py](../tests/test_idea_workflow.py): first-round closest-work comparisons and a basic implementation path, while allowing testable hypotheses with sparse material. |
| [IdeaScientist roles](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/harness/roles.py): `reader/gap_finder/innovator` | `plan_search/prepare_design/focus_sources` in [controller.py](../src/research_idea/controller.py) and [build-mechanism skill](../src/research_idea/builtin_skills/research-idea-build-mechanism/SKILL.md) support question-driven reading, reused evidence, source-to-target mappings, conditions, and simple alternatives, then choose reference routes from `design_transfers`. | [test_technical_design.py](../tests/test_technical_design.py): stage order, targeted reading, source ownership, date windows, and download recovery. |
| [ARIS experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/experiment-bridge/SKILL.md): sanity → baseline → main | Examine key premises and simple alternatives first. Currently [design-falsification skill](../src/research_idea/builtin_skills/research-idea-design-falsification/SKILL.md) compares core explanations during review only. Experiment planning is no longer the default, as requested; execution was not integrated. | Built-in skill routing and schema tests; [test_idea_workflow.py](../tests/test_idea_workflow.py) verifies complete delivery without an experiment plan. |
| CORAL [reflect](https://github.com/Human-Agent-Society/CORAL/blob/0123dfb939b35228cf2c1fde224cd0561e727408/coral/hub/prompts/reflect.md) / [consolidate](https://github.com/Human-Agent-Society/CORAL/blob/0123dfb939b35228cf2c1fde224cd0561e727408/coral/hub/prompts/consolidate.md) | Design discussion in [controller.py](../src/research_idea/controller.py) carries previous comments, actual version changes, and the designer's response. [prompts.py](../src/research_idea/prompts.py) requires repeated criticism to explain why the earlier response remains insufficient and preserves justified choices. Shared records and reflection are adopted; literature and design feedback are not experimental scores. | [test_idea_workflow.py](../tests/test_idea_workflow.py): subsequent review receives the correct prior comments, change records, and corresponding responses. |

The default remains the user's configured backend, model, and total budget. References do not start extra models, automatic experiments, or long-running loops.

### Deriving problems from literature and assessing contribution overlap

On 2026-10-24, the following original implementations further informed exploration, independent analysis, comparison, and ideation:

| Reference | Use in this project |
| --- | --- |
| [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/idea-creator/SKILL.md): structural gaps and varied ideation perspectives | `explore_problems` opens distinct questions; `deepen_problem` derives causes, problems, and value from existing responses; `map` selects before `propose` develops ideas. Fixed candidate counts, multiple-model calls, and experiment execution were not copied. |
| [ARIS novelty-check](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/novelty-check/SKILL.md): adjacent research versus coverage of a specific result | Comparisons identify the claim actually covered. Known components may reveal new interactions or findings; the existence of each component does not establish duplication of the overall contribution. |
| [Supervisor-Skills paradigm-shift probe](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/references/paradigm-shift-probe.md): hidden assumptions and problem significance | Explain value through insight and changes in important capabilities or understanding, without fixed scores, verdict labels, or career restrictions. |
| [research-idea-explorer ideation schema](https://github.com/jameslemon2002/research-idea-explorer/blob/14232d97213b4c21127342ee1f429a4d2a77e158/skills/research-idea-explorer/references/schema.md) and [generation flow](https://github.com/jameslemon2002/research-idea-explorer/blob/14232d97213b4c21127342ee1f429a4d2a77e158/research_idea_explorer/engine.py) | Organize ideation around unexplained problems, claims, distinguishing relationships, and significance; preserve sources and selection links. Their term-similarity, retrieval-proximity, and crowdedness heuristics are not scientific overlap criteria here. |

These references help design reasoning, not prove scientific novelty. Regression tests check handoffs, selection links, valid sources, recovery, and reports. Actual outputs require separate examination of significance, insight, and contribution arguments.

### Deriving background, problems, and motivation

The following specific mechanisms in pinned versions were examined on 2026-10-25. Only reasoning approaches were adopted; third-party skills were not executed or copied.

| Reference and source behavior | Adopted reasoning |
| --- | --- |
| ARIS [idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/idea-creator/SKILL.md) seeks structural problems in shared assumptions, conflicting results, and extended conditions. [research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/23745b69a14880b5716d1773e5d20f5f1e6ab1d6/skills/research-refine/SKILL.md) preserves the original problem, examines bottlenecks and why simple patches fail, then seeks minimal intervention; it permits rejecting feedback that causes drift or unnecessary modules. | Infer meaningful conditions and possible difficulties from existing mechanisms, establish the research need before choosing operations, and keep revisions directed at the same goal while allowing justified reframing. |
| IdeaScientist [gap_finder](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/harness/roles.py#L139) organizes progress by mechanism and explains why the closest approach leaves difficulty before handing off to innovator. [rubric](https://github.com/jiarui-liu/IdeaScientist/blob/82a98a08772eab08d11fd097445afa4a8eaaa5b3/ideascientist/rewards/gap_finder/rubric.py#L180) asks who is impeded and what capability or understanding a solution would provide. | Consider normal responses under the same conditions. “It does not use our operation” is not a remaining problem. Motivation explains why crossing the obstacle advances the background goal. |
| Supervisor-Skills [paradigm-shift probe](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/references/paradigm-shift-probe.md) examines hidden premises, development changes, and significance; [idea-evaluator](https://github.com/HKUSTDial/Supervisor-Skills/blob/a20d76ef3979b804d7dbf599d577826957e0a8a9/skills/idea-evaluator/SKILL.md) accepts ideas with a mechanism argument before measured results. | Allow reasonable literature-based conjectures, explaining conditions and derivations. Significance follows the effect on the original goal, without requiring completed experiments. |

The resulting workflow uses [idea_instructions.py](../src/research_idea/idea_instructions.py) and [motivation skill](../src/research_idea/builtin_skills/research-idea-motivation/SKILL.md). `deepen_problem` first explains how the strongest existing approach works normally under the same conditions and what it alleviates, then derives remaining or newly arising difficulties and their effect on the goal. `bottleneck_hypothesis` needs causal insight into non-obvious dependencies, assumptions, or interactions and why ordinary improvements do not naturally remove the obstacle, rather than renaming it. `map` compares value and insight before `propose` develops the idea and a basic feasible path. Problems arise as new difficulties caused by solving the original problem, or as new questions from the broader background that major approaches struggle to solve. Bold conjectures and inspiration from one paper are allowed; no common flaw, unique cause, or proof of field-wide impossibility is required.

Initial search builds `research_routes` around different causes and existing approaches to the original goal. Queries, actual retrieval, complementary selection, and reading share route links; about two-thirds of the then-current reading budget prioritized stage one. [research_context.py](../src/research_idea/research_context.py) creates an ideation copy limited to initial sources, excluding old candidate interpretations, ready-made improvements, and experiment suggestions while retaining methods, experiments, results, conditions, and quotations. Claim-audit doubts remain in full records. Ideation builds on existing progress instead of rejecting contributions to manufacture motivation; full records support stage two. Routes are not predetermined technical axes and need not fill paper quotas.

The controller preserves the original goal. `research_question` focuses it, and `scope_connection` explains why that focus matters. `map` compares search plans, actual route coverage, and independent arguments while retaining the full pool, route links, and `selected_problems` reasons. The controller constructs `argument_handoff` from selected fields: existing responses, causal insight, problem derivation, goal impact, and research need. Both initial and post-reading `propose` receive it; `selected_opportunity` preserves the problem and rationale later. New sources may revise understanding while distinguishing the scientific problem from implementation difficulties. This makes problem derivation precede solution ideation instead of taking one paper's suggestion directly as a candidate. It is this project's synthesis, adding no calls, scores, or review rounds, rather than a workflow uniformly prescribed by those frameworks.

This design does not fix the example's field, number of difficulties, or modules, and does not introduce those frameworks' scoring, extra reviews, or experiment execution. Stage two continued through [build-mechanism skill](../src/research_idea/builtin_skills/research-idea-build-mechanism/SKILL.md), deriving two technical questions and linking retrieval, transfer, and selection with `design_axes`; one technique could serve both. Tests check stage continuity and material handoffs; argumentative improvement must be assessed from outputs.

## Rating lists and conference-source checks

- [CCF 2026 directory copy](https://dengpingfan.github.io/papers/CCF-Recommend-2026.pdf): pages 57–58; [CCF official directory](https://www.ccf.org.cn/Academic_Evaluation/By_category/). The official page had browser verification, so ratings were checked against the directory text in this iteration.
- [Tsinghua-hosted TH-CPL document](https://numbda.cs.tsinghua.edu.cn/~yuwj/TH-CPL.pdf): adopted 2019-08-13; page 11 lists AI/pattern-recognition A venues. The 2019 document is not described as a 2026 edition.
- [ICORE2026 official database](https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=arank&page=1): the first two grade-sorted pages list 62 A* venues. Only the user-specified LLM/NLP/Agent subset is enabled by default.
- [CCFDDL](https://github.com/ccfddl/ccf-deadlines): CCF/CORE/THCPL filters, conference homepages, and dates provide a manual lookup entry point. Ratings follow the explicitly versioned original documents above.
- [OpenAlex error documentation](https://help.openalex.org/api/errors/): 429 may indicate rate or daily-quota limits; 403 must not be retried indefinitely. The observed 429 in this iteration had zero remaining quota and Retry-After over ten hours.
- [COLM 2026 official acceptance list](https://colm.cc/Conferences/2026/AcceptedPapers), [ICLR 2026 paper list](https://iclr.cc/virtual/2026/papers.html), [ACL 2026 long papers](https://aclanthology.org/2026.acl-long/), [PMLR directory](https://proceedings.mlr.press/), [NeurIPS 2025 main track](https://papers.nips.cc/paper_files/paper/2025/vol38-main-conference): public alternatives when index APIs are restricted. Only metadata actually supplied by the directories is recorded.

### Publication names for expanded venues (checked 2026-10-24)

- [ACM Multimedia official site](https://2026.acmmm.org/): ACM MM's full name is ACM International Conference on Multimedia.
- [The Web Conference official site](https://www2026.thewebconf.org/): WWW uses both The Web Conference and ACM Web Conference names.
- [VLDB Endowment](https://www.vldb.org/): VLDB research papers are reviewed through PVLDB; retrieval includes Proceedings of the VLDB Endowment, separately from The VLDB Journal.
- [SIGMOD 2026 research-paper information](https://2026.sigmod.org/calls_papers_sigmod_research.shtml): research papers appear in corresponding PACMMOD issues. [DBLP PACMMOD directory](https://dblp.org/db/journals/pacmmod/index.html) lists publication associations for both SIGMOD and PODS, so retrieval retains the actual series name.

This expansion updates scope, name matching, and public text sources. Added conferences use matched OpenAlex publication sources; it does not imply a separate official-directory adapter for every venue.
## Context organization references

- [IdeaScientist: separate paper-reading context](https://github.com/jiarui-liu/IdeaScientist/blob/main/ideascientist/harness/runner.py): full-text reading uses a separate context and input budget, returning focused summaries for later roles. Stage-specific materials informed this design; this project retains quotations and experimental results and uses its existing chunked reading.
- [ARIS: session recovery and Research Contract](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/docs/SESSION_RECOVERY_GUIDE_CN.md): compact project state and a focused current-idea document support resumption. Explicit research intent and persistent handoffs informed this project's SQLite and `research_frame`, without extra approvals or roles.


## Problem discussion and memory (2026-10-25)

After examining these implementations, this project added pauses, incremental notes, and version handoffs to its existing SQLite controller, without framework dependencies or copied code:

- [ARIS run_state.py](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/tools/run_state.py) and [resumable-runs](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/resumable-runs.md): persist stages and artifacts and resume from an explicit location. Stage recovery was adopted; pause confirmation comes from user `/continue`, without cross-model acceptance rules.
- [ARIS idea-creator research Wiki persistence](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-creator/SKILL.md): programmatically writes idea-to-paper/gap relationships and preserves existing results. Here the program saves problem versions, selection reasons, and message provenance instead of merely prompting the model to remember.
- [OpenHands condenser](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/context/condenser/README.md): separates append-only event logs from compact model-facing views. Here complete conversations remain stored while models receive active notes, recent dialogue, and original messages awaiting processing.
- [Mem0 prompts.py](https://github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py): user-message extraction and ADD/UPDATE/DELETE/NONE operations. Here source-message IDs support add/replace/remove; no update preserves notes, replacements retain history, and assistant suggestions are not user decisions.
- [LangGraph interrupts](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/interrupts.mdx): durable pauses resumed within the same conversation. Here discussion boundaries are explicit, and resumption does not repeat completed research stages.

These engineering mechanisms reduce forgetting and repeated execution; they do not prove correct conclusions or novel ideas.

### v0.5.0: more frequent discussion and cross-stage conversations

Further examination of ARIS and CORAL informed this division: preserve the complete original conversation, allow current research notes to be replaced or withdrawn, resume discussion stages independently, and select material relevant to each turn's question.

| Examined source behavior | Adopted design |
| --- | --- |
| ARIS [idea-discovery literature-scope discussion](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-discovery/SKILL.md#L237) requests confirmation of the literature map and scope when `AUTO_PROCEED=false`, adjusting queries after corrections; [candidate discussion](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-discovery/SKILL.md#L275) permits renewed ideation or a return to literature. | Discuss while directions and problems remain changeable. Corrections affect later material, problems, and selection rather than only producing a chat reply. |
| ARIS [run_state.py](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/tools/run_state.py) saves stage, artifacts, and recovery data; [research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-refine/SKILL.md#L58) saves stage, round, and session identifiers and resumes from stage documents. | Persist completed research material and current discussion separately; resume at the pause and allow explicit intent revision. |
| ARIS [research_wiki.py](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/tools/research_wiki.py#L225) builds bounded query material from brief, paper, and idea relationships; it is not a complete chat transcript. | Select context for this turn while retaining retrievable provenance, without sending all history each time. |
| CORAL [Codex adapter](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/agent/builtin/codex.py) retrieves session IDs from run records and resumes native conversations with `codex exec resume`; its default execution does not wait for user dialogue. | Adopt continuity while keeping Research-idea's own persistent research conversations, explicit discussion, and `/continue`. Native session resumption is not described as user discussion. |
| CORAL [steering.py](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/hub/steering.py) persists guidance and creation/application timestamps; [manager.py](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/agent/manager.py#L860) applies guidance on recovery. | Corrections need persistence, application, and stage ownership rather than reliance on recent-message memory. |
| CORAL [create-notes](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/template/skills/create-notes/SKILL.md) distinguishes original sources, research notes, and synthesized understanding, retaining replacement links and evidence; [checkpoint.py](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/hub/checkpoint.py) tracks shared-knowledge versions. | Separate original user wording, active requirements, and researcher inference; retain prior versions and sources when requirements change. |

The user-decision ledger in [conversation.py](../src/research_idea/conversation.py) is this project's own combined design. Only user messages can source notes; `add/replace/remove` retain replacement links. Temporary requirements belong to their originating stage and instance; `/continue` ends only the current discussion's temporary requirements. Lasting requirements stay active and originals remain unchanged. Model context includes source wording, recent discussion, and relevant earlier user messages; withdrawn requirements carry inactive records so old selections cannot become current decisions again. Earlier processed messages not distilled into notes remain retrievable. `/history [keyword]` lets users search original wording across the full history.

These sources informed discussion and context organization. At the inspected entry points, neither ARIS nor CORAL directly supplied the same replaceable/withdrawable decision ledger accepting only original user-message provenance. Research-idea copied neither codebase and does not depend on native backend sessions to remember research requirements.


### v0.7.0: preserve intent while improving the problem

The following public descriptions/skills informed organization without adding their dependencies, background services, or extra agent workflows:

- [ARIS research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-refine/SKILL.md) uses a Problem Anchor against drift; [idea-discovery](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-discovery/SKILL.md) distinguishes exploration from refinement. Here intent has original-message provenance and can be revised through discussion. User hypotheses are not fixed, and score-threshold loops are not adopted.
- [CORAL create-notes](https://github.com/Human-Agent-Society/CORAL/blob/main/coral/template/skills/create-notes/SKILL.md) separates focus, synthesis, and evidence notes and retains replacement/refutation links. Here user goals, concern relationships, and literature-driven judgment changes are stored separately with before/after versions, without the full team scheduler.
- [Supervisor-Skills tech-paper-template](https://github.com/HKUSTDial/Supervisor-Skills/blob/main/skills/tech-paper-template/SKILL.md) and [intro-drafter](https://github.com/HKUSTDial/Supervisor-Skills/blob/main/skills/intro-drafter/SKILL.md) emphasize correspondence across research arguments. Here they inform handoffs among background goals, existing responses, difficulty relationships, motivation, and propositions, without restoring technical or experimental sections.
- [IdeaScientist README](https://github.com/jiarui-liu/IdeaScientist) provides a stage/role comparison. This iteration did not claim to inspect its internal implementation or equate one paper's gap with the user's research goal.

Implementation: `research_intent.py` stores goals, concerns, provenance, versions, and formulations; `question_workflow.py` interprets input before search and carries full intent into delivery; `problem_discovery.py` retains related problems during analysis; `controller.py` makes synthesis/reframing the current problem while keeping originals; `problem_dialogue.py` atomically commits corrections; task-specific motivation references explain state use. New workflow tests cover connected difficulties, independent directions, open topics, revised hypotheses, and recovery after discussion. Program checks establish structural and provenance completeness; scientific judgment remains with the model and researcher in discussion.

### Discussion guidance and behavioral evaluation (2026-11-01)

References: [Intuit to Idea core skill](https://github.com/ShawnL1N/intuit-to-idea/blob/main/SKILL.md), [mechanism-comparison guide](https://github.com/ShawnL1N/intuit-to-idea/blob/main/references/novelty-check.md), and [behavioral scenarios](https://github.com/ShawnL1N/intuit-to-idea/blob/main/evals/scenarios.md). Adopt one consequential follow-up at a time, actual changes in interpretation after corrections, and preservation of value when narrowing scope. That repository supplies skills and testing guidance, not an independent retrieval/memory runtime or completed model-effectiveness evaluation.

This project continues actively discovering problems from literature and asks follow-ups only when useful during existing discussion stages. Users need not supply the innovation; technical and experiment stages are not restored. `discussion_focus.py` stores the previous follow-up separately from user decisions with a size limit; unanswered questions do not block `/continue`. Scope changes reuse existing version/reason records. Live multi-turn behavior and program-state tests are reported separately.


## 2026-11-03: broad reading and persistent literature context

References include [ARIS research-lit](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-lit/SKILL.md) for overview-first reading, on-demand sections, and thematic synthesis; [Supervisor-Skills deep-research](https://github.com/HKUSTDial/Supervisor-Skills/blob/main/skills/deep-research/SKILL.md) for multiple perspectives; [synthesis-framework](https://github.com/HKUSTDial/Supervisor-Skills/blob/main/skills/deep-research/references/synthesis-framework.md) for organizing by problem and method family; and [IdeaScientist roles](https://github.com/jiarui-liu/IdeaScientist/blob/main/ideascientist/harness/roles.py) for explicit reading questions and cumulative notes.

These principles informed independently implemented batch caches, original abstract storage, approach overviews, discussion references, and promotion of sources into body reading. No source code, training process, or scoring gate was copied. The 40/8/16/6 limits are initial engineering choices here, not externally established optimal counts. Body reading serves specific judgments; similar titles do not eliminate problems.
