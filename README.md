<p align="center">
  <img src="docs/images/billy-logo.png" alt="Billy logo" width="180">
</p>

# Billy

## Billy 0.12.1

Billy keeps the Lovelace `custom:bill-tracker-card`, while `/billy` is the full-size application.

Billy is a Home Assistant bill manager focused on household expenses: provider bills, recurring costs, forecasts, payment tracking, shared expenses, reimbursements and automatic bill parsing from email.

### What's new in 0.12.0

- **Built-in updater** — Billy exposes an `update` entity (Settings › Updates) with release notes and one-click install, and a "Billy updates" card in Settings › System that shows the changelog and installs the latest build in place. A Home Assistant restart is still required to load the new code.
- **Consistent version display** — the panel and parser manager now report the version of the running integration instead of a value baked into the cached frontend bundle, so it matches the Integrations page even right after an update.
- **Localized error messages** — the websocket API now returns stable error codes with an English fallback instead of hardcoded Italian text, and the Billy panel, Lovelace card and parser manager translate them into the user's language (English, Italian, Spanish, French, German, Portuguese).

### What's new in 0.11.9

- **Short and long billing periods** — Billy now preserves exact billing-period dates (`YYYY-MM-DD`) and automatically identifies unusually short or long bills, such as split invoices generated after a tariff or contract change.
- **Smarter forecasts for split bills** — short/long bills are normalized using their actual number of covered days before they are used for future estimates, so two partial invoices are not mistaken for two complete billing cycles.
- **Day-aware normalized history** — costs that span multiple calendar months are distributed according to the real number of covered days instead of being split evenly by month.
- **Billing-period badges** — the Billy application and Lovelace card can highlight short/long periods and show the number of billed days.
- **Exact parser billing dates** — automatic imports now keep the complete `period_start` and `period_end` dates extracted by community parsers instead of reducing them to month-only values.
- **CSV/backup compatibility** — exact billing-period dates are preserved during export/import and in Billy backups, while existing month-only records remain supported.
- **Multiple reimbursement providers** — each payer can configure PayPal.Me, Revolut, Venmo and Cash App and select a preferred payment method.
- **Provider-aware payment buttons** — reimbursement actions automatically use the payer's preferred provider and show labels such as `Pay with Revolut`, `Pay with Venmo` or `Pay with Cash App` instead of assuming PayPal.
- **Backward-compatible PayPal migration** — existing `paypal_me` payer settings are automatically migrated to the new multi-payment model.
- **Cashflow-aware monthly spending** — paid bills are counted in the month of their actual `payment_date`, while recurring charges are counted in the month of their scheduled due date, so monthly and yearly spending reflects when money really leaves the household budget.
- **New Lovelace widget pack** — Billy now provides dedicated Summary, Spending, Breakdown, Upcoming, Recurring, Balances and Parser Status cards for custom Home Assistant dashboards.
- **Improved localization** — Billy's sidebar, parser manager, widgets, payment settings and Home Assistant configuration strings are now fully localized in English, Italian, Spanish, French, German and Portuguese.
- **Community parser workflow documentation** — the README now documents Catalog v2, country-specific parser catalogs, Experimental/Verified lifecycle, anonymous community feedback and how to connect Home Assistant IMAP sources.
- **Parsed-bill review queue in Bills** — parser candidates waiting for approval are now visible directly in the Bills section, where they can be accepted or rejected before becoming real expenses.
- **Parser-specific payer defaults** — each parser can now define its own default payer and split percentages, which are applied when a parsed bill is accepted or automatically imported.

### What Billy can do

