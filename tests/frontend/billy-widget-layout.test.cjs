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

const settled = () => new Promise(resolve => setImmediate(resolve))
const response = currentMonth => ({
  currency: 'EUR',
  summary: {
    current_month: currentMonth,
    outstanding_total: 35,
    next_month_estimate: 90,
    year_total: 500,
    recurring_monthly_equivalent: 70,
    reimbursement_total: 15,
  },
})

test('Summary does not replace its loading shell on the initial hass assignment', async t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  f.dom.window.document.body.append(card)
  const shell = card.shadowRoot.querySelector('ha-card')
  assert.ok(card.shadowRoot.querySelector('.loading'))

  let finishInitialLoad
  card.hass = {
    connection: { subscribeEvents: async () => () => {} },
    callWS: () => new Promise(resolve => { finishInitialLoad = resolve }),
  }
  assert.equal(card.shadowRoot.querySelector('ha-card'), shell)
  finishInitialLoad(response(100))
  await settled()
  assert.notEqual(card.shadowRoot.querySelector('ha-card'), shell)
  assert.match(card.shadowRoot.querySelector('.hero .value').textContent, /100/)
})

test('iOS dashboard scroll: unrelated hass state updates preserve Summary DOM and position', async t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  f.dom.window.document.body.append(card)
  let reads = 0
  let subscribeCalls = 0
  const connection = {
    subscribeEvents: async () => {
      subscribeCalls++
      return () => {}
    },
  }
  const callWS = async () => {
    reads++
    return response(123)
  }
  card.hass = { connection, callWS, locale: { language: 'en' }, config: { currency: 'EUR' } }
  await settled()

  const root = card.shadowRoot.querySelector('ha-card')
  const amount = card.shadowRoot.querySelector('.hero .value')
  const dashboard = f.dom.window.document.createElement('section')
  dashboard.style.height = '400px'
  dashboard.style.overflowY = 'auto'
  dashboard.append(card)
  dashboard.scrollTop = 120
  const startPosition = dashboard.scrollTop
  const observerChanges = []
  const observer = new f.dom.window.MutationObserver(changes => observerChanges.push(...changes))
  observer.observe(card.shadowRoot, { subtree: true, childList: true, characterData: true })

  for (let i = 0; i < 120; i++) {
    card.hass = {
      connection, callWS, locale: { language: 'en' }, config: { currency: 'EUR' },
      states: { 'sensor.unrelated': { state: String(i) } },
    }
  }
  await settled()
  observer.disconnect()
  assert.equal(card.shadowRoot.querySelector('ha-card'), root, 'the HA card must not be remounted')
  assert.equal(card.shadowRoot.querySelector('.hero .value'), amount, 'the KPI nodes must remain stable')
  assert.equal(dashboard.scrollTop, startPosition, 'the dashboard must keep its scroll position')
  assert.equal(observerChanges.length, 0, 'unrelated state changes must not mutate the card')
  assert.equal(reads, 1, 'only the initial financial data load is needed')
  assert.equal(subscribeCalls, 1, 'only one event subscription is registered')
})

test('unrelated Home Assistant state changes do not remount any Lovelace widget', async t => {
  const f = fixture(t)
  for (const tag of [
    'billy-spending-card', 'billy-breakdown-card', 'billy-upcoming-card',
    'billy-recurring-card', 'billy-balances-card', 'billy-parser-status-card',
  ]) {
    const card = f.widget(tag)
    f.dom.window.document.body.append(card)
    let reads = 0
    const connection = { subscribeEvents: async () => () => {} }
    const callWS = async message => {
      reads++
      return message.type === 'bill_tracker/parser/list'
        ? { catalog: { parsers: [], counts: {} } }
        : response(100)
    }
    card.hass = { connection, callWS, locale: { language: 'en' } }
    await settled()
    const shell = card.shadowRoot.querySelector('ha-card')
    for (let i = 0; i < 15; i++) {
      card.hass = { connection, callWS, locale: { language: 'en' }, states: { abc: { state: i } } }
    }
    assert.equal(card.shadowRoot.querySelector('ha-card'), shell, tag)
    assert.equal(reads, tag === 'billy-parser-status-card' ? 2 : 1, tag)
    card.remove()
  }
})

