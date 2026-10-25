"""Human-facing research summaries; full structured records stay in the store."""
from __future__ import annotations


STAGE_LABELS = {
    'plan_search': ('search', '第一阶段 · 文献构思 · 找论文'),
    'screen_papers': ('search', '第一阶段 · 文献构思 · 选择论文'),
    'extract': ('read', '第一阶段 · 文献构思 · 阅读论文'),
    'read_section': ('read', '第一阶段 · 文献构思 · 阅读正文'),
    'paper_card': ('analysis', '第一阶段 · 文献构思 · 理解问题、方法与启发'),
    'inspect_source': ('read', '第二阶段 · 方案设计 · 定向阅读'),
    'design_transfer': ('design', '第二阶段 · 方案设计 · 这篇论文怎样帮助方案'),
    'audit_claims': ('analysis', '第一阶段 · 文献构思 · 理解实验支持了什么'),
    'explore_problems': ('analysis', '第一阶段 · 探索不同的重要问题'),
    'deepen_problem': ('analysis', '第一阶段 · 深入问题与已有回应'),
    'map': ('analysis', '第一阶段 · 比较问题，说明优先研究什么'),
    'propose': ('concept', '第一阶段 · 背景 → 现有方法 → 可能的问题 → 动机 → Idea'),
    'develop': ('design', '第二阶段 · 技术参考 · 寻找适合 idea 的路线'),
    'refine': ('design', '第二阶段 · 技术参考 · 完善思路'),
    'review': ('review', '第二阶段 · 技术参考 · 讨论关键判断'),
}


def stage_label(stage, phase='ideation'):
    tag, label = STAGE_LABELS.get(stage, ('analysis', stage))
    if phase == 'neighbor':
        return ('read' if stage == 'inspect_source' else 'search'), '第一阶段 · 弄清最接近的方法与关键信息来源'
    if phase == 'ideation_draft' and stage == 'propose':
        return 'analysis', '第一阶段 · 构思核心想法与需要补充的方法细节'
    if phase == 'design' and stage == 'plan_search':
        return 'design', '第二阶段 · 从 idea 推导技术角度与检索方向'
    if phase == 'design':
        label = label.replace('第一阶段 · 文献构思', '第二阶段 · 方案设计')
    return tag, label
SKILL_LABELS = {
    'research-idea-read-evidence': '定位原文依据',
    'research-idea-analyze-paper': '理解方法与研究启发',
    'research-idea-audit-claims': '理解实验与结论',
    'research-idea-motivation': '建立问题与动机',
    'research-idea-compare-methods': '对比动机与贡献',
    'research-idea-build-mechanism': '设计作用机制',
    'research-idea-check-feasibility': '安排实施路径',
    'research-idea-design-falsification': '检视核心解释',
}
STATUS_LABELS = {'initialized': '准备开始', 'running': '研究中', 'completed': '方案已生成',
                 'budget_exhausted': '本轮预算用完，可增加预算后继续', 'blocked': '运行中断，可继续',
                 'interrupted': '已停止，可继续'}


def skill_label(name):
    return SKILL_LABELS.get(name, name)


def points(items):
    return '\n'.join('• ' + str(item) for item in items if str(item).strip())


