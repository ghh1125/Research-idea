"""Human-facing research summaries; full structured records stay in the store."""
from __future__ import annotations


STAGE_LABELS = {
    'plan_search': ('search', '1/4 · 找论文'),
    'screen_papers': ('search', '1/4 · 选择值得精读的论文'),
    'extract': ('read', '2/4 · 阅读论文'),
    'read_section': ('read', '2/4 · 阅读正文'),
    'paper_card': ('analysis', '2/4 · 梳理论文的方法与启发'),
    'inspect_source': ('read', '3/4 · 对照候选补读'),
    'audit_claims': ('analysis', '2/4 · 理解实验支持了什么'),
    'map': ('analysis', '3/4 · 找到值得研究的问题'),
    'propose': ('idea', '3/4 · 提出 idea'),
    'develop': ('analysis', '4/4 · 设计具体方法'),
    'refine': ('review', '4/4 · 改进方案'),
    'review': ('review', '4/4 · 讨论问题、动机与方法'),
}
SKILL_LABELS = {
    'research-idea-read-evidence': '定位原文依据',
    'research-idea-analyze-paper': '理解方法与研究启发',
    'research-idea-audit-claims': '理解实验与结论',
    'research-idea-motivation': '建立问题与动机',
    'research-idea-compare-methods': '对比动机与贡献',
    'research-idea-build-mechanism': '设计作用机制',
    'research-idea-check-feasibility': '安排实施路径',
    'research-idea-design-falsification': '设计第一步测试',
}
STATUS_LABELS = {'initialized': '准备开始', 'running': '研究中', 'completed': '方案已生成',
                 'budget_exhausted': '本轮预算用完，可增加预算后继续', 'blocked': '运行中断，可继续',
                 'interrupted': '已停止，可继续'}


def skill_label(name):
    return SKILL_LABELS.get(name, name)


def points(items):
    return '\n'.join('• ' + str(item) for item in items if str(item).strip())


def activity_summary(stage, result):
    """Show decisions and findings at every stage, rather than nested schema fields."""
    lines = []
    def add(label, value):
        if value:
            lines.append(label + '：' + ('\n' + points(value) if isinstance(value, list) else str(value)))
    if stage in {'extract', 'read_section', 'inspect_source'}:
        for item in result.get('observations', []):
            add('读到的内容', item['statement'])
            add('成立条件', item.get('conditions'))
        if not lines:
            lines.append('这段没有新增引用，继续分析其他材料。')
    elif stage == 'plan_search':
        add('研究问题', result.get('research_question'))
        for item in result.get('queries', []):
            add('检索', item['query'])
            add('为什么找它', item['rationale'])
    elif stage == 'screen_papers':
        add('选读思路', result.get('selection_summary'))
        for item in result.get('selected', []):
            add('选读原因', item['reason'])
            add('要从正文确认什么', item['reading_question'])
    elif stage == 'paper_card':
        labels = {'problem': '它解决什么问题', 'motivation': '为什么这样设计',
                  'method': '具体做法', 'results': '主要结果', 'idea_relevance': '对 idea 的启发'}
        for item in result.get('framework', []):
            if item['dimension'] in labels:
                add(labels[item['dimension']], item['summary'])
        for item in result.get('opportunities', []):
            add('可以进一步研究', item['hypothesis'])
            add('先怎么试', item['first_test'])
    elif stage == 'audit_claims':
        for item in result.get('claims', []):
            add('论文主张', item['claim'])
            add('实验支持', item['warranted_conclusion'])
            add('值得区分的解释', item.get('confounds'))
    elif stage == 'map':
        add('值得研究的问题', result.get('problem'))
        add('观察', result.get('observations'))
        add('可能的原因', result.get('competing_explanations'))
    elif stage == 'propose':
        for item in result.get('candidates', []):
            add('Idea', item['title'])
            add('问题', item['problem'])
            add('为什么值得做', item['motivation']['importance'])
            add('方法', item['intervention'])
            add('预期看到什么', item['prediction'])
        if not lines:
            add('构思结果', result.get('no_candidate_reason'))
    elif stage in {'develop', 'refine'}:
        add('动机', result['motivation']['importance'])
        add('方法', result['method'].get('summary') or result['method']['changes'])
        add('与已有工作的差异', result['prior_art']['justification'])
        add('第一步验证', result['validation'].get('summary') or result['validation']['first_test'])
        for response in result.get('review_responses', []):
            add('回应讨论', response['issue'])
            add('采用的处理', response['change'])
            add('原因', response['reason'])
    elif stage == 'review':
        add('问题与动机', result['motivation_assessment']['reason'])
        for item in result.get('issues', []):
            add('设计讨论', item['issue'])
            add('改进办法', item['action'])
        add('建议先试', result['motivation_assessment']['decisive_test'])
    return '\n\n'.join(lines)


def idea_markdown(candidate):
    """One useful proposal, including method steps and concrete first-test criteria."""
    proposal = candidate['proposal']
    spec = candidate.get('spec') or {}
    motivation = spec.get('motivation', proposal.get('motivation', {}))
    method, validation = spec.get('method', {}), spec.get('validation', {})
    claim = spec.get('novelty_claim', {})
    lines = ['### ' + proposal['title'], '']
    def add(label, value):
        if value:
            lines.extend(['**' + label + '：** ' + str(value), ''])
    add('研究问题' if motivation.get('basis') == 'research_hypothesis' else '问题', motivation.get('problem_observation', proposal.get('problem')))
    add('为什么值得做', motivation.get('importance', proposal.get('why_it_matters')))
    add('现有方法的局限', motivation.get('existing_approach_limit'))
    add('核心想法', motivation.get('causal_explanation', proposal.get('hypothesis')))
    add('具体方法', method.get('summary') or proposal.get('intervention') or '\n'.join(method.get('changes', [])))
    add('输入 → 输出', method.get('inputs', '') + ' → ' + method.get('outputs', '') if method else '')
    add('为什么可能奏效', motivation.get('why_this_method', proposal.get('mechanism')))
    add('与已有工作的差异', claim.get('claim') or spec.get('prior_art', {}).get('justification'))
    add('最简单的对照', motivation.get('simplest_alternative'))
    add('第一步验证', validation.get('summary') or validation.get('first_test', proposal.get('prediction')))
    add('值得继续的结果', validation.get('positive', claim.get('observable_consequence')))
    add('需要修改的结果', validation.get('negative', proposal.get('falsifier')))
    add('结果不明确时', validation.get('inconclusive'))
    add('最关键的假设', validation.get('weakest_assumption'))
    add('资源与规模', validation.get('budget_estimate', method.get('resource_requirements')))
    # Specific impossible inputs need an alternative in the design, not a status badge.
    for item in spec.get('feasibility', {}).get('required_signals', []):
        if item.get('availability') == 'unavailable':
            add('实施替代', item['name'] + '当前不可用；' + item['substitute'])
    return '\n'.join(lines)


def error_summary(error):
    """Turn operational failures into a next action in the terminal."""
    import re
    message = str(error)
    timeout = re.search(r'exceeded the ([0-9.]+)s task timeout', message)
    if timeout:
        seconds = float(timeout.group(1))
        suggested = max(300, int(seconds * 1.5 / 60 + 1) * 60)
        return (f'本次模型调用超过 {seconds / 60:.1f} 分钟，已停止等待。已保存的分析可以继续。\n'
                f'可用 /budget timeout_s {suggested} 延长单次等待，再输入 /run；/budget 查看剩余总预算。')
    return message
