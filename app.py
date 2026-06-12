import requests
import urllib3
import os
import json
import math
import time
import threading
import redis
from datetime import datetime, timedelta
from flask import Flask, jsonify, send_from_directory, request as flask_request
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIGURATION ──────────────────────────────────────────
BBOX_PASSWORD = os.getenv('BBOX_PASSWORD', '')
BBOX_BASE_URL = os.getenv('BBOX_BASE_URL', 'https://mabbox.bytel.fr')
URL_LOGIN = f"{BBOX_BASE_URL}/api/v1/login"
URL_STATS = f"{BBOX_BASE_URL}/api/v1/wan/ip/stats"
URL_WIFI = f"{BBOX_BASE_URL}/api/v1/wireless"
URL_HOSTS = f"{BBOX_BASE_URL}/api/v1/hosts"
URL_DEVICE = f"{BBOX_BASE_URL}/api/v1/device"
URL_WAN_IP = f"{BBOX_BASE_URL}/api/v1/wan/ip"


REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
MONITOR_INTERVAL = int(os.getenv('MONITOR_INTERVAL', '60'))
DATA_DIR = os.getenv('DATA_DIR', '/app/data')
DATA_FILE = os.path.join(DATA_DIR, 'bbox_history.json')

# Date de début d'infra (configurable)
_uptime_str = os.getenv('UPTIME_START_DATE', '')
if _uptime_str:
    try:
        UPTIME_START = datetime.strptime(_uptime_str, '%Y-%m-%d')
    except ValueError:
        UPTIME_START = datetime.now() - timedelta(days=14)
else:
    UPTIME_START = datetime.now() - timedelta(days=14)

TARGET_TB = float(os.getenv('TARGET_TB', '5'))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

bbox_session = requests.Session()
bbox_session.verify = False

app = Flask(__name__, static_folder='static')
history_lock = threading.Lock()

# ─── Redis Connection ───────────────────────────────────────

def is_redis_alive():
    """Check if Redis is reachable without crashing."""
    if redis_client is None:
        return False
    try:
        return redis_client.ping()
    except Exception:
        return False

redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    redis_client.ping()
    print("✅ Redis connecté.")
except Exception as e:
    print(f"⚠️ Redis indisponible ({e}), fallback fichier JSON.")
    redis_client = None

# ─── Redis Keys ─────────────────────────────────────────────
REDIS_HISTORY_KEY = "bboxpulse:history"
REDIS_TIMESERIES_KEY = "bboxpulse:timeseries"
REDIS_CONFIG_KEY = "bboxpulse:config"
REDIS_TIMESERIES_MAX = 10080  # 7 days @ 1 min

# ─── Helpers ────────────────────────────────────────────────

def human_bytes(size):
    """Format bytes to human-readable string with smart precision."""
    if size < 0:
        size = 0
    for unit in ['o', 'Ko', 'Mo', 'Go', 'To', 'Po']:
        if size < 1024.0:
            if size == int(size):
                return f"{int(size)} {unit}"
            elif size < 10:
                return f"{size:.2f} {unit}"
            elif size < 100:
                return f"{size:.1f} {unit}"
            else:
                return f"{size:.0f} {unit}"
        size /= 1024.0
    return f"{size:.2f} Eo"

def human_speed(kbps):
    """Format kbps to human-readable speed string."""
    val = float(kbps)
    if val >= 1000000:
        return f"{val/1000000:.2f} Gb/s"
    if val >= 1000:
        return f"{val/1000:.1f} Mb/s"
    if val >= 1:
        return f"{val:.0f} Kb/s"
    return "0 Kb/s"

# Unified global state for real-time speed calculation
global_speed_state = {
    "rx": 0,
    "tx": 0,
    "time": 0.0,
    "speed_down": 0.0,
    "speed_up": 0.0
}
global_speed_lock = threading.Lock()

