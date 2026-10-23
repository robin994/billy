const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const directory = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
const read = filename => fs.readFileSync(path.join(directory, filename), 'utf8')
  .replace(/^import '[^']+'\n/gm, '')
  .replace(/^import\s*\{[\s\S]*?\}\s*from\s*'[^']+'\s*\n/gm, '')
  .replace(/^export /gm, '')

async function fixture(t, language = 'en') {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    runScripts: 'outside-only',
    url: 'https://ha.local/billy?view=recurring',
  })
  t.after(() => dom.window.close())
  dom.window.console.info = () => {}
  dom.window.eval([read('billy-extra-i18n.js'), read('billy-panel.js')].join('\n'))
  const rule = {
    id: 'mortgage-1', name: 'My mortgage', kind: 'mortgage',
    amount: 800, interval_months: 1, start_date: '2026-02-02',
    end_date: '2027-10-01', auto_renew: true, renewal_interval_months: 12,
    payer: 'Owner', active: true, status: 'active',
    next_due_date: '2026-11-02', monthly_equivalent: 800, color: '#688ACF',
    reimbursement_status: 'none', reimbursement_occurrences: [],
  }
  const snapshot = {
    recurring_expenses: [rule],
    recurring_history: ['2026-02-02', '2026-03-02', '2026-04-02', '2026-05-02']
      .map(due_date => ({
        id: rule.id, kind: rule.kind, name: rule.name,
        amount: 800, due_date, paid: false, actual_amount: null,
        payment_date: null, already_recorded: false,
      })),
    recurring_payments: [],
    accounts: [{ id: 'account-1', name: 'Main account', opening_date: '2026-01-01' }],
    default_account_id: 'account-1',
    payers: [{ id: 'owner', name: 'Owner', enabled: true }],
    currency: 'EUR',
  }
  const calls = []
  const hass = {
    language, locale: { language }, config: { currency: 'EUR' },
    connection: { subscribeEvents: async () => () => {} },
    callWS: async request => {
      calls.push({ ...request })
      if (request.type === 'bill_tracker/list') return snapshot
      if (request.type === 'bill_tracker/recurring/payment/set') {
        const id = request.recurring_id + '@' + request.due_date
        const existing = snapshot.recurring_payments.find(item => item.id === id)
        const record = {
          id, recurring_id: request.recurring_id,
          due_date: request.due_date, payment_date: request.payment_date,
          amount: request.amount, account_id: request.already_recorded ? null : request.account_id,
          already_recorded: request.already_recorded, note: request.note,
        }
        if (existing) Object.assign(existing, record)
        else snapshot.recurring_payments.push(record)
        const installment = snapshot.recurring_history.find(row => row.due_date === request.due_date)
        Object.assign(installment, { paid: true, payment_date: record.payment_date,
          actual_amount: record.amount, account_id: record.account_id,
          payment_note: record.note, already_recorded: record.already_recorded })
        return record
      }
      if (request.type === 'bill_tracker/recurring/payment/delete') {
        snapshot.recurring_payments = snapshot.recurring_payments.filter(
          row => row.due_date !== request.due_date || row.recurring_id !== request.recurring_id)
        const installment = snapshot.recurring_history.find(row => row.due_date === request.due_date)
        Object.assign(installment, { paid: false, payment_date: null,
          actual_amount: null, account_id: null, payment_note: '', already_recorded: false })
        return { deleted: true }
      }
      throw new Error('Unexpected WebSocket command: ' + request.type)
    },
  }
  const recurring = dom.window.document.createElement('billy-recurring')
  dom.window.document.body.append(recurring)
  recurring.hass = hass
  await new Promise(resolve => setTimeout(resolve, 20))
  return { dom, recurring, snapshot, calls }
}

const settled = () => new Promise(resolve => setTimeout(resolve, 15))

test('issue #17: historical installment list is available independently of reimbursements', async t => {
  const { recurring } = await fixture(t)
  assert.ok(recurring.shadowRoot.querySelector('[data-recurring-payments="mortgage-1"]'))
  recurring.shadowRoot.querySelector('[data-recurring-payments]').click()
  const list = recurring.shadowRoot.getElementById('recurring-modal-card')
  assert.equal(list.querySelectorAll('.payment-row').length, 4)
  assert.equal(list.querySelectorAll('[data-payment-date]').length, 4)
  assert.match(list.textContent, /Not confirmed/)
  assert.match(list.textContent, /Only confirmed payments affect actual spending/)
  assert.equal(list.querySelector('[data-recurring-occurrence]'), null)
})

