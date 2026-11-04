# Local research workbench

**English** | [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue)](web-workbench.zh-CN.md)

Start the service once in a terminal, then use the browser for research:

```sh
research-idea web
```

The browser opens `http://127.0.0.1:8769/`. Keep the terminal running the service open. If the port is occupied, use `research-idea web --port 8770`. Add `--no-browser` to start without opening a browser. Run only one Web service per project root at a time.

## Getting started

1. Click **New research** in the sidebar. Enter a research direction, an initial idea, or a specific question.
2. Select the **model and reasoning effort** below the input, then send your message to discuss the research goal.
3. Once the goal is clear, click **Start literature research** above the input. The sidebar shows whether the system is searching, reading, or discussing.
4. Research pauses for **direction discussion**. Send feedback, questions, or corrections over as many turns as needed. When ready, click **Continue deeper analysis**.
5. After deeper analysis, research pauses for **problem discussion**. Discuss further, then click **Frame the research proposition** when ready.
6. Open **Research proposition** at the top to read the result, and click **Export Markdown** to download it. You can continue discussing and produce a revised version after delivery.

**Messages discuss and revise the current step; Continue advances the workflow.** If you have an unsent draft, send it and wait for the reply, or clear it before continuing. Research-brief attachments also enter the input first; they are not sent automatically.

Open the top-right **? User guide** at any time for these instructions and the location of each feature. No CLI commands are required. Control names below are English translations of the current Chinese interface labels.

## Where to find each feature

| What you want to do | Web control | How it works |
| --- | --- | --- |
| Change model or reasoning effort | Two dropdowns below the input | Saves automatically and affects subsequent calls. |
| Refresh models or check sign-in method | Top-right Settings → Refresh models / Sign-in method | Reads the local Codex setup; does not show keys or query your balance. |
| Change call and time limits | Settings, or Adjust in the sidebar | Enter time in minutes. Raising limits preserves usage already recorded. |
| Change paper dates and venues | Settings → Literature scope and reading | Use rolling months or fixed dates; venues can independently use their latest public edition. |
| Adjust paper and problem counts | Full-text reading limit in Settings; Literature scope and reading | Broad reading covers up to 40 papers initially; full text is read as needed. All stages share the model-call budget. |
| Specify hardware, data, or time constraints | Settings → Resources and research constraints | Leave unknown conditions blank. |
| Add local papers | **＋** beside the input → Paper materials | Supports PDF, TXT, Markdown, and paper JSON. Imported materials become available to subsequent research. |
| Provide a long research brief | **＋** → Research brief | UTF-8 TXT/Markdown enters the input for review before sending. |
| Inspect search, skills, and analysis | Process records in the conversation → Expand / Open full details | Viewing saved records does not call the model again. |
| Check papers and sources | Literature at the top → Abstract / Broad-reading notes / Source evidence | Shows source links, pages, and quotations; excerpts are available when full text has been retrieved. |
| Revisit the current discussion or latest analysis | Top-right Records → Current discussion / Latest analysis | Reads saved content only. |
| Find earlier conversations | Records → Enter keywords → View conversation history | Leave keywords blank for recent messages, or search the entire project. |
| Inspect ongoing requirements and revision reasons | Research notes at the top | To correct them, send a message in the discussion. |
| Download results | Research proposition → Export Markdown | Saves to the browser's download directory. Settings also shows the automatic export location. |
| Create or switch research | New research / Research title in the sidebar | New research inherits current settings but starts with a fresh topic, papers, conversation, and usage. |
| Pin, delete, or restore research | Buttons beside the research title / Trash in the sidebar | Deleted research can be restored. Stop running research before deleting it. |
| Stop or resume | Stop beside the running indicator / Resume research after stopping | Completed steps are retained. At a discussion pause, use Continue. |

You can select up to 10 attachments at once, totaling 8 MB. PDF import requires local `pdftotext`; scanned documents need extractable text first. Importing does not call the model. Papers are not merged merely because their titles are similar; repeated imports are deduplicated by existing source identifiers.

The default budget is **200 model calls and 300 minutes of cumulative running time**. Existing research keeps its saved settings. Time spent waiting for you to read or type is not counted. New research inherits the current budget, model, and literature scope.

## Stopping, resuming, and storage

Closing the browser does not stop background research. Reopen it to view progress; click **Stop** to pause a run. Pressing Ctrl+C in the service terminal shuts down the local service and stops its tasks. Completed steps are retained; an interrupted step must run again.

Web and CLI share the project's conversations, papers, and checkpoints. If a CLI is already running the same project, the Web interface reports that it is running in the terminal. Stop it from that terminal.

Choose project and report roots at startup:

```sh
research-idea web --projects ./research-projects --output ./results
```

The project directory stores conversations and progress. Results use a fixed folder name, `idea-TIMESTAMP`. `--output` sets the default result location for new projects; existing projects retain their settings. **Export Markdown** on the research-proposition page downloads an additional copy.

## Optional shortcuts

CLI users can also enter `/run`, `/continue`, `/stop`, `/budget`, `/date`, `/venues`, `/model`, `/reasoning`, and related shortcuts in the input. `/help` opens Web instructions; `/help date` explains a single feature. Commands are handled by the program, not sent to the model as research feedback. Invalid commands display usage guidance.

The Web interface does not accept arbitrary local paths. Import through the attachment picker, switch research in the sidebar, and change the report root with startup arguments; corresponding commands point to these controls. Close the browser tab to leave the Web interface. `/exit` does not shut down the background service.

## Implementation and validation

The Web service reuses CLI command handling, configuration validation, paper import, and the research worker. Problem discovery, literature analysis, and discussion memory use the same workflow. The service binds only to loopback and validates request origins and session tokens. Attachments are written into the current project; raw model output and paper HTML are not executed.

Regression tests cover settings, stage transitions, stopping, concurrency, attachments, invalid input, saving, and recovery. Interface checks use explicitly synthetic materials and simulated tasks to inspect buttons, dialogs, and refresh behavior without consuming research model calls.