def update_and_get_speed(curr_rx, curr_tx):
    """Update global speed counters and calculate speed in Kbps based on delta bytes and delta time."""
    global global_speed_state
    now = time.time()
    with global_speed_lock:
        if global_speed_state["time"] == 0 or global_speed_state["rx"] == 0:
            global_speed_state["rx"] = curr_rx
            global_speed_state["tx"] = curr_tx
            global_speed_state["time"] = now
            return 0.0, 0.0
        
        dt = now - global_speed_state["time"]
        # Limit speed updates to reasonable intervals to avoid division by zero or jitter
        if dt < 0.5:
            return global_speed_state["speed_down"], global_speed_state["speed_up"]
            
        delta_rx = curr_rx - global_speed_state["rx"]
        delta_tx = curr_tx - global_speed_state["tx"]
        
        # If box restarted or bytes wrapped
        if delta_rx < 0 or delta_tx < 0:
            global_speed_state["rx"] = curr_rx
            global_speed_state["tx"] = curr_tx
            global_speed_state["time"] = now
            return 0.0, 0.0
            
        # Speed in Kbps (kilobits per second)
        # bytes * 8 = bits. bits / dt / 1000 = Kbps.
        speed_down = (delta_rx * 8) / (dt * 1000)
        speed_up = (delta_tx * 8) / (dt * 1000)
        
        # Protect against anomalous huge spikes
        if speed_down > 10000000 or speed_up > 10000000:
            return global_speed_state["speed_down"], global_speed_state["speed_up"]
            
        global_speed_state["rx"] = curr_rx
        global_speed_state["tx"] = curr_tx
        global_speed_state["time"] = now
        global_speed_state["speed_down"] = speed_down
        global_speed_state["speed_up"] = speed_up
        
        return speed_down, speed_up



def human_eta(days):
    """Format ETA days to readable string."""
    if days <= 0:
        return "Terminé"
    d = int(days)
    h = int((days - d) * 24)
    if d > 365:
        years = d // 365
        remaining_days = d % 365
        return f"{years}a {remaining_days}j"
    if d > 0:
        return f"{d}j {h}h"
    return f"{h}h"

# ─── Data Storage (Redis + JSON fallback) ───────────────────

def load_data():
    default = {"bank_rx": 0, "bank_tx": 0, "last_rx": 0, "last_tx": 0}

    if redis_client:
        try:
            data = redis_client.hgetall(REDIS_HISTORY_KEY)
            if data:
                return {
                    "bank_rx": int(data.get("bank_rx", 0)),
                    "bank_tx": int(data.get("bank_tx", 0)),
                    "last_rx": int(data.get("last_rx", 0)),
                    "last_tx": int(data.get("last_tx", 0)),
                }
        except Exception as e:
            print(f"⚠️ Redis read error: {e}")

    # Fallback JSON
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                for key in default:
                    if key not in data:
                        data[key] = default[key]
                return data
        except Exception:
            return default
    return default

def save_data(data):
    if redis_client:
        try:
            redis_client.hset(REDIS_HISTORY_KEY, mapping={
                "bank_rx": str(data["bank_rx"]),
                "bank_tx": str(data["bank_tx"]),
                "last_rx": str(data["last_rx"]),
                "last_tx": str(data["last_tx"]),
            })
        except Exception as e:
            print(f"⚠️ Redis write error: {e}")

    # Always write JSON as backup
    try:
        os.makedirs(os.path.dirname(DATA_FILE) or '.', exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"⚠️ JSON write error: {e}")

def update_history_with_current(curr_rx, curr_tx):
    with history_lock:
        history = load_data()
        if history['last_rx'] == 0:
            history['last_rx'], history['last_tx'] = curr_rx, curr_tx

        if curr_rx < history['last_rx']:  # Reset de la box
            history['last_rx'], history['last_tx'] = curr_rx, curr_tx
        else:
            delta_rx = curr_rx - history['last_rx']
            delta_tx = curr_tx - history['last_tx']
            if 0 <= delta_rx < (50 * 1024**3):  # Protection contre les sauts bizarres
                history['bank_rx'] += delta_rx
                history['bank_tx'] += delta_tx
            history['last_rx'], history['last_tx'] = curr_rx, curr_tx

        save_data(history)
        return history

