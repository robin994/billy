# Billy — User guide

Detailed setup and usage for provider bills, recurring expenses, reimbursements, IMAP parsing, community parsers and Lovelace widgets. For a quick introduction see the [README](../README.md).

## What Billy can do

- Track provider bills manually or import them automatically from email.
- Track subscriptions, mortgages, installment plans and other recurring expenses independently from provider invoices.
- Forecast future costs and normalize non-monthly bills into monthly-equivalent spending.
- Split bills between multiple payers and track reimbursements separately from provider payment status.
- Open the configured PayPal.Me, Revolut, Venmo or Cash App reimbursement link for each payer.
- Install declarative parsers from the community `billy-parser` catalog.
- Create and test local custom parsers directly from Billy.
- Share a custom parser with the community as Experimental without uploading the original invoice, email or PDF.
- Use Billy either as the full `/billy` sidebar application or through compact Lovelace dashboard widgets.

## Manage several homes with Houses

Go to **Settings / Impostazioni → Houses / Case** to add or rename houses,
select a default house, and remove unused houses. Billy creates one default
house for existing installations and assigns existing bills and recurring
expenses to it without changing their amounts or payment status.

In **Bills / Bollette**, choose a house in the toolbar to see just its bills
or **All houses / Tutte le case**. In the bill editor, select the house
associated with that invoice. **Recurring → Expenses** similarly supports
house assignment for subscriptions, mortgages and other recurring costs.

**Overview / Dashboard** also has a House selector: **All houses** uses
the existing combined totals, while an individual house shows only its
bills, recurring charges, historical spending and forecasts. The common
bank accounts, income, parsers and Home Assistant user accounts are *not*
split into separate houses or duplicated. House views exclude global income
from their scoped KPIs rather than misrepresenting it as belonging to a house.
In **Settings → Bill types**, each type can create independent automatic
unpaid-bill reminders for each House. Enable the schedule for a house and
choose its own creation day, due day, amount mode (last/forecast/fixed),
optional provider and contract. Existing single-house rules keep their
original association. No extra bill types or Home Assistant users are needed.

This is **one shared Billy workspace**, not financial data segregation by
legal entity or per-user authorization. Houses do not enforce privacy,
access permissions or legal compliance. For independent regulated records,
use genuinely separated environments and appropriate access controls.

## Accounts, income and recurring plans

The main **Accounts / Conti** tab shows balances and internal transfer history.
Select an account card to filter its outgoing transfers, or choose an account
and direction (incoming, outgoing or both) in the history controls. The
**Record a transfer** button moves money between two manually tracked accounts.

Account creation, editing, deletion and default-account selection are in
**Settings / Impostazioni → Accounts / Conti**. Accounts require a payer owner,
which can be configured under **Settings → Payers**. Billy does not access
bank accounts or import bank transactions.

**Income / Entrate** is for actual and expected individual receipts. Use
**Recurring / Ricorrenti → Expenses / Spese** for recurring costs and
**Recurring / Ricorrenti → Income / Entrate** for recurring income plans.
Recurring income estimates remain distinct from expenses and only confirmed
receipts count as actual income.

See [Income, accounts and document archive](INCOME_AND_DOCUMENT_ARCHIVE.md)
for details and accounting rules.

## Recurring expenses

The **Ricorrenti / Recurring → Expenses / Spese** section tracks predictable costs that normally do not arrive as a monthly invoice email: subscriptions, mortgages, installment plans and other fixed recurring charges. Each rule can define an amount, cadence (monthly, every 2/3/4/6 months or yearly), activation date, optional expiration/renewal date, automatic renewal, provider/contract metadata and notes.

For **Installment plan** or a **fixed-term mortgage**, enter the *regular
installment amount* under **Amount**, the total number of installments, and
optionally the **Total to repay**. Billy calculates the last due date and,
when the total is provided, a different final installment to make the sum
exact in cents. For example, a total of EUR 10,520.09 with 21 monthly
installments of EUR 500.00 starting on February 1, 2026 yields 20
installments of EUR 500.00 followed by EUR 520.09 on October 1, 2027.
Renewal controls are not applicable to fixed-term plans.

For a fixed-term plan with a total, **Still to pay** is the total less
**confirmed** installment payments, even if those payments were late or
retroactive. A mortgage's outstanding *principal*, as distinct from
scheduled principal plus interest and other charges, is **not** calculated.
Existing recurring plans with no total retain their legacy calendar-based
estimated number and value of installments remaining. Recurring rules can
be paused, resumed, edited or deleted without creating fake provider invoices
in bill history.

Recurring charges are included in the regular **forecast** on their exact due months. The normalized forecast also includes their monthly-equivalent cost, so an annual subscription contributes `amount / 12` to the normalized monthly planning view. Overview now shows recurring monthly equivalent, charges due next month, active recurring count and remaining installment commitment.

Provider bills and recurring rules remain separate concepts: a recurring rule predicts a cost; it does not mark a provider invoice as paid and it is not an email-parser result.

### Record historical or current recurring payments

