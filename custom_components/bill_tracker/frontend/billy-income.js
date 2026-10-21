// Billy income management. Optional, independent from bills and banking.
import './billy-accounts.js?v=0.16.0-r1'
// The IDs and persisted English names stay stable across language changes.
// Only built-in categories that still have their original name are translated.
const DEFAULT_INCOME_CATEGORY_NAMES = {
  salary: { en: 'Salary', it: 'Stipendio', es: 'Sueldo', fr: 'Salaire', de: 'Gehalt', pt: 'Salário' },
  pension: { en: 'Pension', it: 'Pensione', es: 'Pensión', fr: 'Pension', de: 'Rente', pt: 'Pensão' },
  rent: { en: 'Rental income', it: 'Entrate da affitto', es: 'Ingresos por alquiler', fr: 'Revenus locatifs', de: 'Mieteinnahmen', pt: 'Rendimentos de aluguer' },
  bonus: { en: 'Bonus', it: 'Premi e bonus', es: 'Primas y bonus', fr: 'Primes et bonus', de: 'Prämien und Boni', pt: 'Prémios e bónus' },
  refund: { en: 'External refund', it: 'Rimborso esterno', es: 'Reembolso externo', fr: 'Remboursement externe', de: 'Externe Rückerstattung', pt: 'Reembolso externo' },
  other: { en: 'Other income', it: 'Altre entrate', es: 'Otros ingresos', fr: 'Autres revenus', de: 'Sonstige Einnahmen', pt: 'Outros rendimentos' },
}
const TRANSLATIONS = {
  en: {
    title: 'Income', subtitle: 'Track received income and recurring estimates, without bank connections.',
    rulesSubtitle: 'Manage recurring income plans and estimated future receipts.',
    add: 'Add income', recurring: 'Recurring income', categories: 'Income categories',
    oneTime: 'Income entries', planned: 'Recurring plans', received: 'Received', pending: 'Expected',
    yearly: 'Received this year', monthly: 'Received this month', expected: 'Expected this month',
    empty: 'No income entries yet.', noRules: 'No recurring income plans configured.',
    name: 'Description', category: 'Category', estimated: 'Estimated amount',
    actual: 'Actual amount received', expectedDate: 'Expected date', receivedDate: 'Received date',
    confirm: 'Received (confirmed)', note: 'Note', save: 'Save', cancel: 'Cancel',
    edit: 'Edit', remove: 'Delete', period: 'Frequency', start: 'Start date', end: 'End date (optional)',
    mode: 'Future estimate', fixed: 'Fixed estimate', last: 'Last confirmed amount',
    average3: 'Average of last 3', average6: 'Average of last 6', average12: 'Average of last 12',
    active: 'Active recurring income', every: 'Every {n} month(s)',
    valueHint: 'Each occurrence can be corrected after payment, without changing other months.',
    incomeHint: 'Pending income does not count as received. Enter the actual net amount when you confirm it.',
    confirmDelete: 'Delete this income entry?', confirmRuleDelete: 'Delete this recurring plan? Past entries are kept.',
    confirmCategoryDelete: 'Delete this category?', catName: 'Category name', color: 'Color',
    newCategory: 'Create category', categoryInUse: 'A category with recorded income cannot be deleted.',
    editCategory: 'Edit category', failed: 'Operation failed', search: 'Search income...',
    all: 'All', rows: 'entries', next: 'Next', previous: 'Previous', noData: 'No matching income.',
    forecast: 'Forecast', receivedOn: 'Received on', categoryMissing: 'Create an income category first.',
    accounts: 'Accounts',
    account: 'Account',
    accounts: 'Accounts', checking: 'Checking Account', savings: 'Savings Account',
    totalBalance: 'Total tracked balance', openingBalance: 'Opening balance',
    openingDate: 'Opening balance date', configureAccounts: 'Set opening balances',
    editAccounts: 'Edit opening balances', saveAccounts: 'Save opening balances',
    unconfiguredAccounts: 'Set the starting balance of Checking and Savings to start tracking your cash position.',
    accountHelp: 'Only confirmed income and paid bills change Checking. Savings changes only through internal transfers. Pending bills, projected income, recurring expense schedules and reimbursements do not change these balances.',
    openingHelp: 'Balances are entered at the beginning of this date. Earlier transactions are already included in the opening amounts.',
    internalTransfer: 'Internal transfer', transferHistory: 'Internal transfers',
    transferHelp: 'A transfer moves money between your two accounts; it never creates income or an expense.',
    sourceAccount: 'From account', destinationAccount: 'To account',
    transferDate: 'Transfer date', transferAmount: 'Amount',
    transferTo: 'To {account}', newTransfer: 'Transfer money',
    transferEmpty: 'No internal transfers recorded.',
    confirmTransferDelete: 'Delete this internal transfer? The balances will be recalculated.',
    noBank: 'Manual balances only. Billy never connects to your bank.',
  },
  it: {
    title: 'Entrate', subtitle: 'Registra incassi e previsioni ricorrenti, senza collegamenti bancari.',
    rulesSubtitle: 'Gestisci le entrate ricorrenti e gli incassi futuri stimati.',
    add: 'Aggiungi entrata', recurring: 'Entrate ricorrenti', categories: 'Tipi di entrata',
    oneTime: 'Movimenti', planned: 'Piani ricorrenti', received: 'Incassato', pending: 'Previsto',
    yearly: 'Incassato quest’anno', monthly: 'Incassato questo mese', expected: 'Previsto questo mese',
    empty: 'Nessuna entrata registrata.', noRules: 'Nessuna entrata ricorrente configurata.',
    name: 'Descrizione', category: 'Categoria', estimated: 'Importo previsto',
    actual: 'Importo netto effettivo', expectedDate: 'Data prevista', receivedDate: 'Data accredito',
    confirm: 'Incassato (confermato)', note: 'Nota', save: 'Salva', cancel: 'Annulla',
    edit: 'Modifica', remove: 'Elimina', period: 'Frequenza', start: 'Data inizio', end: 'Data fine (opzionale)',
    mode: 'Stima dei mesi futuri', fixed: 'Stima fissa', last: 'Ultimo importo incassato',
    average3: 'Media ultimi 3', average6: 'Media ultimi 6', average12: 'Media ultimi 12',
    active: 'Entrata ricorrente attiva', every: 'Ogni {n} mesi',
    valueHint: 'Ogni mensilità può essere corretta dopo l’accredito senza modificare gli altri mesi.',
    incomeHint: 'Le entrate previste non sono considerate incassate. Conferma il netto reale quando arriva.',
    confirmDelete: 'Eliminare questa entrata?', confirmRuleDelete: 'Eliminare la ricorrenza? Lo storico resta disponibile.',
    confirmCategoryDelete: 'Eliminare la categoria?', catName: 'Nome categoria', color: 'Colore',
    newCategory: 'Crea categoria', categoryInUse: 'Una categoria con entrate registrate non si può eliminare.',
    editCategory: 'Modifica categoria', failed: 'Operazione non riuscita', search: 'Cerca entrate...',
    all: 'Tutte', rows: 'movimenti', next: 'Successiva', previous: 'Precedente', noData: 'Nessuna entrata corrisponde ai filtri.',
    forecast: 'Previsione', receivedOn: 'Incassato il', categoryMissing: 'Crea prima una categoria di entrata.',
    accounts: 'Conti',
    account: 'Conto',
    accounts: 'Conti', checking: 'Conto corrente', savings: 'Conto risparmio',
    totalBalance: 'Patrimonio monitorato', openingBalance: 'Saldo iniziale',
    openingDate: 'Data saldo iniziale', configureAccounts: 'Imposta saldi iniziali',
    editAccounts: 'Modifica saldi iniziali', saveAccounts: 'Salva saldi iniziali',
    unconfiguredAccounts: 'Inserisci i saldi iniziali del conto corrente e del conto risparmio per iniziare a monitorarli.',
    accountHelp: 'Solo le entrate confermate e le bollette pagate modificano il conto corrente. Il risparmio cambia solo tramite giroconti. Le previsioni, le spese ricorrenti non confermate e i rimborsi non vengono conteggiati.',
    openingHelp: 'I saldi si riferiscono all’inizio di questa data. Le transazioni precedenti sono già comprese nei saldi iniziali.',
    internalTransfer: 'Giroconto', transferHistory: 'Storico giroconti',
    transferHelp: 'Un giroconto sposta denaro fra i due conti e non crea entrate o spese.',
    sourceAccount: 'Dal conto', destinationAccount: 'Al conto',
    transferDate: 'Data giroconto', transferAmount: 'Importo',
    transferTo: 'Verso {account}', newTransfer: 'Registra giroconto',
    transferEmpty: 'Nessun giroconto registrato.',
    confirmTransferDelete: 'Eliminare questo giroconto? I saldi saranno ricalcolati.',
    noBank: 'Solo saldi manuali. Billy non si collega alla banca.',
  },
}
function html(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;')
}
function safeColor(value) {
  return /^#[0-9a-fA-F]{6}$/.test(String(value || '')) ? value : '#6B8394'
}
function todayIso() {
  const date = new Date()
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-')
}

