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


def build_script(lead, concept, link, settings=None, seconds=None, locale=None):
    """Return the caption beats and the spoken script for one concept.

    Facts come from the lead record and the measured audit only. If a value was never
    measured it is not mentioned — the beat shortens instead of inventing.

    ``seconds`` scales the four acts to the cut: problem, process, solution, ask.
    A concept may carry a ``story`` dict that rewords the acts (used for sample ads);
    the facts stay record-only either way.
    """
    settings = settings or {}
    from web.i18n import t as _t, locale_now
    loc = locale or locale_now()
    story = concept.get('story') or {}
    studio = _clean(settings.get('agency') or STUDIO['name'], 40)
    name = _clean(lead.get('name') or _t('ad_biz', loc), 60)
    place = _clean(lead.get('city') or '', 40)
    facts = [str(f) for f in (concept.get('gaps') or []) if f][:3]
    contact = concept.get('contact') or {}

    if contact.get('phone'):
        find_line = _t('ad_find_phone', loc)
    elif contact.get('email'):
        find_line = _t('ad_find_email', loc)
    else:
        find_line = _t('ad_find_none', loc)

    length = float(seconds or 18)
    close_at = max(6.0, length - 3.2)
    marks = [0.6]
    for weight in (0.30, 0.27, 0.20):
        marks.append(round(marks[-1] + (close_at - 0.6) * weight, 1))
    marks.append(round(close_at, 1))

    beats = [
        {'at': marks[0], 'until': marks[1], 'kicker': _t('ad_k1', loc),
         'title': story.get('problem_title') or f"{name}: {_t('ad_today', loc).lower() if loc == 'en' else _t('ad_today', loc)}",
         'body': story.get('problem_body') or find_line,
         'facts': facts or [_t('ad_nosite', loc)]},
        {'at': marks[1], 'until': marks[2], 'kicker': _t('ad_k2', loc),
         'title': story.get('process_title') or _t('ad_p2t', loc),
         'body': story.get('process_body') or
                 _t('ad_p2b', loc),
         'facts': [f for f in (place, concept.get('family_label') or '') if f]},
        {'at': marks[2], 'until': marks[3], 'kicker': _t('ad_k3', loc),
         'title': story.get('solution_title') or _t('ad_p3t', loc),
         'body': story.get('solution_body') or
                 _t('ad_p3b', loc),
         'facts': []},
        {'at': marks[3], 'until': marks[4], 'kicker': _t('ad_k4', loc),
         'title': _t('ad_askt', loc),
         'body': _t('ad_askb', loc),
         'facts': [_t('ad_cf1', loc), _t('ad_cf2', loc), _t('ad_cf3', loc)]},
    ]
    views = int(link.get('views') or 0)
    watched = ((_t('ad_opened1', loc, v=views) if views == 1 else _t('ad_openedn', loc, v=views))
               if views else _t('ad_opened0', loc))
    spoken = (
        f'{name}. {find_line} {_t('ad_sp1', loc)}'
        f'{watched}{_t('ad_sp2', loc, s=studio)}'
    )
    spoken_short = (
        f'{name}. {find_line} {_t('ad_ss1', loc)}'
        f'{_t('ad_ss2', loc)}{_t('ad_ss3', loc, s=studio)}'
    )
    return {
        'studio': studio, 'business': name, 'place': place,
        'beats': beats,
        'spoken': _clean(story.get('spoken') or spoken, 1200),
        'spoken_short': _clean(story.get('spoken_short') or spoken_short, 900),
        'end_note': _t('ad_end', loc, s=studio),
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
        cmd += ['-c:a', 'aac', '-b:a', '128k', '-af', 'adelay=600:all=1']
        # An explicit stop, not -shortest: -shortest deadlocks against -r 30 + adelay
        # on longer cuts (ffmpeg stalls mid-encode waiting on stream interleaving).
        stop = _audio_seconds(voice)
        if stop > 0:
            cmd += ['-t', f'{stop + 1.2:.2f}']
    else:
        cmd += ['-an']
    cmd += [out_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = [ln.strip() for ln in result.stderr.strip().splitlines()
                if ln.strip() and not ln.startswith(('frame=', '[libx264 @'))]
        detail = ' | '.join(tail[-4:])[:400] or 'no ffmpeg output'
        raise RuntimeError(f'ffmpeg failed (rc={result.returncode}): {detail}')
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

    os.makedirs(out_dir, exist_ok=True)
    made, started = {}, time.monotonic()
    audio_len = _audio_seconds(voice) if voice else 0.0
    wanted = [f for f in formats if f in FORMATS]
    lengths = {}
    for fmt in wanted:
        length = int(seconds or DEFAULT_SECONDS.get(fmt, 18))
        if audio_len:
            # hold the closing card until the narration has finished
            length = max(length, int(audio_len + 2.5))
        lengths[fmt] = length
    script = build_script(lead, concept, link, settings,
                          seconds=max(lengths.values()) if lengths else None)
    with tempfile.TemporaryDirectory(prefix='reachmark-ad-') as tmp:
        for fmt in wanted:
            length = lengths[fmt]
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
