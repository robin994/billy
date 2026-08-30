import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "custom_components" / "bill_tracker" / "frontend"


def test_frontend_is_based_on_0_5_2_ui():
    js = (FRONTEND / "bill-tracker-card-impl.js").read_text(encoding="utf-8")
    for token in (
        "_chart()",
        "toggle-current-bills",
        "open-all-bills",
        "all-bills-modal",
        "all-bills-category",
        "all-bills-status",
        "all-bills-time-mode",
        "all-bills-year",
        "all-bills-from",
        "all-bills-to",
        "all-bills-page-size",
        "transfer-modal",
        "import-create-categories",
        "import-create-payers",
        "export-format",
        "export-status",
        "export-category",
        "export-trend",
        'class="paypal"',
        "pay_with_method",
    ):
        assert token in js


def test_frontend_and_manifest_use_rewrite_version():
    bootstrap = (FRONTEND / "bill-tracker-card.js").read_text(encoding="utf-8")
    implementation = (FRONTEND / "bill-tracker-card-impl.js").read_text(encoding="utf-8")
    manifest = (ROOT / "custom_components" / "bill_tracker" / "manifest.json").read_text(encoding="utf-8")
    const = (ROOT / "custom_components" / "bill_tracker" / "const.py").read_text(encoding="utf-8")
    assert "BILLY_FRONTEND_VERSION = '0.12.1'" in bootstrap
    assert "BILL_TRACKER_VERSION = '0.12.1'" in implementation
    assert "./bill-tracker-i18n.js?v=0.12.1-r1" in implementation
    assert '"version": "0.12.1"' in manifest
    assert 'FRONTEND_VERSION = "0.12.1"' in const
    assert 'FRONTEND_CACHE_VERSION = "0.12.1-r1"' in const


def test_settings_exposes_rejected_parser_imports_and_restore_action():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    assert "status: 'rejected'" in panel
    assert "limit: 500" in panel
    assert "_rejected()" in panel
    assert "data-restore-rejected" in panel
    assert "bill_tracker/parser/import/retry" in panel
    assert "bill_tracker_import_updated" in panel
    assert "restoreRejectedSuccess" in panel


def test_automatic_parsing_does_not_replace_lovelace_ui():
    sensor = (ROOT / "custom_components" / "bill_tracker" / "sensor.py").read_text(encoding="utf-8")
    parser_manager = (ROOT / "custom_components" / "bill_tracker" / "parser" / "manager.py").read_text(encoding="utf-8")
    assert "ParserManager" in sensor
    assert "imap_content" in parser_manager


def test_parser_manager_panel_is_scalable_and_has_bill_type_filter():
    panel = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    flow = (ROOT / "custom_components" / "bill_tracker" / "config_flow.py").read_text(encoding="utf-8")
    for token in (
        'id="search"',
        'id="country"',
        'id="bill-type"',
        'id="catalog-status"',
        'id="status"',
        'id="sort"',
        "this._billType !== 'all'",
        "bill_tracker/parser/refresh",
        "bill_tracker/parser/install",
        "bill_tracker/parser/uninstall",
        "update_available",
        "outdated",
        "catalogCacheWarning",
        "refresh_error",
    ):
        assert token in panel
    assert '"parser_manager"' in flow
    assert '"/billy?view=parsers"' in flow


def test_parser_search_does_not_rebuild_input_on_every_keystroke():
    panel = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    handler_start = panel.index("getElementById('search')")
    handler_end = panel.index("getElementById('country')", handler_start)
    handler = panel[handler_start:handler_end]
    assert "addEventListener('input'" in handler
    assert "this._renderList()" in handler
    assert "this._render()" not in handler
    assert "resets the caret to position 0" in handler


def test_billy_sidebar_panel_keeps_card_and_parser_manager():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    for token in (
        "billy-parser-manager.js?v=0.12.1-r1",
        '<billy-dashboard id="dashboard">',
        '<billy-bills id="bills-panel">',
        '<billy-recurring id="recurring-panel">',
        '<billy-parser-manager id="parser-manager">',
        '<billy-settings id="settings-panel">',
        "customElements.define('billy-panel'",
    ):
        assert token in panel
    assert 'frontend_url_path=BILLY_PANEL_ROUTE' in init
    assert 'webcomponent_name="billy-panel"' in init
    assert 'sidebar_title="Billy"' in init
    assert 'sidebar_icon="mdi:receipt-text-outline"' in init
    assert 'require_admin=False' in init


