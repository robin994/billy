const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const frontend = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
const translations = fs.readFileSync(path.join(frontend, 'billy-extra-i18n.js'), 'utf8').replace(/^export /gm, '')
function withoutImports(filename) {
  return fs.readFileSync(path.join(frontend, filename), 'utf8')
    .replace(/^import '[^']+'\n/gm, '')
    .replace(/^import\s*\{[\s\S]*?\}\s*from\s*'[^']+'\s*/gm, '')
}

function fixture(t, language = 'en') {
  const dom = new JSDOM('<!doctype html>', { runScripts: 'outside-only', url: 'https://ha.example/billy' })
  t.after(() => dom.window.close())
  dom.window.console.info = () => {}
  const legacyTranslations = fs.readFileSync(path.join(frontend, 'bill-tracker-i18n.js'), 'utf8').replace(/^export /gm, '')
  dom.window.eval(translations + '\n' + legacyTranslations + '\n' + withoutImports('billy-panel.js') + '\n' + withoutImports('billy-widgets.js') + '\n' + withoutImports('bill-tracker-card-impl.js'))
  const category = { id: 'power', name: 'Power', enabled: true, interval_months: 1, color: '#03a9f4', placeholder: { enabled: true, day: 1, amount_mode: 'last', fixed_amount: 0, start_month: '2026-10', due_day: null } }
  const expense = { id: 'provisional', category_id: 'power', category: 'Power', amount: 40, paid_year: 2026, paid_month: 10, year: 2026, month: 10, period_start_year: 2026, period_start_month: 10, period_end_year: 2026, period_end_month: 10, is_placeholder: true, paid: false, reimbursement_status: 'none', split: [] }
  const data = { categories: [category], active_categories: [category], expenses: [expense], payers: [], default_split: [], current_month_unpaid_bills: [expense] }
  const calls = []
  const hass = { language, config: { currency: 'EUR' }, callWS: async request => { calls.push(request); return request.type === 'bill_tracker/list' ? data : {} } }
  const element = tag => {
    const panel = dom.window.document.createElement(tag)
    panel._data = data
    panel._hass = hass
    panel._render()
    return panel
  }
  return { dom, data, category, expense, calls, hass, element }
}

test('type settings toggle shows schedule fields and posts all supported modes', async t => {
  const f = fixture(t)
  const panel = f.element('billy-settings')
  panel._openCategory('power')
  const form = panel.shadowRoot.querySelector('#category-form')
  const fields = form.querySelector('#placeholder-settings')
  const toggle = form.elements.placeholder_enabled
  const mode = form.elements.placeholder_amount_mode
  assert.equal(fields.style.display, 'grid')
  assert.equal(form.elements.placeholder_fixed_amount.disabled, true)
  toggle.checked = false
  toggle.dispatchEvent(new f.dom.window.Event('change'))
  assert.equal(fields.style.display, 'none')
  toggle.checked = true
  toggle.dispatchEvent(new f.dom.window.Event('change'))
  mode.value = 'fixed'
  mode.dispatchEvent(new f.dom.window.Event('change'))
  assert.equal(form.elements.placeholder_fixed_amount.disabled, false)
  form.elements.placeholder_day.value = '31'
  form.elements.placeholder_fixed_amount.value = '25.50'
  form.elements.placeholder_due_day.value = '20'
  form.elements.placeholder_start_month.value = '2026-11'
  await panel._saveCategory({ preventDefault() {}, currentTarget: form }, 'power')
  const posted = f.calls.find(row => row.type === 'bill_tracker/category/update')
  assert.deepEqual(JSON.parse(JSON.stringify(posted.placeholder)), { enabled: true, day: 31, amount_mode: 'fixed', fixed_amount: 25.5, due_day: 20, start_month: '2026-11' })
})

test('new types remain opt in and allow an absent due day', async t => {
  const f = fixture(t)
  const panel = f.element('billy-settings')
  panel._openCategory()
  const form = panel.shadowRoot.querySelector('#category-form')
  assert.equal(form.elements.placeholder_enabled.checked, false)
  assert.equal(form.querySelector('#placeholder-settings').style.display, 'none')
  form.elements.name.value = 'Water'
  await panel._saveCategory({ preventDefault() {}, currentTarget: form }, null)
  const posted = f.calls.find(row => row.type === 'bill_tracker/category/add')
  assert.equal(posted.placeholder.enabled, false)
  assert.equal(posted.placeholder.due_day, null)
})