- Track provider bills manually or import them automatically from email.
- Track subscriptions, mortgages, installment plans and other recurring expenses independently from provider invoices.
- Forecast future costs and normalize non-monthly bills into monthly-equivalent spending.
- Split bills between multiple payers and track reimbursements separately from provider payment status.
- Open the configured PayPal.Me, Revolut, Venmo or Cash App reimbursement link for each payer.
- Install declarative parsers from the community `billy-parser` catalog.
- Create and test local custom parsers directly from Billy.
- Share a custom parser with the community as Experimental without uploading the original invoice, email or PDF.
- Use Billy either as the full `/billy` sidebar application or through compact Lovelace dashboard widgets.

### Recurring expenses

The new **Ricorrenti / Recurring** tab tracks predictable costs that normally do not arrive as a monthly invoice email: subscriptions, mortgages, installment plans and other fixed recurring charges. Each rule can define an amount, cadence (monthly, every 2/3/4/6 months or yearly), activation date, optional expiration/renewal date, automatic renewal, provider/contract metadata and notes.

Installment plans can also define a total installment count. Billy calculates the final due date, how many installments remain and the remaining committed amount. Recurring rules can be paused, resumed, edited or deleted without creating fake provider invoices in bill history.

Recurring charges are included in the regular **forecast** on their exact due months. The normalized forecast also includes their monthly-equivalent cost, so an annual subscription contributes `amount / 12` to the normalized monthly planning view. Overview now shows recurring monthly equivalent, charges due next month, active recurring count and remaining installment commitment.

Provider bills and recurring rules remain separate concepts: a recurring rule predicts a cost; it does not mark a provider invoice as paid and it is not an email-parser result.

### Split and reimbursements for recurring expenses

Recurring charges use the same payer/split model as normal bills. A recurring rule stores its usual payer and split percentages; when a charge becomes due, Billy materializes a lightweight occurrence containing the amount and payer/split snapshot. That occurrence participates in **Rimborsi tra utenti / User reimbursements** and in PayPal quick-pay exactly like a split bill, but it is not inserted into provider-bill history.

Each due recurring occurrence has its own reimbursement status and can be marked reimbursed/pending from **Billy → Ricorrenti → Gestisci rimborsi**. Reimbursements confirmed from Overview are stored in the shared reimbursement history and cannot be overridden by the quick checkbox until the recorded reimbursement is undone.

To avoid accidental historical debt, adding or migrating a long-running subscription/mortgage starts reimbursement tracking from its latest due charge, not from the original activation date. Future due occurrences are materialized daily at Home Assistant local midnight. Pausing a recurring rule stops new occurrences; resuming starts again from the next real charge without backfilling the paused gap.

### Parser authoring in Billy

The **Parser** tab can create a new local custom parser, edit it, validate/test it against optional email metadata, export it and share it with the community. No invoice PDF, email body or attachment is uploaded by the community publish action.

## Automatic bill parsing

Billy can listen to one or more Home Assistant IMAP sources and automatically detect supported provider emails. The parser runtime is deliberately declarative: community parsers are YAML definitions, not executable Python, JavaScript or shell code.

The high-level flow is:

```text
Provider email arrives
        ↓
Home Assistant IMAP emits metadata
        ↓
Billy prefilters parsers by sender / subject
        ↓
Only potentially matching messages are fetched
        ↓
Email body and required attachments are extracted
        ↓
Parser detection rules calculate a score
        ↓
Fields are extracted from email and/or PDF text
        ↓
Cross-source verification and deduplication
        ↓
Review or automatic import, depending on configuration
```

### Privacy-first fetching

Billy first evaluates inexpensive metadata such as sender, subject and attachment information. The complete message is fetched only when at least one installed parser passes its prefilter. Parsers can then use the email body and selected attachments.

PDF attachments are processed as text documents. Billy does not currently perform OCR, so scanned image-only PDFs may require a future OCR-capable extractor or a parser that can rely on the email body instead.

## Connecting your email

Billy does **not** store your mailbox password and does not create its own mail account connection. It uses Home Assistant's existing **IMAP integration**.

