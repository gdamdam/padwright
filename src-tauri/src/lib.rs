// Library crate so `cargo tauri dev` and `cargo tauri build` share entry.
//
// Lifecycle:
//   1. setup() spawns the `sp404-server` sidecar with the user's --root
//      and --samples paths, plus FFMPEG_PATH/FFPROBE_PATH pointing at the
//      bundled ffmpeg sidecars.
//   2. We listen for stdout lines and parse `SP404_PORT=<n>`.
//   3. Once the port is known we navigate the main webview to
//      http://127.0.0.1:<port>/.
//   4. The child is killed when the app exits.

use std::sync::{Arc, Mutex};
use tauri::{Manager, RunEvent, WebviewUrl};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
struct AppState {
    child: Arc<Mutex<Option<CommandChild>>>,
}

/// Path resolution for the bundled ffmpeg/ffprobe sidecars. Tauri resolves
/// `sidecar("ffmpeg")` to the platform-specific binary at runtime, but the
/// Python server needs an absolute file path through env vars. We get
/// those paths via `app.path().resource_dir()`.
fn bundled_bin_path(app: &tauri::AppHandle, name: &str) -> Option<std::path::PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    // Tauri places sidecars next to the executable under a known layout.
    // On macOS that's <bundle>/Contents/MacOS/ alongside the main binary.
    // Try a few well-known locations to be robust across platforms.
    let candidates = [
        resource_dir.join(name),
        resource_dir.join("binaries").join(name),
        resource_dir.parent()?.join("MacOS").join(name),
    ];
    candidates.into_iter().find(|p| p.exists())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState::default())
        .setup(|app| {
            let handle = app.handle().clone();
            let state: tauri::State<AppState> = app.state();
            let child_slot = state.child.clone();

            // Default --root is ~/Library/Application Support/<id>/kits.
            let app_data = app.path().app_data_dir().unwrap_or_else(|_| {
                app.path().home_dir().unwrap().join(".sp404")
            });
            let kits_root = app_data.join("kits");
            std::fs::create_dir_all(&kits_root).ok();

            // Resolve bundled binaries (best effort; falls back to PATH).
            let ffmpeg = bundled_bin_path(&handle, "ffmpeg")
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|| "ffmpeg".to_string());
            let ffprobe = bundled_bin_path(&handle, "ffprobe")
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|| "ffprobe".to_string());

            let sidecar = handle
                .shell()
                .sidecar("sp404-server")
                .expect("sp404-server sidecar not found — did you run PyInstaller?")
                .args([
                    "--root",
                    &kits_root.to_string_lossy(),
                    "--port",
                    "0",
                    "--no-browser",
                ])
                .env("FFMPEG_PATH", ffmpeg)
                .env("FFPROBE_PATH", ffprobe);

            let (mut rx, child) = sidecar.spawn().expect("failed to spawn sp404-server");
            *child_slot.lock().unwrap() = Some(child);

            // Listen for stdout, find SP404_PORT line, navigate webview.
            tauri::async_runtime::spawn(async move {
                let mut port: Option<u16> = None;
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line_bytes)
                        | CommandEvent::Stderr(line_bytes) => {
                            let line = String::from_utf8_lossy(&line_bytes);
                            // Log to console for visibility during development.
                            eprintln!("[sp404-server] {}", line.trim_end());
                            if port.is_none() {
                                if let Some(p) = parse_port(&line) {
                                    port = Some(p);
                                    let url = format!("http://127.0.0.1:{}/", p);
                                    if let Some(win) = handle.get_webview_window("main") {
                                        let _ = win.navigate(url.parse().unwrap());
                                    }
                                }
                            }
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[sp404-server] terminated: {:?}", payload);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                let state: tauri::State<AppState> = app.state();
                if let Some(child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}

fn parse_port(line: &str) -> Option<u16> {
    let line = line.trim();
    let rest = line.strip_prefix("SP404_PORT=")?;
    rest.split_whitespace().next()?.parse().ok()
}

// Silence unused import warnings when WebviewUrl isn't referenced directly.
#[allow(dead_code)]
fn _unused() {
    let _ = WebviewUrl::App("index.html".into());
}
