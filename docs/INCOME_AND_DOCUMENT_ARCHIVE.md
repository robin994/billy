# Income and document archive (issue #12 — development preview)

This document describes the initial **local development** implementation. It is not a
published release, and it has not yet been validated on a running Home Assistant instance.

## Automatic invoice PDF archive

Open **Settings → Bill types**, edit a category, and enable **Automatically archive
invoice PDFs**. Configure:

- **Folder inside Home Assistant media**: relative path such as `billy/documents`.
  Documents are saved at `<media>/<folder>/<YYYY>/<MM>/<BillType>/<bill-id>-<hash>.pdf`.
  The period currently uses Billy's billing month, not the issue date.
- **Approved download host**: an exact hostname (optionally with a port), such
  as `paperless.local:8000`. HTTP(S) download URLs on other hosts and HTTP
  redirects are rejected. Leave it blank if the only source is IMAP attachments.
- **Document URL**: optional field on each bill. When the category enables
  archiving and the hostname is approved, Billy attempts to download the PDF.
  The archived PDF can later be viewed inline from the bill row.
- **Manual PDF attachment**: edit an existing bill to upload a local PDF
  (maximum 8 MiB) even if automatic archiving is disabled. The file is stored
  in the same Home Assistant media directory. Replacing and deleting an
  attachment permanently remove the prior archived file, after explicit
  confirmation. The current bill must already exist before it can receive a PDF.
- **IMAP imports**: when an imported bill matches an opted-in category, Billy
  attempts to retrieve its original PDF attachment through Home Assistant's
  IMAP integration after successfully importing the bill. If an attachment
  cannot be retrieved, the bill is still imported normally.

**Storage choices:** A local `media` directory or a NAS/network filesystem
mounted into Home Assistant's local media directory is supported in this initial
implementation. Direct SFTP and WebDAV clients are **not yet implemented**.
Paths are constrained to the media directory; no arbitrary filesystem paths
are accepted. To use a share, mount it first in Home Assistant.

The downloader has an **8 MiB** limit per PDF, verifies the PDF signature,
does not follow HTTP redirects, rejects URL credentials, and requires an
explicitly approved source host. Protected Paperless-ngx links requiring a
session or an API token generally cannot be downloaded automatically by this
simple URL fetcher; they can still be stored as external links.

The JSON backup stores **document metadata and paths**, **not PDF bytes**.
Back up the Home Assistant media directory (and any external share) separately.
Changing a document URL/category without explicitly deleting the PDF does not
automatically clean up the old archived file. Using the dedicated **Delete PDF**
action removes the attached file from the media directory, and clears its URL.
An authenticated Billy WebSocket command retrieves archived content. Only Home
Assistant administrators can manually upload/delete PDF files or enable/trigger
remote archiving; uploads are sent as ordered, bounded chunks rather than one
large WebSocket message.

## Income management

Open **Income / Entrate** in the Billy sidebar for confirmed and expected
receipts. Open **Recurring / Ricorrenti → Income / Entrate** to manage
recurring income plans. These sections support:

- Custom income categories, plus preconfigured salary, pension, rent, bonus,
  external refund, and other categories.
- The names of those six default income categories are localized in English,
  Italian, Spanish, French, German and Portuguese. Category IDs stay unchanged;
  renaming a category or editing its color preserves custom naming.
- One-time income with an expected date, estimated amount, confirmed receipt,
  actual net amount, optional receipt date, and note.
- Recurring plans (1, 2, 3, 4, 6, or 12 months), with fixed/last/average
  3, 6, or 12 previously confirmed receipt estimates.
- Independent editable monthly occurrences. Correcting a salary after
  confirming it updates only that month. Unconfirmed, unmodified variable
  estimates may be recalculated from confirmed historical receipts; explicitly
  overridden estimates and confirmed amounts are preserved.
- A separate income line in the main spending chart, controlled by an
  optional toggle. Solid line is confirmed income; dashed line is forecast.

Only **confirmed** income contributes to actual totals. Pending income
contributes to forecasts. Neither the income module nor the chart communicates
with banking providers or bank APIs. Internal shared-expense reimbursements
are not automatically treated as external income, to prevent double counting.
The separate **Accounts / Conti** tab displays optional manually tracked
balances without connecting to a real bank. It does not reconcile against
bank statements.