def record_timeseries(speed_down, speed_up, active_devices, known_devices):
    """Record a data point to Redis timeseries list."""
    now_str = datetime.now().isoformat()
    point = json.dumps({
        "timestamp": now_str,
        "speed_down": speed_down,
        "speed_up": speed_up,
        "active_devices": active_devices,
        "known_devices": known_devices
    })

    if redis_client:
        try:
            redis_client.rpush(REDIS_TIMESERIES_KEY, point)
            # Trim to max length
            redis_client.ltrim(REDIS_TIMESERIES_KEY, -REDIS_TIMESERIES_MAX, -1)
            return
        except Exception as e:
            print(f"⚠️ Redis timeseries error: {e}")

    # Fallback: fichier JSON
    ts_file = os.path.join(DATA_DIR, 'bbox_timeseries.json')
    try:
        ts_data = []
        if os.path.exists(ts_file):
            try:
                with open(ts_file, 'r') as f:
                    ts_data = json.load(f)
                if not isinstance(ts_data, list):
                    ts_data = []
            except (json.JSONDecodeError, ValueError):
                print("⚠️ Fichier timeseries corrompu, réinitialisation.")
                ts_data = []
        ts_data.append(json.loads(point))
        if len(ts_data) > REDIS_TIMESERIES_MAX:
            ts_data = ts_data[-REDIS_TIMESERIES_MAX:]
        with open(ts_file, 'w') as f:
            json.dump(ts_data, f)
    except Exception as e:
        print(f"⚠️ Erreur écriture timeseries: {e}")

def get_timeseries():
    """Retrieve all timeseries data from Redis or JSON fallback."""
    if redis_client:
        try:
            raw = redis_client.lrange(REDIS_TIMESERIES_KEY, 0, -1)
            return [json.loads(r) for r in raw]
        except Exception as e:
            print(f"⚠️ Redis timeseries read error: {e}")

    # Fallback
    ts_file = os.path.join(DATA_DIR, 'bbox_timeseries.json')
    if os.path.exists(ts_file):
        try:
            with open(ts_file, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, ValueError, Exception):
            print("⚠️ Fichier timeseries illisible, ignoré.")
            pass
    return []

# ─── Config Storage ─────────────────────────────────────────

def load_config():
    """Load configuration from Redis or return defaults from env."""
    defaults = {
        "bbox_password": BBOX_PASSWORD,
        "bbox_base_url": BBOX_BASE_URL,
        "monitor_interval": MONITOR_INTERVAL,
        "uptime_start_date": UPTIME_START.strftime('%Y-%m-%d'),
        "target_tb": TARGET_TB,
        "refresh_interval_ms": 4000,
        "max_chart_points": 60,
    }

    if redis_client:
        try:
            data = redis_client.hgetall(REDIS_CONFIG_KEY)
            if data:
                return {
                    "bbox_password": data.get("bbox_password", defaults["bbox_password"]),
                    "bbox_base_url": data.get("bbox_base_url", defaults["bbox_base_url"]),
                    "monitor_interval": int(data.get("monitor_interval", defaults["monitor_interval"])),
                    "uptime_start_date": data.get("uptime_start_date", defaults["uptime_start_date"]),
                    "target_tb": float(data.get("target_tb", defaults["target_tb"])),
                    "refresh_interval_ms": int(data.get("refresh_interval_ms", defaults["refresh_interval_ms"])),
                    "max_chart_points": int(data.get("max_chart_points", defaults["max_chart_points"])),
                }
        except Exception as e:
            print(f"⚠️ Redis config read error: {e}")

    return defaults