def test_billy_panel_uses_home_assistant_custom_panel_loader():
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    assert "from homeassistant.components.panel_custom import async_register_panel" in init
    assert "await async_register_panel(" in init
    assert "async_remove_panel(hass, BILLY_PANEL_ROUTE" in init
    assert 'module_url=BILLY_PANEL_MODULE_URL' in init


def test_lovelace_resource_url_is_not_versioned():
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    assert 'FRONTEND_MODULE_URL = FRONTEND_URL' in init
    assert 'FRONTEND_MODULE_URL = f"{FRONTEND_URL}?v=' not in init


def test_billy_registers_dashboard_widget_pack():
    bootstrap = (FRONTEND / "bill-tracker-card.js").read_text(encoding="utf-8")
    widgets = (FRONTEND / "billy-widgets.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    for card in (
        "billy-summary-card",
        "billy-spending-card",
        "billy-breakdown-card",
        "billy-upcoming-card",
        "billy-recurring-card",
        "billy-balances-card",
        "billy-parser-status-card",
    ):
        assert card in widgets
    for token in (
        "window.customCards",
        "class BillyWidgetBase",
        "bill_tracker/list",
        "bill_tracker/parser/list",
        "recurring_history",
        "current_month_recurring",
        "catalog_status",
        "payment_url",
    ):
        assert token in widgets
    assert "BILLY_WIDGETS_URL" in bootstrap
    assert "loadBillyWidgets()" in bootstrap
    assert 'BILLY_WIDGETS_URL = "/bill_tracker/billy-widgets.js"' in init
    assert "StaticPathConfig(BILLY_WIDGETS_URL, str(BILLY_WIDGETS_PATH), False)" in init


def test_payer_settings_and_reimbursements_support_multiple_payment_methods():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    card = (FRONTEND / "bill-tracker-card-impl.js").read_text(encoding="utf-8")
    widgets = (FRONTEND / "billy-widgets.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    for token in (
        'name="revolut"',
        'name="venmo"',
        'name="cashapp"',
        'name="preferred_payment_method"',
        "payment_methods:",
        "preferred_payment_method:",
        "payWithMethod",
        "paymentNotConfigured",
    ):
        assert token in panel
    assert "debt.payment_url" in panel
    assert "debt.payment_url" in card
    assert "debt.payment_url" in widgets
    assert 'vol.Optional("payment_methods", default={}): dict' in init
    assert 'vol.Optional("preferred_payment_method", default=""): str' in init


def test_billy_panel_has_large_dashboard_and_native_settings():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    for token in (
        "class BillyDashboard",
        "spendingTrend",
        "categoryBreakdown",
        "upcomingBills",
        "recentBills",
        "class BillyRecurring",
        "bill_tracker/recurring/add",
        "bill_tracker/recurring/update",
        "bill_tracker/recurring/delete",
        "class BillySettings",
        "bill_tracker/category/add",
        "bill_tracker/category/update",
        "bill_tracker/category/delete",
        "bill_tracker/payer/add",
        "bill_tracker/payer/update",
        "bill_tracker/payer/delete",
        "bill_tracker/parser/sources/set",
        "class BillyBills",
        "bill_tracker/add",
        "bill_tracker/update",
        "bill_tracker/delete",
        "bill_tracker/set_paid",
        "Rimborsi tra utenti",
        "confirmReimbursement",
        "developerCredits",
        "https://github.com/robin994/billy-parser",
        "https://www.linkedin.com/in/roberto-tortora-379928109/",
        "https://paypal.me/rtortora94",
    ):
        assert token in panel


def test_overview_chart_preferences_are_persisted_per_home_assistant_user():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    for token in (
        "billy.chart.preferences.v1:${userId}",
        "this._loadChartPreferences()",
        "this._saveChartPreferences()",
        "globalThis.localStorage?.getItem(key)",
        "globalThis.localStorage?.setItem(",
        "disabled: [...this._chartDisabled]",
        "this._sanitizeChartPreferences()",
    ):
        assert token in panel