test('issue #17: backdated payment can be created, edited and undone', async t => {
  const { dom, recurring, calls, snapshot } = await fixture(t)
  dom.window.confirm = () => true
  recurring.shadowRoot.querySelector('[data-recurring-payments]').click()
  recurring.shadowRoot.querySelector('[data-payment-date="2026-02-02"]').click()
  let form = recurring.shadowRoot.getElementById('recurring-payment-form')
  assert.equal(form.elements.namedItem('payment_date').value, '2026-02-02')
  assert.equal(form.elements.namedItem('account_id').value, 'account-1')
  form.elements.namedItem('payment_date').value = '2026-02-05'
  form.elements.namedItem('amount').value = '812.37'
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settled()
  let payment = calls.find(call => call.type === 'bill_tracker/recurring/payment/set')
  assert.equal(payment.recurring_id, 'mortgage-1')
  assert.equal(payment.due_date, '2026-02-02')
  assert.equal(payment.payment_date, '2026-02-05')
  assert.equal(payment.amount, 812.37)
  assert.equal(payment.account_id, 'account-1')
  assert.equal(snapshot.recurring_payments.length, 1)
  assert.match(recurring.shadowRoot.getElementById('recurring-modal-card').textContent, /Paid/)

  recurring.shadowRoot.querySelector('[data-payment-date="2026-02-02"]').click()
  form = recurring.shadowRoot.getElementById('recurring-payment-form')
  assert.ok(form.querySelector('#payment-undo'), 'existing payments can be undone')
  form.elements.namedItem('amount').value = '800'
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settled()
  assert.equal(snapshot.recurring_payments[0].amount, 800)
  recurring.shadowRoot.querySelector('[data-payment-date="2026-02-02"]').click()
  recurring.shadowRoot.getElementById('payment-undo').click()
  await settled()
  assert.equal(snapshot.recurring_payments.length, 0)
  assert.equal(calls.filter(call => call.type === 'bill_tracker/recurring/payment/delete').length, 1)
  assert.match(recurring.shadowRoot.getElementById('recurring-modal-card').textContent, /Not confirmed/)
})

test('issue #17: already-recorded bill checkbox suppresses the extra account posting', async t => {
  const { dom, recurring, calls } = await fixture(t)
  recurring.shadowRoot.querySelector('[data-recurring-payments]').click()
  recurring.shadowRoot.querySelector('[data-payment-date="2026-03-02"]').click()
  const check = recurring.shadowRoot.getElementById('payment-already-recorded')
  const account = recurring.shadowRoot.getElementById('recurring-payment-account')
  assert.equal(account.disabled, false)
  check.checked = true
  check.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
  assert.equal(account.disabled, true)
  recurring.shadowRoot.getElementById('recurring-payment-form')
    .dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settled()
  const request = calls.find(call => call.type === 'bill_tracker/recurring/payment/set')
  assert.equal(request.already_recorded, true)
  assert.equal(request.account_id, '')
})

test('issue #17: installment history pagination makes years of payments accessible', async t => {
  const { recurring, snapshot } = await fixture(t)
  snapshot.recurring_history = Array.from({ length: 27 }, (_, i) => ({
    id: 'mortgage-1', kind: 'mortgage', name: 'My mortgage',
    due_date: '2024-' + String(i % 12 + 1).padStart(2, '0') + '-02',
    amount: 800, paid: false,
  }))
  recurring._openRecurringPayments('mortgage-1')
  let card = recurring.shadowRoot.getElementById('recurring-modal-card')
  assert.equal(card.querySelectorAll('.payment-row').length, 12)
  card.querySelector('#payment-next').click()
  card = recurring.shadowRoot.getElementById('recurring-modal-card')
  assert.equal(card.querySelectorAll('.payment-row').length, 12)
  card.querySelector('#payment-next').click()
  card = recurring.shadowRoot.getElementById('recurring-modal-card')
  assert.equal(card.querySelectorAll('.payment-row').length, 3)
  assert.equal(card.querySelector('#payment-next').disabled, true)
})

