# 工作流借鉴与接口资料

本项目的控制器、存储、适配器和测试为本次自主实现；未复制或打包下列项目的源代码。它们是工作流设计的参考，不构成本项目已获得研究效果的证据。

- [ARIS / Auto-Research-In-Sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)：研究任务分解、迭代和状态保存。
- [ARIS idea-creator](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-creator/SKILL.md)：生成后再验证、候选 pilot、正负与不明确结果的解释。
- [ARIS research-refine](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-refine/SKILL.md)：问题锚定、实现规格、避免增加无用模块。
- [ARIS experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/experiment-bridge/SKILL.md)：实现与计划核对、sanity check、结果收集。
- [Karpathy autoresearch program.md](https://github.com/karpathy/autoresearch/blob/master/program.md)：固定评测、运行预算、实验与代码版本记录。
- [CCFA Skills](https://github.com/mikubaka88/CCFA-Skills)：问题—机制—证据关系、最近工作比较、实验到主张的证据边界。

接口参考：

- [Codex non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat/create)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)
- [OpenAlex API](https://developers.openalex.org/)

后端采用已核对文档的接口，但本开发环境未进行真实 CLI/模型账户联调。以后复制第三方代码时，应单独核实许可证、固定版本并保留必要声明。
