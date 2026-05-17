// Library crate so `cargo tauri dev` and `cargo tauri build` share entry.
//
// Architecture:
//   - The Python sidecar (padwright-server) runs on http://127.0.0.1:<port>.
//   - The WebView would normally load that URL directly, but WKWebView's
//     ATS refuses plain-HTTP loads even to localhost in many setups, and
//     the dev binary has no Info.plist to override.
//   - Workaround: register a custom URI scheme `app://`. The WebView loads
//     `app://localhost/...`, Rust intercepts every request and proxies it
//     to the sidecar over HTTP. ATS doesn't apply because the scheme is
//     custom, not http.
//
// Lifecycle:
//   1. setup() spawns the sidecar, listens for `PADWRIGHT_PORT=<n>` on stdout
//      to learn where it's running, stashes the URL in shared state.
//   2. Once the URL is known, eval() into the loading window flips the
//      location to `app://localhost/`.
//   3. Every `app://` request from the webview is proxied by
//      proxy_to_sidecar() via ureq (synchronous, runs on Tauri's
//      protocol-handler thread).
//   4. On exit, the sidecar process is killed.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::borrow::Cow;
use std::io::Read;
use std::sync::{Arc, Mutex};
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Default, Clone)]
struct ServerUrl(Arc<Mutex<Option<String>>>);

#[derive(Default)]
struct AppState {
    child: Arc<Mutex<Option<CommandChild>>>,
}

fn bundled_bin_path(app: &tauri::AppHandle, name: &str) -> Option<std::path::PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let candidates = [
        resource_dir.join(name),
        resource_dir.join("binaries").join(name),
        resource_dir.parent()?.join("MacOS").join(name),
    ];
    candidates.into_iter().find(|p| p.exists())
}

pub fn run() {
    let server_url = ServerUrl::default();
    let server_url_for_proto = server_url.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .register_uri_scheme_protocol("app", move |_ctx, request| {
            proxy_to_sidecar(&server_url_for_proto, request)
        })
        .manage(AppState::default())
        .manage(server_url)
        .setup(|app| {
            let handle = app.handle().clone();
            let app_state: tauri::State<AppState> = app.state();
            let url_state: tauri::State<ServerUrl> = app.state();
            let child_slot = app_state.child.clone();
            let url_slot = url_state.0.clone();

            // No --root/--samples here: Python reads its saved config
            // (see web/app.py / the /settings page in the UI). On first
            // launch the sidecar defaults to its platform data dir; the
            // user changes it from the Settings page and it persists.
            let ffmpeg = bundled_bin_path(&handle, "ffmpeg")
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|| "ffmpeg".to_string());
            let ffprobe = bundled_bin_path(&handle, "ffprobe")
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|| "ffprobe".to_string());

            let sidecar = handle
                .shell()
                .sidecar("padwright-server")
                .expect("padwright-server sidecar not found — did you run PyInstaller?")
                .args(["--port", "0", "--no-browser"])
                .env("FFMPEG_PATH", ffmpeg)
                .env("FFPROBE_PATH", ffprobe);

            let (mut rx, child) = sidecar.spawn().expect("failed to spawn padwright-server");
            *child_slot.lock().unwrap() = Some(child);

            tauri::async_runtime::spawn(async move {
                let mut port: Option<u16> = None;
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(b) | CommandEvent::Stderr(b) => {
                            let line = String::from_utf8_lossy(&b);
                            eprintln!("[padwright-server] {}", line.trim_end());
                            if port.is_none() {
                                if let Some(p) = parse_port(&line) {
                                    port = Some(p);
                                    let upstream = format!("http://127.0.0.1:{}", p);
                                    *url_slot.lock().unwrap() = Some(upstream.clone());
                                    eprintln!(
                                        "[tauri] sidecar ready at {} — switching webview to app://localhost/",
                                        upstream
                                    );
                                    if let Some(win) = handle.get_webview_window("main") {
                                        let js = "window.location.replace('app://localhost/');";
                                        if let Err(e) = win.eval(js) {
                                            eprintln!("[tauri] eval failed: {}", e);
                                        }
                                    } else {
                                        eprintln!("[tauri] no 'main' window found");
                                    }
                                }
                            }
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[padwright-server] terminated: {:?}", payload);
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
                let child_opt = state.child.lock().unwrap().take();
                if let Some(child) = child_opt {
                    let _ = child.kill();
                }
            }
        });
}

