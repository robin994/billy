const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const script = fs.readFileSync(
  path.join(__dirname, '../../custom_components/bill_tracker/frontend/billy-accounts.js'),
  'utf8',
)

function mount(language = 'en') {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    runScripts: 'outside-only', url: 'https://ha.local/billy?view=income',
  })
  dom.window.eval(script)
  const data = {
    currency: 'EUR', accounts: [], default_account_id: null, internal_transfers: [],
    payers: [{ id: 'owner', name: 'Owner' }, { id: 'partner', name: 'Partner' }],
    account_balances: {
      configured: false, accounts: [], as_of: '2026-10-18', total: null,
      default_account_id: null,
    },
  }
  const calls = []
  let index = 0
  const element = dom.window.document.createElement('billy-accounts')
  dom.window.document.body.append(element)
  dom.window.confirm = () => true
  function recalculate() {
    const accounts = data.accounts.map((row) => {
      const inflow = data.internal_transfers
        .filter((transfer) => transfer.to_account === row.id)
        .reduce((sum, transfer) => sum + transfer.amount, 0)
      const outflow = data.internal_transfers
        .filter((transfer) => transfer.from_account === row.id)
        .reduce((sum, transfer) => sum + transfer.amount, 0)
      const manualIncome = (row.balance_adjustments || [])
        .reduce((sum, movement) => sum + Math.max(0, movement.amount), 0)
      const manualExpenses = (row.balance_adjustments || [])
        .reduce((sum, movement) => sum + Math.max(0, -movement.amount), 0)
      return { ...row, is_default: row.id === data.default_account_id,
        income: 0, expenses: 0, transfers_in: inflow, transfers_out: outflow,
        manual_income: manualIncome, manual_expenses: manualExpenses,
        adjustments: manualIncome - manualExpenses,
        balance: row.opening_balance + inflow - outflow + manualIncome - manualExpenses }
    })
    data.account_balances = {
      configured: Boolean(accounts.length), accounts, as_of: '2026-10-18',
      default_account_id: data.default_account_id,
      total: accounts.length ? accounts.reduce((sum, row) => sum + row.balance, 0) : null,
    }
  }
  const hass = {
    language, locale: { language }, config: { currency: 'EUR' },
    async callWS(msg) {
      if (msg.type === 'bill_tracker/list') return data
      calls.push(msg)
      if (msg.type === 'bill_tracker/accounts/add') {
        const row = {
          id: `a${++index}`, name: msg.name, account_type: msg.account_type,
          opening_date: msg.opening_date, opening_balance: msg.opening_balance,
          payer_id: msg.payer_id,
        }
        data.accounts.push(row)
        if (msg.make_default || !data.default_account_id) data.default_account_id = row.id
      } else if (msg.type === 'bill_tracker/accounts/update') {
        const row = data.accounts.find((item) => item.id === msg.account_id)
        Object.assign(row, {
          name: msg.name, account_type: msg.account_type,
          opening_date: msg.opening_date, opening_balance: msg.opening_balance,
          payer_id: msg.payer_id,
        })
        if (msg.make_default) data.default_account_id = row.id
      } else if (msg.type === 'bill_tracker/accounts/delete') {
        data.accounts = data.accounts.filter((row) => row.id !== msg.account_id)
        if (data.default_account_id === msg.account_id)
          data.default_account_id = data.accounts[0]?.id || null
      } else if (msg.type === 'bill_tracker/accounts/adjust_balance') {
        const row = data.accounts.find(item => item.id === msg.account_id)
        const current = data.account_balances.accounts.find(item => item.id === msg.account_id).balance
        const amount = msg.balance - current
        if (amount) {
          row.balance_adjustments ||= []
          row.balance_adjustments.push({
            id: `m${++index}`, date: '2026-10-18', amount,
            type: amount > 0 ? 'income' : 'expense', note: msg.note,
          })
        }
      } else if (msg.type === 'bill_tracker/accounts/default') {
        data.default_account_id = msg.account_id
      } else if (msg.type === 'bill_tracker/accounts/transfer/add') {
        data.internal_transfers = [...data.internal_transfers, { ...msg, id: `t${++index}` }]
      } else if (msg.type === 'bill_tracker/accounts/transfer/update') {
        const target = data.internal_transfers.find((row) => row.id === msg.transfer_id)
        Object.assign(target, msg)
      } else if (msg.type === 'bill_tracker/accounts/transfer/delete') {
        data.internal_transfers = data.internal_transfers.filter((row) => row.id !== msg.transfer_id)
      }
      recalculate()
      return {}
    },
  }
  element.hass = hass
  element.data = data
  return { dom, element, data, calls, recalculate, hass }
}