The new `income_categories`, `incomes`, and `income_rules` collections use
the existing Home Assistant `Store` and are included in Billy JSON backups.
Existing bill data remain in their original collections. Recurring income plans
generate occurrences through the current month; forecast aggregations can
predict future months without marking anything received.

## User-defined accounts and internal transfers

Open **Settings / Impostazioni → Accounts / Conti** to create or edit accounts,
assign a payer owner, choose a default account, and delete unused accounts.
Open the main **Accounts / Conti** tab to review balances and make internal
transfers. Create as many accounts as
needed (up to a generous safety limit of 200), such as Checking, Savings,
Cash, Prepaid card, Investment or another custom type. Names, types, balances
and opening dates are configurable. There is no bank login, banking API, or
automatic synchronization.

Each account has its own opening date and balance: the opening amount is the
balance *at the beginning of that day*, and already includes any transactions
before it. Billy does not invent balances for existing installations; no
accounts are created until the user opts in. The first account becomes the
default. Users can change which account is the default for future entries,
but previously recorded transactions retain their original account.

On or after the individual opening date, the balance of each account is:

- **Account balance:** opening balance + confirmed receipts assigned to it −
  paid bills assigned to it + incoming transfers − outgoing transfers.
- **Combined balance:** sum of all account balances. Internal transfers
  cancel and never appear as external income or expenses.

Income entries, including individual recurring salary occurrences, and bill
forms have an optional account selector. If none is configured, the first
created account becomes the default for existing unassigned transactions.
Subsequent changes to the default do **not** retroactively reallocate history.

Click **Record a transfer** to move money between **any two distinct existing
accounts**. A transfer is editable/deletable, uses cents-accurate accounting,
and must be greater than zero. It cannot predate either account's opening date
or be dated in the future. An account cannot be deleted while referenced by a
bill, income, recurring income rule, or transfer. Renaming it does not change
transaction IDs; accounts can have custom names and types.
The transfer history can be filtered by account and by incoming, outgoing or
both directions. Selecting an account's balance card automatically filters to
transfers going out of that account. The **Manage accounts in Settings** button
opens account configuration directly.
Billy blocks moving an opening date forward if this would silently exclude
previously posted income, paid bills, or transfers.

**Example:** With an opening Checking balance of EUR 1,000 and Savings balance
of EUR 500, confirming an income of EUR 2,000, paying an EUR 80 bill, and moving
EUR 250 to Savings produces Checking EUR 2,670, Savings EUR 750, and combined
EUR 3,420. Without the transfer, the combined balance would still be EUR 3,420.

**Deliberate accuracy constraints:**

- Planned income, unpaid bills and unpaid placeholder bills are not posted.
- Recurring schedules do not by themselves count as paid cash movements.
  Only confirmed recurring installment payments, entered with an actual date
  and amount, are subtracted from the debited account. Already-recorded paid
  Bills can be marked as reconciled without posting a duplicate expense.
  Past installments can be confirmed, edited or undone from **Recurring →
  Expenses → Payments**, independently of payer reimbursements.
- Shared-expense reimbursements and payer positions are a different concept
  from account balances and are **not** counted as account income or
  transfers. Assign each actual bill or receipt to the account that handled it.
- Older paid bills lacking an exact payment date fall back to the **first day
  of their recorded payment month**. Prefer exact payment dates, especially
  if the opening snapshot is taken mid-month.
- Negative balances are displayed if the ledger results in a negative amount;
  Billy does not block overdrafts or pretend to enforce bank rules.
- All accounts share Billy's Home Assistant currency; no foreign-exchange
  conversion or live investment valuation is performed.

The `accounts` list, `default_account_id`, per-transaction `account_id`,
and `internal_transfers` list are saved in Billy's existing Home Assistant
Store and included in JSON backups. Older backups without these keys remain
supported. Unreleased two-account `accounts_config` records and historical
`checking`/`savings` transfers are migrated without changing their IDs.

## Limitations and outstanding work

- This is a development preview, not yet an on-device/Home Assistant test.
- Direct SFTP/WebDAV storage adapters and authenticated Paperless API
  integrations require separate implementation.
- Dynamic account balances and internal transfers have been implemented locally,
  but not yet tested in a running Home Assistant instance. Automatic payment
  confirmation for recurring expenses would require additional functionality.
- The new Income tab currently has full English and Italian control labels;
  default category names are translated in all six supported Billy locales.
  Additional locale translations for the Income controls are pending.
