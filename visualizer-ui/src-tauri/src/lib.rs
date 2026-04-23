use chrono::Utc;
use notify::{Config, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use tauri::{AppHandle, Emitter, Manager};

const INPUT_COUNT: u8 = 4;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct SourceNode {
    device_id: String,
    ip: String,
    active: bool,
    connected_input: Option<u8>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InputNode {
    input_id: u8,
    multicast_ip: String,
    active: bool,
    connected_device_id: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RouteEdge {
    device_id: String,
    input_id: u8,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RoutingSnapshot {
    sources: Vec<SourceNode>,
    inputs: Vec<InputNode>,
    routes: Vec<RouteEdge>,
    last_updated: String,
    errors: Vec<String>,
}

#[derive(Debug, Clone)]
struct AppPaths {
    project_root: PathBuf,
    config: PathBuf,
    state: PathBuf,
    payloads: [PathBuf; INPUT_COUNT as usize],
}

#[derive(Debug, Deserialize)]
struct ConfigFile {
    devices: Vec<ConfigDevice>,
}

#[derive(Debug, Deserialize)]
struct ConfigDevice {
    id: Value,
    ip: String,
}

#[derive(Debug, Deserialize)]
struct BrokerState {
    input_to_device: Option<HashMap<String, String>>,
}

#[tauri::command]
fn get_routing_snapshot(app: AppHandle) -> Result<RoutingSnapshot, String> {
    let paths = app.state::<AppPaths>();
    println!(
        "[routing_visualizer] get_routing_snapshot invoked; broker_state.json={}",
        paths.state.display()
    );
    Ok(build_snapshot(&paths, "command:get_routing_snapshot"))
}

fn normalize_device_id(value: &str) -> String {
    let digits = value.trim().trim_start_matches('0');
    let numeric = if digits.is_empty() { "0" } else { digits };
    match numeric.parse::<u16>() {
        Ok(num) => format!("{num:02}"),
        Err(_) => value.trim().to_string(),
    }
}

fn normalize_config_id(value: &Value) -> String {
    if let Some(num) = value.as_u64() {
        return format!("{num:02}");
    }
    if let Some(text) = value.as_str() {
        return normalize_device_id(text);
    }
    "00".to_string()
}

fn read_config_devices(path: &Path, errors: &mut Vec<String>) -> Vec<(String, String)> {
    match fs::read_to_string(path) {
        Ok(contents) => match serde_yaml::from_str::<ConfigFile>(&contents) {
            Ok(parsed) => parsed
                .devices
                .into_iter()
                .map(|device| (normalize_config_id(&device.id), device.ip))
                .collect(),
            Err(err) => {
                errors.push(format!("Failed parsing config YAML: {err}"));
                vec![]
            }
        },
        Err(err) => {
            errors.push(format!("Failed reading config file: {err}"));
            vec![]
        }
    }
}

fn read_state_map(path: &Path, errors: &mut Vec<String>) -> HashMap<u8, String> {
    match fs::read_to_string(path) {
        Ok(contents) => match serde_json::from_str::<BrokerState>(&contents) {
            Ok(parsed) => parsed
                .input_to_device
                .unwrap_or_default()
                .into_iter()
                .filter_map(|(input, device)| {
                    input
                        .parse::<u8>()
                        .ok()
                        .map(|k| (k, normalize_device_id(&device)))
                })
                .collect(),
            Err(err) => {
                errors.push(format!("Failed parsing broker state JSON: {err}"));
                HashMap::new()
            }
        },
        Err(err) => {
            errors.push(format!("Failed reading broker state file: {err}"));
            HashMap::new()
        }
    }
}

fn read_multicast_ip(path: &Path, errors: &mut Vec<String>, input_id: u8) -> String {
    match fs::read_to_string(path) {
        Ok(contents) => match serde_json::from_str::<Value>(&contents) {
            Ok(json) => json
                .get("dstIpAddress")
                .and_then(Value::as_str)
                .unwrap_or_else(|| {
                    errors.push(format!(
                        "Input {input_id}: missing dstIpAddress in payload JSON"
                    ));
                    "—"
                })
                .to_string(),
            Err(err) => {
                errors.push(format!("Input {input_id}: invalid payload JSON: {err}"));
                "—".to_string()
            }
        },
        Err(err) => {
            errors.push(format!(
                "Input {input_id}: payload file not readable: {err}"
            ));
            "—".to_string()
        }
    }
}

fn build_snapshot(paths: &AppPaths, reason: &str) -> RoutingSnapshot {
    println!(
        "[routing_visualizer] rebuilding snapshot ({reason}); broker_state.json={}",
        paths.state.display()
    );

    let mut errors = Vec::new();
    let devices = read_config_devices(&paths.config, &mut errors);
    let route_map = read_state_map(&paths.state, &mut errors);

    let active_lookup: HashMap<String, u8> = route_map
        .iter()
        .map(|(input, device_id)| (device_id.clone(), *input))
        .collect();

    let sources = devices
        .iter()
        .map(|(device_id, ip)| {
            let connected_input = active_lookup.get(device_id).copied();
            SourceNode {
                device_id: device_id.clone(),
                ip: ip.clone(),
                active: connected_input.is_some(),
                connected_input,
            }
        })
        .collect::<Vec<_>>();

    let mut input_multicasts: BTreeMap<u8, String> = BTreeMap::new();
    for (index, payload_path) in paths.payloads.iter().enumerate() {
        let input_id = (index + 1) as u8;
        input_multicasts.insert(
            input_id,
            read_multicast_ip(payload_path, &mut errors, input_id),
        );
    }

    let inputs = (1..=INPUT_COUNT)
        .map(|input_id| {
            let connected_device_id = route_map.get(&input_id).cloned();
            InputNode {
                input_id,
                multicast_ip: input_multicasts
                    .get(&input_id)
                    .cloned()
                    .unwrap_or_else(|| "—".to_string()),
                active: connected_device_id.is_some(),
                connected_device_id,
            }
        })
        .collect::<Vec<_>>();

    let routes = route_map
        .iter()
        .map(|(input_id, device_id)| RouteEdge {
            device_id: device_id.clone(),
            input_id: *input_id,
        })
        .collect::<Vec<_>>();

    println!(
        "[routing_visualizer] snapshot rebuilt ({reason}): sources={}, inputs={}, routes={}, errors={}",
        sources.len(),
        inputs.len(),
        routes.len(),
        errors.len()
    );

    RoutingSnapshot {
        sources,
        inputs,
        routes,
        last_updated: Utc::now().to_rfc3339(),
        errors,
    }
}

fn canonical_or_original(path: PathBuf) -> PathBuf {
    fs::canonicalize(&path).unwrap_or(path)
}

fn is_project_root(path: &Path) -> bool {
    path.join("config/config.yaml").exists()
        && path.join("state/broker_state.json").exists()
        && path.join("payload/Multicast_video_input_1.json").exists()
}

fn find_root_from(start: PathBuf) -> Option<PathBuf> {
    let mut current = start;
    loop {
        if is_project_root(&current) {
            return Some(canonical_or_original(current));
        }
        if !current.pop() {
            return None;
        }
    }
}

fn resolve_project_root() -> PathBuf {
    let mut candidates = Vec::new();

    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd);
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            candidates.push(parent.to_path_buf());
        }
    }

    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    for candidate in candidates {
        if let Some(root) = find_root_from(candidate) {
            return root;
        }
    }

    canonical_or_original(std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

fn build_paths() -> AppPaths {
    let root = resolve_project_root();
    AppPaths {
        project_root: root.clone(),
        config: root.join("config/config.yaml"),
        state: root.join("state/broker_state.json"),
        payloads: [
            root.join("payload/Multicast_video_input_1.json"),
            root.join("payload/Multicast_video_input_2.json"),
            root.join("payload/Multicast_video_input_3.json"),
            root.join("payload/Multicast_video_input_4.json"),
        ],
    }
}

fn log_paths(paths: &AppPaths) {
    println!(
        "[routing_visualizer] resolved project_root={}",
        paths.project_root.display()
    );
    println!(
        "[routing_visualizer] resolved config_path={}",
        paths.config.display()
    );
    println!(
        "[routing_visualizer] resolved broker_state_path={}",
        paths.state.display()
    );
    for payload in &paths.payloads {
        println!(
            "[routing_visualizer] resolved payload_path={}",
            payload.display()
        );
    }
}

fn relevant_event_paths(event: &Event, paths: &AppPaths) -> Vec<PathBuf> {
    let relevant_names: HashSet<&str> = [
        "broker_state.json",
        "config.yaml",
        "Multicast_video_input_1.json",
        "Multicast_video_input_2.json",
        "Multicast_video_input_3.json",
        "Multicast_video_input_4.json",
    ]
    .into_iter()
    .collect();

    event
        .paths
        .iter()
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| relevant_names.contains(name))
        })
        .map(|path| canonical_or_original(path.clone()))
        .filter(|path| {
            path.starts_with(paths.project_root.join("state"))
                || path.starts_with(paths.project_root.join("config"))
                || path.starts_with(paths.project_root.join("payload"))
        })
        .collect()
}

