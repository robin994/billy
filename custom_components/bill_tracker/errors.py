"""User-facing errors for Billy.

Billy's business logic raises :class:`BillyError`, a ``ValueError`` subclass that
carries a stable ``code``. The websocket API forwards that code to the frontend
together with an English fallback message (``str(err)``); the panel then shows a
message in the user's language, falling back to the English text when it has no
translation for the code.

Home Assistant config/options flows keep working unchanged because they catch
``ValueError`` and map it to their own ``strings.json`` keys.
"""
from __future__ import annotations


class BillyError(ValueError):
    """A validation or business-rule error meant to be shown to the user."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# Stable code -> English fallback message. Placeholders use ``str.format`` syntax.
ERROR_MESSAGES: dict[str, str] = {
    # Payers
    "payer_name_exists": "A payer with this name already exists.",
    "payer_in_history": "This payer appears in the bill history. Disable it instead of deleting it.",
    "payer_in_recurring": "This payer is used by a recurring expense. Disable it instead of deleting it.",
    "payer_in_recurring_history": "This payer appears in the recurring expense history. Disable it instead of deleting it.",
    "payer_is_default": "This payer is set as the default payer of a bill type.",
    "payer_in_settlements": "This payer appears in the settlement history. Disable it instead of deleting it.",
    "payer_not_found": "Payer not found.",
    "payer_invalid": "Invalid payer.",
    "default_payer_invalid": "Invalid default payer.",
    # Bill types
    "category_name_exists": "A bill type with this name already exists.",
    "category_has_history": "This bill type has history. Disable it instead of deleting it.",
    "category_not_found": "Bill type not found.",
    "category_invalid": "Invalid bill type.",
    # Billing period
    "period_start_after_end": "The billing period start is after its end.",
    "period_too_long": "The billing period is too long.",
    # Reimbursements / settlements
    "expense_no_reimbursement": "This bill does not involve reimbursements between users.",
    "expense_settlement_linked": "This bill is linked to a recorded settlement: manage it from the settlement history.",
    "recurring_in_settlements": "This recurring expense appears in the settlement history. Disable it instead of deleting it.",
    "recurring_no_reimbursement": "This recurring expense does not involve reimbursements between users.",
    "recurring_settlement_linked": "This recurring charge is linked to a recorded settlement: manage it from the settlement history.",
    "settlement_invalid_payers": "Invalid payers.",
    "settlement_none_open": "There is no open settlement between these payers.",
    "settlement_partial_unsupported": "For now Billy can only record the full open settlement.",
    "settlement_no_expense": "No expense is linked to this settlement.",
    # Recurring expenses
    "recurring_name_required": "The recurring expense name is required.",
    "recurring_invalid_kind": "Invalid recurring expense type.",
    "recurring_amount_positive": "The recurring expense amount must be greater than zero.",
    "recurring_unsupported_interval": "Unsupported recurring expense frequency.",
    "recurring_start_required": "The activation date is required.",
    "recurring_end_before_start": "The end date cannot be earlier than the activation date.",
    "recurring_invalid_renewal": "Invalid renewal interval.",
    "recurring_invalid_installments": "Invalid number of installments.",
    "recurring_not_found": "Recurring expense not found.",
    "occurrence_not_found": "Recurring charge not found.",
    # Expense split
    "split_invalid_payer": "The split contains an invalid payer.",
    "split_invalid_percentage": "Invalid split percentage.",
    "split_empty": "The expense split is empty.",
    "split_must_total_100": "The expense split must add up to 100%.",
    # Generic field validation
    "name_required": "Name is required.",
    "name_too_long": "Name is too long.",
    "share_invalid": "Invalid default share.",
    "interval_unsupported": "Unsupported frequency.",
    "amount_invalid": "Invalid amount.",
    "amount_missing": "Missing amount.",
    "consumption_invalid": "Invalid consumption.",
    "date_invalid": "Invalid date.",
    "year_invalid": "Invalid year.",
    "month_invalid": "Invalid month.",
    "expense_not_found": "Expense not found.",
    # CSV import
    "csv_empty": "The CSV is empty.",
    "csv_no_headers": "The CSV has no header row.",
    "csv_missing_columns": "The CSV must contain at least the category and amount columns.",
    "csv_missing_period_columns": "The CSV must contain billing_month (YYYY-MM) or year + month.",
    "csv_no_rows": "The CSV has no rows to import.",
    "csv_too_many_rows": "The CSV contains more than 5000 rows.",
    "csv_missing_category": "Missing bill type.",
    "csv_unknown_category": "Unknown bill type: {name}",
    "csv_unsupported_interval": "Unsupported frequency for {name}: {interval} months",
    "csv_unknown_payer": "Unknown payer: {name}",
    "csv_invalid_share": "Invalid share: {token}",
    "csv_currency_mismatch": "Currency {incoming} differs from the Home Assistant currency {current}.",
    "csv_invalid_paid": "Invalid paid value: {value}",
    "csv_invalid_month": "Invalid month: {text}. Use YYYY-MM",
    # Export
    "export_format_unsupported": "Unsupported export format.",
    # Backup
    "backup_invalid_json": "Invalid backup JSON.",
    "backup_not_billy": "This file is not a Billy backup.",
    "backup_unsupported_version": "Unsupported Billy backup version.",
    "backup_no_data": "The Billy backup contains no valid data.",
    "backup_invalid_section": "Invalid backup section: {key}",
    "backup_too_many_bills": "The backup contains too many bills.",
    "backup_too_many_recurring": "The backup contains too many recurring expenses.",
}


def billy_error(code: str, **params: object) -> BillyError:
    """Build a :class:`BillyError` from a code and optional message placeholders."""
    template = ERROR_MESSAGES.get(code, code)
    message = template.format(**params) if params else template
    return BillyError(code, message)
