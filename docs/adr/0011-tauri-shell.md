# 0011 - Tauri desktop shell with Python sidecar

- Status: Accepted (scaffolding only)
- Date: 2026-04-17
- Deciders: @pca-team
- Tags: ui, wave-4, packaging

## Context

Wave 4 is a native desktop experience. The choice is between three shells:

| Shell    | Binary size | Memory | Sandbox       | Tooling cost        |
| -------- | ----------- | ------ | ------------- | ------------------- |
| Electron | ~150 MB     | High   | Chromium      | Node, huge dep tree |
| Tauri    | ~10 MB      | Low    | System webview | Rust toolchain      |
| PyInstaller + Qt | ~80 MB | Medium | None       | PySide6, Qt license |

## Decision

Use **Tauri 2**. The Python app is packaged as a signed `pca-sidecar`
binary (PyInstaller) that the Rust shell spawns on launch. The webview loads
`http://127.0.0.1:8765/` once the sidecar reports healthy.

An ephemeral shared secret is generated per launch and handed to the webview
via `window.__PCA_TOKEN`; all HTMX calls forward it as `x-pca-token`. The
sidecar validates it on every request.

Auto-update uses Tauri's built-in updater plugin backed by signed release
manifests; the signing key lives exclusively in the release workflow's OIDC
credential.

## Consequences

Positive:

- 10-15x smaller installers than Electron.
- Native-platform styling (Edge WebView2 on Windows, WebKit on macOS).
- The web dashboard (Wave 3) is literally the UI; one codebase.

Negative:

- Release pipeline grows a Rust toolchain requirement.
- macOS notarization adds ~5 minutes per release.
- PyInstaller sidecars are large; Apple Silicon + Intel both need binaries.

## Alternatives considered

- **Electron**: simpler for JS-native teams, but bundle and memory cost.
- **PyInstaller + Qt**: Qt licensing is painful and we'd lose the CLI-free
  sidecar decoupling.
- **Ship only the CLI + web**: rejected because non-technical users want
  a launcher icon and auto-update.
