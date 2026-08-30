import {
  BILLY_ERROR_TEXT,
  BILLY_PARSER_EXTRA_TEXT,
} from './billy-extra-i18n.js?v=0.11.10-r1'

const BILLY_PARSER_MANAGER_VERSION = '0.11.10'

const TEXT = {
  en: {
    title: 'Parser management',
    subtitle: 'Install, update and configure automatic bill parsers.',
    refresh: 'Refresh list',
    refreshing: 'Refreshing…',
    search: 'Search provider, parser or type…',
    country: 'Country',
    allCountries: 'All countries',
    billType: 'Bill type',
    allBillTypes: 'All bill types',
    installationStatus: 'Installation status',
    catalogStatus: 'Catalog status',
    allCatalogStatuses: 'All catalog statuses',
    all: 'All',
    installed: 'Installed',
    notInstalled: 'Not installed',
    updates: 'Updates available',
    incompatible: 'Incompatible',
    deprecated: 'Deprecated',
    sort: 'Sort',
    sortCountry: 'Country → provider',
    sortProvider: 'Provider',
    sortType: 'Bill type',
    sortUpdates: 'Updates first',
    available: 'Available',
    outdated: 'Update available',
    catalogOutdated: 'Outdated',
    removed: 'Removed from catalog',
    error: 'Error',
    custom: 'Custom',
    requires: 'Requires Billy',
    version: 'Version',
    installedVersion: 'Installed',
    remoteVersion: 'Available',
    install: 'Install',
    update: 'Update',
    configure: 'Configure',
    remove: 'Remove',
    close: 'Close',
    save: 'Save',
    enabled: 'Parser enabled',
    autoImport: 'Automatic import',
    category: 'Billy bill type',
    defaultPayer: 'Default payer',
    defaultSplit: 'Default split',
    noDefaultPayer: 'No default payer',
    noResults: 'No parsers match the selected filters.',
    catalogUpdated: 'Catalog updated',
    catalogCacheWarning:
      'Remote catalog refresh failed. Showing the last cached catalog.',
    lastIngestion: 'Last IMAP event',
    never: 'not yet',
    parsers: 'parsers',
    updateCount: 'updates available',
    confirmRemove:
      'Remove this parser? Already imported bills will not be deleted.',
    installTitle: 'Install parser',
    updateTitle: 'Update parser',
    configureTitle: 'Configure parser',
    loadError: 'Unable to load parser data.',
    actionError: 'Operation failed',
    updateBlocked: 'Update requires a newer Billy version',
    deprecatedHint: 'This parser is deprecated.',
    removedHint:
      'This installed parser is no longer present in the remote catalog.',
    customHint: 'Custom parser stored locally.',
    changelog: 'Changes',
    verified: 'Verified',
    experimental: 'Experimental',
    experimentalHint:
      'Experimental parser: it may not work with every bill format yet.',
    verifiedHint: 'Verified parser recommended by the Billy parser catalog.',
    outdatedHint: 'This parser is no longer recommended by the catalog.',
    replacement: 'Replacement',
    installReplacement: 'Install replacement',
    shareCommunity: 'Share with community',
    publishTooLarge:
      'This parser is too large for browser sharing. Export it and submit the YAML through the billy-parser submission flow.',
    publishHint:
      'Only parser metadata and YAML are included. No invoices, emails or attachments are shared.',
    communityFeedback: 'Community feedback',
    feedbackPrompt: 'Did this experimental parser work with your bill?',
    feedbackWorking: 'Works',
    feedbackPartial: 'Partial',
    feedbackFailed: 'Does not work',
    feedbackHint:
      'Feedback contains only parser ID, version, result and an anonymous installation fingerprint.',
    feedbackSourceUnknown:
      'Unable to submit feedback because the parser source revision is unknown. Update or reinstall the parser first.',
    feedbackStats: '{working} works · {partial} partial · {failed} failed',
    newCustom: 'New custom parser',
    editCustom: 'Edit parser',
    exportCustom: 'Export',
    customEditorTitle: 'Custom parser editor',
    customEditorNewTitle: 'Create custom parser',
    customEditorHint:
      'Create and manage a local parser here. The YAML must follow the Billy parser schema.',
    yamlSource: 'Parser YAML',
    testData: 'Optional test data',
    testSender: 'Sender',
    testSubject: 'Subject',
    testEmail: 'Email text',
    validateTest: 'Validate / test',
    validating: 'Testing…',
    yamlValid: 'YAML valid',
    yamlInvalid: 'Invalid parser',
    testMatched: 'Detection matched',
    testNotMatched: 'Detection not matched',
    detectionScore: 'Detection score',
    saveCustom: 'Save custom parser',
    customSaved: 'Custom parser saved.',
    editorLoading: 'Loading parser…',
    customIdLocked:
      'The parser ID cannot be changed while editing an existing custom parser.',
  },
  it: {
    title: 'Gestione parser',
    subtitle:
      'Installa, aggiorna e configura i parser automatici delle bollette.',
    refresh: 'Aggiorna lista',
    refreshing: 'Aggiornamento…',
    search: 'Cerca fornitore, parser o tipo…',
    country: 'Nazione',
    allCountries: 'Tutte le nazioni',
    billType: 'Tipologia',
    allBillTypes: 'Tutte le tipologie',
    installationStatus: 'Stato installazione',
    catalogStatus: 'Stato catalogo',
    allCatalogStatuses: 'Tutti gli stati catalogo',
    all: 'Tutti',
    installed: 'Installati',
    notInstalled: 'Non installati',
    updates: 'Aggiornamenti disponibili',
    incompatible: 'Incompatibili',
    deprecated: 'Deprecati',
    sort: 'Ordina',
    sortCountry: 'Nazione → fornitore',
    sortProvider: 'Fornitore',
    sortType: 'Tipo bolletta',
    sortUpdates: 'Aggiornamenti prima',
    available: 'Disponibile',
    outdated: 'Aggiornamento disponibile',
    catalogOutdated: 'Obsoleto',
    removed: 'Rimosso dal catalogo',
    error: 'Errore',
    custom: 'Personalizzato',
    requires: 'Richiede Billy',
    version: 'Versione',
    installedVersion: 'Installata',
    remoteVersion: 'Disponibile',
    install: 'Installa',
    update: 'Aggiorna',
    configure: 'Configura',
    remove: 'Elimina',
    close: 'Chiudi',
    save: 'Salva',
    enabled: 'Parser abilitato',
    autoImport: 'Import automatico',
    category: 'Tipo di bolletta Billy',
    defaultPayer: 'Pagante predefinito',
    defaultSplit: 'Divisione predefinita',
    noDefaultPayer: 'Nessun pagante predefinito',
    noResults: 'Nessun parser corrisponde ai filtri selezionati.',
    catalogUpdated: 'Catalogo aggiornato',
    catalogCacheWarning:
      'Aggiornamento del catalogo remoto non riuscito. Viene mostrata l’ultima copia in cache.',
    lastIngestion: 'Ultimo evento IMAP',
    never: 'mai',
    parsers: 'parser',
    updateCount: 'aggiornamenti disponibili',
    confirmRemove:
      'Eliminare questo parser? Le bollette già importate non verranno cancellate.',
    installTitle: 'Installa parser',
    updateTitle: 'Aggiorna parser',
    configureTitle: 'Configura parser',
    loadError: 'Impossibile caricare i dati dei parser.',
    actionError: 'Operazione non riuscita',
    updateBlocked: 'L’aggiornamento richiede una versione più recente di Billy',
    deprecatedHint: 'Questo parser è deprecato.',
    removedHint:
      'Questo parser installato non è più presente nel catalogo remoto.',
    customHint: 'Parser personalizzato salvato localmente.',
    changelog: 'Modifiche',
    verified: 'Verificato',
    experimental: 'Sperimentale',
    experimentalHint:
      'Parser sperimentale: potrebbe non funzionare ancora con tutti i formati di bolletta.',
    verifiedHint: 'Parser verificato e raccomandato dal catalogo Billy.',
    outdatedHint: 'Questo parser non è più raccomandato dal catalogo.',
    replacement: 'Sostituto',
    installReplacement: 'Installa sostituto',
    shareCommunity: 'Condividi con la community',
    publishTooLarge:
      'Questo parser è troppo grande per la condivisione dal browser. Esportalo e invia lo YAML tramite il flusso di submission di billy-parser.',
    publishHint:
      'Vengono inclusi solo metadata e YAML del parser. Nessuna bolletta, email o allegato viene condiviso.',
    communityFeedback: 'Feedback community',
    feedbackPrompt:
      'Questo parser sperimentale ha funzionato con la tua bolletta?',
    feedbackWorking: 'Funziona',
    feedbackPartial: 'Parziale',
    feedbackFailed: 'Non funziona',
    feedbackHint:
      'Il feedback contiene solo ID parser, versione, esito e un fingerprint anonimo dell’installazione.',
    feedbackSourceUnknown:
      'Impossibile inviare il feedback perché la revisione sorgente del parser è sconosciuta. Aggiorna o reinstalla prima il parser.',
    feedbackStats: '{working} funziona · {partial} parziale · {failed} fallito',
    newCustom: 'Nuovo parser custom',
    editCustom: 'Modifica parser',
    exportCustom: 'Esporta',
    customEditorTitle: 'Editor parser custom',
    customEditorNewTitle: 'Crea parser custom',
    customEditorHint:
      'Crea e gestisci qui un parser locale. Lo YAML deve rispettare lo schema parser di Billy.',
    yamlSource: 'YAML del parser',
    testData: 'Dati di test opzionali',
    testSender: 'Mittente',
    testSubject: 'Oggetto',
    testEmail: 'Testo email',
    validateTest: 'Valida / testa',
    validating: 'Test in corso…',
    yamlValid: 'YAML valido',
    yamlInvalid: 'Parser non valido',
    testMatched: 'Rilevamento riuscito',
    testNotMatched: 'Rilevamento non riuscito',
    detectionScore: 'Punteggio rilevamento',
    saveCustom: 'Salva parser custom',
    customSaved: 'Parser custom salvato.',
    editorLoading: 'Caricamento parser…',
    customIdLocked:
      'L’ID del parser non può essere cambiato durante la modifica di un parser custom esistente.',
  },
}
Object.assign(TEXT, BILLY_PARSER_EXTRA_TEXT)

