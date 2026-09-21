const HISTORY_TEXT = {
  en: {
    title: 'Reimbursement history',
    help: 'Review completed and pending reimbursements, when they were recorded and the items included in each transfer.',
    all: 'All reimbursements',
    completed: 'Completed',
    pending: 'Pending',
    allPayers: 'All payers',
    allYears: 'All years',
    completedCount: 'Completed reimbursements',
    completedTotal: 'Reimbursed total',
    pendingTotal: 'Still pending',
    notDone: 'Not completed yet',
    dateUnknown: 'Completion date unavailable',
    items: 'Items',
    open: 'Open details',
    empty: 'No reimbursements match the selected filters.',
    details: 'Reimbursement details',
    status: 'Status',
    when: 'When',
    amount: 'Amount',
    bill: 'Bill',
    recurring: 'Recurring expense',
    legacy: 'This older reimbursement predates itemized amounts; the items are known but their individual reimbursed amount was not stored.',
    unavailable: 'The original item details are no longer available.',
    undo: 'Undo reimbursement',
    cancel: 'Close',
    loading: 'Loading…',
    error: 'Error',
    retry: 'Retry',
  },
  it: {
    title: 'Storico rimborsi',
    help: 'Consulta rimborsi completati e ancora pendenti, quando sono stati registrati e quali voci comprende ogni trasferimento.',
    all: 'Tutti i rimborsi',
    completed: 'Completati',
    pending: 'Da rimborsare',
    allPayers: 'Tutti i paganti',
    allYears: 'Tutti gli anni',
    completedCount: 'Rimborsi completati',
    completedTotal: 'Totale rimborsato',
    pendingTotal: 'Ancora da rimborsare',
    notDone: 'Non ancora effettuato',
    dateUnknown: 'Data di completamento non disponibile',
    items: 'Voci',
    open: 'Apri dettagli',
    empty: 'Nessun rimborso corrisponde ai filtri selezionati.',
    details: 'Dettaglio rimborso',
    status: 'Stato',
    when: 'Quando',
    amount: 'Importo',
    bill: 'Bolletta',
    recurring: 'Spesa ricorrente',
    legacy: 'Questo rimborso è precedente al dettaglio degli importi per voce: le voci sono note, ma il singolo importo rimborsato non era stato salvato.',
    unavailable: 'I dettagli delle voci originali non sono più disponibili.',
    undo: 'Annulla rimborso',
    cancel: 'Chiudi',
    loading: 'Caricamento…',
    error: 'Errore',
    retry: 'Riprova',
  },
}

function historyLanguage(hass) {
  const raw =
    hass?.language || hass?.locale?.language || navigator.language || 'en'
  return String(raw).toLowerCase().split(/[-_]/)[0] === 'it' ? 'it' : 'en'
}

function ht(hass, key) {
  const language = historyLanguage(hass)
  return HISTORY_TEXT[language]?.[key] ?? HISTORY_TEXT.en[key] ?? key
}

function historyLocale(hass) {
  const raw =
    hass?.locale?.language || hass?.language || navigator.language || 'en-US'
  return String(raw).replace('_', '-')
}

function hEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

