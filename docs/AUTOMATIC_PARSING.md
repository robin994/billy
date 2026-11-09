# Automatic bill parsing — Billy 0.6.0

Billy 0.6.0 adds a separate parsing subsystem. The existing `BillTrackerManager`
continues to own expenses; parsers only produce reviewed `BillCandidate` data.

## Data flow

```text
Home Assistant IMAP event
  -> selected IMAP source check
  -> parser metadata prefilter (sender / subject)
  -> fetch matching message body
  -> weighted parser detection
  -> fetch only the attachment required by the winning parser
  -> PDF/text normalization
  -> declarative parser engine
  -> email/PDF verification
  -> deduplication
  -> review queue OR verified auto-import
  -> BillTrackerManager
```

## Privacy model

Billy does **not** fetch every email body and then search it for invoices.

1. Home Assistant's IMAP integration observes the mailbox/folder/search that the
   user configured in Home Assistant.
2. Billy listens only to IMAP config entries explicitly selected in Billy.
3. For each event Billy initially uses the metadata already present in the
   `imap_content` event: sender, subject, UID and MIME-part metadata.
4. Installed parsers have a `prefilter` section. If no parser passes that
   metadata prefilter, Billy does not call `imap.fetch`.
5. Only after a prefilter match is the email body fetched locally.
6. A PDF/part is fetched only when the selected parser asks for that part.
7. Raw email bodies and PDF bytes are not stored by Billy. The persistent import
   record contains normalized bill fields plus limited source metadata used for
   deduplication and troubleshooting.
8. Email/PDF content is not sent to `billy-parser` or any AI/cloud parsing API.

For maximum isolation, configure a dedicated IMAP folder/search for utility
providers before selecting that IMAP entry in Billy.

## Setup

1. Add Home Assistant's **IMAP** integration for the mailbox/folder you want Billy
   to observe.
2. Open Billy integration options -> **Automatic bill parsing** -> **Email sources**
   and select the permitted IMAP entry or entries.
3. Open **Parser catalog**. Billy downloads `parser.json` from `billy-parser`.
4. Select a parser and map it to one of your existing Billy bill types.
5. Keep **Automatically import verified bills** disabled for the first bills.
6. New candidates appear under **Bills waiting for review**.
7. Once a parser is proven reliable you can enable automatic import for it.

## Autopay and scheduled direct debits

In an installed or custom parser's configuration, enable **Autopay** to mark
imported bills as paid automatically. An optional second flag, **Pay
automatically on the due date**, defers payment until the parsed due date.

- Before that date, the imported bill appears as **Scheduled payment** in
  Bills, not as an overdue/unpaid action; future scheduled bills can still
  appear in Upcoming.
- On the due date, the regular midnight synchronization records the payment.
  If Home Assistant is offline at midnight, the payment is caught up during
  the next integration startup, preserving the original due date as the
  payment date. The operation is idempotent.
- If the parser provides no due date, Billy leaves the imported bill unpaid
  for manual review rather than inventing a payment date.
- **Autopay from joint account** also completes eligible reimbursements, but
  only when the scheduled bill is actually marked paid.
- If a parsed invoice already contains an explicit payment date, Billy honors
  that date as an existing payment rather than scheduling a second payment.

All flags are off by default and apply only to new imports. Existing scheduled
bills remain scheduled if you later change the parser configuration; manually
changing a bill's payment status cancels its remaining schedule.

## Parser storage

Parser files intentionally live outside the HACS integration directory so HACS
updates do not delete them:

```text
/config/billy/parsers/
  official/
  custom/
```

Parser configuration, source selection and import history use a separate Home
Assistant Store key: `bill_tracker.parsers`.

## Catalog integrity

The catalog entry contains a parser path, version, byte size and SHA-256 checksum.
Billy downloads the parser from the catalog's immutable `source_commit` whenever
possible and validates all of those fields before saving the parser.

## Parser security

Schema v1 is declarative. Community/custom parser files cannot execute Python,
JavaScript, shell commands, Jinja, filesystem operations or arbitrary HTTP
requests. Supported v1 operations are bounded matching/extraction plus text,
decimal, date and date-range transforms.

## Automatic import safety

A parser can opt into automatic import only through local Billy configuration.
Even then Billy keeps a candidate in the review queue when email/PDF verification
reports a conflict or when confidence is below the auto-import threshold.

## E.ON reference parser

The first `billy-parser` fixture is `it.eon.electricity`. It was validated against
an actual E.ON email + digitally generated PDF pair. It extracts invoice number,
issue date, amount due, billing period, due/debit date, consumption, customer code,
POD, offer and payment method. The repository fixture itself is synthetic and
contains no customer data.

## 0.6.0 limitations

- Digitally generated PDFs with an extractable text layer only; no OCR yet.
- IMAP is the first mail source. The source abstraction is intentionally separate
  so Gmail API / Outlook OAuth adapters can be added later.
- Billy does not rewrite an IMAP integration's server-side search automatically.
  The user controls that scope in Home Assistant; Billy adds its own metadata
  prefilter before fetching content.
- Existing emails are handled when Home Assistant emits an `imap_content` event;
  0.6.0 does not implement a general mailbox-history crawler.

## Parser management UI (0.6.5+)

Billy exposes a dedicated parser-management page at `/billy-parser`. The page is linked from the integration options under **Automatic parsing → Parser management** and is intentionally hidden from the Home Assistant sidebar.

The page supports search, country/status filters and sorting. Installed parser versions are compared with the refreshed remote catalog. When `catalog.version > installed_version`, Billy marks the parser **Outdated** and shows an explicit **Update** action. Refreshing the catalog never updates installed parser YAML automatically.

Additional states are surfaced when relevant: incompatible with the current Billy version, deprecated, load error, custom parser, and installed parser removed from the remote catalog. Catalog entries may optionally provide `deprecated`, `replacement` and `changelog` metadata; these fields do not change parser schema v1.