test('Summary refreshes on Billy events without remounting during the request', async t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  f.dom.window.document.body.append(card)
  let onUpdate
  let reads = 0
  let finishRefresh
  const connection = {
    subscribeEvents: async (handler, name) => {
      assert.equal(name, 'bill_tracker_updated')
      onUpdate = handler
      return () => {}
    },
  }
  card.hass = {
    connection, locale: { language: 'en' }, config: { currency: 'EUR' },
    callWS: async () => {
      reads++
      if (reads === 1) return response(100)
      return new Promise(resolve => { finishRefresh = resolve })
    },
  }
  await settled()
  assert.equal(typeof onUpdate, 'function')
  const mounted = card.shadowRoot.querySelector('ha-card')
  onUpdate()
  assert.equal(card.shadowRoot.querySelector('ha-card'), mounted, 'a pending refresh must not remount the card')
  finishRefresh(response(250))
  await settled()
  assert.equal(reads, 2)
  assert.match(card.shadowRoot.querySelector('.hero .value').textContent, /250/)

  const afterUpdate = card.shadowRoot.querySelector('ha-card')
  card.hass = {
    connection, locale: { language: 'it' }, config: { currency: 'EUR' },
    callWS: () => { throw new Error('language change must not refetch data') },
  }
  assert.notEqual(card.shadowRoot.querySelector('ha-card'), afterUpdate, 'language changes may update the UI')
  assert.match(card.shadowRoot.textContent, /Questo mese/)
  assert.equal(reads, 2)
})

test('refresh events received during loading are coalesced into one follow-up fetch', async t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  f.dom.window.document.body.append(card)
  let onUpdate
  let resolveFirst
  let reads = 0
  const connection = {
    subscribeEvents: async handler => {
      onUpdate = handler
      return () => {}
    },
  }
  card.hass = {
    connection,
    callWS: () => {
      reads++
      return reads === 1
        ? new Promise(resolve => { resolveFirst = resolve })
        : Promise.resolve(response(200))
    },
  }
  await settled()
  onUpdate()
  onUpdate()
  resolveFirst(response(100))
  await settled()
  assert.equal(reads, 2, 'multiple events during a request require only one extra request')
  assert.match(card.shadowRoot.querySelector('.hero .value').textContent, /200/)
})

test('switching Home Assistant connections discards responses from the previous connection', async t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  f.dom.window.document.body.append(card)
  let resolveOldRequest
  const oldConnection = { subscribeEvents: async () => () => {} }
  const newConnection = { subscribeEvents: async () => () => {} }
  card.hass = {
    connection: oldConnection,
    callWS: () => new Promise(resolve => { resolveOldRequest = resolve }),
  }
  card.hass = { connection: newConnection, callWS: async () => response(300) }
  resolveOldRequest(response(100))
  await settled()
  assert.match(card.shadowRoot.querySelector('.hero .value').textContent, /300/)
  assert.doesNotMatch(card.shadowRoot.querySelector('.hero .value').textContent, /100/)
})

test('widget subscriptions are cleaned up and renewed after dashboard reattachment', async t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  let subscriptions = 0
  let removals = 0
  let reads = 0
  const connection = {
    subscribeEvents: async () => {
      subscriptions++
      return () => { removals++ }
    },
  }
  card.hass = { connection, callWS: async () => { reads++; return response(reads) } }
  f.dom.window.document.body.append(card)
  await settled()
  assert.equal(subscriptions, 1)
  card.remove()
  assert.equal(removals, 1)

  f.dom.window.document.body.append(card)
  await settled()
  assert.equal(subscriptions, 2)
  assert.equal(reads, 2, 'restoring a dashboard card refreshes data missed while hidden')
  card.remove()
  assert.equal(removals, 2)
})

test('late subscription responses cannot leak handlers after a card is detached', async t => {
  const f = fixture(t)
  const card = f.widget('billy-summary-card')
  let resolveSubscription
  let unsubscribeCalls = 0
  card.hass = {
    connection: {
      subscribeEvents: () => new Promise(resolve => { resolveSubscription = resolve }),
    },
    callWS: async () => response(100),
  }
  f.dom.window.document.body.append(card)
  card.remove()
  resolveSubscription(() => { unsubscribeCalls++ })
  await settled()
  assert.equal(unsubscribeCalls, 1)
})

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
  card._data = {}
  card._parserData = { catalog: { parsers: [], counts: {} } }
  card._render()
  assert.equal(card.getGridOptions().rows, 'auto')
  assert.doesNotMatch(card.shadowRoot.querySelector('style').textContent,
    /ha-card\{height:100%;overflow:hidden/)
  assert.equal(card.shadowRoot.querySelectorAll('.stat').length, 4)
})
