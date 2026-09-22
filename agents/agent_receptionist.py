"""Receptionist agent — keeps the front desk honest and answers the queue.

The live widget is served by ``receptionist.py``. This crew member does the part that
needs a schedule rather than a visitor:

1. **Knowledge-base audit** — asks the knowledge file the questions real visitors ask
   (pricing, timing, samples, process, contact, guarantees, reviews) and reports every
   question it could not answer from verified facts. Unanswered questions become a
   to-do list for the owner, not an invented answer.
2. **Queue triage** — reads open conversations, flags the ones that asked for a human,
   left contact details, or arrived through a review link, and prepares a short
   suggested reply for the owner to edit and send. Nothing is sent from here.
"""

from crew.skills_loader import load_skill, rules

import json

try:
    from crew.crew import CrewError
except Exception:  # pragma: no cover
    class CrewError(Exception):
        pass

from crew.business import BRAIN_VERSION, MIN_SCORE, VOICE, detect_intent, load_knowledge, match_answer
from web.receptionist import threads, transcript, _store

# The questions visitors actually ask, phrased the way they type them.
# The CRO playbook's own analysis framework, reduced to the four questions a front desk
# answers all day. Coverage is reported per principle instead of as one percentage.
CRO_PRINCIPLES = {
    'value proposition': 'does the visitor learn what the studio does and for whom',
    'pricing clarity': 'can a visitor get a real number without talking to anyone',
    'process and timing': 'does the visitor know what happens after they say hello',
    'reply path': 'can the visitor reach a human in one step, from any page',
    'limits and honesty': "are the studio's limits, consent rules and opt-out stated plainly",
}

VISITOR_QUESTIONS = [
    ('how much does a website cost?', 'pricing', 'pricing clarity'),
    ('what is your price for a 5 page site', 'pricing', 'pricing clarity'),
    ('is there a cheaper option', 'pricing', 'pricing clarity'),
    ('how long does it take to build', 'timeline', 'process and timing'),
    ('when can you start', 'timeline', 'process and timing'),
    ('can i see samples of your work', 'samples', 'value proposition'),
    ('do you use figma', 'samples', 'value proposition'),
    ('what is included in the price', 'includes', 'value proposition'),
    ('do you handle hosting and the domain', 'includes', 'value proposition'),
    ('how do i contact you', 'contact', 'reply path'),
    ('can i talk to a person', 'human', 'reply path'),
    ('where does your business data come from', 'data', 'value proposition'),
    ('how do you contact businesses', 'data', 'limits and honesty'),
    ('can a business opt out', 'data', 'limits and honesty'),
    ('what is a review link', 'review link', 'value proposition'),
    ('is the concept page the real website', 'review link', 'value proposition'),
    ('do you guarantee results', 'guarantee', 'limits and honesty'),
    ('is my data secure', 'data', 'limits and honesty'),
]


def kb_audit(ctx):
    topics = load_knowledge()
    covered, unanswered = [], []
    by_principle = {name: {'answered': 0, 'asked': 0} for name in CRO_PRINCIPLES}
    for question, expected, principle in VISITOR_QUESTIONS:
        topic, matched_q, answer, score = match_answer(question, topics)
        intent = detect_intent(question, topic, score)
        ok = score >= MIN_SCORE and bool(answer) or intent in ('human', 'new_project', 'greeting')
        bucket = by_principle.setdefault(principle, {'answered': 0, 'asked': 0})
        bucket['asked'] += 1
        bucket['answered'] += 1 if ok else 0
        (covered if ok else unanswered).append({'question': question, 'expected': expected,
                                                'principle': principle,
                                                'matched_topic': topic or '', 'score': round(score, 2)})
        ctx.receipt('kb-check', f'"{question}" → {"answered from " + str(topic) if ok else "NOT covered"} '
                                f'(match {round(score, 2)})')
    coverage = round(100 * len(covered) / max(1, len(VISITOR_QUESTIONS)))
    playbook = load_skill('cro')
    if playbook:
        weak = [name for name, row in by_principle.items() if row['asked'] and row['answered'] < row['asked']]
        ctx.receipt('playbook', 'cro playbook applied: the question battery is grouped by its four front-desk '
                                f"principles ({', '.join(CRO_PRINCIPLES)}). "
                                + (f"Needs attention: {', '.join(weak)}." if weak else 'All principles covered.'),
                    evidence=str(playbook.get('path') or 'skills/vendor/cro/SKILL.md'))
        ctx.artifact('cro-coverage', 'Front desk — coverage by CRO principle',
                     '\n'.join(f"- {name}: {row['answered']}/{row['asked']} questions answered from published facts"
                                for name, row in by_principle.items()) +
                     '\n\nA principle with fewer answers than questions is a knowledge-base gap, not a bug: '
                     'the front desk hands those to you rather than guessing.')
    if unanswered:
        ctx.artifact('kb-gaps', 'Knowledge base — questions with no verified answer',
                     '\n'.join(f"- {row['question']}  (expected topic: {row['expected']})" for row in unanswered) +
                     '\n\nAdd verified facts to knowledge/reachmark.md for these. The receptionist will keep saying '
                     '“I do not have a verified answer” until you do — which is the correct behaviour.')
    return {'topics': [t['topic'] for t in topics], 'covered': covered, 'unanswered': unanswered,
            'coverage': coverage, 'by_principle': by_principle,
            'playbook': 'cro' if playbook else ''}


