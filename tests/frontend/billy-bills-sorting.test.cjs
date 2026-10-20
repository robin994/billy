const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const frontend = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
function source(name) {
  return fs.readFileSync(path.join(frontend, name), 'utf8')
    .replace(/^import '[^']+'\n/gm, '')
    .replace(/^import\s*\{[\s\S]*?\}\s*from\s*'[^']+'\s*/gm, '')
    .replace(/^export /gm, '')
}

function fixture(t, language = 'en') {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only', url: 'https://ha.example/billy?view=bills',
  })
  t.after(() => dom.window.close())
  dom.window.console.info = () => {}
  dom.window.eval(source('billy-extra-i18n.js') + '\n' + source('billy-panel.js'))
  const category = { id: 'power', name: 'Power', enabled: true, color: '#03a9f4' }
  const expenses = [
    { id: 'current', category_id: 'power', category: 'Power', amount: 3296.90,
      paid_year: 2026, paid_month: 10, due_date: '2026-07-10',
      payment_date: '2026-08-04', paid: true, reimbursement_status: 'none',
      document_path: '/media/invoice.pdf', created_at: '2026-10-01', split: [] },
    { id: 'late-payment', category_id: 'power', category: 'Power', amount: 22.40,
      paid_year: 2026, paid_month: 8, due_date: '2026-12-14',
      payment_date: '2026-10-10', paid: true, reimbursement_status: 'none',
      created_at: '2026-08-01', split: [] },
    { id: 'unpaid', category_id: 'power', category: 'Power', amount: 15,
      paid_year: 2026, paid_month: 9, due_date: '2026-11-03',
      payment_date: null, paid: false, reimbursement_status: 'none',
      created_at: '2026-09-01', split: [] },
    { id: 'undated', category_id: 'power', category: 'Power', amount: 12,
      paid_year: 2026, paid_month: 6, due_date: null,
      payment_date: null, paid: false, reimbursement_status: 'none',
      created_at: '2026-06-01', split: [] },
  ]
  const data = { categories: [category], expenses, payers: [], pending_imports: [] }
  const hass = { language, user: { id: 'test-user' }, config: { currency: 'EUR' } }
  const panel = dom.window.document.createElement('billy-bills')
  panel._data = data
  panel.hass = hass
  panel._render()
  const ids = () => panel._filtered().map(row => row.id)
  const sort = mode => {
    const select = panel.shadowRoot.getElementById('bill-sort')
    select.value = mode
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
  }
  return { dom, panel, data, ids, sort, hass }
}

test('Bills preserves legacy billing-month sorting until selected otherwise', t => {
  const f = fixture(t)
  assert.deepEqual(f.ids(), ['current', 'unpaid', 'late-payment', 'undated'])
  assert.equal(f.panel.shadowRoot.getElementById('bill-sort').value, 'billing')
  f.panel._page = 3
  f.sort('due')
  assert.equal(f.panel._page, 1)
  assert.deepEqual(f.ids(), ['late-payment', 'unpaid', 'current', 'undated'])
  f.sort('payment')
  assert.deepEqual(f.ids(), ['late-payment', 'current', 'unpaid', 'undated'])
  f.sort('billing')
  assert.deepEqual(f.ids(), ['current', 'unpaid', 'late-payment', 'undated'])
})

test('payment-date sorting retains unpaid bills at the bottom and cooperates with filters', t => {
  const f = fixture(t)
  f.sort('payment')
  f.panel._status = 'unpaid'
  assert.deepEqual(f.ids(), ['unpaid', 'undated'])
  f.panel._status = 'paid'
  assert.deepEqual(f.ids(), ['late-payment', 'current'])
  f.panel._year = '2026'
  assert.deepEqual(f.ids(), ['late-payment', 'current'])
  assert.deepEqual(f.panel._data.expenses.map(row => row.id),
    ['current', 'late-payment', 'unpaid', 'undated'], 'sorting must not mutate backend data')
})

test('sort choice persists per user across panel instances', t => {
  const f = fixture(t, 'it')
  f.sort('due')
  assert.equal(f.dom.window.localStorage.getItem('billy.bills.sort.v1:test-user'), 'due')
  const second = f.dom.window.document.createElement('billy-bills')
  second._data = f.data
  second.hass = f.hass
  assert.equal(second._sort, 'due')
  second._render()
  assert.equal(second.shadowRoot.getElementById('bill-sort').value, 'due')
  assert.match(second.shadowRoot.textContent, /Ordina bollette|Scadenza \(recenti prima\)/)
})

test('PDF presence never changes the number of action slots or the row structure', t => {
  const f = fixture(t)
  const rows = [...f.panel.shadowRoot.querySelectorAll('.bill-row')]
  assert.equal(rows.length, 4)
  const withPdf = rows[0].querySelector('.bill-actions')
  const withoutPdf = rows[1].querySelector('.bill-actions')
  assert.equal(withPdf.children.length, 3)
  assert.equal(withoutPdf.children.length, 3)
  assert.ok(withPdf.querySelector('.document-action[data-open-document="current"]'))
  assert.ok(withoutPdf.querySelector('.bill-document-placeholder'))
  for (const row of rows) {
    assert.ok(row.querySelector('.bill-month'))
    assert.ok(row.querySelector('.bill-state'))
    assert.ok(row.querySelector('.bill-amount'))
    assert.ok(row.querySelector('[data-edit-bill]'))
    assert.ok(row.querySelector('[data-delete-bill]'))
  }
  assert.match(rows[0].querySelector('.bill-month').textContent, /Aug 04, 2026|Aug 4, 2026/)
  const styles = f.panel._styles()
  assert.match(styles, /grid-template-areas:"paid swatch main month state amount actions"/)
  assert.match(styles, /\.list-card\{container-type:inline-size\}/)
})

test('sort labels are translated in all supported languages', t => {
  const translations = {
    en: 'Sort bills', it: 'Ordina bollette', es: 'Ordenar facturas',
    fr: 'Trier les factures', de: 'Rechnungen sortieren', pt: 'Ordenar contas',
  }
  for (const [language, label] of Object.entries(translations)) {
    const f = fixture(t, language)
    assert.equal(f.panel.shadowRoot.getElementById('bill-sort').getAttribute('aria-label'), label)
  }
})
