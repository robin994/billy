const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const bootstrapPath = path.join(
  __dirname,
  '../../custom_components/bill_tracker/frontend/bill-tracker-card.js',
)

function flush(window) {
  return new Promise((resolve) => window.setTimeout(resolve, 0))
}

test('a pre-upgrade hass property reaches the Lovelace card and editor', async (t) => {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'https://ha.example/lovelace/test',
  })
  t.after(() => dom.window.close())
  const { document, customElements, HTMLElement } = dom.window
  const hass = { language: 'it' }

  // Home Assistant can assign hass to unresolved custom elements while
  // their JavaScript module is still loading.
  const card = document.createElement('bill-tracker-card')
  card.hass = hass
  document.body.append(card)
  const editor = document.createElement('bill-tracker-card-editor')
  editor.hass = hass
  document.body.append(editor)

  class FakeCard extends HTMLElement {
    set hass(value) { this.receivedHass = value }
    setConfig(config) { this.receivedConfig = config }
  }
  class FakeEditor extends FakeCard {}
  customElements.define('bill-tracker-card-impl', FakeCard)
  customElements.define('bill-tracker-card-editor-impl', FakeEditor)

  // Replace the legacy implementation import with a resolved promise, keeping
  // the real host registration and lifecycle code under test.
  const script = fs.readFileSync(bootstrapPath, 'utf8')
    .replace('import(BILLY_IMPL_URL)', 'Promise.resolve()')
  dom.window.eval(script)
  await flush(dom.window)

  assert.equal(card._hass, hass)
  assert.equal(card._inner?.receivedHass, hass)
  assert.equal(editor._hass, hass)
  assert.equal(editor._inner?.receivedHass, hass)
  assert.equal(dom.window.customCards?.some((item) => item.type === 'bill-tracker-card') ?? false, false)
})

test('the deprecated card loads its implementation only when used', async (t) => {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'https://ha.example/lovelace/test',
  })
  t.after(() => dom.window.close())
  const { document, customElements, HTMLElement } = dom.window
  let imports = 0
  dom.window.__loadLegacyImplementation = () => {
    imports += 1
    return Promise.resolve()
  }
  dom.window.console.warn = () => {}

  const script = fs.readFileSync(bootstrapPath, 'utf8')
    .replace('import(BILLY_IMPL_URL)', 'window.__loadLegacyImplementation()')
  dom.window.eval(script)
  assert.equal(imports, 0)
  assert.equal(customElements.get('bill-tracker-card-impl'), undefined)
  assert.ok(customElements.get('bill-tracker-card'))
  assert.equal(dom.window.customCards?.some((card) => card.type === 'bill-tracker-card') ?? false, false)

  class FakeCard extends HTMLElement {
    setConfig(config) { this.receivedConfig = config }
    set hass(value) { this.receivedHass = value }
  }
  customElements.define('bill-tracker-card-impl', FakeCard)
  const card = document.createElement('bill-tracker-card')
  document.body.append(card)
  card.setConfig({ title: 'Previous dashboard' })
  await flush(dom.window)

  assert.equal(imports, 1)
  assert.equal(card._inner?.receivedConfig?.title, 'Previous dashboard')
})

test('the legacy custom element registrations recover after the HA registry changes', (t) => {
  const dom = new JSDOM('<!doctype html><body></body>', {
    runScripts: 'outside-only',
    url: 'https://ha.example/lovelace/test',
  })
  t.after(() => dom.window.close())
  const script = fs.readFileSync(bootstrapPath, 'utf8')
    .replace('import(BILLY_IMPL_URL)', 'Promise.resolve()')
  dom.window.eval(script)

  const registered = new Map()
  Object.defineProperty(dom.window, 'customElements', {
    configurable: true,
    value: {
      get: (name) => registered.get(name),
      define: (name, ctor) => registered.set(name, ctor),
    },
  })
  dom.window.dispatchEvent(new dom.window.Event('load'))
  assert.ok(registered.get('bill-tracker-card'))
  assert.ok(registered.get('bill-tracker-card-editor'))
})