async function submit(dom, form) {
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await new Promise((resolve) => setTimeout(resolve, 20))
}

async function createAccount(ctx, name, type = 'checking', amount = 100, makeDefault = false) {
  ctx.element.shadowRoot.querySelector('[data-add-account]').click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  form.elements.name.value = name
  form.elements.payer_id.value = 'owner'
  form.elements.account_type.value = type
  form.elements.opening_date.value = '2026-01-01'
  form.elements.opening_balance.value = String(amount)
  form.elements.make_default.checked = makeDefault
  await submit(ctx.dom, form)
  return ctx.data.accounts[ctx.data.accounts.length - 1]
}

test('Accounts require a payer and the owner can be changed', async (t) => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  const created = await createAccount(ctx, 'Personal')
  assert.equal(created.payer_id, 'owner')
  ctx.element.shadowRoot.querySelector('[data-edit-account]').click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  form.elements.payer_id.value = 'partner'
  await submit(ctx.dom, form)
  assert.equal(ctx.data.accounts[0].payer_id, 'partner')
  assert.match(ctx.element.shadowRoot.textContent, /Partner/)
})

test('New accounts require an explicit owner chosen from the available payers', t => {
  const ctx = mount('it')
  t.after(() => ctx.dom.window.close())
  ctx.element.shadowRoot.querySelector('[data-add-account]').click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  const owners = form.elements.payer_id
  assert.equal(owners.required, true)
  assert.equal(owners.value, '')
  assert.deepEqual(Array.from(owners.options).map(option => option.value), ['', 'owner', 'partner'])
  assert.match(form.textContent, /Seleziona un pagatore/)
  owners.value = 'partner'
  assert.equal(owners.value, 'partner')
})

test('No account can be created without first creating a payer', t => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  ctx.data.payers = []
  ctx.element.data = ctx.data
  assert.equal(ctx.element.shadowRoot.querySelector('[data-add-account]').disabled, true)
  assert.match(ctx.element.shadowRoot.textContent, /Create a payer/)
})

test('Dynamic accounts start empty: no bank balance is invented', (t) => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  assert.match(ctx.element.shadowRoot.textContent, /Create your first account/)
  assert.ok(!ctx.element.shadowRoot.querySelector('[data-add-transfer]'))
})

test('Account overview shows balances and transfers but moves account creation to Settings', async t => {
  const ctx = mount('it')
  t.after(() => ctx.dom.window.close())
  await createAccount(ctx, 'Current')
  await createAccount(ctx, 'Savings', 'savings')
  ctx.element.setAttribute('mode', 'overview')
  assert.equal(ctx.element.shadowRoot.querySelector('[data-add-account]'), null)
  assert.equal(ctx.element.shadowRoot.querySelector('[data-edit-account]'), null)
  assert.equal(ctx.element.shadowRoot.querySelector('[data-delete-account]'), null)
  assert.ok(ctx.element.shadowRoot.querySelector('[data-add-transfer].primary'))
  assert.equal(ctx.element.shadowRoot.querySelectorAll('[data-filter-outgoing]').length, 2)

  let navigation
  ctx.element.addEventListener('billy-navigate', event => { navigation = event.detail })
  ctx.element.shadowRoot.querySelector('[data-manage-accounts]').click()
  assert.deepEqual(JSON.parse(JSON.stringify(navigation)),
    { view: 'settings', section: 'accounts' })
})

test('Account settings manage accounts without duplicating the transfers interface', async t => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  await createAccount(ctx, 'Current')
  await createAccount(ctx, 'Savings', 'savings')
  ctx.element.setAttribute('mode', 'settings')
  assert.ok(ctx.element.shadowRoot.querySelector('[data-add-account].primary'))
  assert.equal(ctx.element.shadowRoot.querySelectorAll('[data-edit-account]').length, 2)
  assert.equal(ctx.element.shadowRoot.querySelector('[data-add-transfer]'), null)
  assert.equal(ctx.element.shadowRoot.querySelector('.history'), null)
  assert.equal(ctx.element.shadowRoot.querySelector('[data-filter-outgoing]'), null)
})