1. In Home Assistant, add and configure the **IMAP** integration for the mailbox that receives your bills.
2. Verify that Home Assistant receives messages from that account correctly.
3. Open **Billy → Settings → Automatic parsing / IMAP sources**.
4. Select one or more IMAP entries that Billy is allowed to use.
5. Open **Billy → Parser**, refresh the catalog and install the parsers for your providers.
6. Configure each installed parser with the Billy bill type it should import into and choose whether automatic import is enabled.

Billy can use multiple IMAP integrations at the same time, which is useful when household bills arrive on different mailboxes.

The parser source configuration stores only the selected Home Assistant IMAP entry IDs. Mail credentials continue to be managed by Home Assistant.

## The community parser catalog

Official/community parsers live in the separate [`billy-parser`](https://github.com/robin994/billy-parser) repository. Billy uses the scalable Catalog v2 layout:

```text
catalog/
  index.json
  it.json
  fr.json
  ...

parsers/
  <country>/<provider>/<type>.yaml
```

Billy first downloads `catalog/index.json`, selects the shard for the configured/Home Assistant country and downloads only that country's catalog. Parser YAML is downloaded only when a parser is installed or updated.

The catalog refreshes automatically every day at **00:00 Home Assistant local time**. Installed parsers are never silently replaced just because the remote catalog changed.

### Parser lifecycle

The parser lifecycle is community-driven:

```text
Local custom parser
        ↓
Share with community
        ↓
Automatic repository validation
        ↓
Experimental
        ↓
Users install and test it
        ↓
Community feedback
        ↓
Verified
```

Lifecycle values are:

- **Experimental** — newly published parser that still needs community validation.
- **Verified** — parser that reached the automatic community verification threshold.
- **Outdated** — parser that is no longer recommended, usually because the provider format changed or a replacement exists.

No maintainer review is required for the normal Experimental → Verified path. The `billy-parser` automation validates submissions, records feedback and regenerates the catalog.

### Sharing a parser

From a locally saved custom parser, click **Share with community / Condividi con la community**. Billy opens a machine-readable GitHub submission containing parser metadata and the YAML definition.

Billy does **not** attach:

- the original bill PDF;
- the email body;
- customer names or addresses;
- bill amounts from the source message;
- mailbox credentials.

The repository automation validates the submission and, when valid, publishes it as `experimental`.

### Community feedback

Installed Experimental parsers can be rated from Billy as:

- **Working**;
- **Partial**;
- **Failed**.

Feedback is tied to a specific parser version. Billy generates a persistent random local community identifier and sends only a SHA-256 fingerprint scoped to `parser_id + version`, allowing duplicate votes to be avoided without sending the original local identifier or bill contents.

When a new parser version is published, its feedback starts from zero. Votes for an older version are not inherited by the new one.

## Lovelace dashboard widgets

Billy now ships a set of small dashboard cards in addition to the full `custom:bill-tracker-card` and the `/billy` sidebar application. They all use the same Billy WebSocket data and do not duplicate the backend business logic.

The widget pack is loaded automatically with Billy's existing Lovelace resource, so no additional resource URLs are required.

Available cards:

| Card          | Lovelace type                     | Purpose                                                                                        |
| ------------- | --------------------------------- | ---------------------------------------------------------------------------------------------- |
| Summary       | `custom:billy-summary-card`       | Current month, outstanding bills, next month, yearly total, recurring costs and reimbursements |
| Spending      | `custom:billy-spending-card`      | Historical spending plus recurring costs and forecast                                          |
| Breakdown     | `custom:billy-breakdown-card`     | Ranked bill-type / recurring-cost breakdown                                                    |
| Upcoming      | `custom:billy-upcoming-card`      | Upcoming unpaid bills, forecasts and recurring charges                                         |
| Recurring     | `custom:billy-recurring-card`     | Active subscriptions, mortgages, installments and next due dates                               |
| Balances      | `custom:billy-balances-card`      | User-to-user reimbursements and PayPal quick-pay links                                         |
| Parser status | `custom:billy-parser-status-card` | Installed parsers, Experimental parsers, updates and errors                                    |

All cards are registered in `window.customCards`, so they are available from the Home Assistant Lovelace card picker as well as through YAML configuration.

### Summary widget

```yaml
type: custom:billy-summary-card
title: Billy
```

### Spending chart

```yaml
type: custom:billy-spending-card
title: Spending
months: 12
forecast_months: 3
show_recurring: true
```

### Expense breakdown

```yaml
type: custom:billy-breakdown-card
title: This month
limit: 8
show_recurring: true
```

### Upcoming expenses

```yaml
type: custom:billy-upcoming-card
title: Upcoming expenses
days: 90
limit: 8
forecast_months: 3
```

### Recurring expenses

```yaml
type: custom:billy-recurring-card
title: Recurring
limit: 8
active_only: true
```

### Reimbursements / balances

```yaml
type: custom:billy-balances-card
title: Reimbursements
limit: 6
show_paypal: true
```

### Parser status

```yaml
type: custom:billy-parser-status-card
title: Billy Parser
```

### Example Billy dashboard

```yaml
type: grid
columns: 2
square: false
cards:
  - type: custom:billy-summary-card

  - type: custom:billy-parser-status-card

  - type: custom:billy-spending-card
    months: 12
    forecast_months: 3
    show_recurring: true

  - type: custom:billy-breakdown-card
    limit: 8
    show_recurring: true

  - type: custom:billy-upcoming-card
    days: 90
    limit: 8

  - type: custom:billy-recurring-card
    limit: 8

  - type: custom:billy-balances-card
    show_paypal: true
```

### Main sidebar areas

- **Panoramica / Overview** — full-width dashboard, forecasts, reimbursements and recurring commitments.
- **Bollette / Bills** — complete provider-bill history with manual CRUD, payment status and user-reimbursement status.
- **Ricorrenti / Recurring** — subscriptions, mortgages, installments and predictable scheduled costs.
- **Parser** — country-sharded community catalog, local parser authoring, testing, sharing and Experimental feedback.
- **Impostazioni / Settings** — bill types, payers, IMAP sources, system status and developer/support links.

The Lovelace resource remains `/bill_tracker/bill-tracker-card.js` without a version query string. The widget pack is loaded from this same bootstrap resource.

## Billy 0.9.1

Billy keeps the Lovelace `custom:bill-tracker-card`, while the `/billy` sidebar panel is the full-size application.

### Sidebar application

- **Panoramica / Overview**: wide dashboard with KPI, forecast, bill-type breakdown, upcoming/recent bills, parser health and a dedicated **Rimborsi tra utenti / User reimbursements** section.
- **Bollette / Bills**: native complete bill list instead of embedding the Lovelace card. It includes search/filtering, pagination, manual bill creation, edit/delete actions and a quick provider-payment toggle.
- **Parser**: scalable catalog with country/type/status filters, Outdated markers and explicit install/update/remove actions.
- **Impostazioni / Settings**: bill types, payers, IMAP sources, system status and a new **Developer & support** area.

### Provider payments vs user reimbursements

Billy now treats these as two independent concepts:

- **Bolletta pagata / Provider paid** means the configured payer actually paid the utility/provider invoice.
- **Rimborso tra utenti / User reimbursement** means another Billy participant reimbursed their share to the payer.

Confirming a reimbursement no longer marks provider bills as paid, and undoing a reimbursement no longer reopens provider bills. Split balances are calculated from bill shares independently of the provider-payment checkbox, then reduced by recorded reimbursements.

The Overview provides quick **Pay with PayPal** and **Confirm reimbursement** actions, plus recent reimbursement history.

### Reimbursement status in Bills

The full **Bollette / Bills** tab now has an independent reimbursement filter and status for each bill. You can filter bills by **To reimburse**, **Reimbursed**, or **No reimbursement**. A bill with multiple participants can also show **Partially reimbursed**.

When no reimbursement has already been recorded in the reimbursement history, the row includes a quick checkbox to mark all user reimbursements for that bill as completed or pending. This changes only the user-to-user balance; it never changes whether the provider invoice itself is paid. Bills linked to recorded reimbursement history are intentionally locked to that history to prevent double-accounting.

### Developer & support

The Billy Settings panel now credits **Roberto Tortora** as creator/maintainer and links to:

- Billy: `https://github.com/robin994/billy`
- billy-parser: `https://github.com/robin994/billy-parser`
- GitHub profile: `https://github.com/robin994`
- LinkedIn: `https://www.linkedin.com/in/roberto-tortora-379928109/`
- optional PayPal.Me support: `https://paypal.me/rtortora94`

Both repositories include an explicit action encouraging users to open the project and leave a GitHub star.

The parser catalog continues to refresh automatically every day at **00:00 Home Assistant local time** without silently upgrading installed parser YAML files. The Lovelace resource stays unversioned at `/bill_tracker/bill-tracker-card.js`.

## 0.6.3 parser compatibility

Billy 0.6.3 adds support for abbreviated Italian dates used in provider invoices and anchors automatic imports to the billing/competence month before the due date. The 0.5.2-based dashboard UI from 0.6.2 is unchanged.

# Billy 0.6.2

Billy is a Home Assistant custom integration for tracking recurring household bills,
forecasting upcoming costs, splitting expenses between payers and importing bill data.

This archive is a **complete source package** for the integration. It is not an overlay:
`custom_components/bill_tracker` contains the full Python integration, Lovelace frontend,
translations, automatic parser runtime, IMAP source adapter and tests required by this build.

## 0.6.x automatic parsing

- External `billy-parser` catalog with SHA-256 verified parser downloads. Current Billy versions use the country-sharded Catalog v2, with legacy `parser.json` retained only as compatibility fallback.
- Declarative YAML parser schema v1; downloaded parsers cannot execute Python/JavaScript/shell code.
- Official parsers stored under `/config/billy/parsers/official`.
- Custom parsers stored under `/config/billy/parsers/custom` and exportable.
- Home Assistant IMAP integration using metadata prefiltering before message-body fetching.
- PDF text extraction via `pypdf`; OCR is intentionally out of scope.
- Email/PDF cross-verification, confidence scoring, review queue and optional verified auto-import.
- Source and semantic deduplication.
- Parser/source/review management through the native Billy options flow.

## 0.6.2 fixes

- Restored the bill-history filters removed by the first 0.6 frontend rewrite:
  bill type, paid/unpaid status, all history/year/month range, page size and pagination.
- Restored the styled **Pay with PayPal** action and localized reimbursement counts.
- Fixed IMAP event scheduling so parser processing runs on the Home Assistant event loop.
- Fixed hassfest manifest ordering and the config-entry-only `CONFIG_SCHEMA`.
- Registers the Lovelace resource after Lovelace setup and bumps frontend assets to 0.6.2
  to invalidate stale browser caches.

See `docs/AUTOMATIC_PARSING.md` for parser setup and privacy details.

## Billy sidebar panel

Billy 0.7.0 adds a sidebar panel at `/billy` while keeping `custom:bill-tracker-card` available for Lovelace dashboards. The panel reuses the existing bill UI and includes scalable parser management in the same application surface.

## Community parser publishing

Billy's Parser page can share a locally saved custom parser with the community. Billy opens a machine-readable GitHub submission containing parser metadata plus the declarative YAML. The `billy-parser` workflow validates it and publishes valid submissions automatically as **Experimental**, without maintainer approval.

Community feedback is version-scoped and drives automatic promotion from **Experimental** to **Verified**. Parsers that are no longer recommended can be marked **Outdated** and point to a replacement. The catalog exposes only aggregate feedback counts; it does not expose installation fingerprints or bill data.
