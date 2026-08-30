"""Constants for Bill Tracker."""

DOMAIN = "bill_tracker"
PROJECT_URL = "https://github.com/robin994/billy"
PARSER_PROJECT_URL = "https://github.com/robin994/billy-parser"
SUPPORT_URL = "https://paypal.me/rtortora94"
STORAGE_VERSION = 1
STORAGE_SCHEMA_VERSION = 14
STORAGE_KEY = "bill_tracker.expenses"
EVENT_UPDATED = "bill_tracker_updated"
FRONTEND_VERSION = "0.11.10"
FRONTEND_CACHE_VERSION = "0.11.10-r2"

SUPPORTED_INTERVALS = (1, 2, 3, 4, 6, 12)

RECURRING_KINDS = ("subscription", "mortgage", "installment", "recurring")
RECURRING_INTERVALS = (1, 2, 3, 4, 6, 12)
INTERVAL_LABELS = {
    1: "Mensile",
    2: "Bimestrale",
    3: "Trimestrale",
    4: "Quadrimestrale",
    6: "Semestrale",
    12: "Annuale",
}

DEFAULT_CATEGORIES = [
    {
        "id": "internet",
        "name": "Internet",
        "interval_months": 1,
        "enabled": True,
        "color": "#5B8FF9",
        "consumption_unit": "",
    },
    {
        "id": "electricity",
        "name": "Elettricità",
        "interval_months": 1,
        "enabled": True,
        "color": "#F6BD16",
        "consumption_unit": "kWh",
    },
    {
        "id": "water",
        "name": "Acqua",
        "interval_months": 2,
        "enabled": True,
        "color": "#5AD8A6",
        "consumption_unit": "m³",
    },
    {
        "id": "gas",
        "name": "Gas",
        "interval_months": 2,
        "enabled": True,
        "color": "#E8684A",
        "consumption_unit": "m³",
    },
    {
        "id": "condominium",
        "name": "Condominio",
        "interval_months": 1,
        "enabled": True,
        "color": "#9270CA",
        "consumption_unit": "",
    },
    {
        "id": "phone",
        "name": "Telefono",
        "interval_months": 1,
        "enabled": True,
        "color": "#6DC8EC",
        "consumption_unit": "",
    },
    {
        "id": "tari",
        "name": "TARI / Rifiuti",
        "interval_months": 12,
        "enabled": True,
        "color": "#FF9D4D",
        "consumption_unit": "",
    },
    {
        "id": "other",
        "name": "Altro",
        "interval_months": 1,
        "enabled": True,
        "color": "#A0A7B4",
        "consumption_unit": "",
    },
]

FALLBACK_COLORS = (
    "#5B8FF9",
    "#5AD8A6",
    "#5D7092",
    "#F6BD16",
    "#E8684A",
    "#6DC8EC",
    "#9270CA",
    "#FF9D4D",
    "#269A99",
    "#FF99C3",
)
