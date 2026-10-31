"""Carry paper-level understanding into question discovery, with quote provenance."""
from copy import deepcopy

from .store import digest

READING_INSTRUCTIONS = """
针对 reading_question 阅读给定原文，帮助研究者理解已有回应，再判断它怎样影响 user_goal 与 research_intent。只使用当前 excerpt，不声称读过未提供的部分。
同一次阅读返回 observations（最多六条连续原文引文）和 reading_points（通常六至十条有内容的解释，最多十二条，不为填栏目编造）。
reading_points.role 可用 research_problem / prior_response / core_intuition / input / information_source / processing / output / research_impact。
先说原论文具体要解决什么、为什么重要，以及已有主要思路实际做到了哪里。核心 intuition 解释哪个原因使方法可能有效；输入→处理→输出说明实际操作，不复述模块名称。尤其说明标签、反馈、状态或其他关键输入从哪里取得、在哪个阶段可用、其可靠性依据是什么。读到的只有需求而没有取得程序，就说清这一具体区别，不凭空补出接口。
research_impact 回答：它让我们对当前困难增加、修改或确认了什么认识？它是在回应原问题、修正一个原因猜想，还是提示成功使用后可能产生新问题？不要强迫每篇论文有缺点，也不要把论文的小场景直接当作我们的研究范围。问题的重要性可以综合多篇后形成，不必每篇都独立产出新选题。
information_type 四类分开：paper_claim=本文明确报告的方法、主张或结果；prior_literature=本文对已有文献的转述，不能假装已经核查被引原作；reasoned_inference=基于当前材料的合理推断；hypothesis=仍需研究的猜想。前两类必须关联原文，引文仍分别标 author_claim/reported_result/limitation；后两类也关联其实际前提，可无引文但不能冒充论文事实。
observation_indices 用字符串形式的零起始索引关联本次 observations，例如 ["0", "2"]；只指向实际用到的摘录。程序随后转换为可追溯的证据和论文链接。
有助于理解时用原文中的例子连起输入、处理、输出；自行构造的示意明确写为示意并归入推断，不能编造真实案例、数据或性能。理论或分析论文按其论证结构理解，不硬套算法流水线。未读到的信息可以略去；若影响判断，在解释中说清缺少的是哪一步，不启动固定补读循环。
用自然、清楚、有信息量的中文，每条围绕一个判断展开。不要求模仿某个人，不堆术语；必要公式解释每个符号及直觉，不为形式插入公式或图。不生成新方法、实验计划或研究质量评分。
"""


def validate_reading_points(result):
    observations = result['observations']
    for point in result.get('reading_points', []):
        indices = point['observation_indices']
        if any(index not in {str(i) for i in range(len(observations))} for index in indices):
            raise ValueError('Reading points must refer to observations from this source call')
        if point['information_type'] in {'paper_claim', 'prior_literature'} and not indices:
            raise ValueError('Source descriptions must link to their quoted observations')
        if not point['text'].strip():
            raise ValueError('Explain the reading point')


def filter_reading_points(result, accepted):
    """After quote repair, drop dependent explanations rather than invent support."""
    positions = {digest(obs): str(i) for i, obs in enumerate(accepted)}
    remap = {str(i): positions[digest(obs)] for i, obs in enumerate(result['observations'])
             if digest(obs) in positions}
    points = []
    for point in result.get('reading_points', []):
        indices = point['observation_indices']
        if not set(indices) <= remap.keys():
            continue
        points.append({**deepcopy(point), 'observation_indices': [remap[i] for i in indices]})
    return points


def save_understanding(controller, reading, result, generated, paper):
    # make_evidence deduplicates observations and may normalize PDF whitespace.
    # Match by submitted observation, not by a position in its deduplicated list.
    by_observation = {}
    for evidence in generated:
        observation = {key: evidence[key] for key in ('statement', 'quote', 'kind', 'conditions', 'source_section')}
        observation['quote'] = evidence.get('submitted_quote', evidence['quote'])
        by_observation[digest(observation)] = evidence['id']
    indices = {str(i): by_observation[digest(obs)] for i, obs in enumerate(result['observations'])}
    points = [{key: deepcopy(value) for key, value in point.items() if key != 'observation_indices'} |
              {'evidence_ids': list(dict.fromkeys(indices[i] for i in point['observation_indices']))}
              for point in result.get('reading_points', [])]
    reading = {**reading, 'reading_points': points, 'title': paper['title'],
               'intent_key': digest(controller.store.get('research_intent')),
               'guidance_key': controller.guidance_keys['read_problem_source']}
    journal = controller.store.get('source_understandings', {})
    key = digest([paper['id'], reading['scope'], reading['reading_question']])
    journal.pop(key, None)
    journal[key] = deepcopy(reading)
    controller.store.set('source_understandings', journal)
    return reading


def current_understandings(controller):
    """Exclude changed sources, expired guidance and interpretations of an old goal."""
    store = controller.store
    papers = {p['id']: p for p in store.rows('papers')}
    evidence = {e['id']: e for e in store.rows('evidence')}
    intent_key = digest(store.get('research_intent'))
    current = []
    for reading in store.get('source_understandings', {}).values():
        paper = papers.get(reading['paper_id'])
        if (not paper or reading['source_hash'] != digest(paper.get('text') or paper.get('abstract', ''))
                or reading['intent_key'] != intent_key
                or reading['guidance_key'] != controller.guidance_keys['read_problem_source']):
            continue
        if any(eid not in evidence or evidence[eid]['paper_id'] != paper['id']
               for eid in reading['evidence_ids']):
            continue
        current.append({key: deepcopy(reading[key]) for key in
                        ('paper_id', 'reading_question', 'reading_points', 'evidence_ids')})
    return current[-12:]


ROLE_LABELS = {'research_problem': '论文要解决什么', 'prior_response': '已有方法做到哪里',
    'core_intuition': '为什么可能有效', 'input': '需要什么输入', 'information_source': '关键信息怎样取得',
    'processing': '具体怎样处理', 'output': '最终得到什么', 'research_impact': '对当前研究的启发'}
TYPE_LABELS = {'paper_claim': '论文所述', 'prior_literature': '论文转述的前作',
               'reasoned_inference': '分析推断', 'hypothesis': '研究猜想'}


def understanding_text(reading, citations=None):
    heading = citations.paper(reading['paper_id']) if citations else reading.get('title', '论文理解')
    lines = [heading]
    # Lead with relevance and intuition; the full pipeline stays in the reading record.
    for role in ('research_impact', 'core_intuition', 'information_source', 'processing'):
        for point in reading.get('reading_points', []):
            if point['role'] != role:
                continue
            text = point['text']
            if citations:
                text = citations.text(text, compact=True)
            lines.append(f"**{ROLE_LABELS[role]} · {TYPE_LABELS[point['information_type']]}**\n\n{text}")
    return '\n\n'.join(lines)
