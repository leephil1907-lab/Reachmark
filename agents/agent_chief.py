"""Chief — the crew member who takes the owner's orders in plain words.

Chief lives on the workspace AI-crew page as a conversation. Deterministic
commands run crew skills directly (status, leads, audit, brand, concept,
gaps, showcase); anything else is offered to the configured local model
(Ollama by default) with crew context, falling back to the command list when
no provider answers. Chief reads and reports only — it never sends e-mail,
SMS, or shares anything outbound.
"""
import re

COMMANDS = ('help', 'status', 'leads', 'audit', 'brand', 'concept', 'gaps', 'showcase')
ALIASES = {'check': 'audit', 'inspect': 'audit', 'scan': 'audit', 'site': 'audit',
           'link': 'concept', 'preview': 'concept', 'page': 'concept',
           'businesses': 'leads', 'prospects': 'leads',
           'hi': 'help', 'hello': 'help', 'hey': 'help'}

HELP = (
    "I run the crew from here. Say things like:\n"
    "• status — pipeline at a glance\n"
    "• leads [search] — recently saved businesses\n"
    "• audit <name> — check the listing (live, bounded, robots-aware)\n"
    "• brand <name> — colours, logo and images we harvested\n"
    "• concept <name> — the preview link and how it is themed\n"
    "• gaps <name> — ranked observed gaps\n"
    "• showcase — which trades have photo sets"
)

SYSTEM = (
    "You are Chief, the crew chief of Reachmark, a website studio. The owner "
    "is chatting with you on the crew console. Crew commands: status, leads, "
    "audit <business>, brand <business>, concept <business>, gaps <business>, "
    "showcase, help. Scouts find businesses, Auditors check listings, Builders "
    "theme concept pages. Answer briefly in plain words; when the request maps "
    "to a command, say the exact command to run."
)


class _Ctx:
    """Minimal stand-in so Chief can run agent skills outside a crew run."""

    def __init__(self, db, now, params=None):
        self.db = db
        self.now = now
        self.params = params or {}
        self.receipts = []

    def receipt(self, kind, detail, evidence=None, url=None, when=None):
        self.receipts.append({'kind': kind, 'detail': str(detail)[:600]})
        return self.receipts[-1]


def parse(message):
    """Split 'audit Sunrise Bakery' -> ('audit', 'Sunrise Bakery')."""
    text = re.sub(r'\s+', ' ', (message or '').strip())
    if not text:
        return '', ''
    head, _, rest = text.partition(' ')
    head = head.strip('?!.,:').lower()
    return ALIASES.get(head, head), rest.strip().strip('"').strip("'").strip()


def resolve_lead(db, ref):
    """Find a lead by id or name fragment. Returns (lead|None, note)."""
    ref = (ref or '').strip()
    if not ref:
        return None, 'Give me a business to look at — e.g. “brand Sunrise”.'
    with db() as c:
        row = c.execute('SELECT * FROM leads WHERE id=?', (ref,)).fetchone()
        if row:
            return dict(row), ''
        rows = c.execute('SELECT * FROM leads WHERE name LIKE ? ORDER BY updated DESC LIMIT 6',
                         (f'%{ref}%',)).fetchall()
    if not rows:
        return None, f'No saved business matches “{ref}”. Try “leads {ref}”.'
    if len(rows) == 1:
        return dict(rows[0]), ''
    options = ', '.join(f"{r['name']} ({r['id']})" for r in rows)
    return None, f'Several match — be specific: {options}.'


def _latest_audit(db, lead_id):
    from agents.agent_auditor import ensure_tables, latest_audit
    ensure_tables(db)
    return latest_audit(db, lead_id)


