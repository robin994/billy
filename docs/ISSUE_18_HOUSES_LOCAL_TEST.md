# Billy - Houses / Case (issue #18): local smoke-test checklist

This change is **unreleased** and is present only in the working tree with
the uncommitted issue #17 historical recurring-payment changes. The manifest
remains at `0.16.0`. The frontend cache key is `0.16.0-r4`.

## Install locally for testing

1. Back up the Home Assistant config directory and export a Billy JSON backup.
2. Copy the working tree's `custom_components/bill_tracker/` over the test
   installation at `config/custom_components/bill_tracker/`.
3. Restart Home Assistant and hard-refresh the browser/companion app. HACS or
   the GitHub updater will not supply this code until a release is published.
4. Navigate to `/billy?view=settings&section=houses`.

## House administration

- Existing installs create exactly one default House named **Home**. Existing
  bills and recurring rules retain their amounts, payment status and history.
- Add **House X** and **House Y** from **Settings → Houses / Case**.
- Rename a house, set a different default house, and ensure the changes
  persist after restarting Home Assistant.
- A house linked to an existing bill/recurring expense cannot be deleted,
  nor can the default house be removed before selecting another default.

## Bills and recurring expenses

- Open **Bills**, filter the history by House X, House Y or **All houses**.
- Create a bill while House Y is selected. Check the new bill defaults to Y.
- Reassign that bill to House X using **Edit**. Confirm both histories update
  and the total for All houses remains unchanged.
- Check that **Edit** and **Delete** buttons never overlap or truncate, at
  desktop, tablet and mobile widths. In Recurring, all five filters must
  occupy balanced columns and wrap sensibly as the window narrows.
- Assign a mortgage/subscription in **Recurring → Expenses** to House X and
  verify its forecast only contributes to X.
- New automatically generated unpaid bill placeholders currently belong to
  the configured default house; change the house in the bill editor when needed.

## Dashboard / Overview

- **All houses** shows the original combined actual spending and forecasts.
- **House X** shows only X's paid bills, recurring payments and future charges.
  **House Y** shows only Y's corresponding totals, history and forecasts.
- Switching X → Y → All must never mutate data. Common bank accounts and
  income are **not assigned to a house**; house-scoped income is not shown
  rather than allocating one income to every house.
- Revisit previously populated views to ensure the last selection does not
  generate stale data or count expenses twice.

## Reimbursement history

- Open **Reimbursement history / Storico rimborsi** and select House X,
  House Y or **All houses**. Existing status, payer and year filters still work.
- Verify that the completed count, total reimbursed and total pending
  correspond to the selected house, including manually marked bills and
  reimbursed recurring charges.
- Check a combined reimbursement containing an invoice from each house:
  each house shows only its own line items and amount. The complete transfer
  remains visible under **All houses**.
- A combined reimbursement cannot be undone from an individual house view,
  since undo would cancel the entire transfer. Go to **All houses** to undo.
- Older combined reimbursements without itemized amounts display an
  unavailable amount and a warning; Billy must not invent a proportional
  split or include an unknown amount in the monetary total.
- Move an already reimbursed bill to another house: the itemized historical
  reimbursement keeps its original house association.

## Compatibility and isolation limits

- Confirm issue #17 installment payments still work, with correct bank account
  ledger totals and no double counting.
- Test JSON backup/export, restoration and an older backup with no Houses.
- A House is a **filtering/grouping dimension in a single shared workspace**.
  It is **not a separate integration instance, a per-person access-control
  system, a separate database, or legal segregation**. Do not represent this
  feature as satisfying guardianship/privacy requirements.

## Automated verification

~~~sh
npm test
python3 -m pytest -q
~~~

The Python suite requires development dependencies such as `voluptuous`.

No commit, push or release should be made before the user completes their
Home Assistant UI test.
