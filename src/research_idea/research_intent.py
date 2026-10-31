"""Source-linked research intent and explicit, revisable problem formulations.

These checks validate links, not the merit of a hypothesis. Models can reject a
premise or change a formulation without deleting what the user originally asked.
"""
from copy import deepcopy
import re

from .store import digest, now


def intent_sources(store, message=None):
    from .conversation import transcript
    sources = {'topic': store.get('topic') or ''}
    sources.update({m['id']: m['content'] for m in transcript(store) if m['role'] == 'user'})
    if message:
        sources[message['id']] = message['content']
    return sources


def validate_intent(value, sources):
    from .schema import RESEARCH_INTENT, validate
    validate(value, RESEARCH_INTENT)
    if not value['goal'].strip() or not value['goal_sources']:
        raise ValueError('Link the research goal to supplied user words')
    from .memory_scope import resolve_scope
    for statement, provenance in [(value['goal'], value['goal_sources']),
                                  *((c['statement'], c['sources']) for c in value['concerns'])]:
        source_words = '\n'.join(sources.get(s['message_id'], '') for s in provenance)
        research_content = re.search(r'研究|模型|训练|数据|课题|research|model|training|data|agent', statement, re.I)
        if not research_content and resolve_scope(statement, 'research', source_words) == 'turn':
            raise ValueError('Temporary presentation requests belong in turn memory, not research intent')
    ids = [c['id'] for c in value['concerns']]
    if len(ids) != len(set(ids)) or any(not i.strip() for i in ids):
        raise ValueError('Use unique concern IDs')
    for item in [dict(sources=value['goal_sources']), *value['concerns']]:
        if not item['sources']:
            raise ValueError('Link each user concern to its source')
        for source in item['sources']:
            quote = source['quote'].strip()
            if not quote or quote not in sources.get(source['message_id'], ''):
                raise ValueError('Intent sources must quote the supplied user message')
    for link in value['relationships']:
        if link['from_id'] not in ids or link['to_id'] not in ids or link['from_id'] == link['to_id']:
            raise ValueError('Link distinct existing concerns')
        if not link['reason'].strip():
            raise ValueError('Explain the interpreted relationship')


def intent_state(store, value, *, source_message_id='', reason='initial interpretation'):
    """Return an atomic state update; callers commit with the discussion itself."""
    previous = store.get('research_intent')
    if value == previous:
        return {}
    history = store.get('research_intent_history', [])
    history.append({'revision': len(history) + 1, 'time': now(),
                    'source_message_id': source_message_id, 'reason': reason,
                    'before': previous, 'after': deepcopy(value)})
    return {'research_intent': deepcopy(value), 'research_intent_history': history}


def ensure_intent(controller):
    """One cached intake call before discovery; later discussion edits it in place."""
    store = controller.store
    key = digest(store.get('topic'))
    if store.get('research_intent') and store.get('research_intent_topic_key') == key:
        return store.get('research_intent')
    from .conversation import memory_context
    memory = memory_context(store)
    supplied = {'topic': store.get('topic') or ''}
    for name in ('memory_sources', 'recent_history', 'retrieved_history', 'unreviewed_user_messages'):
        for message in memory.get(name, []):
            if message.get('role', 'user') == 'user':
                supplied[message['id']] = message['content']
    value = controller.task('interpret_research', {
        'topic': supplied['topic'], 'user_notes': controller.user_notes(),
        'user_sources': [{'id': k, 'content': v} for k, v in supplied.items()],
        'active_memory': memory.get('active_memory', [])},
        lambda result: validate_intent(result, supplied))
    store.set_many({**intent_state(store, value), 'research_intent_topic_key': key})
    modes = {'explore': '探索研究方向', 'refine': '深化已有想法', 'assess': '审视已有问题'}
    controller.progress('[concept] ' + modes[value['mode']] + ' · ' + value['interpretation'])
    return value


def validate_formulation(forms, cases, intent):
    if not forms and not intent:  # Legacy projects can still be resumed.
        return
    if len(forms) != 1:
        raise ValueError('Return one current formulation, retaining the individual analyses')
    from .schema import FORMULATION, validate
    form = forms[0]
    validate(form, FORMULATION)
    case = form['opportunity']
    for field in ('id', 'question', 'derivation', 'bottleneck_hypothesis', 'why_it_matters', 'prior_art_delta', 'research_need'):
        if not case[field].strip():
            raise ValueError('Explain the complete formulated research question')
    if case['basis'] == 'source_observation' and not case['evidence_ids']:
        raise ValueError('Observed formulations require source evidence; hypotheses may be proposed')
    ids = {c['id'] for c in cases}
    members = form['member_ids']
    if not members or len(set(members)) != len(members) or not set(members) <= ids:
        raise ValueError('Formulate from actual developed problem IDs')
    if form['strategy'] == 'synthesize' and len(members) < 2:
        raise ValueError('A synthesis must identify its contributing problems')
    if form['strategy'] == 'select' and (len(members) != 1 or form['opportunity']['id'] != members[0]):
        raise ValueError('Selection must identify the existing selected problem')
    if form['strategy'] != 'select' and form['opportunity']['id'] in ids:
        raise ValueError('Give a new formulation its own ID to preserve original analyses')
    for field in ('relationship_assessment', 'scope_reason'):
        if not form[field].strip():
            raise ValueError('Explain the problem relationship and scope choice')
    concerns = {c['id'] for c in (intent or {}).get('concerns', [])}
    dispositions = form['concern_disposition']
    if len(dispositions) != len(concerns) or {c['concern_id'] for c in dispositions} != concerns:
        raise ValueError('Account for every recorded user concern once')
    if any(not c['reason'].strip() for c in dispositions):
        raise ValueError('Explain each concern treatment; hypotheses may be revised')


def apply_formulation(problem, intent):
    result = deepcopy(problem)
    forms = result.get('formulation', [])
    if not forms:
        return result
    form = forms[0]
    # Selection uses the already-developed argument, never a weakened rewrite.
    if form['strategy'] == 'select':
        form['opportunity'] = deepcopy(next(c for c in result['opportunities']
                                           if c['id'] == form['member_ids'][0]))
    else:
        result['opportunities'].append(deepcopy(form['opportunity']))
    result['selected_problems'] = [{'opportunity_id': form['opportunity']['id'],
                                   'selection_reason': form['scope_reason']}]
    result['problem'] = form['opportunity']['question']
    result['research_frame']['research_question'] = result['problem']
    result['research_frame']['scope_connection'] = form['scope_reason']
    result['research_intent'] = deepcopy(intent)
    result['opportunity_types'] = list(dict.fromkeys(c['problem_origin'] for c in result['opportunities']))
    return result


def revised_intent(controller, result, message):
    updates = result.get('updated_intent', [])
    if len(updates) > 1:
        raise ValueError('Return zero or one revised research intent')
    if not updates:
        return {}
    validate_intent(updates[0], intent_sources(controller.store, message))
    # Revisions describe research content, never temporary style preferences.
    return intent_state(controller.store, updates[0], source_message_id=message['id'],
                        reason='user discussion')
