"""Small runtime localization helpers used outside Home Assistant translation files.

Home Assistant handles config/options form labels through strings.json and the
translations directory. Billy also has a few values that are built dynamically
(select option labels and generated XLSX/PDF reports); those values need a
runtime language table because they are not static HA translation keys.
"""
from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES = {"en", "it", "es", "fr", "de", "pt"}


def normalize_language(value: Any) -> str:
    """Normalize a HA/browser style locale to one of Billy's languages."""
    raw = str(value or "en").strip().lower().replace("_", "-")
    language = raw.split("-", 1)[0]
    return language if language in SUPPORTED_LANGUAGES else "en"


CONFIG_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "none": "None", "edit": "Edit", "delete": "Delete", "share": "share", "disabled": "disabled",
        "interval_1": "Monthly", "interval_2": "Every 2 months", "interval_3": "Quarterly",
        "interval_4": "Every 4 months", "interval_6": "Half-yearly", "interval_12": "Yearly",
    },
    "it": {
        "none": "Nessuno", "edit": "Modifica", "delete": "Elimina", "share": "quota", "disabled": "disattivato",
        "interval_1": "Mensile", "interval_2": "Bimestrale", "interval_3": "Trimestrale",
        "interval_4": "Quadrimestrale", "interval_6": "Semestrale", "interval_12": "Annuale",
    },
    "es": {
        "none": "Ninguno", "edit": "Editar", "delete": "Eliminar", "share": "cuota", "disabled": "desactivado",
        "interval_1": "Mensual", "interval_2": "Cada 2 meses", "interval_3": "Trimestral",
        "interval_4": "Cada 4 meses", "interval_6": "Semestral", "interval_12": "Anual",
    },
    "fr": {
        "none": "Aucun", "edit": "Modifier", "delete": "Supprimer", "share": "part", "disabled": "désactivé",
        "interval_1": "Mensuelle", "interval_2": "Tous les 2 mois", "interval_3": "Trimestrielle",
        "interval_4": "Tous les 4 mois", "interval_6": "Semestrielle", "interval_12": "Annuelle",
    },
    "de": {
        "none": "Keiner", "edit": "Bearbeiten", "delete": "Löschen", "share": "Anteil", "disabled": "deaktiviert",
        "interval_1": "Monatlich", "interval_2": "Alle 2 Monate", "interval_3": "Vierteljährlich",
        "interval_4": "Alle 4 Monate", "interval_6": "Halbjährlich", "interval_12": "Jährlich",
    },
    "pt": {
        "none": "Nenhum", "edit": "Editar", "delete": "Eliminar", "share": "quota", "disabled": "desativado",
        "interval_1": "Mensal", "interval_2": "A cada 2 meses", "interval_3": "Trimestral",
        "interval_4": "A cada 4 meses", "interval_6": "Semestral", "interval_12": "Anual",
    },
}

CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "en": {"internet": "Internet", "electricity": "Electricity", "water": "Water", "gas": "Gas", "condominium": "Condominium", "phone": "Phone", "tari": "Waste / tax", "other": "Other"},
    "it": {"internet": "Internet", "electricity": "Elettricità", "water": "Acqua", "gas": "Gas", "condominium": "Condominio", "phone": "Telefono", "tari": "TARI / Rifiuti", "other": "Altro"},
    "es": {"internet": "Internet", "electricity": "Electricidad", "water": "Agua", "gas": "Gas", "condominium": "Comunidad", "phone": "Teléfono", "tari": "Residuos / impuestos", "other": "Otro"},
    "fr": {"internet": "Internet", "electricity": "Électricité", "water": "Eau", "gas": "Gaz", "condominium": "Copropriété", "phone": "Téléphone", "tari": "Déchets / taxe", "other": "Autre"},
    "de": {"internet": "Internet", "electricity": "Strom", "water": "Wasser", "gas": "Gas", "condominium": "Hausverwaltung", "phone": "Telefon", "tari": "Abfall / Steuer", "other": "Sonstiges"},
    "pt": {"internet": "Internet", "electricity": "Eletricidade", "water": "Água", "gas": "Gás", "condominium": "Condomínio", "phone": "Telefone", "tari": "Resíduos / imposto", "other": "Outro"},
}

