"""Local command reference shared by chat help and completion descriptions."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches


@dataclass(frozen=True)
class CommandHelp:
    group: str
    usage: str
    summary: str
    details: str
    examples: tuple[str, ...]
    aliases: tuple[str, ...] = ()

    @property
    def name(self):
        return self.usage.split()[0]


BUDGET_LABELS = {
    'search_results_per_query': '每次检索先筛的论文数',
    'max_papers': '初次选读规模',
    'max_candidates': '优先问题数量',
    'max_calls': '模型调用上限',
    'max_seconds': '累计时间（秒）',
    'timeout_s': '单次调用超时（秒）',
}

COMMAND_HELP = (
    CommandHelp('入门与帮助', '/intro', '看从输入方向到交付研究主张的操作步骤。',
        '适合第一次使用。介绍两次讨论暂停、/continue、结果查看和恢复方式，不调用模型。',
        ('/intro',)),
    CommandHelp('入门与帮助', '/help [命令|all]', '查看全部命令，或某个命令的参数与示例。',
        '不带参数显示分类总览；命令名可带或不带 /；all 展开全部详细说明。\n'
        '也可以在任意命令后加 --help 或 -h，只查看说明，不执行命令。\n'
        '方括号表示可选内容，竖线表示选一个；实际输入时不用写这些符号。',
        ('/help', '/help date', '/help /budget', '/help all', '/model --help')),
    CommandHelp('研究与讨论', '/topic [研究方向]', '查看主题，或在研究开始前设置主题。',
        '不带参数显示当前主题；带文字会保存主题，但不会立即调研。\n'
        '已有研究任务后，换题请用 /new 新方向；当前问题的补充和纠正直接发消息即可。',
        ('/topic', '/topic 多智能体如何持续改进协作')),
    CommandHelp('研究与讨论', '/input 路径', '把文本文件作为一条讨论消息发送给模型。',
        '读取 UTF-8 文本文件，最多 128 KiB，适合较长的研究说明。会调用模型并计入预算。\n'
        '项目还没有主题时，文件内容同时作为主题。导入论文正文请用 /papers。',
        ('/input ./brief.txt',)),
    CommandHelp('研究与讨论', '/constraints [文字]', '查看或保存设备、时间、数据等资源条件。',
        '不带参数查看当前条件；带文字会整体替换已保存的资源条件，供后续分析使用。\n'
        '这里的时间和资源描述用于研究讨论；程序调用上限由 /budget 设置。',
        ('/constraints', '/constraints 单张24GB GPU，两周，可小规模微调')),
    CommandHelp('研究与讨论', '/run [研究方向]', '开始调研，或从已保存的进度继续。',
        '使用当前主题检索、阅读和分析，会调用模型。新项目也可直接附上研究方向。\n'
        '交互研究先暂停讨论方向，再暂停讨论深入后的问题；暂停时请用 /continue 推进。\n'
        '中断或预算用完后，处理问题或提高预算，再用 /run 恢复。',
        ('/run', '/run 多智能体如何持续改进协作')),
    CommandHelp('研究与讨论', '/continue', '结束当前讨论，进入底部提示的下一步。',
        '方向讨论后：逐个深入并比较问题。问题讨论后：整理背景、现有方法、问题、动机和研究主张。\n'
        '同一问题可多轮迭代：直接发意见 → 等回复 → 继续追问或纠正 → /problems 查看当前版本。\n'
        '先直接发送补充或纠正，讨论满意后再单独输入 /continue；此命令会调用模型。\n'
        '交付后也可直接提出修改，重新进入问题讨论；满意后 /continue 更新最终主张。\n'
        '没有暂停中的讨论时，用 /run 开始或恢复研究。',
        ('/continue',)),
    CommandHelp('研究与讨论', '/stop', '停止当前任务，保留已完成的进度。',
        '运行时输入框隐藏，请按 Ctrl+C 停止；/stop 是停止任务的命令入口。\n'
        '中断后可用 /run 恢复；已消耗的调用和时间不会清零。没有运行任务时不会开始新任务。',
        ('/stop',)),
    CommandHelp('研究与讨论', '/problems [detail]', '重看当前方向或问题讨论。',
        '不带参数显示易读概览；detail 显示完整论证，包括不同问题及选择理由。\n'
        '只读取已保存的结果，不调用模型。想修改判断时，直接输入意见，可反复讨论。\n'
        '例如：这个问题为什么妨碍原目标？请把原因讲清楚，再更新当前论证。\n'
        '修订过程中看这里；满意后 /continue，再用 /report 查看更新后的最终主张。',
        ('/problems', '/problems detail')),
    CommandHelp('模型与账户', '/model [模型ID|inherit]', '选择模型，或直接指定模型 ID。',
        '不带参数打开选择菜单；也可以手动填写当前后端与账户支持的模型 ID。\n'
        'inherit 清除本项目的模型覆盖，沿用后端配置。设置保存到当前项目，下次调用生效。\n'
        '这只切换模型，不切换后端；后端在启动时通过 --backend 选择。',
        ('/model', '/model gpt-6.1-sol', '/model inherit')),
    CommandHelp('模型与账户', '/reasoning [强度|inherit]', '选择 Codex 模型的思考强度。',
        '不带参数打开菜单；可用档位取决于模型和 CLI。常用 low、medium、high。\n'
        '程序接受 none、minimal、low、medium、high、xhigh、max、ultra；不代表每个模型都支持。\n'
        'inherit 沿用 Codex 配置；其他后端应使用 inherit。仅影响本项目后续调用。',
        ('/reasoning', '/reasoning high', '/reasoning inherit')),
    CommandHelp('模型与账户', '/models', '查看本地模型目录和已记录的思考档位。',
        '读取本地 Codex 模型缓存，不是账户权限的实时查询。没有缓存时仍可用 /model 模型ID 手动设置。',
        ('/models',)),
    CommandHelp('模型与账户', '/account', '查看后端、模型、配置档和登录方式。',
        'Codex 使用本地登录状态；API 后端显示密钥环境变量是否已设置；Claude 登录由其 CLI 管理。\n'
        '不显示密钥，不查询实时余额，也不消耗研究模型调用预算。',
        ('/account',)),
    CommandHelp('文献与检索', '/papers [路径…]', '列出已有论文，或导入论文文件与目录。',
        '不带参数列出论文、来源链接和正文获取状态。带路径可导入 PDF、TXT、Markdown、论文 JSON 或目录。\n'
        '多个路径用空格分隔；路径内有空格时加引号。Windows 路径建议使用 / 分隔或双引号。\n'
        '这里只导入材料，不立即让模型阅读；下一次研究会使用这些材料。PDF 提取需要 pdftotext。',
        ('/papers', '/papers ./papers', '/papers "./my papers/paper.pdf" ./notes.md')),
    CommandHelp('文献与检索', '/scope [ai-recent|local|起始日期 截止日期]', '查看文献范围，或选择联网检索与本地资料。',
        '不带参数查看设置。ai-recent 启用最新公开会议届次 + CS arXiv，并恢复默认日期窗口和会议名单。\n'
        'local 关闭自动检索，保留已有资料。两项日期使用 YYYY-MM-DD，并将会议也改为日期窗口筛选。\n'
        '只想改时间或会议时，分别用 /date 或 /venues，避免重置其他范围设置。',
        ('/scope', '/scope ai-recent', '/scope local', '/scope 2025-01-01 2026-10-23')),
    CommandHelp('文献与检索', '/date [操作 参数…]', '调整 arXiv 时间窗口和会议届次。',
        '不带参数显示设置并打开选择菜单。\n'
        'rolling 背景月数 动机月数：按运行当天向前计算；不写月数时用 12 和 6。\n'
        'fixed 起始日期 截止日期：两项都用 YYYY-MM-DD，同时把会议改为日期窗口。\n'
        'conference latest：每个会议取截止日期前最新公开的一届；本届未公开则取上一届。\n'
        'conference window：会议也按日期窗口筛选。可在 fixed 之后单独改回 latest。',
        ('/date', '/date rolling 12 6', '/date fixed 2025-01-01 2026-10-23',
         '/date conference latest', '/date conference window')),
    CommandHelp('文献与检索', '/venues [预设或会议列表]', '查看已选会议，或替换会议名单。',
        '不带参数显示已选会议和分类；带多个会议名时用空格或逗号分隔。\n'
        '常用预设：ai-recommended、ccf-a-ai-2026、tsinghua-a-ai-2019、core-astar-ai-2026。\n'
        '其他预设和完整支持名单可在系统终端运行 research-idea venues 查看。\n'
        '日期由 /date 控制；如果此前用了 /scope local，先切回 /scope ai-recent 再选会议以启用自动检索。',
        ('/venues', '/venues ACL EMNLP COLM ICLR', '/venues ai-recommended', '/venues core-astar-ai-2026')),
    CommandHelp('记录与结果', '/status', '查看当前进度、累计用量和下一步。',
        '显示项目路径、主题、阶段、模型、调用与时间预算、论文和证据数量。讨论暂停时会提示如何继续。',
        ('/status',)),
    CommandHelp('记录与结果', '/report', '查看当前保存的研究主张。',
        '显示背景、现有方法、问题、动机和一句核心研究主张。只读取结果，不重新调用模型。\n'
        '最终报告还没形成时，可用 /problems 查看当前讨论，/output 查看结果保存位置。',
        ('/report',)),
    CommandHelp('记录与结果', '/evidence [序号或证据ID]', '查看论文依据，并展开对应原文。',
        '不带参数列出依据、论文标题和来源链接；输入列表序号或证据 ID 可展开原文及位置。\n'
        '序号使用当前 /evidence 列表中的编号，例如 1，不是 /papers 中的论文编号。',
        ('/evidence', '/evidence 1')),
    CommandHelp('记录与结果', '/details [on|off]', '展开上一步分析，或调整后续过程输出。',
        '不带参数展开最近一步已保存的完整分析；on 持续显示完整过程，off 恢复易读概览。\n'
        '不会重复调用模型；显示模式只影响当前窗口。',
        ('/details', '/details on', '/details off')),
    CommandHelp('记录与结果', '/memory', '查看持续保留的研究要点和讨论理由。',
        '展示现行要求、原话出处，以及已保存的异议和判断修改理由。\n'
        '也显示最近一轮实际保存的完整改动；窗口中的 [update] 是这些改动的简短提示。\n'
        '要修改这些要点，直接在对话中说明；要查原始消息，用 /history。',
        ('/memory',)),
    CommandHelp('记录与结果', '/history [关键词]', '查看原始对话，或查找较早的讨论。',
        '不带参数显示最近消息及编号；带关键词检索整个项目的原始会话。\n'
        '只读取记录，不会把查到的内容自动作为新指令发送给模型。',
        ('/history', '/history 研究范围')),
    CommandHelp('项目与设置', '/config', '查看当前项目的模型、范围、预算等配置。',
        '只显示配置，不修改设置。使用 /model、/reasoning、/scope、/date、/venues、/budget、/constraints 或 /output 调整对应项目。',
        ('/config',)),
    CommandHelp('项目与设置', '/budget [设置项 数值]', '查看或修改调用、时间和选文上限。',
        '不带参数列出当前值；修改时每次传一个设置项和一个整数。\n'
        + '\n'.join(f'{key}：{label}' for key, label in BUDGET_LABELS.items())
        + '\nmax_seconds 和 timeout_s 的单位是秒；例如 7200 秒为两小时。\n'
        '调用包括讨论、研究、格式修复与失败重试；等待重试计入时间，等待用户输入不计入。\n'
        '提高上限不会清零已用预算；用 /run 恢复中断的研究，/new 开始新的计数。',
        ('/budget', '/budget max_calls 100', '/budget max_seconds 7200', '/budget max_papers 6')),
    CommandHelp('项目与设置', '/output [目录|default]', '查看或更改结果保存的父目录。',
        '不带参数显示位置；传目录会保存设置，有结果时重新导出，原文件保留；default 恢复默认。\n'
        '文件夹名固定为 idea-时间戳；同一项目继续运行沿用原名称。\n'
        '这里存放 report.md、report.json 和论文分析；对话与检查点仍在项目目录。',
        ('/output', '/output ~/research-results', '/output "D:\\Research Results"', '/output default')),
    CommandHelp('项目与设置', '/new [研究方向]', '新建空白研究，沿用设置并从零计数。',
        '沿用模型、思考强度、检索范围、资源条件、预算上限和输出父目录。\n'
        '主题、论文、对话和已用预算不复制；可附上新方向，也可随后输入。旧项目保留，用 /open 返回。',
        ('/new', '/new 多智能体如何持续改进协作')),
    CommandHelp('项目与设置', '/open 项目目录', '打开项目，恢复对话、设置和讨论位置。',
        '使用 /status 中的项目路径，不是 /output 中的结果文件夹。\n'
        '已有项目会恢复原有记录；路径还没有项目时会初始化一个项目。累计用量不会清零。',
        ('/open ./research-projects/my-idea',)),
    CommandHelp('项目与设置', '/exit', '退出窗口，保留项目记录。',
        '如果有运行任务，会先停止。下次用同一个 --project 或 /open 路径继续。\n'
        'Ctrl+D 或 /quit 也可以退出；清空输入请按 Ctrl+C，清空输入不会重置预算。',
        ('/exit', '/quit'), aliases=('/quit',)),
)

COMMAND_LOOKUP = {name: item for item in COMMAND_HELP for name in (item.name, *item.aliases)}
COMMANDS = tuple(COMMAND_LOOKUP)
COMMAND_SUMMARIES = {name: item.summary for name, item in COMMAND_LOOKUP.items()}


def _detail(item):
    aliases = '\n别名：' + '、'.join(item.aliases) if item.aliases else ''
    return (f'## {item.name} · {item.summary}\n\n用法：{item.usage}{aliases}\n\n'
            f'{item.details}\n\n示例：\n' + '\n'.join('  ' + example for example in item.examples))


def help_text(topic=''):
    """Return help without executing a command, opening a menu, or using a model."""
    topic = topic.strip()
    if topic == 'all':
        return '\n\n'.join(_detail(item) for item in COMMAND_HELP)
    if topic:
        name = '/' + topic.lstrip('/') if topic not in {'-h', '--help'} else '/help'
        if name not in COMMAND_LOOKUP:
            close = get_close_matches(name, COMMANDS, n=1, cutoff=0.6)
            hint = f'；你可能想查看 /help {close[0][1:]}' if close else ''
            raise ValueError(f'没有这个命令：{topic}{hint}。输入 /help 查看全部命令。')
        return _detail(COMMAND_LOOKUP[name])
    lines = ['命令总览 · 在对话窗口中使用',
             '直接输入文字与模型讨论；/run 开始调研，暂停后 /continue 推进。',
             '详细说明：/help date 或 /date --help；/help all 展开全部。',
             '方括号内为可选参数，实际输入时不用写方括号。']
    previous = None
    for item in COMMAND_HELP:
        if item.group != previous:
            lines.extend(('', '## ' + item.group))
            previous = item.group
        aliases = '（也可 ' + '、'.join(item.aliases) + '）' if item.aliases else ''
        lines.extend((item.usage + aliases, '  ' + item.summary))
    lines.extend(('', 'Enter 发送 · Esc 然后 Enter 换行 · Tab 补全并看用途 · ↑↓ 历史',
                  'Ctrl+C 停止任务/清空输入 · Ctrl+D 退出',
                  '系统终端的命令说明：research-idea --help；单项示例：research-idea start --help'))
    return '\n'.join(lines)
