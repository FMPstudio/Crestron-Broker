use chrono::Utc;
use notify::{Config, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, HashMap};
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
    Ok(build_snapshot(&paths))
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
                .filter_map(|(input, device)| input.parse::<u8>().ok().map(|k| (k, normalize_device_id(&device))))
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
                    errors.push(format!("Input {input_id}: missing dstIpAddress in payload JSON"));
                    "—"
                })
                .to_string(),
            Err(err) => {
                errors.push(format!("Input {input_id}: invalid payload JSON: {err}"));
                "—".to_string()
            }
        },
        Err(err) => {
            errors.push(format!("Input {input_id}: payload file not readable: {err}"));
            "—".to_string()
        }
    }
}

fn build_snapshot(paths: &AppPaths) -> RoutingSnapshot {
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
        input_multicasts.insert(input_id, read_multicast_ip(payload_path, &mut errors, input_id));
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

    RoutingSnapshot {
        sources,
        inputs,
        routes,
        last_updated: Utc::now().to_rfc3339(),
        errors,
    }
}

fn detect_repo_root() -> PathBuf {
    let mut current = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    loop {
        if current.join("config/config.yaml").exists() && current.join("state/broker_state.json").exists() {
            return current;
        }
        if !current.pop() {
            return std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        }
    }
}

fn build_paths() -> AppPaths {
    let root = detect_repo_root();
    AppPaths {
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

fn start_file_watcher(app: AppHandle, paths: AppPaths) {
    let (tx, rx) = mpsc::channel();

    std::thread::spawn(move || {
        let mut watcher = match RecommendedWatcher::new(tx, Config::default()) {
            Ok(watcher) => watcher,
            Err(err) => {
                let _ = app.emit("routing_snapshot_updated", build_snapshot(&paths));
                eprintln!("Failed to create watcher: {err}");
                return;
            }
        };

        let mut files_to_watch = vec![paths.config.clone(), paths.state.clone()];
        files_to_watch.extend(paths.payloads.iter().cloned());

        for file in files_to_watch {
            if let Err(err) = watcher.watch(&file, RecursiveMode::NonRecursive) {
                eprintln!("Watcher warning for {}: {err}", file.display());
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
                    let snapshot = build_snapshot(&paths);
                    let _ = app.emit("routing_snapshot_updated", snapshot);
                }
                Ok(_) => {}
                Err(err) => {
                    eprintln!("Watch event error: {err}");
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
            app.manage(paths.clone());

            let initial = build_snapshot(&paths);
            let _ = app.emit("routing_snapshot_updated", initial);
            start_file_watcher(app.handle().clone(), paths);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_routing_snapshot])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
