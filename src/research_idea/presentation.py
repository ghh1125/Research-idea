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
    'map': ('analysis', '第一阶段 · 文献构思 · 连接背景、问题与动机'),
    'propose': ('concept', '第一阶段 · Background → Problem → Motivation → Idea'),
    'develop': ('design', '第二阶段 · 方案设计 · 确定方法与首测'),
    'refine': ('design', '第二阶段 · 方案设计 · 完善方案'),
    'review': ('review', '第二阶段 · 方案设计 · 讨论设计选择'),
}


def stage_label(stage, phase='ideation'):
    tag, label = STAGE_LABELS.get(stage, ('analysis', stage))
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
    'research-idea-design-falsification': '设计第一步测试',
}
STATUS_LABELS = {'initialized': '准备开始', 'running': '研究中', 'completed': '方案已生成',
                 'budget_exhausted': '本轮预算用完，可增加预算后继续', 'blocked': '运行中断，可继续',
                 'interrupted': '已停止，可继续'}


def skill_label(name):
    return SKILL_LABELS.get(name, name)


def points(items):
    return '\n'.join('• ' + str(item) for item in items if str(item).strip())


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
        add('研究问题', result.get('research_question'))
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
            section('Idea · ' + item['title'])
            section('新问题是什么')
            add('背景与需要', item['motivation'].get('background'))
            add('问题', item['problem'])
            section('为什么重要')
            add('为什么值得做', item['motivation']['importance'])
            add('现有简单做法的局限', item['motivation']['existing_approach_limit'])
            section('Idea 怎样解决它')
            add('可能的原因', item['motivation']['causal_explanation'])
            add('核心想法', item['intervention'])
            add('为什么这个想法有用', item['motivation']['why_this_method'])
            add('预期看到什么', item['prediction'])
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
                               ('simpler_alternative', '简单替代方案'), ('first_test', '先做什么实验')]:
                add(label, option[key])
            source_refs(option['evidence_ids'], result['paper_id'])
        if not result.get('options'):
            add('接下来重点读', result.get('reading_gaps'))
    elif stage in {'develop', 'refine'}:
        section('新问题是什么')
        add('问题', result['motivation']['problem_observation'])
        section('为什么重要')
        add('研究价值', result['motivation']['importance'])
        section('Idea 怎样解决它')
        add('具体方法', result['method'].get('summary') or result['method']['changes'])
        add('作用理由', result['motivation']['why_this_method'])
        for decision in result.get('design_decisions', []):
            section(decision['question'])
            add('采用', decision['choice'])
            add('选择理由', decision['rationale'])
            add('针对本场景的改造', decision['adaptation'])
            add('原文依据', decision['evidence_ids'])
        section('贡献与首测')
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
    text = '\n\n'.join(lines)
    return citations.text(text) if citations else text


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
    lines.extend(['#### 新问题是什么', ''])
    add('背景与需要', motivation.get('background'))
    add('研究问题' if motivation.get('basis') == 'research_hypothesis' else '问题', motivation.get('problem_observation', proposal.get('problem')))
    lines.extend(['#### 为什么重要', ''])
    add('为什么值得做', motivation.get('importance', proposal.get('why_it_matters')))
    add('现有方法的局限', motivation.get('existing_approach_limit'))
    add('希望取得的实质进展', motivation.get('expected_progress'))
    lines.extend(['#### Idea 怎样解决它', ''])
    # A cause explains the problem; the intervention describes the idea. Prefer
    # the current method after refinement so an abandoned proposal cannot leak back.
    add('问题成因', motivation.get('causal_explanation', proposal.get('hypothesis')))
    add('具体方法' if spec else '核心想法',
        (method.get('summary') or '\n'.join(method.get('changes', []))) if spec else proposal.get('intervention'))
    add('输入 → 输出', method.get('inputs', '') + ' → ' + method.get('outputs', '') if method else '')
    add('为什么能针对这个问题', motivation.get('why_this_method', proposal.get('mechanism')))
    add('与已有工作的差异', claim.get('claim') or spec.get('prior_art', {}).get('justification'))
    add('最简单的对照', motivation.get('simplest_alternative'))
    if not spec:
        sketch = proposal.get('feasibility_sketch', {})
        add('可用输入', sketch.get('inputs'))
        add('关键假设', sketch.get('key_assumption'))
        return '\n'.join(lines)
    lines.extend(['#### 第一项值得做的实验', ''])
    add('第一步验证', validation.get('summary') or validation.get('first_test', proposal.get('prediction')))
    add('值得继续的结果', validation.get('positive', claim.get('observable_consequence')))
    add('需要修改的结果', validation.get('negative', proposal.get('falsifier')))
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
