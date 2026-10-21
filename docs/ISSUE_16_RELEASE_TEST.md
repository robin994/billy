# Billy 0.16.0 - issue #16 upgrade smoke test

These navigation and account-management changes ship with the `v0.16.0`
release. The frontend resource cache key is `0.16.0-r1`.

## How to test in Home Assistant

1. Make a backup of your Billy data and Home Assistant configuration.
2. Upgrade Billy to `0.16.0` from your configured HACS custom repository or
   Billy's built-in updater. For a manual installation, copy
   `custom_components/bill_tracker/` into
   `config/custom_components/bill_tracker/`.
3. Restart Home Assistant and fully reload the browser or mobile companion
   app so it fetches the `0.16.0-r1` frontend resources.
4. Run the checks below with existing test data.

### Functional checks

- **Accounts / Conti** appears as a top-level tab. It shows balances,
  individual account cards, the combined balance and internal transfers,
  but has no Add/Edit/Delete account controls.
- **Manage accounts in Settings** navigates to **Settings / Impostazioni →
  Accounts / Conti**, where you can add, edit, delete and set the default
  account. A payer must exist before creating a new account.
- The **Record a transfer** primary button on Accounts can transfer an
  amount between two distinct accounts without changing the combined balance.
  Existing transfer Edit/Delete operations remain available.
- Clicking an account card filters to transfers **outgoing** from that
  account. The Account and Direction controls can show all/incoming/outgoing;
  they must not alter saved data.
- **Recurring / Ricorrenti → Expenses / Spese** still manages subscriptions,
  loans and recurring charges. **Recurring → Income / Entrate** now manages
  recurring income plans (edit/add/delete, estimated amount methods).
- **Income / Entrate** shows actual and expected income entries. The former
  Accounts and Recurring plans subtabs are no longer present there.

### Direct links

- `/billy?view=accounts`
- `/billy?view=settings&section=accounts`
- `/billy?view=recurring&tab=income`
- `/billy?view=recurring` (defaults to recurring expenses)

### Test commands

From the repository root:

~~~sh
npm test
python3 -m pytest -q
~~~

The Python suite requires the development dependencies, including
`voluptuous`. The JavaScript suite uses the packages defined in `package.json`.

## Scope

No database schema, WebSocket command type or accounting calculation changed.
This is an interface/navigation change only. Real Home Assistant desktop and
mobile testing is still recommended to catch WebView-specific regressions.
