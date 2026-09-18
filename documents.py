"""Private, branded PDF exports from saved records. No invented legal terms or prices."""
import io,os
from decimal import Decimal
from xml.sax.saxutils import escape
from flask import Response,abort
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,KeepTogether
from operations import CURRENCIES
FONTDIR=os.path.join(os.path.dirname(__file__),'static','pdf-fonts')
pdfmetrics.registerFont(TTFont('Reachmark',os.path.join(FONTDIR,'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('ReachmarkBold',os.path.join(FONTDIR,'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('Reachmark',normal='Reachmark',bold='ReachmarkBold',italic='Reachmark',boldItalic='ReachmarkBold')
def amount(value,currency):return 'Tailored quote — amount not set' if value is None else f'{currency} {Decimal(value)/(10**CURRENCIES[currency]):,.{CURRENCIES[currency]}f}'
def pdf(title,subtitle,sections,stamp,studio):
    buf=io.BytesIO();styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RMBody',fontName='Reachmark',fontSize=9.5,leading=15,spaceAfter=9,textColor=colors.HexColor('#30382c'),wordWrap='CJK'))
    styles.add(ParagraphStyle(name='RMTitle',fontName='ReachmarkBold',fontSize=26,leading=32,spaceAfter=14,textColor=colors.HexColor('#26351e')))
    styles.add(ParagraphStyle(name='RMHeading',fontName='ReachmarkBold',fontSize=12,leading=17,spaceBefore=14,spaceAfter=7))
    def text(value):return escape(str(value or 'Not recorded')).replace('\n','<br/>')
    story=[Paragraph(text(studio),styles['RMHeading']),Paragraph(text(title),styles['RMTitle']),Paragraph(text(subtitle),styles['RMBody']),Paragraph('Generated '+text(stamp),styles['RMBody'])]
    for heading,value in sections:story.extend([Paragraph(text(heading),styles['RMHeading']),Paragraph(text(value),styles['RMBody'])])
    def page(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#cce57b'));canvas.setLineWidth(3);canvas.line(42,43,553,43);canvas.setFont('Reachmark',8);canvas.setFillColor(colors.HexColor('#56644a'));canvas.drawString(42,28,'REACHMARK · Saved-record export');canvas.drawRightString(553,28,f'Page {doc.page}')
    doc=SimpleDocTemplate(buf,pagesize=(595,842),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=60,title=title,author=studio)
    doc.build(story,onFirstPage=page,onLaterPages=page);return buf.getvalue()
def register_documents(app,db,now,settings):
    @app.get('/api/documents/<kind>/<record_id>.pdf')
    def export_pdf(kind,record_id):
        if kind not in ('audit','proposal','contract','brief'):abort(404)
        table='leads' if kind=='audit' else 'contracts' if kind=='contract' else 'projects'
        with db() as c:
            row=c.execute('SELECT * FROM '+table+' WHERE id=?',(record_id,)).fetchone()
            if not row:abort(404)
            r=dict(row)
            client=c.execute('SELECT name,city,address,email FROM leads WHERE id=?',(r.get('lead_id',''),)).fetchone() if kind in ('proposal','brief') else None
            review=c.execute('SELECT * FROM lead_reviews WHERE lead_id=?',(record_id,)).fetchone() if kind=='audit' else None
        if kind=='audit':
            title='Business audit report';subtitle=r['name']+' · Evidence summary, not a guarantee'
            sections=[('Business and source',f"{r['name']}\n{r['city']}\n{r['address']}\nSource: {r['source']}\n{r['source_url']}\nLast imported / seen: {r['source_seen_at']}"),('Website evidence',f"Listed URL: {r['website'] or 'No website listed in source'}\nSource status: {r['status']}\nAutomated observation: {r['audit_status'] or 'Not checked'}\nChecked: {r['checked_at'] or 'Not checked'}\n{r['audit_reason'] or 'No URL check recorded.'}"),('Manual verification',f"{review['verification']}\n{review['note']}\n{review['evidence_url']}\nReviewed: {review['reviewed_at']}" if review else 'No manual verification recorded.'),('Limitations','A missing source URL is not proof of no website. Connection errors do not establish closure or permanent unavailability. Contact fields and ownership must be independently verified.')]
        elif kind=='contract':
            title='Contract record';subtitle=r['title']+' · '+('DRAFT / NOT AGREED' if r['status'] in ('Draft','Sent') else 'MANUALLY RECORDED STATUS: '+r['status'])
            sections=[('Client',r['client']+'\n'+r['email']),('Recorded agreement',f"Status: {r['status']}\nValue: {amount(r['amount_minor'],r['currency'])}\nPayments recorded: {amount(r['paid_minor'],r['currency'])}"),('Recorded scope and notes',r['notes']),('Important distinction','This PDF is an export of your tracker, not an electronically signed agreement, invoice, payment receipt or independently verified contract. No additional terms are implied.')]
        else:
            title='Website proposal & quote' if kind=='proposal' else 'Project brief';subtitle=r['title']+' · DRAFT FOR REVIEW'
            sections=[('Client',f"{client['name']}\n{client['city']}\n{client['address']}\n{client['email']}" if client else 'No business linked'),('Project',f"Stage: {r['stage']}\nLead reference: {r['lead_id'] or 'Not linked'}\nContract reference: {r['contract_id'] or 'Not linked'}"),('Proposed scope',r['scope']),('Tailored quote',amount(r['quote_minor'],r['currency'])),('Next action',f"{r['next_action'] or 'Not set'}\nTarget date: {r['due_date'] or 'Not set'}"),('Approval and terms','Draft only. Pricing, scope, taxes, payment terms, schedule and acceptance must be expressly agreed with the client. Linked contract records remain separate. No automatic sending, signing or payment collection.')]
        content=pdf(title,subtitle,sections,now(),settings()['agency'] or 'Reachmark Studio')
        return Response(content,mimetype='application/pdf',headers={'Content-Disposition':f'attachment; filename="reachmark-{kind}-{record_id[:12]}.pdf"','Cache-Control':'no-store'})