REPORT_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "report_title": "Billy - Bill report", "period": "Period", "generated": "Generated", "no_data": "No data in the selected period",
        "bills": "Bills", "total": "Total", "paid": "Paid", "unpaid": "Unpaid",
        "payments_trend": "Payment trend", "normalized_cost": "Normalized monthly cost",
        "totals_by_type": "Totals by type", "report_note": "The report filters by billing month. Normalized cost distributes each amount across its competence period.",
        "bill_details": "Bill details", "month": "Month", "type": "Type", "amount": "Amount", "status": "Status",
        "due_date": "Due date", "payment_date": "Payment", "provider": "Provider", "contract": "Contract",
        "consumption": "Consumption", "note": "Note", "sheet_bills": "Bills", "sheet_summary": "Monthly summary",
        "interval_months": "Interval (months)", "currency": "Currency", "unit": "Unit", "billing_month": "Billing month",
        "period_start": "Period start", "period_end": "Period end", "payer": "Payer", "split": "Split", "id": "ID",
        "paid_total": "Paid total", "bills_count": "Bills",
    },
    "it": {
        "report_title": "Billy - Report bollette", "period": "Periodo", "generated": "Generato", "no_data": "Nessun dato nel periodo selezionato",
        "bills": "Bollette", "total": "Totale", "paid": "Pagate", "unpaid": "Da pagare",
        "payments_trend": "Andamento pagamenti", "normalized_cost": "Costo mensile normalizzato",
        "totals_by_type": "Totali per tipo", "report_note": "Il report usa il mese bolletta per il filtro temporale. Il costo normalizzato distribuisce l'importo sul periodo di competenza.",
        "bill_details": "Dettaglio bollette", "month": "Mese", "type": "Tipo", "amount": "Importo", "status": "Stato",
        "due_date": "Scadenza", "payment_date": "Pagamento", "provider": "Fornitore", "contract": "Contratto",
        "consumption": "Consumo", "note": "Nota", "sheet_bills": "Bollette", "sheet_summary": "Riepilogo mensile",
        "interval_months": "Periodicità (mesi)", "currency": "Valuta", "unit": "Unità", "billing_month": "Mese bolletta",
        "period_start": "Inizio periodo", "period_end": "Fine periodo", "payer": "Pagatore", "split": "Divisione", "id": "ID",
        "paid_total": "Totale pagato", "bills_count": "Bollette",
    },
    "es": {
        "report_title": "Billy - Informe de facturas", "period": "Periodo", "generated": "Generado", "no_data": "No hay datos en el periodo seleccionado",
        "bills": "Facturas", "total": "Total", "paid": "Pagadas", "unpaid": "Por pagar",
        "payments_trend": "Evolución de pagos", "normalized_cost": "Coste mensual normalizado",
        "totals_by_type": "Totales por tipo", "report_note": "El informe filtra por mes de facturación. El coste normalizado distribuye cada importe entre su periodo de competencia.",
        "bill_details": "Detalle de facturas", "month": "Mes", "type": "Tipo", "amount": "Importe", "status": "Estado",
        "due_date": "Vencimiento", "payment_date": "Pago", "provider": "Proveedor", "contract": "Contrato",
        "consumption": "Consumo", "note": "Nota", "sheet_bills": "Facturas", "sheet_summary": "Resumen mensual",
        "interval_months": "Periodicidad (meses)", "currency": "Moneda", "unit": "Unidad", "billing_month": "Mes de facturación",
        "period_start": "Inicio del periodo", "period_end": "Fin del periodo", "payer": "Pagador", "split": "División", "id": "ID",
        "paid_total": "Total pagado", "bills_count": "Facturas",
    },
    "fr": {
        "report_title": "Billy - Rapport des factures", "period": "Période", "generated": "Généré", "no_data": "Aucune donnée sur la période sélectionnée",
        "bills": "Factures", "total": "Total", "paid": "Payées", "unpaid": "À payer",
        "payments_trend": "Évolution des paiements", "normalized_cost": "Coût mensuel normalisé",
        "totals_by_type": "Totaux par type", "report_note": "Le rapport filtre sur le mois de facturation. Le coût normalisé répartit chaque montant sur sa période de compétence.",
        "bill_details": "Détail des factures", "month": "Mois", "type": "Type", "amount": "Montant", "status": "Statut",
        "due_date": "Échéance", "payment_date": "Paiement", "provider": "Fournisseur", "contract": "Contrat",
        "consumption": "Consommation", "note": "Note", "sheet_bills": "Factures", "sheet_summary": "Résumé mensuel",
        "interval_months": "Périodicité (mois)", "currency": "Devise", "unit": "Unité", "billing_month": "Mois de facturation",
        "period_start": "Début de période", "period_end": "Fin de période", "payer": "Payeur", "split": "Partage", "id": "ID",
        "paid_total": "Total payé", "bills_count": "Factures",
    },
    "de": {
        "report_title": "Billy - Rechnungsbericht", "period": "Zeitraum", "generated": "Erstellt", "no_data": "Keine Daten im ausgewählten Zeitraum",
        "bills": "Rechnungen", "total": "Gesamt", "paid": "Bezahlt", "unpaid": "Offen",
        "payments_trend": "Zahlungsverlauf", "normalized_cost": "Normalisierte Monatskosten",
        "totals_by_type": "Summen nach Typ", "report_note": "Der Bericht filtert nach Rechnungsmonat. Normalisierte Kosten verteilen jeden Betrag auf seinen Leistungszeitraum.",
        "bill_details": "Rechnungsdetails", "month": "Monat", "type": "Typ", "amount": "Betrag", "status": "Status",
        "due_date": "Fälligkeit", "payment_date": "Zahlung", "provider": "Anbieter", "contract": "Vertrag",
        "consumption": "Verbrauch", "note": "Notiz", "sheet_bills": "Rechnungen", "sheet_summary": "Monatsübersicht",
        "interval_months": "Intervall (Monate)", "currency": "Währung", "unit": "Einheit", "billing_month": "Rechnungsmonat",
        "period_start": "Zeitraum Beginn", "period_end": "Zeitraum Ende", "payer": "Zahler", "split": "Aufteilung", "id": "ID",
        "paid_total": "Bezahlt gesamt", "bills_count": "Rechnungen",
    },
    "pt": {
        "report_title": "Billy - Relatório de contas", "period": "Período", "generated": "Gerado", "no_data": "Sem dados no período selecionado",
        "bills": "Contas", "total": "Total", "paid": "Pagas", "unpaid": "Por pagar",
        "payments_trend": "Evolução dos pagamentos", "normalized_cost": "Custo mensal normalizado",
        "totals_by_type": "Totais por tipo", "report_note": "O relatório filtra pelo mês da conta. O custo normalizado distribui cada valor pelo respetivo período de competência.",
        "bill_details": "Detalhe das contas", "month": "Mês", "type": "Tipo", "amount": "Valor", "status": "Estado",
        "due_date": "Vencimento", "payment_date": "Pagamento", "provider": "Fornecedor", "contract": "Contrato",
        "consumption": "Consumo", "note": "Nota", "sheet_bills": "Contas", "sheet_summary": "Resumo mensal",
        "interval_months": "Periodicidade (meses)", "currency": "Moeda", "unit": "Unidade", "billing_month": "Mês da conta",
        "period_start": "Início do período", "period_end": "Fim do período", "payer": "Pagador", "split": "Divisão", "id": "ID",
        "paid_total": "Total pago", "bills_count": "Contas",
    },
}


def config_label(language: Any, key: str) -> str:
    lang = normalize_language(language)
    return CONFIG_LABELS.get(lang, CONFIG_LABELS["en"]).get(key, CONFIG_LABELS["en"].get(key, key))


def interval_label(language: Any, months: int) -> str:
    return config_label(language, f"interval_{int(months)}")


def category_label(language: Any, category: dict[str, Any] | None, fallback: str = "") -> str:
    if not category:
        return fallback
    lang = normalize_language(language)
    category_id = str(category.get("id", ""))
    stored_name = str(category.get("name") or "").strip()
    localized_names = {
        labels[category_id]
        for labels in CATEGORY_LABELS.values()
        if category_id in labels
    }
    if stored_name and stored_name not in localized_names:
        return stored_name
    return CATEGORY_LABELS.get(lang, CATEGORY_LABELS["en"]).get(
        category_id, stored_name or fallback or category_id
    )


def report_labels(language: Any) -> dict[str, str]:
    lang = normalize_language(language)
    return REPORT_LABELS.get(lang, REPORT_LABELS["en"])
