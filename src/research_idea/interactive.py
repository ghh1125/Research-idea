"""Small terminal launcher; all execution still goes through the regular CLI."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

from .config import load_config
from .store import Store
from .search_scope import recent_defaults


def read_topic_file(path):
    path = Path(path).expanduser()
    with path.open('rb') as stream:
        raw = stream.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError('Topic file exceeds 128 KiB')
    try:
        text = raw.decode('utf-8-sig').strip()
    except UnicodeDecodeError:
        raise ValueError('Topic file must use UTF-8') from None
    if not text or '\x00' in text:
        raise ValueError('Topic file must contain nonempty text without null characters')
    return text


def ask(label, default=''):
    hint = f' [{default}]' if default else ''
    try:
        return input(f'{label}{hint}：').strip() or str(default)
    except EOFError:
        raise ValueError('输入已结束；尚未启动研究。可使用 start 命令直接传入参数。') from None


def choose(label, options, default=0):
    print(label)
    for index, option in enumerate(options, 1):
        print(f'  {index}. {option}')
    while True:
        value = ask('选择编号', str(default + 1))
        if value.isdecimal() and 1 <= int(value) <= len(options):
            return int(value) - 1
        if value in options:
            return options.index(value)
        print('请输入列表中的编号。')


def configure_launch(args):
    if not sys.stdin.isatty():
        raise ValueError('launch requires an interactive terminal; use start TOPIC --project PATH for scripts')
    print('Research-idea · 本地研究启动器（回车接受默认值，Ctrl+C 退出）')
    if args.project is None:
        args.project = Path(ask('项目目录', 'research-projects/idea-' + datetime.now().strftime('%Y%m%d-%H%M%S')))
    args.project = args.project.expanduser().resolve()
    cfg = load_config(args.project)
    existing = (args.project / 'research.sqlite3').exists()
    saved_topic = ''
    if existing:
        store = Store(args.project, readonly=True)
        try:
            saved_topic = store.get('topic', '')
        finally:
            store.close()
    if not args.topic:
        value = ask('研究方向（多行内容用 @文件路径）', saved_topic)
        args.topic = read_topic_file(value[1:]) if value.startswith('@') else value
    if not args.topic or not args.topic.strip():
        raise ValueError('Research topic cannot be empty')
    if saved_topic and args.topic != saved_topic:
        raise ValueError('Project already has a different topic; choose a new project directory')
    args.backend = args.backend or cfg['backend']
    if args.model is None:
        preferred = cfg['model'] or ('gpt-6.1-sol' if args.backend == 'codex' else '')
        options = ([preferred] if preferred else []) + ['沿用后端配置', '手动输入模型 ID']
        selected = options[choose('模型（不是账户可用模型的实时列表）', options)]
        args.model = '' if selected == '沿用后端配置' else ask('模型 ID') if selected == '手动输入模型 ID' else selected
        if selected == '手动输入模型 ID' and not args.model:
            raise ValueError('Model ID cannot be empty; choose 沿用后端配置 to inherit')
    if args.reasoning_effort is None and args.backend == 'codex':
        levels = ['inherit', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra', 'minimal', 'none']
        if args.model == 'gpt-6.1-sol':
            levels = [level for level in levels if level not in {'minimal', 'none'}]
        print('思考强度依赖所选模型与 Codex 版本；inherit 沿用 Codex 配置。')
        default = cfg['reasoning_effort'] or ('inherit' if existing else 'medium')
        if default not in levels:
            default = 'inherit'
        args.reasoning_effort = levels[choose('思考强度', levels, levels.index(default))]
    if args.papers is None:
        args.papers = []
        print('可导入 PDF、正文或论文 JSON；每次输入一个文件/目录，空行结束。')
        while value := ask('论文路径（可留空）'):
            args.papers.append(Path(value).expanduser())
    if args.no_search:
        args.auto_search = False
    elif args.literature_preset is None and args.search_source is None and args.venues is None:
        selection = choose('文献来源', ['近期 AI 会议 + CS arXiv', '近期 CS arXiv', '仅本地资料', '沿用项目设置'], 3 if existing else 0)
        if selection == 0:
            args.literature_preset = 'ai-recent'
            args.auto_search = True
        elif selection == 1:
            args.search_source, args.venues = 'arxiv', []
            if args.cs_only is None:
                args.cs_only = True
            if args.arxiv_categories is None:
                args.arxiv_categories = ['cs.*']
            args.auto_search = True
        elif selection == 2:
            args.no_search, args.auto_search = True, False
    if not args.no_search:
        dates = recent_defaults() if not existing or args.literature_preset else cfg
        if args.search_date_mode is None:
            if args.since is not None or args.until is not None:
                args.search_date_mode = 'fixed'
            else:
                default_mode = 'rolling' if args.literature_preset else cfg['search_date_mode']
                args.search_date_mode = ['rolling', 'fixed'][choose(
                    'arXiv 时间范围', ['动态：方法近一年 / 动机查重近半年', '固定日期'],
                    0 if default_mode == 'rolling' else 1)]
        if args.search_date_mode == 'fixed':
            if args.since is None:
                args.since = ask('论文起始日期 YYYY-MM-DD', dates['search_since'])
            if args.until is None:
                args.until = ask('论文截止日期 YYYY-MM-DD', dates['search_until'])
        else:
            print(f'arXiv 每次运行自动更新日期：方法近 {args.strategy_months or cfg["strategy_months"]} 个月；'
                  f'动机查重近 {args.novelty_months or cfg["novelty_months"]} 个月。')
        conference_policy = args.conference_policy or ('window' if args.search_date_mode == 'fixed'
            else 'latest' if args.literature_preset else cfg['conference_policy'])
        print('会议时间范围：' + ('各会议最新公开的一届；本届未公开则选上一届。'
            if conference_policy == 'latest' else '按所设日期窗口筛选。') + '可在对话中用 /date 修改。')
    if args.constraints is None:
        args.constraints = ask('资源限制（如单卡24GB、两周；未知可回车）', cfg['constraints'])
    budget = {'max_papers': 6, 'max_candidates': 1, 'max_rounds': 2,
              'max_calls': 80, 'max_seconds': 6600, 'timeout_s': 1200}
    selection = choose('运行预算', ['试跑：6篇 / 1候选 / 2轮 / 80次调用 / 110分钟', '沿用项目设置', '逐项设置'], 1 if existing else 0)
    labels = {'max_papers': '最多论文数', 'max_candidates': '最多候选数', 'max_rounds': '最多修订轮数',
              'max_calls': '模型调用上限', 'max_seconds': '累计运行秒数上限', 'timeout_s': '单次模型调用超时秒数'}
    for key, value in budget.items():
        if getattr(args, key) is not None:
            continue
        if selection == 0:
            setattr(args, key, value)
        elif selection == 2:
            while True:
                raw = ask(labels[key], str(cfg[key]))
                if raw.isdecimal() and int(raw) > 0:
                    setattr(args, key, int(raw))
                    break
                print('请输入正整数。')
    print(f'\n项目：{args.project}\n主题：{args.topic}\n模型：{args.model or "沿用后端配置"}；思考强度：{args.reasoning_effort or "沿用后端配置"}')
    if not args.setup_only:
        args.setup_only = choose('下一步', ['开始研究', '仅保存配置，稍后运行']) == 1
    args.command = 'start'
