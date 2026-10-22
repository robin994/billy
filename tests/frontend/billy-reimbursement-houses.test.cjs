const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const script = fs.readFileSync(
  path.join(__dirname, '../../custom_components/bill_tracker/frontend/billy-reimbursement-history.js'),
  'utf8',
)

function fixture(t, language = 'it') {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'https://ha.example/billy?view=reimbursementArchive',
    runScripts: 'outside-only',
  })
  t.after(() => dom.window.close())
  dom.window.eval(script)
  const houses = [
    { id: 'home-a', name: 'Casa principale' },
    { id: 'home-b', name: 'Casa vacanze' },
  ]
  const expenses = [
    { id: 'bill-a', house_id: 'home-a', amount: 100, category: 'Energy' },
    { id: 'bill-b', house_id: 'home-b', amount: 200, category: 'Water' },
    {
      id: 'bill-manual', house_id: 'home-a', amount: 40, category: 'Phone',
      payer_id: 'a', payer: 'Alex', reimbursement_manual_done: true,
      reimbursement_manual_at: '2026-10-17T10:00:00+02:00',
      split: [{ payer_id: 'b', name: 'Ben', percentage: 50 }],
    },
  ]
  const recurring_expenses = [{ id: 'rule-a', house_id: 'home-a', name: 'Mortgage' }]
  const recurring_occurrences = [{
    id: 'occ-a', recurring_id: 'rule-a', amount: 60, due_date: '2026-10-01',
    payer_id: 'a', payer: 'Alex', reimbursement_manual_done: true,
    reimbursement_manual_at: '2026-10-18T10:00:00+02:00',
    split: [{ payer_id: 'b', name: 'Ben', percentage: 50 }],
  }]
  const settlements = [
    {
      id: 'mix', from_payer_id: 'b', from_name: 'Ben',
      to_payer_id: 'a', to_name: 'Alex', amount: 90,
      created_at: '2026-10-15T10:00:00+02:00',
      items: [
        { kind: 'expense', id: 'bill-a', house_id: 'home-a', amount: 20, label: 'Electricity' },
        { kind: 'expense', id: 'bill-b', house_id: 'home-b', amount: 70, label: 'Water' },
      ],
    },
    {
      id: 'pure-b', from_payer_id: 'b', from_name: 'Ben',
      to_payer_id: 'a', to_name: 'Alex', amount: 15,
      created_at: '2025-03-15T10:00:00+01:00',
      items: [{ kind: 'expense', id: 'bill-b', amount: 15, label: 'Water (2025)' }],
    },
  ]
  const debts = [{
    from_payer_id: 'b', from_name: 'Ben', to_payer_id: 'a', to_name: 'Alex',
    amount: 30, items: [
      { kind: 'expense', id: 'bill-a', amount: 5, label: 'Electricity' },
      { kind: 'expense', id: 'bill-b', amount: 25, label: 'Water' },
    ],
  }]
  const data = {
    currency: 'EUR', houses, default_house_id: 'home-a',
    payers: [{ id: 'a', name: 'Alex' }, { id: 'b', name: 'Ben' }],
    expenses, recurring_expenses, recurring_occurrences, settlements, debts,
  }
  const calls = []
  const hass = {
    language, locale: { language }, config: { currency: 'EUR' },
    connection: { subscribeEvents: async () => () => {} },
    callWS: async message => { calls.push(message); return data },
  }
  const el = dom.window.document.createElement('billy-reimbursement-history')
  dom.window.document.body.append(el)
  el._hass = hass
  el._data = data
  el._render()
  return { dom, el, data, calls }
}

function selectHouse(dom, el, house) {
  const select = el.shadowRoot.getElementById('history-house')
  assert.ok(select, 'history must expose a house selector')
  select.value = house
  select.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
  assert.equal(el._house, house)
}

test('all houses preserves original settlements and pending amounts without duplicate entries', t => {
  const { el } = fixture(t)
  assert.equal(el._house, 'all')
  assert.equal(el._rows().length, 5)
  const rows = el._houseRows()
  const done = rows.filter(row => row.archive_status === 'done')
  const pending = rows.filter(row => row.archive_status === 'pending')
  assert.equal(done.reduce((sum, row) => sum + Number(row.amount), 0), 155)
  assert.equal(pending.reduce((sum, row) => sum + Number(row.amount), 0), 30)
  assert.equal(el.shadowRoot.querySelectorAll('.history-item').length, 5)
})