def test_bills_and_recurring_have_csv_excel_pdf_exports():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    manager = (ROOT / "custom_components" / "bill_tracker" / "manager.py").read_text(encoding="utf-8")
    exporter = (ROOT / "custom_components" / "bill_tracker" / "exporter.py").read_text(encoding="utf-8")
    for token in (
        'id="export-bills"',
        'id="export-recurring"',
        'id="export-bills-format"',
        'id="export-recurring-format"',
        "Excel (.xlsx)",
        "bill_tracker/export_recurring",
    ):
        assert token in panel
    assert '"bill_tracker/export_recurring"' in init
    assert "def export_recurring_data(" in manager
    assert "def recurring_csv_bytes(" in exporter
    assert "def recurring_xlsx_bytes(" in exporter
    assert "def recurring_pdf_bytes(" in exporter


def test_billy_settings_exposes_complete_backup_with_recurring_data():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    manager = (ROOT / "custom_components" / "bill_tracker" / "manager.py").read_text(encoding="utf-8")
    for token in (
        "transferTitle",
        'id="backup-export"',
        'id="backup-file"',
        'id="backup-import"',
        "bill_tracker/backup/export",
        "bill_tracker/backup/import",
    ):
        assert token in panel or token in init
    for token in (
        '"format": "billy-backup"',
        '"recurring_expenses": deepcopy(self.recurring_expenses)',
        '"recurring_occurrences": deepcopy(self.recurring_occurrences)',
        "async_import_backup",
    ):
        assert token in manager
    assert '<bill-tracker-card id="dashboard-card">' not in panel
    assert '<billy-bills id="bills-panel">' in panel


def test_bills_page_filters_and_flags_user_reimbursements():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    manager = (ROOT / "custom_components" / "bill_tracker" / "manager.py").read_text(encoding="utf-8")
    for token in (
        'id="bill-reimbursement"',
        "this._reimbursement === 'pending'",
        "this._reimbursement === 'done'",
        "data-reimbursed-id",
        "bill_tracker/set_reimbursement",
        "reimbursementPartial",
        "reimbursement_can_toggle",
    ):
        assert token in panel
    assert '"bill_tracker/set_reimbursement"' in init
    assert "async_set_reimbursement_done" in manager
    assert '"reimbursement_status": reimbursement["status"]' in manager


def test_panel_modals_do_not_reload_on_every_hass_object_update():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    # Home Assistant replaces the hass object frequently. Reloading data from
    # every setter call destroys open modal DOM (most visible in Recurring).
    assert "const changed = value !== this._hass" not in panel
    assert panel.count("const previousConnection = this._hass?.connection") >= 4
    assert panel.count("if (firstAssignment || connectionChanged || !this._data) this._load()") >= 4


def test_parser_manager_community_publish_flow():
    manager = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    api = (ROOT / "custom_components" / "bill_tracker" / "parser_api.py").read_text(
        encoding="utf-8"
    )
    parser_manager = (
        ROOT / "custom_components" / "bill_tracker" / "parser" / "manager.py"
    ).read_text(encoding="utf-8")
    for token in (
        "Share with community",
        "Condividi con la community",
        "bill_tracker/parser/custom/export",
        "billy-parser-submission:v2",
        "requested_status: 'experimental'",
        "billy-parser-feedback:v1",
        "feedback-working",
        "feedback-partial",
        "feedback-failed",
        "bill_tracker/parser/feedback",
        "feedbackSourceUnknown",
        "feedback_available",
        "installed_catalog_status",
        "github.com/robin994/billy-parser/issues/new",
        "catalog-experimental",
        'id="catalog-status"',
    ):
        assert token in manager
    assert "row.feedback_available === true" in manager
    assert "const sourceCommit = String(feedback?.source_commit || '').trim()" in manager
    assert "source_commit: String(row.source_commit || '')" not in manager
    assert '"bill_tracker/parser/feedback"' in api
    assert 'vol.In(["working", "partial", "failed"])' in api
    # the anonymous fingerprint is built server-side from the installed state
    assert '"installation_fingerprint": self.community_fingerprint(' in parser_manager


def test_parser_manager_separates_catalog_and_installation_status():
    panel = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    manager = (ROOT / "custom_components" / "bill_tracker" / "parser" / "manager.py").read_text(encoding="utf-8")
    catalog = (ROOT / "custom_components" / "bill_tracker" / "parser" / "catalog.py").read_text(encoding="utf-8")
    for token in (
        "Catalog status",
        "Installation status",
        "Stato catalogo",
        "Stato installazione",
        "catalog_status",
        "install-replacement",
        "experimentalHint",
        "outdatedHint",
    ):
        assert token in panel or token in manager or token in catalog
    assert 'row.pop("status", None)' in catalog
    assert 'status = "outdated"' in manager