test('issue #17: Italian payment controls render with localized labels', async t => {
  const { recurring } = await fixture(t, 'it')
  recurring.shadowRoot.querySelector('[data-recurring-payments]').click()
  const card = recurring.shadowRoot.getElementById('recurring-modal-card')
  assert.match(card.textContent, /Storico pagamenti rate/)
  card.querySelector('[data-payment-date="2026-02-02"]').click()
  assert.match(recurring.shadowRoot.getElementById('recurring-payment-form').textContent,
    /Data effettiva di pagamento/)
})

test('issue #17: rejected payments preserve editable amounts and show the error', async t => {
  const { dom, recurring, snapshot } = await fixture(t)
  const original = recurring._hass.callWS
  recurring._hass.callWS = async request => {
    if (request.type === 'bill_tracker/recurring/payment/set') {
      throw new Error('Payment predates the account opening date')
    }
    return original(request)
  }
  recurring.shadowRoot.querySelector('[data-recurring-payments]').click()
  recurring.shadowRoot.querySelector('[data-payment-date="2026-02-02"]').click()
  const form = recurring.shadowRoot.getElementById('recurring-payment-form')
  form.elements.namedItem('amount').value = '831.24'
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settled()
  assert.equal(snapshot.recurring_payments.length, 0)
  assert.equal(recurring.shadowRoot.getElementById('recurring-payment-form'), form)
  assert.equal(form.elements.namedItem('amount').value, '831.24')
  assert.match(form.querySelector('[role="alert"]').textContent, /predates/)
})

test('issue #17: future installments have no confirm-payment action', async t => {
  const { recurring, snapshot } = await fixture(t)
  snapshot.recurring_history.push({
    id: 'mortgage-1', name: 'My mortgage', kind: 'mortgage',
    due_date: '2099-11-02', amount: 800, paid: false,
  })
  recurring._openRecurringPayments('mortgage-1')
  const modal = recurring.shadowRoot.getElementById('recurring-modal-card')
  assert.match(modal.textContent, /Upcoming/)
  assert.equal(modal.querySelectorAll('.payment-row').length, 5)
  assert.equal(modal.querySelectorAll('[data-payment-date]').length, 4)
})

test('v0.17.1: rejected recurring save leaves form open, preserves input and displays reason', async t => {
  const { dom, recurring } = await fixture(t)
  recurring._hass.callWS = async request => {
    if (request.type === 'bill_tracker/recurring/add') {
      throw new Error('Total repayable must exceed preceding installments')
    }
    return {}
  }
  recurring._openRecurring()
  const form = recurring.shadowRoot.getElementById('recurring-form')
  form.elements.namedItem('name').value = 'Family loan'
  form.elements.namedItem('kind').value = 'installment'
  form.elements.namedItem('kind').dispatchEvent(new dom.window.Event('input'))
  form.elements.namedItem('amount').value = '500'
  form.elements.namedItem('installment_count').value = '21'
  form.elements.namedItem('total_amount').value = '9999.99'
  form.dispatchEvent(new dom.window.Event('submit', { cancelable: true, bubbles: true }))
  await settled()
  assert.equal(recurring.shadowRoot.getElementById('recurring-modal').hidden, false)
  assert.equal(recurring.shadowRoot.getElementById('recurring-form'), form)
  assert.equal(form.elements.namedItem('total_amount').value, '9999.99')
  assert.match(form.querySelector('[data-recurring-save-error]').textContent, /Total repayable/)
  assert.equal(form.querySelector('[type="submit"]').disabled, false)
})