test('house selection scopes itemized completed, manual and pending reimbursements including KPIs', t => {
  const { dom, el } = fixture(t)
  selectHouse(dom, el, 'home-a')
  const rowsA = el._houseRows()
  assert.equal(rowsA.length, 4)
  assert.equal(rowsA.filter(row => row.archive_status === 'done').length, 3)
  assert.equal(rowsA.filter(row => row.archive_status === 'done')
    .reduce((sum, row) => sum + Number(row.amount), 0), 70)
  assert.equal(rowsA.filter(row => row.archive_status === 'pending')
    .reduce((sum, row) => sum + Number(row.amount), 0), 5)
  assert.equal(rowsA.find(row => row.id === 'mix').archive_items.length, 1)
  assert.equal(rowsA.find(row => row.id === 'mix').amount, 20)
  assert.ok(rowsA.some(row => row.archive_source === 'manual-recurring'))
  assert.equal(el.shadowRoot.querySelectorAll('.history-item').length, 4)
  assert.match(el.shadowRoot.querySelector('.stats').textContent, /70,00/)
  assert.match(el.shadowRoot.querySelector('.stats').textContent, /5,00/)

  selectHouse(dom, el, 'home-b')
  const rowsB = el._houseRows()
  assert.equal(rowsB.length, 3)
  assert.equal(rowsB.filter(row => row.archive_status === 'done')
    .reduce((sum, row) => sum + Number(row.amount), 0), 85)
  assert.equal(rowsB.find(row => row.id === 'mix').amount, 70)
  assert.equal(rowsB.find(row => row.id === 'mix').archive_items[0].id, 'bill-b')
  assert.equal(rowsB.filter(row => row.archive_status === 'pending')[0].amount, 25)
  assert.ok(!rowsB.some(row => row.archive_source?.startsWith('manual')))
  assert.match(el.shadowRoot.querySelector('.stats').textContent, /85,00/)

  selectHouse(dom, el, 'all')
  assert.equal(el._houseRows().length, 5)
  assert.equal(el._houseRows().find(row => row.id === 'mix').amount, 90)
  assert.equal(el._data.settlements[0].amount, 90, 'filtering must not mutate storage')
})

test('mixed-house settlement details show only the selected items and disallow partial undo', t => {
  const { dom, el, data } = fixture(t)
  selectHouse(dom, el, 'home-a')
  el._openDetails('done:mix')
  const dialog = el.shadowRoot.getElementById('history-modal')
  assert.equal(dialog.hidden, false)
  const details = dialog.querySelectorAll('.detail-row')
  assert.equal(details.length, 1)
  assert.match(details[0].textContent, /Electricity/)
  assert.doesNotMatch(details[0].textContent, /Water/)
  assert.match(dialog.textContent, /Tutte le case/)
  assert.equal(dialog.querySelector('#history-undo'), null)
  assert.equal(data.settlements[0].amount, 90)
})

test('existing status, payer and year filters continue to work together with houses', t => {
  const { dom, el } = fixture(t)
  selectHouse(dom, el, 'home-b')
  const status = el.shadowRoot.getElementById('history-status')
  status.value = 'done'
  status.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
  assert.equal(el._rows().length, 2)
  const year = el.shadowRoot.getElementById('history-year')
  year.value = '2025'
  year.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
  assert.equal(el._rows().length, 1)
  assert.equal(el._rows()[0].id, 'pure-b')
  const payer = el.shadowRoot.getElementById('history-payer')
  payer.value = 'a'
  payer.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
  assert.equal(el._rows().length, 1)
})

test('legacy mixed-house settlement with unknown amounts does not invent house totals', t => {
  const { dom, el, data } = fixture(t)
  data.settlements = [{
    id: 'legacy', amount: 105, from_payer_id: 'b', from_name: 'Ben',
    to_payer_id: 'a', to_name: 'Alex', created_at: '2026-05-10',
    items: [
      { kind: 'expense', id: 'bill-a', amount: null, legacy_amount_unknown: true },
      { kind: 'expense', id: 'bill-b', amount: null, legacy_amount_unknown: true },
    ],
  }]
  selectHouse(dom, el, 'home-a')
  const legacy = el._houseRows().find(row => row.id === 'legacy')
  assert.equal(legacy.amount, null)
  assert.equal(legacy.unknown_amount, true)
  assert.match(el.shadowRoot.querySelector('.notice.warning').textContent, /importi sconosciuti/)
  const legacyButton = el.shadowRoot.querySelector('[data-history-details="done:legacy"]')
  assert.match(legacyButton.closest('.history-item').querySelector('.history-amount').textContent, /—/)
  el._openDetails('done:legacy')
  assert.equal(el.shadowRoot.getElementById('history-undo'), null)
  selectHouse(dom, el, 'all')
  assert.equal(el._houseRows().find(row => row.id === 'legacy').amount, 105)
})

test('known house of a settlement item takes priority over later bill reassignment', t => {
  const { dom, el, data } = fixture(t)
  data.expenses[0].house_id = 'home-b'
  selectHouse(dom, el, 'home-a')
  assert.equal(el._houseRows().find(row => row.id === 'mix').amount, 20)
  selectHouse(dom, el, 'home-b')
  assert.equal(el._houseRows().find(row => row.id === 'mix').amount, 70)
})