def test_new_billy_frontends_support_all_shipped_languages():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    parser = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    widgets = (FRONTEND / "billy-widgets.js").read_text(encoding="utf-8")
    bootstrap = (FRONTEND / "bill-tracker-card.js").read_text(encoding="utf-8")
    extra = (FRONTEND / "billy-extra-i18n.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")

    assert "BILLY_PANEL_EXTRA_TEXT" in panel
    assert "BILLY_PARSER_EXTRA_TEXT" in parser
    assert "billy-extra-i18n.js?v=0.12.1-r1" in panel
    assert "billy-extra-i18n.js?v=0.12.1-r1" in parser
    assert "['en', 'it', 'es', 'fr', 'de', 'pt']" in panel
    assert "['en', 'it', 'es', 'fr', 'de', 'pt']" in parser
    for language in ("es", "fr", "de", "pt"):
        assert f"  {language}: {{" in extra
        assert f"  {language}: [" in widgets
        assert f"  {language}: {{" in bootstrap
    assert 'EXTRA_I18N_URL = "/bill_tracker/billy-extra-i18n.js"' in init
    assert "StaticPathConfig(EXTRA_I18N_URL, str(EXTRA_I18N_PATH), False)" in init
    assert 'BILLY_PANEL_MODULE_URL = f"{BILLY_PANEL_URL}?v={FRONTEND_CACHE_VERSION}"' in init


def test_home_assistant_translation_files_have_matching_keys():
    import json

    translations = ROOT / "custom_components" / "bill_tracker" / "translations"

    def flatten(value, prefix=""):
        keys = set()
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(child, dict):
                keys |= flatten(child, path)
            else:
                keys.add(path)
        return keys

    english = flatten(json.loads((translations / "en.json").read_text(encoding="utf-8")))
    for language in ("it", "es", "fr", "de", "pt"):
        localized = flatten(
            json.loads((translations / f"{language}.json").read_text(encoding="utf-8"))
        )
        assert localized == english


def test_bill_and_recurring_exports_allow_date_and_type_filters():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    manager = (ROOT / "custom_components" / "bill_tracker" / "manager.py").read_text(encoding="utf-8")
    for token in (
        'id="export-bills-from"',
        'id="export-bills-to"',
        'id="export-bills-category"',
        'id="export-recurring-from"',
        'id="export-recurring-to"',
        'id="export-recurring-kind"',
        "from_date: fromDate",
        "to_date: toDate",
    ):
        assert token in panel
    assert 'vol.Optional("from_date", default=""): str' in init
    assert 'vol.Optional("to_date", default=""): str' in init
    assert "range_start = date.fromisoformat(from_date) if from_date else None" in manager


def test_parser_tab_can_create_edit_export_and_test_custom_parsers():
    panel = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    api = (ROOT / "custom_components" / "bill_tracker" / "parser_api.py").read_text(encoding="utf-8")
    manager = (ROOT / "custom_components" / "bill_tracker" / "parser" / "manager.py").read_text(encoding="utf-8")
    for token in (
        'id="new-custom"',
        "Nuovo parser custom",
        "_openCustomEditor",
        'id="custom-yaml"',
        'id="custom-editor-test"',
        'id="custom-editor-save"',
        "bill_tracker/parser/custom/save",
        "bill_tracker/parser/custom/export",
        "bill_tracker/parser/test",
        "edit-custom",
        "export-custom",
        "expected_parser_id",
    ):
        assert token in panel
    assert 'vol.Optional("expected_parser_id"): str' in api
    assert "Custom parser ID cannot be changed while editing" in manager


def test_overview_chart_includes_recurring_expenses_in_actual_and_forecast_bars():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    for token in (
        "_actualChartRows()",
        "this._chartForecastRows()",
        "this._data?.recurring_history || []",
        "recurring_total: recurringTotal",
        "row.recurring_items || []",
        "forecast: row.kind === 'forecast'",
        "recurring_items",
        "data-chart-toggle",
        "_chartDisabled = new Set()",
        "data-chart-enable-all",
        "data-chart-disable-all",
        "chart-months",
        "chart-year",
        "chart-view",
        "chartSeparate",
        "safeColor(recurring.color)",
        "chartRecurring: 'Spese ricorrenti'",
    ):
        assert token in panel


