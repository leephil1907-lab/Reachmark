"""Evidence-led PDF export for public Reachmark opportunity reports."""
from __future__ import annotations

from html import escape
from io import BytesIO
import os
import re
import tempfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    KeepTogether, Image as ReportImage,
)


def _hex(value, fallback):
    value = str(value or '').strip()
    if re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        return colors.HexColor(value)
    if re.fullmatch(r'#[0-9a-fA-F]{3}', value):
        return colors.HexColor('#' + ''.join(ch * 2 for ch in value[1:]))
    return colors.HexColor(fallback)


def _text(value, limit=3000):
    return escape(str(value or '')[:limit]).replace('\n', '<br/>') or 'Not observed'


def _safe_url(value):
    value = str(value or '').strip()
    return value if value.startswith(('https://', 'http://', 'mailto:', 'tel:')) else ''


def _load_observed_logo(url):
    """Fetch only a small, public raster logo through the audit's SSRF-checked fetcher."""
    if not _safe_url(url):
        return None
    try:
        from web.web_probe import _fetch_public
        response, reason = _fetch_public(url, timeout=4, max_bytes=700000)
        if response is None:
            return None
        try:
            content_type = (response.headers.get('content-type') or '').split(';', 1)[0].strip().lower()
            if content_type not in ('image/png', 'image/jpeg'):
                return None
            raw = response.raw.read(700001, decode_content=True) or b''
            if len(raw) > 700000:
                return None
            if not (raw.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10))) or raw.startswith(bytes((255, 216, 255)))):
                return None
            reader = ImageReader(BytesIO(raw))
            width, height = reader.getSize()
            if not width or not height:
                return None
            scale = min((25 * mm) / width, (18 * mm) / height)
            return ReportImage(BytesIO(raw), width=width * scale, height=height * scale)
        finally:
            response.close()
    except Exception:
        # Missing or unsupported logo assets never prevent a report being generated.
        return None


