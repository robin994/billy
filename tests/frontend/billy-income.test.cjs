const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const incomeJs = fs.readFileSync(path.join(__dirname, '../../custom_components/bill_tracker/frontend/billy-income.js'), 'utf8')
const accountsJs = fs.readFileSync(path.join(__dirname, '../../custom_components/bill_tracker/frontend/billy-accounts.js'), 'utf8')

async function mountedIncome(language = 'en') {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'https://ha.local/billy?view=income',
    runScripts: 'outside-only',
  })
  // The test DOM does not evaluate ES module imports. Evaluate the
  // imported component first, then the Income module, as the browser does.
  dom.window.eval(accountsJs + '\n' + incomeJs.replace(/^import[^\n]*\n/gm, ''))
  const snapshot = {
    currency: 'EUR',
    accounts: [
      { id: 'a1', name: 'Joint bank', account_type: 'checking', opening_date: '2026-01-01', opening_balance: 0 },
      { id: 'a2', name: 'Cash wallet', account_type: 'cash', opening_date: '2026-01-01', opening_balance: 0 },
    ],
    default_account_id: 'a1',
    income_categories: [{ id: 'salary', name: 'Salary', color: '#116655' }],
    income_summary: { month_received: 0, month_pending: 2000, year_received: 0 },
    incomes: [{
      id: 'oct', description: 'Salary', category_id: 'salary', expected_date: '2026-10-27',
      estimated_amount: 2000, actual_amount: null, received_date: null,
      received: false, rule_id: 'salary-rule', note: '', account_id: 'a1',
    }],
    income_rules: [{ id: 'salary-rule', name: 'Salary', category_id: 'salary',
      estimated_amount: 2000, start_date: '2026-01-27', end_date: null,
      interval_months: 1, amount_mode: 'average3', active: true, note: '', account_id: 'a1',
    }],
  }
  const writes = []
  const element = dom.window.document.createElement('billy-income')
  dom.window.document.body.appendChild(element)
  element.hass = {
    language, locale: { language }, config: { currency: 'EUR' },
    connection: { async subscribeEvents() { return () => {} } },
    async callWS(msg) {
      if (msg.type === 'bill_tracker/list') return snapshot
      writes.push(msg)
      if (msg.type === 'bill_tracker/income/update') {
        snapshot.incomes[0] = { ...snapshot.incomes[0], ...msg }
      }
      if (msg.type === 'bill_tracker/income/category/update') {
        Object.assign(snapshot.income_categories.find(row => row.id === msg.category_id), msg)
      }
      return {}
    },
  }
  await new Promise((resolve) => setTimeout(resolve, 30))
  return { dom, element, snapshot, writes }
}

test('Billy Income opens the exact recurring occurrence and submits its actual salary', async (t) => {
  const { dom, element, writes } = await mountedIncome()
  t.after(() => dom.window.close())
  assert.match(element.shadowRoot.textContent, /Salary/)
  assert.match(element.shadowRoot.textContent, /Expected/)
  element.shadowRoot.querySelector('[data-edit="oct"]').click()
  const form = element.shadowRoot.querySelector('#modal form')
  assert.ok(form)
  assert.equal(form.elements.expected_date.value, '2026-10-27')
  assert.equal(form.elements.expected_date.readOnly, true)
  form.elements.actual_amount.value = '2155.31'
  form.elements.received_date.value = '2026-10-27'
  form.elements.received.checked = true
  form.elements.account_id.value = 'a2'
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await new Promise((resolve) => setTimeout(resolve, 30))
  const update = writes.find((row) => row.type === 'bill_tracker/income/update')
  assert.ok(update)
  assert.equal(update.income_id, 'oct')
  assert.equal(update.actual_amount, 2155.31)
  assert.equal(update.estimated_amount, 2000)
  assert.equal(update.received, true)
  assert.equal(update.received_date, '2026-10-27')
  assert.equal(update.expected_date, '2026-10-27')
  assert.equal(update.account_id, 'a2')
})

test('Income section displays recurring amount estimation mode and independent plan editor', async (t) => {
  const { dom, element } = await mountedIncome()
  t.after(() => dom.window.close())
  element.shadowRoot.querySelector('[data-tab="rules"]').click()
  assert.match(element.shadowRoot.textContent, /Recurring plans/)
  assert.match(element.shadowRoot.textContent, /Average of last 3/)
  element.shadowRoot.querySelector('[data-edit-rule="salary-rule"]').click()
  const form = element.shadowRoot.querySelector('#modal form')
  assert.ok(form)
  assert.equal(form.elements.amount_mode.value, 'average3')
  assert.equal(form.elements.start_date.value, '2026-01-27')
  assert.equal(form.elements.account_id.value, 'a1')
})

test('Income Accounts subtab mounts the dynamic account manager', async (t) => {
  const { dom, element } = await mountedIncome()
  t.after(() => dom.window.close())
  element.shadowRoot.querySelector('[data-tab="accounts"]').click()
  const accounts = element.shadowRoot.querySelector('billy-accounts')
  assert.ok(accounts)
  assert.match(accounts.shadowRoot.textContent, /Create your first account/)
  assert.ok(accounts._hass?.connection)
  assert.ok(accounts._data)
})

for (const [language, label] of [
  ['en', 'Salary'], ['it', 'Stipendio'], ['es', 'Sueldo'],
  ['fr', 'Salaire'], ['de', 'Gehalt'], ['pt', 'Salário'],
]) {
  test(`Built-in income categories are translated in ${language} without changing IDs`, async t => {
    const { dom, element, snapshot } = await mountedIncome(language)
    t.after(() => dom.window.close())
    assert.equal(snapshot.income_categories[0].name, 'Salary')
    assert.match(element.shadowRoot.textContent, new RegExp(label))
    element._openIncome('oct')
    const form = element.shadowRoot.querySelector('#modal form')
    assert.equal(form.elements.category_id.value, 'salary')
    assert.equal(form.elements.category_id.selectedOptions[0].textContent, label)
    element._openCategories()
    assert.match(element.shadowRoot.querySelector('.cat-list').textContent, new RegExp(label))
    element._query = label.toLowerCase()
    assert.equal(element._filtered().length, 1)
  })
}

test('A custom income category name is never overwritten by translation', async t => {
  const { dom, element, snapshot, writes } = await mountedIncome('it')
  t.after(() => dom.window.close())
  element._openCategories()
  element.shadowRoot.querySelector('[data-cat-edit="salary"]').click()
  const form = element.shadowRoot.querySelector('#modal form')
  assert.equal(form.elements.name.value, 'Stipendio')
  form.elements.color.value = '#efaa22'
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await new Promise(resolve => setTimeout(resolve, 50))
  const update = writes.find(row => row.type === 'bill_tracker/income/category/update')
  assert.equal(update.category_id, 'salary')
  assert.equal(update.name, 'Salary')
  assert.equal(snapshot.income_categories[0].name, 'Salary')

  snapshot.income_categories[0].name = 'Consulting'
  element._render()
  element._openIncome('oct')
  assert.equal(element.shadowRoot.querySelector('[name="category_id"]').selectedOptions[0].textContent, 'Consulting')
})
