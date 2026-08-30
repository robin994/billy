# Changelog

## 0.11.10

- Backend error messages are no longer hardcoded in Italian: the websocket API returns stable error codes with an English fallback, and the Billy panel, Lovelace card and parser manager translate them into the user's language across English, Italian, Spanish, French, German and Portuguese.
- Added Spanish, French, German and Portuguese translations for the recurring-expense interval labels and the parser-manager bill-type labels (thanks @iDazai).
- Fixed inconsistent version info: the Billy panel and parser manager now show the version reported by the running integration (from `manifest.json`) instead of a value baked into the cached frontend bundle, so it always matches the Integrations page even right after an update.
- Added a built-in updater: an `update` entity surfaces new Billy versions in Settings > Updates with release notes, and Billy Settings > System has a "Billy updates" card that shows the changelog and installs the latest `main` build in place (a Home Assistant restart is still required to load it).
- Aligned frontend cache-busting and version constants to 0.11.10.

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
