const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')
const root = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
const src = name => fs.readFileSync(path.join(root, name), 'utf8')
  .replace(/^import '[^']+'\n/gm, '')
  .replace(/^import\s*\{[\s\S]*?\}\s*from\s*'[^']+'\s*\n/gm, '')
  .replace(/^export /gm, '')
const settled = () => new Promise(resolve => setTimeout(resolve, 25))

function fixture(t) {
  const dom = new JSDOM('<!doctype html><body></body></html>', {
    runScripts: 'outside-only', url: 'https://ha.example/billy',
  })
  t.after(() => dom.window.close())
  dom.window.console.info = () => {}
  dom.window.confirm = () => true
  dom.window.eval([src('billy-extra-i18n.js'), src('billy-accounts.js'),
    src('billy-income.js'), src('billy-panel.js')].join('\n'))
  const houses = [{ id: 'a', name: 'Main home' }, { id: 'b', name: 'Vacation' }]
  const bills = [
    { id: 'bill1', house_id: 'a', category_id: 'electricity', amount: 100 },
    { id: 'bill2', house_id: 'b', category_id: 'electricity', amount: 250 },
  ].map(x => ({ ...x, category: 'Electricity', paid_year: 2026, paid_month: 10,
    year: 2026, month: 10, paid: true, payment_date: '2026-10-10',
    period_start_year: 2026, period_start_month: 10,
    period_end_year: 2026, period_end_month: 10, split: [] }))
  const calls = []
  const snapshot = (house = 'all') => {
    const expenses = bills.filter(x => house === 'all' || x.house_id === house)
    const value = expenses.reduce((sum, x) => sum + x.amount, 0)
    return {
      houses, default_house_id: 'a', currency: 'EUR', expenses,
      categories: [{ id: 'electricity', name: 'Electricity', enabled: true,
        interval_months: 1, color: '#315bb9' }],
      payers: [], active_payers: [], recurring_expenses: [], recurring_history: [],
      recurring_occurrences: [], recurring_payments: [], incomes: [], income_rules: [],
      income_categories: [], accounts: [], internal_transfers: [],
      default_split: [], account_balances: { accounts: [], total: 0 },
      settlements: [], debts: [], balances: [], monthly: [], cashflow_monthly: [],
      normalized_monthly: [], forecast: [], normalized_forecast: [],
      upcoming: [], current_month_recurring: [], current_month_unpaid_bills: [],
      income_monthly: [], income_forecast: [], income_summary: {},
      summary: { current_month: value, year_total: value, next_month_estimate: 0,
        outstanding_total: 0, recurring_monthly_equivalent: 0 },
    }
  }
  const hass = {
    language: 'en', locale: { language: 'en' }, config: { currency: 'EUR' },
    connection: { subscribeEvents: async () => () => {} },
    callWS: async msg => {
      calls.push({ ...msg })
      if (msg.type === 'bill_tracker/list') return snapshot(msg.house_id)
      if (msg.type === 'bill_tracker/parser/list') return { catalog: { parsers: [] } }
      if (msg.type === 'bill_tracker/parser/imports') return []
      if (msg.type === 'bill_tracker/update/status') return {}
      if (msg.type === 'bill_tracker/house/add') {
        const result = { id: 'c', name: msg.name }; houses.push(result); return result
      }
      if (msg.type === 'bill_tracker/house/update') {
        const target = houses.find(x => x.id === msg.house_id); target.name = msg.name; return target
      }
      return {}
    },
  }
  return { dom, snapshot, hass, houses, bills, calls }
}

