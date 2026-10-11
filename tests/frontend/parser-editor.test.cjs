const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const { JSDOM } = require('jsdom')

const frontend = path.join(__dirname, '../../custom_components/bill_tracker/frontend')
const translations = fs.readFileSync(path.join(frontend, 'billy-extra-i18n.js'), 'utf8')
  .replace(/^export /gm, '')
const source = fs.readFileSync(path.join(frontend, 'billy-parser-manager.js'), 'utf8')
  .replace(/^import\s*\{[\s\S]*?\}\s*from\s*'[^']+'\s*/, '')
const original = 'schema: 1\nid: gr.protergia.electricity\nversion: 1\n'
const row = { id: 'gr.protergia.electricity', category_id: 'electricity', enabled: true }
const draft = {
  'custom-yaml': original + '# unsaved change <>&"\n',
  'custom-category': 'electricity',
  'custom-enabled': false,
  'custom-auto': true,
  'custom-test-sender': 'billing@example.com',
  'custom-test-subject': 'Invoice <October> & "utilities"',
  'custom-test-email': 'Amount: 42.00 EUR\n<invoice> & details',
}

function fixture(t, handler = () => undefined) {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    runScripts: 'outside-only', url: 'https://ha.example/billy?view=parsers',
  })
  t.after(() => dom.window.close())
  dom.window.TextDecoder = TextDecoder
  dom.window.console.info = () => {}
  dom.window.eval(translations + '\n' + source)
  const panel = dom.window.document.createElement('billy-parser-manager')
  const data = { catalog: { parsers: [] }, installed: [] }
  const bills = {
    categories: [{ id: 'internet', name: 'Internet' }, { id: 'electricity', name: 'Electricity' }],
  }
  const calls = []
  const hass = {
    language: 'en', connection: {}, callWS: async msg => {
      calls.push(msg)
      const result = handler(msg)
      if (result !== undefined) return result
      switch (msg.type) {
        case 'bill_tracker/parser/custom/export':
          return { content_base64: Buffer.from(original).toString('base64') }
        case 'bill_tracker/parser/custom/save': return { id: row.id }
        case 'bill_tracker/parser/list': return data
        case 'bill_tracker/list': return bills
        case 'bill_tracker/parser/test':
          return { matched: false, score: 0, threshold: 60, data: {} }
        default: throw new Error('Unexpected request: ' + msg.type)
      }
    },
  }
  panel._data = data
  panel._billData = bills
  panel.hass = hass
  dom.window.document.body.append(panel)
  const field = id => panel.shadowRoot.getElementById(id)
  const edit = (id, value) => {
    const element = field(id)
    if (typeof value === 'boolean') element.checked = value
    else element.value = value
    element.dispatchEvent(new dom.window.Event(
      element.tagName === 'SELECT' || element.type === 'checkbox' ? 'change' : 'input',
      { bubbles: true },
    ))
  }
  const fill = () => Object.entries(draft).forEach(([id, value]) => edit(id, value))
  const assertDraft = () => Object.entries(draft).forEach(([id, value]) => {
    assert.equal(typeof value === 'boolean' ? field(id).checked : field(id).value, value, id)
  })
  return { panel, hass, calls, field, edit, fill, assertDraft }
}

test('unrelated HA state updates preserve a new editor, focus, and selection', async t => {
  const f = fixture(t)
  await f.panel._openCustomEditor()
  f.fill()
  const yaml = f.field('custom-yaml')
  yaml.focus()
  yaml.setSelectionRange(5, 12, 'forward')
  yaml.scrollTop = 27
  for (let i = 0; i < 10; i++) {
    f.panel.hass = { ...f.hass, states: { 'sensor.unrelated': { state: String(i) } } }
    f.assertDraft()
    assert.equal(f.field('custom-yaml'), yaml)
    assert.equal(f.panel.shadowRoot.activeElement, yaml)
    assert.equal(yaml.selectionStart, 5)
    assert.equal(yaml.selectionEnd, 12)
    assert.equal(yaml.scrollTop, 27)
  }
  assert.equal(f.calls.length, 0)
})

test('editing an existing parser keeps its draft and sends the original ID', async t => {
  const f = fixture(t)
  await f.panel._openCustomEditor(row)
  f.fill()
  f.panel.hass = { ...f.hass, states: {} }
  f.assertDraft()
  await f.panel._saveCustomEditor()
  const saved = f.calls.find(msg => msg.type === 'bill_tracker/parser/custom/save')
  assert.equal(saved.expected_parser_id, row.id)
  assert.equal(saved.content, draft['custom-yaml'])
  assert.equal(saved.category_id, 'electricity')
  assert.equal(saved.enabled, false)
  assert.equal(saved.auto_import, true)
  assert.equal(f.panel._customEditor, null)
})

test('creating a parser omits expected_parser_id', async t => {
  const f = fixture(t)
  await f.panel._openCustomEditor()
  f.fill()
  await f.panel._saveCustomEditor()
  const saved = f.calls.find(msg => msg.type === 'bill_tracker/parser/custom/save')
  assert.equal(saved.content, draft['custom-yaml'])
  assert.equal('expected_parser_id' in saved, false)
})

test('a necessary rerender preserves the draft, focus, selection, and scroll', async t => {
  const f = fixture(t)
  await f.panel._openCustomEditor()
  f.fill()
  const yaml = f.field('custom-yaml')
  yaml.focus()
  yaml.setSelectionRange(5, 12, 'backward')
  yaml.scrollTop = 27
  f.panel.shadowRoot.querySelector('.custom-editor-modal').scrollTop = 45
  f.panel._render()
  f.assertDraft()
  const restored = f.field('custom-yaml')
  assert.equal(f.panel.shadowRoot.activeElement, restored)
  assert.equal(restored.selectionStart, 5)
  assert.equal(restored.selectionEnd, 12)
  assert.equal(restored.selectionDirection, 'backward')
  assert.equal(restored.scrollTop, 27)
  assert.equal(f.panel.shadowRoot.querySelector('.custom-editor-modal').scrollTop, 45)
})