test('Account balance can be corrected without changing its opening balance', async t => {
  const ctx = mount('it')
  t.after(() => ctx.dom.window.close())
  const account = await createAccount(ctx, 'Current', 'checking', 100)
  ctx.element.shadowRoot.querySelector('[data-adjust-balance]').click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  assert.match(form.textContent, /Modifica saldo attuale/)
  form.elements.balance.value = '85.50'
  form.elements.balance.dispatchEvent(new ctx.dom.window.Event('input', { bubbles: true }))
  assert.match(form.querySelector('[data-adjustment-preview]').textContent, /Uscita manuale da registrare/)
  assert.match(form.querySelector('[data-adjustment-preview]').textContent, /14,50/)
  form.elements.note.value = 'Payment outside Billy'
  await submit(ctx.dom, form)
  const message = ctx.calls.find(item => item.type === 'bill_tracker/accounts/adjust_balance')
  assert.equal(message.account_id, account.id)
  assert.equal(message.balance, 85.5)
  assert.equal(message.note, 'Payment outside Billy')
  assert.equal(ctx.data.accounts[0].opening_balance, 100)
  assert.equal(ctx.data.account_balances.total, 85.5)
  assert.equal(ctx.data.account_balances.accounts[0].manual_expenses, 14.5)
  assert.equal(ctx.data.accounts[0].balance_adjustments[0].type, 'expense')
  assert.match(ctx.element.shadowRoot.querySelector('.manual-row').textContent, /Uscita manuale/)
})

test('Positive and negative corrections are dated account movements and filter by direction', async t => {
  const ctx = mount('en')
  t.after(() => ctx.dom.window.close())
  const bank = await createAccount(ctx, 'Main bank', 'checking', 100)
  const cash = await createAccount(ctx, 'Cash', 'cash', 50)
  async function setBalance(id, amount, note) {
    ctx.element.shadowRoot.querySelector(`[data-adjust-balance="${id}"]`).click()
    const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
    form.elements.balance.value = String(amount)
    form.elements.note.value = note
    await submit(ctx.dom, form)
  }
  await setBalance(bank.id, 80, 'Untracked purchase')
  await setBalance(bank.id, 125, 'Untracked credit')
  await setBalance(cash.id, 55, 'Wallet correction')
  assert.equal(ctx.data.account_balances.total, 180)
  assert.equal(ctx.data.account_balances.accounts[0].manual_income, 45)
  assert.equal(ctx.data.account_balances.accounts[0].manual_expenses, 20)
  assert.equal(ctx.data.accounts[0].opening_balance, 100)
  assert.deepEqual(ctx.data.accounts[0].balance_adjustments.map(row => row.type),
    ['expense', 'income'])
  ctx.data.internal_transfers = [{
    id: 't1', from_account: bank.id, to_account: cash.id,
    amount: 5, transfer_date: '2026-10-10', note: 'Normal transfer',
  }]
  ctx.recalculate()
  ctx.element.data = ctx.data
  ctx.element.setAttribute('mode', 'overview')
  assert.equal(ctx.element.shadowRoot.querySelectorAll('.manual-row').length, 3)
  assert.equal(ctx.element.shadowRoot.querySelectorAll('.transfer-row:not(.manual-row)').length, 1)
  assert.match(ctx.element.shadowRoot.textContent, /Untracked purchase/)
  assert.match(ctx.element.shadowRoot.textContent, /Untracked credit/)
  const choose = (id, value) => {
    const control = ctx.element.shadowRoot.getElementById(id)
    control.value = value
    control.dispatchEvent(new ctx.dom.window.Event('change', { bubbles: true }))
  }
  choose('transfer-account', bank.id)
  choose('transfer-direction', 'incoming')
  assert.equal(ctx.element.shadowRoot.querySelectorAll('.manual-row').length, 1)
  assert.match(ctx.element.shadowRoot.querySelector('.manual-row').textContent, /Manual income/)
  choose('transfer-direction', 'outgoing')
  assert.equal(ctx.element.shadowRoot.querySelectorAll('.manual-row').length, 1)
  assert.equal(ctx.element.shadowRoot.querySelectorAll('.transfer-row:not(.manual-row)').length, 1)
  assert.match(ctx.element.shadowRoot.querySelector('.manual-row').textContent, /Manual expense/)
  choose('transfer-account', cash.id)
  choose('transfer-direction', 'incoming')
  assert.match(ctx.element.shadowRoot.querySelector('.manual-row').textContent, /Wallet correction/)
  assert.equal(ctx.element.shadowRoot.querySelectorAll('.manual-row').length, 1)
})