def argument_markdown(motivation, proposal, *, include_intervention=True, idea_core=None):
    """Render consecutive parts of the argument, including older saved outputs."""
    existing = motivation.get('existing_work') or '；'.join(
        p.get('addressed_problem', '') for p in proposal.get('positioning', []))
    core = proposal.get('idea_core', {}) if idea_core is None else idea_core
    concrete_idea = ['**' + label + '：** ' + core[key] for key, label in (
        ('concrete_target', '具体利用什么'), ('construction_path', '这些信息怎样得到'),
        ('capability_bridge', '为什么能解决这个问题'), ('essential_difference', '与已有方法的本质区别'))
        if core.get(key)]
    for item in core.get('information_path', []):
        concrete_idea.append('**关键信息：' + item['information'] + '**\n\n' + '\n\n'.join(
            '**' + label + '：** ' + item[key] for key, label in (
                ('source', '从哪里获得'), ('construction', '怎样取得'),
                ('reliability_basis', '判断依据'), ('error_handling', '信息有误时怎样处理'),
                ('applicability', '适用条件'))))
    parts = [
        ('Background · 研究背景', [motivation.get('background')]),
        ('Existing methods · 现有方法做到了什么', [existing]),
        ('Possible problem · 从已有进展推导研究问题', [motivation.get('existing_approach_limit'),
            motivation.get('causal_explanation', proposal.get('hypothesis')),
            motivation.get('problem_derivation'),
            motivation.get('problem_observation', proposal.get('problem')),
            motivation.get('importance', proposal.get('why_it_matters'))]),
        ('Motivation · 为什么需要这项研究', [motivation.get('research_need')]),
        ('Idea · 基于动机提出核心想法', [proposal.get('intervention') if include_intervention else None,
            motivation.get('why_this_method', proposal.get('intervention')),
            *concrete_idea,
            motivation.get('expected_progress')]),
    ]
    return '\n\n'.join('**' + label + '**\n\n' + '\n\n'.join(dict.fromkeys(v.strip() for v in values if v and v.strip()))
                        for label, values in parts)


def design_axes_markdown(axes):
    return '\n\n'.join(
        f"**技术角度 {index}：{axis['question']}**\n\n{axis['why_needed']}\n\n"
        f"需要解决：{axis['required_function']}"
        for index, axis in enumerate(axes, 1))


