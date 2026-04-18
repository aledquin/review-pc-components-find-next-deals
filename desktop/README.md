# Desktop shell (Tauri)

A thin Tauri application that wraps the Wave 3 FastAPI dashboard. The Rust
shell spawns the bundled Python sidecar on launch, waits for the
`/health` endpoint to return `{"status":"ok"}`, then loads the web UI
inside a native window.

## Status

Wave 4 - scaffolding only. No binaries are produced from the CI pipeline
yet; the Rust toolchain install cost is deferred until the UX is pinned.

## Layout

```
desktop/
├── src-tauri/
│   ├── Cargo.toml        # Rust crate (Tauri 2.x)
│   ├── tauri.conf.json   # Window, bundle, and sidecar config
│   └── src/main.rs       # Spawn sidecar + init window
├── index.html            # Splash screen shown while the sidecar warms up
└── README.md
```

## Sidecar

The sidecar is the pinned `pca serve` executable produced by PyInstaller
and committed (or downloaded) as a signed binary. The Tauri shell launches
it bound to `127.0.0.1` with an ephemeral token; that token is passed to
the webview via `window.__PCA_TOKEN` and used as the `x-pca-token` header
on every HTMX request.

## Signing / notarization

Handled by the release workflow (`release.yml`, tracked separately):

- macOS: `codesign --timestamp --options runtime` + `notarytool submit`.
- Windows: `signtool sign /fd sha256 /tr http://timestamp.digicert.com`.
- Linux: AppImage + detached GPG signature; Flatpak/Snap optional.

## Auto-update

Tauri's built-in updater reads a signed `latest.json` from GitHub Releases.
The public key is committed in `tauri.conf.json`; the private key never
leaves the release runner's OIDC-scoped KMS credential.

See ADR 0011 for the sidecar + packaging decision.