function languageOf(hass) {
  const raw =
    hass?.language || hass?.locale?.language || navigator.language || 'en'
  const language = String(raw).toLowerCase().split(/[-_]/)[0]
  return ['en', 'it', 'es', 'fr', 'de', 'pt'].includes(language)
    ? language
    : 'en'
}

// Localized labels for the built-in Billy bill types, keyed by language then by
// bill-type id. Unknown ids fall back to a title-cased version of the id.
const BILL_TYPE_LABELS = {
  en: {
    electricity: 'Electricity',
    gas: 'Gas',
    water: 'Water',
    internet: 'Internet',
    mobile: 'Mobile',
    phone: 'Phone',
    insurance: 'Insurance',
  },
  it: {
    electricity: 'Elettricità',
    gas: 'Gas',
    water: 'Acqua',
    internet: 'Internet',
    mobile: 'Telefonia mobile',
    phone: 'Telefono',
    insurance: 'Assicurazione',
  },
  es: {
    electricity: 'Electricidad',
    gas: 'Gas',
    water: 'Agua',
    internet: 'Internet',
    mobile: 'Móvil',
    phone: 'Teléfono',
    insurance: 'Seguro',
  },
  fr: {
    electricity: 'Électricité',
    gas: 'Gaz',
    water: 'Eau',
    internet: 'Internet',
    mobile: 'Mobile',
    phone: 'Téléphone',
    insurance: 'Assurance',
  },
  de: {
    electricity: 'Strom',
    gas: 'Gas',
    water: 'Wasser',
    internet: 'Internet',
    mobile: 'Handy',
    phone: 'Telefon',
    insurance: 'Versicherung',
  },
  pt: {
    electricity: 'Eletricidade',
    gas: 'Gás',
    water: 'Água',
    internet: 'Internet',
    mobile: 'Telemóvel',
    phone: 'Telefone',
    insurance: 'Seguro',
  },
}

// Resolve a websocket/runtime error to a localized message via its stable code,
// falling back to the English message the backend sends with it.
function errorText(hass, error) {
  const code = error?.code
  if (code) {
    const table = BILLY_ERROR_TEXT[languageOf(hass)] || BILLY_ERROR_TEXT.en || {}
    if (table[code]) return table[code]
  }
  return String(error?.message || error)
}

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function countryFlag(code) {
  const value = String(code || '')
    .trim()
    .toUpperCase()
  if (!/^[A-Z]{2}$/.test(value)) return '🌐'
  return String.fromCodePoint(
    ...[...value].map((char) => 127397 + char.charCodeAt(0)),
  )
}

