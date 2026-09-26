import { chromium } from '@playwright/test';

const base = (process.env.BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

async function expectStatus(path, status, options = {}) {
  const r = await page.request.fetch(base + path, options);
  if (r.status() !== status) throw new Error(path + ' returned ' + r.status() + ', expected ' + status);
  return r;
}

try {
  await expectStatus('/api/map/state', 401);
  await expectStatus('/api/map/search', 401, {
    method: 'POST',
    data: { query: 'Lagos, Nigeria' },
    headers: { 'Content-Type': 'application/json' }
  });
  await expectStatus('/api/map/scans', 401, {
    method: 'POST',
    data: { category: 'Bakery', label: 'Lagos' },
    headers: { 'Content-Type': 'application/json' }
  });
  await page.goto(base + '/signin', { waitUntil: 'networkidle' });
  if (!(await page.locator('input').count())) throw new Error('signin form unavailable');
  console.log('Independent map-browser access-control flow: PASS');
} finally {
  await browser.close();
}
