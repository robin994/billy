const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const frontend = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
const read = name => fs.readFileSync(path.join(frontend, name), 'utf8').replace(/^import[^\n]*\n/gm, '').replace(/^export /gm, '')

function fixture(t) {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only', url: 'https://ha.example/lovelace',
  })
  t.after(() => dom.window.close())
  dom.window.console.info = () => {}
  dom.window.eval(read('billy-extra-i18n.js') + '\n' + read('billy-widgets.js'))
  const widget = (tag, config = {}) => {
    const card = dom.window.document.createElement(tag)
    card.setConfig(config)
    return card
  }
  return { dom, widget }
}

test('all widgets default to auto-height grid rows with backwards-compatible 6-column width', t => {
  const f = fixture(t)
  for (const tag of ['billy-summary-card', 'billy-upcoming-card',
    'billy-recurring-card', 'billy-balances-card', 'billy-parser-status-card']) {
    const card = f.widget(tag)
    assert.deepEqual(JSON.parse(JSON.stringify(card.getGridOptions())),
      { columns: 6, min_columns: 3, rows: 'auto' }, tag)
    assert.equal(card.hasAttribute('data-fixed-rows'), false)
    assert.match(card.shadowRoot.querySelector('style').textContent, /ha-card\{height:auto/)
    assert.match(card.shadowRoot.querySelector('style').textContent,
      /\.card\{padding:16px;min-width:0;container-type:inline-size\}/)
  }
})

test('upcoming can span the full Section and remains readable on narrow cards', t => {
  const f = fixture(t)
  const card = f.widget('billy-upcoming-card', { columns: 'full', limit: 6 })
  assert.deepEqual(JSON.parse(JSON.stringify(card.getGridOptions())),
    { columns: 'full', min_columns: 3, rows: 'auto' })
  assert.match(card.shadowRoot.querySelector('style').textContent, /-webkit-line-clamp:2/)
  assert.match(card.shadowRoot.querySelector('style').textContent, /@container \(max-width:330px\)/)
  card._data = {
    current_month_unpaid_bills: [{
      id: 'long-bill', category: 'Very long subscription name with detail',
      amount: 2450.50, due_date: '2026-10-29',
    }],
  }
  card._config.filter = 'unpaid_this_month'
  card._render()
  assert.match(card.shadowRoot.querySelector('.bill-name').textContent, /Very long subscription/)
  assert.ok(card.shadowRoot.querySelector('.name .kind'), 'bill kind remains visible outside the name clamp')
  card.setConfig({ columns: 12 })
  assert.equal(card.getGridOptions().columns, 12)
  card.setConfig({ columns: 8 })
  assert.equal(card.getGridOptions().columns, 8)
  card.setConfig({ columns: 'bogus' })
  assert.equal(card.getGridOptions().columns, 6)
})

test('matching fixed grid rows are opt-in for recurring expenses and reimbursements', t => {
  const f = fixture(t)
  const recurring = f.widget('billy-recurring-card', { columns: 6, rows: 3 })
  const reimbursement = f.widget('billy-balances-card', { columns: 6, rows: 3 })
  for (const card of [recurring, reimbursement]) {
    assert.equal(card.getGridOptions().rows, 3)
    assert.equal(card.hasAttribute('data-fixed-rows'), true)
    const style = card.shadowRoot.querySelector('style').textContent
    assert.match(style, /ha-card\{min-height:170px\}/)
    assert.match(style, /:host\(\[data-fixed-rows\]\) ha-card\{height:100%\}/)
  }
  recurring.setConfig({ rows: 'auto' })
  assert.equal(recurring.getGridOptions().rows, 'auto')
  assert.equal(recurring.hasAttribute('data-fixed-rows'), false)
})

test('summary KPI columns are symmetric and never clip long currency values', t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  card._data = { summary: { current_month: 3296.90, outstanding_total: 2480.42 } }
  card._render()
  const style = card.shadowRoot.querySelector('style').textContent
  assert.match(style, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/)
  assert.match(style, /overflow-wrap:anywhere/)
  assert.match(style, /@container \(max-width:390px\)/)
  assert.equal(card.shadowRoot.querySelectorAll('.hero .metric').length, 2)
  assert.ok(card.shadowRoot.querySelector('.hero').textContent.includes('3,296'))
})

test('parser card is content-height by default, not stretched to match a tall neighbor', t => {
  const f = fixture(t)
  const card = f.widget('billy-parser-status-card')
  card._parserData = { catalog: { parsers: [], counts: {} } }
  card._render()
  assert.equal(card.getGridOptions().rows, 'auto')
  assert.doesNotMatch(card.shadowRoot.querySelector('style').textContent,
    /ha-card\{height:100%;overflow:hidden/)
  assert.equal(card.shadowRoot.querySelectorAll('.stat').length, 4)
})