test('Houses settings create and rename houses without a second HA integration', async t => {
  const f = fixture(t)
  const settings = f.dom.window.document.createElement('billy-settings')
  f.dom.window.document.body.append(settings)
  settings._hass = f.hass
  settings._data = f.snapshot()
  settings.section = 'houses'
  assert.ok(settings.shadowRoot.getElementById('add-house'))
  settings.shadowRoot.getElementById('add-house').click()
  let form = settings.shadowRoot.getElementById('house-form')
  form.elements.namedItem('name').value = 'Mountain'
  form.dispatchEvent(new f.dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settled()
  assert.equal(f.houses[2].name, 'Mountain')
  settings.shadowRoot.querySelector('[data-edit-house="b"]').click()
  form = settings.shadowRoot.getElementById('house-form')
  form.elements.namedItem('name').value = 'Beach'
  form.dispatchEvent(new f.dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settled()
  assert.equal(f.houses[1].name, 'Beach')
  assert.ok(settings.shadowRoot.querySelector('[data-default-house="b"]'))
})

test('Bills filter by house and the new bill form inherits the selected house', t => {
  const f = fixture(t)
  const component = f.dom.window.document.createElement('billy-bills')
  f.dom.window.document.body.append(component)
  component._hass = f.hass
  component._data = f.snapshot()
  component._render()
  assert.equal(component._filtered().length, 2)
  const selector = component.shadowRoot.getElementById('bill-house')
  selector.value = 'b'
  selector.dispatchEvent(new f.dom.window.Event('change', { bubbles: true }))
  assert.deepEqual(component._filtered().map(x => x.id), ['bill2'])
  component.shadowRoot.getElementById('add-bill').click()
  const form = component.shadowRoot.getElementById('bill-form')
  assert.equal(form.elements.namedItem('house_id').value, 'b')
  component.shadowRoot.getElementById('bill-cancel').click()
  selector.value = 'all'
  selector.dispatchEvent(new f.dom.window.Event('change', { bubbles: true }))
  assert.equal(component._filtered().length, 2)
})

test('Recurring expenses have a house filter and new subscriptions inherit its selection', t => {
  const f = fixture(t)
  const component = f.dom.window.document.createElement('billy-recurring')
  f.dom.window.document.body.append(component)
  component._hass = f.hass
  component._data = f.snapshot()
  component._data.recurring_expenses = [
    { id: 'r1', house_id: 'a', kind: 'subscription', name: 'Internet',
      amount: 20, interval_months: 1, active: true,
      start_date: '2026-09-01', status: 'active', reimbursement_status: 'none' },
    { id: 'r2', house_id: 'b', kind: 'subscription', name: 'Heating',
      amount: 40, interval_months: 1, active: true,
      start_date: '2026-09-01', status: 'active', reimbursement_status: 'none' },
  ]
  component._render()
  assert.equal(component._filtered().length, 2)
  const selector = component.shadowRoot.getElementById('recurring-house')
  selector.value = 'b'
  selector.dispatchEvent(new f.dom.window.Event('change', { bubbles: true }))
  assert.equal(component._filtered().length, 1)
  assert.equal(component._filtered()[0].name, 'Heating')
  component.shadowRoot.getElementById('add-recurring').click()
  const form = component.shadowRoot.getElementById('recurring-form')
  assert.equal(form.elements.namedItem('house_id').value, 'b')
})

test('Dashboard house selector scopes WebSocket totals and All restores the aggregate', async t => {
  const f = fixture(t)
  const dashboard = f.dom.window.document.createElement('billy-dashboard')
  f.dom.window.document.body.append(dashboard)
  dashboard.hass = f.hass
  await settled()
  assert.equal(dashboard._data.summary.current_month, 350)
  let selector = dashboard.shadowRoot.getElementById('dashboard-house')
  assert.ok(selector)
  selector.value = 'b'
  selector.dispatchEvent(new f.dom.window.Event('change', { bubbles: true }))
  await settled()
  assert.equal(dashboard._data.summary.current_month, 250)
  assert.ok(f.calls.some(msg => msg.type === 'bill_tracker/list' && msg.house_id === 'b'))
  selector = dashboard.shadowRoot.getElementById('dashboard-house')
  selector.value = 'all'
  selector.dispatchEvent(new f.dom.window.Event('change', { bubbles: true }))
  await settled()
  assert.equal(dashboard._data.summary.current_month, 350)
})

test('House settings labels are localized into all six frontend languages', t => {
  const f = fixture(t)
  const settings = f.dom.window.document.createElement('billy-settings')
  f.dom.window.document.body.append(settings)
  settings._data = f.snapshot()
  for (const [language, expected] of [
    ['en', 'Houses'], ['it', 'Case'], ['es', 'Viviendas'],
    ['fr', 'Logements'], ['de', 'Häuser'], ['pt', 'Casas'],
  ]) {
    settings._hass = { language, locale: { language } }
    settings.section = 'categories'
    settings.section = 'houses'
    assert.match(settings.shadowRoot.textContent, new RegExp(expected))
  }
})

test('Bills actions reserve adequate width and recurring toolbar defines five desktop columns', t => {
  const f = fixture(t)
  const bills = f.dom.window.document.createElement('billy-bills')
  const recurring = f.dom.window.document.createElement('billy-recurring')
  const billStyles = bills._styles()
  const recurringStyles = recurring._styles()
  assert.match(billStyles, /grid-template-columns:minmax\(0,1fr\) minmax\(73px,auto\) minmax\(70px,auto\)/)
  assert.match(billStyles, /\.bill-actions button\{white-space:nowrap/)
  assert.match(billStyles, /grid-template-columns:minmax\(190px,1\.6fr\) repeat\(6,minmax\(110px,1fr\)\)/)
  assert.match(recurringStyles, /\.recurring-page\{container-type:inline-size\}/)
  assert.match(recurringStyles, /grid-template-columns:minmax\(155px,1fr\) minmax\(210px,1\.4fr\) repeat\(3,minmax\(140px,1fr\)\)/)
  assert.match(recurringStyles, /@container \(max-width:700px\)/)
})
