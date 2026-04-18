# 0008 - WeasyPrint for PDF, with graceful fallback

- Status: Accepted
- Date: 2026-04-17
- Deciders: @pca-team
- Tags: reporting, wave-2

## Context

The MVP shipped HTML + JSON reports. Users want a single-file PDF they can
attach to support tickets or share. Rendering a PDF from the existing Jinja
templates keeps the single source of truth - we don't want to maintain
ReportLab-style imperative PDF code in parallel.

## Decision

Use **WeasyPrint** to render the existing HTML template to PDF. WeasyPrint is
an optional dependency (the `reporting` extra) because its native GTK / Pango
/ Cairo dependencies are heavy on Windows and require extra apt packages on
Linux. When WeasyPrint fails to import we degrade silently - the CLI still
writes HTML + JSON and the ``Report.pdf_path`` field is ``None``.

Golden-file testing avoids byte-level PDF comparison (font subsetting makes
bytes non-deterministic). We assert (a) magic bytes, (b) positive page count,
and defer pixel-diff to v1.x via ``pypdfium2``.

## Consequences

Positive:

- Single HTML template drives HTML, in-app preview, and PDF outputs.
- CI runs the full PDF smoke test only on Linux, where the native stack
  installs cheaply via apt.
- Missing WeasyPrint never blocks the CLI.

Negative:

- Windows users need MSYS2 or a prebuilt wheel to produce PDFs locally.
- Emoji rendering depends on host fonts; we pin DejaVu in CI.

## Alternatives considered

- **ReportLab**: imperative API; we'd maintain a second template DSL.
- **Puppeteer / playwright**: spawns a Chromium process; too much weight.
- **wkhtmltopdf**: unmaintained upstream; licensing was also ambiguous.
