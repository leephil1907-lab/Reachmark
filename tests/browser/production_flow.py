"""Complete owner/review/project/PDF workflow on disposable data only."""
import os,tempfile,threading
from pathlib import Path
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright,expect
class Quiet(WSGIRequestHandler):
    def log_request(self,*a,**kw):pass
with tempfile.TemporaryDirectory() as tmp:
    os.environ['DATABASE_PATH']=str(Path(tmp)/'ui.sqlite3');os.environ['OWNER_PASSWORD_HASH']=generate_password_hash('test-owner-password');os.environ['SECRET_KEY']='temporary-test-secret-not-for-production-12345';os.environ.pop('DASHBOARD_PASSWORD',None)
    import web.app as module
    module.add_lead({'name':'Temporary Café','city':'Fixture City','phone':'1234567890','email':'test@example.test','website':''})
    module.add_lead({'name':'Temporary Café branch','city':'Fixture City','phone':'1234567890','website':''})
    server=make_server('127.0.0.1',0,module.app,threaded=True,request_handler=Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
            page.goto(base);expect(page.locator('body')).to_be_visible();page.goto(base+'/login');page.locator('#password').fill('test-owner-password');page.locator('#login-form button[type=submit], form button[type=submit]').first.click();
            try:page.wait_for_url('**/workspace**',timeout=8000)
            except Exception:page.goto(base+'/login');page.locator('#password').fill('test-owner-password');page.locator('#login-form button[type=submit], form button[type=submit]').first.click();page.wait_for_url('**/workspace**',timeout=15000)
            expect(page.locator('#stat-total')).to_have_text('2')
            page.locator('[data-tour="skip"]').click();
            page.locator('.nav[data-page="leads"]').click();page.locator('#filter-contact').select_option('email');expect(page.locator('#lead-table tr')).to_have_count(1);page.locator('#lead-table button').click()
            page.get_by_text('Manual verification and evidence',exact=True).click();page.locator('#review-form [name="verification"]').select_option('NO_SITE_FOUND');page.locator('#review-form [name="evidence_url"]').fill('https://example.test/research');page.locator('#review-form [name="note"]').fill('Manually searched the business name and checked the source listing.');page.locator('#review-form [type="submit"]').click();expect(page.locator('#review-time')).to_contain_text('Manual review:')
            with page.expect_download() as download:page.get_by_role('link',name='Audit report PDF').click()
            saved=Path(tmp)/'audit.pdf';download.value.save_as(saved);assert saved.read_bytes().startswith(b'%PDF')
            page.locator('.close-inline').click();page.locator('.nav[data-page="projects"]').click();page.get_by_role('button',name='New project').click();page.locator('#project-form [name="title"]').fill('Temporary café project');page.locator('#project-form [name="stage"]').select_option('Proposal');page.locator('#project-form [name="scope"]').fill('A simple saved website scope.');page.locator('#project-form [name="quote"]').fill('100.50');page.locator('#project-form [name="due_date"]').fill('2026-01-01');page.locator('#project-form [name="next_action"]').fill('Review the client preview');page.locator('#project-form [type="submit"]').click();expect(page.locator('#project-board')).to_contain_text('Temporary café project');expect(page.locator('#project-reminders')).to_contain_text('1 overdue')
            page.get_by_role('button',name='Open project',exact=False).click()
            with page.expect_download() as download:page.get_by_role('link',name='Draft proposal & quote PDF').click()
            saved=Path(tmp)/'proposal.pdf';download.value.save_as(saved);assert saved.read_bytes().startswith(b'%PDF')
            page.get_by_role('button',name='Close project',exact=True).click();page.screenshot(path=str(Path(tmp)/'project-board-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});overflow=page.evaluate("""() => ({scrollWidth:document.documentElement.scrollWidth,innerWidth:innerWidth,items:[...document.querySelectorAll('body *')].map(el=>{const r=el.getBoundingClientRect();return {tag:el.tagName,id:el.id,cls:el.className,x:r.x,right:r.right,width:r.width}}).filter(x=>x.right>innerWidth+1||x.x< -1).slice(0,20)})""");assert overflow['scrollWidth']<=overflow['innerWidth'],overflow;page.screenshot(path=str(Path(tmp)/'project-board-mobile.png'),full_page=True)
            page.evaluate("navigate('crew')");expect(page.locator('#crew-agent-grid .crew-agent')).to_have_count(8);expect(page.locator('#crew-run-hint')).to_contain_text('Nothing is ever sent');expect(page.locator('#crew-guardrails')).to_contain_text('needs a separate owner approval');expect(page.locator('#page-crew')).to_be_visible();page.evaluate("navigate('settings')");page.get_by_role('button',name='Sign out of owner session').click();expect(page).to_have_url(base+'/login');assert page.request.get(base+'/api/projects').status==401
            assert not errors,errors;print('PASS: owner login/CSRF, private pages, lead filters, evidence review, PDF downloads, project board, overdue reminders, AI crew console, mobile, logout. Disposable records only.');b.close()
    finally:server.shutdown();thread.join(timeout=5)