def activity_summary(stage, result, citations=None):
    """Show decisions and findings at every stage, rather than nested schema fields."""
    lines = []
    def add(label, value):
        if value:
            lines.append('**' + label + '：** ' + ('\n' + points(value) if isinstance(value, list) else str(value)))
    def section(title):
        lines.append('### ' + title)
    def source(paper_id):
        if citations:
            add('论文', citations.paper(paper_id))
    def source_refs(ids, paper_id):
        if citations:
            # The paper link is already directly above this source's findings.
            refs = [citations.location(citations.evidence[eid])
                    if eid in citations.evidence and citations.evidence[eid]['paper_id'] == paper_id
                    else citations.reference(eid) for eid in ids]
            add('原文依据', list(dict.fromkeys(refs)))
        else:
            add('原文依据', ids)
    if stage in {'extract', 'read_section', 'inspect_source'}:
        for item in result.get('observations', []):
            add('读到的内容', item['statement'])
            add('成立条件', item.get('conditions'))
        if not lines:
            lines.append('这段没有新增引用，继续分析其他材料。')
    elif stage == 'plan_search':
        for route in result.get('research_routes', []):
            section('探索路线 · ' + route['question'])
            add('为什么看这条路线', route['why_relevant'])
        add('研究问题', result.get('research_question'))
        if result.get('design_axes'):
            lines.append(design_axes_markdown(result['design_axes']))
        for item in result.get('queries', []):
            add('检索', item['query'])
            add('为什么找它', item['rationale'])
    elif stage == 'screen_papers':
        add('选读思路', result.get('selection_summary'))
        for item in result.get('selected', []):
            source(item['paper_id'])
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
            add('为什么值得研究', item['why_meaningful'])
    elif stage == 'audit_claims':
        for item in result.get('claims', []):
            add('论文主张', item['claim'])
            add('实验支持', item['warranted_conclusion'])
            add('值得区分的解释', item.get('confounds'))
    elif stage == 'explore_problems':
        add('从背景和已有进展出发', result.get('background_logic'))
        for seed in result.get('problem_seeds', []):
            section('值得深入的问题 · ' + seed['question'])
            add('为什么考虑它', seed['entry_reason'])
    elif stage == 'deepen_problem':
        item = result['opportunity']
        section(item['question'])
        add('问题来源', {'unresolved_need': '已有进展之后仍值得解决的重要需要',
                       'emerging_problem': '已有方法使用或发展中产生的新困难'}.get(item.get('problem_origin')))
        for key, label in (('prior_art_delta', '已有办法怎样回应'),
                           ('bottleneck_hypothesis', '为什么仍会遇到这个困难'),
                           ('derivation', '由此怎样引出问题'), ('why_it_matters', '解决它有什么价值'),
                           ('research_need', '因此需要研究什么'), ('evidence_ids', '原文依据')):
            add(label, item.get(key))
    elif stage == 'map':
        frame = result.get('research_frame', {})
        add('我们要解决的大问题', frame.get('user_goal'))
        for approach in result.get('approach_landscape', []):
            section('已有思路 · ' + approach['name'])
            add('怎样起作用', approach['principle'])
            add('已经做到什么', approach['achieved_progress'])
            add('原文依据', approach['evidence_ids'])
        add('把相关研究连起来看', frame.get('literature_logic'))
        add('由此提出的研究问题', frame.get('research_question'))
        add('值得研究的问题', result.get('problem'))
        directions = {item['id']: item for item in result.get('opportunities', [])}
        for comparison in result.get('problem_comparisons', []):
            item = directions.get(comparison['opportunity_id'], {})
            section('问题比较 · ' + item.get('question', comparison['opportunity_id']))
            add('最值得研究之处', comparison['strongest_case'])
            add('已有回应后仍留下什么', comparison['remaining_obstacle'])
            add('与其他问题相比', comparison['priority_reason'])
            add('原文依据', item.get('evidence_ids'))
        if result.get('opportunities') and not result.get('problem_comparisons'):
            for opportunity in result['opportunities']:
                section('研究切口 · ' + opportunity['question'])
                add('问题来源', {'unresolved_need': '从背景需求提出新问题，现有主要方法难以解决',
                    'emerging_problem': '已有方法解决问题的过程又暴露新问题'}.get(opportunity.get('problem_origin')))
                add('文献怎样导出这个问题', opportunity['derivation'])
                if opportunity.get('bottleneck_hypothesis'):
                    add('可能的根本原因', opportunity['bottleneck_hypothesis'])
                else:
                    add('核心洞见', opportunity.get('insight'))
                add('已有思路怎样回应这个问题', opportunity.get('prior_art_delta'))
                add('由此产生的研究需要', opportunity.get('research_need'))
                add('研究价值', opportunity['why_it_matters'])
                add('原文依据', opportunity['evidence_ids'])
        elif not result.get('opportunities'):
            add('观察', result.get('observations'))
            add('可能的原因', result.get('competing_explanations'))
        choices = result.get('selected_problems', [])
        for choice in choices:
            question = directions.get(choice['opportunity_id'], {}).get('question', choice['opportunity_id'])
            section('先选定问题 · ' + question)
            add('为什么优先研究它', choice['selection_reason'])
        if choices:
            lines.append('问题与选择理由已保存。接下来围绕这个障碍构思 idea。')
    elif stage == 'propose':
        for item in result.get('candidates', []):
            section('Idea · ' + item['title'])
            lines.append(argument_markdown(item['motivation'], item))
            add('选择这个方向的理由', item.get('selection_reason'))
            section('基本可行性')
            sketch = item.get('feasibility_sketch', {})
            add('可用输入', sketch.get('inputs'))
            add('关键假设', sketch.get('key_assumption'))
            if item.get('positioning'):
                section('与已有工作的区别')
            for comparison in item.get('positioning', []):
                source(comparison['paper_id'])
                add('已有工作解决了什么', comparison['addressed_problem'])
                add('我们继续回答什么', comparison['remaining_question'])
                add('预期贡献', comparison['contribution'])
                source_refs(comparison['evidence_ids'], comparison['paper_id'])
        if lines:
            lines.append('第一阶段到此完成。接下来：Idea → Method，探索技术路线并形成研究方案。')
        if not lines:
            add('构思结果', result.get('no_candidate_reason'))
    elif stage == 'design_transfer':
        source(result['paper_id'])
        for option in result.get('options', []):
            section(option['question'])
            for key, label in [('source_technique', '可借鉴的技术'),
                               ('shared_structure', '为什么可以迁移'), ('source_conditions', '原技术的适用条件'),
                               ('adaptation', '在本方案中怎么改'), ('why_it_helps', '如何解决当前问题'),
                               ('simpler_alternative', '简单替代方案')]:
                add(label, option[key])
            source_refs(option['evidence_ids'], result['paper_id'])
        if not result.get('options'):
            add('接下来重点读', result.get('reading_gaps'))
    elif stage in {'develop', 'refine'}:
        if result.get('design_axes'):
            lines.append(design_axes_markdown(result['design_axes']))
        section('技术路线')
        add('具体方法', result['method'].get('summary') or result['method']['changes'])
        for decision in result.get('design_decisions', []):
            section(decision['question'])
            add('采用', decision['choice'])
            add('选择理由', decision['rationale'])
            add('针对本场景的改造', decision['adaptation'])
            add('原文依据', decision['evidence_ids'])
        section('与 idea 的关系')
        add('与已有工作的差异', result['prior_art']['justification'])
        for response in result.get('review_responses', []):
            add('回应讨论', response['issue'])
            add('采用的处理', response['change'])
            add('原因', response['reason'])
    elif stage == 'review':
        add('问题与动机', result['motivation_assessment']['reason'])
        for item in result.get('issues', []):
            add('设计讨论', item['issue'])
            add('改进办法', item['action'])
    text = '\n\n'.join(lines)
    return citations.text(text) if citations else text


