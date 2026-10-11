# Regression tests

Run the Python suite from the repository root with Python 3.12 or newer:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q tests
```

Run the frontend behavior tests with Node.js 22:

```sh
npm ci --ignore-scripts
npm test
```

The frontend tests execute the actual parser-manager component in jsdom, with
WebSocket responses supplied by the test fixture. They cover new and existing
parser drafts, unrelated Home Assistant state updates, focus and selection,
necessary rerenders, validation results, save errors, reconnects, and responses
that arrive after an editor has been closed or replaced.

The parser API tests compile the command schemas declared in `parser_api.py`
with Voluptuous and execute the save handler and the manager's identity check.
They verify that edits accept and forward `expected_parser_id`, creations do
not require it, unknown fields and invalid types are rejected, and renaming
an existing parser cannot write a replacement file.

These tests do not start Home Assistant or exercise a browser connected to a
live Home Assistant instance. Both suites run in the Regression tests workflow.