for (const failed of [false, true]) {
  test(`validation ${failed ? 'failure' : 'success'} preserves all test fields`, async t => {
    const f = fixture(t, msg => {
      if (failed && msg.type === 'bill_tracker/parser/test') throw new Error('Invalid YAML')
    })
    await f.panel._openCustomEditor()
    f.fill()
    await f.panel._testCustomEditor()
    f.assertDraft()
    const sent = f.calls.find(msg => msg.type === 'bill_tracker/parser/test')
    assert.equal(sent.sender, draft['custom-test-sender'])
    assert.equal(sent.subject, draft['custom-test-subject'])
    assert.equal(sent.email_text, draft['custom-test-email'])
    assert.equal(f.panel._customEditor.result.ok, !failed)
    assert.equal(f.panel._customEditor.testing, false)
  })
}

test('a save error keeps the complete draft available for correction', async t => {
  const f = fixture(t, msg => {
    if (msg.type === 'bill_tracker/parser/custom/save') throw new Error('Invalid YAML')
  })
  await f.panel._openCustomEditor(row)
  f.fill()
  await f.panel._saveCustomEditor()
  f.assertDraft()
  assert.match(f.panel._customEditor.error, /Invalid YAML/)
  assert.equal(f.panel._customEditor.originalId, row.id)
})

test('a language change preserves the draft while updating labels', async t => {
  const f = fixture(t)
  await f.panel._openCustomEditor()
  f.fill()
  f.panel.hass = { ...f.hass, language: 'it' }
  f.assertDraft()
  assert.equal(f.field('custom-editor-save').textContent, f.panel._t('saveCustom'))
  assert.notEqual(f.field('custom-editor-save').textContent, 'Save custom parser')
})

test('reconnecting reloads data and preserves the open editor', async t => {
  const f = fixture(t)
  await f.panel._openCustomEditor()
  f.fill()
  f.panel.hass = { ...f.hass, connection: {} }
  await new Promise(resolve => setImmediate(resolve))
  f.assertDraft()
  assert.equal(f.calls.filter(msg => msg.type === 'bill_tracker/parser/list').length, 1)
})

test('an old export response cannot overwrite a newly opened editor', async t => {
  let complete
  const response = new Promise(resolve => { complete = resolve })
  const f = fixture(t, msg => msg.type === 'bill_tracker/parser/custom/export' ? response : undefined)
  const pending = f.panel._openCustomEditor(row)
  f.panel._closeCustomEditor()
  await f.panel._openCustomEditor()
  f.fill()
  complete({ content_base64: Buffer.from(original).toString('base64') })
  await pending
  f.assertDraft()
  assert.equal(f.panel._customEditor.originalId, null)
})

test('closing an editor before export completes does not throw', async t => {
  let complete
  const response = new Promise(resolve => { complete = resolve })
  const f = fixture(t, msg => msg.type === 'bill_tracker/parser/custom/export' ? response : undefined)
  const pending = f.panel._openCustomEditor(row)
  f.panel._closeCustomEditor()
  complete({ content_base64: Buffer.from(original).toString('base64') })
  await pending
  assert.equal(f.panel._customEditor, null)
})

test('a pending validation preserves edits made while waiting for the result', async t => {
  let complete
  const response = new Promise(resolve => { complete = resolve })
  const f = fixture(t, msg => msg.type === 'bill_tracker/parser/test' ? response : undefined)
  await f.panel._openCustomEditor()
  f.fill()
  const pending = f.panel._testCustomEditor()
  assert.equal(f.field('custom-editor-test').disabled, true)
  await f.panel._testCustomEditor()
  assert.equal(f.calls.filter(msg => msg.type === 'bill_tracker/parser/test').length, 1)
  f.edit('custom-yaml', original + '# newer draft\n')
  f.edit('custom-test-subject', 'Updated subject')
  f.panel.hass = { ...f.hass, states: {} }
  complete({ matched: false, score: 0, threshold: 60, data: {} })
  await pending
  assert.equal(f.field('custom-yaml').value, original + '# newer draft\n')
  assert.equal(f.field('custom-test-subject').value, 'Updated subject')
  assert.equal(f.field('custom-editor-test').disabled, false)
})

test('a completed validation cannot affect a different editor', async t => {
  let complete
  const response = new Promise(resolve => { complete = resolve })
  const f = fixture(t, msg => msg.type === 'bill_tracker/parser/test' ? response : undefined)
  await f.panel._openCustomEditor()
  f.fill()
  const pending = f.panel._testCustomEditor()
  f.panel._closeCustomEditor()
  await f.panel._openCustomEditor()
  f.fill()
  const yaml = f.field('custom-yaml')
  complete({ matched: true, score: 60, threshold: 60, data: {} })
  await pending
  f.assertDraft()
  assert.equal(f.field('custom-yaml'), yaml)
  assert.equal(f.panel._customEditor.result, null)
})

test('a pending save cannot close a newly opened editor', async t => {
  let complete
  const response = new Promise(resolve => { complete = resolve })
  const f = fixture(t, msg => msg.type === 'bill_tracker/parser/custom/save' ? response : undefined)
  await f.panel._openCustomEditor(row)
  f.fill()
  const pending = f.panel._saveCustomEditor()
  f.panel._closeCustomEditor()
  await f.panel._openCustomEditor()
  f.fill()
  complete({ id: row.id })
  await pending
  f.assertDraft()
  assert.equal(f.panel._customEditor.originalId, null)
})
