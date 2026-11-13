const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const frontend = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
const script = name => fs.readFileSync(path.join(frontend, name), 'utf8')
  .replace(/^import '[^']+'\n/gm, '')
  .replace(/^import\s*\{[\s\S]*?\}\s*from\s*'[^']+'\s*\n/gm, '')
  .replace(/^export /gm, '')

function fixture(t, url = 'https://ha.example/billy') {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url })
  t.after(() => dom.window.close())
  dom.window.console.info = () => {}
  dom.window.eval([
    script('bill-tracker-i18n.js'),
    script('billy-extra-i18n.js'),
    script('billy-accounts.js'),
    script('billy-income.js'),
    script('billy-panel.js'),
  ].join('\n'))
  const panel = dom.window.document.createElement('billy-panel')
  panel._render()
  return { dom, panel }
}

test('issue #16: Accounts has a main tab and recurring expenses/income have separate subviews', t => {
  const { dom, panel } = fixture(t)
  const views = [...panel.shadowRoot.querySelectorAll('nav [data-view]')]
    .map(button => button.dataset.view)
  assert.deepEqual(views, [
    'dashboard', 'bills', 'recurring', 'income', 'accounts',
    'reimbursementArchive', 'parsers', 'settings',
  ])
  const accounts = panel.shadowRoot.getElementById('accounts-panel')
  const income = panel.shadowRoot.getElementById('income-panel')
  const recurringIncome = panel.shadowRoot.getElementById('recurring-income-panel')
  assert.equal(accounts.getAttribute('mode'), 'overview')
  assert.equal(income.getAttribute('mode'), 'entries')
  assert.equal(recurringIncome.getAttribute('mode'), 'rules')

  panel._setView('accounts')
  assert.equal(panel._view, 'accounts')
  assert.equal(dom.window.location.search, '?view=accounts')
  assert.equal(panel.shadowRoot.querySelector('[data-section="accounts"]').hidden, false)
  assert.equal(panel.shadowRoot.querySelector('[data-section="income"]').hidden, true)

  panel._setView('recurring')
  panel.shadowRoot.querySelector('[data-recurring-type="income"]').click()
  assert.equal(panel._recurringType, 'income')
  assert.equal(dom.window.location.search, '?view=recurring&tab=income')
  assert.equal(panel.shadowRoot.querySelector('[data-recurring-view="expenses"]').hidden, true)
  assert.equal(panel.shadowRoot.querySelector('[data-recurring-view="income"]').hidden, false)
  assert.equal(panel.shadowRoot.querySelector('[data-recurring-type="income"]').getAttribute('aria-selected'), 'true')
  panel.shadowRoot.querySelector('[data-recurring-type="expenses"]').click()
  assert.equal(panel._recurringType, 'expenses')
  assert.equal(dom.window.location.search, '?view=recurring')
  assert.equal(panel.shadowRoot.querySelector('[data-recurring-view="income"]').hidden, true)
})

test('issue #16: Accounts settings deep link and configure navigation remain on the correct section', t => {
  const { dom, panel } = fixture(t, 'https://ha.example/billy?view=settings&section=accounts')
  assert.equal(panel._view, 'settings')
  assert.equal(panel.shadowRoot.getElementById('settings-panel')._section, 'accounts')

  panel._setView('accounts')
  const accountPage = panel.shadowRoot.getElementById('accounts-panel')
  accountPage.data = {
    payers: [],
    accounts: [],
    internal_transfers: [],
    account_balances: { accounts: [] },
  }
  accountPage.shadowRoot.querySelector('[data-manage-accounts]').click()
  assert.equal(panel._view, 'settings')
  assert.equal(dom.window.location.search, '?view=settings&section=accounts')
  assert.equal(panel.shadowRoot.getElementById('settings-panel')._section, 'accounts')
})

test('issue #16: six languages expose account and recurring navigation labels', t => {
  const { panel } = fixture(t)
  for (const [language, labels] of [
    ['en', ['Accounts', 'Recurring expenses', 'Recurring income']],
    ['it', ['Conti', 'Spese ricorrenti', 'Entrate ricorrenti']],
    ['es', ['Cuentas', 'Gastos recurrentes', 'Ingresos recurrentes']],
    ['fr', ['Comptes', 'Dépenses récurrentes', 'Revenus récurrents']],
    ['de', ['Konten', 'Wiederkehrende Ausgaben', 'Wiederkehrende Einnahmen']],
    ['pt', ['Contas financeiras', 'Despesas recorrentes', 'Receitas recorrentes']],
  ]) {
    panel._hass = { language }
    panel._updateLabels()
    assert.equal(panel.shadowRoot.querySelector('[data-view="accounts"]').textContent, labels[0])
    assert.equal(panel.shadowRoot.querySelector('[data-recurring-type="expenses"]').textContent, labels[1])
    assert.equal(panel.shadowRoot.querySelector('[data-recurring-type="income"]').textContent, labels[2])
  }
})

