# Crestron-Broker

Production-oriented Python broker service that accepts Crestron WebSocket routing commands and applies Matrox ConvertIP REST API payloads.

## Matrox API details extracted from `ConvertIP_APIdocumentation.pdf`

The broker implementation follows the documented endpoints and models from the PDF:

- Login endpoint: `POST /user/login`
  - Request body fields: `username`, `password`, optional `closeExistingSessions`.
  - Success response includes `access_token` and `refresh_token`; broker uses `access_token` as `Authorization: Bearer ...` and also keeps cookies from the same session.
- Stream endpoints used:
  - `GET/POST /device/settings/streams/video/0`
  - `GET/POST /device/settings/streams/audio/0`
  - `GET/POST /device/settings/streams/video/0/manual`
  - `GET/POST /device/settings/streams/audio/0/manual`
- Authorization behavior:
  - API returns `401` for unauthenticated requests.
- Payload shape:
  - `.../video/0` and `.../audio/0` payloads include stream-level fields such as `enable`, `nmosId`.
  - `.../video/0/manual` and `.../audio/0/manual` carry destination multicast fields including `dstIpAddress`.

### Deviation note

The provided PDF is highly encoded and not trivially machine-readable in this environment; extraction was performed using a local stream/CMap decoder script. The key endpoint and field names above were recovered from that extraction plus verified payload JSON files. No undocumented API endpoints were invented.

## Project structure

```
app/
  __init__.py
  main.py
  config.py
  logging_setup.py
  models.py
  payload_manager.py
  state_store.py
  matrox_client.py
  broker_service.py
  websocket_server.py
config/
  config.example.yaml
  config.yaml
payload/
  *.json
state/
  broker_state.json
tools/
  test_client.py
requirements.txt
README.md
```

## Configuration

Edit `config/config.yaml`:

- `bind_host`: `0.0.0.0`
- `bind_port`: `8080`
- `devices`: includes all 7 required devices (IDs `01`..`07`, including `10.100.20.101` for ID `07`)
- `username` / `password`: default credentials
- `payload_directory`: payload source path
- `state_file`: persistent state cache path
- `dry_run`: if `true`, all POST requests are logged but not sent

## How startup sync works

At startup the broker:
1. logs into all configured devices,
2. GETs current stream+manual state for audio/video,
3. maps each device's `dstIpAddress` against payload-derived input mappings,
4. keeps only devices where both audio+video are enabled and point to the same logical input,
5. writes `state/broker_state.json` with:
   - `input_to_device`
   - per-device `video_stream`, `audio_stream`, `video_manual`, `audio_manual`
   - `last_successful_sync`

This ensures state reconstruction from live device state, not stale cache.

## Routing behavior

Incoming WebSocket command format: `input_id,device_id` (e.g. `1,7`).

Validation:
- command shape must be exactly two comma-separated values,
- input in range `1..4`,
- device in configured set (`01..07`, accepts both `7` and `07`).

Routing order:
1. identify old device for input from in-memory state,
2. disable old device video/audio streams,
3. apply target input video+audio manual payloads,
4. enable target device video/audio streams,
5. persist updated state,
6. return `<input>,<device> OK!`.

If any step fails, broker returns `ERROR route failed` and does not persist success state.

## Run instructions

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main --config config/config.yaml
```

Dry run:

```bash
python -m app.main --config config/config.yaml --dry-run
```

## WebSocket test procedure

Terminal 1:
```bash
python -m app.main --config config/config.yaml
```

Terminal 2:
```bash
python tools/test_client.py
```

Or custom commands:
```bash
python tools/test_client.py --uri ws://127.0.0.1:8080 1,7 1,6 3,7
```

## Important implementation decisions

- **Config-driven inventory/credentials**: no device IPs are hardcoded in routing logic.
- **Payloads loaded from disk**: no hardcoded request bodies when payload file exists.
- **State reconstruction on boot**: uses live GET state + payload-derived multicast mapping.
- **Transport isolation**: command parsing and routing is in `BrokerService`; WebSocket adapter is thin.
- **Self-signed TLS support**: `verify=False` and warning suppression enabled.
- **Safe commit policy**: state updates are persisted only after full route flow succeeds.

## Desktop Routing Visualizer (Tauri + Svelte + Rust)

A read-only visualization desktop app is available under `visualizer-ui/`.

### What it does
- Reads source devices from `config/config.yaml`
- Reads current routes from `state/broker_state.json`
- Reads input multicast destination IPs from `payload/Multicast_video_input_{1..4}.json`
- Renders a premium dark routing map with active source/input highlights and curved SVG route lines
- Updates live using a Rust file watcher and emits updates to the frontend

### Run locally

```bash
cd visualizer-ui
npm install
npm run tauri dev
```

### Build desktop bundle

```bash
cd visualizer-ui
npm run tauri build
```

### Path resolution assumption
The backend searches upward from the current working directory until it finds both:
- `config/config.yaml`
- `state/broker_state.json`

This keeps relative repository paths stable when launching from inside `visualizer-ui`.
