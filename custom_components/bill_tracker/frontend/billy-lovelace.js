// Lovelace widgets are independent of the deprecated full-size Billy card.
// The legacy card host is registered separately for existing dashboards.
import './billy-widgets.js?v=0.16.0-r1'

const BILLY_LOVELACE_VERSION = '0.16.0'

// A Home Assistant SPA session can retain the old picker entry after an update.
// Keep existing YAML cards working, but stop offering the obsolete card anew.
function hideLegacyPickerEntry() {
  window.customCards = window.customCards || []
  for (let index = window.customCards.length - 1; index >= 0; index--) {
    if (window.customCards[index].type === 'bill-tracker-card') {
      window.customCards.splice(index, 1)
    }
  }
}
hideLegacyPickerEntry()
if (document.readyState !== 'complete') {
  window.addEventListener('load', hideLegacyPickerEntry, { once: true })
}

console.info(`Billy Lovelace widgets v${BILLY_LOVELACE_VERSION} loaded`)