def build_report_pdf(report, lead, brand_theme):
    """Render only saved report data; absent measurements remain explicitly unverified."""
    report = report if isinstance(report, dict) else {}
    lead = lead if isinstance(lead, dict) else {}
    theme = brand_theme if isinstance(brand_theme, dict) else {}
    primary = _hex(theme.get('primary'), '#d6f269')
    strong = _hex(theme.get('strong'), '#202820')
    paper = _hex(theme.get('background'), '#f5f6f0')
    ink = _hex(theme.get('text'), '#202820')
    muted = _hex(theme.get('muted'), '#687064')
    reachmark_lime = _hex(theme.get('reachmark'), '#d6f269')
    critical = _hex(theme.get('severity_critical'), '#b42318')
    warning = _hex(theme.get('severity_warning'), '#b54708')
    success = _hex(theme.get('severity_success'), '#247044')

    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=17 * mm, bottomMargin=18 * mm,
        title='Website Growth Audit — Reachmark',
        author='Reachmark Digital', pageCompression=0,
    )
    base = getSampleStyleSheet()
    styles = {
        'title': ParagraphStyle('ReachmarkTitle', parent=base['Title'], fontName='Helvetica-Bold',
                                fontSize=25, leading=29, textColor=strong, alignment=TA_LEFT,
                                spaceAfter=7 * mm),
        'h1': ParagraphStyle('ReachmarkH1', parent=base['Heading1'], fontName='Helvetica-Bold',
                             fontSize=16, leading=20, textColor=strong, spaceBefore=5 * mm,
                             spaceAfter=3 * mm),
        'h2': ParagraphStyle('ReachmarkH2', parent=base['Heading2'], fontName='Helvetica-Bold',
                             fontSize=11, leading=14, textColor=strong, spaceBefore=3 * mm,
                             spaceAfter=1.5 * mm),
        'body': ParagraphStyle('ReachmarkBody', parent=base['BodyText'], fontName='Helvetica',
                               fontSize=9, leading=13, textColor=ink, spaceAfter=2.2 * mm),
        'small': ParagraphStyle('ReachmarkSmall', parent=base['BodyText'], fontName='Helvetica',
                                fontSize=7.5, leading=10, textColor=muted, spaceAfter=1.5 * mm),
        'badge': ParagraphStyle('ReachmarkBadge', parent=base['BodyText'], fontName='Helvetica-Bold',
                                fontSize=8, leading=10, textColor=ink),
    }
    story = []
    name = theme.get('site_name') or lead.get('name') or 'Business website'
    website = lead.get('website') or (report.get('evidence') or {}).get('website') or ''
    created = str(report.get('created') or '')[:10] or 'Date not recorded'
    logo_url = _safe_url(theme.get('logo'))
    favicon_url = _safe_url(theme.get('favicon'))
    logo_source = logo_url or favicon_url
    logo_flow = _load_observed_logo(logo_source) if logo_source else None
    top = Table([
        [logo_flow or Paragraph('<b>WEBSITE GROWTH AUDIT</b>', styles['small']),
         Paragraph('<b>PREPARED BY REACHMARK</b>', styles['small'])],
        [Paragraph(_text(name, 180), styles['title']),
         Paragraph('Reachmark Digital<br/>reachmarkdigital.xyz', styles['small'])],
        [Paragraph(_text(website, 300), styles['body']),
         Paragraph('Audit date: ' + _text(created, 40), styles['small'])],
    ], colWidths=[118 * mm, 48 * mm])
    top.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary),
        ('TEXTCOLOR', (0, 0), (-1, 0), _hex(theme.get('on_primary'), '#101510')),
        ('BACKGROUND', (0, 1), (-1, -1), paper),
        ('BOX', (0, 0), (-1, -1), 0.6, _hex(theme.get('secondary'), '#e2e5dc')),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story += [top, Spacer(1, 5 * mm)]
    if logo_source:
        story.append(Paragraph('Observed logo asset: <link href="%s" color="#687064">%s</link>' %
                               (escape(logo_source, quote=True), _text(logo_source, 240)), styles['small']))
    if not theme.get('detected'):
        story.append(Paragraph('<b>Limited brand data detected.</b> A neutral theme is used because the public page did not provide enough brand details.', styles['small']))
    story.append(Paragraph('Brand identity', styles['h1']))
    profile_rows = [
        [Paragraph('<b>Business name</b>', styles['small']), Paragraph(_text(name, 180), styles['body'])],
        [Paragraph('<b>Website</b>', styles['small']), Paragraph(_text(website, 300), styles['body'])],
        [Paragraph('<b>Primary color</b>', styles['small']), Paragraph(_text(theme.get('primary') or 'Reachmark fallback', 40), styles['body'])],
        [Paragraph('<b>Secondary color</b>', styles['small']), Paragraph(_text(theme.get('secondary') or 'Not observed', 40), styles['body'])],
        [Paragraph('<b>Font family</b>', styles['small']), Paragraph(_text(', '.join(theme.get('fonts') or []) or 'Not observed', 200), styles['body'])],
        [Paragraph('<b>Contact links found</b>', styles['small']), Paragraph(_text(', '.join(theme.get('contact_details') or []) or 'Not observed', 600), styles['body'])],
        [Paragraph('<b>Social profiles found</b>', styles['small']), Paragraph(_text(', '.join(theme.get('social_links') or []) or 'Not observed', 700), styles['body'])],
    ]
    identity = Table(profile_rows, colWidths=[42 * mm, 124 * mm])
    identity.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), paper),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#e2e5dc')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story += [identity, Paragraph('Brand identity is detected from public website data. The report creator remains Reachmark Digital.', styles['small'])]

    story.append(Paragraph('Overall opportunity score', styles['h1']))
    score = report.get('score')
    score_label = (str(score) + '/100') if isinstance(score, (int, float)) else 'Not measured'
    priority = str(report.get('priority') or 'Not assigned')
    score_card = Table([[
        Paragraph('<font size="24"><b>%s</b></font><br/><font size="8">Relative opportunity ranking</font>' % _text(score_label, 30), styles['body']),
        Paragraph('<b>Priority</b><br/>%s<br/><br/><b>Observed findings</b><br/>%s' %
                  (_text(priority, 30), _text(report.get('leak_count', len(report.get('leaks') or [])), 20)), styles['body'])
    ]], colWidths=[83 * mm, 83 * mm])
    score_card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), paper), ('BACKGROUND', (1, 0), (1, 0), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.7, primary), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story += [score_card, Paragraph('This score ranks the website gaps detected by this check. It is not a conversion probability, website-quality grade, or revenue estimate.', styles['small'])]

    story.append(Paragraph('Category scores', styles['h1']))
    category_scores = (report.get('evidence') or {}).get('category_scores') or {}
    categories = ['Conversion', 'Mobile experience', 'SEO basics', 'Trust and credibility', 'Local visibility', 'Technical health']
    cat_rows = [[Paragraph('<b>Category</b>', styles['small']), Paragraph('<b>Score</b>', styles['small']), Paragraph('<b>Status</b>', styles['small'])]]
    for category in categories:
        value = category_scores.get(category) if isinstance(category_scores, dict) else None
        cat_rows.append([Paragraph(_text(category, 80), styles['body']),
                         Paragraph(_text(str(value) + '/100' if isinstance(value, (int, float)) else 'Not measured', 30), styles['body']),
                         Paragraph(_text('Measured' if isinstance(value, (int, float)) else 'Not verified in this report', 60), styles['small'])])
    cat_table = Table(cat_rows, colWidths=[65 * mm, 35 * mm, 66 * mm], repeatRows=1)
    cat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), paper), ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#e2e5dc')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(cat_table)

    evidence = report.get('evidence') if isinstance(report.get('evidence'), dict) else {}
    story.append(Paragraph('Executive summary', styles['h1']))
    story.append(Paragraph(_text(evidence.get('disclaimer') or 'This report summarizes the public website signals and opportunity gaps saved at the time of the check.', 900), styles['body']))
    story.append(Paragraph('Strengths', styles['h1']))
    story.append(Paragraph('This opportunity report does not currently store a separate verified strengths inventory. No strengths are inferred from missing findings.', styles['small']))

    story.append(Paragraph('Issues found and priority fixes', styles['h1']))
    leaks = report.get('leaks') if isinstance(report.get('leaks'), list) else []
    if not leaks:
        story.append(Paragraph('No issue records were stored in this report. This does not establish that the website has no issues.', styles['body']))
    for index, item in enumerate(leaks[:20], 1):
        if not isinstance(item, dict):
            continue
        severity = str(item.get('severity') or item.get('priority') or '').lower()
        severity_color = critical if severity in ('critical', 'high') else warning if severity in ('warning', 'medium') else success
        title = item.get('title') or item.get('issue') or 'Observed finding'
        story.append(KeepTogether([
            Paragraph('%02d. %s' % (index, _text(title, 240)), styles['h2']),
            Paragraph('<font color="%s"><b>%s</b></font>' %
                      (severity_color.hexval(), _text(severity.upper() or 'PRIORITY NOT RECORDED', 40)), styles['small']),
            Paragraph('<b>Evidence / observation:</b> ' + _text(item.get('source') or item.get('evidence') or item.get('leak') or 'No separate evidence detail was saved.', 1200), styles['body']),
            Paragraph('<b>Why it matters:</b> ' + _text(item.get('impact') or item.get('leak') or 'Business impact has not been separately measured.', 900), styles['body']),
            Paragraph('<b>Recommended fix:</b> ' + _text(item.get('fix') or item.get('recommendation') or 'Review this finding and define a fix.', 900), styles['body']),
            HRFlowable(width='100%', thickness=0.4, color=colors.HexColor('#e2e5dc'), spaceBefore=1 * mm, spaceAfter=2 * mm),
        ]))

    story.append(Paragraph('Screenshots and visual evidence', styles['h1']))
    story.append(Paragraph('Homepage and mobile screenshots were not captured by the saved opportunity report, so this PDF does not present screenshots as evidence. Use the detailed browser audit when screenshot capture is available.', styles['small']))
    story.append(Paragraph('Recommended next steps', styles['h1']))
    solution = report.get('solution') if isinstance(report.get('solution'), dict) else {}
    story.append(Paragraph('<b>%s</b>' % _text(solution.get('name') or 'Review the highest-priority finding', 180), styles['body']))
    story.append(Paragraph(_text(solution.get('why') or 'Confirm the findings, approve a practical fix scope, and re-check the website after implementation.', 1000), styles['body']))
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width='100%', thickness=3, color=reachmark_lime, spaceBefore=2 * mm, spaceAfter=3 * mm))
    story.append(Paragraph('<b>Prepared by Reachmark</b> · <link href="https://reachmarkdigital.xyz" color="#202820">reachmarkdigital.xyz</link>', styles['body']))
    story.append(Paragraph('This report was generated by Reachmark using publicly available website data. Findings reflect the pages and signals saved at the time of the check; dynamic content may not have been observed.', styles['small']))
    doc.build(story)
    return output.getvalue()


def report_pdf_cache_path(report_id):
    """Deterministic cache path keyed by the saved report ID, never by a user path."""
    key = str(report_id or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', key):
        return ''
    root = os.getenv('REPORT_PDF_DIR', '/data/reachmark-reports')
    try:
        os.makedirs(root, exist_ok=True)
        return os.path.join(root, key + '.pdf')
    except OSError:
        fallback = '/tmp/reachmark-reports'
        try:
            os.makedirs(fallback, exist_ok=True)
            return os.path.join(fallback, key + '.pdf')
        except OSError:
            return ''


def save_report_pdf(report_id, payload):
    """Atomically cache the generated PDF against its report ID."""
    path = report_pdf_cache_path(report_id)
    if not path:
        return ''
    directory = os.path.dirname(path)
    try:
        fd, temp_path = tempfile.mkstemp(prefix='.reachmark-', suffix='.pdf', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        return path
    except OSError:
        return ''
