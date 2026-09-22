"""Reads the vendored agent playbooks (skills/) at runtime.

Provenance: the playbooks in ``skills/vendor`` are unmodified copies of two MIT
licensed upstream projects — ``marketingskills`` by Corey Haines and ``brag`` by
Shunit Haviv Hakimi. Licences and exact commits live in
``skills/vendor/licenses/`` and ``skills/vendor/VENDOR.json``; the loader never
modifies them and never executes anything from them.

Nothing here invents product facts: a playbook supplies *how* the crew writes and
checks things, never *what* is true about a business. Business facts always come
from saved records and measured observations.
"""
import os, re, json, functools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_DIR = os.path.join(ROOT, 'skills', 'vendor')

# Playbooks the crew is allowed to use, and what each agent uses it for.
PLAYBOOKS = {
    'cold-email': {'use': 'outreach drafts, subject lines, follow-up cadence', 'agents': ['scribe', 'closer']},
    'copywriting': {'use': 'page and message structure, plain-language rules', 'agents': ['scribe', 'builder']},
    'cro': {'use': 'review-page and reply-path conversion checks', 'agents': ['builder', 'receptionist']},
    'prospecting': {'use': 'qualification, fit signals, compliance notes', 'agents': ['scout', 'closer']},
    'ai-seo': {'use': 'making the studio findable in AI answers', 'agents': ['brag', 'scribe']},
    'seo-audit': {'use': 'measured on-page observations for the builder', 'agents': ['auditor', 'builder']},
    'brag': {'use': 'launch-kit plan, tone presets, share copy', 'agents': ['brag']},
}


def _strip_front_matter(text):
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            return text[end + 4:].lstrip('\n'), text[3:end]
    return text, ''


def _front_matter(raw):
    out = {}
    for line in raw.splitlines():
        m = re.match(r'^([a-zA-Z_][\w-]*):\s*(.*)$', line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip().strip('"\'')
        m2 = re.match(r'^\s{2,}version:\s*(.*)$', line)
        if m2:
            out['version'] = m2.group(1).strip().strip('"\'')
    return out


@functools.lru_cache(maxsize=32)
def load_skill(slug):
    """Return {slug, title, description, version, body, sections, bullets}."""
    path = os.path.join(VENDOR_DIR, slug, 'SKILL.md')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as fh:
        raw = fh.read()
    body, fm = _strip_front_matter(raw)
    meta = _front_matter(fm)
    sections, title, buf = {}, '', []
    for line in body.splitlines():
        if line.startswith('# ') and not title:
            title = line[2:].strip()
            continue
        if line.startswith('## '):
            if title and buf:
                sections.setdefault(title, []).append('\n'.join(buf).strip())
            title = line[3:].strip()
            buf = []
            continue
        if title:
            buf.append(line)
    if title and buf:
        sections.setdefault(title, []).append('\n'.join(buf).strip())
    bullets = [b.strip('*• ').strip() for b in re.findall(r'^\s*[-*]\s+(.{12,240})$', body, re.M)]
    return {
        'slug': slug,
        'title': meta.get('name', slug),
        'description': meta.get('description', ''),
        'version': meta.get('version', ''),
        'body': body,
        'sections': sections,
        'bullets': bullets,
        'path': os.path.relpath(path, os.path.dirname(VENDOR_DIR)),
    }


def rules(slug, needle, limit=6):
    """Short, quotable rules from a playbook section whose name contains `needle`."""
    skill = load_skill(slug)
    if not skill:
        return []
    out = []
    for name, blocks in skill['sections'].items():
        if needle.lower() in name.lower():
            for block in blocks:
                for line in block.splitlines():
                    line = line.strip()
                    if line.startswith(('- ', '* ')) and len(line) > 24:
                        out.append(re.sub(r'\s+', ' ', line[2:]).strip())
    return out[:limit]


def reference(slug, filename, limit=4000):
    """Read a vendored reference file for prompt context (bounded)."""
    path = os.path.join(VENDOR_DIR, slug, 'references', filename)
    if not os.path.exists(path):
        return ''
    with open(path, encoding='utf-8') as fh:
        return fh.read()[:limit]


def prompt_brief(slugs, per_skill=2600):
    """Bounded playbook context for an optional language-model phrasing pass."""
    parts = []
    for slug in slugs:
        skill = load_skill(slug)
        if skill:
            parts.append(f"### playbook: {skill['slug']}\n{skill['body'][:per_skill]}")
    return '\n\n'.join(parts)


def playbook_index():
    """Catalogue for the crew console and the docs — provenance included."""
    try:
        with open(os.path.join(VENDOR_DIR, 'VENDOR.json'), encoding='utf-8') as fh:
            vendor = json.load(fh)
    except (OSError, ValueError):
        vendor = {'sources': []}
    items = []
    for slug, meta in PLAYBOOKS.items():
        skill = load_skill(slug)
        items.append({
            'slug': slug,
            'name': skill['title'] if skill else slug,
            'version': skill['version'] if skill else '',
            'agents': meta['agents'],
            'use': meta['use'],
            'bytes': len(skill['body']) if skill else 0,
            'loaded': bool(skill),
        })
    return {'skills': sorted(items, key=lambda i: i['slug']), 'sources': vendor.get('sources', []),
            'note': vendor.get('note', '')}


if __name__ == '__main__':
    index = playbook_index()
    for item in index['skills']:
        print(f"{item['slug']:<12} {item['name'][:38]:<40} {item['bytes']:>7} bytes  agents={','.join(item['agents'])}")
    for src in index['sources']:
        print(f"source: {src['repo']} ({src['license']}) @ {src.get('vendored_commit','')[:8]}")
