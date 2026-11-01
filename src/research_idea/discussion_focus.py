"""One optional conversational question, separate from research decisions."""
from copy import deepcopy


INSTRUCTIONS = """
讨论先回应本轮需要，不把每次答复变成问卷。需要用户判断才能改变研究理解时，discussion_focus
给零或一个条目：question 是一个通俗、可回答的关键问题，why_it_matters 说明不同回答会怎样改变
问题成因、重要性或研究重点。answer 先解释必要背景，不重复 question；程序会把问题显示在答复末尾。
不为维持互动而问，不把预定结论包装成诱导用户同意的选择题；允许不知道、不同意或另一种解释。
previous_discussion_focus 是上一轮助手实际提出的问题，不是用户要求或已确认判断。结合它理解
“后者”“不一定”等短回复；用户换话题时回应新话题。先区分用户观察、猜想和选择，再更新研究判断。
用户说不懂或不知道时，先把争议解释清楚；必要时用简短对照帮助理解，不要求用户先懂算法。
优先讨论会改变选题的分歧：困难是否影响原目标、最强已有回应能否消除它、另一种原因是否更合理。
文献能回答的问题由系统补读；需要用户经验或取舍时才追问。得到回答后修改受影响的因果解释与动机，
不要只把新意见追加到旧稿末尾。
用户要求总结、检索、直接分析或不再追问时直接完成，discussion_focus=[]；不要延迟交付。
问题只服务背景、现有方法、问题与动机，不引导用户填写技术方案或实验计划。每次 question
不超过400字符，why_it_matters不超过300字符；没有必要追问就[]。未回答不阻止 /continue。
"""

SCOPE_INSTRUCTIONS = """
遇到最接近工作或调整范围时，回到原研究目标：已有工作实际覆盖哪部分，仍保留的困难为什么重要。
不要为避开每篇论文不断追加对象、场景、时间等限制。缩小范围应有独立的科学或实际理由，解释它
仍能揭示什么重要问题；小范围本身不是缺点。若限制只为制造“无人做过”，撤回该限制并重新考虑问题。
确有核心重叠就承认并调整，不用改名字或加条件挽救新颖性。用户提出限制的问句不等于选择。
在既有修订理由中说明依据和保留下来的价值：讨论使用reasoning_updates，重新构思用changes.reason，
深入用revision_reason，选择用scope_reason/selection_reason。仅实际改变判断时记录，不增加固定审查或评分。
"""


def validate_focus(result):
    items = result.get('discussion_focus', [])  # Older saved pending turns have none.
    if len(items) > 1:
        raise ValueError('Ask at most one focused discussion question')
    for item in items:
        for key, limit in (('question', 400), ('why_it_matters', 300)):
            if not item[key].strip() or len(item[key]) > limit:
                raise ValueError(f'Discussion {key} must be nonempty and at most {limit} characters')


def previous_focus(checkpoint):
    """Only the current, still-open checkpoint owns this conversational hint."""
    if checkpoint.get('state') != 'discussing':
        return []
    return deepcopy(checkpoint.get('discussion_focus', []))


def rendered_answer(result):
    question = (result.get('discussion_focus') or [{}])[0].get('question', '').strip()
    answer = result['answer'].rstrip()
    if question and question not in answer:
        answer += '\n\n' + question
    return answer


def saved_focus(result, message):
    return [{**deepcopy(item), 'origin': 'assistant_question',
             'in_reply_to': message['id']} for item in result.get('discussion_focus', [])]
