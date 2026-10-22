# Billy issue #17 - local installment-payment tests

This is an **unreleased local change** on the 0.16.0 source tree. The manifest
remains `0.16.0`; the frontend cache key was changed to `0.16.0-r4`. Do not
use HACS or the Billy updater to obtain these changes: those currently serve
the released version, which does not include this feature.

## Install into a test Home Assistant

1. Back up Billy's data and the Home Assistant configuration, especially if
   you previously used negative-opening-balance accounts or fake transfers.
2. Copy the entire local `custom_components/bill_tracker/` directory into
   the test Home Assistant `config/custom_components/bill_tracker/`.
3. Restart Home Assistant, then hard-reload the browser or restart the
   companion app to force the `0.16.0-r4` JavaScript resources.
4. Open **Recurring > Expenses**, then choose **Payments** on a mortgage
   or other recurring rule. Also test `/billy?view=recurring`.

## Expected behavior

- Historical scheduled due dates appear individually as **Not confirmed**;
  future due dates must not offer a Record payment action.
- On a past due date, choose **Record payment**, enter the **actual payment
  date** and **actual amount**, choose the **debited account**, and save.
  This changes the actual cash outflow *in the month paid*, not necessarily
  the month when the installment was scheduled.
- **Edit payment** corrects the same occurrence without adding another row.
  **Undo payment** deletes that recorded payment and restores the account
  balance accordingly.
- Payments are independent of reimbursements among household members.
- Recurring schedules and future forecasts continue to show planned charges,
  but historical spending charts and the Spending widget only count
  confirmed recurring payments.
- If that installment was **already included as a paid Bill in Billy**, use
  the reconciliation checkbox. It marks the installment paid but does not
  post a duplicate expense or debit the account again.
- The history modal paginates long schedules (12 installments per page).
- Deleting an account referenced by a recorded payment and changing the
  recurring rule's due dates to orphan a recorded payment must be blocked.
- New payments must survive restarting Home Assistant, and be included in
  the JSON backup/restore workflow.

## Philippe's mortgage data

The text in issue #17 states the mortgage began on 02/01/2026, while the
attached exported rule has `start_date = 2026-02-02`. Resolve this date
difference with the user before entering January installments. Do not
silently change their rule.

The mortgage principal/debt balance is not automatically amortized: a payment
is an expense from a cash account, not a transfer into another cash account.
Previously created transfers and negative-balance workaround accounts are
**never automatically changed**. After recording and reconciling payments,
manually remove fictitious transfers or revise account opening snapshots only
after comparing the ledger with actual statements and saving a backup.

## Local verification

~~~sh
npm test
python3 -m pytest -q
~~~

Do not tag, commit, or publish this version until the actual Home Assistant
test has confirmed the UI and account reconciliation behavior.
