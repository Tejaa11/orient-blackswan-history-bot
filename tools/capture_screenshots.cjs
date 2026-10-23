/* Optional submission evidence tool; requires Playwright and installed Chrome.
 * It submits actual questions through the running UI. It never injects answers.
 * Example: NODE_PATH=tmp/browser/node_modules node tools/capture_screenshots.cjs
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const screenshotDir = process.env.SCREENSHOT_DIR || 'docs/screenshots';
const evaluationReport = process.env.EVALUATION_REPORT || 'reports/evaluation.json';
const uiReport = process.env.UI_REPORT || 'reports/ui_browser.json';

(async () => {
  fs.mkdirSync(path.join(root, screenshotDir), { recursive: true });
  const evaluation = JSON.parse(fs.readFileSync(path.join(root, evaluationReport), 'utf8'));
  let assessment = evaluation
    .cases.filter(c => /^q[1-5]$/.test(c.id));
  if (assessment.length !== 5) throw new Error('Run python -m history_bot evaluate first.');
  if (process.env.CAPTURE_CASES) assessment = assessment.filter(c => process.env.CAPTURE_CASES.split(',').includes(c.id));
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1600 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const reportPath = path.join(root, uiReport);
  const report = process.env.CAPTURE_CASES && fs.existsSync(reportPath)
    ? JSON.parse(fs.readFileSync(reportPath, 'utf8'))
    : { cases: [] };
  Object.assign(report, { captured_at_utc: new Date().toISOString(), method: 'Actual Chrome UI submissions; no injected answers', evaluation_report: evaluationReport, chat_model: evaluation.chat_model, embedding_model: evaluation.embedding_model });
  try {
    await page.goto(process.env.APP_URL || 'http://127.0.0.1:8501');
    await page.getByRole('textbox', { name: 'Ask the catalogue' }).waitFor({ timeout: 60000 });
    await page.screenshot({ path: path.join(root, screenshotDir, '00-ready.png'), fullPage: true, animations: 'disabled' });
    for (const item of assessment) {
      await page.getByRole('button', { name: 'Reset session', exact: true }).click();
      await page.getByRole('heading', { name: 'An answer you can trace.', exact: true }).waitFor();
      await page.getByRole('textbox', { name: 'Ask the catalogue' }).fill(item.question);
      await page.getByRole('button', { name: 'Find an answer →', exact: true }).click();
      await page.getByRole('heading', { name: 'From the catalogue', exact: true }).waitFor({ timeout: 600000 });
      await page.waitForFunction(() => document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state') === 'notRunning');
      const expander = page.getByText(/Read the exact supporting passages/);
      if (await expander.count()) await expander.click();
      if (item.supported) {
        const passageLabel = page.getByText('Passage 1 · PDF page 2', { exact: true });
        await passageLabel.waitFor();
        await passageLabel.scrollIntoViewIfNeeded();
        await page.getByTestId('stMain').getByTestId('stExpander').evaluate(el => Promise.allSettled(el.getAnimations({ subtree: true }).map(a => a.finished)));
      }
      await page.getByRole('button', { name: 'Reset session', exact: true }).waitFor({ state: 'visible' });
      const body = await page.getByTestId('stMain').innerText();
      if (!body.includes(item.question)) throw new Error(`Question missing: ${item.id}`);
      if (!item.supported && !body.includes('Not found')) throw new Error(`Abstention missing: ${item.id}`);
      if (item.supported && !body.includes('PDF page 2')) throw new Error(`Source missing: ${item.id}`);
      const screenshot = `${screenshotDir}/${item.id}.png`;
      await page.screenshot({ path: path.join(root, screenshot), fullPage: true, animations: 'disabled' });
      report.cases = report.cases.filter(c => c.id !== item.id);
      report.cases.push({ id: item.id, question: item.question, screenshot, rendered_ui_text: body, pass: true });
      fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
      console.log(`${item.id}: captured actual response`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: path.join(root, screenshotDir, '06-mobile.png'), fullPage: true, animations: 'disabled' });
    report.mobile = { width: 390, screenshot: `${screenshotDir}/06-mobile.png`, horizontal_overflow: await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth) };
    await page.getByRole('button', { name: 'Reset session', exact: true }).click();
    await page.getByRole('heading', { name: 'An answer you can trace.', exact: true }).waitFor();
    report.reset = { pass: await page.getByRole('heading', { name: 'From the catalogue', exact: true }).count() === 0 };
    await page.getByRole('button', { name: 'Find an answer →', exact: true }).click();
    await page.getByText('Enter a question about the history catalogue.', { exact: true }).waitFor();
    report.empty_input = { pass: true };
    report.browser_errors = errors;
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