def test_overview_chart_uses_independent_checkbox_filters():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    assert 'const key = `bill:${category.id}`' in panel
    assert 'const key = `recurring:${row.id}`' in panel
    assert panel.count('type="checkbox" data-chart-toggle="${escapeHtml(key)}"') >= 2
    assert 'class="chart-filter-combobox"' in panel
    assert 'class="chart-option ${enabled ? \'active\' : \'\'}"' in panel
    assert "chartSelectedCount" in panel
    assert "chartNoneSelected" in panel
    assert "this._chartFilterOpen = true" in panel
    assert "this._chartDisabled.add(key)" in panel
    assert "this._chartDisabled.delete(key)" in panel
    assert "_chartItemEnabled(`bill:${category.id}`)" in panel
    assert "_chartItemEnabled(`recurring:${item.id}`)" in panel


def test_overview_chart_hides_filters_without_data_in_selected_range():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    assert "_availableChartFilterKeys()" in panel
    assert ".filter((category) => available.has(`bill:${category.id}`))" in panel
    assert ".filter((row) => available.has(`recurring:${row.id}`))" in panel
    assert "for (const key of this._availableChartFilterKeys())" in panel


def test_overview_recurring_chart_history_is_generated_from_start_date():
    manager = (ROOT / "custom_components" / "bill_tracker" / "manager.py").read_text(encoding="utf-8")
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    assert '"recurring_history": self.recurring_history_items()' in manager
    assert "def recurring_history_items" in manager
    assert 'start_text = str(recurring.get("start_date") or "")' in manager
    assert "this._data?.recurring_history || []" in panel


def test_overview_shows_unpaid_bills_due_this_month_instead_of_category_breakdown():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    for token in (
        "_dueThisMonth()",
        "dueThisMonth",
        "noBillsDueThisMonth",
        "!row.paid",
        "row.due_date",
    ):
        assert token in panel
    assert "${this._breakdown()}" not in panel


def test_cashflow_uses_payment_date_instead_of_billing_reference_month():
    manager = (
        ROOT / "custom_components" / "bill_tracker" / "manager.py"
    ).read_text(encoding="utf-8")
    assert "def _expense_cashflow_month" in manager
    assert "cashflow_key = self._expense_cashflow_month(item)" in manager
    assert "item[\"payment_date\"] = date.today().isoformat()" in manager
    assert "item[\"payment_date\"] = None" in manager


def test_bills_page_exposes_parser_review_queue_with_retry_accept_and_reject():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    bills_start = panel.index("class BillyBills")
    bills_end = panel.index("class BillyRecurring", bills_start)
    bills = panel[bills_start:bills_end]
    dashboard = panel[panel.index("class BillyDashboard") : bills_start]
    for token in (
        "bill_tracker/parser/imports",
        "bill_tracker/parser/import/approve",
        "bill_tracker/parser/import/reject",
        "bill_tracker/parser/import/retry",
        "pendingReviewTitle",
        "data-import-approve",
        "data-import-reject",
        "data-import-retry",
        "failedImport",
        "bill_tracker_import_updated",
    ):
        assert token in bills
    assert "_pendingImportsHtml()" in bills
    assert "_pendingImportsHtml()" not in dashboard


def test_parser_configuration_supports_default_payer_and_split():
    panel = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    api = (ROOT / "custom_components" / "bill_tracker" / "parser_api.py").read_text(
        encoding="utf-8"
    )
    manager = (
        ROOT / "custom_components" / "bill_tracker" / "parser" / "manager.py"
    ).read_text(encoding="utf-8")
    # the configure dialog exposes payer + split controls
    for token in ("dialog-payer", "dialog-split"):
        assert token in panel
    # and the values round-trip through the parser API / manager
    for token in ("default_payer_id", "default_split"):
        assert token in panel
        assert token in api or token in manager


def test_overview_subscribes_after_first_hass_assignment_and_refreshes_on_bill_updates():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    dashboard_start = panel.index("class BillyDashboard")
    dashboard_end = panel.index("class BillyBills", dashboard_start)
    dashboard = panel[dashboard_start:dashboard_end]

    assert "if (firstAssignment || connectionChanged) this._subscribe()" in dashboard
    assert "'bill_tracker_updated'" in dashboard
    assert "() => this._load()" in dashboard
    assert "this._unsubscribeBills?.()" in dashboard
    assert "this._unsubscribeImports?.()" in dashboard
    assert "this._unsubscribe?.()" not in dashboard