class BillyReimbursementHistory extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._hass = null
    this._data = null
    this._loading = false
    this._error = null
    this._status = 'all'
    this._payer = 'all'
    this._year = 'all'
    this._unsubscribe = null
  }

  set hass(value) {
    const previousConnection = this._hass?.connection
    const connectionChanged =
      previousConnection && previousConnection !== value?.connection
    const firstAssignment = !this._hass
    this._hass = value
    if (!this.isConnected) return
    if (connectionChanged) {
      this._unsubscribe?.()
      this._unsubscribe = null
      this._subscribe()
    }
    if (firstAssignment || connectionChanged || !this._data) this._load()
  }

  get hass() {
    return this._hass
  }

  connectedCallback() {
    this._subscribe()
    this._load()
  }

  disconnectedCallback() {
    this._unsubscribe?.()
    this._unsubscribe = null
  }

  _t(key) {
    return ht(this._hass, key)
  }

  _money(value) {
    const currency =
      this._data?.currency || this._hass?.config?.currency || 'EUR'
    try {
      return new Intl.NumberFormat(historyLocale(this._hass), {
        style: 'currency',
        currency,
      }).format(Number(value || 0))
    } catch (_error) {
      return `${Number(value || 0).toFixed(2)} ${currency}`
    }
  }

  _dateTime(value) {
    if (!value) return this._t('dateUnknown')
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return String(value)
    return parsed.toLocaleString(historyLocale(this._hass), {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  }

  _date(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ''))
    if (!match) return ''
    return new Intl.DateTimeFormat(historyLocale(this._hass), {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  }

  async _subscribe() {
    if (!this._hass || this._unsubscribe) return
    try {
      this._unsubscribe = await this._hass.connection.subscribeEvents(
        () => this._load(false),
        'bill_tracker_updated',
      )
    } catch (_error) {}
  }

  async _load(showLoading = true) {
    if (!this._hass || this._loading) return
    if (showLoading) this._loading = true
    if (showLoading) this._render()
    try {
      this._data = await this._hass.callWS({
        type: 'bill_tracker/list',
        forecast_months: 1,
      })
      this._error = null
    } catch (error) {
      this._error = String(error?.message || error)
    } finally {
      this._loading = false
      this._render()
    }
  }

  _manualRows() {
    const payerNames = new Map(
      (this._data?.payers || []).map((payer) => [String(payer.id), payer.name]),
    )
    const recurringById = new Map(
      (this._data?.recurring_expenses || []).map((row) => [
        String(row.id),
        row,
      ]),
    )
    const rows = []
    for (const expense of this._data?.expenses || []) {
      if (!expense.reimbursement_manual_done) continue
      const creditor = String(expense.payer_id || '')
      if (!creditor) continue
      for (const part of expense.split || []) {
        const debtor = String(part.payer_id || '')
        const percentage = Number(part.percentage || 0)
        if (!debtor || debtor === creditor || percentage <= 0) continue
        const amount = Number(expense.amount || 0) * percentage / 100
        rows.push({
          id: `manual-expense:${expense.id}:${debtor}`,
          archive_key: `manual-expense:${expense.id}:${debtor}`,
          archive_status: 'done',
          archive_source: 'manual-expense',
          archive_date: expense.reimbursement_manual_at || '',
          manual_id: expense.id,
          from_payer_id: debtor,
          from_name: part.name || payerNames.get(debtor) || debtor,
          to_payer_id: creditor,
          to_name: expense.payer || payerNames.get(creditor) || creditor,
          amount,
          item_count: 1,
          note: expense.note || '',
          archive_items: [
            {
              kind: 'expense',
              id: expense.id,
              amount,
              label: expense.provider || expense.category || this._t('bill'),
              date: expense.due_date || expense.payment_date || '',
              category: expense.category || '',
              provider: expense.provider || '',
              contract: expense.contract || '',
              legacy_amount_unknown: false,
            },
          ],
        })
      }
    }
    for (const occurrence of this._data?.recurring_occurrences || []) {
      if (!occurrence.reimbursement_manual_done) continue
      const creditor = String(occurrence.payer_id || '')
      if (!creditor) continue
      const recurring = recurringById.get(String(occurrence.recurring_id || ''))
      for (const part of occurrence.split || []) {
        const debtor = String(part.payer_id || '')
        const percentage = Number(part.percentage || 0)
        if (!debtor || debtor === creditor || percentage <= 0) continue
        const amount = Number(occurrence.amount || 0) * percentage / 100
        rows.push({
          id: `manual-recurring:${occurrence.id}:${debtor}`,
          archive_key: `manual-recurring:${occurrence.id}:${debtor}`,
          archive_status: 'done',
          archive_source: 'manual-recurring',
          archive_date: occurrence.reimbursement_manual_at || '',
          manual_id: occurrence.id,
          from_payer_id: debtor,
          from_name: part.name || payerNames.get(debtor) || debtor,
          to_payer_id: creditor,
          to_name: occurrence.payer || payerNames.get(creditor) || creditor,
          amount,
          item_count: 1,
          archive_items: [
            {
              kind: 'recurring',
              id: occurrence.id,
              amount,
              label: occurrence.name || recurring?.name || this._t('recurring'),
              date: occurrence.due_date || '',
              category: '',
              provider: recurring?.provider || '',
              contract: recurring?.contract || '',
              legacy_amount_unknown: false,
            },
          ],
        })
      }
    }
    return rows
  }

  _allRows() {
    const completed = (this._data?.settlements || []).map((row) => ({
      ...row,
      archive_key: `done:${row.id}`,
      archive_status: 'done',
      archive_source: 'settlement',
      archive_date: row.created_at || '',
      archive_items: Array.isArray(row.items) ? row.items : [],
    }))
    const pending = (this._data?.debts || []).map((row) => ({
      ...row,
      id: `pending:${row.from_payer_id}:${row.to_payer_id}`,
      archive_key: `pending:${row.from_payer_id}:${row.to_payer_id}`,
      archive_status: 'pending',
      archive_source: 'pending',
      archive_date: '',
      archive_items: Array.isArray(row.items) ? row.items : [],
    }))
    return [...pending, ...this._manualRows(), ...completed]
  }

  _rows() {
    return this._allRows()
      .filter((row) => {
        if (this._status !== 'all' && row.archive_status !== this._status)
          return false
        if (
          this._payer !== 'all' &&
          row.from_payer_id !== this._payer &&
          row.to_payer_id !== this._payer
        )
          return false
        if (this._year !== 'all') {
          if (!row.archive_date) return false
          if (String(new Date(row.archive_date).getFullYear()) !== this._year)
            return false
        }
        return true
      })
      .sort((a, b) => {
        if (a.archive_status !== b.archive_status)
          return a.archive_status === 'pending' ? -1 : 1
        return String(b.archive_date || '').localeCompare(
          String(a.archive_date || ''),
        )
      })
  }

  _years() {
    return [
      ...new Set(
        this._allRows()
          .filter((row) => row.archive_status === 'done')
          .map((row) => {
            const parsed = new Date(row.archive_date || '')
            return Number.isNaN(parsed.getTime()) ? null : parsed.getFullYear()
          })
          .filter(Boolean),
      ),
    ].sort((a, b) => b - a)
  }

  _statusLabel(status) {
    return status === 'done' ? this._t('completed') : this._t('pending')
  }

  _itemMeta(item) {
    const parts = [item.kind === 'recurring' ? this._t('recurring') : this._t('bill')]
    if (item.category) parts.push(item.category)
    if (item.provider && item.provider !== item.label) parts.push(item.provider)
    if (item.contract) parts.push(item.contract)
    if (item.date) parts.push(this._date(item.date))
    return parts.filter(Boolean).join(' · ')
  }

  _render() {
    if (this._loading && !this._data) {
      this.shadowRoot.innerHTML = `<style>${this._styles()}</style><div class="loading">${hEscape(this._t('loading'))}</div>`
      return
    }
    if (this._error && !this._data) {
      this.shadowRoot.innerHTML = `<style>${this._styles()}</style><div class="error-card"><strong>${hEscape(this._t('error'))}</strong><p>${hEscape(this._error)}</p><button id="retry">${hEscape(this._t('retry'))}</button></div>`
      this.shadowRoot
        .getElementById('retry')
        ?.addEventListener('click', () => this._load())
      return
    }
    if (!this._data) return

    const rows = this._rows()
    const completed = this._allRows().filter(
      (row) => row.archive_status === 'done',
    )
    const pending = this._data.debts || []
    const completedTotal = completed.reduce(
      (sum, row) => sum + Number(row.amount || 0),
      0,
    )
    const pendingTotal = pending.reduce(
      (sum, row) => sum + Number(row.amount || 0),
      0,
    )
    const payers = this._data.payers || []

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <div class="history-page">
        <div class="hero"><h1>${hEscape(this._t('title'))}</h1><p>${hEscape(this._t('help'))}</p></div>
        ${this._error ? `<div class="notice error">${hEscape(this._error)}</div>` : ''}
        <div class="stats">
          <article><span>${hEscape(this._t('completedCount'))}</span><strong>${completed.length}</strong></article>
          <article><span>${hEscape(this._t('completedTotal'))}</span><strong>${hEscape(this._money(completedTotal))}</strong></article>
          <article><span>${hEscape(this._t('pendingTotal'))}</span><strong>${hEscape(this._money(pendingTotal))}</strong></article>
        </div>
        <div class="toolbar">
          <select id="history-status">
            <option value="all" ${this._status === 'all' ? 'selected' : ''}>${hEscape(this._t('all'))}</option>
            <option value="done" ${this._status === 'done' ? 'selected' : ''}>${hEscape(this._t('completed'))}</option>
            <option value="pending" ${this._status === 'pending' ? 'selected' : ''}>${hEscape(this._t('pending'))}</option>
          </select>
          <select id="history-payer">
            <option value="all">${hEscape(this._t('allPayers'))}</option>
            ${payers.map((payer) => `<option value="${hEscape(payer.id)}" ${this._payer === payer.id ? 'selected' : ''}>${hEscape(payer.name)}</option>`).join('')}
          </select>
          <select id="history-year">
            <option value="all">${hEscape(this._t('allYears'))}</option>
            ${this._years().map((year) => `<option value="${year}" ${String(this._year) === String(year) ? 'selected' : ''}>${year}</option>`).join('')}
          </select>
        </div>
        <div class="history-card">
          ${rows.length ? rows.map((row) => `
            <div class="history-item">
              <span class="state ${row.archive_status}">${hEscape(this._statusLabel(row.archive_status))}</span>
              <div class="history-main"><strong>${hEscape(`${row.from_name} → ${row.to_name}`)}</strong><small>${hEscape(row.archive_status === 'done' ? this._dateTime(row.archive_date) : this._t('notDone'))}</small></div>
              <div class="history-count"><span>${hEscape(this._t('items'))}</span><strong>${Number(row.item_count || row.archive_items.length || 0)}</strong></div>
              <b class="history-amount">${hEscape(this._money(row.amount))}</b>
              <button class="secondary small" data-history-details="${hEscape(row.archive_key)}">${hEscape(this._t('open'))}</button>
            </div>`).join('') : `<div class="empty">${hEscape(this._t('empty'))}</div>`}
        </div>
      </div>
      <div class="modal" id="history-modal" hidden><div class="modal-backdrop"></div><div class="modal-card" id="history-modal-card"></div></div>
    `

    this.shadowRoot.getElementById('history-status')?.addEventListener('change', (event) => {
      this._status = event.currentTarget.value
      this._render()
    })
    this.shadowRoot.getElementById('history-payer')?.addEventListener('change', (event) => {
      this._payer = event.currentTarget.value
      this._render()
    })
    this.shadowRoot.getElementById('history-year')?.addEventListener('change', (event) => {
      this._year = event.currentTarget.value
      this._render()
    })
    for (const button of this.shadowRoot.querySelectorAll('[data-history-details]')) {
      button.addEventListener('click', () =>
        this._openDetails(button.dataset.historyDetails),
      )
    }
  }

  _openDetails(key) {
    const row = this._allRows().find((item) => item.archive_key === key)
    const modal = this.shadowRoot.getElementById('history-modal')
    const card = this.shadowRoot.getElementById('history-modal-card')
    if (!row || !modal || !card) return
    const items = row.archive_items || []
    const hasLegacyAmounts =
      row.archive_status === 'done' &&
      items.some((item) => item.legacy_amount_unknown)

    card.innerHTML = `
      <div class="modal-head"><div><h3>${hEscape(this._t('details'))}</h3><div class="hint">${hEscape(`${row.from_name} → ${row.to_name}`)}</div></div><button type="button" class="icon-close" id="history-close">×</button></div>
      <div class="detail-summary">
        <div><span>${hEscape(this._t('status'))}</span><strong class="state ${row.archive_status}">${hEscape(this._statusLabel(row.archive_status))}</strong></div>
        <div><span>${hEscape(this._t('when'))}</span><strong>${hEscape(row.archive_status === 'done' ? this._dateTime(row.archive_date) : this._t('notDone'))}</strong></div>
        <div><span>${hEscape(this._t('amount'))}</span><strong>${hEscape(this._money(row.amount))}</strong></div>
      </div>
      ${hasLegacyAmounts ? `<div class="legacy-note">${hEscape(this._t('legacy'))}</div>` : ''}
      <div class="detail-list">
        ${items.length ? items.map((item) => `
          <div class="detail-row">
            <div><strong>${hEscape(item.label || (item.kind === 'recurring' ? this._t('recurring') : this._t('bill')))}</strong><small>${hEscape(this._itemMeta(item))}</small></div>
            <b>${item.amount === null || item.amount === undefined ? '—' : hEscape(this._money(item.amount))}</b>
          </div>`).join('') : `<div class="empty compact">${hEscape(this._t('unavailable'))}</div>`}
      </div>
      ${row.note ? `<div class="history-note">${hEscape(row.note)}</div>` : ''}
      <div class="modal-actions">
        <button type="button" class="secondary" id="history-cancel">${hEscape(this._t('cancel'))}</button>
        ${row.archive_status === 'done' ? `<button type="button" class="danger" id="history-undo">${hEscape(this._t('undo'))}</button>` : ''}
      </div>
    `

    modal.hidden = false
    const close = () => {
      modal.hidden = true
    }
    card.querySelector('#history-close')?.addEventListener('click', close)
    card.querySelector('#history-cancel')?.addEventListener('click', close)
    modal.querySelector('.modal-backdrop')?.addEventListener('click', close)
    card.querySelector('#history-undo')?.addEventListener('click', async () => {
      if (!window.confirm(`${this._t('undo')}: ${this._money(row.amount)}?`)) return
      try {
        if (row.archive_source === 'manual-expense') {
          await this._hass.callWS({
            type: 'bill_tracker/set_reimbursement',
            expense_id: row.manual_id,
            done: false,
          })
        } else if (row.archive_source === 'manual-recurring') {
          await this._hass.callWS({
            type: 'bill_tracker/recurring/set_reimbursement',
            occurrence_id: row.manual_id,
            done: false,
          })
        } else {
          await this._hass.callWS({
            type: 'bill_tracker/settlement/delete',
            settlement_id: row.id,
          })
        }
        close()
        await this._load(false)
      } catch (error) {
        this._error = String(error?.message || error)
        close()
        this._render()
      }
    })
  }

  _styles() {
    return `
      :host{display:block;color:var(--primary-text-color)}*{box-sizing:border-box}.history-page{display:flex;flex-direction:column;gap:18px}.hero h1{font-size:30px;line-height:1.1;margin:0 0 6px}.hero p{margin:0;max-width:900px;color:var(--secondary-text-color);font-size:14px;line-height:1.5}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.stats article{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:5px}.stats span,.history-count span,.detail-summary span{font-size:11px;color:var(--secondary-text-color)}.stats strong{font-size:20px}.toolbar{display:grid;grid-template-columns:repeat(3,minmax(170px,1fr));gap:10px}.toolbar select{height:44px;border:1px solid var(--divider-color);border-radius:11px;padding:0 11px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}.history-card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:16px;overflow:hidden}.history-item{display:grid;grid-template-columns:auto minmax(220px,1fr) auto auto auto;gap:14px;align-items:center;padding:14px 16px;border-top:1px solid var(--divider-color)}.history-item:first-child{border-top:0}.history-main{display:flex;flex-direction:column;gap:4px;min-width:0}.history-main strong,.history-main small{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.history-main small{color:var(--secondary-text-color)}.history-count{display:flex;flex-direction:column;align-items:center;gap:2px}.history-amount{font-size:15px;white-space:nowrap}.state{display:inline-flex;width:max-content;align-items:center;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:650;white-space:nowrap}.state.done{color:var(--success-color,#2e7d32);background:color-mix(in srgb,var(--success-color,#2e7d32) 12%,transparent)}.state.pending{color:var(--warning-color,#f9a825);background:color-mix(in srgb,var(--warning-color,#f9a825) 12%,transparent)}.secondary,.danger,.error-card button{appearance:none;border-radius:9px;padding:9px 13px;font:inherit;font-weight:600;cursor:pointer;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color)}.small{padding:7px 10px;font-size:12px}.danger{color:var(--error-color,#d32f2f)}.empty{padding:48px 16px;text-align:center;color:var(--secondary-text-color)}.empty.compact{padding:24px 8px}.notice.error{padding:11px 14px;border-radius:10px;background:color-mix(in srgb,var(--error-color,#d32f2f) 10%,var(--card-background-color));color:var(--error-color,#d32f2f);border:1px solid color-mix(in srgb,var(--error-color,#d32f2f) 28%,transparent)}.loading,.error-card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:14px;padding:24px}.modal[hidden]{display:none}.modal{position:fixed;inset:0;z-index:10000;display:grid;place-items:center;padding:20px}.modal-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.55)}.modal-card{position:relative;z-index:1;width:min(780px,100%);max-height:min(90vh,900px);overflow:auto;background:var(--card-background-color);border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.35);padding:20px}.modal-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:16px}.modal-head h3{font-size:20px;margin:0}.hint{font-size:12px;color:var(--secondary-text-color);margin-top:4px}.icon-close{appearance:none;border:0;background:transparent;color:var(--secondary-text-color);font-size:28px;line-height:1;cursor:pointer}.detail-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:14px}.detail-summary>div{border:1px solid var(--divider-color);border-radius:11px;padding:12px;display:flex;flex-direction:column;gap:5px}.legacy-note{padding:11px 13px;margin-bottom:12px;border-radius:10px;background:color-mix(in srgb,var(--warning-color,#f9a825) 10%,transparent);color:var(--warning-color,#f9a825);font-size:12px;line-height:1.45}.detail-list{display:flex;flex-direction:column;border-top:1px solid var(--divider-color)}.detail-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center;padding:13px 2px;border-bottom:1px solid var(--divider-color)}.detail-row>div{display:flex;flex-direction:column;gap:4px;min-width:0}.detail-row small{color:var(--secondary-text-color);line-height:1.4}.history-note{margin-top:13px;padding:12px;border-radius:10px;background:var(--secondary-background-color);color:var(--secondary-text-color);font-size:12px}.modal-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px;padding-top:16px;border-top:1px solid var(--divider-color)}@media(max-width:900px){.history-item{grid-template-columns:auto minmax(0,1fr) auto}.history-count{grid-column:2;align-items:flex-start}.history-amount{grid-column:3;grid-row:1}.history-item button{grid-column:3;grid-row:2}.toolbar{grid-template-columns:1fr 1fr}.toolbar select:last-child{grid-column:1/-1}}@media(max-width:650px){.stats{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr}.toolbar select:last-child{grid-column:auto}.history-item{grid-template-columns:1fr}.state,.history-main,.history-count,.history-amount,.history-item button{grid-column:auto!important;grid-row:auto!important}.history-count{align-items:flex-start}.history-item button{width:100%}.detail-summary{grid-template-columns:1fr}.modal{padding:8px}.modal-card{padding:16px}.hero h1{font-size:25px}}
    `
  }
}

if (!customElements.get('billy-reimbursement-history')) {
  customElements.define('billy-reimbursement-history', BillyReimbursementHistory)
}