def save_config(config):
    """Save configuration to Redis."""
    if redis_client:
        try:
            redis_client.hset(REDIS_CONFIG_KEY, mapping={
                k: str(v) for k, v in config.items()
            })
            return True
        except Exception as e:
            print(f"⚠️ Redis config write error: {e}")
            return False
    return False

# ─── BBox Auth ──────────────────────────────────────────────

def login_bbox():
    try:
        config = load_config()
        password = config.get("bbox_password", BBOX_PASSWORD)
        res = bbox_session.post(URL_LOGIN, data={'password': password}, timeout=10)
        if res.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Bbox infiltrée.")
            return True
        return False
    except Exception as e:
        print(f"🔥 Erreur Login : {e}")
        return False

# ─── Background Monitor ─────────────────────────────────────

def background_monitor():
    time.sleep(15)
    login_bbox()  # Login initial

    while True:
        try:
            interval = load_config().get("monitor_interval", MONITOR_INTERVAL)
            time.sleep(interval)

            resp = bbox_session.get(URL_STATS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                
                # Safe stats extraction
                if isinstance(data, list) and len(data) > 0:
                    stats = data[0].get('wan', {}).get('ip', {}).get('stats', {})
                elif isinstance(data, dict):
                    stats = data.get('wan', {}).get('ip', {}).get('stats', {})
                else:
                    stats = {}
                    
                rx_stats = stats.get('rx', {})
                tx_stats = stats.get('tx', {})
                curr_rx = int(rx_stats.get('bytes', 0))
                curr_tx = int(tx_stats.get('bytes', 0))

                update_history_with_current(curr_rx, curr_tx)

                # Fetch devices count
                try:
                    hosts_res = bbox_session.get(URL_HOSTS, timeout=10)
                    if hosts_res.status_code == 200:
                        hosts_json = hosts_res.json()
                        if isinstance(hosts_json, list) and len(hosts_json) > 0:
                            host_list = hosts_json[0].get('hosts', {}).get('list', [])
                        elif isinstance(hosts_json, dict):
                            host_list = hosts_json.get('hosts', {}).get('list', [])
                        else:
                            host_list = []
                        active_dev = sum(1 for d in host_list if d.get('active') == 1)
                        known_dev = len(host_list)
                    else:
                        active_dev, known_dev = 0, 0
                except Exception:
                    active_dev, known_dev = 0, 0

                spd_dn, spd_up = update_and_get_speed(curr_rx, curr_tx)
                record_timeseries(spd_dn / 1000, spd_up / 1000, active_dev, known_dev)
            elif resp.status_code in (401, 403):
                print("⚠️ Session expirée, reconnexion...")
                login_bbox()
        except Exception as e:
            print(f"⚠️ Monitor error: {e}")
            # Try to re-login on connection errors
            try:
                login_bbox()
            except Exception:
                pass

monitor_thread = threading.Thread(target=background_monitor, daemon=True)
monitor_thread.start()

# ─── API Routes ─────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/graph')
def graph():
    return send_from_directory('static', 'graph.html')

@app.route('/setting')
def setting():
    return send_from_directory('static', 'setting.html')

@app.route('/api/health')
def api_health():
    """Healthcheck endpoint for Docker."""
    status = {
        "status": "ok",
        "redis": is_redis_alive(),
        "timestamp": datetime.now().isoformat()
    }
    return jsonify(status), 200

@app.route('/api/stats')
def api_stats():
    def get_bbox_data():
        try:
            resp = bbox_session.get(URL_STATS, timeout=15)
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                _ = data[0]['wan']['ip']['stats']
            elif isinstance(data, dict):
                _ = data['wan']['ip']['stats']
            else:
                return None
            return resp
        except Exception:
            return None

    response_stats = get_bbox_data()

    if response_stats is None:
        print("⚠️ Session perdue ou Bbox saturée. Tentative de reconnexion...")
        for i in range(3):
            if login_bbox():
                time.sleep(1)
                response_stats = get_bbox_data()
                if response_stats:
                    break
            time.sleep(2)

        if not response_stats:
            return jsonify({"error": "Bbox injoignable après 3 tentatives. Vérifiez votre réseau et le mot de passe."}), 503

    try:
        response_wifi = bbox_session.get(URL_WIFI, timeout=15)
        response_hosts = bbox_session.get(URL_HOSTS, timeout=15)
        response_device = bbox_session.get(URL_DEVICE, timeout=10)
        response_wan_ip = bbox_session.get(URL_WAN_IP, timeout=10)

        # --- PARSING ---
        # Parse System info
        sys_model = "Bbox"
        sys_firmware = "Inconnue"
        sys_connection = "Inconnue"
        sys_ip = "Inconnu"

        if response_device.status_code == 200:
            try:
                dev_json = response_device.json()
                if isinstance(dev_json, list) and len(dev_json) > 0:
                    dev_data = dev_json[0].get('device', {})
                elif isinstance(dev_json, dict):
                    dev_data = dev_json.get('device', {})
                else:
                    dev_data = {}
                sys_model = dev_data.get('modelname', 'Bbox')
                sys_firmware = dev_data.get('running', {}).get('version', 'Inconnue')
                using = dev_data.get('using', {})
                if using.get('ftth') == 1:
                    sys_connection = "Fibre (FTTH)"
                elif using.get('vdsl') == 1:
                    sys_connection = "VDSL"
                elif using.get('adsl') == 1:
                    sys_connection = "ADSL"
            except Exception:
                pass

        if response_wan_ip.status_code == 200:
            try:
                wan_json = response_wan_ip.json()
                if isinstance(wan_json, list) and len(wan_json) > 0:
                    wan_data = wan_json[0].get('wan', {})
                elif isinstance(wan_json, dict):
                    wan_data = wan_json.get('wan', {})
                else:
                    wan_data = {}
                sys_ip = wan_data.get('ip', {}).get('address', 'Inconnu')
            except Exception:
                pass

        data_stats = response_stats.json()
        if isinstance(data_stats, list) and len(data_stats) > 0:
            stats = data_stats[0].get('wan', {}).get('ip', {}).get('stats', {})
        elif isinstance(data_stats, dict):
            stats = data_stats.get('wan', {}).get('ip', {}).get('stats', {})
        else:
            stats = {}
            
        rx_stats = stats.get('rx', {})
        tx_stats = stats.get('tx', {})
        curr_rx = int(rx_stats.get('bytes', 0))
        curr_tx = int(tx_stats.get('bytes', 0))

        # Safe parsing for WIFI
        data_wifi = {}
        radio = {}
        r_24, r_5, r_6 = {}, {}, {}
        mlo_data = {}
        if response_wifi.status_code == 200:
            try:
                wifi_json = response_wifi.json()
                if isinstance(wifi_json, list) and len(wifi_json) > 0:
                    data_wifi = wifi_json[0].get('wireless', {})
                elif isinstance(wifi_json, dict):
                    data_wifi = wifi_json.get('wireless', {})
                
                radio = data_wifi.get('radio', {})
                r_24 = radio.get('24', {})
                r_5 = radio.get('5', {})
                r_6 = radio.get('6', {})
                mlo_data = data_wifi.get('mlo', {})
            except Exception as e:
                print(f"⚠️ Erreur parsing WiFi: {e}")

        # Safe parsing for Hosts
        active_devices = 0
        total_known = 0
        if response_hosts.status_code == 200:
            try:
                hosts_json = response_hosts.json()
                if isinstance(hosts_json, list) and len(hosts_json) > 0:
                    host_list = hosts_json[0].get('hosts', {}).get('list', [])
                elif isinstance(hosts_json, dict):
                    host_list = hosts_json.get('hosts', {}).get('list', [])
                else:
                    host_list = []
                active_devices = sum(1 for device in host_list if device.get('active') == 1)
                total_known = len(host_list)
            except Exception as e:
                print(f"⚠️ Erreur parsing Hosts: {e}")

        history = update_history_with_current(curr_rx, curr_tx)

        # --- CALCULS ---
        config = load_config()
        total_down = history['bank_rx']
        target_tb = config.get("target_tb", TARGET_TB)

        # L'objectif s'adapte par palier de 1 To
        current_to_floor = math.floor(total_down / (1024**4))
        computed_target = max(target_tb, current_to_floor + 1)
        target_bytes = computed_target * (1024**4)
        progress = min((total_down / target_bytes) * 100, 100)

        # ETA
        try:
            uptime_date_str = config.get("uptime_start_date", UPTIME_START.strftime('%Y-%m-%d'))
            uptime_start = datetime.strptime(uptime_date_str, '%Y-%m-%d')
        except Exception:
            uptime_start = UPTIME_START

        days_elapsed = (datetime.now() - uptime_start).total_seconds() / 86400
        avg_speed = total_down / days_elapsed if days_elapsed > 0 else 1
        eta_days = (target_bytes - total_down) / avg_speed if avg_speed > 0 else 0

        # Real-time speed calculation from byte difference
        spd_dn, spd_up = update_and_get_speed(curr_rx, curr_tx)

        return jsonify({
            "speed": {
                "down": human_speed(spd_dn),
                "up": human_speed(spd_up),
                "down_raw": spd_dn,
                "up_raw": spd_up,
            },
            "line_specs": {
                "max_down": human_speed(rx_stats.get('maxBandwidth', 0)),
                "contract_down": human_speed(rx_stats.get('contractualBandwidth', 0)),
            },
            "hardware": {
                "rx_packets": int(rx_stats.get('packets', 0)),
                "tx_packets": int(tx_stats.get('packets', 0)),
                "rx_errors": int(rx_stats.get('packetserrors', 0)),
                "tx_errors": int(tx_stats.get('packetserrors', 0)),
            },
            "network": {"active_devices": active_devices, "total_known": total_known},
            "wifi": {
                "band_2_4GHz": {"status": "ON" if r_24.get('enable') else "OFF", "standard": r_24.get('standard', '').upper()},
                "band_5GHz": {"status": "ON" if r_5.get('enable') else "OFF", "standard": r_5.get('standard', '').upper()},
                "band_6GHz": {"status": "ON" if r_6.get('enable') else "OFF", "standard": r_6.get('standard', '').upper()},
                "mlo_wifi7": {"status": "ON" if mlo_data.get('enable') else "OFF"}
            },
            "session": {
                "down": human_bytes(curr_rx),
                "up": human_bytes(curr_tx),
                "down_raw": curr_rx,
                "up_raw": curr_tx
            },
            "objective": {
                "target": f"{computed_target:.0f} To",
                "progress": round(progress, 2),
                "eta_avg": human_eta(eta_days)
            },
            "total": {
                "down": human_bytes(history['bank_rx']),
                "up": human_bytes(history['bank_tx'])
            },
            "system": {
                "model": sys_model,
                "firmware": sys_firmware,
                "connection_type": sys_connection,
                "public_ip": sys_ip
            },
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    except Exception as e:
        return jsonify({"error": f"Erreur traitement données: {repr(e)}"}), 500

@app.route('/api/history')
def api_history():
    timeframe = flask_request.args.get('timeframe', 'live')
    ts_data = get_timeseries()

    if not ts_data:
        return jsonify({"labels": [], "speed_down": [], "speed_up": [], "active_devices": [], "known_devices": []})

    try:
        now = datetime.now()

        if timeframe == 'live':
            cutoff = now - timedelta(minutes=30)
        elif timeframe == '1h':
            cutoff = now - timedelta(hours=1)
        elif timeframe == '24h':
            cutoff = now - timedelta(hours=24)
        elif timeframe == '7d':
            cutoff = now - timedelta(days=7)
        else:
            cutoff = now - timedelta(hours=1)

        filtered = []
        for pt in ts_data:
            try:
                dt = datetime.fromisoformat(pt['timestamp'])
                if dt >= cutoff:
                    filtered.append(pt)
            except Exception:
                continue

        # Limit rendering to ~100 points
        step = max(1, len(filtered) // 100)
        decimated = filtered[::step]

        labels = []
        for pt in decimated:
            dt = datetime.fromisoformat(pt['timestamp'])
            if timeframe in ['24h', '7d']:
                labels.append(dt.strftime("%d/%m %H:%M"))
            else:
                labels.append(dt.strftime("%H:%M:%S"))

        return jsonify({
            "labels": labels,
            "speed_down": [pt['speed_down'] for pt in decimated],
            "speed_up": [pt['speed_up'] for pt in decimated],
            "active_devices": [pt['active_devices'] for pt in decimated],
            "known_devices": [pt['known_devices'] for pt in decimated]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/set_total')
def api_set_total():
    """Permet de corriger le total cumulé historique."""
    try:
        down_bytes = flask_request.args.get('down', type=int)
        up_bytes = flask_request.args.get('up', type=int)
        down_gb = flask_request.args.get('down_gb', type=float)
        up_gb = flask_request.args.get('up_gb', type=float)
        down_tb = flask_request.args.get('down_tb', type=float)
        up_tb = flask_request.args.get('up_tb', type=float)

        with history_lock:
            history = load_data()
            updated = False

            if down_bytes is not None:
                history['bank_rx'] = down_bytes
                updated = True
            elif down_tb is not None:
                history['bank_rx'] = int(down_tb * (1024**4))
                updated = True
            elif down_gb is not None:
                history['bank_rx'] = int(down_gb * (1024**3))
                updated = True

            if up_bytes is not None:
                history['bank_tx'] = up_bytes
                updated = True
            elif up_tb is not None:
                history['bank_tx'] = int(up_tb * (1024**4))
                updated = True
            elif up_gb is not None:
                history['bank_tx'] = int(up_gb * (1024**3))
                updated = True

            if updated:
                save_data(history)
                return jsonify({
                    "status": "success",
                    "message": "Total historique modifié avec succès.",
                    "new_total": {
                        "down_bytes": history['bank_rx'],
                        "up_bytes": history['bank_tx'],
                        "down_human": human_bytes(history['bank_rx']),
                        "up_human": human_bytes(history['bank_tx'])
                    }
                })

            return jsonify({
                "status": "error",
                "message": "Aucun paramètre valide. Exemples: ?down_tb=2.5&up_tb=0.5"
            }), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/config', methods=['GET'])
def api_get_config():
    """Récupérer la configuration actuelle."""
    config = load_config()
    # Masquer le mot de passe
    safe_config = dict(config)
    if safe_config.get("bbox_password"):
        safe_config["bbox_password"] = "●" * min(len(safe_config["bbox_password"]), 12)
    safe_config["redis_status"] = "connected" if is_redis_alive() else "disconnected"
    safe_config["uptime_days"] = round((datetime.now() - UPTIME_START).total_seconds() / 86400, 1)
    return jsonify(safe_config)

@app.route('/api/config', methods=['POST'])
def api_set_config():
    """Mettre à jour la configuration."""
    try:
        body = flask_request.get_json(force=True)
        config = load_config()

        allowed_keys = ["bbox_password", "bbox_base_url", "monitor_interval",
                        "uptime_start_date", "target_tb", "refresh_interval_ms", "max_chart_points"]

        updated = False
        for key in allowed_keys:
            if key in body and body[key] is not None and body[key] != "":
                config[key] = body[key]
                updated = True

        if not updated:
            return jsonify({"status": "error", "message": "Aucun paramètre fourni."}), 400

        if save_config(config):
            return jsonify({"status": "success", "message": "Configuration sauvegardée."})
        else:
            return jsonify({"status": "error", "message": "Impossible de sauvegarder (Redis indisponible)."}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    login_bbox()
    app.run(host='0.0.0.0', port=int(os.getenv('APP_PORT', '5000')))