test('v0.17.1: fixed-term preview calculates the final different installment', async t => {
  const { dom, recurring, calls } = await fixture(t)
  recurring._openRecurring()
  const form = recurring.shadowRoot.getElementById('recurring-form')
  const input = (name, value) => {
    const field = form.elements.namedItem(name)
    field.value = value
    field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  }
  input('kind', 'installment')
  input('name', 'Example loan')
  input('amount', '500')
  input('installment_count', '21')
  input('total_amount', '10520.09')
  input('start_date', '2026-02-01')
  assert.match(form.querySelector('#recurring-plan-preview').textContent, /520/)
  assert.equal(form.querySelector('[name="renewal_interval_months"]').closest('[data-renewable]').hidden, true)
  assert.equal(form.querySelector('[name="end_date"]').disabled, true)
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  await settled()
  const request = calls.find(call => call.type === 'bill_tracker/recurring/add')
  assert.ok(request)
  assert.equal(request.amount, 500)
  assert.equal(request.total_amount, 10520.09)
  assert.equal(request.installment_count, 21)
  assert.equal(request.auto_renew, false)
})

test('issue #17 follow-up: selected house is included when saving the installment plan', async t => {
  const { dom, recurring, snapshot, calls } = await fixture(t)
  const selectedHouse = 'd736a68ed48f4935ac036b4ecef69b31'
  snapshot.houses = [
    { id: selectedHouse, name: 'Default home' },
    { id: 'vacation-home', name: 'Vacation home' },
  ]
  snapshot.default_house_id = selectedHouse
  const originalCall = recurring._hass.callWS
  recurring._hass.callWS = async request => {
    if (request.type === 'bill_tracker/recurring/add') {
      calls.push({ ...request })
      return { id: 'new-loan' }
    }
    return originalCall(request)
  }
  recurring._openRecurring()
  const form = recurring.shadowRoot.getElementById('recurring-form')
  assert.equal(form.elements.namedItem('house_id').value, selectedHouse)
  form.elements.namedItem('kind').value = 'installment'
  form.elements.namedItem('name').value = 'Mortgage'
  form.elements.namedItem('amount').value = '500'
  form.elements.namedItem('installment_count').value = '21'
  form.elements.namedItem('total_amount').value = '10520.09'
  form.dispatchEvent(new dom.window.Event('submit', { cancelable: true, bubbles: true }))
  await settled()
  const sent = calls.find(request => request.type === 'bill_tracker/recurring/add')
  assert.equal(sent.house_id, selectedHouse)
  assert.equal(sent.total_amount, 10520.09)
  assert.equal(recurring.shadowRoot.getElementById('recurring-modal').hidden, true)
})

test('v0.17.1: incomplete payer share does not close the recurring editor', async t => {
  const { dom, recurring } = await fixture(t)
  recurring._openRecurring()
  const form = recurring.shadowRoot.getElementById('recurring-form')
  form.elements.namedItem('name').value = 'New subscription'
  const share = form.querySelector('.recurring-split-input')
  assert.ok(share)
  share.value = '40'
  form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))
  assert.equal(recurring.shadowRoot.getElementById('recurring-modal').hidden, false)
  assert.equal(form.elements.namedItem('name').value, 'New subscription')
  assert.match(form.querySelector('[data-recurring-save-error]').textContent, /100|percent|shares|split/i)
})

test('issue #17: actual dashboard spending counts payment date and skips unconfirmed or linked bills', async t => {
  const { dom } = await fixture(t)
  const dashboard = dom.window.document.createElement('billy-dashboard')
  dashboard._chartActualPoints = () => [
    new dom.window.Date(2026, 1, 1),
    new dom.window.Date(2026, 2, 1),
  ]
  dashboard._chartItemEnabled = () => true
  dashboard._data = {
    categories: [],
    monthly: [],
    recurring_history: [
      { id: 'unpaid', name: 'Planned mortgage', kind: 'mortgage',
        due_date: '2026-02-02', amount: 800, paid: false },
      { id: 'paid', name: 'Paid mortgage', kind: 'mortgage',
        due_date: '2026-02-02', payment_date: '2026-03-04',
        amount: 800, actual_amount: 812.37, paid: true },
      { id: 'already-billed', name: 'Already paid Bill', kind: 'mortgage',
        due_date: '2026-02-02', payment_date: '2026-02-05',
        amount: 800, actual_amount: 800, paid: true, already_recorded: true },
    ],
  }
  const actual = dashboard._actualChartRows()
  assert.equal(actual.find(row => row.key === '2026-02').recurring_total, 0)
  assert.equal(actual.find(row => row.key === '2026-03').recurring_total, 812.37)
})
