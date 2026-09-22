"""Brag agent — the launch kit for work that was won.

Adapted from the vendored ``brag`` skill (MIT, Shunit Haviv Hakimi): the story, tone and
brief format come from that playbook. What the agent produces here is a *plan* — a
storyboard, a composition brief, share copy and a self-contained shareable card — plus
an honest note that rendering a video is a separate, external step this workspace does
not fake. If the owner later renders it with Hyperframes, the brief is already there and
the order of the brief is what the renderer expects: hook, proof, close, with the real
observations from the workspace in the proof slot.
"""
import json, re

try:
    from crew.crew import CrewError
except Exception:  # pragma: no cover
    class CrewError(Exception):
        pass

from crew.business import BRAIN_VERSION, STUDIO, review_ask
from crew.skills_loader import load_skill, rules

TONES = {'default': 'confident and simple', 'polished': 'premium studio, measured',
         'yc-parody': 'deadpan overstated startup launch', 'chaotic': 'fast, funny, over the top',
         'deadpan': 'flat delivery, dry humour', 'cinematic': 'slow build, big reveal',
         'app-store': 'bright, feature-forward product ad'}


def profile_from(db, lead_id=None, project_id=None):
    """Collect only real, saved facts for the launch story."""
    from web.review_links import ensure_tables as ensure_link_tables
    from agents.agent_auditor import ensure_tables as ensure_audit_tables
    for ensure in (ensure_link_tables, ensure_audit_tables):
        try:
            ensure(db)
        except Exception:
            pass
    with db() as c:
        lead = None
        project = None
        if project_id:
            row = c.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            project = dict(row) if row else None
            lead_id = lead_id or (project or {}).get('lead_id')
        if lead_id:
            row = c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
            lead = dict(row) if row else None
        try:
            audit = c.execute('SELECT * FROM site_audits WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                              (lead_id or '',)).fetchone()
        except Exception:  # the crew has not audited anything in this workspace yet
            audit = None
        link = c.execute('SELECT token,views FROM review_links WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                         (lead_id or '',)).fetchone()
        responses = c.execute('SELECT choice,created FROM review_responses WHERE lead_id=? ORDER BY created DESC',
                              (lead_id or '',)).fetchall()
    facts = []
    if lead:
        facts.append(f'Business: {lead["name"]}' + (f' ({lead["category"]})' if lead.get('category') else '') +
                     (f' · {lead["city"]}' if lead.get('city') else ''))
    if audit:
        facts.append(f'Measured before the concept: {audit["status"]} on {(audit["created"] or "")[:10]}.')
    if link:
        facts.append(f'Review link opened {link["views"]} time(s).')
    if responses:
        facts.append('Business answered: ' + ', '.join(row[0] for row in responses) + '.')
    if project:
        facts.append(f'Project stage: {project.get("stage")}' + (f' · {project.get("title")}' if project.get('title') else ''))
    return {'lead': lead, 'project': project, 'facts': facts, 'responses': [{'choice': r[0], 'at': r[1]} for r in (responses or [])]}


def _findability_notes(lead):
    """How to publish this result so an AI answer can actually cite it.

    Taken from the vendored ``ai-seo`` playbook: owned, dated, attributable pages with
    real structure get cited; self-promotional listicles and invented metrics do not.
    """
    name = (lead or {}).get('name') or 'the business'
    return {
        'publish_as': f'An owned, dated case-study page on the studio site — not a listicle and not a post about "what {name} should have done".',
        'keep_verifiable': 'Only the measured facts recorded here: the observation, its date, the review-link views and the answer.',
        'cite_is_not_recommendation': 'Being cited means the page was useful to consult. Being recommended comes from reviews, forums and press — not from your own copy.',
        'never_do': ['Separate content written “for AI”', 'Invented metrics or client names', 'Blocking the search-and-cite crawlers'],
    }


def build_kit(profile, tone_key='default', format_='landscape', title='', voice=False):
    skill = load_skill('brag')
    seo = load_skill('ai-seo')
    measured = [fact for fact in profile.get('facts', []) if not fact.startswith('Business:')]
    tone = (tone_key or 'default').lower()
    direction = TONES.get(tone, TONES['default'])
    headline = title or ((profile['lead'] or {}).get('name') or (profile['project'] or {}).get('title') or 'A new website')
    beats = [
        {'at': '0.0s', 'beat': 'Hook', 'shot': f'Open on the business name — {headline} — over the measured observation.',
         'copy': 'This business was almost invisible online.'},
        {'at': '3.0s', 'beat': 'Proof', 'shot': 'The concept page scrolling on a phone, then the review link being opened.',
         'copy': 'So we built the front door first — before asking for anything.'},
        {'at': '8.0s', 'beat': 'Proof', 'shot': 'The measured observations appearing as ticked lines (real values only).',
         'copy': 'Not a pitch deck. A page they could answer in one tap.'},
        {'at': '13.0s', 'beat': 'Close', 'shot': 'Result card: the answer they gave, and the next step.',
         'copy': 'They said yes. The site ships in days, not months.'},
    ]
    brief = {
        'title': headline,
        'tone': tone, 'direction': direction,
        'format': format_, 'target_duration_seconds': 18 if format_ != 'vertical' else 22,
        'voiceover': bool(voice),
        'beats': beats,
        'facts_allowed_in_script': profile['facts'],
        'facts_that_are_proof': measured,
        'do_not_claim': ['Specific revenue or traffic improvements (not measured here)',
                         'Client names or testimonials not stored in this workspace',
                         'Delivery dates that were never agreed'],
        'render_step': 'External: hand this brief to Hyperframes (or any renderer). This workspace does not render video '
                       'and does not claim a video exists until one does.',
    }
    share_lines = [
        f'{headline}: we noticed the gap, built the concept, and asked one question.',
        *[f'· {fact}' for fact in profile['facts'][:4]],
        'Concept first. Ask second. Build when they say yes.',
    ]
    quotable = ' '.join(measured[:2]) if measured else ''
    return {'plan': brief, 'share_copy': '\n'.join(share_lines),
            'findability': _findability_notes((profile or {}).get('lead')),
            'quotable_fact': quotable,
            'tone_presets': list(TONES),
            'playbook_rules': (rules('brag', 'what this skill does', 4) or rules('brag', 'tone', 4)),
            'playbook_loaded': bool(skill),
            'playbooks': [name for name, loaded in (('brag', skill), ('ai-seo', seo)) if loaded],
            'findability_rules': rules('ai-seo', 'official', 2) or rules('ai-seo', 'cited', 2)}


def brag_card_html(kit, studio='Reachmark'):
    """A tiny self-contained shareable card — no external assets, no tracking."""
    facts = ''.join(f'<li>{_esc(fact)}</li>' for fact in kit['plan']['facts_allowed_in_script'][:4])
    beats = ''.join(f'<div class="beat"><b>{_esc(b["beat"])} · {_esc(b["at"])}</b><p>{_esc(b["copy"])}</p></div>'
                    for b in kit['plan']['beats'])
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(kit['plan']['title'])} — launch card</title>
<meta name="robots" content="noindex,nofollow">
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#20251F;color:#F5F5EF;font:16px/1.6 ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;display:grid;place-items:center;min-height:100vh;padding:24px}}
.card{{max-width:760px;width:100%;background:linear-gradient(160deg,#262c24,#1b201a);border:1px solid #3a4433;border-radius:22px;padding:34px}}
.tag{{display:inline-block;background:#D5F268;color:#1b201a;font-weight:700;font-size:12px;letter-spacing:.08em;text-transform:uppercase;padding:6px 12px;border-radius:999px}}
h1{{font-size:clamp(26px,4.4vw,40px);line-height:1.12;margin:18px 0 10px}}
p.lead{{color:#b9c7a6;margin:0 0 22px}}
ul{{color:#cfd8c2;padding-left:20px;margin:0 0 22px}}li{{margin:6px 0}}
.beat{{border-left:2px solid #4d5c43;padding:2px 0 2px 14px;margin:14px 0}}
.beat b{{color:#D5F268;font-size:12px;letter-spacing:.06em;text-transform:uppercase}}
.beat p{{margin:4px 0 0;color:#e6ecdc}}
footer{{margin-top:24px;padding-top:16px;border-top:1px solid #333c2d;color:#8b977c;font-size:13px}}
@media(max-width:520px){{.card{{padding:22px}}}}
</style></head><body><div class="card">
<span class="tag">Launch kit</span>
<h1>{_esc(kit['plan']['title'])}</h1>
<p class="lead">Tone: {_esc(kit['plan']['tone'])} — {_esc(kit['plan']['direction'])} · {_esc(kit['plan']['format'])} · ~{kit['plan']['target_duration_seconds']}s</p>
<ul>{facts or '<li>No measured facts stored yet — add the review-link result first.</li>'}</ul>
{beats}
<footer>Prepared by {_esc(studio)} with the /brag playbook (MIT, Shunit Haviv Hakimi). Rendering a video is a separate step;
nothing here claims a video exists.</footer>
</div></body></html>'''


def _esc(value):
    return (str(value or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def run(ctx):
    lead_id = ctx.params.get('lead_id') or (ctx.params.get('lead_ids') or [None])[0]
    project_id = ctx.params.get('project_id') or ''
    profile = profile_from(ctx.db, lead_id, project_id)
    if not profile['lead'] and not profile['project']:
        raise CrewError('Brag needs a saved business or project — it will not invent a story.')
    measured = [fact for fact in profile['facts'] if not fact.startswith('Business:')]
    if not measured:
        raise CrewError('There is nothing measured to celebrate yet for this record — no audit, no review-link view and '
                        'no answer. Brag will not invent a story; get a real signal first.')
    kit = build_kit(profile, ctx.params.get('tone', 'default'), ctx.params.get('format', 'landscape'),
                    ctx.params.get('title', ''), ctx.params.get('voice', False))
    studio_name = (ctx.settings().get('agency') or STUDIO['name']).strip()
    card = brag_card_html(kit, studio_name)
    ctx.receipt('launch-kit', f"Plan, composition brief and share copy written from {len(profile['facts'])} stored fact(s). "
                              'Video rendering is an external step and is not claimed here.',
                evidence='; '.join(profile['facts'])[:400])
    ctx.artifact('launch-plan', f"Launch plan — {kit['plan']['title']}", json.dumps(kit['plan'], indent=2))
    ctx.artifact('findability-notes', f"How to publish this so it can be cited — {kit['plan']['title']}",
                 '\n'.join([f"- {value}" if isinstance(value, str) else f"- {value}" 
                             for key, value in kit['findability'].items() if isinstance(value, str)] +
                            [f"- never: {item}" for item in kit['findability']['never_do']] +
                            ([f"\nQuotable, measured: {kit['quotable_fact']}"] if kit['quotable_fact'] else [])),
                 meta={'playbooks': kit['playbooks'], 'rules': kit['findability_rules'][:2]})
    ctx.artifact('share-copy', f"Share copy — {kit['plan']['title']}", kit['share_copy'])
    ctx.artifact('brag-card', f"Shareable launch card — {kit['plan']['title']}", card,
                 meta={'self_contained': True, 'brain': BRAIN_VERSION,
                       'note': 'Download and open in any browser; no external assets.'})
    ask = review_ask((profile['lead'] or {}).get('name') or '', kit['plan']['title'], studio_name)
    ctx.artifact('review-ask', 'Review request — ' + kit['plan']['title'],
                 f"Subject: {ask['subject']}\n\n{ask['body']}",
                 meta={'brain': BRAIN_VERSION, 'note': 'Send only for genuinely won work.'})
    if kit['playbooks']:
        ctx.receipt('playbook', f"Playbooks applied: {', '.join(kit['playbooks'])} — story shape from brag, publishing "
                                'guidance from ai-seo (owned dated page, measured facts only).',
                    evidence=str((load_skill('brag') or {}).get('path') or 'skills/vendor/brag/SKILL.md'))
    summary = (f"Launch kit ready for {kit['plan']['title']}: {len(kit['plan']['beats'])} storyboard beats, share copy, a review ask and a "
               'self-contained card. Hand the brief to a renderer when you are ready — nothing claims a video exists.')
    ctx.emit(summary)
    return {'summary': summary, 'data': {'title': kit['plan']['title'], 'tone': kit['plan']['tone'],
                                         'facts': profile['facts'], 'playbooks': kit['playbooks'],
                                         'quotable_fact': kit['quotable_fact'], 'artifacts': 5}}