class BillyIncome extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._hass = null
    this._data = null
    this._error = ''
    this._loading = false
    this._unsubscribe = null
    this._mode = 'entries'
    this._query = ''
    this._status = 'all'
    this._page = 0
  }
  static get observedAttributes() { return ['mode'] }
  attributeChangedCallback(name, previous, next) {
    if (name !== 'mode' || previous === next) return
    this._mode = next === 'rules' ? 'rules' : 'entries'
    if (this._data) this._render()
  }
  set hass(value) {
    const changed = this._hass?.connection && this._hass.connection !== value?.connection
    const initial = !this._hass
    this._hass = value
    if (!this.isConnected) return
    if (changed) { this._unsubscribe?.(); this._unsubscribe = null }
    if (initial || changed) this._subscribe()
    if (initial || changed || !this._data) this._load()
  }
  get hass() { return this._hass }
  connectedCallback() { this._subscribe(); this._load() }
  disconnectedCallback() { this._unsubscribe?.(); this._unsubscribe = null }
  _language() {
    return String(this._hass?.language || 'en').split(/[-_]/)[0].toLowerCase()
  }
  _t(key, vars = {}) {
    const language = this._language()
    let text = (TRANSLATIONS[language] || TRANSLATIONS.en)[key] || TRANSLATIONS.en[key] || key
    for (const [name, value] of Object.entries(vars)) text = text.replaceAll(`{${name}}`, String(value))
    return text
  }
  _money(number) {
    try {
      return new Intl.NumberFormat(this._hass?.locale?.language || 'en', {
        style: 'currency', currency: this._data?.currency || 'EUR',
      }).format(Number(number || 0))
    } catch (_error) { return `${Number(number || 0).toFixed(2)} ${this._data?.currency || 'EUR'}` }
  }
  async _subscribe() {
    if (!this._hass || this._unsubscribe) return
    try {
      this._unsubscribe = await this._hass.connection.subscribeEvents(() => this._load(false), 'bill_tracker_updated')
    } catch (_error) {}
  }
  async _load(showLoading = true) {
    if (!this._hass || this._loading) return
    if (showLoading) this._loading = true
    if (showLoading) this._render()
    try {
      this._data = await this._hass.callWS({ type: 'bill_tracker/list', forecast_months: 12 })
      this._error = ''
    } catch (error) { this._error = error?.message || String(error) }
    finally { this._loading = false; this._render() }
  }
  async _request(payload) {
    try {
      await this._hass.callWS(payload)
      this._error = ''
      await this._load(false)
      return true
    } catch (error) {
      this._error = error?.message || String(error)
      this._render()
      return false
    }
  }
  _cat(id) {
    return (this._data?.income_categories || []).find((item) => item.id === id)
  }
  _categoryName(category) {
    if (!category) return ''
    const labels = DEFAULT_INCOME_CATEGORY_NAMES[category.id]
    return labels && category.name === labels.en
      ? (labels[this._language()] || labels.en)
      : (category.name || '')
  }
  _categoryOptions(selected) {
    return (this._data?.income_categories || []).map((item) =>
      `<option value="${html(item.id)}" ${item.id === selected ? 'selected' : ''}>${html(this._categoryName(item))}</option>`
    ).join('')
  }
  _accountOptions(selected) {
    const accounts = this._data?.accounts || []
    const active = selected || this._data?.default_account_id
    return accounts.map((account) =>
      `<option value="${html(account.id)}" ${account.id === active ? 'selected' : ''}>${html(account.name)}</option>`
    ).join('')
  }
  _filtered() {
    return (this._data?.incomes || []).filter((row) => {
      if (this._status !== 'all' && (row.received ? 'received' : 'pending') !== this._status) return false
      if (!this._query) return true
      const category = this._cat(row.category_id)
      const names = `${this._categoryName(category)} ${category?.name || ''}`
      return `${row.description} ${row.note} ${names}`.toLowerCase().includes(this._query.toLowerCase())
    })
  }
  _rows() {
    const matched = this._filtered()
    const count = matched.length
    const totalPages = Math.max(1, Math.ceil(count / 25))
    this._page = Math.min(this._page, totalPages - 1)
    const rows = matched.slice(this._page * 25, (this._page + 1) * 25)
    return `<div class="rows">${rows.map((row) => {
      const category = this._cat(row.category_id)
      return `<article class="entry">
        <span class="category-dot" style="background:${safeColor(category?.color)}"></span>
        <div class="main"><strong>${html(row.description)}</strong><small>${html(this._categoryName(category))} · ${html((this._data?.accounts || []).find((item) => item.id === row.account_id)?.name || '')} · ${html(row.expected_date)}</small>
          ${row.note ? `<small>${html(row.note)}</small>` : ''}</div>
        <div class="amount"><strong>${html(this._money(row.received ? row.actual_amount : row.estimated_amount))}</strong>
          <small>${html(this._t(row.received ? 'received' : 'pending'))}</small>
          ${row.received && row.actual_amount !== row.estimated_amount ? `<small>${html(this._t('forecast'))}: ${html(this._money(row.estimated_amount))}</small>` : ''}
          ${row.received_date ? `<small>${html(this._t('receivedOn'))}: ${html(row.received_date)}</small>` : ''}
        </div>
        <div class="actions">
          <button data-edit="${html(row.id)}">${html(this._t('edit'))}</button>
          <button class="danger" data-delete="${html(row.id)}">${html(this._t('remove'))}</button>
        </div>
      </article>`
    }).join('') || `<div class="empty">${html(this._t('noData'))}</div>`}</div>
    <div class="pager"><span>${count} ${html(this._t('rows'))}</span>
      <button data-prev ${this._page === 0 ? 'disabled' : ''}>${html(this._t('previous'))}</button>
      <button data-next ${this._page >= totalPages - 1 ? 'disabled' : ''}>${html(this._t('next'))}</button>
    </div>`
  }
  _rules() {
    const rules = this._data?.income_rules || []
    return `<div class="rows">${rules.map((row) => `<article class="entry">
      <span class="category-dot" style="background:${safeColor(this._cat(row.category_id)?.color)}"></span>
      <div class="main"><strong>${html(row.name)}</strong>
        <small>${html(this._categoryName(this._cat(row.category_id)))} · ${html(this._t('every', { n: row.interval_months }))}</small>
        <small>${html(row.start_date)} ${row.end_date ? '– ' + html(row.end_date) : ''}</small></div>
      <div class="amount"><strong>${html(this._money(row.estimated_amount))}</strong>
        <small>${html(this._t(row.amount_mode))}</small>
        <small>${html(this._t(row.active ? 'active' : 'pending'))}</small></div>
      <div class="actions"><button data-edit-rule="${html(row.id)}">${html(this._t('edit'))}</button>
        <button class="danger" data-delete-rule="${html(row.id)}">${html(this._t('remove'))}</button></div>
    </article>`).join('') || `<div class="empty">${html(this._t('noRules'))}</div>`}</div>`
  }
  _render() {
    if (!this._data && this._loading) {
      this.shadowRoot.innerHTML = `<style>${this._styles()}</style><div class="shell">${html(this._t('title'))}…</div>`
      return
    }
    const sum = this._data?.income_summary || {}
    const rules = this._mode === 'rules'
    this.shadowRoot.innerHTML = `<style>${this._styles()}</style><div class="shell">
      <header><div><h1>${html(this._t(rules ? 'recurring' : 'title'))}</h1><p>${html(this._t(rules ? 'rulesSubtitle' : 'subtitle'))}</p></div>
        <div class="actions head-actions">
          ${rules ? `<button class="primary" id="new-rule">${html(this._t('recurring'))}</button>` : `<button class="primary" id="add">${html(this._t('add'))}</button>`}
          <button id="categories">${html(this._t('categories'))}</button>
        </div></header>
      ${this._error ? `<div class="error" role="alert">${html(this._error)}</div>` : ''}
      ${rules ? '' : `<div class="stats">
        <article><span>${html(this._t('monthly'))}</span><strong>${html(this._money(sum.month_received))}</strong></article>
        <article><span>${html(this._t('expected'))}</span><strong>${html(this._money(sum.month_pending))}</strong></article>
        <article><span>${html(this._t('yearly'))}</span><strong>${html(this._money(sum.year_received))}</strong></article>
      </div>
      <p class="hint">${html(this._t('incomeHint'))}</p>`}
      <div class="content">${!rules
        ? `<div class="filters"><input id="search" placeholder="${html(this._t('search'))}" value="${html(this._query)}">
          <select id="status"><option value="all">${html(this._t('all'))}</option>
            <option value="received" ${this._status === 'received' ? 'selected' : ''}>${html(this._t('received'))}</option>
            <option value="pending" ${this._status === 'pending' ? 'selected' : ''}>${html(this._t('pending'))}</option>
          </select></div><div id="list">${this._rows()}</div>`
        : this._rules()}</div>
      <div id="modal" class="modal" hidden><div class="backdrop"></div><div id="dialog" class="dialog"></div></div>
    </div>`
    this._wire()
  }
  _wireRows() {
    for (const el of this.shadowRoot.querySelectorAll('[data-edit]')) el.addEventListener('click', () => this._openIncome(el.dataset.edit))
    for (const el of this.shadowRoot.querySelectorAll('[data-delete]')) el.addEventListener('click', async () => {
      if (window.confirm(this._t('confirmDelete'))) await this._request({ type: 'bill_tracker/income/delete', income_id: el.dataset.delete })
    })
    for (const el of this.shadowRoot.querySelectorAll('[data-edit-rule]')) el.addEventListener('click', () => this._openRule(el.dataset.editRule))
    for (const el of this.shadowRoot.querySelectorAll('[data-delete-rule]')) el.addEventListener('click', async () => {
      if (window.confirm(this._t('confirmRuleDelete'))) await this._request({ type: 'bill_tracker/income/rule/delete', rule_id: el.dataset.deleteRule })
    })
    this.shadowRoot.querySelector('[data-prev]')?.addEventListener('click', () => { this._page--; this._render() })
    this.shadowRoot.querySelector('[data-next]')?.addEventListener('click', () => { this._page++; this._render() })
  }
  _wire() {
    this.shadowRoot.getElementById('add')?.addEventListener('click', () => this._openIncome())
    this.shadowRoot.getElementById('new-rule')?.addEventListener('click', () => this._openRule())
    this.shadowRoot.getElementById('categories')?.addEventListener('click', () => this._openCategories())
    this.shadowRoot.getElementById('search')?.addEventListener('input', (event) => {
      this._query = event.target.value; this._page = 0
      this.shadowRoot.getElementById('list').innerHTML = this._rows()
      this._wireRows()
    })
    this.shadowRoot.getElementById('status')?.addEventListener('change', (event) => {
      this._status = event.target.value; this._page = 0
      this.shadowRoot.getElementById('list').innerHTML = this._rows()
      this._wireRows()
    })
    this._wireRows()
  }
  _modal(markup, submit) {
    const modal = this.shadowRoot.getElementById('modal')
    if (!modal) return
    modal.querySelector('#dialog').innerHTML = markup
    modal.hidden = false
    const close = () => { modal.hidden = true }
    modal.querySelector('.backdrop').onclick = close
    modal.querySelector('[data-close]')?.addEventListener('click', close)
    modal.querySelector('form')?.addEventListener('submit', async (event) => {
      event.preventDefault()
      const success = await submit(new FormData(event.currentTarget), event.currentTarget)
      if (success) close()
    })
  }
  _openIncome(id = null) {
    const row = (this._data?.incomes || []).find((item) => item.id === id)
    const date = row?.expected_date || todayIso()
    if (!(this._data?.income_categories || []).length) { this._error = this._t('categoryMissing'); this._render(); return }
    this._modal(`<form><h2>${html(this._t(row ? 'edit' : 'add'))}</h2>
      <div class="fields">
        <label>${html(this._t('name'))}<input name="description" required maxlength="120" value="${html(row?.description || '')}"></label>
        <label>${html(this._t('category'))}<select name="category_id">${this._categoryOptions(row?.category_id)}</select></label>
        ${(this._data?.accounts || []).length
          ? `<label>${html(this._t('account'))}<select name="account_id" required>${this._accountOptions(row?.account_id)}</select></label>`
          : ''}
        <label>${html(this._t('expectedDate'))}<input name="expected_date" type="date" required value="${html(date)}" ${row?.rule_id ? 'readonly' : ''}></label>
        <label>${html(this._t('estimated'))}<input name="estimated_amount" type="number" min="0" step="0.01" required value="${html(row?.estimated_amount ?? '')}"></label>
        <label class="check"><input name="received" id="income-received" type="checkbox" ${row?.received ? 'checked' : ''}>${html(this._t('confirm'))}</label>
        <label>${html(this._t('actual'))}<input name="actual_amount" type="number" min="0" step="0.01" placeholder="${html(this._t('estimated'))}" value="${html(row?.actual_amount ?? '')}"></label>
        <label>${html(this._t('receivedDate'))}<input name="received_date" type="date" value="${html(row?.received_date || '')}"></label>
        <label class="span2">${html(this._t('note'))}<textarea name="note" rows="3">${html(row?.note || '')}</textarea></label>
      </div><p class="hint">${html(this._t('valueHint'))}</p>
      <div class="modal-actions"><button type="button" data-close>${html(this._t('cancel'))}</button>
        <button type="submit" class="primary">${html(this._t('save'))}</button></div></form>`, async (data) => {
      const payload = {
        type: row ? 'bill_tracker/income/update' : 'bill_tracker/income/add',
        ...(row ? { income_id: row.id } : {}),
        description: String(data.get('description') || '').trim(),
        category_id: String(data.get('category_id') || ''),
        expected_date: String(data.get('expected_date') || ''),
        estimated_amount: Number(data.get('estimated_amount')),
        received: data.get('received') === 'on',
        received_date: String(data.get('received_date') || ''),
        note: String(data.get('note') || ''),
      }
      if (data.get('account_id')) payload.account_id = String(data.get('account_id'))
      const actual = String(data.get('actual_amount') || '').trim()
      if (actual !== '') payload.actual_amount = Number(actual)
      return this._request(payload)
    })
  }
  _openRule(id = null) {
    const row = (this._data?.income_rules || []).find((item) => item.id === id)
    if (!(this._data?.income_categories || []).length) { this._error = this._t('categoryMissing'); this._render(); return }
    this._modal(`<form><h2>${html(this._t('recurring'))}</h2><div class="fields">
      <label>${html(this._t('name'))}<input name="name" required maxlength="120" value="${html(row?.name || '')}"></label>
      <label>${html(this._t('category'))}<select name="category_id">${this._categoryOptions(row?.category_id)}</select></label>
      ${(this._data?.accounts || []).length
        ? `<label>${html(this._t('account'))}<select name="account_id" required>${this._accountOptions(row?.account_id)}</select></label>`
        : ''}
      <label>${html(this._t('estimated'))}<input name="estimated_amount" type="number" min="0" step="0.01" required value="${html(row?.estimated_amount ?? '')}"></label>
      <label>${html(this._t('period'))}<select name="interval_months">${[1, 2, 3, 4, 6, 12].map((n) =>
        `<option value="${n}" ${Number(row?.interval_months || 1) === n ? 'selected' : ''}>${html(this._t('every', { n }))}</option>`).join('')}</select></label>
      <label>${html(this._t('mode'))}<select name="amount_mode">${['fixed', 'last', 'average3', 'average6', 'average12'].map((mode) =>
        `<option value="${mode}" ${(row?.amount_mode || 'fixed') === mode ? 'selected' : ''}>${html(this._t(mode))}</option>`).join('')}</select></label>
      <label>${html(this._t('start'))}<input name="start_date" type="date" required value="${html(row?.start_date || todayIso())}"></label>
      <label>${html(this._t('end'))}<input name="end_date" type="date" value="${html(row?.end_date || '')}"></label>
      <label class="check"><input name="active" type="checkbox" ${row?.active !== false ? 'checked' : ''}>${html(this._t('active'))}</label>
      <label class="span2">${html(this._t('note'))}<textarea name="note" rows="3">${html(row?.note || '')}</textarea></label>
    </div><p class="hint">${html(this._t('valueHint'))}</p>
    <div class="modal-actions"><button type="button" data-close>${html(this._t('cancel'))}</button>
      <button type="submit" class="primary">${html(this._t('save'))}</button></div></form>`, async (data) => this._request({
      type: row ? 'bill_tracker/income/rule/update' : 'bill_tracker/income/rule/add',
      ...(row ? { rule_id: row.id } : {}),
      name: String(data.get('name') || '').trim(),
      category_id: String(data.get('category_id') || ''),
      estimated_amount: Number(data.get('estimated_amount')),
      interval_months: Number(data.get('interval_months')),
      start_date: String(data.get('start_date') || ''),
      end_date: String(data.get('end_date') || ''),
      amount_mode: String(data.get('amount_mode') || 'fixed'),
      active: data.get('active') === 'on',
      note: String(data.get('note') || ''),
      ...(data.get('account_id') ? { account_id: String(data.get('account_id')) } : {}),
    }))
  }
  _openCategories() {
    const categories = this._data?.income_categories || []
    this._modal(`<form><h2>${html(this._t('categories'))}</h2>
      <div class="cat-list">${categories.map((cat) => `<div class="cat">
        <span class="category-dot" style="background:${safeColor(cat.color)}"></span><strong>${html(this._categoryName(cat))}</strong>
        <button type="button" data-cat-edit="${html(cat.id)}">${html(this._t('edit'))}</button>
        <button type="button" class="danger" data-cat-delete="${html(cat.id)}">${html(this._t('remove'))}</button>
      </div>`).join('')}</div>
      <div class="fields">
        <label>${html(this._t('catName'))}<input name="name" required maxlength="80"></label>
        <label>${html(this._t('color'))}<input name="color" type="color" value="#6B8394"></label>
      </div>
      <div class="modal-actions"><button type="button" data-close>${html(this._t('cancel'))}</button>
        <button type="submit" class="primary">${html(this._t('newCategory'))}</button></div>
    </form>`, async (data) => this._request({
      type: 'bill_tracker/income/category/add',
      name: String(data.get('name') || '').trim(),
      color: String(data.get('color') || '#6B8394'),
    }))
    for (const button of this.shadowRoot.querySelectorAll('[data-cat-edit]')) button.addEventListener('click', () => {
      const cat = this._cat(button.dataset.catEdit)
      this._modal(`<form><h2>${html(this._t('editCategory'))}</h2>
        <div class="fields"><label>${html(this._t('catName'))}<input name="name" value="${html(this._categoryName(cat))}" required></label>
          <label>${html(this._t('color'))}<input name="color" type="color" value="${safeColor(cat.color)}"></label></div>
        <div class="modal-actions"><button type="button" data-close>${html(this._t('cancel'))}</button>
          <button type="submit" class="primary">${html(this._t('save'))}</button></div></form>`,
      async (data) => this._request({
        type: 'bill_tracker/income/category/update', category_id: cat.id,
        // Editing only the color must not persist a translated display label.
        name: String(data.get('name') || '').trim() === this._categoryName(cat)
          ? cat.name : String(data.get('name') || '').trim(),
        color: String(data.get('color') || '#6B8394'),
      }))
    })
    for (const button of this.shadowRoot.querySelectorAll('[data-cat-delete]')) button.addEventListener('click', async () => {
      if (window.confirm(this._t('confirmCategoryDelete'))) {
        await this._request({ type: 'bill_tracker/income/category/delete', category_id: button.dataset.catDelete })
      }
    })
  }
  _styles() {
    return `
      :host{display:block;color:var(--primary-text-color)}*{box-sizing:border-box}
      .shell{display:flex;flex-direction:column;gap:18px}
      header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:18px}
      header h1{font-size:30px;margin:0 0 5px}header p,.hint{font-size:13px;color:var(--secondary-text-color);margin:0}
      .actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
      button{appearance:none;border:1px solid var(--divider-color);border-radius:9px;padding:9px 12px;font:inherit;font-weight:600;cursor:pointer;color:var(--primary-text-color);background:var(--card-background-color)}
      button:disabled{opacity:.35;cursor:not-allowed}.primary{background:var(--primary-color);color:white;border-color:var(--primary-color)}
      .danger{color:var(--error-color,#d32f2f)}
      .stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
      .stats article,.content{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:15px;padding:18px}
      .stats article span{color:var(--secondary-text-color);font-size:12px;display:block;margin-bottom:9px}
      .stats article strong{font-size:23px}
      nav{display:flex;gap:8px;border-bottom:1px solid var(--divider-color);padding-bottom:13px;margin-bottom:15px}
      nav button.active{border-color:var(--primary-color);color:var(--primary-color)}
      .filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
      .filters input{flex:1;min-width:180px}
      input,select,textarea{font:inherit;background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:9px;padding:10px;min-height:42px}
      .entry{display:grid;grid-template-columns:10px minmax(150px,1fr) minmax(130px,auto) auto;gap:16px;align-items:center;padding:15px 6px;border-top:1px solid var(--divider-color)}
      .entry:first-child{border-top:0}.category-dot{display:block;width:10px;height:10px;border-radius:50%}
      .main,.amount{display:flex;flex-direction:column;gap:5px;min-width:0}
      .main strong{overflow-wrap:anywhere}.main small,.amount small{font-size:12px;color:var(--secondary-text-color)}
      .amount strong{font-size:17px}.pager{display:flex;align-items:center;gap:10px;justify-content:flex-end;padding-top:15px}
      .pager span{margin-right:auto;font-size:12px;color:var(--secondary-text-color)}
      .error{border:1px solid var(--error-color,#d32f2f);color:var(--error-color,#d32f2f);border-radius:10px;padding:12px}
      .empty{text-align:center;padding:45px;color:var(--secondary-text-color)}
      .modal[hidden]{display:none}.modal{position:fixed;inset:0;z-index:10000;display:grid;place-items:center;padding:18px}
      .backdrop{position:absolute;inset:0;background:rgba(0,0,0,.6)}
      .dialog{position:relative;z-index:1;background:var(--card-background-color);border-radius:16px;padding:24px;width:min(720px,100%);max-height:90vh;overflow:auto;box-shadow:0 18px 50px rgba(0,0,0,.3)}
      .dialog h2{margin:0 0 20px;font-size:22px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:15px}
      .fields label{font-size:13px;color:var(--secondary-text-color);display:flex;flex-direction:column;gap:6px}
      .fields input,.fields select,.fields textarea{width:100%;min-width:0}
      .fields .span2{grid-column:1/-1}.fields .check{flex-direction:row;align-items:center}
      .check input{width:17px;min-height:17px;accent-color:var(--primary-color)}
      .modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}
      .cat-list{max-height:240px;overflow:auto;margin-bottom:16px}.cat{display:flex;align-items:center;gap:10px;margin-bottom:7px}
      .cat strong{margin-right:auto}.cat button{padding:6px 9px}
      @media(max-width:780px){.stats{grid-template-columns:1fr}.entry{grid-template-columns:10px minmax(0,1fr)}.entry .amount,.entry .actions{grid-column:2}.fields{grid-template-columns:1fr}.fields .span2{grid-column:auto}.head-actions{width:100%}.dialog{padding:16px}}
    `
  }
}
if (!customElements.get('billy-income')) customElements.define('billy-income', BillyIncome)
