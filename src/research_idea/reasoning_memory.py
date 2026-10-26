"""Source-linked reasons for revisions, separate from user requirements."""
from copy import deepcopy
from .store import digest


def reasoning_context(store):
    topic_key = digest(store.get('topic'))
    return [deepcopy(note) for note in store.get('reasoning_notes', [])
            if note['active'] and note['topic_key'] == topic_key]


def revised_reasoning(store, updates, message, checkpoint):
    """Prepare an atomic update; questions and assistant judgments are not consent."""
    notes = deepcopy(store.get('reasoning_notes', []))
    current = {n['id']: n for n in reasoning_context(store)}
    topic_key = digest(store.get('topic'))
    for index, update in enumerate(updates):
        if not set(update['replaces']) <= current.keys():
            raise ValueError('Replace only supplied reasoning notes')
        quote = update['user_quote']
        if quote and quote not in message['content']:
            raise ValueError('User objections must quote the current message exactly')
        if update['kind'] == 'user_objection' and not quote:
            raise ValueError('Attribute a user objection to their actual words')
        identifier = 'reason_' + digest([message['id'], index, update])[:12]
        for note in notes:
            if note['id'] in update['replaces']:
                note.update(active=False, replaced_by=identifier)
        if any(n['id'] == identifier for n in notes):
            continue
        notes.append({**deepcopy(update), 'id': identifier, 'active': True,
            'topic_key': topic_key, 'source_message_id': message['id'],
            'checkpoint_id': checkpoint.get('checkpoint_id'),
            'origin': 'user_quote' if update['kind'] == 'user_objection' else 'assistant_analysis'})
    return notes
