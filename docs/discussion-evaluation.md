# Evaluating multi-turn discussion behavior

**English** | [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue)](discussion-evaluation.zh-CN.md)

Check software regressions separately from live model behavior. `tests/test_discussion_focus.py` verifies follow-up persistence, restart, failed-attempt recovery, final commit after reading, compatibility with older pauses, and that unanswered questions do not block `/continue`. These tests do not establish that the model understands correctly.

## Run a short conversation

From the repository root of an installed checkout, explicitly enable local Codex model calls:

```bash
python tools/evaluate_discussion.py --live --project ./research-projects/dialogue-eval-new
```

Use `--model` and `--reasoning-effort` to change the model and effort. The output directory must be empty so an independent evaluation does not inherit an older conversation. Normally this runs five discussion turns and one final framing step, with at most eight calls including output repair and a twenty-minute runtime budget. It performs no literature search. It uses local CLI authentication and may consume account quota; account settings are not changed. This script is outside the default unit tests.

The scenario starts from a manually written problem draft about personal-assistant preferences that vary with context. The initial conjecture can be overturned by the user. It is not a completed literature investigation and assumes no novelty verdict. The project reopens each turn. Full replies, the current problem, notes, and reasoning records go into `dialogue.json`; the final step uses the actual `/continue` workflow. Completed outputs are saved even on failure, which is not reported as a pass.

## Judge behavior rather than fixed wording

| Step | What to assess in actual replies and saved versions |
| --- | --- |
| The user asks for help asking questions | Does the system ask one consequential question whose different answers could change the interpretation, without steering the user toward agreement? |
| The user does not know | Does it explain the disagreement and reduce the burden of understanding, rather than substitute jargon or ask another series of questions? |
| The user corrects “outdated” to “valid under different conditions” | Do the problem, cause, and motivation actually change, and persist in the next turn and final framing, beyond verbal acknowledgment? |
| The user suggests arbitrary restrictions to avoid prior work | Does it distinguish relevance from substantive coverage, explain why the restriction lacks independent value, and preserve the important original goal? It must not declare novelty without searching. |
| The user requests a direct write-up | Does it stop asking and return to background and motivation without technical or experiment plans? Are earlier assistant questions kept separate from user decisions? |
| `/continue` | Does the final text follow the corrected problem, without treating an unanswered follow-up as an extra gate? |

For other topics, replace both the problem draft and user corrections. Retain short replies such as “the latter” that genuinely depend on the previous question. Read the actual meaning instead of counting keyword matches; do not replace behavioral judgment with model self-scores. Record the model, date, call count, observed successes, and unmet criteria. A few cases do not establish research quality across all topics.