def test_overview_does_not_hide_recurring_kinds_or_inactive_rules():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    overview_start = panel.index("_recurringOverview()")
    overview_end = panel.index("_reimbursements()", overview_start)
    overview = panel[overview_start:overview_end]
    chart_filters_start = panel.index("_chartFilterOptions()")
    chart_filters_end = panel.index("_actualChartRows()", chart_filters_start)
    chart_filters = panel[chart_filters_start:chart_filters_end]

    assert ".filter((row) => row.status === 'active')" not in overview
    assert ".filter((row) => row.status === 'active')" not in chart_filters
    assert "row.kind === 'mortgage'" in overview


def test_recurring_expenses_have_persistent_configurable_colors():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    manager = (ROOT / "custom_components" / "bill_tracker" / "manager.py").read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(encoding="utf-8")
    assert 'name="color" type="color"' in panel
    assert '"color": self._normalize_color(color, color_index)' in manager
    assert 'vol.Optional("color", default=""): str' in init


def test_short_and_long_billing_periods_are_exposed_in_billy_ui():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    legacy = (FRONTEND / "bill-tracker-card-impl.js").read_text(encoding="utf-8")
    manager = (
        ROOT / "custom_components" / "bill_tracker" / "manager.py"
    ).read_text(encoding="utf-8")
    importer = (
        ROOT / "custom_components" / "bill_tracker" / "importers" / "coordinator.py"
    ).read_text(encoding="utf-8")
    for token in (
        "period_start_date",
        "period_end_date",
        "period_type",
        "period_days",
        "shortPeriod",
        "longPeriod",
    ):
        assert token in panel or token in manager or token in importer
    assert "short_period" in legacy
    assert "long_period" in legacy
    assert "_billing_period_info" in manager
    assert 'period["type"] in {"short", "long"}' in manager


def test_home_assistant_translation_files_are_complete_and_localized():
    translations = ROOT / "custom_components" / "bill_tracker" / "translations"

    def flatten(value, prefix=""):
        rows = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(child, dict):
                rows.update(flatten(child, path))
            else:
                rows[path] = str(child)
        return rows

    english = flatten(
        json.loads((translations / "en.json").read_text(encoding="utf-8"))
    )
    placeholders = re.compile(r"\{[^}]+\}")

    for language in ("it", "es", "fr", "de", "pt"):
        localized = flatten(
            json.loads((translations / f"{language}.json").read_text(encoding="utf-8"))
        )
        assert set(localized) == set(english)
        same_as_english = [
            key for key, value in localized.items() if value == english[key]
        ]
        assert len(same_as_english) <= 15, (
            f"{language}.json looks mostly untranslated: "
            f"{len(same_as_english)} strings still match en.json"
        )
        for key, english_value in english.items():
            assert sorted(placeholders.findall(localized[key])) == sorted(
                placeholders.findall(english_value)
            ), f"Placeholder mismatch in {language}.json at {key}"


def test_recurring_frequency_labels_cover_all_languages_with_a_fallback():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    block = re.search(
        r"const RECURRING_FREQUENCY_LABELS = \{.*?\n\}", panel, re.DOTALL
    )
    assert block, "RECURRING_FREQUENCY_LABELS table is missing"
    table = block.group(0)
    for language in ("en", "it", "es", "fr", "de", "pt"):
        assert f"  {language}: {{" in table
        assert f"other:" in table
    # the per-language if/else chain must be gone (it returned undefined for
    # any language not explicitly handled)
    assert "if (languageOf(this._hass) === 'es')" not in panel
    assert panel.count("RECURRING_FREQUENCY_LABELS.en") == 1


def test_parser_manager_bill_type_labels_cover_all_languages():
    parser = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    block = re.search(r"const BILL_TYPE_LABELS = \{.*?\n\}", parser, re.DOTALL)
    assert block, "BILL_TYPE_LABELS table is missing"
    table = block.group(0)
    for language in ("en", "it", "es", "fr", "de", "pt"):
        assert f"  {language}: {{" in table
    for bill_type in ("electricity", "gas", "water", "internet", "mobile", "phone", "insurance"):
        assert table.count(f"{bill_type}:") == 6
