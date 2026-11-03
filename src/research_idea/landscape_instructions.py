"""Abstract breadth and question-driven depth; no novelty veto by metadata."""

SKIM = """
阅读每篇给定摘要，保留它对研究视野的贡献，不在这里淘汰研究问题。每篇给出一条简短记录：
problem=研究什么问题；approach=怎样回应；claimed_progress=作者声称取得的进展；conditions=摘要明确给出的条件，未提到时留空；
connection=对用户目标的联系或启发，推断用自然的“可能”表达；reading_question=只有细节会影响判断时提出具体补读问题，否则留空。
每项通常一句短话，整条约100–180中文字；不复制整段摘要，不生成完整论文卡。
relevance 是 direct/adjacent/unrelated/insufficient。相邻领域的不同术语也可能提供关键认识。每篇都保留记录，不为填数捏造贡献。
标题、名称、关键词相似只能提示需要比较；不能据此认定用户问题已被解决、idea撞车或应该放弃。
摘要主张也不等于已验证的普遍能力。不从未提及的内容推断方法缺陷，不把我们的解释归给作者。
research_mode=focused_question 时，围绕用户给定问题的已有回应与不同解释阅读，不改成寻找互不相关的新选题。
"""

SYNTHESIZE = """
把泛读记录综合成研究认识，供后续讨论持续使用。按问题或方法原理组织，不逐篇堆摘要。
background 解释用户目标与已有进展；approaches 梳理不同大类的作用原理、已取得的进展并引用 paper_ids；
connections 提出跨工作关系、共同条件、不同解释或值得探讨的后果。猜想可以大胆，但要说明为什么从已有进展自然引出。
coverage 解释已覆盖什么、哪里可能遗漏。数量多不代表路线齐全，不把没搜到等同于没人做过。
research_mode.kind=open_exploration 时，为比较不同重要问题提供视野；focused_question 时，保留用户具体问题，比较直接回应、不同叫法下的同一困难和相邻领域认识，不强凑多个新问题。
作者贡献按摘要主张表达；不得仅凭标题、方法名相似或摘要口号作重复/无价值判断。若担心实质重叠，指出需比较的问题、可用信息、机制条件和实际解决范围；让后续定向阅读回答，不能现在否决。
allow_supplement=true 时，只有缺失的重要路线、不同术语或相邻解释可能改变理解，才给最多两条简短英文学术检索词及具体 reason；否则 []。不是固定第二轮查重。
每条查询 purpose=strategy 使用用户策略时间窗，适合近期路线；purpose=lineage 用于追溯基础概念或代表原作，动态模式允许更早文献，仍遵循用户显式日期限制。不因近期窗口漏掉相邻领域已成熟的回应。
allow_supplement=false 时不再追加查询，保留有用认识与讨论问题。文献事实关联 supplied paper_ids，不生成 evidence_ids，泛读并非正文验证。
"""

COMMON = """
literature_landscape 是广泛摘要阅读形成的方法概览及逐篇笔记，不只包含选中正文阅读的论文。利用各条路线形成、修订问题；focused_abstracts 是当前问题相关的原摘要片段。
摘要记录属于作者主张；正文阅读结果提供实际细节；connections 属于跨论文分析或假设。不要混为一类。
遇到同名方法、相近标题或相似描述，先解释它们实际研究的问题与已知解决范围；这些相似本身不能成为放弃或缩小问题的理由。
需要决定是否实质重叠时，对比具体目标、可用信息、作用机制、成立条件、解决范围与核心贡献。方法相似可借鉴；问题与动机不同仍可有价值。不能通过否定原贡献制造缺口。
重要差别没有材料时，通过 research_requests / 阅读规划点名 paper_ids 或提出查询，读取改变判断的段落；没有疑问时直接推进，不追加固定审查。
research_mode.kind=focused_question 时，多个种子表示同一问题的不同解释、已有回应或研究切口，不是必须竞争的新课题；可以只有一个种子。保持用户目标，重构时解释依据。
"""

FEEDBACK = """
收到反馈后先定位改变了哪个判断，再决定材料动作。表达或推理衔接问题优先重用现有材料修订；不同原因解释先比较现有证据；
已知论文的方法、条件或贡献有争议时，research_requests 用其 paper_ids 与具体问题，query 留空，只补读对应段落；
缺少一条可能改变判断的路线、术语或对象时才填写 query 补搜。已有记录已回答时不重复请求。
literature_landscape.coverage_basis 记录旧概览的研究目标与查询范围。目标改变后重新判断哪些认识仍适用，不能把旧检索覆盖当成新目标已充分调研；也不因此自动重跑全部文献。
需要查资料时简短说明分歧、缺的具体信息以及它会改变哪个判断。source_work_done=true 后依据实际 reading_result 说明保留或修改了什么，修改相应问题与动机，用 reasoning_updates 记录有意义的判断变化。
用户不同意不是已推翻论文的证据，标题相似也不是已解决问题的证据。允许新解释与合理猜想，不增设固定审查或强制确认。
"""


def extend(instructions):
    instructions['skim_papers'] = SKIM
    instructions['synthesize_landscape'] = SYNTHESIZE
    for stage in ('screen_papers', 'explore_problems', 'plan_problem_reading', 'deepen_problem',
                  'reconsider_problems', 'map', 'discuss_direction', 'discuss_question', 'frame_question'):
        instructions[stage] += COMMON
    for stage in ('discuss_direction', 'discuss_question'):
        instructions[stage] += FEEDBACK

