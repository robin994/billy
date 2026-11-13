const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM, ResourceLoader } = require('jsdom')

const frontend = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
function source(name) {
  return fs.readFileSync(path.join(frontend, name), 'utf8')
    .replace(/^import '[^']+'\n/gm, '')
    .replace(/^import\s*\{[\s\S]*?\}\s*from\s*'[^']+'\s*/gm, '')
    .replace(/^export /gm, '')
}

const PDF_BASE64 = Buffer.from('%PDF-1.4\ntest bill').toString('base64')

function fixture(t, { userAgent = 'Mozilla/5.0 (X11; Linux x86_64)', androidApp = false, androidAppV2 = false } = {}) {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only', url: 'https://ha.example/billy?view=bills',
    resources: new ResourceLoader({ userAgent }),
  })
  t.after(() => dom.window.close())
  dom.window.console.info = () => {}
  if (androidApp) dom.window.externalApp = { getExternalAuth() {} }
  if (androidAppV2) dom.window.externalAppV2 = { postMessage() {} }
  const created = []
  const revoked = []
  dom.window.URL.createObjectURL = blob => { created.push(blob); return `blob:https://ha.example/${created.length}` }
  dom.window.URL.revokeObjectURL = url => { revoked.push(url) }
  const clicks = []
  dom.window.HTMLAnchorElement.prototype.click = function click() {
    clicks.push({ href: this.href, download: this.download, attached: this.isConnected })
  }
  const timers = []
  dom.window.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length }
  dom.window.eval(source('bill-tracker-i18n.js') + '\n' + source('billy-extra-i18n.js') + '\n' + source('billy-panel.js'))
  const calls = []
  const hass = {
    language: 'en', user: { id: 'test-user', is_admin: true }, config: { currency: 'EUR' },
    async callWS(message) {
      calls.push(message)
      if (message.type === 'bill_tracker/document/read') {
        return { content_base64: PDF_BASE64, filename: `billy-${message.expense_id}.pdf`, mime_type: 'application/pdf' }
      }
      throw new Error(`unexpected ${message.type}`)
    },
  }
  const category = { id: 'power', name: 'Power', enabled: true, color: '#03a9f4' }
  const expenses = [
    { id: 'bill001', category_id: 'power', category: 'Power', amount: 10,
      paid_year: 2026, paid_month: 10, due_date: null, payment_date: null, paid: false,
      reimbursement_status: 'none', document_path: 'billy/documents/2026/10/Power/bill001.pdf',
      created_at: '2026-10-01', split: [] },
  ]
  const panel = dom.window.document.createElement('billy-bills')
  panel._data = { categories: [category], expenses, payers: [], pending_imports: [] }
  panel.hass = hass
  panel._render()
  const flush = () => new Promise(resolve => setImmediate(resolve))
  return { dom, panel, calls, clicks, created, revoked, timers, flush }
}

test('bill rows keep their three action slots; no extra row button is added', t => {
  const f = fixture(t)
  const actions = f.panel.shadowRoot.querySelector('.bill-actions')
  assert.equal(actions.children.length, 3)
  assert.equal(f.panel.shadowRoot.querySelector('[data-download-document]'), null)
})

test('View PDF keeps the inline viewer in desktop browsers', async t => {
  const f = fixture(t, { userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36' })
  f.panel.shadowRoot.querySelector('[data-open-document="bill001"]').click()
  await f.flush()
  const modal = f.panel.shadowRoot.getElementById('bill-pdf-modal')
  assert.equal(modal.hidden, false)
  assert.ok(modal.querySelector('iframe').src.startsWith('blob:'))
  assert.equal(f.clicks.length, 0, 'no download in a desktop browser')
})

for (const [name, options] of [
  ['the Android V1 external app bridge', { androidApp: true }],
  ['the Android V2 external app bridge (current apps)', { androidAppV2: true }],
  ['the current Android app user agent', { userAgent: 'Mozilla/5.0 (Linux; Android 10; K; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/156.0.0.0 Mobile Safari/537.36 Home Assistant/2026.10.1-24906 (Android 17; Pixel Fold)' }],
  ['an older Android app user agent', { userAgent: 'Mozilla/5.0 (Linux; Android 13; wv) Chrome/120.0 Mobile Safari/537.36 HomeAssistant/2024.1.0-1234 (Android 13; Pixel 7)' }],
]) {
  test(`View PDF downloads instead of opening the inline viewer when detected via ${name}`, async t => {
    const f = fixture(t, options)
    f.panel.shadowRoot.querySelector('[data-open-document="bill001"]').click()
    await f.flush()
    assert.equal(f.panel.shadowRoot.getElementById('bill-pdf-modal').hidden, true)
    assert.equal(f.clicks.length, 1)
    assert.equal(f.clicks[0].download, 'billy-bill001.pdf')
  })
}

test('the iOS app keeps the inline viewer', async t => {
  const f = fixture(t, { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Home Assistant/2026.11 (io.robbie.HomeAssistant; build:2026.1234; iOS 18.0.0)' })
  f.panel.shadowRoot.querySelector('[data-open-document="bill001"]').click()
  await f.flush()
  assert.equal(f.panel.shadowRoot.getElementById('bill-pdf-modal').hidden, false)
  assert.equal(f.clicks.length, 0)
})

test('the bill editor has no separate download button; View PDF downloads on Android', async t => {
  const f = fixture(t, { androidAppV2: true })
  const card = f.dom.window.document.createElement('div')
  card.innerHTML = f.panel._documentToolsHtml(f.panel._data.expenses[0])
  f.panel._wireDocumentEditor(card, 'bill001')
  assert.equal(card.querySelector('[data-pdf-download]'), null)
  card.querySelector('[data-pdf-view]').click()
  await f.flush()
  assert.deepEqual(f.calls.map(call => call.type), ['bill_tracker/document/read'])
  assert.equal(f.calls[0].expense_id, 'bill001')
  assert.equal(f.clicks.length, 1)
  assert.equal(f.clicks[0].download, 'billy-bill001.pdf')
  assert.ok(f.clicks[0].href.startsWith('blob:'))
  assert.equal(f.clicks[0].attached, true, 'anchor must be in the document when clicked')
  assert.equal(f.created[0].type, 'application/pdf')
  assert.deepEqual(f.revoked, [], 'blob URL stays alive for the companion app to read it')
  assert.equal(f.timers.at(-1).ms, 60000)
  f.timers.at(-1).fn()
  assert.deepEqual(f.revoked, [f.clicks[0].href])
})
