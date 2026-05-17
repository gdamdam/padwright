// Padwright — Tauri v2 desktop wrapper. The "frontend" is a Python web
// app that runs as a sidecar process; the Rust shell navigates the
// webview to the sidecar's localhost port via a custom app:// URI scheme.
// See lib.rs for the lifecycle and proxy details.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    padwright_lib::run();
}