def queue_review(ctx):
    open_threads = threads(ctx.db, limit=25, status='open')
    flagged, suggested = [], []
    for thread in open_threads:
        lines = transcript(ctx.db, thread['id'], limit=12)
        if not lines:
            continue
        visitor_lines = [line['text'] for line in lines if line['role'] == 'visitor']
        assistant_lines = [line['text'] for line in lines if line['role'] == 'assistant']
        needs_human = bool(thread.get('handoff'))
        captured = bool(thread.get('email'))
        question = visitor_lines[0] if visitor_lines else ''
        if needs_human or captured:
            flagged.append({'thread_id': thread['id'], 'intent': thread.get('intent'),
                            'email': thread.get('email') or '', 'business': thread.get('business') or '',
                            'needs_human': needs_human, 'captured': captured, 'question': question[:200]})
            suggestion = _suggest(thread, question, assistant_lines)
            suggested.append({'thread_id': thread['id'], 'to': thread.get('email') or '',
                              'subject': f"Re: your question about {thread.get('business') or 'a website'}",
                              'body': suggestion})
            ctx.receipt('queue', f"Thread {thread['id'][:6]} — {'asked for a human' if needs_human else 'left contact details'}; "
                                 f"a suggested reply is ready for you to edit.")
    return {'open': len(open_threads), 'flagged': flagged, 'suggested': suggested}


def _suggest(thread, question, assistant_lines):
    topic, matched_q, answer, score = match_answer(question)
    opener = f"Thanks for reaching out about {question[:120]}" if question else 'Thanks for your message'
    body = [opener.rstrip('?') + '.', '']
    if answer and score >= MIN_SCORE:
        body += ['Here is what is confirmed:', answer, '']
    body += ['If you tell me a little more about the business (what you do, roughly how many pages, and whether you '
             'already own a domain), I can come back with scope and a fixed price.', '',
             VOICE['signoff']]
    return '\n'.join(body)[:2000]


def run(ctx):
    audit = kb_audit(ctx)
    review = queue_review(ctx)
    summary = (f'Front desk checked: knowledge base answers {len(audit["covered"])}/{len(audit["covered"]) + len(audit["unanswered"])} '
               f'common questions from verified facts ({audit["coverage"]}% coverage); '
               f'{review["open"]} open conversation(s), {len(review["flagged"])} needing your attention.')
    ctx.emit(summary)
    ctx.artifact('receptionist-report', 'Front desk report',
                 json.dumps({'coverage_percent': audit['coverage'], 'unanswered': audit['unanswered'],
                             'conversations': review['flagged']}, indent=2),
                 meta={'brain': BRAIN_VERSION})
    for draft in review['suggested'][:5]:
        ctx.artifact('reply-draft', f"Suggested reply → {draft['to'] or 'conversation'}", draft['body'],
                     meta={'thread_id': draft['thread_id']})
    return {'summary': summary, 'data': {'coverage': audit['coverage'], 'unanswered': audit['unanswered'],
                                         'by_principle': audit.get('by_principle', {}),
                                         'playbooks': [audit.get('playbook', 'cro')],
                                         'conversations': review['flagged'],
                                         'suggested_replies': len(review['suggested'])}}
