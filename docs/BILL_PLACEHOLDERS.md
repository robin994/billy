# Monthly bill checklist

Implemented for [feature request #10](https://github.com/robin994/billy/issues/10).

## Configure a bill type

Open **Billy → Settings → Bill types**, edit a type and enable **Create an unpaid bill each period**. Existing types have this option disabled by default.

| Setting | Behavior |
| --- | --- |
| Creation day | Day 1–31; default 1. Days beyond the month's end become its last day. |
| Provisional amount | The last actual bill amount, Billy's forecast estimate, or a fixed value. |
| Fixed amount | Used only by fixed mode. Zero is allowed. |
| Due day | Optional day 1–31 in the generated bill's month, with the same month-end clipping. |
| First expected month | Optional scheduling anchor. When empty, inferred from the latest actual bill and the type's cadence; without history, defaults to the current month. |

The type's existing `interval_months` defines the schedule. A two-month type starting in November creates entries in November, January, March and so on. The selected starting month is stored so the schedule remains stable across restarts and missing invoices.

Last-amount mode uses the latest actual invoice, without normalizing its amount. Forecast mode uses the existing estimator, including billing-period normalization and individual bill exclusions. Provisional invoices and future invoices are excluded from both amount lookups. Without eligible history, last/forecast mode creates a zero-amount entry that remains visible on the checklist. The type-level **Exclude from estimates** option does not disable its checklist.

Generated entries inherit the type's provider, contract, consumption unit and default payer, plus Billy's default split. If all payers are disabled but the type still names a valid default payer, that payer receives a 100% provisional split. A type without any configured payer can still create checklist entries.

## Scheduling and duplicate prevention

Billy checks at Home Assistant startup, each local midnight and when bill-type settings are saved. The date comes from Home Assistant's configured time zone. If Home Assistant was offline on the creation day, the next startup creates the current month's entry once that day has passed.

Only the current month is generated. Past missing months are not backfilled. Disabled bill types and disabled checklist options create no new entries; existing entries remain available.

An existing bill of the same type and **billing month** prevents generation, whether paid or unpaid. If the actual invoice arrives later, adding it manually, approving/importing a parser candidate or importing an ordinary CSV row replaces the provisional entry of that type and billing month. Its ID and creation timestamp are preserved, while the amount, billing dates, provider and other invoice fields become the actual values. Further real invoices of the same type/month remain separate, preserving split/tariff-change invoices.

Matching uses the billing month, not the due month. A parser invoice for September due in October updates the September provisional entry, if present; it does not replace October's entry. This follows Billy's existing billing-month import convention.

Deleting an automatically generated entry skips regeneration for that same month, including after a restart or a settings edit. The next scheduled month is unaffected.

## Confirm and pay an entry

Provisional entries have a visible **Provisional bill — confirm amount** label in the Billy panel and the compact bill card. Open the entry, enter the actual amount and save. Saving confirms it even if it remains unpaid. Marking a provisional entry paid opens that form with payment selected and focuses the amount field.

Confirmed entries use normal Billy payment and reimbursement behavior. Unmarking a confirmed invoice as paid does not turn it back into a provisional entry. API clients can confirm an entry by saving it or marking it paid; these paths accept the submitted/current amount.

Before confirmation, the amount is visible in outstanding/checklist totals but does not contribute to paid spending, normalized spending, forecast amount estimation, contract savings or user reimbursements. Provisional billing months can still anchor forecast cadence. Confirmed unpaid invoices retain Billy's existing independent reimbursement behavior.

Backups preserve configuration, entries and the last generated month. CSV export adds the optional `is_placeholder` column, which CSV import preserves for unpaid entries. CSV rows with an existing ID are still skipped, as before; CSV remains an import workflow, rather than an update-by-ID workflow. Complete configuration is transferred through a Billy backup.

## Upcoming widget

The widget includes a selector for all upcoming expenses or the unpaid current-month checklist. Configure its initial view with:

```yaml
type: custom:billy-upcoming-card
title: Bills to pay this month
filter: unpaid_this_month
limit: 20
```

The monthly filter includes unpaid bills whose billing month is current or whose due date is in the current month. It includes overdue due dates, zero amounts and entries without a due date. It excludes forecasts and recurring rules. Its displayed list is limited by `limit`; the backend/sensor list is complete.

The Overview uses the same checklist. Paying an entry removes it from both lists.

## Home Assistant reminders

The existing total-bills sensor exposes:

- `current_month_unpaid_bills`: compact entries with `id`, `category_id`, `category`, `amount`, `due_date`, `is_placeholder`, `year` and `month`;
- `current_month_unpaid_count`: number of these entries;
- `current_month_unpaid_total`: sum of their current amounts.

These attributes refresh when bills change and at local midnight, including a month transition without any newly generated entry. Billy also uses its existing `bill_tracker_updated` event after persisting changes.

Example local reminder; replace `sensor.bill_tracker_total` with the actual entity ID assigned to Billy's total-bills sensor:

The example uses Home Assistant's documented [time triggers](https://www.home-assistant.io/docs/automation/trigger/) and [persistent notification action](https://www.home-assistant.io/integrations/persistent_notification/).

```yaml
alias: Billy unpaid monthly checklist
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: template
    value_template: >-
      {{ state_attr('sensor.bill_tracker_total', 'current_month_unpaid_count') | int(0) > 0 }}
actions:
  - action: persistent_notification.create
    data:
      notification_id: billy_unpaid_bills
      title: Bills to pay this month
      message: >-
        {% set bills = state_attr('sensor.bill_tracker_total', 'current_month_unpaid_bills') or [] %}
        {% for bill in bills %}
        {{ bill.category }}: {{ bill.amount }}{% if bill.due_date %} ({{ bill.due_date }}){% endif %}
        {% endfor %}
```

## Validation

Host tests exercise the complete manager with Home Assistant storage, event delivery and time replaced by test adapters. DOM tests execute the frontend in jsdom. Run them with:

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
npm ci --ignore-scripts
npm test
```

Before release, verify on a running Home Assistant instance: enable a type; inspect its unpaid entry and sensor attributes; confirm the actual amount; add/import a same-month actual invoice; and verify local-midnight updates and the Upcoming filter in a real browser. Host and DOM tests do not establish live Home Assistant installation or browser rendering.