test('checking a provisional bill opens amount confirmation before paying it', async t => {
  const f = fixture(t)
  const bills = f.element('billy-bills')
  bills._load = async () => {}
  bills._subscribe = () => {}
  f.dom.window.document.body.append(bills)
  assert.match(bills._rowsHtml(), /Provisional bill/)
  const input = bills.shadowRoot.querySelector('[data-paid-id]')
  input.checked = true
  await bills._setPaid(input)
  assert.equal(input.checked, false)
  assert.equal(f.calls.length, 0)
  const form = bills.shadowRoot.querySelector('#bill-form')
  assert.equal(form.elements.paid.checked, true)
  assert.equal(bills.shadowRoot.activeElement, form.elements.amount)
  form.elements.amount.value = '67.50'
  await bills._submitBill({ preventDefault() {}, currentTarget: form }, () => {})
  const update = f.calls.find(row => row.type === 'bill_tracker/update')
  assert.equal(update.expense_id, 'provisional')
  assert.equal(update.amount, 67.5)
  assert.equal(update.paid, true)
})

test('ordinary bills retain the immediate payment toggle', async t => {
  const f = fixture(t)
  f.expense.is_placeholder = false
  const bills = f.element('billy-bills')
  const input = bills.shadowRoot.querySelector('[data-paid-id]')
  input.checked = true
  await bills._setPaid(input)
  assert.equal(f.calls[0].type, 'bill_tracker/set_paid')
})

test('compact bill card opens the same amount confirmation before paying a provisional bill', async t => {
  const f = fixture(t, 'it')
  const card = f.element('bill-tracker-card-impl')
  const input = f.dom.window.document.createElement('input')
  input.type = 'checkbox'
  input.dataset.id = f.expense.id
  input.checked = true
  await card._togglePaid(input)
  assert.equal(f.calls.length, 0)
  assert.equal(input.checked, false)
  assert.equal(card.shadowRoot.getElementById('paid-status').checked, true)
  assert.equal(card.shadowRoot.getElementById('amount').value, '40')
  assert.equal(card._t('placeholderBill'), 'Bolletta provvisoria — conferma l’importo')
})

test('overview shows a provisional bill with no due date', t => {
  const f = fixture(t)
  const dashboard = f.element('billy-dashboard')
  assert.match(dashboard._dueThisMonth(), /Power/)
  assert.match(dashboard._dueThisMonth(), /Provisional bill/)
})

test('Upcoming month filter includes overdue, undated and zero entries without collapsing equal invoices', t => {
  const f = fixture(t)
  f.data.current_month_unpaid_bills.push({ ...f.expense, id: 'other', amount: 0, due_date: '2026-10-01' })
  f.data.current_month_unpaid_bills.push({ ...f.expense, id: 'equal' })
  f.data.upcoming = [{ amount: 999, key: '2099-01', source: 'bill_forecast' }]
  const card = f.element('billy-upcoming-card')
  card.setConfig({ filter: 'unpaid_this_month', limit: 8 })
  const items = card._items()
  assert.equal(items.length, 3)
  assert.equal(items[0].amount, 40)
  assert.equal(items[2].amount, 0)
  assert.match(card.shadowRoot.innerHTML, /Unpaid this month/)
  const filter = card.shadowRoot.querySelector('[data-upcoming-filter]')
  filter.value = 'all'
  filter.dispatchEvent(new f.dom.window.Event('change'))
  assert.equal(card._config.filter, 'all')
})

for (const [language, label] of Object.entries({ en: 'Unpaid this month', it: 'Da pagare questo mese', es: 'Pendientes este mes', fr: 'Impayées ce mois-ci', de: 'Diesen Monat offen', pt: 'Por pagar este mês' })) {
  test(`placeholder controls and Upcoming filter are translated in ${language}`, t => {
    const f = fixture(t, language)
    const card = f.element('billy-upcoming-card')
    card.setConfig({ filter: 'unpaid_this_month' })
    assert.match(card.shadowRoot.innerHTML, new RegExp(label))
    const settings = f.element('billy-settings')
    settings._openCategory('power')
    assert.doesNotMatch(settings.shadowRoot.querySelector('#category-form').textContent, /placeholderDay|autoPlaceholder/)
  })
}
