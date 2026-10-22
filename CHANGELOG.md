# Changelog

## 0.17.0

Released: 2026-10-22.

- Added a **Houses / Case** model within the existing Billy integration:
  create, rename and choose a default house in Settings. Bills and recurring
  expenses can be assigned to a house, and filtered by house in their lists.
- Dashboard supports **All houses** and individual house views with scoped
  totals, history and forecasts. The global view remains unchanged. Bank
  accounts, income, parsers, HA user accounts and updates remain shared;
  grouping by house is not legal, authorization or privacy segregation.
- Previous bills and recurring expenses are automatically assigned to a
  generated default house. The backup includes house definitions and links;
  deleting a house with linked financial records is prohibited.
- Added backend and frontend regression tests for house migration, API
  grouping, filtering, recurring expenses and backup round trips.
- Fixed narrow action-button columns on Bills and the oversized, wrapped
  house-filter layout on Recurring expenses at desktop and tablet widths.
- Reimbursement history now filters by House, including completed,
  outstanding and manual reimbursements. Mixed-house transfers show only
  itemized amounts attributable to the selected House, without changing
  the original settlement; historic transfers without itemized amounts
  display an unknown amount instead of an incorrect sum. Mixed transfers
  can only be undone from the All houses view.
- New settlement items retain their House identity even when the source
  bill is subsequently moved, and houses with recorded reimbursements
  cannot be deleted until those records are undone.

- Added explicit payments for recurring expenses, including historical
  mortgage installments. Each payment records an actual date, amount,
  debited account and optional note, and can be corrected or undone.
- Separated *scheduled* expenses from *paid* cash outflows in account
  balances, historical spending charts and the Spending Lovelace widget.
- Added an explicit reconciliation option for payments already represented
  as paid Bills in Billy, preventing double posting. Existing negative
  opening balances and internal transfers are not automatically rewritten.
- Added WebSocket payment CRUD actions, backup storage/validation, account
  reference guards and protection against orphaned installments when editing
  recurring schedules. Storage schema is now version 20, including houses.
- Added a paginated installment-payment interface and regression tests.
  Frontend resource cache is `0.17.0-r1` and the integration version is
  `0.17.0`.

## 0.16.0

Released: 2026-10-21.

- Reorganized the Billy navigation in response to issue #16. **Accounts** is
  now a dedicated main tab showing account balances and internal transfers.
- Moved creating, editing, deleting, assigning payers and choosing the default
  account to **Settings → Accounts**. The Accounts overview links directly to
  the configuration screen without duplicating account editors.
- Added account and incoming/outgoing filters to transfer history. Selecting
  an account card filters its outgoing transfers; the transfer action is more
  prominent on the Accounts page.
- Split **Recurring** into **Expenses** and **Income** views. Income entries
  remain in the main **Income** tab, while recurring income plans now live in
  **Recurring → Income** with their original editing and forecasting behavior.
- Preserved direct links to the new views and translated navigation labels in
  English, Italian, Spanish, French, German and Portuguese.
- Added frontend regression tests for navigation, transfer filtering, account
  management, recurring-income editors and Home Assistant integration.
- No storage migrations, account balance changes or WebSocket API changes are
  required. Bumped the version and frontend resource cache to `0.16.0` /
  `0.16.0-r1`.

