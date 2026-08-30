import {
  billyCategoryLabel,
  billyLanguage,
  billyLocale,
  billyT,
} from './bill-tracker-i18n.js?v=0.12.0-r1'
import { BILLY_ERROR_TEXT } from './billy-extra-i18n.js?v=0.12.0-r1'

// Resolve a websocket/runtime error to a message in the user's language via its
// stable `code`, falling back to the English text the backend sends with it.
function billyErrorText(hass, error, fallback = '') {
  const code = error?.code
  if (code) {
    const table =
      BILLY_ERROR_TEXT[billyLanguage(hass)] || BILLY_ERROR_TEXT.en || {}
    if (table[code]) return table[code]
  }
  return String(error?.message || fallback || error)
}

const BILL_TRACKER_VERSION = '0.12.0'

class BillTrackerCard extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._hass = null
    this._config = {}
    this._data = null
    this._loading = false
    this._editing = null
    this._formOpen = false
    this._error = null
    this._chartMode = 'cashflow'
    this._allBillsOpen = false
    this._allBillsCategory = 'all'
    this._allBillsStatus = 'all'
    this._allBillsTimeMode = 'all'
    this._allBillsYear = 'all'
    this._allBillsFrom = ''
    this._allBillsTo = ''
    this._allBillsPage = 1
    this._allBillsPageSize = 10
    this._currentMonthBillsOpen = true
    this._transferOpen = false
    this._importCsvText = ''
    this._importFileName = ''
    this._transferBusy = false
    this._transferMessage = ''
    this._exportFormat = 'csv'
    this._exportFrom = ''
    this._exportTo = ''
    this._exportStatus = 'all'
    this._exportCategory = 'all'
    this._exportTrend = 'both'
    this._unsubscribe = null
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

  setConfig(config) {
    const rawColumns = config.columns ?? 'full'
    const columns =
      rawColumns === 'full'
        ? 'full'
        : Math.max(1, Math.min(12, Number(rawColumns || 12)))
    this._config = {
      title: config.title || '',
      columns,
      history_months: Math.max(
        3,
        Math.min(36, Number(config.history_months ?? 12)),
      ),
      forecast_months: Math.max(
        1,
        Math.min(24, Number(config.forecast_months ?? 12)),
      ),
    }
    this._render()
  }

  set hass(hass) {
    const first = !this._hass
    this._hass = hass
    if (first) {
      this._subscribeEvents()
      if (!this._data) this._load()
    }
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe()
      this._unsubscribe = null
    }
  }

  getCardSize() {
    return 12
  }

  getGridOptions() {
    const configured = this._config.columns ?? 'full'
    return {
      columns:
        configured === 'full'
          ? 'full'
          : Math.max(1, Math.min(12, Number(configured || 12))),
      min_columns: 6,
    }
  }

  async _subscribeEvents() {
    if (!this._hass || this._unsubscribe) return
    try {
      this._unsubscribe = await this._hass.connection.subscribeEvents(
        () => this._load(),
        'bill_tracker_updated',
      )
    } catch (_err) {
      // Local writes still trigger an explicit reload.
    }
  }

  async _load() {
    if (!this._hass || this._loading) return
    this._loading = true
    try {
      this._data = await this._hass.callWS({
        type: 'bill_tracker/list',
        forecast_months: this._config.forecast_months || 12,
      })
      this._error = null
    } catch (err) {
      this._error = billyErrorText(this._hass, err)
    } finally {
      this._loading = false
      this._render()
    }
  }

  _language() {
    return billyLanguage(this._hass)
  }

  _locale() {
    return billyLocale(this._hass)
  }

  _t(key, vars = {}) {
    return billyT(this._hass, key, vars)
  }

  _categoryLabel(category) {
    return billyCategoryLabel(this._hass, category)
  }

  _expenseCategoryLabel(item) {
    const category = this._categoryById(item?.category_id)
    return category
      ? this._categoryLabel(category)
      : String(item?.category || '')
  }

  _monthNames() {
    const formatter = new Intl.DateTimeFormat(this._locale(), { month: 'long' })
    return Array.from({ length: 12 }, (_, index) =>
      formatter.format(new Date(2026, index, 1)),
    )
  }

  _monthShort() {
    const formatter = new Intl.DateTimeFormat(this._locale(), {
      month: 'short',
    })
    return Array.from({ length: 12 }, (_, index) =>
      formatter.format(new Date(2026, index, 1)).replace(/\.$/, ''),
    )
  }

  _intervalLabel(months) {
    const count = Number(months)
    const key = `interval.${count}`
    const translated = this._t(key)
    return translated === key
      ? this._t('interval.other', { count })
      : translated
  }

  _defaultDate() {
    const d = new Date()
    return { year: d.getFullYear(), month: d.getMonth() + 1 }
  }

  _money(value) {
    const currency =
      this._data?.currency || this._hass?.config?.currency || 'EUR'
    const locale = this._locale()
    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
      }).format(Number(value || 0))
    } catch (_err) {
      return `${Number(value || 0).toFixed(2)} ${currency}`
    }
  }

  _compactMoney(value) {
    const currency =
      this._data?.currency || this._hass?.config?.currency || 'EUR'
    const locale = this._locale()
    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
        maximumFractionDigits: 0,
      }).format(Number(value || 0))
    } catch (_err) {
      return `${Math.round(Number(value || 0))} ${currency}`
    }
  }

  _unitPrice(value, unit) {
    const currency =
      this._data?.currency || this._hass?.config?.currency || 'EUR'
    const number = Number(value || 0)
    return `${number.toLocaleString(this._locale(), {
      maximumFractionDigits: 6,
    })} ${currency}/${unit}`
  }

  _usageText(item) {
    const parts = []
    const provider = String(item?.provider || '').trim()
    const contract = String(item?.contract || '').trim()
    if (provider || contract)
      parts.push([provider, contract].filter(Boolean).join(' · '))
    if (
      item?.consumption !== null &&
      item?.consumption !== undefined &&
      item?.consumption_unit
    ) {
      parts.push(
        this._t('consumption_value', {
          value: Number(item.consumption).toLocaleString(this._locale(), {
            maximumFractionDigits: 4,
          }),
          unit: item.consumption_unit,
        }),
      )
    }
    return parts.join(' · ')
  }

  _formatDate(value) {
    const text = String(value || '').trim()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return ''
    const [year, month, day] = text.split('-').map(Number)
    const parsed = new Date(year, month - 1, day)
    if (Number.isNaN(parsed.getTime())) return text
    return new Intl.DateTimeFormat(this._locale(), {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(parsed)
  }

  _expenseDatesText(item) {
    const parts = []
    if (item?.due_date)
      parts.push(this._t('due_date', { date: this._formatDate(item.due_date) }))
    if (item?.payment_date)
      parts.push(
        this._t('payment_date', { date: this._formatDate(item.payment_date) }),
      )
    return parts.join(' · ')
  }

  _escape(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;')
  }

  _safeColor(value) {
    const text = String(value || '').trim()
    return /^#[0-9a-fA-F]{6}$/.test(text) ? text : '#A0A7B4'
  }

  _monthValue(year, month) {
    return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}`
  }

  _parseMonth(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(value || ''))
    if (!match) return null
    const year = Number(match[1])
    const month = Number(match[2])
    if (!Number.isInteger(year) || month < 1 || month > 12) return null
    return { year, month }
  }

  _addMonths(year, month, delta) {
    const absolute = year * 12 + (month - 1) + delta
    return {
      year: Math.floor(absolute / 12),
      month: (((absolute % 12) + 12) % 12) + 1,
    }
  }

  _activeCategories() {
    return (this._data?.active_categories || [])
      .slice()
      .sort((a, b) =>
        this._categoryLabel(a).localeCompare(
          this._categoryLabel(b),
          this._locale(),
        ),
      )
  }

  _activePayers() {
    return (this._data?.active_payers || [])
      .slice()
      .sort((a, b) =>
        String(a.name || '').localeCompare(
          String(b.name || ''),
          this._locale(),
        ),
      )
  }

  _categoryById(id) {
    return (this._data?.categories || []).find((x) => x.id === id) || null
  }

  _payerById(id) {
    return (this._data?.payers || []).find((x) => x.id === id) || null
  }

  _categoryByName(name) {
    return (this._data?.categories || []).find((x) => x.name === name) || null
  }

  _splitMap(split) {
    const result = {}
    for (const part of split || [])
      result[part.payer_id] = Number(part.percentage || 0)
    return result
  }

  _chart() {
    const normalized = this._chartMode === 'normalized'
    const actualSource = normalized
      ? this._data?.normalized_monthly
      : this._data?.monthly
    const forecastSource = normalized
      ? this._data?.normalized_forecast
      : this._data?.forecast
    const actual = (actualSource || []).slice(-this._config.history_months)
    const forecast = (forecastSource || []).slice(
      0,
      this._config.forecast_months,
    )

    if (!actual.length) {
      return `<div class="empty-chart">${this._escape(
        this._t('empty_chart'),
      )}</div>`
    }

    const rows = [
      ...actual.map((x) => ({ ...x, kind: 'actual' })),
      ...forecast.map((x) => ({ ...x, kind: 'forecast' })),
    ]
    const maxValue =
      Math.max(1, ...rows.map((x) => Number(x.total || 0))) * 1.15
    const width = Math.max(860, rows.length * 52 + 80)
    const height = 300
    const left = 60
    const right = 18
    const top = 18
    const bottom = 48
    const plotW = width - left - right
    const plotH = height - top - bottom
    const step = plotW / Math.max(1, rows.length)
    const barW = Math.max(10, Math.min(34, step * 0.64))
    const y = (v) => top + plotH - (Number(v || 0) / maxValue) * plotH
    const x = (i) => left + step * i + step / 2

    const grid = [0, 0.25, 0.5, 0.75, 1]
      .map((ratio) => {
        const gy = top + plotH * (1 - ratio)
        const val = maxValue * ratio
        return `<line x1="${left}" y1="${gy}" x2="${
          width - right
        }" y2="${gy}" class="grid" />
        <text x="${left - 8}" y="${
          gy + 4
        }" text-anchor="end" class="axis-value">${this._escape(
          this._compactMoney(val),
        )}</text>`
      })
      .join('')

    const bars = actual
      .map((row, i) => {
        const bx = x(i) - barW / 2
        const total = Math.max(0, Number(row.total || 0))
        let cursor = top + plotH
        const parts = []
        const entries = Object.entries(row.categories || {}).filter(
          ([, value]) => Number(value) > 0,
        )
        for (const [name, rawValue] of entries) {
          const value = Number(rawValue || 0)
          const h = Math.max(0, (value / maxValue) * plotH)
          cursor -= h
          const category = this._categoryByName(name)
          const color = this._safeColor(category?.color)
          const percentage = total > 0 ? (value / total) * 100 : 0
          parts.push(`<rect x="${bx}" y="${cursor}" width="${barW}" height="${h}" fill="${color}" class="stack-segment">
          <title>${this._monthNames()[row.month - 1]} ${
            row.year
          } · ${this._escape(name)}: ${this._money(
            value,
          )} (${percentage.toFixed(1)}%)</title>
        </rect>`)
        }
        return parts.join('')
      })
      .join('')

    const forecastOffset = actual.length
    const forecastPoints = []
    if (forecast.length) {
      const lastActual = actual[actual.length - 1]
      forecastPoints.push([x(actual.length - 1), y(lastActual.total)])
      forecast.forEach((row, idx) =>
        forecastPoints.push([x(forecastOffset + idx), y(row.total)]),
      )
    }
    const forecastPath = forecastPoints.length
      ? `M ${forecastPoints.map((p) => `${p[0]} ${p[1]}`).join(' L ')}`
      : ''
    const forecastDots = forecast
      .map((row, idx) => {
        const px = x(forecastOffset + idx)
        const py = y(row.total)
        const breakdown = Object.entries(row.categories || {})
          .map(([name, amount]) => `${name}: ${this._money(amount)}`)
          .join(' · ')
        return `<circle cx="${px}" cy="${py}" r="4" class="forecast-dot">
        <title>${this._monthNames()[row.month - 1]} ${
          row.year
        }: stima ${this._money(row.total)}${
          breakdown ? ` · ${this._escape(breakdown)}` : ''
        }</title>
      </circle>`
      })
      .join('')

    const labelEvery = rows.length > 22 ? 3 : rows.length > 14 ? 2 : 1
    const labels = rows
      .map((row, i) => {
        if (i % labelEvery !== 0 && i !== rows.length - 1) return ''
        return `<text x="${x(i)}" y="${
          height - 18
        }" text-anchor="middle" class="axis-label">${
          this._monthShort()[row.month - 1]
        } '${String(row.year).slice(-2)}</text>`
      })
      .join('')

    const dividerX = forecast.length ? left + step * forecastOffset : null
    const divider = dividerX
      ? `<line x1="${dividerX}" y1="${top}" x2="${dividerX}" y2="${
          top + plotH
        }" class="forecast-divider" />`
      : ''

    return `<div class="chart-scroll">
      <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${this._escape(
        this._t('chart_aria'),
      )}">
        ${grid}
        ${bars}
        ${divider}
        ${
          forecastPath
            ? `<path d="${forecastPath}" class="forecast-line" />`
            : ''
        }
        ${forecastDots}
        ${labels}
      </svg>
    </div>`
  }

  _chartLegend() {
    const normalized = this._chartMode === 'normalized'
    const source = normalized
      ? this._data?.normalized_monthly
      : this._data?.monthly
    const rows = (source || []).slice(-this._config.history_months)
    const used = new Set()
    for (const row of rows) {
      for (const name of Object.keys(row.categories || {})) used.add(name)
    }
    const categoryLegend = [...used]
      .map((name) => {
        const category = this._categoryByName(name)
        return `<span><i class="legend-square" style="background:${this._safeColor(
          category?.color,
        )}"></i>${this._escape(
          category ? this._categoryLabel(category) : name,
        )}</span>`
      })
      .join('')
    return `${categoryLegend}<span><i class="legend-line"></i>${this._escape(
      this._t('forecast_total'),
    )}</span>`
  }

  _periodText(item) {
    if (item?.period_start_date && item?.period_end_date) {
      return `${this._date(item.period_start_date)} → ${this._date(item.period_end_date)}`
    }
    const start = this._monthValue(
      item.period_start_year,
      item.period_start_month,
    )
    const end = this._monthValue(item.period_end_year, item.period_end_month)
    if (start === end)
      return this._monthLabel(item.period_end_year, item.period_end_month)
    return `${this._monthLabel(
      item.period_start_year,
      item.period_start_month,
    )} → ${this._monthLabel(item.period_end_year, item.period_end_month)}`
  }

  _periodBadgeText(item) {
    if (item?.period_type === 'short') {
      return this._t('short_period', { days: Number(item.period_days || 0) })
    }
    if (item?.period_type === 'long') {
      return this._t('long_period', { days: Number(item.period_days || 0) })
    }
    return ''
  }

  _monthLabel(year, month) {
    return `${this._monthShort()[Number(month) - 1]} ${year}`
  }

  _splitText(item) {
    const parts = (item.split || []).filter((x) => Number(x.percentage) > 0)
    if (!parts.length) return this._t('not_split')
    return parts
      .map(
        (x) =>
          `${x.name} ${Number(x.percentage).toFixed(
            Number(x.percentage) % 1 ? 1 : 0,
          )}%`,
      )
      .join(' · ')
  }

  _expenseFormPayers(editing) {
    if (!editing) return this._activePayers()
    const ids = new Set(
      [
        editing.payer_id,
        ...(editing.split || []).map((x) => x.payer_id),
      ].filter(Boolean),
    )
    return (this._data?.payers || []).filter((p) => p.enabled || ids.has(p.id))
  }

  _allBillsYears(expenses) {
    return [
      ...new Set(
        (expenses || [])
          .map((x) => Number(x.paid_year))
          .filter(Number.isInteger),
      ),
    ].sort((a, b) => b - a)
  }

  _filterAllBills(expenses) {
    let rows = (expenses || []).slice()
    if (this._allBillsCategory !== 'all') {
      rows = rows.filter((x) => x.category_id === this._allBillsCategory)
    }
    if (this._allBillsStatus === 'paid') {
      rows = rows.filter((x) => Boolean(x.paid))
    } else if (this._allBillsStatus === 'unpaid') {
      rows = rows.filter((x) => !Boolean(x.paid))
    }
    if (this._allBillsTimeMode === 'year' && this._allBillsYear !== 'all') {
      const year = Number(this._allBillsYear)
      rows = rows.filter((x) => Number(x.paid_year) === year)
    } else if (this._allBillsTimeMode === 'range') {
      let from = this._allBillsFrom || ''
      let to = this._allBillsTo || ''
      if (from && to && from > to) [from, to] = [to, from]
      rows = rows.filter((x) => {
        const key = this._monthValue(x.paid_year, x.paid_month)
        return (!from || key >= from) && (!to || key <= to)
      })
    }
    return rows
  }

  _closeAllBillsModal() {
    this._allBillsOpen = false
    this._render()
  }

  _renderDebts() {
    const payers = this._data?.payers || []
    if (payers.length < 2) {
      return `<div class="settle-empty">${this._escape(
        this._t('configure_two_payers'),
      )}</div>`
    }
    const debts = this._data?.debts || []
    if (!debts.length) {
      return `<div class="settle-empty ok">✓ ${this._escape(
        this._t('no_balance'),
      )}</div>`
    }
    return `<div class="debt-list">${debts
      .map(
        (debt) => `
      <div class="debt-row">
        <div><strong>${this._escape(debt.from_name)} → ${this._escape(
          debt.to_name,
        )}</strong><span>${this._escape(
          this._t('balance_to_settle', {
            count: Number(debt.item_count ?? debt.expense_count ?? 0),
            bills:
              Number(debt.recurring_count || 0) > 0
                ? this._t('expense_items')
                : this._t(
                    Number(debt.expense_count || 0) === 1
                      ? 'bill_singular'
                      : 'bill_plural',
                  ),
          }),
        )}</span></div>
        <b>${this._money(debt.amount)}</b>
        <div class="debt-actions">
          ${
            debt.payment_url
              ? `<a class="paypal" href="${this._escape(
                  debt.payment_url,
                )}" target="_blank" rel="noopener noreferrer">${this._escape(
                  this._t('pay_with_method', {
                    method:
                      debt.payment_method === 'cashapp'
                        ? 'Cash App'
                        : debt.payment_method === 'revolut'
                          ? 'Revolut'
                          : debt.payment_method === 'venmo'
                            ? 'Venmo'
                            : 'PayPal',
                  }),
                )}</a>`
              : `<button class="secondary small" type="button" disabled>${this._escape(
                  this._t('payment_missing'),
                )}</button>`
          }
          <button class="primary small settle" type="button" data-from="${this._escape(
            debt.from_payer_id,
          )}" data-to="${this._escape(debt.to_payer_id)}" data-amount="${Number(
            debt.amount,
          )}" data-count="${Number(debt.item_count ?? debt.expense_count ?? 0)}">${this._escape(
            this._t('mark_settled'),
          )}</button>
        </div>
      </div>`,
      )
      .join('')}</div>`
  }

  _render() {
    if (!this.shadowRoot) return
    if (!this._data) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:20px">${
        this._loading
          ? this._escape(this._t('loading'))
          : this._escape(this._error || this._t('not_available'))
      }</div></ha-card>`
      return
    }

    const summary = this._data.summary || {}
    const activeCategories = this._activeCategories()
    const activePayers = this._activePayers()
    const editing = this._editing
    const selectedCategoryId =
      editing?.category_id || activeCategories[0]?.id || ''
    const selectedCategory = this._categoryById(selectedCategoryId)
    const now = this._defaultDate()
    const selectedPaid = editing
      ? this._monthValue(editing.paid_year, editing.paid_month)
      : this._monthValue(now.year, now.month)
    const paidParsed = this._parseMonth(selectedPaid) || now
    const interval = Math.max(1, Number(selectedCategory?.interval_months || 1))
    const startAuto = this._addMonths(
      paidParsed.year,
      paidParsed.month,
      -(interval - 1),
    )
    const defaultStart = editing
      ? this._monthValue(editing.period_start_year, editing.period_start_month)
      : this._monthValue(startAuto.year, startAuto.month)
    const defaultEnd = editing
      ? this._monthValue(editing.period_end_year, editing.period_end_month)
      : selectedPaid
    const formPayers = this._expenseFormPayers(editing)
    const defaultPayerId =
      editing?.payer_id ||
      selectedCategory?.default_payer_id ||
      activePayers[0]?.id ||
      ''
    const splitMap = this._splitMap(
      editing?.split?.length ? editing.split : this._data.default_split || [],
    )
    const allExpenses = this._data.expenses || []
    const currentMonthExpenses = allExpenses.filter(
      (x) =>
        Number(x.paid_year) === now.year && Number(x.paid_month) === now.month,
    )
    const allBillCategories = (this._data.categories || [])
      .slice()
      .sort((a, b) =>
        this._categoryLabel(a).localeCompare(
          this._categoryLabel(b),
          this._locale(),
        ),
      )
    const allBillYears = this._allBillsYears(allExpenses)
    const filteredAllExpenses = this._filterAllBills(allExpenses)
    const totalAllBillPages = Math.max(
      1,
      Math.ceil(filteredAllExpenses.length / this._allBillsPageSize),
    )
    if (this._allBillsPage > totalAllBillPages)
      this._allBillsPage = totalAllBillPages
    if (this._allBillsPage < 1) this._allBillsPage = 1
    const allBillsStart = (this._allBillsPage - 1) * this._allBillsPageSize
    const pagedAllExpenses = filteredAllExpenses.slice(
      allBillsStart,
      allBillsStart + this._allBillsPageSize,
    )
    const settlements = (this._data.settlements || []).slice(0, 5)
    const upcoming = (this._data.upcoming || []).slice(0, 8)
    const contractSavings = this._data.contract_savings || []
    const currency =
      this._data.currency || this._hass?.config?.currency || 'EUR'
    const selectedConsumptionUnit = String(
      selectedCategory?.consumption_unit || '',
    )

    const expenseFormHtml = `<form id="expense-form">
          <label>${this._escape(this._t('type'))}
            <select id="category" required>
              ${activeCategories
                .map(
                  (c) =>
                    `<option value="${this._escape(c.id)}" ${
                      c.id === selectedCategoryId ? 'selected' : ''
                    }>${this._escape(this._categoryLabel(c))} · ${this._escape(
                      this._intervalLabel(c.interval_months),
                    )}</option>`,
                )
                .join('')}
              ${
                editing && selectedCategory && !selectedCategory.enabled
                  ? `<option value="${this._escape(
                      selectedCategory.id,
                    )}" selected>${this._escape(
                      this._categoryLabel(selectedCategory),
                    )} · ${this._escape(this._t('disabled_type'))}</option>`
                  : ''
              }
            </select>
          </label>
          <label>${this._escape(
            this._t('payment_month'),
          )}<input id="paid-month" type="month" required value="${this._escape(
            selectedPaid,
          )}"></label>
          <label>${this._escape(
            this._t('amount', { currency }),
          )}<input id="amount" type="number" min="0" step="0.01" inputmode="decimal" required value="${
            editing ? this._escape(editing.amount) : ''
          }" placeholder="0,00"></label>
          <label>${this._escape(
            this._t('provider_optional'),
          )}<input id="provider" type="text" maxlength="100" value="${
            editing
              ? this._escape(editing.provider || '')
              : this._escape(selectedCategory?.default_provider || '')
          }" placeholder="${this._escape(this._t('provider_placeholder'))}"></label>
          <label>${this._escape(
            this._t('contract_optional'),
          )}<input id="contract" type="text" maxlength="100" value="${
            editing
              ? this._escape(editing.contract || '')
              : this._escape(selectedCategory?.default_contract || '')
          }" placeholder="${this._escape(this._t('contract_placeholder'))}"></label>
          <label id="consumption-label">${this._escape(
            this._t('consumption'),
          )}${
            selectedConsumptionUnit
              ? ` (${this._escape(selectedConsumptionUnit)})`
              : ` (${this._escape(this._t('unit_not_configured'))})`
          }<input id="consumption" type="number" min="0" step="any" inputmode="decimal" ${
            selectedConsumptionUnit ? '' : 'disabled'
          } value="${
            editing?.consumption !== null && editing?.consumption !== undefined
              ? this._escape(editing.consumption)
              : ''
          }" placeholder="${
            selectedConsumptionUnit
              ? '0'
              : this._escape(this._t('configure_unit'))
          }"></label>
          <label class="paid-check"><input id="paid-status" type="checkbox" ${
            editing?.paid ? 'checked' : ''
          }><div><strong>${this._escape(
            this._t('paid_checkbox'),
          )}</strong> <span>${this._escape(
            this._t('paid_checkbox_help'),
          )}</span></div></label>
          <label>${this._escape(
            this._t('payment_date_optional'),
          )}<input id="payment-date" type="date" value="${
            editing?.payment_date ? this._escape(editing.payment_date) : ''
          }"></label>
          <label>${this._escape(
            this._t('due_date_optional'),
          )}<input id="due-date" type="date" value="${
            editing?.due_date ? this._escape(editing.due_date) : ''
          }"></label>
          ${
            formPayers.length
              ? `<label>${this._escape(this._t('paid_by'))}
            <select id="payer" required>
              ${formPayers
                .map(
                  (p) =>
                    `<option value="${this._escape(p.id)}" ${
                      p.id === defaultPayerId ? 'selected' : ''
                    }>${this._escape(p.name)}${
                      p.enabled ? '' : ` · ${this._escape(this._t('disabled'))}`
                    }</option>`,
                )
                .join('')}
            </select>
          </label>`
              : ''
          }
          <label>${this._escape(
            this._t('competence_end'),
          )}<input id="period-end" type="month" required value="${this._escape(
            defaultEnd,
          )}"></label>
          <label>${this._escape(
            this._t('competence_start'),
          )}<input id="period-start" type="month" required value="${this._escape(
            defaultStart,
          )}"></label>
          <label>${this._escape(
            this._t('exact_period_start'),
          )}<input id="period-start-date" type="date" value="${
            editing?.period_start_date
              ? this._escape(editing.period_start_date)
              : ''
          }"></label>
          <label>${this._escape(
            this._t('exact_period_end'),
          )}<input id="period-end-date" type="date" value="${
            editing?.period_end_date
              ? this._escape(editing.period_end_date)
              : ''
          }"></label>
          <label class="wide">${this._escape(
            this._t('note_optional'),
          )}<input id="note" type="text" maxlength="120" value="${
            editing ? this._escape(editing.note || '') : ''
          }" placeholder="${this._escape(this._t('note_placeholder'))}"></label>
          ${
            formPayers.length
              ? `<div class="split-box">
            <div class="split-head"><strong>${this._escape(
              this._t('expense_split'),
            )}</strong><span id="split-total" class="split-total"></span></div>
            <div class="split-grid">
              ${formPayers
                .map(
                  (p) =>
                    `<label>${this._escape(
                      p.name,
                    )} (%)<input class="split-input" data-payer="${this._escape(
                      p.id,
                    )}" type="number" min="0" max="100" step="0.01" value="${Number(
                      splitMap[p.id] || 0,
                    )}"></label>`,
                )
                .join('')}
            </div>
          </div>`
              : `<div class="form-help">${this._escape(
                  this._t('no_payers'),
                )}</div>`
          }
          <div class="form-help">${this._escape(this._t('form_help'))}</div>
          <div class="buttons"><button class="secondary" id="cancel" type="button">${this._escape(
            this._t('cancel'),
          )}</button><button class="primary" type="submit">${this._escape(
            this._t(editing ? 'save_changes' : 'add'),
          )}</button></div>
        </form>`

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:18px; overflow:hidden; }
        .head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:14px; flex-wrap:wrap; }
        .title { font-size:20px; font-weight:600; }
        .head-actions,.debt-actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
        button,a.paypal { min-height:42px; border:0; border-radius:10px; padding:0 14px; cursor:pointer; font-weight:600; box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; text-decoration:none; }
        button:disabled { opacity:.55; cursor:not-allowed; }
        .primary { background:var(--primary-color); color:var(--text-primary-color,white); }
        .secondary { background:transparent; border:1px solid var(--divider-color); color:var(--primary-text-color); }
        .paypal { background:var(--primary-color); color:var(--text-primary-color,#fff); }
        .small { min-height:36px; font-size:12px; padding:0 11px; }
        .stats { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:8px; margin-bottom:14px; }
        .stat { border:1px solid var(--divider-color); border-radius:12px; padding:11px; min-width:0; }
        .stat span { display:block; color:var(--secondary-text-color); font-size:11px; line-height:1.25; }
        .stat strong { display:block; font-size:18px; margin-top:4px; overflow-wrap:anywhere; }
        form { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; padding:14px; margin-bottom:14px; border:1px solid var(--divider-color); border-radius:12px; }
        .edit-modal { position:fixed; inset:0; z-index:1000; display:flex; align-items:center; justify-content:center; padding:24px; background:rgba(0,0,0,.52); box-sizing:border-box; }
        .edit-modal-shell { width:min(820px,100%); max-height:calc(100vh - 48px); overflow:auto; background:var(--card-background-color); color:var(--primary-text-color); border-radius:16px; box-shadow:0 16px 50px rgba(0,0,0,.35); }
        .edit-modal-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 16px; border-bottom:1px solid var(--divider-color); position:sticky; top:0; z-index:2; background:var(--card-background-color); }
        .edit-modal-head strong { font-size:16px; }
        .edit-modal-head span { display:block; margin-top:2px; color:var(--secondary-text-color); font-size:12px; }
        .edit-modal-close { min-width:42px; width:42px; padding:0; font-size:22px; }
        .edit-modal form { margin:0; border:0; border-radius:0; padding:16px; }
        label { display:flex; flex-direction:column; gap:5px; font-size:12px; color:var(--secondary-text-color); min-width:0; }
        .wide,.split-box,.form-help,.buttons { grid-column:1 / -1; }
        select,input { box-sizing:border-box; width:100%; min-height:44px; border-radius:10px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); padding:8px 10px; font-size:16px; }
        .paid-check { grid-column:1 / -1; display:flex; flex-direction:row; align-items:center; gap:10px; min-height:44px; color:var(--primary-text-color); font-size:13px; }
        .paid-check input { width:20px; min-height:20px; height:20px; margin:0; padding:0; accent-color:var(--success-color,#43a047); }
        .paid-check span { color:var(--secondary-text-color); font-size:12px; }
        .paid-status { width:28px; height:28px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:17px; font-weight:700; }
        .paid-status.yes { color:var(--success-color,#43a047); background:color-mix(in srgb,var(--success-color,#43a047) 14%,transparent); }
        .paid-status.no { visibility:hidden; }
        .split-box { border-top:1px solid var(--divider-color); padding-top:10px; }
        .split-head { display:flex; justify-content:space-between; gap:8px; align-items:center; margin-bottom:8px; }
        .split-head strong { color:var(--primary-text-color); font-size:13px; }
        .split-total { font-size:12px; color:var(--secondary-text-color); }
        .split-total.bad { color:var(--error-color); font-weight:600; }
        .split-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; }
        .buttons { display:flex; justify-content:flex-end; gap:8px; flex-wrap:wrap; }
        .form-help { color:var(--secondary-text-color); font-size:12px; }
        .bill-dates { margin-top:3px; color:var(--secondary-text-color); font-size:11px; }
        .msg { margin:10px 0; font-size:13px; }
        .error { color:var(--error-color); }
        .warning { padding:10px 12px; border-radius:10px; border:1px solid var(--warning-color,#f0ad4e); margin-bottom:12px; }
        .section { margin-top:16px; }
        .section-title { font-size:15px; font-weight:600; margin-bottom:8px; }
        .section-head { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }
        .section-head .section-title { margin-bottom:0; }
        .all-bills-modal,.transfer-modal { position:fixed; inset:0; z-index:900; display:flex; align-items:center; justify-content:center; padding:24px; background:rgba(0,0,0,.52); box-sizing:border-box; }
        .all-bills-shell { width:min(1120px,100%); max-height:calc(100vh - 48px); display:flex; flex-direction:column; overflow:hidden; background:var(--card-background-color); color:var(--primary-text-color); border-radius:16px; box-shadow:0 16px 50px rgba(0,0,0,.35); }
        .transfer-shell { width:min(900px,100%); max-height:calc(100vh - 48px); overflow:auto; background:var(--card-background-color); color:var(--primary-text-color); border-radius:16px; box-shadow:0 16px 50px rgba(0,0,0,.35); }
        .transfer-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 16px; border-bottom:1px solid var(--divider-color); position:sticky; top:0; z-index:2; background:var(--card-background-color); }
        .transfer-head strong { display:block; font-size:17px; }
        .transfer-head span { display:block; margin-top:2px; color:var(--secondary-text-color); font-size:12px; }
        .transfer-body { display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:16px; }
        .transfer-panel { border:1px solid var(--divider-color); border-radius:12px; padding:14px; min-width:0; }
        .transfer-panel h3 { margin:0 0 4px; font-size:15px; }
        .transfer-panel > p { margin:0 0 12px; color:var(--secondary-text-color); font-size:12px; line-height:1.45; }
        .transfer-fields { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
        .transfer-fields .full { grid-column:1 / -1; }
        .transfer-actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
        .transfer-check { display:flex; flex-direction:row; align-items:center; gap:8px; color:var(--primary-text-color); font-size:12px; margin-top:8px; }
        .transfer-check input { width:18px; min-height:18px; height:18px; padding:0; }
        .transfer-file { padding:10px; border:1px dashed var(--divider-color); border-radius:10px; color:var(--secondary-text-color); font-size:12px; margin-top:8px; }
        .transfer-message { margin:0 16px 16px; padding:10px 12px; border-radius:10px; background:color-mix(in srgb,var(--primary-color) 10%,transparent); font-size:12px; white-space:pre-wrap; }
        .all-bills-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 16px; border-bottom:1px solid var(--divider-color); }
        .all-bills-head strong { display:block; font-size:17px; }
        .all-bills-head span { display:block; margin-top:2px; color:var(--secondary-text-color); font-size:12px; }
        .all-bills-body { padding:14px 16px; overflow:auto; min-height:0; }
        .all-bills-toolbar { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; align-items:end; margin-bottom:12px; }
        .all-bills-toolbar .range-hidden { display:none; }
        .all-bills-count { color:var(--secondary-text-color); font-size:12px; margin:4px 0 8px; }
        .all-bills-list { min-height:180px; }
        .all-bills-footer { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; padding:12px 16px; border-top:1px solid var(--divider-color); }
        .pagination { display:flex; align-items:center; gap:8px; }
        .pagination span { color:var(--secondary-text-color); font-size:12px; }
        .all-row { display:grid; grid-template-columns:42px 125px minmax(180px,1fr) 120px auto; gap:10px; align-items:center; padding:10px 0; border-bottom:1px solid var(--divider-color); }
        .all-row:last-child { border-bottom:0; }
        .paid-toggle { display:flex; align-items:center; justify-content:center; cursor:pointer; }
        .paid-toggle input { position:absolute; opacity:0; pointer-events:none; }
        .paid-toggle-mark { width:28px; height:28px; border-radius:8px; border:2px solid var(--divider-color); display:inline-flex; align-items:center; justify-content:center; box-sizing:border-box; font-weight:800; font-size:18px; color:transparent; transition:background .15s,border-color .15s,color .15s; }
        .paid-toggle input:checked + .paid-toggle-mark { background:var(--success-color,#43a047); border-color:var(--success-color,#43a047); color:white; }
        .paid-toggle input:focus-visible + .paid-toggle-mark { outline:2px solid var(--primary-color); outline-offset:2px; }
        .paid-toggle input:disabled + .paid-toggle-mark { opacity:.5; cursor:wait; }
        .settle-box { border:1px solid var(--divider-color); border-radius:12px; padding:12px; }
        .settle-empty { color:var(--secondary-text-color); padding:8px 2px; }
        .settle-empty.ok { color:var(--success-color,#43a047); font-weight:600; }
        .debt-list { display:grid; gap:8px; }
        .debt-row { display:grid; grid-template-columns:minmax(160px,1fr) auto auto; gap:12px; align-items:center; padding:9px 0; border-bottom:1px solid var(--divider-color); }
        .debt-row:last-child { border-bottom:0; }
        .debt-row span { display:block; color:var(--secondary-text-color); font-size:11px; margin-top:3px; }
        .chart-panel { padding:14px 0 6px; border-top:1px solid var(--divider-color); border-bottom:1px solid var(--divider-color); margin-top:16px; }
        .chart-head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:6px; flex-wrap:wrap; }
        .chart-copy strong { display:block; font-size:15px; }
        .chart-copy span { color:var(--secondary-text-color); font-size:12px; }
        .mode { display:flex; border:1px solid var(--divider-color); border-radius:10px; overflow:hidden; }
        .mode button { min-height:34px; border-radius:0; background:transparent; color:var(--primary-text-color); font-size:12px; }
        .mode button.active { background:var(--primary-color); color:var(--text-primary-color,white); }
        .legend { display:flex; gap:12px; align-items:center; margin:8px 0 0; color:var(--secondary-text-color); font-size:11px; flex-wrap:wrap; }
        .legend span { display:flex; gap:5px; align-items:center; }
        .legend-square { width:10px; height:10px; border-radius:2px; display:inline-block; }
        .legend-line { width:18px; border-top:2px dashed var(--warning-color,#f0ad4e); display:inline-block; }
        .chart-scroll { width:100%; overflow-x:auto; }
        .chart { width:100%; min-width:760px; height:auto; overflow:visible; }
        .grid { stroke:var(--divider-color); stroke-width:1; opacity:.7; }
        .axis-value,.axis-label { fill:var(--secondary-text-color); font-size:10px; }
        .stack-segment { opacity:.86; stroke:var(--card-background-color); stroke-width:.6; }
        .forecast-line { fill:none; stroke:var(--warning-color,#f0ad4e); stroke-width:3; stroke-dasharray:7 6; stroke-linecap:round; stroke-linejoin:round; }
        .forecast-dot { fill:var(--card-background-color); stroke:var(--warning-color,#f0ad4e); stroke-width:2; }
        .forecast-divider { stroke:var(--secondary-text-color); stroke-width:1; stroke-dasharray:3 5; opacity:.5; }
        .empty-chart { color:var(--secondary-text-color); padding:24px 4px; text-align:center; }
        .upcoming-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; }
        .upcoming-item { border:1px solid var(--divider-color); border-radius:10px; padding:10px; display:grid; gap:4px; }
        .upcoming-item span { color:var(--secondary-text-color); font-size:12px; }
        .upcoming-item strong { display:flex; justify-content:space-between; gap:8px; }
        .list { margin-top:4px; }
        .row { display:grid; grid-template-columns:125px minmax(180px,1fr) 120px auto; gap:10px; align-items:center; padding:10px 0; border-bottom:1px solid var(--divider-color); }
        .date,.note,.competence,.payer-line { color:var(--secondary-text-color); font-size:12px; }
        .amount { text-align:right; font-weight:600; }
        .actions { display:flex; gap:6px; }
        .icon { min-width:34px; min-height:34px; padding:0 8px; background:transparent; border:1px solid var(--divider-color); color:var(--primary-text-color); }
        .settlement { display:grid; grid-template-columns:1fr auto auto; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--divider-color); }
        .settlement span { color:var(--secondary-text-color); font-size:12px; }
        .usage-line { color:var(--secondary-text-color); font-size:12px; margin-top:2px; }
        .savings-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:10px; }
        .savings-card { border:1px solid var(--divider-color); border-radius:12px; padding:12px; display:grid; gap:8px; }
        .savings-card-head { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
        .savings-card-head span,.savings-meta { color:var(--secondary-text-color); font-size:12px; }
        .savings-value { font-size:20px; font-weight:700; }
        .savings-value.positive { color:var(--success-color,#43a047); }
        .savings-value.negative { color:var(--error-color,#db4437); }
        .savings-comparison { display:grid; grid-template-columns:1fr auto 1fr; gap:8px; align-items:center; font-size:12px; }
        .savings-comparison > div { min-width:0; }
        .savings-comparison b { display:block; overflow-wrap:anywhere; }
        @media (max-width:1000px) { .stats { grid-template-columns:repeat(3,minmax(0,1fr)); } .debt-row { grid-template-columns:1fr auto; } .debt-actions { grid-column:1 / -1; } }
        @media (max-width:760px) { .transfer-body { grid-template-columns:1fr; } .stats { grid-template-columns:repeat(2,minmax(0,1fr)); } form { grid-template-columns:1fr 1fr; } .wide,.split-box,.form-help,.buttons { grid-column:1 / -1; } .all-bills-toolbar { grid-template-columns:1fr 1fr; } .all-row { grid-template-columns:42px 110px 1fr auto; } .all-row .amount { grid-column:3; text-align:left; } .all-row .actions { grid-column:4; grid-row:1 / span 2; } }
        @media (max-width:560px) { ha-card { padding:13px; } .edit-modal,.all-bills-modal,.transfer-modal { padding:8px; align-items:flex-end; } .edit-modal-shell,.all-bills-shell,.transfer-shell { max-height:calc(100vh - 16px); border-radius:16px 16px 8px 8px; } .stats { grid-template-columns:1fr; } form { grid-template-columns:1fr; } .wide,.split-box,.form-help,.buttons { grid-column:1; } .row { grid-template-columns:1fr auto; } .row .amount { grid-column:1; text-align:left; } .row .actions { grid-column:2; grid-row:1 / span 2; } .debt-row { grid-template-columns:1fr; } .debt-actions { grid-column:1; } .settlement { grid-template-columns:1fr auto; } .all-bills-toolbar { grid-template-columns:1fr; } .all-row { grid-template-columns:36px 1fr auto; } .all-row .all-date { grid-column:2; } .all-row .all-main { grid-column:2; } .all-row .amount { grid-column:2; text-align:left; } .all-row .actions { grid-column:3; grid-row:1 / span 3; } }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${this._escape(
            this._config.title || this._t('card_title'),
          )}</div>
          <div class="head-actions">
            <button class="secondary" id="open-transfer" type="button">⇅ ${this._escape(
              this._t('import_export'),
            )}</button>
            <button class="secondary" id="settings" type="button">⚙ ${this._escape(
              this._t('settings'),
            )}</button>
            <button class="primary" id="open-form" type="button" ${
              activeCategories.length ? '' : 'disabled'
            }>+ ${this._escape(this._t('add_bill'))}</button>
          </div>
        </div>
        <div class="stats">
          <div class="stat"><span>${this._escape(
            this._t('paid_this_month'),
          )}</span><strong>${this._money(summary.current_month)}</strong></div>
          <div class="stat"><span>${this._escape(
            this._t('average_6_months'),
          )}</span><strong>${this._money(
            summary.average_6_months,
          )}</strong></div>
          <div class="stat"><span>${this._escape(
            this._t('next_month_estimate'),
          )}</span><strong>${this._money(
            summary.next_month_estimate,
          )}</strong></div>
          <div class="stat"><span>${this._escape(
            this._t('normalized_monthly_cost'),
          )}</span><strong>${this._money(
            summary.normalized_current_month,
          )}</strong></div>
          <div class="stat"><span>${this._escape(
            this._t('bills_to_pay'),
          )}</span><strong>${this._money(
            summary.unpaid_total ?? summary.outstanding_total,
          )}</strong></div>
        </div>
        ${
          !activeCategories.length
            ? `<div class="warning">${this._escape(
                this._t('no_active_types'),
              )}</div>`
            : ''
        }
        ${
          editing
            ? `<div class="edit-modal" id="edit-modal" role="presentation">
          <div class="edit-modal-shell" role="dialog" aria-modal="true" aria-labelledby="edit-modal-title">
            <div class="edit-modal-head">
              <div><strong id="edit-modal-title">${this._escape(
                this._t('edit_bill'),
              )}</strong><span>${this._escape(
                this._expenseCategoryLabel(editing),
              )} · ${this._monthLabel(
                editing.paid_year,
                editing.paid_month,
              )}</span></div>
              <button class="secondary edit-modal-close" id="modal-close" type="button" aria-label="${this._escape(
                this._t('close_edit'),
              )}">×</button>
            </div>
            ${expenseFormHtml}
          </div>
        </div>`
            : this._formOpen
              ? expenseFormHtml
              : ''
        }
        ${
          this._error
            ? `<div class="msg error">${this._escape(this._error)}</div>`
            : ''
        }

        <div class="section"><div class="section-title">${this._escape(
          this._t('reimbursements'),
        )}</div><div class="settle-box">${this._renderDebts()}</div></div>

        <div class="chart-panel">
          <div class="chart-head">
            <div class="chart-copy"><strong>${this._escape(
              this._t('trend_forecast'),
            )}</strong><span>${this._escape(
              this._t(
                this._chartMode === 'cashflow'
                  ? 'cashflow_help'
                  : 'normalized_help',
              ),
            )}</span></div>
            <div class="mode"><button type="button" data-mode="cashflow" class="${
              this._chartMode === 'cashflow' ? 'active' : ''
            }">${this._escape(
              this._t('payments'),
            )}</button><button type="button" data-mode="normalized" class="${
              this._chartMode === 'normalized' ? 'active' : ''
            }">${this._escape(this._t('monthly_cost'))}</button></div>
          </div>
          <div class="legend">${this._chartLegend()}</div>
          ${this._chart()}
        </div>

        <div class="section">
          <div class="section-title">${this._escape(
            this._t('savings_title'),
          )}</div>
          ${
            contractSavings.length
              ? `<div class="savings-grid">${contractSavings
                  .map((x) => {
                    const saving = Number(x.estimated_savings || 0)
                    const oldLabel =
                      [x.old_provider, x.old_contract]
                        .filter(Boolean)
                        .join(' · ') || this._t('previous_contract')
                    const newLabel =
                      [x.new_provider, x.new_contract]
                        .filter(Boolean)
                        .join(' · ') || this._t('current_contract')
                    return `<div class="savings-card">
              <div class="savings-card-head"><div><strong>${this._escape(
                this._expenseCategoryLabel(x),
              )}</strong><span>${this._escape(x.unit)} · ${this._escape(
                this._t('bills_with_consumption', {
                  old: Number(x.old_bill_count || 0),
                  new: Number(x.new_bill_count || 0),
                }),
              )}</span></div><div class="savings-value ${
                saving >= 0 ? 'positive' : 'negative'
              }">${saving >= 0 ? '+' : ''}${this._money(saving)}</div></div>
              <div class="savings-comparison"><div><span>${this._escape(
                this._t('savings_before'),
              )}</span><b>${this._escape(oldLabel)}</b><span>${this._escape(
                this._unitPrice(x.old_unit_price, x.unit),
              )}</span></div><span>→</span><div><span>${this._escape(
                this._t('savings_after'),
              )}</span><b>${this._escape(newLabel)}</b><span>${this._escape(
                this._unitPrice(x.new_unit_price, x.unit),
              )}</span></div></div>
              <div class="savings-meta">${this._escape(
                this._t('equivalent_saving', {
                  kind: this._t(saving >= 0 ? 'saving' : 'increase'),
                  percent: Math.abs(
                    Number(x.estimated_savings_percent || 0),
                  ).toFixed(1),
                  old_amount: this._money(x.old_avg_amount),
                  new_amount: this._money(x.new_avg_amount),
                  old_consumption: Number(
                    x.old_avg_consumption || 0,
                  ).toLocaleString(this._locale(), {
                    maximumFractionDigits: 4,
                  }),
                  new_consumption: Number(
                    x.new_avg_consumption || 0,
                  ).toLocaleString(this._locale(), {
                    maximumFractionDigits: 4,
                  }),
                  unit: x.unit,
                  change: `${
                    Number(x.consumption_change_percent || 0) >= 0 ? '+' : ''
                  }${Number(x.consumption_change_percent || 0).toFixed(1)}`,
                }),
              )}</div>
            </div>`
                  })
                  .join('')}</div>`
              : `<div class="msg">${this._escape(this._t('savings_empty'))}</div>`
          }
        </div>
        <div class="section"><div class="section-title">${this._escape(
          this._t('upcoming_title'),
        )}</div>
          ${
            upcoming.length
              ? `<div class="upcoming-grid">${upcoming
                  .map(
                    (x) =>
                      `<div class="upcoming-item"><span>${
                        this._monthNames()[Number(x.month) - 1]
                      } ${x.year}</span><strong><b>${this._escape(
                        this._expenseCategoryLabel(x),
                      )}</b><b>${this._money(x.amount)}</b></strong></div>`,
                  )
                  .join('')}</div>`
              : `<div class="msg">${this._escape(
                  this._t('upcoming_empty'),
                )}</div>`
          }
        </div>

        ${
          settlements.length
            ? `<div class="section"><div class="section-title">${this._escape(
                this._t('recent_settlements'),
              )}</div>${settlements
                .map(
                  (x) =>
                    `<div class="settlement"><div><strong>${this._escape(
                      x.from_name,
                    )} → ${this._escape(x.to_name)}</strong><span>${new Date(
                      x.created_at,
                    ).toLocaleString(this._locale())}${
                      x.note ? ` · ${this._escape(x.note)}` : ''
                    }</span></div><b>${this._money(
                      x.amount,
                    )}</b><button class="icon delete-settlement" type="button" data-id="${this._escape(
                      x.id,
                    )}" title="${this._escape(
                      this._t('cancel_settlement'),
                    )}">×</button></div>`,
                )
                .join('')}</div>`
            : ''
        }

        <div class="section">
          <div class="section-head">
            <div class="section-title">${this._escape(
              this._t('current_month_bills', {
                month: this._monthNames()[now.month - 1],
                year: now.year,
                count: currentMonthExpenses.length,
              }),
            )}</div>
            <div class="head-actions">
              <button class="secondary small" id="toggle-current-bills" type="button">${this._escape(
                this._currentMonthBillsOpen
                  ? this._t('hide')
                  : this._t('show_count', {
                      count: currentMonthExpenses.length,
                    }),
              )}</button>
              <button class="secondary small" id="open-all-bills" type="button">${this._escape(
                this._t('all_bills_count', { count: allExpenses.length }),
              )}</button>
            </div>
          </div>
          ${
            this._currentMonthBillsOpen
              ? `<div class="list">
            ${
              currentMonthExpenses.length
                ? currentMonthExpenses
                    .map(
                      (x) => `<div class="row">
              <div><strong>${this._monthLabel(
                x.paid_year,
                x.paid_month,
              )}</strong><div class="date">${this._escape(
                this._periodText(x),
              )}</div>${this._periodBadgeText(x) ? `<div class="bill-dates">${this._escape(this._periodBadgeText(x))}</div>` : ''}</div>
              <div><strong>${this._escape(
                this._expenseCategoryLabel(x),
              )}</strong><div class="payer-line">${
                x.payer
                  ? this._escape(this._t('payer_prefix', { name: x.payer }))
                  : ''
              }${this._escape(this._splitText(x))}</div>${
                this._usageText(x)
                  ? `<div class="usage-line">${this._escape(
                      this._usageText(x),
                    )}</div>`
                  : ''
              }${
                this._expenseDatesText(x)
                  ? `<div class="bill-dates">${this._escape(
                      this._expenseDatesText(x),
                    )}</div>`
                  : ''
              }${
                x.note ? `<div class="note">${this._escape(x.note)}</div>` : ''
              }</div>
              <div class="amount"><span class="paid-status ${
                x.paid ? 'yes' : 'no'
              }" title="${this._escape(
                this._t(x.paid ? 'bill_paid' : 'bill_unpaid'),
              )}" aria-label="${this._escape(
                this._t(x.paid ? 'bill_paid' : 'bill_unpaid'),
              )}">✓</span> ${this._money(x.amount)}</div>
              <div class="actions"><button class="icon edit" type="button" data-id="${this._escape(
                x.id,
              )}" title="${this._escape(
                this._t('edit'),
              )}">✎</button><button class="icon delete" type="button" data-id="${this._escape(
                x.id,
              )}" title="${this._escape(this._t('delete'))}">×</button></div>
            </div>`,
                    )
                    .join('')
                : `<div class="msg">${this._escape(
                    this._t('no_current_bills'),
                  )}</div>`
            }
          </div>`
              : ''
          }
        </div>
        ${
          this._allBillsOpen
            ? `<div class="all-bills-modal" id="all-bills-modal" role="presentation">
          <div class="all-bills-shell" role="dialog" aria-modal="true" aria-labelledby="all-bills-title">
            <div class="all-bills-head">
              <div><strong id="all-bills-title">${this._escape(
                this._t('all_bills'),
              )}</strong><span>${this._escape(
                this._t('results_of', {
                  filtered: filteredAllExpenses.length,
                  total: allExpenses.length,
                }),
              )}</span></div>
              <button class="secondary edit-modal-close" id="all-bills-close" type="button" aria-label="${this._escape(
                this._t('close_bill_list'),
              )}">×</button>
            </div>
            <div class="all-bills-body">
              <div class="all-bills-toolbar">
                <label>${this._escape(this._t('type'))}
                  <select id="all-bills-category">
                    <option value="all" ${
                      this._allBillsCategory === 'all' ? 'selected' : ''
                    }>${this._escape(this._t('all_types'))}</option>
                    ${allBillCategories
                      .map(
                        (c) =>
                          `<option value="${this._escape(c.id)}" ${
                            c.id === this._allBillsCategory ? 'selected' : ''
                          }>${this._escape(this._categoryLabel(c))}</option>`,
                      )
                      .join('')}
                  </select>
                </label>
                <label>${this._escape(this._t('status'))}
                  <select id="all-bills-status">
                    <option value="all" ${
                      this._allBillsStatus === 'all' ? 'selected' : ''
                    }>${this._escape(this._t('all'))}</option>
                    <option value="unpaid" ${
                      this._allBillsStatus === 'unpaid' ? 'selected' : ''
                    }>${this._escape(this._t('unpaid'))}</option>
                    <option value="paid" ${
                      this._allBillsStatus === 'paid' ? 'selected' : ''
                    }>${this._escape(this._t('paid'))}</option>
                  </select>
                </label>
                <label>${this._escape(this._t('period'))}
                  <select id="all-bills-time-mode">
                    <option value="all" ${
                      this._allBillsTimeMode === 'all' ? 'selected' : ''
                    }>${this._escape(this._t('all_history'))}</option>
                    <option value="year" ${
                      this._allBillsTimeMode === 'year' ? 'selected' : ''
                    }>${this._escape(this._t('by_year'))}</option>
                    <option value="range" ${
                      this._allBillsTimeMode === 'range' ? 'selected' : ''
                    }>${this._escape(this._t('month_range'))}</option>
                  </select>
                </label>
                ${
                  this._allBillsTimeMode === 'year'
                    ? `<label>${this._escape(this._t('year'))}
                  <select id="all-bills-year">
                    <option value="all" ${
                      this._allBillsYear === 'all' ? 'selected' : ''
                    }>${this._escape(this._t('all_years'))}</option>
                    ${allBillYears
                      .map(
                        (year) =>
                          `<option value="${year}" ${
                            String(year) === String(this._allBillsYear)
                              ? 'selected'
                              : ''
                          }>${year}</option>`,
                      )
                      .join('')}
                  </select>
                </label>`
                    : ''
                }
                ${
                  this._allBillsTimeMode === 'range'
                    ? `<label>${this._escape(
                        this._t('from'),
                      )}<input id="all-bills-from" type="month" value="${this._escape(
                        this._allBillsFrom,
                      )}"></label><label>${this._escape(
                        this._t('to'),
                      )}<input id="all-bills-to" type="month" value="${this._escape(
                        this._allBillsTo,
                      )}"></label>`
                    : ''
                }
                <label>${this._escape(this._t('per_page'))}
                  <select id="all-bills-page-size">
                    ${[10, 20, 50]
                      .map(
                        (size) =>
                          `<option value="${size}" ${
                            Number(this._allBillsPageSize) === size
                              ? 'selected'
                              : ''
                          }>${size}</option>`,
                      )
                      .join('')}
                  </select>
                </label>
              </div>
              <div class="all-bills-count">${
                filteredAllExpenses.length
                  ? this._escape(
                      this._t('range_count', {
                        start: allBillsStart + 1,
                        end: Math.min(
                          allBillsStart + this._allBillsPageSize,
                          filteredAllExpenses.length,
                        ),
                        total: filteredAllExpenses.length,
                      }),
                    )
                  : this._escape(this._t('no_bills'))
              }</div>
              <div class="all-bills-list">
                ${
                  pagedAllExpenses.length
                    ? pagedAllExpenses
                        .map(
                          (x) => `<div class="all-row">
                  <label class="paid-toggle" title="${this._escape(
                    this._t(x.paid ? 'mark_unpaid' : 'mark_paid'),
                  )}">
                    <input class="bill-paid-toggle" type="checkbox" data-id="${this._escape(
                      x.id,
                    )}" ${x.paid ? 'checked' : ''} aria-label="${this._escape(
                      this._t(x.paid ? 'bill_paid' : 'bill_unpaid'),
                    )}">
                    <span class="paid-toggle-mark">✓</span>
                  </label>
                  <div class="all-date"><strong>${this._monthLabel(
                    x.paid_year,
                    x.paid_month,
                  )}</strong><div class="date">${this._escape(
                    this._periodText(x),
                  )}</div></div>
                  <div class="all-main"><strong>${this._escape(
                    this._expenseCategoryLabel(x),
                  )}</strong><div class="payer-line">${
                    x.payer
                      ? this._escape(this._t('payer_prefix', { name: x.payer }))
                      : ''
                  }${this._escape(this._splitText(x))}</div>${
                    this._usageText(x)
                      ? `<div class="usage-line">${this._escape(
                          this._usageText(x),
                        )}</div>`
                      : ''
                  }${
                    this._expenseDatesText(x)
                      ? `<div class="bill-dates">${this._escape(
                          this._expenseDatesText(x),
                        )}</div>`
                      : ''
                  }${
                    x.note
                      ? `<div class="note">${this._escape(x.note)}</div>`
                      : ''
                  }</div>
                  <div class="amount">${this._money(x.amount)}</div>
                  <div class="actions"><button class="icon edit" type="button" data-id="${this._escape(
                    x.id,
                  )}" title="${this._escape(
                    this._t('edit'),
                  )}">✎</button><button class="icon delete" type="button" data-id="${this._escape(
                    x.id,
                  )}" title="${this._escape(
                    this._t('delete'),
                  )}">×</button></div>
                </div>`,
                        )
                        .join('')
                    : `<div class="msg">${this._escape(
                        this._t('no_filtered_bills'),
                      )}</div>`
                }
              </div>
            </div>
            <div class="all-bills-footer">
              <span class="all-bills-count">${this._escape(
                this._t('page_of', {
                  page: this._allBillsPage,
                  pages: totalAllBillPages,
                }),
              )}</span>
              <div class="pagination">
                <button class="secondary small all-bills-page" type="button" data-page="${
                  this._allBillsPage - 1
                }" ${
                  this._allBillsPage <= 1 ? 'disabled' : ''
                }>← ${this._escape(this._t('previous'))}</button>
                <button class="secondary small all-bills-page" type="button" data-page="${
                  this._allBillsPage + 1
                }" ${
                  this._allBillsPage >= totalAllBillPages ? 'disabled' : ''
                }>${this._escape(this._t('next'))} →</button>
              </div>
            </div>
          </div>
        </div>`
            : ''
        }
        ${
          this._transferOpen
            ? `<div class="transfer-modal" id="transfer-modal" role="presentation">
          <div class="transfer-shell" role="dialog" aria-modal="true" aria-labelledby="transfer-title">
            <div class="transfer-head">
              <div><strong id="transfer-title">${this._escape(
                this._t('import_export_title'),
              )}</strong><span>${this._escape(
                this._t('import_export_help'),
              )}</span></div>
              <button class="secondary edit-modal-close" id="transfer-close" type="button" aria-label="${this._escape(
                this._t('close_import_export'),
              )}">×</button>
            </div>
            <div class="transfer-body">
              <section class="transfer-panel">
                <h3>${this._escape(this._t('import_csv'))}</h3>
                <p>${this._escape(this._t('import_csv_help'))}</p>
                <label>${this._escape(
                  this._t('csv_file'),
                )}<input id="import-csv-file" type="file" accept=".csv,text/csv"></label>
                <div class="transfer-file" id="import-file-label">${
                  this._importFileName
                    ? this._escape(this._importFileName)
                    : this._escape(this._t('no_file'))
                }</div>
                <label class="transfer-check"><input id="import-create-categories" type="checkbox" checked> ${this._escape(
                  this._t('create_missing_types'),
                )}</label>
                <label class="transfer-check"><input id="import-create-payers" type="checkbox" checked> ${this._escape(
                  this._t('create_missing_payers'),
                )}</label>
                <div class="transfer-actions">
                  <button class="secondary small" id="download-template" type="button" ${
                    this._transferBusy ? 'disabled' : ''
                  }>${this._escape(this._t('download_csv_template'))}</button>
                  <button class="primary small" id="import-csv" type="button" ${
                    !this._importCsvText || this._transferBusy ? 'disabled' : ''
                  }>${this._escape(
                    this._t(this._transferBusy ? 'wait' : 'import'),
                  )}</button>
                </div>
              </section>
              <section class="transfer-panel">
                <h3>${this._escape(this._t('export_history'))}</h3>
                <p>${this._escape(this._t('export_help'))}</p>
                <div class="transfer-fields">
                  <label>${this._escape(
                    this._t('format'),
                  )}<select id="export-format">
                    <option value="csv" ${
                      this._exportFormat === 'csv' ? 'selected' : ''
                    }>CSV</option>
                    <option value="xlsx" ${
                      this._exportFormat === 'xlsx' ? 'selected' : ''
                    }>Excel (.xlsx)</option>
                    <option value="pdf" ${
                      this._exportFormat === 'pdf' ? 'selected' : ''
                    }>${this._escape(this._t('pdf_report'))}</option>
                  </select></label>
                  <label>${this._escape(
                    this._t('status'),
                  )}<select id="export-status">
                    <option value="all" ${
                      this._exportStatus === 'all' ? 'selected' : ''
                    }>${this._escape(this._t('all'))}</option>
                    <option value="unpaid" ${
                      this._exportStatus === 'unpaid' ? 'selected' : ''
                    }>${this._escape(this._t('unpaid'))}</option>
                    <option value="paid" ${
                      this._exportStatus === 'paid' ? 'selected' : ''
                    }>${this._escape(this._t('paid'))}</option>
                  </select></label>
                  <label>${this._escape(
                    this._t('from'),
                  )}<input id="export-from" type="month" value="${this._escape(
                    this._exportFrom,
                  )}"></label>
                  <label>${this._escape(
                    this._t('to'),
                  )}<input id="export-to" type="month" value="${this._escape(
                    this._exportTo,
                  )}"></label>
                  <label class="full">${this._escape(
                    this._t('type'),
                  )}<select id="export-category">
                    <option value="all" ${
                      this._exportCategory === 'all' ? 'selected' : ''
                    }>${this._escape(this._t('all_types'))}</option>
                    ${allBillCategories
                      .map(
                        (c) =>
                          `<option value="${this._escape(c.id)}" ${
                            c.id === this._exportCategory ? 'selected' : ''
                          }>${this._escape(this._categoryLabel(c))}</option>`,
                      )
                      .join('')}
                  </select></label>
                  ${
                    this._exportFormat === 'pdf'
                      ? `<label class="full">${this._escape(
                          this._t('report_trend'),
                        )}<select id="export-trend">
                    <option value="both" ${
                      this._exportTrend === 'both' ? 'selected' : ''
                    }>${this._escape(this._t('payments_plus_monthly'))}</option>
                    <option value="payments" ${
                      this._exportTrend === 'payments' ? 'selected' : ''
                    }>${this._escape(this._t('payments_only'))}</option>
                    <option value="normalized" ${
                      this._exportTrend === 'normalized' ? 'selected' : ''
                    }>${this._escape(this._t('normalized_only'))}</option>
                  </select></label>`
                      : ''
                  }
                </div>
                <div class="transfer-actions"><button class="primary" id="export-data" type="button" ${
                  this._transferBusy ? 'disabled' : ''
                }>${this._escape(
                  this._t(this._transferBusy ? 'generating' : 'export'),
                )}</button></div>
              </section>
            </div>
            ${
              this._transferMessage
                ? `<div class="transfer-message">${this._escape(
                    this._transferMessage,
                  )}</div>`
                : ''
            }
          </div>
        </div>`
            : ''
        }
      </ha-card>`

    this.shadowRoot
      .getElementById('open-form')
      ?.addEventListener('click', () => {
        this._editing = null
        this._formOpen = true
        this._render()
      })
    this.shadowRoot
      .getElementById('settings')
      ?.addEventListener('click', () => this._openSettings())
    this.shadowRoot
      .getElementById('open-transfer')
      ?.addEventListener('click', () => this._openTransfer())
    this.shadowRoot
      .getElementById('transfer-close')
      ?.addEventListener('click', () => this._closeTransfer())
    this.shadowRoot
      .getElementById('transfer-modal')
      ?.addEventListener('click', (event) => {
        if (event.target?.id === 'transfer-modal') this._closeTransfer()
      })
    this.shadowRoot
      .getElementById('transfer-modal')
      ?.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') this._closeTransfer()
      })
    this.shadowRoot
      .getElementById('import-csv-file')
      ?.addEventListener('change', (event) =>
        this._readImportFile(event.target),
      )
    this.shadowRoot
      .getElementById('download-template')
      ?.addEventListener('click', () => this._downloadTemplate())
    this.shadowRoot
      .getElementById('import-csv')
      ?.addEventListener('click', () => this._importCsv())
    this.shadowRoot
      .getElementById('export-data')
      ?.addEventListener('click', () => this._exportData())
    this.shadowRoot
      .getElementById('export-format')
      ?.addEventListener('change', (event) => {
        this._exportFormat = event.target.value || 'csv'
        this._render()
      })
    this.shadowRoot
      .getElementById('export-status')
      ?.addEventListener('change', (event) => {
        this._exportStatus = event.target.value || 'all'
      })
    this.shadowRoot
      .getElementById('export-category')
      ?.addEventListener('change', (event) => {
        this._exportCategory = event.target.value || 'all'
      })
    this.shadowRoot
      .getElementById('export-from')
      ?.addEventListener('change', (event) => {
        this._exportFrom = event.target.value || ''
      })
    this.shadowRoot
      .getElementById('export-to')
      ?.addEventListener('change', (event) => {
        this._exportTo = event.target.value || ''
      })
    this.shadowRoot
      .getElementById('export-trend')
      ?.addEventListener('change', (event) => {
        this._exportTrend = event.target.value || 'both'
      })
    this.shadowRoot
      .getElementById('expense-form')
      ?.addEventListener('submit', (e) => this._submit(e))
    this.shadowRoot.getElementById('cancel')?.addEventListener('click', () => {
      this._editing = null
      this._formOpen = false
      this._render()
    })
    this.shadowRoot
      .getElementById('modal-close')
      ?.addEventListener('click', () => this._closeEditModal())
    this.shadowRoot
      .getElementById('edit-modal')
      ?.addEventListener('click', (event) => {
        if (event.target?.id === 'edit-modal') this._closeEditModal()
      })
    this.shadowRoot
      .getElementById('edit-modal')
      ?.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') this._closeEditModal()
      })
    this.shadowRoot
      .getElementById('category')
      ?.addEventListener('change', () => this._applyCategoryDefaults())
    this.shadowRoot
      .getElementById('paid-month')
      ?.addEventListener('change', () => this._autoPeriod())
    this.shadowRoot
      .querySelectorAll('.split-input')
      .forEach((input) =>
        input.addEventListener('input', () => this._updateSplitTotal()),
      )
    this._updateSplitTotal()
    this.shadowRoot.querySelectorAll('.mode button').forEach((btn) =>
      btn.addEventListener('click', () => {
        this._chartMode =
          btn.dataset.mode === 'normalized' ? 'normalized' : 'cashflow'
        this._render()
      }),
    )
    this.shadowRoot
      .getElementById('toggle-current-bills')
      ?.addEventListener('click', () => {
        this._currentMonthBillsOpen = !this._currentMonthBillsOpen
        this._render()
      })
    this.shadowRoot
      .getElementById('open-all-bills')
      ?.addEventListener('click', () => {
        this._allBillsOpen = true
        this._allBillsPage = 1
        this._render()
        const modal = this.shadowRoot?.getElementById('all-bills-modal')
        if (modal) {
          modal.tabIndex = -1
          modal.focus()
        }
      })
    this.shadowRoot
      .getElementById('all-bills-close')
      ?.addEventListener('click', () => this._closeAllBillsModal())
    this.shadowRoot
      .getElementById('all-bills-modal')
      ?.addEventListener('click', (event) => {
        if (event.target?.id === 'all-bills-modal') this._closeAllBillsModal()
      })
    this.shadowRoot
      .getElementById('all-bills-modal')
      ?.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !this._editing) this._closeAllBillsModal()
      })
    this.shadowRoot
      .getElementById('all-bills-category')
      ?.addEventListener('change', (event) => {
        this._allBillsCategory = event.target.value || 'all'
        this._allBillsPage = 1
        this._render()
      })
    this.shadowRoot
      .getElementById('all-bills-status')
      ?.addEventListener('change', (event) => {
        this._allBillsStatus = ['all', 'unpaid', 'paid'].includes(
          event.target.value,
        )
          ? event.target.value
          : 'all'
        this._allBillsPage = 1
        this._render()
      })
    this.shadowRoot
      .getElementById('all-bills-time-mode')
      ?.addEventListener('change', (event) => {
        this._allBillsTimeMode = event.target.value || 'all'
        this._allBillsPage = 1
        this._render()
      })
    this.shadowRoot
      .getElementById('all-bills-year')
      ?.addEventListener('change', (event) => {
        this._allBillsYear = event.target.value || 'all'
        this._allBillsPage = 1
        this._render()
      })
    this.shadowRoot
      .getElementById('all-bills-from')
      ?.addEventListener('change', (event) => {
        this._allBillsFrom = event.target.value || ''
        this._allBillsPage = 1
        this._render()
      })
    this.shadowRoot
      .getElementById('all-bills-to')
      ?.addEventListener('change', (event) => {
        this._allBillsTo = event.target.value || ''
        this._allBillsPage = 1
        this._render()
      })
    this.shadowRoot
      .getElementById('all-bills-page-size')
      ?.addEventListener('change', (event) => {
        this._allBillsPageSize = [10, 20, 50].includes(
          Number(event.target.value),
        )
          ? Number(event.target.value)
          : 10
        this._allBillsPage = 1
        this._render()
      })
    this.shadowRoot.querySelectorAll('.all-bills-page').forEach((btn) =>
      btn.addEventListener('click', () => {
        this._allBillsPage = Math.max(1, Number(btn.dataset.page || 1))
        this._render()
      }),
    )
    this.shadowRoot
      .querySelectorAll('.bill-paid-toggle')
      .forEach((input) =>
        input.addEventListener('change', () => this._togglePaid(input)),
      )
    this.shadowRoot
      .querySelectorAll('.edit')
      .forEach((btn) =>
        btn.addEventListener('click', () => this._startEdit(btn.dataset.id)),
      )
    this.shadowRoot
      .querySelectorAll('.delete')
      .forEach((btn) =>
        btn.addEventListener('click', () => this._delete(btn.dataset.id)),
      )
    this.shadowRoot
      .querySelectorAll('.settle')
      .forEach((btn) => btn.addEventListener('click', () => this._settle(btn)))
    this.shadowRoot
      .querySelectorAll('.delete-settlement')
      .forEach((btn) =>
        btn.addEventListener('click', () =>
          this._deleteSettlement(btn.dataset.id),
        ),
      )
  }

  _openTransfer() {
    const expenses = this._data?.expenses || []
    if (!this._exportFrom && expenses.length) {
      const oldest = expenses.reduce((best, item) => {
        const value = this._monthValue(item.paid_year, item.paid_month)
        return !best || value < best ? value : best
      }, '')
      this._exportFrom = oldest
    }
    if (!this._exportTo) {
      const now = this._defaultDate()
      const latest = expenses.reduce(
        (best, item) => {
          const value = this._monthValue(item.paid_year, item.paid_month)
          return !best || value > best ? value : best
        },
        this._monthValue(now.year, now.month),
      )
      this._exportTo = latest
    }
    this._transferMessage = ''
    this._transferOpen = true
    this._render()
  }

  _closeTransfer() {
    if (this._transferBusy) return
    this._transferOpen = false
    this._transferMessage = ''
    this._render()
  }

  async _readImportFile(input) {
    const file = input?.files?.[0]
    if (!file) {
      this._importCsvText = ''
      this._importFileName = ''
      this._render()
      return
    }
    if (file.size > 5_000_000) {
      this._importCsvText = ''
      this._importFileName = file.name
      this._transferMessage = this._t('csv_too_large')
      this._render()
      return
    }
    try {
      this._importCsvText = await file.text()
      this._importFileName = file.name
      this._transferMessage = this._t('csv_ready', { name: file.name })
    } catch (err) {
      this._importCsvText = ''
      this._transferMessage = billyErrorText(this._hass, err)
    }
    this._render()
  }

  _downloadPayload(result) {
    if (!result?.content_base64) throw new Error(this._t('empty_export'))
    const binary = atob(result.content_base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
    const blob = new Blob([bytes], {
      type: result.mime_type || 'application/octet-stream',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = result.filename || 'billy-export'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  async _downloadTemplate() {
    if (!this._hass || this._transferBusy) return
    this._transferBusy = true
    this._transferMessage = ''
    this._render()
    try {
      const result = await this._hass.callWS({
        type: 'bill_tracker/export_template',
      })
      this._downloadPayload(result)
      this._transferMessage = this._t('template_downloaded')
    } catch (err) {
      this._transferMessage = this._t('template_error', {
        error: billyErrorText(this._hass, err),
      })
    } finally {
      this._transferBusy = false
      this._render()
    }
  }

  async _importCsv() {
    if (!this._hass || !this._importCsvText || this._transferBusy) return
    const createCategories = Boolean(
      this.shadowRoot.getElementById('import-create-categories')?.checked,
    )
    const createPayers = Boolean(
      this.shadowRoot.getElementById('import-create-payers')?.checked,
    )
    this._transferBusy = true
    this._transferMessage = this._t('importing')
    this._render()
    try {
      const result = await this._hass.callWS({
        type: 'bill_tracker/import_csv',
        content: this._importCsvText,
        create_missing_categories: createCategories,
        create_missing_payers: createPayers,
      })
      const parts = [
        this._t('imported', { count: Number(result.imported || 0) }),
        this._t('skipped', { count: Number(result.skipped || 0) }),
        this._t('new_types', { count: Number(result.created_categories || 0) }),
        this._t('new_payers', { count: Number(result.created_payers || 0) }),
      ]
      if (Number(result.error_count || 0))
        parts.push(
          `${this._t('errors', { count: Number(result.error_count || 0) })}\n${(
            result.errors || []
          ).join('\n')}`,
        )
      this._transferMessage = parts.join(' · ')
      this._importCsvText = ''
      this._importFileName = ''
      await this._load()
      this._transferOpen = true
    } catch (err) {
      this._transferMessage = this._t('import_failed', {
        error: billyErrorText(this._hass, err),
      })
    } finally {
      this._transferBusy = false
      this._render()
    }
  }

  async _exportData() {
    if (!this._hass || this._transferBusy) return
    const fromMonth =
      this.shadowRoot.getElementById('export-from')?.value ||
      this._exportFrom ||
      ''
    const toMonth =
      this.shadowRoot.getElementById('export-to')?.value || this._exportTo || ''
    this._exportFrom = fromMonth
    this._exportTo = toMonth
    if (fromMonth && toMonth && fromMonth > toMonth) {
      this._transferMessage = this._t('invalid_range')
      this._render()
      return
    }
    this._transferBusy = true
    this._transferMessage = this._t('generating_export')
    this._render()
    try {
      const result = await this._hass.callWS({
        type: 'bill_tracker/export',
        format: this._exportFormat,
        from_month: fromMonth,
        to_month: toMonth,
        status: this._exportStatus,
        category_id: this._exportCategory,
        trend: this._exportTrend,
        language: this._language(),
      })
      this._downloadPayload(result)
      this._transferMessage = this._t('export_created', {
        filename: result.filename,
      })
    } catch (err) {
      this._transferMessage = this._t('export_failed', {
        error: billyErrorText(this._hass, err),
      })
    } finally {
      this._transferBusy = false
      this._render()
    }
  }

  _updateSplitTotal() {
    const label = this.shadowRoot.getElementById('split-total')
    if (!label) return
    const total = [...this.shadowRoot.querySelectorAll('.split-input')].reduce(
      (sum, input) => sum + (Number(input.value) || 0),
      0,
    )
    label.textContent = this._t('split_total', { total: total.toFixed(2) })
    label.classList.toggle('bad', Math.abs(total - 100) > 0.05)
  }

  _applyCategoryDefaults() {
    this._autoPeriod()
    const category = this._categoryById(
      this.shadowRoot.getElementById('category')?.value,
    )
    const payer = this.shadowRoot.getElementById('payer')
    if (
      payer &&
      category?.default_payer_id &&
      [...payer.options].some((x) => x.value === category.default_payer_id)
    ) {
      payer.value = category.default_payer_id
    }
    const provider = this.shadowRoot.getElementById('provider')
    const contract = this.shadowRoot.getElementById('contract')
    if (provider) provider.value = String(category?.default_provider || '')
    if (contract) contract.value = String(category?.default_contract || '')
    const unit = String(category?.consumption_unit || '')
    const consumption = this.shadowRoot.getElementById('consumption')
    const consumptionLabel = this.shadowRoot.getElementById('consumption-label')
    if (consumption) {
      consumption.disabled = !unit
      consumption.placeholder = unit ? '0' : this._t('configure_unit')
      if (!unit) consumption.value = ''
    }
    if (consumptionLabel) {
      const textNode = consumptionLabel.childNodes[0]
      if (textNode)
        textNode.textContent = unit
          ? `${this._t('consumption')} (${unit})`
          : `${this._t('consumption')} (${this._t('unit_not_configured')})`
    }
  }

  _autoPeriod() {
    const categoryId = this.shadowRoot.getElementById('category')?.value
    const paid = this._parseMonth(
      this.shadowRoot.getElementById('paid-month')?.value,
    )
    const category = this._categoryById(categoryId)
    if (!paid || !category) return
    const interval = Math.max(1, Number(category.interval_months || 1))
    const start = this._addMonths(paid.year, paid.month, -(interval - 1))
    const endInput = this.shadowRoot.getElementById('period-end')
    const startInput = this.shadowRoot.getElementById('period-start')
    if (endInput) endInput.value = this._monthValue(paid.year, paid.month)
    if (startInput) startInput.value = this._monthValue(start.year, start.month)
  }

  _openSettings() {
    history.pushState(null, '', '/config/integrations/integration/bill_tracker')
    window.dispatchEvent(new Event('location-changed'))
  }

  async _submit(event) {
    event.preventDefault()
    if (!this._hass) return
    const categoryId = this.shadowRoot.getElementById('category')?.value
    const paid = this._parseMonth(
      this.shadowRoot.getElementById('paid-month')?.value,
    )
    const start = this._parseMonth(
      this.shadowRoot.getElementById('period-start')?.value,
    )
    const end = this._parseMonth(
      this.shadowRoot.getElementById('period-end')?.value,
    )
    const amount = Number(this.shadowRoot.getElementById('amount')?.value)
    const note = this.shadowRoot.getElementById('note')?.value.trim() || ''
    const payerId = this.shadowRoot.getElementById('payer')?.value || undefined
    const paidFlag = Boolean(
      this.shadowRoot.getElementById('paid-status')?.checked,
    )
    const paymentDate =
      this.shadowRoot.getElementById('payment-date')?.value || ''
    const dueDate = this.shadowRoot.getElementById('due-date')?.value || ''
    const periodStartDate =
      this.shadowRoot.getElementById('period-start-date')?.value || ''
    const periodEndDate =
      this.shadowRoot.getElementById('period-end-date')?.value || ''
    const provider =
      this.shadowRoot.getElementById('provider')?.value.trim() || ''
    const contract =
      this.shadowRoot.getElementById('contract')?.value.trim() || ''
    const consumptionRaw =
      this.shadowRoot.getElementById('consumption')?.value ?? ''
    const consumption =
      String(consumptionRaw).trim() === '' ? undefined : Number(consumptionRaw)
    const split = [...this.shadowRoot.querySelectorAll('.split-input')]
      .map((input) => ({
        payer_id: input.dataset.payer,
        percentage: Number(input.value || 0),
      }))
      .filter((x) => x.payer_id && x.percentage > 0)
    if (
      !categoryId ||
      !paid ||
      !start ||
      !end ||
      !Number.isFinite(amount) ||
      amount < 0
    ) {
      this._error = this._t('invalid_data')
      this._render()
      return
    }
    if (
      split.length &&
      Math.abs(split.reduce((sum, x) => sum + x.percentage, 0) - 100) > 0.05
    ) {
      this._error = this._t('split_must_100')
      this._render()
      return
    }
    const payload = {
      year: paid.year,
      month: paid.month,
      category_id: categoryId,
      amount,
      note,
      period_start_year: start.year,
      period_start_month: start.month,
      period_end_year: end.year,
      period_end_month: end.month,
      period_start_date: periodStartDate,
      period_end_date: periodEndDate,
      paid: paidFlag,
      payment_date: paymentDate,
      due_date: dueDate,
      provider,
      contract,
    }
    if (consumption !== undefined) {
      if (!Number.isFinite(consumption) || consumption < 0) {
        this._error = this._t('invalid_consumption')
        this._render()
        return
      }
      payload.consumption = consumption
    }
    if (payerId) payload.payer_id = payerId
    if (split.length) payload.split = split
    try {
      if (this._editing) {
        await this._hass.callWS({
          type: 'bill_tracker/update',
          expense_id: this._editing.id,
          ...payload,
        })
      } else {
        await this._hass.callWS({ type: 'bill_tracker/add', ...payload })
      }
      this._editing = null
      this._formOpen = false
      this._error = null
      await this._load()
    } catch (err) {
      this._error = billyErrorText(this._hass, err)
      this._render()
    }
  }

  async _togglePaid(input) {
    if (!this._hass || !input) return
    const id = input.dataset.id
    const paid = Boolean(input.checked)
    input.disabled = true
    try {
      await this._hass.callWS({
        type: 'bill_tracker/set_paid',
        expense_id: id,
        paid,
      })
      this._error = null
      await this._load()
    } catch (err) {
      input.checked = !paid
      input.disabled = false
      this._error = billyErrorText(this._hass, err)
      this._render()
    }
  }

  _startEdit(id) {
    this._editing =
      (this._data?.expenses || []).find((x) => x.id === id) || null
    this._formOpen = false
    this._render()
    const modal = this.shadowRoot?.getElementById('edit-modal')
    if (modal) {
      modal.tabIndex = -1
      modal.focus()
    }
  }

  _closeEditModal() {
    this._editing = null
    this._formOpen = false
    this._error = null
    this._render()
  }

  async _delete(id) {
    if (!this._hass || !confirm(this._t('delete_bill_confirm'))) return
    try {
      await this._hass.callWS({ type: 'bill_tracker/delete', expense_id: id })
      await this._load()
    } catch (err) {
      this._error = billyErrorText(this._hass, err)
      this._render()
    }
  }

  async _settle(button) {
    if (!this._hass) return
    const amount = Number(button.dataset.amount || 0)
    const from = button.dataset.from
    const to = button.dataset.to
    const fromName = this._payerById(from)?.name || this._t('debtor')
    const toName = this._payerById(to)?.name || this._t('creditor')
    const count = Number(button.dataset.count || 0)
    if (
      !confirm(
        this._t('settle_confirm', {
          amount: this._money(amount),
          from: fromName,
          to: toName,
          count: count || '',
        }),
      )
    )
      return
    try {
      await this._hass.callWS({
        type: 'bill_tracker/settlement/add',
        from_payer_id: from,
        to_payer_id: to,
        amount,
        note: this._t('settlement_note'),
      })
      await this._load()
    } catch (err) {
      this._error = billyErrorText(this._hass, err)
      this._render()
    }
  }

  async _deleteSettlement(id) {
    if (!this._hass || !confirm(this._t('undo_settlement_confirm'))) return
    try {
      await this._hass.callWS({
        type: 'bill_tracker/settlement/delete',
        settlement_id: id,
      })
      await this._load()
    } catch (err) {
      this._error = billyErrorText(this._hass, err)
      this._render()
    }
  }
}

class BillTrackerCardEditor extends HTMLElement {
  constructor() {
    super()
    this.attachShadow({ mode: 'open' })
    this._config = BillTrackerCard.getStubConfig()
    this._hass = null
  }

  setConfig(config) {
    this._config = { ...BillTrackerCard.getStubConfig(), ...config }
    this._render()
  }

  set hass(hass) {
    this._hass = hass
    this._render()
  }

  _t(key, vars = {}) {
    return billyT(this._hass, key, vars)
  }

  _render() {
    if (!this.shadowRoot) return
    const columns = this._config.columns ?? 'full'
    this.shadowRoot.innerHTML = `
      <style>
        .editor { display:grid; gap:14px; padding:8px 0; }
        label { display:grid; gap:6px; color:var(--primary-text-color); }
        span { font-size:13px; color:var(--secondary-text-color); }
        input,select { min-height:44px; box-sizing:border-box; width:100%; border:1px solid var(--divider-color); border-radius:10px; padding:8px 10px; background:var(--card-background-color); color:var(--primary-text-color); font-size:16px; }
        .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
        @media (max-width:520px) { .grid { grid-template-columns:1fr; } }
      </style>
      <div class="editor">
        <label><span>${this._escape(
          this._t('editor_title'),
        )}</span><input data-key="title" type="text" value="${this._escape(
          this._config.title || '',
        )}"></label>
        <div class="grid">
          <label><span>${this._escape(
            this._t('editor_width'),
          )}</span><select data-key="columns">
            <option value="full" ${
              columns === 'full' ? 'selected' : ''
            }>${this._escape(this._t('editor_full'))}</option>
            ${[4, 6, 8, 10, 12]
              .map(
                (n) =>
                  `<option value="${n}" ${
                    Number(columns) === n ? 'selected' : ''
                  }>${this._escape(
                    this._t('editor_columns', { count: n }),
                  )}</option>`,
              )
              .join('')}
          </select></label>
          <label><span>${this._escape(
            this._t('editor_history'),
          )}</span><input data-key="history_months" type="number" min="3" max="36" step="1" value="${Number(
            this._config.history_months || 12,
          )}"></label>
          <label><span>${this._escape(
            this._t('editor_forecast'),
          )}</span><input data-key="forecast_months" type="number" min="1" max="24" step="1" value="${Number(
            this._config.forecast_months || 12,
          )}"></label>
        </div>
      </div>`
    this.shadowRoot
      .querySelectorAll('input,select')
      .forEach((input) =>
        input.addEventListener('change', () => this._changed(input)),
      )
  }

  _changed(input) {
    const key = input.dataset.key
    if (!key) return
    let value = input.value
    if (['history_months', 'forecast_months'].includes(key))
      value = Number(value)
    if (key === 'columns' && value !== 'full') value = Number(value)
    const config = { ...this._config, [key]: value }
    if (key === 'history_months')
      config.history_months = Math.max(3, Math.min(36, Number(value || 12)))
    if (key === 'forecast_months')
      config.forecast_months = Math.max(1, Math.min(24, Number(value || 12)))
    this._config = config
    const event = new Event('config-changed', { bubbles: true, composed: true })
    event.detail = { config }
    this.dispatchEvent(event)
  }

  _escape(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
  }
}

if (!customElements.get('bill-tracker-card-impl'))
  customElements.define('bill-tracker-card-impl', BillTrackerCard)
if (!customElements.get('bill-tracker-card-editor-impl'))
  customElements.define('bill-tracker-card-editor-impl', BillTrackerCardEditor)

console.info(
  `Billy / Bill Tracker implementation v${BILL_TRACKER_VERSION} loaded`,
)
