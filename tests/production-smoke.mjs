import { chromium } from '@playwright/test';

const base = (process.env.BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

async function expectStatus(path, status = 200) {
  const response = await page.request.get(base + path);
  if (response.status() !== status) throw new Error(path + ' returned ' + response.status() + ', expected ' + status);
  return response;
}

try {
  const health = await expectStatus('/healthz');
  const healthJson = await health.json();
  if (healthJson.status !== 'ok') throw new Error('healthz did not report ok');

  for (const path of ['/', '/about', '/showcase', '/pricing', '/enquire', '/signin', '/signup', '/receptionist', '/robots.txt', '/sitemap.xml', '/static/manifest.webmanifest', '/static/sw.js']) {
    await expectStatus(path);
  }

  await page.goto(base + '/', { waitUntil: 'networkidle' });
  if (!(await page.locator('header.pub-head').count())) throw new Error('public header missing');
  if (!(await page.locator('#pub-menu-btn').count())) throw new Error('mobile menu control missing');
  if (!(await page.locator('a[href="/showcase"]').count())) throw new Error('showcase navigation missing');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: 'networkidle' });
  const menuButton = page.locator('#pub-menu-btn');
  if (!(await menuButton.isVisible())) throw new Error('mobile menu button is not visible at 390px');
  await menuButton.click();
  if (!(await page.locator('#pub-menu').isVisible())) throw new Error('mobile navigation did not open');

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(base + '/signin', { waitUntil: 'networkidle' });
  if (!(await page.locator('input').count())) throw new Error('signin form inputs missing');

  const manifest = await (await page.request.get(base + '/static/manifest.webmanifest')).json();
  for (const required of ['name', 'short_name', 'start_url', 'scope', 'display', 'icons']) {
    if (!manifest[required]) throw new Error('manifest missing ' + required);
  }

  console.log('Production public/browser flow: PASS');
} finally {
  await browser.close();
}