test('Transfer history filters by source, destination, or both without mutating records', async t => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  const a = await createAccount(ctx, 'Joint')
  const b = await createAccount(ctx, 'Savings', 'savings')
  const c = await createAccount(ctx, 'Cash', 'cash')
  const records = [
    { id: 't1', from_account: a.id, to_account: b.id, amount: 50, transfer_date: '2026-10-01' },
    { id: 't2', from_account: b.id, to_account: a.id, amount: 25, transfer_date: '2026-10-02' },
    { id: 't3', from_account: a.id, to_account: c.id, amount: 10, transfer_date: '2026-10-03' },
  ]
  ctx.data.internal_transfers = records
  ctx.element.data = ctx.data
  ctx.element.setAttribute('mode', 'overview')
  const count = () => ctx.element.shadowRoot.querySelectorAll('.transfer-row').length
  assert.equal(count(), 3)
  assert.equal(ctx.element.shadowRoot.getElementById('transfer-direction').disabled, true)

  const accountCard = ctx.element.shadowRoot.querySelector('[data-filter-outgoing]')
  accountCard.dispatchEvent(new ctx.dom.window.KeyboardEvent('keydown', {
    key: 'Enter', bubbles: true, cancelable: true,
  }))
  assert.equal(ctx.element.shadowRoot.getElementById('transfer-account').value, a.id)
  assert.equal(ctx.element.shadowRoot.getElementById('transfer-direction').value, 'outgoing')
  assert.equal(count(), 2)

  const select = (id, value) => {
    const control = ctx.element.shadowRoot.getElementById(id)
    control.value = value
    control.dispatchEvent(new ctx.dom.window.Event('change', { bubbles: true }))
  }
  select('transfer-direction', 'incoming')
  assert.equal(count(), 1)
  assert.match(ctx.element.shadowRoot.querySelector('.transfer-row').textContent, /Savings → Joint/)
  select('transfer-direction', 'all')
  assert.equal(count(), 3)
  select('transfer-account', c.id)
  assert.equal(count(), 1)
  select('transfer-direction', 'outgoing')
  assert.equal(count(), 0)
  assert.match(ctx.element.shadowRoot.querySelector('.history').textContent, /No movements match/)
  select('transfer-account', 'all')
  assert.equal(count(), 3)
  assert.equal(ctx.element.shadowRoot.getElementById('transfer-direction').value, 'all')
  assert.equal(ctx.element.shadowRoot.getElementById('transfer-direction').disabled, true)
  assert.deepEqual(ctx.data.internal_transfers, records)
})

test('Any number of named accounts and custom types are available in the UI', async (t) => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  const bank = await createAccount(ctx, 'Household bank', 'checking', 1000)
  await createAccount(ctx, 'Cash drawer', 'cash', 200)
  await createAccount(ctx, 'Vacation wallet', 'prepaid', 350)
  const last = await createAccount(ctx, 'Bond portfolio', 'investment', 4000)
  assert.equal(ctx.data.accounts.length, 4)
  assert.ok(last.id !== bank.id)
  assert.match(ctx.element.shadowRoot.textContent, /Bond portfolio/)
  assert.match(ctx.element.shadowRoot.textContent, /Investments/)
  assert.match(ctx.element.shadowRoot.textContent, /€5,550.00/)
  assert.equal(ctx.element.shadowRoot.querySelectorAll('[data-edit-account]').length, 4)

  ctx.element.shadowRoot.querySelector(`[data-edit-account="${last.id}"]`).click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  form.elements.name.value = 'Long-term portfolio'
  form.elements.account_type.value = 'custom-portfolio'
  await submit(ctx.dom, form)
  assert.match(ctx.element.shadowRoot.textContent, /Long-term portfolio/)
  assert.match(ctx.element.shadowRoot.textContent, /custom-portfolio/)
})

