const BILLY_FRONTEND_VERSION = '0.17.1'
const BILLY_FRONTEND_CACHE_VERSION = '0.17.1-r1'
const BILLY_IMPL_URL = `/bill_tracker/bill-tracker-card-impl.js?v=${BILLY_FRONTEND_CACHE_VERSION}`

const BOOTSTRAP_TEXT = {
  en: {
    loading: 'Loading Billy…',
    frontendError: 'Billy frontend failed to load',
    editorLoading: 'Loading Billy editor…',
    editorError: 'Billy editor failed to load',
  },
  it: {
    loading: 'Caricamento Billy…',
    frontendError: 'Impossibile caricare il frontend di Billy',
    editorLoading: 'Caricamento editor Billy…',
    editorError: 'Impossibile caricare l’editor di Billy',
  },
  es: {
    loading: 'Cargando Billy…',
    frontendError: 'No se pudo cargar la interfaz de Billy',
    editorLoading: 'Cargando el editor de Billy…',
    editorError: 'No se pudo cargar el editor de Billy',
  },
  fr: {
    loading: 'Chargement de Billy…',
    frontendError: 'Impossible de charger l’interface Billy',
    editorLoading: 'Chargement de l’éditeur Billy…',
    editorError: 'Impossible de charger l’éditeur Billy',
  },
  de: {
    loading: 'Billy wird geladen…',
    frontendError: 'Billy-Oberfläche konnte nicht geladen werden',
    editorLoading: 'Billy-Editor wird geladen…',
    editorError: 'Billy-Editor konnte nicht geladen werden',
  },
  pt: {
    loading: 'A carregar Billy…',
    frontendError: 'Não foi possível carregar a interface do Billy',
    editorLoading: 'A carregar o editor do Billy…',
    editorError: 'Não foi possível carregar o editor do Billy',
  },
}

function bootstrapText(key) {
  const raw = String(navigator.language || 'en')
    .toLowerCase()
    .split(/[-_]/)[0]
  const language = BOOTSTRAP_TEXT[raw] ? raw : 'en'
  return BOOTSTRAP_TEXT[language][key] || BOOTSTRAP_TEXT.en[key] || key
}

let billyImplementationPromise = null
let legacyWarningShown = false

function loadBillyImplementation() {
  if (!billyImplementationPromise) {
    billyImplementationPromise = import(BILLY_IMPL_URL).catch((error) => {
      billyImplementationPromise = null
      throw error
    })
  }
  return billyImplementationPromise
}

// Home Assistant can assign hass before the custom element is registered.
// Replaying an own property allows the setter to run after its class upgrades.
function upgradeEarlyProperty(element, name) {
  if (!Object.prototype.hasOwnProperty.call(element, name)) return
  const value = element[name]
  delete element[name]
  element[name] = value
}

class BillyCardHost extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._config = null
    this._hass = null
    this._inner = null
    this._loading = false
    this._loadError = null
  }

  static getStubConfig() {
    return {
      title: '',
      columns: 'full',
      history_months: 12,
      forecast_months: 12,
    }
  }

  static getConfigElement() {
    return document.createElement('bill-tracker-card-editor')
  }

  connectedCallback() {
    if (!legacyWarningShown) {
      console.warn(
        'Billy: custom:bill-tracker-card is deprecated. Use /billy or the Billy Lovelace widgets; the legacy card will be removed in 1.0.0.',
      )
      legacyWarningShown = true
    }
    upgradeEarlyProperty(this, 'hass')
    this._ensureImplementation()
  }

  setConfig(config) {
    this._config = { ...config }
    if (this._inner) this._inner.setConfig(this._config)
    else this._ensureImplementation()
  }

  set hass(hass) {
    this._hass = hass
    if (this._inner) this._inner.hass = hass
    else this._ensureImplementation()
  }

  getCardSize() {
    return this._inner?.getCardSize?.() ?? 12
  }

  getGridOptions() {
    return (
      this._inner?.getGridOptions?.() ?? { columns: 'full', min_columns: 6 }
    )
  }

  async _ensureImplementation() {
    if (this._inner || this._loading) return
    this._loading = true
    this._renderLoading()
    try {
      await loadBillyImplementation()
      await customElements.whenDefined('bill-tracker-card-impl')
      if (!this.isConnected && !this._config && !this._hass) return
      const inner = document.createElement('bill-tracker-card-impl')
      this._inner = inner
      this.shadowRoot.replaceChildren(inner)
      if (this._config) inner.setConfig(this._config)
      if (this._hass) inner.hass = this._hass
      this._loadError = null
    } catch (error) {
      this._loadError = String(error?.message || error)
      this._renderLoading()
      console.error('Billy frontend failed to load', error)
    } finally {
      this._loading = false
    }
  }

  _renderLoading() {
    if (!this.shadowRoot || this._inner) return
    const message = this._loadError
      ? `${bootstrapText('frontendError')}: ${this._escape(this._loadError)}`
      : bootstrapText('loading')
    this.shadowRoot.innerHTML = `<ha-card><div style="padding:20px">${message}</div></ha-card>`
  }

  _escape(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;')
  }
}

class BillyCardEditorHost extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._config = BillyCardHost.getStubConfig()
    this._hass = null
    this._inner = null
    this._loading = false
    this._loadError = null
  }

  connectedCallback() {
    upgradeEarlyProperty(this, 'hass')
    this._ensureImplementation()
  }

  setConfig(config) {
    this._config = { ...BillyCardHost.getStubConfig(), ...config }
    if (this._inner) this._inner.setConfig(this._config)
    else this._ensureImplementation()
  }

  set hass(hass) {
    this._hass = hass
    if (this._inner) this._inner.hass = hass
  }

  async _ensureImplementation() {
    if (this._inner || this._loading) return
    this._loading = true
    this._renderLoading()
    try {
      await loadBillyImplementation()
      await customElements.whenDefined('bill-tracker-card-editor-impl')
      const inner = document.createElement('bill-tracker-card-editor-impl')
      this._inner = inner
      this.shadowRoot.replaceChildren(inner)
      inner.setConfig(this._config)
      if (this._hass) inner.hass = this._hass
      this._loadError = null
    } catch (error) {
      this._loadError = String(error?.message || error)
      this._renderLoading()
      console.error('Billy card editor failed to load', error)
    } finally {
      this._loading = false
    }
  }

  _renderLoading() {
    if (!this.shadowRoot || this._inner) return
    const message = this._loadError
      ? `${bootstrapText('editorError')}: ${this._escape(this._loadError)}`
      : bootstrapText('editorLoading')
    this.shadowRoot.innerHTML = `<div style="padding:16px;color:var(--primary-text-color)">${message}</div>`
  }

  _escape(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;')
  }
}

// Keep existing dashboards working without advertising the old card in the
// picker. Extra HA modules can execute before HA installs its scoped custom
// element registry; repeat registration at window load if it was lost.
function registerLegacyHosts() {
  if (!customElements.get('bill-tracker-card')) {
    customElements.define('bill-tracker-card', BillyCardHost)
  }
  if (!customElements.get('bill-tracker-card-editor')) {
    customElements.define('bill-tracker-card-editor', BillyCardEditorHost)
  }
}
registerLegacyHosts()
if (document.readyState !== 'complete') {
  window.addEventListener('load', registerLegacyHosts, { once: true })
}

console.info(`Billy legacy card host v${BILLY_FRONTEND_VERSION} loaded`)