fn parse_port(line: &str) -> Option<u16> {
    line.trim()
        .strip_prefix("PADWRIGHT_PORT=")?
        .split_whitespace()
        .next()?
        .parse()
        .ok()
}

/// Proxy a webview request to the Python sidecar via HTTP.
///
/// Runs on Tauri's protocol-handler thread (synchronous). We deliberately
/// disable redirect-following so 303 responses (POST→GET) pass through to
/// the webview, which will then issue a fresh GET that re-enters this
/// handler.
fn proxy_to_sidecar(
    server_url: &ServerUrl,
    request: http::Request<Vec<u8>>,
) -> http::Response<Cow<'static, [u8]>> {
    let upstream = match server_url.0.lock().unwrap().clone() {
        Some(u) => u,
        None => return error_resp(503, "sidecar not ready yet — try again in a moment"),
    };

    let path_and_query = request
        .uri()
        .path_and_query()
        .map(|p| p.as_str().to_string())
        .unwrap_or_else(|| "/".to_string());
    let target = format!("{}{}", upstream.trim_end_matches('/'), path_and_query);

    // Capture method + headers + body before consuming the request.
    let method = request.method().clone();
    let headers_to_forward: Vec<(String, String)> = request
        .headers()
        .iter()
        .filter_map(|(k, v)| {
            let name = k.as_str().to_lowercase();
            // Skip headers that would mislead the upstream about the origin.
            if matches!(name.as_str(), "host" | "origin" | "referer") {
                return None;
            }
            v.to_str().ok().map(|s| (name, s.to_string()))
        })
        .collect();
    let body = request.into_body();
    let agent = ureq::AgentBuilder::new().redirects(0).build();

    // Retry transport errors (Connection refused etc.) for up to ~3s. The
    // sidecar's listener can be a beat late even after we print PADWRIGHT_PORT
    // from its lifespan hook. Application-level errors (4xx/5xx) are NOT
    // retried.
    let response: ureq::Response = {
        let mut last_err: Option<ureq::Error> = None;
        let mut got: Option<ureq::Response> = None;
        for attempt in 0..30 {
            let mut req = agent.request(method.as_str(), &target);
            for (k, v) in &headers_to_forward {
                req = req.set(k, v);
            }
            let attempt_result = if body.is_empty() {
                req.call()
            } else {
                req.send_bytes(&body)
            };
            match attempt_result {
                Ok(r) => { got = Some(r); break; }
                Err(ureq::Error::Status(_, r)) => { got = Some(r); break; }
                Err(e @ ureq::Error::Transport(_)) => {
                    last_err = Some(e);
                    if attempt == 0 {
                        eprintln!("[tauri] proxy waiting for sidecar to accept connections…");
                    }
                    std::thread::sleep(std::time::Duration::from_millis(100));
                }
            }
        }
        match got {
            Some(r) => r,
            None => {
                let msg = last_err
                    .map(|e| format!("proxy error: {}", e))
                    .unwrap_or_else(|| "proxy error: unknown".to_string());
                return error_resp(502, &msg);
            }
        }
    };

    let status = response.status();
    let content_type = response.content_type().to_string();
    let location = response.header("location").map(|s| s.to_string());
    let content_length = response.header("content-length").map(|s| s.to_string());

    let mut body_buf = Vec::new();
    let _ = response.into_reader().read_to_end(&mut body_buf);

    let mut builder = http::Response::builder()
        .status(status)
        .header("content-type", content_type);
    if let Some(loc) = location {
        // 303 redirect: rewrite Location from '/kit/foo' (relative) to
        // 'app://localhost/kit/foo' so the webview stays in the custom
        // scheme. Absolute URLs are left alone.
        let rewritten = if loc.starts_with('/') {
            format!("app://localhost{}", loc)
        } else {
            loc
        };
        builder = builder.header("location", rewritten);
    }
    if let Some(cl) = content_length {
        builder = builder.header("content-length", cl);
    }
    builder.body(body_buf.into()).unwrap()
}

fn error_resp(status: u16, msg: &str) -> http::Response<Cow<'static, [u8]>> {
    http::Response::builder()
        .status(status)
        .header("content-type", "text/plain; charset=utf-8")
        .body(msg.as_bytes().to_vec().into())
        .unwrap()
}
