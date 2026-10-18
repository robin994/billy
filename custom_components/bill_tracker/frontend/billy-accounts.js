// Lightweight user-defined accounts ledger. No bank APIs.
const ACCOUNT_TEXT = {
  en: {
    title: 'Accounts',
    intro: 'Manage your accounts and internal transfers without bank connections.',
    addAccount: 'Add account', editAccount: 'Edit account',
    accountName: 'Account name', accountType: 'Account type',
    payer: 'Owner (payer)', choosePayer: 'Select a payer',
    noPayers: 'Create a payer in Settings before adding an account.',
    defaultAccount: 'Default for new bills and income',
    setDefault: 'Set as default', deleteAccount: 'Delete account',
    confirmDeleteAccount: 'Delete this account? Accounts with linked transactions cannot be deleted.',
    checking: 'Checking', savings: 'Savings', cash: 'Cash',
    prepaid: 'Prepaid card', investment: 'Investments', other: 'Other',
    total: 'Combined balance',
    openingDate: 'Opening date',
    openingBalance: 'Opening balance',
    setOpening: 'Create your first account',
    editOpening: 'Edit account',
    setupHelp: 'Create as many accounts as you need. Give each a name, type, opening date and initial balance.',
    dateHelp: 'The opening amounts already include all transactions before this date.',
    scopeHelp: 'Only confirmed income and paid bills affect the account selected on each transaction. Scheduled recurring expenses, unpaid bills, forecasts and payer reimbursements are excluded. Unassigned historical movements use the account selected as default at migration time.',
    transfer: 'Internal transfer',
    addTransfer: 'Record a transfer',
    direction: 'From account',
    to: 'To {name}',
    date: 'Transfer date',
    amount: 'Amount',
    note: 'Note (optional)',
    transferHelp: 'Moves money between any two accounts without creating income or expense.',
    history: 'Transfer history',
    empty: 'No internal transfers recorded.',
    edit: 'Edit',
    remove: 'Delete',
    save: 'Save',
    cancel: 'Cancel',
    confirmRemove: 'Delete this transfer? Your balances will be recalculated.',
    incoming: 'Confirmed income',
    outgoing: 'Paid bills',
    asOf: 'Balance as of {date}',
    needsTwo: 'Create at least two accounts to record an internal transfer.',
    accountError: 'Unable to save this account.',
  },
  it: {
    title: 'Conti',
    intro: 'Gestisci conti e giroconti liberamente, senza collegamenti bancari.',
    addAccount: 'Aggiungi conto', editAccount: 'Modifica conto',
    accountName: 'Nome del conto', accountType: 'Tipologia del conto',
    payer: 'Intestatario (pagatore)', choosePayer: 'Seleziona un pagatore',
    noPayers: 'Crea un pagatore nelle impostazioni prima di aggiungere un conto.',
    defaultAccount: 'Predefinito per nuove bollette ed entrate',
    setDefault: 'Imposta predefinito', deleteAccount: 'Elimina conto',
    confirmDeleteAccount: 'Eliminare il conto? I conti con movimenti associati non possono essere eliminati.',
    checking: 'Conto corrente', savings: 'Risparmio', cash: 'Contanti',
    prepaid: 'Carta prepagata', investment: 'Investimenti', other: 'Altro',
    total: 'Saldo complessivo',
    openingDate: 'Data saldo iniziale',
    openingBalance: 'Saldo iniziale',
    setOpening: 'Crea il primo conto',
    editOpening: 'Modifica conto',
    setupHelp: 'Crea tutti i conti necessari indicando nome, tipologia, data e saldo iniziale.',
    dateHelp: 'I saldi iniziali comprendono già tutti i movimenti precedenti a questa data.',
    scopeHelp: 'Solo entrate confermate e bollette pagate incidono sul conto associato al movimento. Le ricorrenze previste, le bollette non pagate, le stime e i rimborsi tra paganti restano esclusi. I vecchi movimenti senza conto vengono associati al conto predefinito durante la migrazione.',
    transfer: 'Giroconto',
    addTransfer: 'Registra giroconto',
    direction: 'Dal conto',
    to: 'Verso {name}',
    date: 'Data giroconto',
    amount: 'Importo',
    note: 'Nota (facoltativa)',
    transferHelp: 'Sposta denaro tra due conti qualsiasi senza generare entrate o spese.',
    history: 'Storico giroconti',
    empty: 'Nessun giroconto registrato.',
    edit: 'Modifica',
    remove: 'Elimina',
    save: 'Salva',
    cancel: 'Annulla',
    confirmRemove: 'Eliminare il giroconto? I saldi saranno ricalcolati.',
    incoming: 'Entrate confermate',
    outgoing: 'Bollette pagate',
    asOf: 'Saldo al {date}',
    needsTwo: 'Crea almeno due conti per registrare un giroconto.',
    accountError: 'Impossibile salvare il conto.',
  },
}
const ACCOUNT_OWNER_TEXT = {
  es: { payer: 'Titular (pagador)', choosePayer: 'Selecciona un pagador', noPayers: 'Crea primero un pagador en Ajustes.' },
  fr: { payer: 'Titulaire (payeur)', choosePayer: 'Sélectionnez un payeur', noPayers: 'Créez un payeur dans les paramètres avant d’ajouter un compte.' },
  de: { payer: 'Inhaber (Zahler)', choosePayer: 'Zahler auswählen', noPayers: 'Erstellen Sie zuerst einen Zahler in den Einstellungen.' },
  pt: { payer: 'Titular (pagador)', choosePayer: 'Selecione um pagador', noPayers: 'Crie primeiro um pagador nas Definições.' },
}
const e = (value) => String(value ?? '').replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;')