Automated tests cover these changes. Manual Home Assistant desktop/mobile UI
testing is still recommended after upgrading; see the
[issue #16 upgrade smoke-test checklist](docs/ISSUE_16_RELEASE_TEST.md).

## 0.15.2

- Addressed the Home Assistant iOS app's Lovelace dashboard scrolling issue
  reported in #15: Billy widgets no longer replace their Shadow DOM on every
  unrelated Home Assistant state change.
- Widgets now refresh their financial data on `bill_tracker_updated` events,
  while preserving the card DOM during requests and avoiding duplicate loads.
  Subscriptions are cleaned up when cards are removed from a dashboard.
- Reduced the initial loading layout changes and added regression tests for
  scrolling stability, connection changes, language changes and async cleanup.
- Refreshed the frontend cache key to `0.15.2-r1`. Testing in the Home
  Assistant companion app on a physical iOS device is still required to
  confirm the reported behavior is resolved.

## 0.15.1

Released: 2026-10-20.

This release includes the income/accounts and PDF features initially developed
for issue #12, plus user-facing improvements requested in issues #13 and #14.

- Added optional PDF invoice archiving for bill types, including IMAP PDF
  attachments and approved-host HTTP(S) URLs, using Home Assistant's media
  directory or mounted media share.
- Introduced a separate Income section: categories, one-time and variable
  recurring income, editable confirmed monthly receipts, and optional
  income-versus-expense chart overlay.
- Added configurable manual accounts (custom names, types and opening
  balances), default-account selection, per-bill and per-income account
  assignment, and cents-accurate internal transfers between arbitrary
  accounts. The combined balance is conserved across transfers.
- Each account now requires one existing payer owner; payers may own zero or
  more accounts. Accounts can be reassigned, while payer deletion is blocked
  until their accounts are reassigned or removed. Pre-existing orphan accounts
  receive a stable legacy owner during migration.
- Localized the six built-in income category labels in all six supported
  languages, without changing persisted category IDs or custom names.
- Added inline PDF preview and confirmed manual upload/replace/delete actions
  to bill editing. Administrators can upload up to 8 MiB PDFs to the existing
  Home Assistant media archive using bounded WebSocket chunks.
- Added switchable sorting in the Bills page by billing month, due date or
  actual payment date (latest first), with missing dates last. The selected
  mode persists per user; bill rows keep amount, status and PDF actions aligned.
- Improved Lovelace widget responsiveness and automatic heights. Summary
  metrics use equal-width columns, Upcoming supports full-width Sections
  placement and two-line bill names, and Recurring/Reimbursements can opt into
  matching grid row heights without stretching every other widget.
- Fixed the multi-country parser catalog refresh. Billy now fetches and displays
  the available country shards (including Belgium) rather than only the
  Home Assistant default country's catalog, allowing parsers from other
  countries to be installed directly.
- Extended JSON backups with income data, account configuration, transaction
  assignments and transfers. Older backups and the earlier two-account
  prototype's records are migrated.
- Reorganized the README into a product overview, with anonymized illustrative
  promotional assets. Detailed usage instructions now live in
  `docs/USER_GUIDE.md`; historical release notes remain in this changelog.
- Bumped the storage schema to 18 and frontend code/cache to
  `0.15.1-r1`. Automated tests validate these changes; manual testing in a
  running Home Assistant instance is still recommended.

## 0.15.0

- Deprecated `custom:bill-tracker-card`. Existing Lovelace dashboards continue to work, but the old card is no longer offered in the card picker and will be removed in Billy 1.0.0.
- Added a dedicated `billy-lovelace.js` entrypoint for all seven supported dashboard widgets, independent of the legacy full-card bootstrap and the `/billy` sidebar.
- Kept the legacy custom element and editor for existing dashboards, but load their full implementation only on use instead of preloading it on every Home Assistant frontend startup.
- Register the new `/bill_tracker/billy-lovelace.js?v=0.15.0-r1` resource alongside the versioned legacy resource in Lovelace storage, preserving existing cards and avoiding early module-registration races.
- Recheck custom-element registrations after Home Assistant startup for YAML-mode installations, where frontend extra modules can run before the scoped registry is ready.
- Aligned frontend cache versions and added regression tests for legacy cards, widget registration and resource upgrades. Storage schema remains unchanged.

## 0.14.1

- Versioned the Lovelace bootstrap resource URL so Home Assistant clients reload the card registration script after updates, addressing the missing `bill-tracker-card` element and stalled loading indicator.
- Restored early `hass` assignments after the Lovelace custom element upgrades, so the original card and its editor load data instead of displaying "Bill Tracker non ancora disponibile".
- Refreshed all frontend module cache keys to `0.14.1-r2` to avoid mixing old and new JavaScript modules.

## 0.14.0

- Added opt-in unpaid provisional bills for each bill type, respecting its 1/2/3/4/6/12-month cadence, creation day and optional due day.
- Added last-invoice, forecast and fixed provisional amounts, with a configurable first expected month and a history-derived default.
- Generate the current month's missing entries at startup, local midnight and when bill-type settings are saved; clamp days 29–31 at month-end and avoid backfilling past months.
- Real manual, parser and CSV invoices replace a matching provisional entry in place. Existing real invoices prevent generation, and deleting a provisional entry skips regeneration for that month.
- Excluded provisional amounts from forecast estimates, normalized spending, contract savings and reimbursements until confirmation. Saving or marking paid confirms the invoice; regular unpaid invoices retain their existing behavior.
- Added provisional labels and an amount-confirmation form when marking a provisional bill paid in the Billy panel, localized in all six languages.
- Added the Upcoming widget's `unpaid_this_month` filter and current-month unpaid list/count/total sensor attributes for Home Assistant automations.
- Preserve provisional metadata in backups and CSV, and add executable backend and frontend regression tests for the monthly checklist.
- Bumped storage schema to 15 and frontend version/cache keys to 0.14.0.

## 0.13.8

- Fixed custom parser drafts resetting to the template or saved YAML on ordinary Home Assistant state updates (issue #11).
- Preserved category, enabled/automatic-import options, email test data, focus and selection when the parser editor needs to rerender.
- Fixed editing existing custom parsers being rejected at `expected_parser_id` by declaring it on the custom-save WebSocket command.
- Kept parser IDs immutable during edits and prevented late export/test/save responses from affecting a newly opened editor.
- Added executable frontend and WebSocket regression tests and a CI workflow for both test suites.
- Bumped frontend cache keys to 0.13.8.

## 0.13.7

- Fixed exported/report bill-type labels after renaming a built-in category.
- Fixed the Consumption field not refreshing when the bill type changes while adding a new bill.
- Added help text clarifying that Consumption is analytics data and does not affect user splits.
- Bumped frontend cache keys to 0.13.7.

## 0.13.6

- Added `Exclude from estimates` for individual bills and bill types without disabling normal history or tracking.
- Excluded bill amounts no longer influence forecast and normalized-forecast calculations, while individual excluded bills still preserve the latest billing cadence anchor.
- Added visible exclusion badges and controls in the Billy bill and bill-type interfaces.
- Bumped frontend cache keys to 0.13.6.

## 0.13.5

- Fixed the lazy-loaded reimbursement-history element losing its Home Assistant context because a pre-upgrade `hass` property shadowed the component setter.
- The panel now waits for the history custom element to be registered before assigning `hass`, and clears any stale own property before invoking the real setter.
- Bumped frontend cache keys to 0.13.5.

## 0.13.4

- Reimbursement history is now lazy-loaded when its navigation tab is opened instead of being a blocking top-level import.
- Failure to load the history module is isolated to that section and no longer causes Home Assistant to reject the entire Billy custom panel.
- Bumped all frontend cache keys to 0.13.4.

## 0.13.3

- Registered `billy-reimbursement-history.js` as a Home Assistant static path so the Billy panel can import the reimbursement history module successfully.
- Bumped frontend cache keys to force clients off the broken 0.13.2 module graph.

## 0.13.2

- Added a dedicated Reimbursement history section with completed/pending status, date/time, payer direction, amount, filters and detailed included items.
- Settlement snapshots now expose human-readable bill/recurring details for history, including a legacy fallback for reimbursements created before itemized amounts were stored.
- Reimbursements completed through the manual bill/recurring toggles are included in history too, with their original completion timestamp.
- Reimbursements can still be undone from the history detail without affecting provider-payment state.

## 0.13.1

- Fixed the Billy panel startup syntax error caused by escaped JavaScript template literals in the reimbursement payment-link helper.

## 0.13.0

- Added a reimbursement detail view showing the individual bills and recurring charges included in each user-to-user reimbursement.
- Added partial reimbursements: users can select which items to settle now while leaving the remaining items pending for a later payment.
- Payment-provider links in the detail view now follow the selected subtotal, while the existing full reimbursement action remains available.
- Settlement records now persist itemized reimbursement references so already-settled items are not offered again.

## 0.12.4

- Official parser installation now promotes a same-ID local custom parser automatically instead of failing with `A custom parser with this ID already exists`.
- Custom parser configuration is preserved during promotion, including category, enabled/automatic-import state, default payer and expense split.

## 0.12.3

- Fixed parser imports with no parser-specific split: Billy now falls back to its configured default split instead of failing with `The expense split is empty`.
- Failed parser imports now offer an `Add manually` action that opens the bill form prefilled with all usable parsed data, then removes the failed candidate after a successful manual save.

## 0.12.2

- Updater now shows a "restart required" state with a Restart button after an update is installed, and detects an update applied out-of-band (HACS or a manual copy) too — a Home Assistant restart is always needed for new code and version numbers to take effect.

## 0.12.1

- Maintenance release: repaired the test suite (128 passing) and exercised the new built-in update check. No user-facing changes.

## 0.12.0

- Added a built-in updater: an `update` entity surfaces new Billy versions in Settings > Updates with release notes, and Billy Settings > System has a "Billy updates" card that shows the changelog and installs the latest `main` build in place (a Home Assistant restart is still required to load it).
- Fixed inconsistent version info: the Billy panel and parser manager now show the version reported by the running integration (from `manifest.json`) instead of a value baked into the cached frontend bundle, so it always matches the Integrations page even right after an update.
- Backend error messages are no longer hardcoded in Italian: the websocket API returns stable error codes with an English fallback, and the Billy panel, Lovelace card and parser manager translate them into the user's language across English, Italian, Spanish, French, German and Portuguese.
- Added Spanish, French, German and Portuguese translations for the recurring-expense interval labels and the parser-manager bill-type labels (thanks @iDazai).
- Aligned frontend cache-busting and version constants to 0.12.0.

## 0.11.9

- Added a parsed-bill review queue directly to the Bills section, with Accept/Reject actions before an automatic parser candidate becomes a real expense.
- Added parser-specific default payer and split percentages, applied consistently to manual approval and automatic imports.
- Added support for PayPal.Me, Revolut, Venmo and Cash App reimbursement links with a preferred payment provider per payer.
- Added short/long billing-period support with exact dates and day-aware forecast normalization for split tariff-cycle bills.
- Monthly cashflow now follows the actual payment date for provider bills and includes recurring charges in their due month.
- Overview chart filters now persist per Home Assistant user/browser and the current-month panel focuses on unpaid bills due this month.
- Fixed Overview live refresh after changing a bill's paid state.
- Expanded Billy and Home Assistant localization across English, Italian, Spanish, French, German and Portuguese.
- Added the Lovelace widget pack and aligned frontend cache-busting/version constants to 0.11.9.

## 0.11.3

- Fixed the Overview spending chart so recurring expenses are visible instead of being hidden inside forecast totals.
- Actual 12-month chart bars now combine paid provider bills with materialized recurring charges due in the same month.
- Forecast bars now visibly split provider-bill estimates from recurring charges.
- Added a dedicated recurring-expense legend/segment while preserving the existing bill-category stacks.

## 0.11.2

- Fixed Billy panel modals being destroyed by normal Home Assistant state refreshes.
- The Recurring add/edit and reimbursement dialogs now stay open while the Home Assistant `hass` object is refreshed.
- Applied the same lifecycle fix to Dashboard, Bills and Settings data components so their UI is not unnecessarily reloaded on every HA state change.
- Data is still reloaded when the Billy update event fires or the Home Assistant websocket connection changes.

## 0.11.1

- Apply Billy's payer/split model to recurring expenses as well as provider bills.
- Add payer selection and editable split percentages to the Recurring create/edit dialog.
- Materialize each due recurring charge with an amount/payer/split snapshot so reimbursements are tracked per occurrence without creating fake provider bills.
- Add a reimbursement filter and reimbursement status badges to the Recurring tab.
- Add a per-occurrence reimbursement manager with quick reimbursed/pending checkboxes.
- Include due recurring charges in Overview/Lovelace split balances, PayPal quick-pay and recorded reimbursement history.
- Extend settlements with recurring occurrence IDs while keeping provider-payment status independent.
- Preserve completed reimbursement history when recurring rules are edited; open occurrences follow updated amount/payer/split values.
- Avoid retroactive debt when enabling an existing long-running recurring rule: tracking begins at the latest due occurrence, and paused periods are not backfilled when resumed.
- Refresh due recurring occurrences at Home Assistant local midnight.
- Upgrade storage schema to v11 with the new `recurring_occurrences` ledger.

## 0.11.0

- Added a first-class **Recurring** tab to the Billy sidebar application for subscriptions, mortgages, installment plans and other predictable charges.
- Recurring items support amount, billing frequency, activation date, optional expiration/renewal date, automatic renewal, renewal interval, provider, contract and notes.
- Installment plans can define a total number of installments; Billy derives the final due date and exposes remaining installments and remaining committed amount.
- Added pause/resume, edit, delete, search, kind and status filters for recurring items.
- Exact recurring due months are merged into the standard forecast, while normalized forecast includes their monthly-equivalent cost.
- Added recurring forecast totals to the Overview: monthly equivalent, next-month recurring charges, active recurring count and remaining installment commitment.
- Upcoming expenses now include individual recurring charges alongside estimated provider bills.
- Storage schema upgraded to v10 and persists recurring-expense rules independently from normal provider bills.
- Preserved the Lovelace card and its unversioned `/bill_tracker/bill-tracker-card.js` resource.
- Kept custom parser creation/edit/test/export/publish directly inside the Parser tab.

## 0.10.1

- Added custom parser authoring directly in the Billy Parser tab.
- Added create/edit, validate/test, save, export, delete and Experimental publishing actions for local custom parsers.
- Kept custom parser IDs immutable while editing to protect installed-parser identity.

## 0.10.0

- Added community Experimental parser publishing from Billy → Parser.
- Custom parsers can open a pre-filled GitHub submission containing only parser YAML.
- Added parser quality badges and filter: Verified, Tested, Experimental and Custom.
- Experimental publishing does not upload invoices, email bodies or attachments.
- Kept `/bill_tracker/bill-tracker-card.js` as the unversioned Lovelace resource.

## 0.9.1

- Add a **User reimbursements** filter to the full Bills tab: all, pending/partial, reimbursed, or not applicable.
- Show a reimbursement badge on every bill independently from the provider-payment badge.
- Add a quick reimbursement checkbox for bills that have not already been settled through reimbursement history.
- Manual reimbursement flags update the outstanding user-reimbursement balances without changing provider payment state.
- Bills linked to recorded settlements remain controlled by reimbursement history to avoid double-accounting.
- Reset a manual reimbursement flag when amount, payer, or split shares are edited.
- Migrate storage schema to v9 with explicit manual reimbursement state.

## 0.9.0

- Replace the sidebar **Bills** tab embedded Lovelace card with a full-width native bill list.
- Add manual bill creation plus edit, delete, search, bill-type/status/year filters, pagination and one-click provider payment status.
- Keep `custom:bill-tracker-card` available independently for normal Lovelace dashboards.
- Separate **provider bill payment** from **user reimbursements** in the data model.
- Rename the shared-payment concept to **Rimborsi tra utenti / User reimbursements**.
- Reimbursement confirmation no longer marks the underlying provider bills as paid; undoing a reimbursement does not change provider bill status.
- Calculate reimbursement balances from split shares independently of `expense.paid`, then subtract recorded reimbursements.
- Add a wide Overview reimbursement section with PayPal quick-pay, confirm reimbursement and recent reimbursement history.
- Add **Developer & support** to Billy Settings with Roberto Tortora credits, Billy/billy-parser repository links, GitHub and LinkedIn profiles, star calls-to-action and optional PayPal.Me donation.
- Preserve the parser catalog UI, Outdated markers, midnight refresh and unversioned Lovelace card resource.

## 0.8.0

- Redesign the Billy sidebar panel as a full application instead of using the Lovelace card as its Dashboard.
- Add a wide **Overview** dashboard with KPI summaries, actual/forecast spending chart, current-month category breakdown, upcoming bills, recent bills and parser-health indicators.
- Add a dedicated **Bills** tab that keeps the existing Lovelace card and all of its mature bill-management features intact.
- Move core Billy settings into the panel with native CRUD for bill types and payers.
- Add IMAP source selection directly under Billy Settings using the existing parser source API.
- Add a system/status settings section showing Billy version, currency, configured entities and parser update health.
- Keep the existing Home Assistant Options Flow as a fallback instead of making it the primary Billy UI.
- Preserve parser search, bill-type filtering, Outdated states, daily catalog refresh and the unversioned Lovelace resource URL.

## 0.7.0

- Add a first-class **Billy** sidebar panel at `/billy` while keeping `custom:bill-tracker-card` available for Lovelace dashboards.
- Reuse the existing full Billy card in the panel Dashboard and expose parser management as a dedicated tab.
- Fix parser search typing backwards by updating only the result list while the search input keeps focus/caret state.
- Add a **bill type** filter to parser management in addition to country, install state and sorting.
- Refresh the remote parser catalog automatically every day at **00:00 Home Assistant local time**; this refreshes only `parser.json` and never silently updates installed parser YAML files.
- Keep explicit Outdated/update states and manual per-parser updates.
- Register the sidebar through Home Assistant's supported custom-panel loader.
- Keep the Lovelace resource URL unversioned: `/bill_tracker/bill-tracker-card.js`.

## 0.6.6

- Fix the blank `/billy-parser` page by registering the parser manager through Home Assistant's supported **custom panel** loader instead of declaring a non-existent built-in panel type.
- Make panel registration update-safe so an integration reload can replace the stale 0.6.5 panel definition.
- Register the Lovelace card resource as `/bill_tracker/bill-tracker-card.js` with no manifest-version query string.
- Keep the parser-manager module independently versioned for browser cache invalidation.
- Preserve all parser catalog, filtering, install/update/remove and Outdated-state functionality introduced in 0.6.5.

## 0.6.4

- Fix automatic parsing of PDF attachments exposed by IMAP as `application/octet-stream` when the parser filename rule matches.
- Preserve `imap_content` attachment metadata when merging the later `imap.fetch` response.
- Allow failed IMAP parse attempts to be retried after updating a parser instead of permanently deduplicating the UID.
- Include available attachment metadata in parser failure logs for easier diagnosis.

# Billy 0.6.3

## Added

- Parser-engine support for abbreviated Italian month names and two-digit years used by provider PDFs such as `01 lug 26 - 31 lug 26`.

## Fixed

- Automatic imports now anchor the bill to the parsed competence/billing month first, then the invoice issue date, instead of incorrectly preferring a later due date.

# Billy 0.6.2

## Fixed

- Restored bill-history filtering and pagination in the Lovelace card.
- Restored the styled PayPal payment action and localized bill counts in reimbursements.
- Fixed IMAP callback scheduling for current Home Assistant thread-safety checks.
- Fixed hassfest manifest key order and config-entry-only schema warning.
- Delayed Lovelace resource registration until Lovelace setup completes.
- Bumped frontend asset version to 0.6.2 to avoid stale cached UI files.

# Billy 0.6.0

## Added

- Automatic email bill parsing subsystem.
- External parser catalog support via `billy-parser/parser.json`.
- SHA-256, size, identity, schema and minimum-version validation for downloaded parsers.
- Declarative YAML parser engine with weighted detection and metadata prefilters.
- Home Assistant IMAP source adapter using `imap.fetch` and `imap.fetch_part`.
- PDF text extraction with `pypdf`.
- Email/PDF field cross-verification and confidence scoring.
- Pending import queue with approve/reject actions.
- Optional verified auto-import, disabled by default.
- Source and invoice-level deduplication.
- Official/custom parser persistence outside the HACS integration directory.
- Custom parser creation, validation and authenticated YAML export.
- Native options-flow pages for source, catalog, installed parser and review management.
- Parser WebSocket API for future frontend surfaces.

## Privacy

- Message bodies are fetched only after sender/subject metadata passes at least one
  installed parser prefilter.
- Attachments are fetched only when required by the selected parser.
- Raw message bodies and PDF bytes are not persisted by Billy.
- No mail or invoice content is sent to the parser repository.

## Not included yet

- OCR/scanned-PDF support.
- Gmail API or Outlook OAuth source adapters.
- Historical mailbox crawling.
