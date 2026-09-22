"""Brag's video step: turn a concept into a short ad, using a real recording.

Why a recording and not generated frames: the honest version of "a video of the website"
is a browser rendering the actual page. Playwright drives one, ffmpeg muxes it, and the
overlays reuse the same saved facts the concept page shows. Nothing is invented, and if
the renderer is not installed the agent says so instead of pretending a video exists.

Two cuts are produced from one render pass per format:

* ``wide`` 1920×1080 — websites, YouTube, e-mail.
* ``tall`` 1080×1920 — Reels, TikTok, WhatsApp status.

Requirements (optional — the crew works without them):

    pip install playwright imageio-ffmpeg && python -m playwright install chromium
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from crew.business import BRAIN_VERSION, STUDIO

WIDE = (1920, 1080)
TALL = (1080, 1920)
FORMATS = {'wide': WIDE, 'tall': TALL}
DEFAULT_SECONDS = {'wide': 18, 'tall': 22}


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
def _ffmpeg():
    """ffmpeg from PATH, else the one imageio-ffmpeg ships. '' when neither exists."""
    found = shutil.which('ffmpeg')
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ''


def _playwright():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def available():
    """What this machine can actually do — reported to the owner verbatim."""
    return {
        'playwright': _playwright(),
        'ffmpeg': bool(_ffmpeg()),
        'enabled': os.getenv('CREW_VIDEO_RENDER', '1') != '0',
        'install': 'pip install playwright imageio-ffmpeg && python -m playwright install chromium',
    }


def can_render():
    state = available()
    return bool(state['playwright'] and state['ffmpeg'] and state['enabled'])


# --------------------------------------------------------------------------- #
# The script of the ad — every line is a saved fact
# --------------------------------------------------------------------------- #
def _clean(value, limit=90):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:limit]


def lead_for(db, link):
    """The saved business record behind a link — the name lives on the lead, not the concept."""
    with db() as c:
        row = c.execute('SELECT * FROM leads WHERE id=?', (link.get('lead_id'),)).fetchone()
    return dict(row) if row else {}


def build_script(lead, concept, link, settings=None):
    """Return the caption beats and the spoken script for one concept.

    Facts come from the lead record and the measured audit only. If a value was never
    measured it is not mentioned — the beat shortens instead of inventing.
    """
    settings = settings or {}
    studio = _clean(settings.get('agency') or STUDIO['name'], 40)
    name = _clean(lead.get('name') or 'this business', 60)
    place = _clean(lead.get('city') or '', 40)
    facts = [str(f) for f in (concept.get('gaps') or []) if f][:3]
    contact = concept.get('contact') or {}

    if contact.get('phone'):
        find_line = 'Right now the first thing a customer finds is a phone number in a listing.'
    elif contact.get('email'):
        find_line = 'Right now the first thing a customer finds is an e-mail address in a listing.'
    else:
        find_line = 'Right now there is nothing of their own for a customer to land on.'

    beats = [
        {'at': 0.6, 'until': 6.0, 'kicker': 'The situation',
         'title': f"{name}: what a customer finds today",
         'body': find_line,
         'facts': [f for f in (facts or [('No website listed in the public listing',)])[:2]]},
        {'at': 6.0, 'until': 12.0, 'kicker': 'What we did instead of asking',
         'title': 'An independent concept, built from public details only',
         'body': 'One page, about a minute to read, ending in a single question.',
         'facts': [f for f in (place, concept.get('family_label') or '') if f]},
        {'at': 12.0, 'until': 18.0, 'kicker': 'The ask',
         'title': 'Would you like this built?',
         'body': 'Three answers: yes, not right now, or “we already have a website”. A no ends it.',
         'facts': ['No charge', 'Nothing published under their name', 'Reply STOP ends contact']},
    ]
    views = int(link.get('views') or 0)
    watched = (f"It has been opened {views} time{'s' if views != 1 else ''} so far. "
               if views else "It has just gone out to them. ")
    spoken = (
        f"{name}. {find_line} So instead of pitching, we built an independent concept page "
        "from the details already public — about a minute to read, and one question at the end. "
        f"{watched}{studio} answers either way: concept first, ask second."
    )
    # A short narration for the 16-second cut: same facts, fewer words, no rush.
    spoken_short = (
        f"{name}. {find_line} So instead of pitching them, we built a concept page from the "
        "details already public. One question at the end: would you like this built? "
        f"{studio} — concept first, ask second."
    )
    return {
        'studio': studio, 'business': name, 'place': place,
        'beats': beats,
        'spoken': _clean(spoken, 900),
        'spoken_short': _clean(spoken_short, 500),
        'end_note': f'Prepared by {studio} as an independent concept. No reviews, prices, hours or photographs were invented.',
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _record(base_url, token, fmt, seconds, out_dir, captions):
    """Record one cut of the ad stage. Returns the webm path."""
    from playwright.sync_api import sync_playwright

    size = FORMATS[fmt]
    os.makedirs(out_dir, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': size[0], 'height': size[1]},
                                      record_video_dir=out_dir, record_video_size={'width': size[0], 'height': size[1]},
                                      device_scale_factor=1)
        page = context.new_page()
        page.route('**/*', lambda route: route.abort()
                   if not route.request.url.startswith(('http://127.0.0.1', 'http://localhost', 'data:'))
                   else route.continue_())
        url = f'{base_url.rstrip("/")}/ads/{token}?seconds={seconds}&fmt={fmt}'
        page.goto(url, wait_until='domcontentloaded', timeout=25000)
        page.wait_for_function('() => window.__adDone === true', timeout=(seconds + 25) * 1000)
        page.wait_for_timeout(400)
        path = page.video.path()
        context.close()
        browser.close()
    return path


def _to_mp4(webm, out_path, fmt, voice=None):
    """Convert the recording to H.264/yuv420p — the format every phone and browser plays."""
    ffmpeg = _ffmpeg()
    size = FORMATS[fmt]
    cmd = [ffmpeg, '-y', '-i', webm]
    if voice and os.path.exists(voice):
        cmd += ['-i', voice]
    cmd += ['-c:v', 'libx264', '-preset', 'medium', '-crf', '21', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', '-r', '30',
            '-vf', f'scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease,pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2:color=0x161a15']
    if voice and os.path.exists(voice):
        # 0.6 s of air before the first word: the opening beat lands before the voice does.
        # all=1 so the delay applies however many channels the narration has.
        cmd += ['-c:a', 'aac', '-b:a', '128k', '-af', 'adelay=600:all=1', '-shortest']
    else:
        cmd += ['-an']
    cmd += [out_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        lines = [ln.strip() for ln in result.stderr.strip().splitlines()
                 if ln.strip() and not ln.startswith('frame=')]
        detail = (lines[-3:] or result.stderr.strip().splitlines()[-1:])[-1][:200]
        raise RuntimeError(f'ffmpeg failed: {detail}')
    return out_path


def render(concept, lead, link, settings, out_dir, formats=('wide', 'tall'), voice=None,
           base_url='http://127.0.0.1:8000', seconds=None):
    """Render the ad cuts. Returns {fmt: path} plus the script that was used.

    Raises RuntimeError with a plain-language reason when the renderer is unavailable —
    the caller turns that into an honest "no video yet" message.
    """
    if not can_render():
        state = available()
        reason = ('video rendering is switched off (CREW_VIDEO_RENDER=0)' if not state['enabled'] else
                  'the renderer is not installed on this machine')
        raise RuntimeError(f'{reason}. Install with: {state["install"]}')

    script = build_script(lead, concept, link, settings)
    os.makedirs(out_dir, exist_ok=True)
    made, started = {}, time.monotonic()
    with tempfile.TemporaryDirectory(prefix='reachmark-ad-') as tmp:
        audio_len = _audio_seconds(voice) if voice else 0.0
        for fmt in formats:
            if fmt not in FORMATS:
                continue
            length = int(seconds or DEFAULT_SECONDS.get(fmt, 18))
            if audio_len:
                # hold the closing card until the narration has finished
                length = max(length, int(audio_len + 2.5))
            webm = _record(base_url, link['token'], fmt, length, os.path.join(tmp, fmt), script['beats'])
            name = f"{(lead.get('name') or 'concept').lower().replace(' ', '-')[:40]}-{fmt}.mp4"
            out = os.path.join(out_dir, re.sub(r'[^a-z0-9.-]+', '-', name))
            _to_mp4(webm, out, fmt, voice)
            made[fmt] = {'path': out, 'bytes': os.path.getsize(out), 'seconds': length}
    return {'ok': True, 'cuts': made, 'script': script, 'brain': BRAIN_VERSION,
            'took_seconds': round(time.monotonic() - started, 1)}


def _audio_seconds(path):
    """Length of an audio file, read from ffmpeg's own report. 0.0 when unknown."""
    if not path or not os.path.exists(path):
        return 0.0
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return 0.0
    out = subprocess.run([ffmpeg, '-hide_banner', '-i', path], capture_output=True, text=True).stderr
    match = re.search(r'Duration: (\d+):(\d+):([\d.]+)', out)
    if not match:
        return 0.0
    h, m, sec = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return h * 3600 + m * 60 + sec


def write_narration(script, out_dir, stem='narration', short=True):
    """Save the spoken line beside the cuts so a human can record it (or a TTS can read it)."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f'{stem}.txt')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(narration(script, short=short).strip() + '\n')
    return path


def narration(script, short=True):
    """The line to read aloud, chosen for the length of the cut."""
    return (script.get('spoken_short') if short else script.get('spoken')) or script.get('spoken') or ''


def status_line(result):
    """One line for the crew console, in plain language."""
    if not result.get('cuts'):
        return 'No cut was produced.'
    bits = [f"{fmt} {round(row['seconds'])}s ({row['bytes'] // 1024} KB)" for fmt, row in result['cuts'].items()]
    return 'Rendered ' + ', '.join(bits) + f" in {result['took_seconds']}s. This is a recording of the real concept page — no frames were faked."


if __name__ == '__main__':
    print(json.dumps(available(), indent=2))
