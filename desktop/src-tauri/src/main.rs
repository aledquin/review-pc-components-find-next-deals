// PC Upgrade Advisor - Tauri shell (scaffolding).
//
// Responsibilities:
//   1. Launch the pinned `pca-sidecar` binary on 127.0.0.1:8765 with an
//      ephemeral shared token.
//   2. Wait for /health, then show the main window.
//   3. Forward the token to the webview via a window variable so HTMX calls
//      include it as `x-pca-token`.
//   4. Ensure the sidecar is terminated on app shutdown.
//
// A full implementation will live here once Wave 4 exits scaffolding.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct SidecarHandle(Mutex<Option<Child>>);

fn main() {
    tauri::Builder::default()
        .manage(SidecarHandle(Mutex::new(None)))
        .setup(|app| {
            let token = uuid::Uuid::new_v4().to_string();
            let sidecar_path = app
                .path()
                .resource_dir()
                .expect("resource dir")
                .join("binaries")
                .join("pca-sidecar");
            let child = Command::new(sidecar_path)
                .args(["serve", "--host", "127.0.0.1", "--port", "8765", "--token", &token])
                .spawn();
            if let Ok(c) = child {
                *app.state::<SidecarHandle>().0.lock().unwrap() = Some(c);
            }
            let main = app.get_webview_window("main").expect("main window");
            main.eval(&format!("window.__PCA_TOKEN = '{}';", token))
                .ok();
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(handle) = window.app_handle().try_state::<SidecarHandle>() {
                    if let Some(mut c) = handle.0.lock().unwrap().take() {
                        let _ = c.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
