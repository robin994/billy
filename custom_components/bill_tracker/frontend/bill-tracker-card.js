const BILLY_FRONTEND_VERSION = '0.11.10'
const BILLY_IMPL_URL = `/bill_tracker/bill-tracker-card-impl.js?v=${BILLY_FRONTEND_VERSION}`
const BILLY_WIDGETS_URL = `/bill_tracker/billy-widgets.js?v=${BILLY_FRONTEND_VERSION}`

const BOOTSTRAP_TEXT = {
  en: {
    loading: 'Loading Billy…',
    frontendError: 'Billy frontend failed to load',
    editorLoading: 'Loading Billy editor…',
    editorError: 'Billy editor failed to load',
    cardName: 'Billy - Bill Tracker',
    cardDescription:
      'Recurring bills, expense splitting, balances and forecasts',
  },
  it: {
    loading: 'Caricamento Billy…',
    frontendError: 'Impossibile caricare il frontend di Billy',
    editorLoading: 'Caricamento editor Billy…',
    editorError: 'Impossibile caricare l’editor di Billy',
    cardName: 'Billy - Gestione bollette',
    cardDescription: 'Bollette ricorrenti, divisione spese, saldi e previsioni',
  },
  es: {
    loading: 'Cargando Billy…',
    frontendError: 'No se pudo cargar la interfaz de Billy',
    editorLoading: 'Cargando el editor de Billy…',
    editorError: 'No se pudo cargar el editor de Billy',
    cardName: 'Billy - Gestión de facturas',
    cardDescription:
      'Facturas recurrentes, reparto de gastos, saldos y previsiones',
  },
  fr: {
    loading: 'Chargement de Billy…',
    frontendError: 'Impossible de charger l’interface Billy',
    editorLoading: 'Chargement de l’éditeur Billy…',
    editorError: 'Impossible de charger l’éditeur Billy',
    cardName: 'Billy - Gestion des factures',
    cardDescription:
      'Factures récurrentes, partage des dépenses, soldes et prévisions',
  },
  de: {
    loading: 'Billy wird geladen…',
    frontendError: 'Billy-Oberfläche konnte nicht geladen werden',
    editorLoading: 'Billy-Editor wird geladen…',
    editorError: 'Billy-Editor konnte nicht geladen werden',
    cardName: 'Billy - Rechnungsverwaltung',
    cardDescription:
      'Wiederkehrende Rechnungen, Kostenteilung, Salden und Prognosen',
  },
  pt: {
    loading: 'A carregar Billy…',
    frontendError: 'Não foi possível carregar a interface do Billy',
    editorLoading: 'A carregar o editor do Billy…',
    editorError: 'Não foi possível carregar o editor do Billy',
    cardName: 'Billy - Gestão de contas',
    cardDescription:
      'Contas recorrentes, divisão de despesas, saldos e previsões',
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
let billyWidgetsPromise = null

function loadBillyImplementation() {
  if (!billyImplementationPromise) {
    billyImplementationPromise = import(BILLY_IMPL_URL).catch((error) => {
      billyImplementationPromise = null
      throw error
    })
  }
  return billyImplementationPromise
}

function loadBillyWidgets() {
  if (!billyWidgetsPromise) {
    billyWidgetsPromise = import(BILLY_WIDGETS_URL).catch((error) => {
      billyWidgetsPromise = null
      throw error
    })
  }
  return billyWidgetsPromise
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

// Register the lightweight host elements before exposing Billy to HA's card picker.
// This avoids the picker trying to instantiate the full card while its implementation
// module is still downloading/evaluating on a cold frontend load.
if (!customElements.get('bill-tracker-card')) {
  customElements.define('bill-tracker-card', BillyCardHost)
}
if (!customElements.get('bill-tracker-card-editor')) {
  customElements.define('bill-tracker-card-editor', BillyCardEditorHost)
}

window.customCards = window.customCards || []
if (!window.customCards.some((card) => card.type === 'bill-tracker-card')) {
  window.customCards.push({
    type: 'bill-tracker-card',
    name: bootstrapText('cardName'),
    description: bootstrapText('cardDescription'),
    preview: false,
    documentationURL: 'https://github.com/robin994/billy',
  })
}

// Start preloading immediately, but the custom element hosts above are already
// available even if the implementation takes longer to arrive.
loadBillyImplementation().catch((error) => {
  console.error('Billy implementation preload failed', error)
})
loadBillyWidgets().catch((error) => {
  console.error('Billy widgets preload failed', error)
})

console.info(`Billy frontend bootstrap v${BILLY_FRONTEND_VERSION} loaded`)