class BillyParserManagerPanel extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._hass = null
    this._data = null
    this._billData = null
    this._loading = false
    this._refreshing = false
    this._busy = ''
    this._error = ''
    this._search = ''
    this._country = 'all'
    this._billType = 'all'
    this._status = 'all'
    this._catalogStatus = 'all'
    this._sort = 'country'
    this._dialog = null
    this._customEditor = null
  }

  set hass(value) {
    this._hass = value
    if (!this._data && !this._loading) this._load()
    else this._render()
  }

  // Installed Billy version reported by the backend; falls back to this bundle's.
  _billyVersion() {
    return this._billData?.version || BILLY_PARSER_MANAGER_VERSION
  }

  get hass() {
    return this._hass
  }

  connectedCallback() {
    this._render()
    if (this._hass && !this._data && !this._loading) this._load()
  }

  _t(key, values = {}) {
    const language = languageOf(this._hass)
    let text = TEXT[language]?.[key] ?? TEXT.en[key] ?? key
    for (const [name, value] of Object.entries(values)) {
      text = text.replaceAll(`{${name}}`, String(value))
    }
    return text
  }

  async _load({ refreshIfEmpty = true } = {}) {
    if (!this._hass || this._loading) return
    this._loading = true
    this._error = ''
    this._render()
    try {
      const [parserData, billData] = await Promise.all([
        this._hass.callWS({ type: 'bill_tracker/parser/list' }),
        this._hass.callWS({ type: 'bill_tracker/list', forecast_months: 1 }),
      ])
      this._data = parserData
      this._billData = billData
      const rows = parserData?.catalog?.parsers || []
      if (refreshIfEmpty && rows.length === 0) {
        await this._refreshCatalog()
        return
      }
    } catch (error) {
      this._error = `${this._t('loadError')} ${errorText(this._hass, error)}`
    } finally {
      this._loading = false
      this._render()
    }
  }

  async _refreshCatalog() {
    if (!this._hass || this._refreshing) return
    this._refreshing = true
    this._error = ''
    this._render()
    try {
      await this._hass.callWS({ type: 'bill_tracker/parser/refresh' })
      this._loading = false
      await this._load({ refreshIfEmpty: false })
    } catch (error) {
      this._error = `${this._t('actionError')}: ${errorText(this._hass, error)}`
    } finally {
      this._refreshing = false
      this._render()
    }
  }

  _rows() {
    const catalogRows = [...(this._data?.catalog?.parsers || [])]
    const known = new Set(catalogRows.map((row) => String(row.id)))
    for (const installed of this._data?.installed || []) {
      if (installed.source !== 'custom' || known.has(String(installed.id)))
        continue
      catalogRows.push({
        ...installed,
        status: 'custom',
        catalog_status: 'custom',
        installed: true,
        installed_version: installed.version,
        compatible: true,
        country: installed.country || '',
        provider: installed.provider || '',
        bill_type: installed.bill_type || '',
        source: 'custom',
      })
    }
    return catalogRows
  }

  _filteredRows() {
    const search = this._search.trim().toLowerCase()
    const rows = this._rows().filter((row) => {
      if (
        this._country !== 'all' &&
        String(row.country || '') !== this._country
      )
        return false
      if (
        this._billType !== 'all' &&
        String(row.bill_type || '') !== this._billType
      )
        return false
      if (this._status !== 'all') {
        if (this._status === 'updates') {
          if (!row.update_available) return false
        } else if (String(row.status || 'available') !== this._status)
          return false
      }
      if (
        this._catalogStatus !== 'all' &&
        String(row.catalog_status || 'experimental') !== this._catalogStatus
      )
        return false
      if (!search) return true
      return [row.name, row.provider, row.id, row.bill_type, row.country].some(
        (value) =>
          String(value || '')
            .toLowerCase()
            .includes(search),
      )
    })

    const compareText = (a, b) =>
      String(a || '').localeCompare(String(b || ''), undefined, {
        sensitivity: 'base',
      })
    rows.sort((a, b) => {
      if (this._sort === 'updates') {
        const updateDiff =
          Number(Boolean(b.update_available)) -
          Number(Boolean(a.update_available))
        if (updateDiff) return updateDiff
      }
      if (this._sort === 'provider')
        return compareText(a.provider || a.name, b.provider || b.name)
      if (this._sort === 'type') {
        return (
          compareText(a.bill_type, b.bill_type) ||
          compareText(a.provider || a.name, b.provider || b.name)
        )
      }
      return (
        compareText(a.country, b.country) ||
        compareText(a.provider || a.name, b.provider || b.name)
      )
    })
    return rows
  }

  _countries() {
    return [
      ...new Set(
        this._rows()
          .map((row) => String(row.country || ''))
          .filter(Boolean),
      ),
    ].sort()
  }

  _billTypes() {
    return [
      ...new Set(
        this._rows()
          .map((row) => String(row.bill_type || ''))
          .filter(Boolean),
      ),
    ].sort()
  }

  _billTypeLabel(value) {
    const language = languageOf(this._hass)
    const key = String(value || '')
    return (
      BILL_TYPE_LABELS[language]?.[key] ||
      key.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
    )
  }

  _statusLabel(row) {
    if (row.status === 'outdated') return this._t('outdated')
    if (row.status === 'installed') return this._t('installed')
    if (row.status === 'incompatible') return this._t('incompatible')
    if (row.status === 'deprecated') return this._t('deprecated')
    if (row.status === 'removed') return this._t('removed')
    if (row.status === 'error') return this._t('error')
    if (row.status === 'custom') return this._t('custom')
    return this._t('available')
  }

  _catalogStatusLabel(catalogStatus) {
    const value = String(catalogStatus || 'experimental')
    if (value === 'experimental') return this._t('experimental')
    if (value === 'verified') return this._t('verified')
    if (value === 'outdated') return this._t('catalogOutdated')
    return this._t('custom')
  }

  _renderRow(row) {
    const installedVersion = row.installed_version ?? row.version
    const remoteVersion = row.version
    const busy = this._busy === String(row.id)
    const canUpdate =
      row.update_available &&
      row.compatible !== false &&
      !row.removed_from_catalog
    let versionLine = `${this._t('version')} v${esc(remoteVersion ?? '?')}`
    if (row.update_available) {
      versionLine = `${this._t('installedVersion')} v${esc(installedVersion)} → ${this._t('remoteVersion')} v${esc(remoteVersion)}`
    }

    let hint = ''
    if (row.compatible === false)
      hint = `${this._t('requires')} ${esc(row.min_billy_version || '?')}`
    if (row.deprecated) hint = this._t('deprecatedHint')
    if (row.catalog_status === 'experimental')
      hint = this._t('experimentalHint')
    if (row.catalog_status === 'verified' && !hint)
      hint = this._t('verifiedHint')
    if (row.catalog_status === 'outdated') {
      hint = this._t('outdatedHint')
      if (row.replacement)
        hint += ` ${this._t('replacement')}: ${esc(row.replacement)}.`
    }
    if (row.status === 'removed') hint = this._t('removedHint')
    if (row.status === 'custom') hint = this._t('customHint')
    if (row.load_error) hint = esc(row.load_error)

    let actions = ''
    if (row.source === 'custom') {
      actions = `
        <button class="secondary" data-action="edit-custom" data-id="${esc(row.id)}">${this._t('editCustom')}</button>
        <button class="secondary" data-action="configure" data-id="${esc(row.id)}">${this._t('configure')}</button>
        <button class="secondary" data-action="export-custom" data-id="${esc(row.id)}">${this._t('exportCustom')}</button>
        <button class="primary" data-action="publish" data-id="${esc(row.id)}">${this._t('shareCommunity')}</button>
        <button class="danger" data-action="remove" data-id="${esc(row.id)}">${this._t('remove')}</button>`
    } else if (!row.installed) {
      actions = `<button class="primary" data-action="install" data-id="${esc(row.id)}" ${row.compatible === false || busy ? 'disabled' : ''}>${this._t('install')}</button>`
    } else {
      actions = `
        <button class="secondary" data-action="configure" data-id="${esc(row.id)}">${this._t('configure')}</button>
        ${row.update_available ? `<button class="primary" data-action="update" data-id="${esc(row.id)}" ${canUpdate && !busy ? '' : 'disabled'} title="${row.compatible === false ? esc(this._t('updateBlocked')) : ''}">${this._t('update')}</button>` : ''}
        <button class="danger" data-action="remove" data-id="${esc(row.id)}" ${busy ? 'disabled' : ''}>${this._t('remove')}</button>`
    }
    const feedbackEligible =
      row.source !== 'custom' &&
      row.installed &&
      (row.installed_catalog_status || row.catalog_status) === 'experimental'
    const canSubmitFeedback =
      feedbackEligible && row.feedback_available === true
    if (canSubmitFeedback) {
      actions += `<div class="feedback-actions" title="${esc(this._t('feedbackHint'))}"><span>${esc(this._t('feedbackPrompt'))}</span><div><button class="feedback-working" data-action="feedback-working" data-id="${esc(row.id)}">✓ ${esc(this._t('feedbackWorking'))}</button><button class="feedback-partial" data-action="feedback-partial" data-id="${esc(row.id)}">~ ${esc(this._t('feedbackPartial'))}</button><button class="feedback-failed" data-action="feedback-failed" data-id="${esc(row.id)}">× ${esc(this._t('feedbackFailed'))}</button></div></div>`
    }
    const feedbackUnavailable =
      row.source !== 'custom' &&
      row.installed &&
      row.feedback_block_reason === 'source_commit_unavailable'
        ? this._t('feedbackSourceUnknown')
        : ''
    if (
      row.catalog_status === 'outdated' &&
      row.replacement &&
      row.source !== 'custom'
    ) {
      actions += `<button class="secondary" data-action="install-replacement" data-id="${esc(row.replacement)}">${this._t('installReplacement')}</button>`
    }

    const badges = [
      `<span class="badge status-${esc(row.status || 'available')}">${esc(this._statusLabel(row))}</span>`,
      row.update_available
        ? `<span class="badge warning">v${esc(installedVersion)} → v${esc(remoteVersion)}</span>`
        : '',
      row.deprecated
        ? `<span class="badge warning">${this._t('deprecated')}</span>`
        : '',
      row.compatible === false
        ? `<span class="badge error">${this._t('incompatible')}</span>`
        : '',
      `<span class="badge catalog-${esc(row.catalog_status || 'experimental')}">${esc(this._catalogStatusLabel(row.catalog_status))}</span>`,
    ].join('')
    const feedback = row.feedback || {}
    const feedbackTotal =
      Number(feedback.working || 0) +
      Number(feedback.partial || 0) +
      Number(feedback.failed || 0)
    const feedbackLine = feedbackTotal
      ? this._t('feedbackStats', {
          working: Number(feedback.working || 0),
          partial: Number(feedback.partial || 0),
          failed: Number(feedback.failed || 0),
        })
      : ''

    return `
      <article class="parser-row">
        <div class="identity">
          <div class="flag">${countryFlag(row.country)}</div>
          <div class="details">
            <div class="name-line">
              <strong>${esc(row.provider || row.name || row.id)}</strong>
              ${badges}
            </div>
            <div class="parser-name">${esc(row.name || row.id)}</div>
            <div class="meta">${esc(row.id)} · ${esc(row.bill_type || '—')} · ${versionLine}</div>
            ${hint ? `<div class="hint">${hint}</div>` : ''}
            ${feedbackUnavailable ? `<div class="hint feedback-unavailable">${esc(feedbackUnavailable)}</div>` : ''}
            ${feedbackLine ? `<div class="hint"><strong>${this._t('communityFeedback')}:</strong> ${esc(feedbackLine)}</div>` : ''}
            ${row.changelog ? `<div class="hint"><strong>${this._t('changelog')}:</strong> ${esc(row.changelog)}</div>` : ''}
          </div>
        </div>
        <div class="actions">${actions}</div>
      </article>`
  }

  _render() {
    if (!this.shadowRoot) return
    const rows = this._filteredRows()
    const counts = this._data?.catalog?.counts || {}
    const updatedAt = this._data?.catalog?.updated_at
    const countries = this._countries()
    const billTypes = this._billTypes()
    const countryOptions = [
      `<option value="all">${this._t('allCountries')}</option>`,
    ]
      .concat(
        countries.map(
          (code) =>
            `<option value="${esc(code)}" ${this._country === code ? 'selected' : ''}>${countryFlag(code)} ${esc(code)}</option>`,
        ),
      )
      .join('')
    const billTypeOptions = [
      `<option value="all">${this._t('allBillTypes')}</option>`,
    ]
      .concat(
        billTypes.map(
          (type) =>
            `<option value="${esc(type)}" ${this._billType === type ? 'selected' : ''}>${esc(this._billTypeLabel(type))}</option>`,
        ),
      )
      .join('')

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <div class="page">
        <header>
          <div>
            <h1>${this._t('title')}</h1>
            <p>${this._t('subtitle')}</p>
          </div>
          <div class="header-actions">
            <button id="new-custom" class="secondary">＋ ${this._t('newCustom')}</button>
            <button id="refresh" class="primary" ${this._refreshing ? 'disabled' : ''}>
              ${this._refreshing ? this._t('refreshing') : `↻ ${this._t('refresh')}`}
            </button>
          </div>
        </header>

        <section class="summary">
          <strong>${esc(counts.total ?? this._rows().length)} ${this._t('parsers')}</strong>
          <span class="${Number(counts.outdated || 0) > 0 ? 'summary-alert' : ''}">${esc(counts.outdated || 0)} ${this._t('updateCount')}</span>
          <span>${this._t('catalogUpdated')}: ${updatedAt ? esc(new Date(updatedAt).toLocaleString()) : this._t('never')}</span>
        </section>

        ${this._data?.catalog?.refresh_error ? `<div class="warning-box">⚠ ${esc(this._t('catalogCacheWarning'))}</div>` : ''}
        ${
          this._data?.diagnostic
            ? `<div class="diagnostic-box"><strong>${esc(this._t('lastIngestion'))}</strong><span>${esc(`${this._data.diagnostic.outcome || 'unknown'} · UID ${this._data.diagnostic.uid || '—'} · ${this._data.diagnostic.subject || '—'}`)}</span><small>${esc(this._data.diagnostic.detail || '')}</small></div>`
            : ''
        }

        <section class="filters">
          <label class="search-field">
            <span>⌕</span>
            <input id="search" type="search" value="${esc(this._search)}" placeholder="${esc(this._t('search'))}">
          </label>
          <label><span>${this._t('country')}</span><select id="country">${countryOptions}</select></label>
          <label><span>${this._t('billType')}</span><select id="bill-type">${billTypeOptions}</select></label>
          <label><span>${this._t('catalogStatus')}</span><select id="catalog-status">
            <option value="all" ${this._catalogStatus === 'all' ? 'selected' : ''}>${this._t('allCatalogStatuses')}</option>
            <option value="verified" ${this._catalogStatus === 'verified' ? 'selected' : ''}>${this._t('verified')}</option>
            <option value="experimental" ${this._catalogStatus === 'experimental' ? 'selected' : ''}>${this._t('experimental')}</option>
            <option value="outdated" ${this._catalogStatus === 'outdated' ? 'selected' : ''}>${this._t('catalogOutdated')}</option>
            <option value="custom" ${this._catalogStatus === 'custom' ? 'selected' : ''}>${this._t('custom')}</option>
          </select></label>
          <label><span>${this._t('installationStatus')}</span><select id="status">
            <option value="all" ${this._status === 'all' ? 'selected' : ''}>${this._t('all')}</option>
            <option value="installed" ${this._status === 'installed' ? 'selected' : ''}>${this._t('installed')}</option>
            <option value="available" ${this._status === 'available' ? 'selected' : ''}>${this._t('available')}</option>
            <option value="updates" ${this._status === 'updates' ? 'selected' : ''}>${this._t('updates')}</option>
            <option value="incompatible" ${this._status === 'incompatible' ? 'selected' : ''}>${this._t('incompatible')}</option>
            <option value="deprecated" ${this._status === 'deprecated' ? 'selected' : ''}>${this._t('deprecated')}</option>
            <option value="error" ${this._status === 'error' ? 'selected' : ''}>${this._t('error')}</option>
            <option value="removed" ${this._status === 'removed' ? 'selected' : ''}>${this._t('removed')}</option>
            <option value="custom" ${this._status === 'custom' ? 'selected' : ''}>${this._t('custom')}</option>
          </select></label>
          <label><span>${this._t('sort')}</span><select id="sort">
            <option value="country" ${this._sort === 'country' ? 'selected' : ''}>${this._t('sortCountry')}</option>
            <option value="provider" ${this._sort === 'provider' ? 'selected' : ''}>${this._t('sortProvider')}</option>
            <option value="type" ${this._sort === 'type' ? 'selected' : ''}>${this._t('sortType')}</option>
            <option value="updates" ${this._sort === 'updates' ? 'selected' : ''}>${this._t('sortUpdates')}</option>
          </select></label>
        </section>

        ${this._error ? `<div class="error-box">${esc(this._error)}</div>` : ''}
        ${this._loading ? '<div class="loading">Loading…</div>' : ''}
        <section class="list">
          ${rows.length ? rows.map((row) => this._renderRow(row)).join('') : `<div class="empty">${this._t('noResults')}</div>`}
        </section>
        ${this._customEditor ? this._renderCustomEditor() : this._dialog ? this._renderDialog() : ''}
      </div>`

    this._wireEvents()
  }

  _renderList() {
    const list = this.shadowRoot?.querySelector('.list')
    if (!list) return
    const rows = this._filteredRows()
    list.innerHTML = rows.length
      ? rows.map((row) => this._renderRow(row)).join('')
      : `<div class="empty">${this._t('noResults')}</div>`
    this._wireActionEvents()
  }

  _wireActionEvents() {
    this.shadowRoot.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', (event) => {
        const action = event.currentTarget.dataset.action
        const id = event.currentTarget.dataset.id
        this._handleAction(action, id)
      })
    })
  }

  _wireEvents() {
    this.shadowRoot
      .getElementById('new-custom')
      ?.addEventListener('click', () => this._openCustomEditor())
    this.shadowRoot
      .getElementById('refresh')
      ?.addEventListener('click', () => this._refreshCatalog())
    this.shadowRoot
      .getElementById('search')
      ?.addEventListener('input', (event) => {
        // Do not rebuild the input itself while the user is typing: replacing it
        // resets the caret to position 0 and made text appear in reverse order.
        this._search = event.target.value
        this._renderList()
      })
    this.shadowRoot
      .getElementById('country')
      ?.addEventListener('change', (event) => {
        this._country = event.target.value
        this._render()
      })
    this.shadowRoot
      .getElementById('bill-type')
      ?.addEventListener('change', (event) => {
        this._billType = event.target.value
        this._render()
      })
    this.shadowRoot
      .getElementById('catalog-status')
      ?.addEventListener('change', (event) => {
        this._catalogStatus = event.target.value
        this._render()
      })
    this.shadowRoot
      .getElementById('status')
      ?.addEventListener('change', (event) => {
        this._status = event.target.value
        this._render()
      })
    this.shadowRoot
      .getElementById('sort')
      ?.addEventListener('change', (event) => {
        this._sort = event.target.value
        this._render()
      })
    this._wireActionEvents()
    const closeDialog = () => {
      this._dialog = null
      this._render()
    }
    this.shadowRoot
      .getElementById('dialog-close')
      ?.addEventListener('click', closeDialog)
    this.shadowRoot
      .getElementById('dialog-close-secondary')
      ?.addEventListener('click', closeDialog)
    this.shadowRoot
      .getElementById('dialog-save')
      ?.addEventListener('click', () => this._saveDialog())
    this.shadowRoot
      .getElementById('custom-editor-close')
      ?.addEventListener('click', () => this._closeCustomEditor())
    this.shadowRoot
      .getElementById('custom-editor-cancel')
      ?.addEventListener('click', () => this._closeCustomEditor())
    this.shadowRoot
      .getElementById('custom-editor-save')
      ?.addEventListener('click', () => this._saveCustomEditor())
    this.shadowRoot
      .getElementById('custom-editor-test')
      ?.addEventListener('click', () => this._testCustomEditor())
  }

  _defaultCustomTemplate() {
    const version = this._billyVersion()
    return `schema: 1
id: it.provider.internet
version: 1

metadata:
  name: Provider - Internet
  country: IT
  language: it
  provider: Provider
  bill_type: internet
  min_billy_version: ${version}
  status: experimental
  quality: experimental

prefilter:
  email:
    subject_contains:
      - bolletta

detection:
  threshold: 60
  rules:
    - source: email.subject
      contains: bolletta
      weight: 60

documents:
  email:
    enabled: true

fields:
  provider:
    value: Provider

  bill_type:
    value: internet

  currency:
    value: EUR

  amount:
    required: true
    candidates:
      - source: email
        regex: '(?i)(?:totale|importo)\s*(?:da\s+pagare)?[:\s]+(?P<value>[0-9.,]+)\s*€'
    transform:
      type: decimal
      locale: it_IT
`
  }

  async _openCustomEditor(row = null) {
    const categories = this._billData?.categories || []
    const defaultCategory = String(
      row?.category_id ||
        categories.find(
          (item) => String(item.id) === String(row?.bill_type || ''),
        )?.id ||
        categories.find((item) => item.enabled !== false)?.id ||
        categories[0]?.id ||
        '',
    )
    this._dialog = null
    this._customEditor = {
      row,
      originalId: row ? String(row.id) : null,
      content: row ? '' : this._defaultCustomTemplate(),
      categoryId: defaultCategory,
      enabled: row ? row.enabled !== false : true,
      autoImport: row ? Boolean(row.auto_import) : false,
      loading: Boolean(row),
      testing: false,
      result: null,
      error: '',
    }
    this._render()
    if (!row) return
    try {
      const exported = await this._hass.callWS({
        type: 'bill_tracker/parser/custom/export',
        parser_id: String(row.id),
      })
      const raw = atob(exported.content_base64 || '')
      const bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0))
      this._customEditor.content = new TextDecoder().decode(bytes)
      this._customEditor.loading = false
    } catch (error) {
      this._customEditor.loading = false
      this._customEditor.error = `${this._t('actionError')}: ${errorText(this._hass, error)}`
    }
    this._render()
  }

  _closeCustomEditor() {
    this._customEditor = null
    this._render()
  }

  _renderCustomEditor() {
    const editor = this._customEditor
    const categories = this._billData?.categories || []
    const options = categories
      .map(
        (category) => `
      <option value="${esc(category.id)}" ${String(category.id) === String(editor.categoryId) ? 'selected' : ''}>
        ${esc(category.name)}${category.enabled === false ? ' · disabled' : ''}
      </option>`,
      )
      .join('')
    const result = editor.result
      ? `<div class="test-result ${editor.result.ok ? 'test-ok' : 'test-error'}">
          <strong>${editor.result.ok ? this._t('yamlValid') : this._t('yamlInvalid')}</strong>
          ${editor.result.ok ? `<span>${editor.result.matched ? this._t('testMatched') : this._t('testNotMatched')} · ${this._t('detectionScore')}: ${esc(editor.result.score)}/${esc(editor.result.threshold)}</span>` : ''}
          ${editor.result.message ? `<span>${esc(editor.result.message)}</span>` : ''}
          ${editor.result.ok && editor.result.data && Object.keys(editor.result.data).length ? `<pre>${esc(JSON.stringify(editor.result.data, null, 2))}</pre>` : ''}
        </div>`
      : ''
    return `
      <div class="modal-backdrop custom-editor-backdrop">
        <div class="modal custom-editor-modal" role="dialog" aria-modal="true">
          <div class="modal-head">
            <div>
              <h2>${editor.originalId ? this._t('customEditorTitle') : this._t('customEditorNewTitle')}</h2>
              <p>${this._t('customEditorHint')}</p>
            </div>
            <button id="custom-editor-close" class="icon-button">×</button>
          </div>
          ${
            editor.loading
              ? `<div class="loading">${this._t('editorLoading')}</div>`
              : `
            ${editor.originalId ? `<div class="editor-note">${this._t('customIdLocked')} <strong>${esc(editor.originalId)}</strong></div>` : ''}
            ${editor.error ? `<div class="error-box">${esc(editor.error)}</div>` : ''}
            <div class="editor-layout">
              <section class="editor-main">
                <label class="modal-field"><span>${this._t('yamlSource')}</span>
                  <textarea id="custom-yaml" spellcheck="false">${esc(editor.content)}</textarea>
                </label>
              </section>
              <aside class="editor-side">
                <label class="modal-field"><span>${this._t('category')}</span><select id="custom-category">${options}</select></label>
                <label class="check"><input id="custom-enabled" type="checkbox" ${editor.enabled ? 'checked' : ''}><span>${this._t('enabled')}</span></label>
                <label class="check"><input id="custom-auto" type="checkbox" ${editor.autoImport ? 'checked' : ''}><span>${this._t('autoImport')}</span></label>
                <h3>${this._t('testData')}</h3>
                <label class="modal-field"><span>${this._t('testSender')}</span><input id="custom-test-sender" type="text" placeholder="billing@example.com"></label>
                <label class="modal-field"><span>${this._t('testSubject')}</span><input id="custom-test-subject" type="text"></label>
                <label class="modal-field"><span>${this._t('testEmail')}</span><textarea id="custom-test-email" class="test-email"></textarea></label>
                <button id="custom-editor-test" class="secondary" ${editor.testing ? 'disabled' : ''}>${editor.testing ? this._t('validating') : this._t('validateTest')}</button>
                ${result}
              </aside>
            </div>
            <div class="modal-actions">
              <button id="custom-editor-cancel" class="secondary">${this._t('close')}</button>
              <button id="custom-editor-save" class="primary">${this._t('saveCustom')}</button>
            </div>
          `
          }
        </div>
      </div>`
  }

  _readCustomEditorForm() {
    const editor = this._customEditor
    if (!editor) return null
    return {
      content:
        this.shadowRoot.getElementById('custom-yaml')?.value ?? editor.content,
      categoryId:
        this.shadowRoot.getElementById('custom-category')?.value ||
        editor.categoryId,
      enabled: Boolean(
        this.shadowRoot.getElementById('custom-enabled')?.checked,
      ),
      autoImport: Boolean(
        this.shadowRoot.getElementById('custom-auto')?.checked,
      ),
      sender: this.shadowRoot.getElementById('custom-test-sender')?.value || '',
      subject:
        this.shadowRoot.getElementById('custom-test-subject')?.value || '',
      emailText:
        this.shadowRoot.getElementById('custom-test-email')?.value || '',
    }
  }

  async _testCustomEditor() {
    const editor = this._customEditor
    const form = this._readCustomEditorForm()
    if (!editor || !form) return
    editor.content = form.content
    editor.categoryId = form.categoryId
    editor.enabled = form.enabled
    editor.autoImport = form.autoImport
    editor.testing = true
    editor.result = null
    try {
      const result = await this._hass.callWS({
        type: 'bill_tracker/parser/test',
        content: form.content,
        sender: form.sender,
        subject: form.subject,
        email_text: form.emailText,
        documents: {},
      })
      editor.result = {
        ok: true,
        matched: Boolean(result.matched),
        score: result.score ?? 0,
        threshold: result.threshold ?? 0,
        data: result.data || {},
      }
    } catch (error) {
      editor.result = { ok: false, message: errorText(this._hass, error) }
    } finally {
      editor.testing = false
      this._render()
    }
  }

  async _saveCustomEditor() {
    const editor = this._customEditor
    const form = this._readCustomEditorForm()
    if (!editor || !form) return
    editor.content = form.content
    editor.categoryId = form.categoryId
    editor.enabled = form.enabled
    editor.autoImport = form.autoImport
    try {
      await this._hass.callWS({
        type: 'bill_tracker/parser/custom/save',
        content: form.content,
        category_id: form.categoryId,
        enabled: form.enabled,
        auto_import: form.autoImport,
        ...(editor.originalId ? { expected_parser_id: editor.originalId } : {}),
      })
      this._customEditor = null
      await this._load({ refreshIfEmpty: false })
    } catch (error) {
      editor.error = `${this._t('yamlInvalid')}: ${errorText(this._hass, error)}`
      this._render()
    }
  }

  async _exportCustom(row) {
    try {
      const exported = await this._hass.callWS({
        type: 'bill_tracker/parser/custom/export',
        parser_id: String(row.id),
      })
      const raw = atob(exported.content_base64 || '')
      const bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0))
      const content = new TextDecoder().decode(bytes)
      const blob = new Blob([content], {
        type: exported.mime_type || 'application/yaml',
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = exported.filename || `${row.id}.yaml`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      this._error = `${this._t('actionError')}: ${errorText(this._hass, error)}`
      this._render()
    }
  }

  _findRow(id) {
    return this._rows().find((row) => String(row.id) === String(id))
  }

  async _handleAction(action, id) {
    const row = this._findRow(id)
    if (!row) return
    if (action === 'install-replacement') {
      this._openDialog(row, 'install')
      return
    }
    if (action === 'edit-custom') {
      await this._openCustomEditor(row)
      return
    }
    if (action === 'export-custom') {
      await this._exportCustom(row)
      return
    }
    if (action === 'publish') {
      await this._publishCustom(row)
      return
    }
    if (action.startsWith('feedback-')) {
      await this._submitFeedback(row, action.slice('feedback-'.length))
      return
    }
    if (action === 'remove') {
      if (!window.confirm(this._t('confirmRemove'))) return
      this._busy = String(id)
      this._render()
      try {
        const type =
          row.source === 'custom'
            ? 'bill_tracker/parser/custom/delete'
            : 'bill_tracker/parser/uninstall'
        await this._hass.callWS({ type, parser_id: String(id) })
        await this._load({ refreshIfEmpty: false })
      } catch (error) {
        this._error = `${this._t('actionError')}: ${errorText(this._hass, error)}`
      } finally {
        this._busy = ''
        this._render()
      }
      return
    }
    this._openDialog(row, action)
  }

  async _publishCustom(row) {
    try {
      const exported = await this._hass.callWS({
        type: 'bill_tracker/parser/custom/export',
        parser_id: String(row.id),
      })
      const raw = atob(exported.content_base64 || '')
      const bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0))
      const content = new TextDecoder().decode(bytes)
      if (content.length > 24000) {
        window.alert(this._t('publishTooLarge'))
        return
      }
      const submission = {
        schema_version: 2,
        parser_id: String(row.id),
        version: Number(row.version || 1),
        country: String(row.country || '').toUpperCase(),
        provider: String(row.provider || row.name || ''),
        bill_type: String(row.bill_type || ''),
        requested_status: 'experimental',
        billy_version: this._billyVersion(),
      }
      const body = `<!-- billy-parser-submission:v2 -->\n\n${this._t('publishHint')}\n\n\`\`\`json\n${JSON.stringify(submission, null, 2)}\n\`\`\`\n\n\`\`\`yaml\n${content.trim()}\n\`\`\`\n`
      const params = new URLSearchParams({
        title: `[Parser Submission] ${row.id} v${row.version || 1}`,
        body,
      })
      window.open(
        `https://github.com/robin994/billy-parser/issues/new?${params.toString()}`,
        '_blank',
        'noopener,noreferrer',
      )
    } catch (error) {
      this._error = `${this._t('actionError')}: ${errorText(this._hass, error)}`
      this._render()
    }
  }

  async _submitFeedback(row, result) {
    if (!['working', 'partial', 'failed'].includes(result)) return
    try {
      const feedback = await this._hass.callWS({
        type: 'bill_tracker/parser/feedback',
        parser_id: String(row.id),
        result,
      })
      const sourceCommit = String(feedback?.source_commit || '').trim()
      if (!sourceCommit) throw new Error(this._t('feedbackSourceUnknown'))
      feedback.source_commit = sourceCommit
      const version = Number(feedback.version || 0)
      const body = `<!-- billy-parser-feedback:v1 -->\n\n${this._t('feedbackHint')}\n\n\`\`\`json\n${JSON.stringify(feedback, null, 2)}\n\`\`\`\n`
      const params = new URLSearchParams({
        title: `[Parser Feedback] ${row.id} v${version} - ${result}`,
        body,
      })
      window.open(
        `https://github.com/robin994/billy-parser/issues/new?${params.toString()}`,
        '_blank',
        'noopener,noreferrer',
      )
    } catch (error) {
      this._error = `${this._t('actionError')}: ${errorText(this._hass, error)}`
      this._render()
    }
  }

  _openDialog(row, mode) {
    const categories = this._billData?.categories || []
    const payers = (this._billData?.active_payers || []).slice()
    const suggested = row.category_id || row.bill_type
    const defaultCategory = categories.some(
      (item) => String(item.id) === String(suggested),
    )
      ? String(suggested)
      : String(
          categories.find((item) => item.enabled !== false)?.id ||
            categories[0]?.id ||
            '',
        )
    this._dialog = {
      mode,
      row,
      categoryId: defaultCategory,
      enabled: row.installed ? row.enabled !== false : true,
      autoImport: row.installed ? Boolean(row.auto_import) : false,
      defaultPayerId: row.installed ? String(row.default_payer_id || '') : '',
      defaultSplit:
        row.installed && Array.isArray(row.default_split)
          ? row.default_split
          : this._billData?.default_split || [],
      payers,
    }
    this._render()
  }

  _renderDialog() {
    const dialog = this._dialog
    const categories = this._billData?.categories || []
    const payers = dialog.payers || this._billData?.active_payers || []
    const splitMap = new Map(
      (dialog.defaultSplit || []).map((item) => [
        String(item.payer_id || ''),
        Number(item.percentage || 0),
      ]),
    )
    const title =
      dialog.mode === 'install'
        ? this._t('installTitle')
        : dialog.mode === 'update'
          ? this._t('updateTitle')
          : this._t('configureTitle')
    const options = categories
      .map(
        (category) => `
      <option value="${esc(category.id)}" ${String(category.id) === String(dialog.categoryId) ? 'selected' : ''}>
        ${esc(category.name)}${category.enabled === false ? ' · disabled' : ''}
      </option>`,
      )
      .join('')
    return `
      <div class="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <div class="modal-head">
            <div><h2>${title}</h2><p>${esc(dialog.row.provider || dialog.row.name)} · ${esc(dialog.row.id)}</p></div>
            <button id="dialog-close" class="icon-button">×</button>
          </div>
          <label class="modal-field"><span>${this._t('category')}</span><select id="dialog-category">${options}</select></label>
          <label class="modal-field"><span>${this._t('defaultPayer')}</span><select id="dialog-payer"><option value="">${this._t('noDefaultPayer')}</option>${payers.map((payer) => `<option value="${esc(payer.id)}" ${String(payer.id) === String(dialog.defaultPayerId) ? 'selected' : ''}>${esc(payer.name)}</option>`).join('')}</select></label>
          <div class="modal-field"><span>${this._t('defaultSplit')}</span><div class="dialog-split-grid">${payers.map((payer) => `<label><span>${esc(payer.name)}</span><input class="dialog-split" data-payer-id="${esc(payer.id)}" type="number" min="0" max="100" step="0.01" value="${splitMap.get(String(payer.id)) ?? 0}"></label>`).join('')}</div></div>
          <label class="check"><input id="dialog-enabled" type="checkbox" ${dialog.enabled ? 'checked' : ''}><span>${this._t('enabled')}</span></label>
          <label class="check"><input id="dialog-auto" type="checkbox" ${dialog.autoImport ? 'checked' : ''}><span>${this._t('autoImport')}</span></label>
          <div class="modal-actions">
            <button id="dialog-close-secondary" class="secondary">${this._t('close')}</button>
            <button id="dialog-save" class="primary">${dialog.mode === 'install' ? this._t('install') : dialog.mode === 'update' ? this._t('update') : this._t('save')}</button>
          </div>
        </div>
      </div>`
  }

  async _saveDialog() {
    const dialog = this._dialog
    if (!dialog) return
    const categoryId =
      this.shadowRoot.getElementById('dialog-category')?.value ||
      dialog.categoryId
    const enabled = Boolean(
      this.shadowRoot.getElementById('dialog-enabled')?.checked,
    )
    const autoImport = Boolean(
      this.shadowRoot.getElementById('dialog-auto')?.checked,
    )
    const defaultPayerId =
      this.shadowRoot.getElementById('dialog-payer')?.value || ''
    const defaultSplit = [...this.shadowRoot.querySelectorAll('.dialog-split')]
      .map((input) => ({
        payer_id: String(input.dataset.payerId || ''),
        percentage: Number(input.value || 0),
      }))
      .filter((item) => item.payer_id && item.percentage > 0)
    this._busy = String(dialog.row.id)
    this._dialog = null
    this._render()
    try {
      if (dialog.mode === 'configure') {
        await this._hass.callWS({
          type: 'bill_tracker/parser/configure',
          parser_id: String(dialog.row.id),
          category_id: categoryId,
          enabled,
          auto_import: autoImport,
          default_payer_id: defaultPayerId,
          default_split: defaultSplit,
        })
      } else {
        await this._hass.callWS({
          type: 'bill_tracker/parser/install',
          parser_id: String(dialog.row.id),
          category_id: categoryId,
          enabled,
          auto_import: autoImport,
          default_payer_id: defaultPayerId,
          default_split: defaultSplit,
        })
      }
      await this._load({ refreshIfEmpty: false })
    } catch (error) {
      this._error = `${this._t('actionError')}: ${errorText(this._hass, error)}`
    } finally {
      this._busy = ''
      this._render()
    }
  }

  _styles() {
    return `
      :host { display:block; min-height:100%; color:var(--primary-text-color); background:var(--primary-background-color); }
      * { box-sizing:border-box; }
      .page { max-width:1100px; margin:0 auto; padding:24px 20px 48px; }
      header { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:18px; }
      .header-actions { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
      h1 { margin:0 0 6px; font-size:28px; font-weight:600; }
      h2 { margin:0; font-size:20px; }
      p { margin:0; color:var(--secondary-text-color); }
      button, select, input { font:inherit; }
      button { border-radius:10px; border:1px solid var(--divider-color); padding:9px 14px; cursor:pointer; font-weight:600; }
      button:disabled { opacity:.5; cursor:not-allowed; }
      .primary { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
      .secondary { background:var(--card-background-color); color:var(--primary-text-color); }
      .danger { background:transparent; color:var(--error-color, #db4437); border-color:color-mix(in srgb, var(--error-color, #db4437) 45%, transparent); }
      .summary { display:flex; gap:18px; flex-wrap:wrap; align-items:center; padding:12px 14px; margin-bottom:14px; border:1px solid var(--divider-color); border-radius:12px; background:var(--card-background-color); color:var(--secondary-text-color); font-size:14px; }
      .summary strong { color:var(--primary-text-color); }
      .summary-alert { color:var(--warning-color, #f39c12); font-weight:700; }
      .diagnostic-box { display:flex; flex-direction:column; gap:4px; margin-bottom:14px; padding:12px 14px; border:1px solid var(--divider-color); border-radius:11px; background:var(--secondary-background-color); }
      .diagnostic-box strong { font-size:12px; color:var(--primary-text-color); }
      .diagnostic-box span { font-size:12px; color:var(--secondary-text-color); }
      .diagnostic-box small { font-size:11px; color:var(--secondary-text-color); overflow-wrap:anywhere; }
      .filters { display:grid; grid-template-columns:minmax(220px, 1.5fr) repeat(5, minmax(120px, .7fr)); gap:10px; margin-bottom:16px; }
      .filters label, .modal-field { display:flex; flex-direction:column; gap:5px; color:var(--secondary-text-color); font-size:12px; }
      .filters select, .filters input, .modal-field select { width:100%; height:42px; border:1px solid var(--divider-color); border-radius:10px; padding:0 11px; background:var(--card-background-color); color:var(--primary-text-color); }
      .dialog-split-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
      .dialog-split-grid label { display:flex; flex-direction:column; gap:4px; }
      .dialog-split-grid label span { color:var(--secondary-text-color); font-size:11px; }
      .dialog-split-grid input { width:100%; height:38px; border:1px solid var(--divider-color); border-radius:9px; padding:0 9px; background:var(--card-background-color); color:var(--primary-text-color); }
      .search-field { position:relative; justify-content:flex-end; }
      .search-field > span { position:absolute; left:12px; bottom:11px; font-size:18px; }
      .search-field input { padding-left:34px; }
      .list { overflow:hidden; border:1px solid var(--divider-color); border-radius:14px; background:var(--card-background-color); }
      .parser-row { display:flex; justify-content:space-between; gap:20px; padding:17px 18px; border-bottom:1px solid var(--divider-color); }
      .parser-row:last-child { border-bottom:0; }
      .identity { display:flex; gap:13px; min-width:0; }
      .flag { font-size:27px; line-height:1; padding-top:2px; }
      .details { min-width:0; }
      .name-line { display:flex; flex-wrap:wrap; align-items:center; gap:7px; margin-bottom:3px; }
      .name-line strong { font-size:17px; }
      .parser-name { color:var(--primary-text-color); margin-bottom:4px; }
      .meta, .hint { color:var(--secondary-text-color); font-size:13px; overflow-wrap:anywhere; }
      .hint { margin-top:5px; }
      .badge { display:inline-flex; padding:3px 7px; border-radius:999px; font-size:11px; font-weight:700; background:var(--secondary-background-color); color:var(--secondary-text-color); }
      .status-installed { color:var(--success-color, #2e7d32); background:color-mix(in srgb, var(--success-color, #2e7d32) 12%, transparent); }
      .status-available { color:var(--primary-color); background:color-mix(in srgb, var(--primary-color) 12%, transparent); }
      .status-outdated, .warning { color:var(--warning-color, #f39c12); background:color-mix(in srgb, var(--warning-color, #f39c12) 14%, transparent); }
      .status-incompatible, .status-error, .error { color:var(--error-color, #db4437); background:color-mix(in srgb, var(--error-color, #db4437) 12%, transparent); }
      .status-deprecated, .status-removed, .status-custom { color:var(--secondary-text-color); }
      .catalog-verified { color:var(--success-color,#2e7d32); background:color-mix(in srgb,var(--success-color,#2e7d32) 12%,transparent); }
      .catalog-experimental { color:var(--warning-color,#f39c12); background:color-mix(in srgb,var(--warning-color,#f39c12) 14%,transparent); }
      .catalog-outdated { color:var(--error-color,#db4437); background:color-mix(in srgb,var(--error-color,#db4437) 12%,transparent); }
      .catalog-custom { color:var(--secondary-text-color); background:var(--secondary-background-color); }
      .actions { display:flex; align-items:center; justify-content:flex-end; gap:8px; flex-wrap:wrap; flex:0 0 auto; }
      .feedback-actions { width:100%; max-width:330px; margin-top:4px; padding:9px 10px; border:1px solid color-mix(in srgb,var(--warning-color,#f39c12) 32%,var(--divider-color)); border-radius:10px; background:color-mix(in srgb,var(--warning-color,#f39c12) 7%,transparent); }
      .feedback-actions > span { display:block; margin-bottom:7px; color:var(--secondary-text-color); font-size:11px; text-align:right; }
      .feedback-actions > div { display:flex; justify-content:flex-end; gap:5px; flex-wrap:wrap; }
      .feedback-actions button { padding:6px 8px; border-radius:8px; background:var(--card-background-color); color:var(--primary-text-color); font-size:11px; }
      .feedback-working { border-color:color-mix(in srgb,var(--success-color,#2e7d32) 45%,var(--divider-color))!important; }
      .feedback-partial { border-color:color-mix(in srgb,var(--warning-color,#f39c12) 45%,var(--divider-color))!important; }
      .feedback-failed { border-color:color-mix(in srgb,var(--error-color,#db4437) 45%,var(--divider-color))!important; }
      .empty, .loading { padding:36px; text-align:center; color:var(--secondary-text-color); }
      .error-box { margin:0 0 14px; padding:12px 14px; border-radius:10px; color:var(--error-color, #db4437); background:color-mix(in srgb, var(--error-color, #db4437) 10%, transparent); }
      .warning-box { margin:0 0 14px; padding:12px 14px; border-radius:10px; color:var(--warning-color, #f39c12); background:color-mix(in srgb, var(--warning-color, #f39c12) 12%, transparent); }
      .modal-backdrop { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:20px; background:rgba(0,0,0,.48); }
      .modal { width:min(520px, 100%); padding:20px; border-radius:16px; background:var(--card-background-color); box-shadow:var(--ha-card-box-shadow, 0 8px 30px rgba(0,0,0,.3)); }
      .modal-head { display:flex; justify-content:space-between; gap:16px; margin-bottom:20px; }
      .modal-head p { margin-top:4px; font-size:13px; }
      .icon-button { border:0; background:transparent; color:var(--primary-text-color); font-size:25px; padding:0 6px; }
      .check { display:flex; align-items:center; gap:10px; margin-top:16px; }
      .check input { width:18px; height:18px; }
      .modal-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:24px; }
      .custom-editor-backdrop { align-items:flex-start; overflow:auto; }
      .custom-editor-modal { width:min(1120px, 100%); margin:24px 0; }
      .editor-layout { display:grid; grid-template-columns:minmax(0, 1.7fr) minmax(280px, .8fr); gap:18px; }
      .editor-main textarea { width:100%; min-height:570px; resize:vertical; border:1px solid var(--divider-color); border-radius:10px; padding:12px; background:var(--code-editor-background-color, var(--secondary-background-color)); color:var(--primary-text-color); font:13px/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; tab-size:2; }
      .editor-side { display:flex; flex-direction:column; gap:12px; }
      .editor-side h3 { margin:8px 0 0; font-size:15px; }
      .editor-side .modal-field input, .editor-side .modal-field textarea { width:100%; border:1px solid var(--divider-color); border-radius:10px; padding:9px 10px; background:var(--card-background-color); color:var(--primary-text-color); font:inherit; }
      .editor-side .test-email { min-height:120px; resize:vertical; }
      .editor-note { margin-bottom:14px; padding:10px 12px; border-radius:10px; color:var(--secondary-text-color); background:var(--secondary-background-color); font-size:13px; }
      .test-result { display:flex; flex-direction:column; gap:5px; padding:10px 12px; border-radius:10px; font-size:13px; overflow:auto; }
      .test-result pre { max-height:180px; overflow:auto; margin:5px 0 0; white-space:pre-wrap; word-break:break-word; }
      .test-ok { color:var(--success-color,#2e7d32); background:color-mix(in srgb,var(--success-color,#2e7d32) 10%,transparent); }
      .test-error { color:var(--error-color,#db4437); background:color-mix(in srgb,var(--error-color,#db4437) 10%,transparent); }
      @media (max-width: 800px) {
        .page { padding:16px 10px 32px; }
        header { align-items:stretch; flex-direction:column; }
        header button { align-self:flex-start; }
        .header-actions { justify-content:flex-start; }
        .editor-layout { grid-template-columns:1fr; }
        .editor-main textarea { min-height:430px; }
        .filters { grid-template-columns:1fr 1fr; }
        .search-field { grid-column:1 / -1; }
        .parser-row { flex-direction:column; }
        .actions { justify-content:flex-start; padding-left:40px; }
        .feedback-actions { max-width:none; }
        .feedback-actions > span { text-align:left; }
        .feedback-actions > div { justify-content:flex-start; }
      }
      @media (max-width: 480px) {
        .filters { grid-template-columns:1fr; }
        .search-field { grid-column:auto; }
        .actions { padding-left:0; }
      }
    `
  }
}

if (!customElements.get('billy-parser-manager')) {
  customElements.define('billy-parser-manager', BillyParserManagerPanel)
}

console.info(`Billy parser manager v${BILLY_PARSER_MANAGER_VERSION} loaded`)