function localToday() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

class BillyAccounts extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._data = null
    this._hass = null
    this._error = ''
  }
  set hass(value) { this._hass = value }
  set data(value) { this._data = value; this._render() }
  connectedCallback() { if (this._data) this._render() }
  _t(key, replacements = {}) {
    const language = String(this._hass?.language || 'en').split('-')[0].toLowerCase()
    let result = (ACCOUNT_TEXT[language] || ACCOUNT_OWNER_TEXT[language] || ACCOUNT_TEXT.en)[key] || ACCOUNT_TEXT.en[key] || key
    for (const [name, value] of Object.entries(replacements)) result = result.replaceAll(`{${name}}`, String(value))
    return result
  }
  _money(amount) {
    try {
      return new Intl.NumberFormat(this._hass?.locale?.language || 'en', {
        style: 'currency', currency: this._data?.currency || 'EUR',
      }).format(Number(amount || 0))
    } catch (_error) {
      return `${Number(amount || 0).toFixed(2)} ${this._data?.currency || 'EUR'}`
    }
  }
  async _request(payload) {
    if (!this._hass) return false
    try {
      await this._hass.callWS(payload)
      this._error = ''
    } catch (error) {
      this._error = error?.message || String(error)
      const modal = this.shadowRoot.getElementById('accounts-modal')
      if (modal && !modal.hidden) {
        const form = modal.querySelector('form')
        let notice = modal.querySelector('[data-form-error]')
        if (!notice && form) {
          notice = this.ownerDocument.createElement('p')
          notice.setAttribute('data-form-error', '')
          notice.className = 'error'
          notice.setAttribute('role', 'alert')
          form.prepend(notice)
        }
        if (notice) notice.textContent = this._error
      } else {
        this._render()
      }
      return false
    }
    // A successful write must not be retried just because the follow-up
    // snapshot fails. Repeated transfer writes would duplicate money moves.
    try {
      const refreshed = await this._hass.callWS({ type: 'bill_tracker/list', forecast_months: 12 })
      this.data = refreshed
    } catch (error) {
      this._error = error?.message || String(error)
      this._render()
    }
    return true
  }
  _transferRow(record) {
    const names = Object.fromEntries((this._data?.accounts || []).map((row) => [row.id, row.name]))
    return `<article class="transfer-row">
      <span class="transfer-icon"><ha-icon icon="mdi:swap-horizontal"></ha-icon></span>
      <div class="transfer-main">
        <strong>${e(names[record.from_account] || record.from_account)} → ${e(names[record.to_account] || record.to_account)}</strong>
        <small>${e(record.transfer_date)}${record.note ? ' · ' + e(record.note) : ''}</small>
      </div>
      <strong class="transfer-amount">${e(this._money(record.amount))}</strong>
      <div class="actions">
        <button type="button" data-edit-transfer="${e(record.id)}">${e(this._t('edit'))}</button>
        <button type="button" class="danger" data-delete-transfer="${e(record.id)}">${e(this._t('remove'))}</button>
      </div>
    </article>`
  }
  _render() {
    if (!this._data) return
    const balances = this._data.account_balances || {}
    const rows = balances.accounts || []
    const configured = rows.length > 0
    const history = this._data.internal_transfers || []
    const payerNames = Object.fromEntries((this._data.payers || []).map((payer) => [payer.id, payer.name]))
    this.shadowRoot.innerHTML = `<style>${this._styles()}</style>
      <div class="account-page">
        ${this._error ? `<div class="error" role="alert">${e(this._error)}</div>` : ''}
        <div class="header">
          <div><h2>${e(this._t('title'))}</h2><p>${e(this._t('intro'))}</p></div>
          <div class="actions">
            <button type="button" class="primary" data-add-account ${!(this._data.payers || []).length ? 'disabled' : ''}>${e(this._t('addAccount'))}</button>
            ${rows.length >= 2 ? `<button type="button" data-add-transfer>${e(this._t('addTransfer'))}</button>` : ''}
          </div>
        </div>
        ${!(this._data.payers || []).length ? `<p class="hint">${e(this._t('noPayers'))}</p>` : ''}
        ${configured ? `
          <div class="account-cards">
            ${rows.map((row) => `<article class="account-card">
              <div class="account-label">
                <ha-icon icon="mdi:wallet-outline"></ha-icon>
                <span>${e(row.name)}</span>
                ${row.is_default ? `<ha-icon icon="mdi:star" title="${e(this._t('defaultAccount'))}"></ha-icon>` : ''}
              </div>
              <small>${e(this._t(row.account_type))} · ${e(row.opening_date)}</small>
              <small>${e(this._t('payer'))}: ${e(payerNames[row.payer_id] || row.payer_id || '')}</small>
              <strong class="account-balance">${e(this._money(row.balance))}</strong>
              <small>${e(this._t('openingBalance'))}: ${e(this._money(row.opening_balance))}</small>
              <div class="account-breakdown">
                <span>+${e(this._money(row.income))} · ${e(this._t('incoming'))}</span>
                <span>−${e(this._money(row.expenses))} · ${e(this._t('outgoing'))}</span>
              </div>
              <div class="actions account-actions">
                <button data-edit-account="${e(row.id)}">${e(this._t('edit'))}</button>
                ${!row.is_default ? `<button data-default-account="${e(row.id)}">${e(this._t('setDefault'))}</button>` : ''}
                <button class="danger" data-delete-account="${e(row.id)}">${e(this._t('remove'))}</button>
              </div>
            </article>`).join('')}
            <article class="account-card combined">
              <div class="account-label"><ha-icon icon="mdi:cash-multiple"></ha-icon>
                <span>${e(this._t('total'))}</span></div>
              <strong class="account-balance">${e(this._money(balances.total))}</strong>
              <small>${e(this._t('asOf', { date: balances.as_of }))}</small>
            </article>
          </div>
          <p class="hint">${e(this._t('scopeHelp'))}</p>
          ${rows.length < 2 ? `<p class="hint">${e(this._t('needsTwo'))}</p>` : ''}
          <section class="history">
            <div class="history-head"><h3>${e(this._t('history'))}</h3>
              <span class="hint">${e(this._t('transferHelp'))}</span></div>
            ${history.length ? history.map((row) => this._transferRow(row)).join('')
              : `<div class="empty">${e(this._t('empty'))}</div>`}
          </section>
        ` : `<div class="setup">
          <ha-icon icon="mdi:bank-outline"></ha-icon><h3>${e(this._t('setOpening'))}</h3>
          <p>${e(this._t('setupHelp'))}</p>
          <button type="button" class="primary" data-create-first ${!(this._data.payers || []).length ? 'disabled' : ''}>${e(this._t('setOpening'))}</button>
        </div>`}
        <div class="modal" id="accounts-modal" hidden>
          <div class="backdrop"></div><div class="dialog" id="accounts-dialog"></div>
        </div>
      </div>`
    for (const button of this.shadowRoot.querySelectorAll('[data-add-account], [data-create-first]')) {
      button.addEventListener('click', () => this._openAccount())
    }
    for (const button of this.shadowRoot.querySelectorAll('[data-edit-account]')) {
      button.addEventListener('click', () => this._openAccount(button.dataset.editAccount))
    }
    for (const button of this.shadowRoot.querySelectorAll('[data-default-account]')) {
      button.addEventListener('click', () => this._request({
        type: 'bill_tracker/accounts/default', account_id: button.dataset.defaultAccount,
      }))
    }
    for (const button of this.shadowRoot.querySelectorAll('[data-delete-account]')) {
      button.addEventListener('click', async () => {
        if (window.confirm(this._t('confirmDeleteAccount'))) {
          await this._request({
            type: 'bill_tracker/accounts/delete', account_id: button.dataset.deleteAccount,
          })
        }
      })
    }
    this.shadowRoot.querySelector('[data-add-transfer]')?.addEventListener('click', () => this._openTransfer())
    this.shadowRoot.querySelectorAll('[data-edit-transfer]').forEach((button) =>
      button.addEventListener('click', () => this._openTransfer(button.dataset.editTransfer)))
    this.shadowRoot.querySelectorAll('[data-delete-transfer]').forEach((button) =>
      button.addEventListener('click', async () => {
        if (!window.confirm(this._t('confirmRemove'))) return
        await this._request({
          type: 'bill_tracker/accounts/transfer/delete', transfer_id: button.dataset.deleteTransfer,
        })
      }))
  }
  _modal(markup, onSave) {
    const modal = this.shadowRoot.getElementById('accounts-modal')
    if (!modal) return
    modal.querySelector('#accounts-dialog').innerHTML = markup
    modal.hidden = false
    const close = () => { modal.hidden = true }
    modal.querySelector('.backdrop').onclick = close
    modal.querySelector('[data-close]')?.addEventListener('click', close)
    modal.querySelector('form')?.addEventListener('submit', async (event) => {
      event.preventDefault()
      if (await onSave(new FormData(event.currentTarget))) close()
    })
    return modal
  }
  _openAccount(id = null) {
    const row = (this._data?.accounts || []).find((item) => item.id === id)
    const payers = this._data?.payers || []
    if (!payers.length) return
    this._modal(`<form>
      <h2>${e(this._t(row ? 'editAccount' : 'addAccount'))}</h2>
      <p class="hint">${e(this._t('dateHelp'))}</p>
      <div class="fields">
        <label>${e(this._t('accountName'))}
          <input name="name" maxlength="90" required value="${e(row?.name || '')}" placeholder="e.g. Joint account"></label>
        <label>${e(this._t('payer'))}
          <select name="payer_id" required>
            ${row ? '' : `<option value="" selected disabled>${e(this._t('choosePayer'))}</option>`}
            ${payers.map((payer) =>
              `<option value="${e(payer.id)}" ${payer.id === row?.payer_id ? 'selected' : ''}>${e(payer.name)}</option>`).join('')}
          </select></label>
        <label>${e(this._t('accountType'))}
          <input name="account_type" maxlength="50" required list="account-types" value="${e(row?.account_type || 'checking')}">
          <datalist id="account-types">
            ${['checking', 'savings', 'cash', 'prepaid', 'investment', 'other'].map((kind) =>
              `<option value="${kind}" label="${e(this._t(kind))}"></option>`).join('')}
          </datalist>
        </label>
        <label>${e(this._t('openingDate'))}
          <input name="opening_date" type="date" max="${localToday()}" required value="${e(row?.opening_date || localToday())}"></label>
        <label>${e(this._t('openingBalance'))}
          <input name="opening_balance" type="number" step="0.01" required value="${e(row?.opening_balance ?? 0)}"></label>
        <label class="wide check"><input name="make_default" type="checkbox" ${!this._data?.accounts?.length || row?.id === this._data?.default_account_id ? 'checked' : ''}>
          ${e(this._t('defaultAccount'))}</label>
      </div>
      <div class="modal-actions"><button type="button" data-close>${e(this._t('cancel'))}</button>
        <button type="submit" class="primary">${e(this._t('save'))}</button></div>
    </form>`, (data) => this._request({
      type: row ? 'bill_tracker/accounts/update' : 'bill_tracker/accounts/add',
      ...(row ? { account_id: row.id } : {}),
      name: String(data.get('name') || '').trim(),
      payer_id: String(data.get('payer_id') || ''),
      account_type: String(data.get('account_type') || '').trim(),
      opening_date: String(data.get('opening_date') || ''),
      opening_balance: Number(data.get('opening_balance')),
      make_default: data.get('make_default') === 'on',
    }))
  }
  _openTransfer(id = null) {
    const accounts = this._data?.accounts || []
    if (accounts.length < 2) return
    const row = (this._data?.internal_transfers || []).find((item) => item.id === id)
    const initial = row?.from_account || this._data?.default_account_id || accounts[0].id
    const other = accounts.find((account) => account.id !== initial)?.id
    const destination = row?.to_account || other
    const options = (selected) => accounts.map((account) =>
      `<option value="${e(account.id)}" ${account.id === selected ? 'selected' : ''}>${e(account.name)}</option>`
    ).join('')
    const modal = this._modal(`<form>
      <h2>${e(this._t('transfer'))}</h2>
      <p class="hint">${e(this._t('transferHelp'))}</p>
      <div class="fields">
        <label>${e(this._t('direction'))}
          <select name="from_account" required>${options(initial)}</select>
        </label>
        <label>${e(this._t('transfer'))}
          <select name="to_account" required>${options(destination)}</select></label>
        <label>${e(this._t('amount'))}<input name="amount" type="number" min="0.01" step="0.01" required value="${e(row?.amount ?? '')}"></label>
        <label>${e(this._t('date'))}<input name="transfer_date" type="date" max="${localToday()}" required value="${e(row?.transfer_date || localToday())}"></label>
        <label class="wide">${e(this._t('note'))}<textarea name="note" rows="3" maxlength="500">${e(row?.note || '')}</textarea></label>
      </div>
      <div class="modal-actions"><button type="button" data-close>${e(this._t('cancel'))}</button>
        <button type="submit" class="primary">${e(this._t('save'))}</button></div>
    </form>`, async (data) => {
      return this._request({
        type: row ? 'bill_tracker/accounts/transfer/update' : 'bill_tracker/accounts/transfer/add',
        ...(row ? { transfer_id: row.id } : {}),
        from_account: String(data.get('from_account') || ''),
        to_account: String(data.get('to_account') || ''),
        amount: Number(data.get('amount')),
        transfer_date: String(data.get('transfer_date') || ''),
        note: String(data.get('note') || ''),
      })
    })
    modal?.querySelector('[name="from_account"]')?.addEventListener('change', (event) => {
      const target = modal.querySelector('[name="to_account"]')
      if (target.value === event.currentTarget.value)
        target.value = accounts.find((account) => account.id !== event.currentTarget.value)?.id || ''
    })
  }
  _styles() {
    return `
      :host{display:block;color:var(--primary-text-color);font:inherit}*{box-sizing:border-box}
      h2{font-size:21px;margin:0 0 5px}h3{font-size:16px;margin:0 0 7px}
      p{margin:0}.header{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
      .header p,.hint{color:var(--secondary-text-color);font-size:12px;line-height:1.6}
      .account-page{display:flex;flex-direction:column;gap:16px}
      button{appearance:none;border:1px solid var(--divider-color);border-radius:9px;padding:9px 12px;font:inherit;font-weight:600;cursor:pointer;color:var(--primary-text-color);background:var(--card-background-color)}
      .primary{background:var(--primary-color);color:white;border-color:var(--primary-color)}
      .danger{color:var(--error-color,#d32f2f)}
      .actions{display:flex;gap:8px;flex-wrap:wrap}
      .account-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
      .account-card{background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:14px;padding:20px;display:flex;flex-direction:column;gap:12px;min-width:0}
      .account-card.combined{background:color-mix(in srgb,var(--primary-color) 8%,var(--card-background-color))}
      .account-label{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:650}
      .account-label ha-icon{--mdc-icon-size:21px;color:var(--primary-color)}
      .account-balance{font-size:clamp(21px,2.3vw,29px);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
      .account-card small{color:var(--secondary-text-color);font-size:12px}
      .account-breakdown{display:flex;flex-direction:column;gap:5px;font-size:11px;color:var(--secondary-text-color)}
      .history{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:13px;padding:15px}
      .history-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}
      .transfer-row{border-top:1px solid var(--divider-color);display:grid;grid-template-columns:34px minmax(160px,1fr) auto auto;align-items:center;gap:12px;padding:13px 0}
      .transfer-row:first-of-type{border-top:0}.transfer-icon{border-radius:50%;background:color-mix(in srgb,var(--primary-color) 10%,transparent);color:var(--primary-color);width:31px;height:31px;display:grid;place-items:center}
      .transfer-icon ha-icon{--mdc-icon-size:19px}.transfer-main{display:flex;flex-direction:column;gap:5px;min-width:0}
      .transfer-main strong{font-size:13px}.transfer-main small{font-size:11px;color:var(--secondary-text-color);overflow-wrap:anywhere}
      .transfer-amount{font-size:15px;white-space:nowrap}.empty{padding:35px 15px;text-align:center;color:var(--secondary-text-color)}
      .setup{background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:13px;padding:35px 20px;text-align:center;display:flex;align-items:center;flex-direction:column;gap:13px}
      .setup ha-icon{--mdc-icon-size:44px;color:var(--primary-color)}.setup p{max-width:570px;color:var(--secondary-text-color);font-size:14px;line-height:1.65}
      .modal[hidden]{display:none}.modal{position:fixed;inset:0;z-index:10000;display:grid;place-items:center;padding:16px}
      .backdrop{position:absolute;inset:0;background:rgba(0,0,0,.55)}
      .dialog{position:relative;z-index:1;background:var(--card-background-color);border-radius:14px;width:min(650px,100%);max-height:90vh;overflow:auto;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,.28)}
      .fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:17px}
      .fields label{display:flex;flex-direction:column;gap:7px;font-size:12px;color:var(--secondary-text-color)}
      .fields input,.fields select,.fields textarea{font:inherit;color:var(--primary-text-color);background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:9px;padding:9px 11px;min-height:42px;width:100%;min-width:0}
      .fields .wide{grid-column:1/-1}.transfer-target{font-size:13px;padding:12px;border-radius:9px;background:var(--secondary-background-color);color:var(--primary-text-color)}
      .modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:20px}
      .error{border-radius:9px;border:1px solid var(--error-color,#d32f2f);padding:13px;color:var(--error-color,#d32f2f)}
      @media(max-width:900px){.account-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.account-card.combined{grid-column:1/-1}}
      @media(max-width:700px){.account-cards{grid-template-columns:1fr}.account-card.combined{grid-column:auto}.transfer-row{grid-template-columns:32px minmax(0,1fr)}.transfer-amount,.transfer-row .actions{grid-column:2}.fields{grid-template-columns:1fr}.fields .wide{grid-column:auto}.dialog{padding:17px}.header .actions{width:100%}}
    `
  }
}
if (!customElements.get('billy-accounts')) customElements.define('billy-accounts', BillyAccounts)
