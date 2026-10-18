const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const frontend = path.join(__dirname, '../../custom_components/bill_tracker/frontend')

function read(filename) {
  return fs.readFileSync(path.join(frontend, filename), 'utf8')
}

test('the standalone Lovelace entrypoint registers seven widgets and hides only the legacy picker entry', (t) => {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'https://ha.example/lovelace/test',
  })
  t.after(() => dom.window.close())

  const bootstrap = read('billy-lovelace.js')
  assert.match(bootstrap, /import '\.\/billy-widgets\.js\?v=\d+\.\d+\.\d+-r\d+'/)
  assert.doesNotMatch(bootstrap, /import.*bill-tracker-card/)
  assert.doesNotMatch(bootstrap, /bill-tracker-card-impl/)

  // JSDOM does not evaluate ES module imports: execute the imported module
  // first, mirroring the browser's static module-import evaluation order.
  const extraI18n = read('billy-extra-i18n.js').replace(/^export /gm, '')
  const widgets = read('billy-widgets.js')
    .replace(/^import[^\n]*\n/gm, '')
  const entrypoint = bootstrap.replace(/^import[^\n]*\n/gm, '')
  dom.window.customCards = [
    { type: 'bill-tracker-card', name: 'Obsolete' },
    { type: 'other-integration-card', name: 'Unrelated' },
  ]
  const picker = dom.window.customCards
  dom.window.eval(extraI18n + '\n' + widgets + '\n' + entrypoint)

  for (const type of [
    'billy-summary-card',
    'billy-spending-card',
    'billy-breakdown-card',
    'billy-upcoming-card',
    'billy-recurring-card',
    'billy-balances-card',
    'billy-parser-status-card',
  ]) {
    assert.ok(dom.window.customElements.get(type), type)
    assert.equal(dom.window.customCards.filter((card) => card.type === type).length, 1)
  }
  assert.equal(dom.window.customElements.get('bill-tracker-card'), undefined)
  assert.equal(dom.window.customCards, picker)
  assert.equal(dom.window.customCards.some((card) => card.type === 'bill-tracker-card'), false)
  assert.equal(dom.window.customCards.some((card) => card.type === 'other-integration-card'), true)

  // In HA YAML-resource mode extra modules can register before the scoped
  // custom-element registry polyfill replaces the browser registry.
  const registered = new Map()
  Object.defineProperty(dom.window, 'customElements', {
    configurable: true,
    value: {
      get: (name) => registered.get(name),
      define: (name, ctor) => registered.set(name, ctor),
    },
  })
  picker.push({ type: 'bill-tracker-card', name: 'Stale registration' })
  dom.window.dispatchEvent(new dom.window.Event('load'))
  assert.equal(registered.size, 7)
  assert.equal(picker.some((card) => card.type === 'bill-tracker-card'), false)
  assert.equal(picker.filter((card) => card.type === 'billy-summary-card').length, 1)
})