test('Transfers support two independently selected accounts among N', async (t) => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  const a = await createAccount(ctx, 'Current', 'checking', 1000)
  const b = await createAccount(ctx, 'Cash', 'cash', 100)
  const c = await createAccount(ctx, 'Other card', 'prepaid', 400)
  ctx.element.shadowRoot.querySelector('[data-add-transfer]').click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  form.elements.from_account.value = c.id
  form.elements.to_account.value = b.id
  form.elements.amount.value = '31.25'
  form.elements.transfer_date.value = '2026-01-21'
  await submit(ctx.dom, form)
  const write = ctx.calls.find((message) => message.type === 'bill_tracker/accounts/transfer/add')
  assert.ok(write)
  assert.equal(write.from_account, c.id)
  assert.equal(write.to_account, b.id)
  assert.equal(write.amount, 31.25)
  assert.match(ctx.element.shadowRoot.textContent, /Other card → Cash/)
  assert.equal(ctx.data.account_balances.total, 1500)

  const transferId = ctx.data.internal_transfers[0].id
  ctx.element.shadowRoot.querySelector(`[data-edit-transfer="${transferId}"]`).click()
  const edit = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  edit.elements.from_account.value = a.id
  edit.elements.to_account.value = c.id
  edit.elements.amount.value = '10.01'
  await submit(ctx.dom, edit)
  assert.equal(ctx.data.internal_transfers[0].from_account, a.id)
  assert.equal(ctx.data.internal_transfers[0].to_account, c.id)
  assert.equal(ctx.data.account_balances.total, 1500)

  ctx.element.shadowRoot.querySelector(`[data-delete-transfer="${transferId}"]`).click()
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.equal(ctx.data.internal_transfers.length, 0)
  assert.equal(ctx.data.account_balances.total, 1500)
})

test('A default account is selected without restricting which types exist', async (t) => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  const a = await createAccount(ctx, 'Joint')
  const b = await createAccount(ctx, 'Travel prepaid', 'prepaid')
  assert.equal(ctx.data.default_account_id, a.id)
  ctx.element.shadowRoot.querySelector(`[data-default-account="${b.id}"]`).click()
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.equal(ctx.data.default_account_id, b.id)
  assert.match(ctx.element.shadowRoot.textContent, /Travel prepaid/)
})

test('A failed account edit preserves form fields and does not lose input', async (t) => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  await createAccount(ctx, 'Old name')
  ctx.hass.callWS = async () => { throw new Error('Validation failed') }
  ctx.element.shadowRoot.querySelector('[data-edit-account]').click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  form.elements.name.value = 'New name not saved'
  await submit(ctx.dom, form)
  assert.ok(form.isConnected)
  assert.equal(form.elements.name.value, 'New name not saved')
  assert.match(form.textContent, /Validation failed/)
})

test('Transfer writes are not retried if the later snapshot fails', async (t) => {
  const ctx = mount()
  t.after(() => ctx.dom.window.close())
  await createAccount(ctx, 'A')
  await createAccount(ctx, 'B')
  const saved = ctx.hass.callWS
  ctx.hass.callWS = (message) => message.type === 'bill_tracker/list'
    ? Promise.reject(new Error('Refresh unavailable')) : saved(message)
  ctx.element.shadowRoot.querySelector('[data-add-transfer]').click()
  const form = ctx.element.shadowRoot.querySelector('#accounts-modal form')
  form.elements.amount.value = '25'
  form.elements.transfer_date.value = '2026-02-01'
  await submit(ctx.dom, form)
  assert.equal(ctx.calls.filter((m) => m.type === 'bill_tracker/accounts/transfer/add').length, 1)
  assert.match(ctx.element.shadowRoot.textContent, /Refresh unavailable/)
})

test('Italian account management is localized', (t) => {
  const ctx = mount('it')
  t.after(() => ctx.dom.window.close())
  assert.match(ctx.element.shadowRoot.textContent, /Gestisci conti e giroconti/)
  assert.match(ctx.element.shadowRoot.textContent, /Crea il primo conto/)
})
