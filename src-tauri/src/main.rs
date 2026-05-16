// Tauri v2 desktop wrapper. The "frontend" is a Python web app that runs
// as a sidecar process; we navigate the webview to localhost:<port> once
// the sidecar prints `SP404_PORT=<n>` to stdout.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    sp404_toolkit_lib::run();
}