def idea_markdown(candidate):
    """Lead with the idea; technical references support it without an experiment plan."""
    proposal = candidate['proposal']
    spec = candidate.get('spec') or {}
    motivation = spec.get('motivation', proposal.get('motivation', {}))
    method = spec.get('method', {})
    claim = spec.get('novelty_claim', {})
    lines = ['### ' + proposal['title'], '']
    def add(label, value):
        if value:
            lines.extend(['**' + label + '：** ' + str(value), ''])
    lines.extend(['#### 第一部分 · Background → Existing methods → Possible problem → Motivation → Idea', '',
                  argument_markdown(motivation, proposal, include_intervention=not spec,
                      idea_core=spec.get('idea_core', proposal.get('idea_core', {}))), ''])
    add('与已有工作的差异', claim.get('claim') or spec.get('prior_art', {}).get('justification'))
    if not spec:
        sketch = proposal.get('feasibility_sketch', {})
        add('可用输入', sketch.get('inputs'))
        add('关键假设', sketch.get('key_assumption'))
        return '\n'.join(lines)
    lines.extend(['#### 第二部分 · Idea → Method · 技术参考', ''])
    axes = spec.get('design_axes') or candidate.get('design_search_plan', {}).get('design_axes', [])
    if axes:
        lines.extend([design_axes_markdown(axes), ''])
    by_id = {a['id']: a['question'] for a in axes}
    for decision in spec.get('design_decisions', []):
        add('对应技术问题', '；'.join(by_id[i] for i in decision.get('axis_ids', []) if i in by_id))
        add('可借鉴的技术', decision['choice'])
        add('为什么适合', decision['rationale'])
        add('如何用于这个 idea', decision['adaptation'])
        add('来源', '、'.join(decision.get('evidence_ids', [])))
    add('参考路线 · 怎样共同实现 Idea' if axes else '参考路线', method.get('summary') or '\n'.join(method.get('changes', [])))
    # Specific impossible inputs need an alternative in the design, not a status badge.
    for item in spec.get('feasibility', {}).get('required_signals', []):
        if item.get('availability') == 'unavailable':
            add('实施替代', item['name'] + '当前不可用；' + item['substitute'])
    return '\n'.join(lines)


def error_summary(error):
    """Turn operational failures into a next action in the terminal."""
    import re
    from .backend_errors import RetryExhausted
    message = str(error)
    if isinstance(error, RetryExhausted):
        return message
    timeout = re.search(r'exceeded the ([0-9.]+)s task timeout', message)
    if timeout:
        seconds = float(timeout.group(1))
        suggested = max(300, int(seconds * 1.5 / 60 + 1) * 60)
        return (f'本次模型调用超过 {seconds / 60:.1f} 分钟，已停止等待。已保存的分析可以继续。\n'
                f'可用 /budget timeout_s {suggested} 延长单次等待，再输入 /run；/budget 查看剩余总预算。')
    return message
