"""Intent-aware reasoning; schema and state transitions live in separate modules."""
INTAKE = """
先理解用户需要怎样的研究帮助，不做文献判断或生成选题。
mode: explore=从宽方向发现问题；refine=已有相连的目标与想法，梳理完善整条论证；assess=审视一个已提出问题的必要性与前提。
goal 是希望推进的目标；concerns 是用户提出的关键需要或待检验假设。不要把猜想写成事实，也不要把一次表达/格式要求记成研究目标。
active_memory 中仍有效的研究纠正优先于旧原话；保留原话出处，不重新启用已被替换的要求。
每项目标/关切用 sources 关联 user_sources 中 message_id 和连续原话 quote（原始输入 ID=topic）。不要从论文或助手回答制造用户要求。
relationships 分清：alternative 是独立备选方向；joint 是同一目标需要兼顾的方面；depends_on 的 from_id 依赖 to_id；shared_cause 是可能共同原因的不同表现。关系是当前解读，可随讨论修订，不强凑因果或把两个困难当两个模块。
保留不同需要，不因某个最容易讨论就删掉其他；宽泛输入可以没有具体 concerns/relationships。interpretation 用一句通俗话解释如何推进，用户可在讨论中纠正。不设评分或确认步骤。当前产品止于研究问题、动机和主张，不承诺后续技术方案或实验。
"""
COMMON = """
research_intent 保存用户原目标、待检验假设和困难之间的关系；它不是科学事实，也不是不可修改的锚。
explore 模式比较不同重要问题；refine 模式先研究原想法各方面如何共同影响目标，不把相连困难自动拆成竞争选题；assess 模式考察前提和最强已有回应。
允许大胆提出更好的解释，允许文献推翻前提。区分用户目标与实现它的假设：否定一个假设，不等于删掉该目标。不要为了方便讨论，把仍需研究的核心困难假定已经解决，也不要擅自改成另一个更好写的问题。
独立方向可以选择；相连困难可以综合为一个问题；新证据可以重构问题。决定依据是对原目标的解释力，不是写作便利。不要机械合并、保留所有猜想或堆叠模块。聚焦时解释保留了什么、为什么可以暂不研究另一部分。
"""
SPECIFIC = {
'plan_search': """
通常三个不同方向的默认仅适用于 explore。已有连贯想法时，research_routes 可以围绕相连困难、它们如何共同作用及最接近的整体回应组织。queries 在原六项预算内兼顾各方面与关系检索，不只检索单独关键词；rationale 说明该查询能改变哪一个关系判断。
""",
'explore_problems': """
对 refine 输入，problem_seeds 可以是同一研究问题的不同解释或相互作用，不必凑出三个互斥选题。entry_reason 说明与用户关切以及其他种子的关系。深入阅读可以由这些种子分工，最终可以回到整体问题。
""",
'plan_problem_reading': """
同时检查当前种子与 research_intent 其他关切的关系：已有回应是否同时处理了这些需要，还是依赖另一个方面已经成立？在现有两个阅读名额内选择能改变该判断的来源与段落，不增加固定检索轮次。
""",
'deepen_problem': """
related_problem_seeds 是同轮其他问题。承接 research_intent 中相关需要，说明本问题与它们是竞争、前提还是共同影响，不能通过假定另一核心困难已解决来制造优先级。可以局部深入，但 research_need 应回接整体目标。
""",
'map': """
先保留全部 problem_cases 与逐项 comparisons；selected_problems 仍标出已有案例中的优先参考项。
随后 formulation 给出一个最终问题表述（旧流程无 research_intent 时可 []）：strategy=select 选一个已有问题；synthesize 综合多个相关问题；reframe 根据文献重构问题。
member_ids 标出实际贡献案例。select 沿用该案例 ID 和论证；synthesize/reframe 用新 ID 写完整 opportunity，明确已有回应、关键关系、为何重要，不拼接标题。relationship_assessment 解释困难之间实际是什么关系；scope_reason 解释为何这份表述最能推进原目标。
concern_disposition 逐一记录所有 research_intent.concerns：central=主问题保留，context=作为背景/条件但非默认已解决，revised=根据材料修订原假设，deferred=暂不研究，并写具体原因。可以大胆修订，不强制每项都 central，不以已有相关论文为由直接放弃。
程序保存个别问题分析，用 formulation 作为当前研究主张的起点；不要在旧 selected_problems 中填新 ID。
""",
'frame_question': """
从 discussion_handoff.research_intent 和当前问题版本出发，而非只扩写一个局部案例。formulation 若存在，沿着其关系判断和范围理由写；讨论使它失效时，以用户最新问题版本重新梳理各关切如何作用。原假设被修订时自然解释原因，不把当前叙述当成用户原话。背景与问题之间应看得见原目标为何需要解决这个困难。正文不用输出内部 ID 或逐项检查表。
"""
}
DISCUSSION = """
updated_intent：仅当用户澄清或改变研究目标、假设、关切关系时返回一个完整更新版本，否则 []；沿用未变 concern ID，来源引用本轮 current_user_message 或已提供的用户原话。保留仍相关关切，临时格式要求不进入研究意图。论文引起的假设调整写入问题论证及 reasoning_updates，不伪造用户改了目标。
若更新问题/选择，也重新解释它与每项用户关切的关系；不能只答“记住了”。source_work_done 时返回本轮最终完整更新。
"""


def extend(instructions):
    instructions['interpret_research'] = INTAKE
    for stage in (*SPECIFIC, 'reconsider_problems', 'discuss_direction', 'discuss_question'):
        instructions[stage] += COMMON + SPECIFIC.get(stage, '')
    for stage in ('discuss_direction', 'discuss_question'):
        instructions[stage] += DISCUSSION