def cmd_status(db):
    from agents.agent_auditor import ensure_tables
    from web.concept import ARCH_THEMES, SHOWCASE
    ensure_tables(db)
    with db() as c:
        leads = c.execute('SELECT COUNT(*) n FROM leads').fetchone()['n']
        audits = c.execute('SELECT COUNT(*) n FROM site_audits').fetchone()['n']
        try:
            pending = c.execute("SELECT COUNT(*) n FROM crew_approvals WHERE state='pending'").fetchone()['n']
        except Exception:
            pending = 0
    full = sum(1 for a in ARCH_THEMES if _showcase_state(SHOWCASE.get(a, {}))[0] == 'full')
    try:
        from web.ai_provider import health
        provider = health()
        brain = f"{provider.get('provider', '?')}/{provider.get('model', '?')}"
    except Exception:
        brain = 'rule-based only'
    return (f'{leads} businesses saved · {audits} audits stored · '
            f'{pending} approvals waiting · photo sets {full}/{len(ARCH_THEMES)} trades · '
            f'model: {brain}.')


def cmd_leads(db, query):
    with db() as c:
        if query:
            rows = c.execute('SELECT id,name,category,city,stage FROM leads '
                             'WHERE name LIKE ? OR category LIKE ? OR city LIKE ? '
                             'ORDER BY updated DESC LIMIT 8',
                             (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
        else:
            rows = c.execute('SELECT id,name,category,city,stage FROM leads '
                             'ORDER BY updated DESC LIMIT 8').fetchall()
    if not rows:
        return 'No saved businesses yet — run the crew or import a CSV.'
    lines = [f"• {r['name']} — {r['category'] or '?'} · {r['city'] or '?'} "
             f"[{r['stage'] or 'New'}] ({r['id']})" for r in rows]
    return '\n'.join(lines)


def cmd_audit(db, now, lead):
    from agents.agent_auditor import audit_lead
    result = audit_lead(_Ctx(db, now), lead)
    gaps = (result.get('gaps') or {})
    lines = [f"Audited {lead['name']}: {result.get('status')} — "
             f"{gaps.get('score', 0)} ranked points ({gaps.get('tier', '?')})."]
    for gap in (gaps.get('gaps') or [])[:3]:
        lines.append(f"• {gap['reason']}")
    brand = (result.get('observations') or {}).get('brand') or {}
    lines.append('Brand harvested: ' + _brand_one_liner(brand) + '.')
    return '\n'.join(lines)


def _brand_one_liner(brand):
    bits = []
    colors = [c for c in ([brand.get('theme_color')] if brand.get('theme_color') else [])
              + list(brand.get('colors') or [])][:3]
    if colors:
        bits.append('colours ' + ', '.join(colors))
    bits.append('logo ' + ('yes' if brand.get('logo') else 'no'))
    images = brand.get('images') or []
    bits.append(f'{len(images)} image(s)')
    if brand.get('fonts'):
        bits.append('fonts ' + ', '.join(brand['fonts'][:2]))
    return ', '.join(bits) if bits else 'nothing found'


def cmd_brand(db, lead):
    audit = _latest_audit(db, lead['id'])
    if not audit or not (audit.get('observations') or {}).get('ok'):
        return f"No live audit stored for {lead['name']} yet — say “audit {lead['name']}”."
    brand = (audit.get('observations') or {}).get('brand') or {}
    if not brand.get('logo') and not brand.get('colors') and not brand.get('images'):
        return (f"Audited {lead['name']}, but the page gave no brand traces — "
                'the preview falls back to the trade palette.')
    lines = [f"Brand observed for {lead['name']}:"]
    colors = ([brand['theme_color']] if brand.get('theme_color') else []) + list(brand.get('colors') or [])
    if colors:
        lines.append('• Colours: ' + ', '.join(colors[:5]))
    if brand.get('logo'):
        lines.append(f"• Logo: {brand['logo']} ({brand.get('logo_source') or 'seen on page'})")
    for img in (brand.get('images') or [])[:4]:
        lines.append(f"• Image: {img.get('url')} — {img.get('alt') or 'no caption'}")
    if brand.get('fonts'):
        lines.append('• Fonts: ' + ', '.join(brand['fonts'][:4]))
    return '\n'.join(lines)


def cmd_concept(db, lead, base_url):
    from web.concept import build_theme, detect_archetype
    audit = _latest_audit(db, lead['id'])
    brand = (audit.get('observations') or {}).get('brand') or {} if audit else {}
    arch = detect_archetype(lead.get('category'))
    theme = build_theme(arch, brand)
    colors = theme['colors']
    link = (base_url.rstrip('/') + f"/preview/{lead['token']}" if lead.get('token')
            else 'no preview token on this lead yet')
    slots = theme.get('showcase') or {}
    photos = (1 if slots.get('hero') else 0) + len(slots.get('offers') or []) \
        + (1 if slots.get('craft') else 0) + (1 if slots.get('strip') else 0)
    return (f"Concept for {lead['name']} ({arch}): {link}\n"
            f"• Accent {colors['accent']} ({colors.get('accent_source')}) · {colors['vibe']} type\n"
            f"• Brand pack: {'observed' if theme['has_brand'] else 'trade fallback'} · "
            f"photos {photos}/6 · logo {'yes' if theme['logo'] else 'no'}")


def cmd_gaps(db, lead):
    audit = _latest_audit(db, lead['id'])
    gaps = (audit.get('gaps') or {}) if audit else {}
    if not audit or not (gaps.get('gaps') or []):
        return (f'No ranked gaps stored for {lead["name"]} — '
                f'say “audit {lead["name"]}” first.')
    lines = [f"Observed gaps for {lead['name']} "
             f"({gaps.get('score')} pts, {gaps.get('tier')}):"]
    for gap in gaps['gaps'][:6]:
        lines.append(f"• {gap['reason']} [{gap['source']}]")
    lines.append('Observed at check time — confirm with the business.')
    return '\n'.join(lines)


def _showcase_state(slots):
    photos = (1 if slots.get('hero') else 0) + len(slots.get('offers') or []) \
        + (1 if slots.get('craft') else 0) + (1 if slots.get('strip') else 0)
    if photos >= 6:
        return 'full', photos
    if photos:
        return 'teaser', photos
    return 'planned', 0


def cmd_showcase():
    from web.concept import ARCH_THEMES, SHOWCASE
    lines = []
    for arch in ARCH_THEMES:
        state, photos = _showcase_state(SHOWCASE.get(arch, {}))
        lines.append(f'• {arch}: {state} ({photos}/6 photos)')
    return 'Photo sets by trade:\n' + '\n'.join(lines)


def cmd_freeform(message):
    try:
        from crew.skills_loader import rules
        from web.ai_provider import safe_complete
        doctrine = rules('chief', 'directive', 3)
        system = SYSTEM + (' Doctrines: ' + ' '.join(doctrine) if doctrine else '')
        text, _meta = safe_complete(system, message, max_tokens=300)
    except Exception:
        text = None
    if text:
        return text.strip()[:1500]
    return ("I don't follow that yet — I work best with commands. Say “help” "
            "for the list.")


def answer(db, now, message, base_url=''):
    """Route one owner message to a crew skill. Never raises."""
    try:
        command, arg = parse(message)
        if command == 'help' or not command:
            return HELP
        if command == 'status':
            return cmd_status(db)
        if command == 'leads':
            return cmd_leads(db, arg)
        if command == 'showcase':
            return cmd_showcase()
        if command in ('audit', 'brand', 'concept', 'gaps'):
            lead, note = resolve_lead(db, arg)
            if not lead:
                return note
            if command == 'audit':
                return cmd_audit(db, now, lead)
            if command == 'brand':
                return cmd_brand(db, lead)
            if command == 'concept':
                return cmd_concept(db, lead, base_url)
            return cmd_gaps(db, lead)
        return cmd_freeform(message)
    except Exception as exc:
        return f'Chief stumbled on that one ({type(exc).__name__}) — try “help”.'


def run(ctx):
    """Crew single-mode entry: answer ctx.params['message'] with a receipt."""
    try:
        base = (ctx.settings().get('public_base_url') or '').rstrip('/')
    except Exception:
        base = ''
    message = (ctx.params.get('message') or 'status').strip() or 'status'
    reply = answer(ctx.db, ctx.now, message, base_url=base)
    ctx.receipt('chief', reply[:600])
    return {'reply': reply}