test('issue #16: mounted panel loads Account overview and Settings editor using existing list API', async t => {
  const { dom, panel } = fixture(t, 'https://ha.example/billy?view=accounts')
  const snapshot = {
    currency: 'EUR', expenses: [], categories: [], recurring_expenses: [],
    incomes: [], income_rules: [], income_categories: [],
    payers: [{ id: 'p1', name: 'Owner' }],
    accounts: [{ id: 'a1', name: 'Main account', account_type: 'checking',
      payer_id: 'p1', opening_date: '2026-01-01', opening_balance: 150 }],
    default_account_id: 'a1',
    internal_transfers: [],
    account_balances: {
      accounts: [{ id: 'a1', name: 'Main account', payer_id: 'p1', account_type: 'checking',
        opening_date: '2026-01-01', opening_balance: 150, balance: 150,
        income: 0, expenses: 0, is_default: true }],
      total: 150, as_of: '2026-10-21',
    },
    summary: { current_month: 0, outstanding_total: 0 },
  }
  let reads = 0
  const hass = {
    language: 'en', locale: { language: 'en' }, config: { currency: 'EUR' },
    connection: { subscribeEvents: async () => () => {} },
    callWS: async message => {
      if (message.type === 'bill_tracker/list') { reads++; return snapshot }
      if (message.type === 'bill_tracker/parser/list') {
        return { catalog: { parsers: [], counts: {} }, sources: [] }
      }
      if (message.type === 'bill_tracker/parser/imports') return []
      if (message.type === 'bill_tracker/update/status') return {}
      return {}
    },
  }
  dom.window.document.body.append(panel)
  panel.hass = hass
  await new Promise(resolve => setTimeout(resolve, 50))
  const overview = panel.shadowRoot.getElementById('accounts-panel')
  assert.equal(overview._data?.accounts[0]?.name, 'Main account')
  assert.match(overview.shadowRoot.textContent, /Main account/)
  assert.equal(overview.shadowRoot.querySelector('[data-add-account]'), null)
  assert.ok(reads > 0)

  panel._setView('settings')
  const settings = panel.shadowRoot.getElementById('settings-panel')
  settings.section = 'accounts'
  await new Promise(resolve => setTimeout(resolve, 50))
  const editor = settings.shadowRoot.getElementById('settings-accounts')
  assert.ok(editor)
  assert.equal(editor.getAttribute('mode'), 'settings')
  assert.equal(editor._data?.accounts[0]?.name, 'Main account')
  assert.ok(editor.shadowRoot.querySelector('[data-add-account]'))
  assert.equal(editor.shadowRoot.querySelector('[data-add-transfer]'), null)
})

test('issue #22: account expense editing opens existing bill and recurring payment editors', t => {
  const { panel } = fixture(t, 'https://ha.example/billy?view=accounts')
  const snapshot = {
    currency: 'EUR',
    categories: [{ id: 'electricity', name: 'Electricity', enabled: true, interval_months: 1 }],
    payers: [{ id: 'p1', name: 'Owner', enabled: true }],
    houses: [{ id: 'h1', name: 'Home' }], default_house_id: 'h1',
    accounts: [{ id: 'a1', name: 'Current account', account_type: 'checking',
      payer_id: 'p1', opening_date: '2026-01-01', opening_balance: 500 }],
    default_account_id: 'a1', internal_transfers: [],
    account_balances: {
      accounts: [{ id: 'a1', name: 'Current account', account_type: 'checking',
        payer_id: 'p1', opening_date: '2026-01-01',
        opening_balance: 500, balance: 400, income: 0, expenses: 100 }],
      total: 400, as_of: '2026-11-06',
    },
    expenses: [{ id: 'b1', paid: true, category: 'Electricity',
      category_id: 'electricity', house_id: 'h1', amount: 45,
      paid_year: 2026, paid_month: 10, payment_date: '2026-10-10',
      account_id: 'a1', split: [] }],
    recurring_expenses: [{ id: 'r1', name: 'Monthly rental', kind: 'recurring',
      start_date: '2026-01-01', interval_months: 1, amount: 55 }],
    recurring_payments: [{ recurring_id: 'r1', due_date: '2026-09-01',
      payment_date: '2026-09-03', account_id: 'a1', amount: 55 }],
    recurring_history: [{ id: 'r1', name: 'Monthly rental',
      due_date: '2026-09-01', amount: 55, paid: true,
      payment_date: '2026-09-03', actual_amount: 55 }],
  }
  const accountView = panel.shadowRoot.getElementById('accounts-panel')
  const bills = panel.shadowRoot.getElementById('bills-panel')
  const recurring = panel.shadowRoot.getElementById('recurring-panel')
  accountView.data = snapshot
  bills._data = snapshot
  bills._render()
  recurring._data = snapshot
  recurring._render()
  accountView.shadowRoot.querySelector('[data-filter-outgoing]').click()

  const expenseButtons = accountView.shadowRoot.querySelectorAll('[data-edit-account-expense]')
  assert.equal(expenseButtons.length, 2)
  expenseButtons[0].click()
  assert.equal(panel._view, 'bills')
  assert.equal(bills.shadowRoot.getElementById('bill-modal').hidden, false)
  assert.equal(bills._editing?.id, 'b1')

  panel._setView('accounts')
  expenseButtons[1].click()
  assert.equal(panel._view, 'recurring')
  assert.equal(panel._recurringType, 'expenses')
  assert.equal(recurring.shadowRoot.getElementById('recurring-modal').hidden, false)
  assert.equal(recurring.shadowRoot.querySelector('[name="payment_date"]').value, '2026-09-03')
})
