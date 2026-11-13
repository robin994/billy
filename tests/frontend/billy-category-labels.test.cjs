const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')

const source = fs.readFileSync(path.join(__dirname,
  '../../custom_components/bill_tracker/frontend/bill-tracker-i18n.js'), 'utf8')
  .replace(/^export /gm, '')
const context = vm.createContext({})
vm.runInContext(source + '\nglobalThis.label = billyCategoryLabel', context)

for (const [language, expected] of [
  ['en', 'Electricity'], ['it', 'Elettricità'], ['de', 'Strom'],
]) {
  test(`default bill type follows ${language} locale`, () => {
    assert.equal(context.label({ language }, { id: 'electricity', name: 'Elettricità' }), expected)
  })
}

test('renamed built-in bill type is never overwritten by locale', () => {
  for (const language of ['en', 'it', 'de']) {
    assert.equal(context.label({ language }, { id: 'electricity', name: 'Áram' }), 'Áram')
  }
})

test('custom categories always preserve their names', () => {
  assert.equal(context.label({ language: 'en' }, { id: 'heating-oil', name: 'Öl' }), 'Öl')
})

test('removed bill type fallback is translated for each locale', () => {
  const removed = { id: 'deleted-category', name: 'Bolletta rimossa' }
  assert.equal(context.label({ language: 'en' }, removed), 'Removed bill type')
  assert.equal(context.label({ language: 'it' }, removed), 'Bolletta rimossa')
  assert.equal(context.label({ language: 'de' }, removed), 'Entfernter Rechnungstyp')
})