fn start_file_watcher(app: AppHandle, paths: AppPaths) {
    let (tx, rx) = mpsc::channel();

    std::thread::spawn(move || {
        let mut watcher = match RecommendedWatcher::new(tx, Config::default()) {
            Ok(watcher) => watcher,
            Err(err) => {
                eprintln!("[routing_visualizer] failed to create watcher: {err}");
                return;
            }
        };

        let watch_dirs = [
            paths.project_root.join("config"),
            paths.project_root.join("state"),
            paths.project_root.join("payload"),
        ];

        for dir in watch_dirs {
            if let Err(err) = watcher.watch(&dir, RecursiveMode::NonRecursive) {
                eprintln!(
                    "[routing_visualizer] watcher warning for {}: {err}",
                    dir.display()
                );
            } else {
                println!("[routing_visualizer] watching directory={}", dir.display());
            }
        }

        while let Ok(result) = rx.recv() {
            match result {
                Ok(event)
                    if matches!(
                        event.kind,
                        EventKind::Modify(_) | EventKind::Create(_) | EventKind::Remove(_)
                    ) =>
                {
                    let hits = relevant_event_paths(&event, &paths);
                    if hits.is_empty() {
                        continue;
                    }

                    println!(
                        "[routing_visualizer] watcher event kind={:?} paths={:?}",
                        event.kind, hits
                    );
                    let snapshot = build_snapshot(&paths, "watcher:event");
                    if let Err(err) = app.emit("routing_snapshot_updated", snapshot) {
                        eprintln!(
                            "[routing_visualizer] failed emitting routing_snapshot_updated: {err}"
                        );
                    } else {
                        println!("[routing_visualizer] emitted routing_snapshot_updated");
                    }
                }
                Ok(_) => {}
                Err(err) => {
                    eprintln!("[routing_visualizer] watch event error: {err}");
                }
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let paths = build_paths();
            log_paths(&paths);
            app.manage(paths.clone());

            let initial = build_snapshot(&paths, "startup");
            if let Err(err) = app.emit("routing_snapshot_updated", initial) {
                eprintln!("[routing_visualizer] failed emitting startup snapshot: {err}");
            } else {
                println!("[routing_visualizer] emitted startup routing snapshot");
            }

            start_file_watcher(app.handle().clone(), paths);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_routing_snapshot])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
