# v0.8.0 Web design preview (archived)

**English** | [![简体中文](https://img.shields.io/badge/Language-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-blue)](README.zh-CN.md)

> This page preserves the earlier design preview. The current local implementation runs real research; see the [local Web workbench](../web-workbench.md). “Not connected” statements below describe the preview at that time.

## Start

After installation or upgrade:

```bash
research-idea web
```

The browser opens <http://127.0.0.1:8769/> automatically. Press Ctrl+C to stop the server. The same command works on macOS, Linux, and Windows from any directory.

```bash
research-idea web --no-browser --port 8770
research-idea web --codex-profile research
research-idea web --help
```

`--codex-bin` selects a local Codex executable. The service binds only to loopback. The old `python -m http.server` command can display a static page but cannot discover local models; use the entry point above.

## Interface

- The left sidebar selects existing conversations or creates new ones. Drafts stay in the current browser.
- The center shows the conversation, composer, and stage progress. Completed steps open a detail dialog.
- System settings open from the top right. Model and effort use dropdowns; literature scope, budgets, output location, and skills expand when needed.
- During discussion, sending a message discusses, corrects, or requests more reading. Continue advances from direction discussion to deeper problem analysis, or from problem discussion to the final research argument. There is no confirmation after every paper.
- Unsent drafts survive closing dialogs and switching conversations. The temporary preview-stage control has been removed.
- Process details cover search, reading, skills, problem comparisons, turn changes, calls, and runtime. Each explains its input, action, and effect on the discussion. Skill text comes from the installed version rather than a copy embedded in the page.

## Connected and remaining at preview time

**Codex model discovery was already live.** Initial loading reads the local model cache; Refresh reads the paginated `model/list` catalog through `codex app-server`, showing its source. IDs, names, and reasoning options come from returned metadata rather than a single hardcoded choice. Failed refreshes preserve the previous catalog and selection. Profiles are queried separately rather than receiving a default-profile cache. No inference turn is started and no credentials are returned to the browser. A catalog is not proof of inference entitlement; Codex may itself use a cached catalog. See [the official protocol](https://learn.chatgpt.com/docs/app-server#list-models-modellist).

**Research interactions were still a demonstration.** Browser drafts were not CLI projects. Research execution, project persistence, account checks, and other providers' catalogs were not connected. At that time, real research used `research-idea`; a sample discussion was available through System settings → Projects and help → Introduction → Demo.

Source: [`web.py`](../../src/research_idea/web.py), [`model_discovery.py`](../../src/research_idea/model_discovery.py), [`web_assets/index.html`](../../src/research_idea/web_assets/index.html). The preview did not change CLI research, evidence, memory, or budget handling.