Under **Recurring / Ricorrenti → Expenses / Spese**, choose **Payments** on
any mortgage, installment plan, subscription or recurring expense. Billy shows
the individual scheduled installments, including past due dates, with an
independent **Paid / Not confirmed** status. A scheduled installment is *not*
proof that money left an account.

Choose **Record payment** on a due installment and enter its **actual payment
date**, **actual amount**, **debited account** (if configured) and optional
note. You can also **Edit payment** or **Undo payment** without changing the
recurring rule or reimbursements between household members. Future due dates
cannot be confirmed as paid before they arrive.

Confirmed payments affect the account balance and historical spending **on
the actual payment date**, even if the installment was due in an earlier
month. Scheduled but unconfirmed installments remain forecasts. If the same
payment is already registered as a **paid Bill in Billy**, use **Already
recorded as a paid Bill** to mark the installment paid without adding the
expense twice; check this against your financial records before selecting it.
Accounts have dated opening balances: a historical payment cannot be posted
to an account opened after that payment's date.

For historical mortgage payments, verify the rule's **activation date** first:
the first scheduled installment must be correct. Editing the recurrence in a
way that would orphan existing confirmed payments is blocked. The loan's
outstanding principal is **not** automatically amortized; Billy tracks
installment payments and account cash outflows, not principal-versus-interest
allocations. Do not use transfers between your own accounts as a substitute
for mortgage payments: transfers do not create expenses.

**Reconciliation:** if you previously recorded mortgage installments as
ordinary paid Bills, use the already-recorded checkbox to avoid counting the
same cash outflow again. If you previously used a negative-opening-balance
account and internal transfers as a workaround, make a backup, verify actual
balances against statements, then manually reconcile/remove the fictitious
transfers and correct opening snapshots as appropriate. Billy will **not**
delete or reinterpret those earlier records automatically.

For provider invoices that need a paid/unpaid monthly checklist, enable **Create an unpaid bill each period** in **Settings → Bill types**. See [Monthly bill checklist](docs/BILL_PLACEHOLDERS.md).

## Split and reimbursements for recurring expenses

Recurring charges use the same payer/split model as normal bills. A recurring rule stores its usual payer and split percentages; when a charge becomes due, Billy materializes a lightweight occurrence containing the amount and payer/split snapshot. That occurrence participates in **Rimborsi tra utenti / User reimbursements** and in PayPal quick-pay exactly like a split bill, but it is not inserted into provider-bill history.

Each due recurring occurrence has its own reimbursement status and can be marked reimbursed/pending from **Billy → Ricorrenti → Gestisci rimborsi**. Reimbursements confirmed from Overview are stored in the shared reimbursement history and cannot be overridden by the quick checkbox until the recorded reimbursement is undone.

To avoid accidental historical debt, adding or migrating a long-running subscription/mortgage starts reimbursement tracking from its latest due charge, not from the original activation date. Future due occurrences are materialized daily at Home Assistant local midnight. Pausing a recurring rule stops new occurrences; resuming starts again from the next real charge without backfilling the paused gap.

## Parser authoring in Billy

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

Billy downloads `catalog/index.json` and the country catalog shards listed there, so providers from all catalog countries can be discovered. Individual parser YAML files are downloaded only when installed or updated.

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

Billy ships seven supported dashboard widgets alongside the `/billy` sidebar application. They share the Billy WebSocket backend rather than duplicating business logic.

The widget pack is registered automatically via `/bill_tracker/billy-lovelace.js?v=0.17.0-r1`. No manual resource URLs are required for a storage-mode installation. Existing legacy cards remain compatible via the separately registered `/bill_tracker/bill-tracker-card.js?v=0.17.0-r1` host until Billy 1.0.0.

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
columns: full
```

To show only the current month's unpaid bill checklist, including overdue entries and entries without a due date:

```yaml
type: custom:billy-upcoming-card
title: Bills to pay this month
filter: unpaid_this_month
limit: 20
```

On a Home Assistant Sections dashboard, `columns: full` makes the Upcoming card
occupy the full section width so longer invoice names can use two lines. Other
widgets default to six columns; their height follows their contents. To align
Recurring and Reimbursements cards side by side at an identical height, set
`rows: 3` on both cards (adjust as needed for the number of displayed items).
These optional `columns` and `rows` settings are widget defaults for Sections;
Home Assistant's own dashboard editor can also override the grid dimensions.

## Recurring expenses

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

## Main sidebar areas

- **Panoramica / Overview** — full-width dashboard, forecasts, reimbursements and recurring commitments.
- **Bollette / Bills** — complete provider-bill history with manual CRUD, payment status and user-reimbursement status.
- **Ricorrenti / Recurring** — subscriptions, mortgages, installments and predictable scheduled costs.
- **Parser** — country-sharded community catalog, local parser authoring, testing, sharing and Experimental feedback.
- **Impostazioni / Settings** — bill types, payers, IMAP sources, system status and developer/support links.

In Billy 0.15.1 and later, the widget resource is `/bill_tracker/billy-lovelace.js` with a version query parameter. The historical `/bill_tracker/bill-tracker-card.js` endpoint continues to serve only the deprecated legacy card.
