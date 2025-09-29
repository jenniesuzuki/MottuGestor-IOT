import asyncio
import os, json, time, threading, queue, datetime, base64, requests
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import paho.mqtt.client as mqtt
from sqlalchemy import create_engine, text
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import numpy as np
import cv2
import traceback
YOLO = None

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DB_URL = os.getenv("DB_URL", "sqlite:///./mottu.db")
INFERENCE_URL = os.getenv("INFERENCE_URL", "http://roboflow:9001")
ROBOFLOW_MODEL = os.getenv("ROBOFLOW_MODEL", "workspace/project/1")
VISION_MODE = os.getenv("VISION_MODE", "roboflow")  # "local" | "roboflow"
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "yolov8n.pt")  # baixado automaticamente no 1º uso

app = FastAPI(title="Mottu Gestor IoT+CV API", version="1.1")
# serve todos os arquivos da pasta /app (onde está o index.html copiado no Dockerfile)
app.mount("/static", StaticFiles(directory="."), name="static")

# opcional: rota explícita para "/" (garante servir o index mesmo se o mount mudar)
@app.get("/")
def root():
    return FileResponse("index.html")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {}, pool_pre_ping=True)

def init_db():
    with engine.begin() as conn:
        if DB_URL.startswith("sqlite"):
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.execute(text("PRAGMA synchronous=NORMAL;"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS rfid_reads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_client TEXT NOT NULL,
            ts_server TEXT NOT NULL,
            tag TEXT NOT NULL,
            gate TEXT NOT NULL,
            rssi REAL,
            latency_ms INTEGER
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS zone_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_client TEXT NOT NULL,
            ts_server TEXT NOT NULL,
            zone TEXT NOT NULL,
            count INTEGER,
            latency_ms INTEGER
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tamper_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_client TEXT NOT NULL,
            ts_server TEXT NOT NULL,
            device TEXT NOT NULL,
            state TEXT NOT NULL,
            latency_ms INTEGER
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_server TEXT NOT NULL,
            device TEXT NOT NULL,
            cmd TEXT NOT NULL
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vision_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_client TEXT NOT NULL,
            ts_server TEXT NOT NULL,
            cls TEXT NOT NULL,
            confidence REAL,
            x REAL, y REAL, w REAL, h REAL,
            track_id TEXT,
            latency_ms INTEGER
        );
        """))

init_db()

# Carrega YOLO somente se for modo local
if VISION_MODE.lower() == "local":
    from ultralytics import YOLO as _YOLO
    YOLO = _YOLO(LOCAL_MODEL)

event_queue: "queue.Queue[str]" = queue.Queue()

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe("mottu/rfid/read")
    client.subscribe("mottu/zone/heartbeat")
    client.subscribe("mottu/tamper")
    client.subscribe("mottu/vision/detections")
    print("MQTT connected and subscribed.")

def on_message(client, userdata, msg):
    ts_server = now_iso()
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        payload = {"raw": msg.payload.decode(errors="ignore")}
    tsc = payload.get("ts", ts_server)

    try:
        latency_ms = int((datetime.datetime.fromisoformat(tsc.replace("Z","")) - datetime.datetime.fromisoformat(ts_server.replace("Z",""))).total_seconds()*-1000)
    except Exception:
        latency_ms = None

    with engine.begin() as conn:
        if msg.topic == "mottu/rfid/read":
            conn.execute(text("INSERT INTO rfid_reads (ts_client, ts_server, tag, gate, rssi, latency_ms) VALUES (:a,:b,:c,:d,:e,:f)"),
                         {"a": tsc, "b": ts_server, "c": payload.get("tag"), "d": payload.get("gate"), "e": payload.get("rssi"), "f": latency_ms})
        elif msg.topic == "mottu/zone/heartbeat":
            conn.execute(text("INSERT INTO zone_status (ts_client, ts_server, zone, count, latency_ms) VALUES (:a,:b,:c,:d,:e)"),
                         {"a": tsc, "b": ts_server, "c": payload.get("zone"), "d": payload.get("count"), "e": latency_ms})
        elif msg.topic == "mottu/tamper":
            conn.execute(text("INSERT INTO tamper_events (ts_client, ts_server, device, state, latency_ms) VALUES (:a,:b,:c,:d,:e)"),
                         {"a": tsc, "b": ts_server, "c": payload.get("device"), "d": payload.get("state"), "e": latency_ms})
        elif msg.topic == "mottu/vision/detections":
            preds = payload.get("predictions", []) or []
            for p in preds:
                conn.execute(text("""
                    INSERT INTO vision_events (ts_client, ts_server, cls, confidence, x, y, w, h, track_id, latency_ms)
                    VALUES (:a,:b,:c,:d,:e,:f,:g,:h,:i,:j)
                """), {
                    "a": tsc, "b": ts_server, "c": p.get("class"), "d": p.get("confidence"),
                    "e": p.get("x"), "f": p.get("y"), "g": p.get("width"), "h": p.get("height"),
                    "i": p.get("track_id"), "j": latency_ms
                })

    event = {"topic": msg.topic, "payload": payload, "ts_server": ts_server, "latency_ms": latency_ms}
    event_queue.put(json.dumps(event))

mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.connect(MQTT_HOST, MQTT_PORT, 60)

threading.Thread(target=mqttc.loop_forever, daemon=True).start()

@app.get("/events")
async def sse_events():
    async def event_generator():
        while True:
            data = await asyncio.to_thread(event_queue.get)
            yield {"event": "update", "data": data}
    return EventSourceResponse(event_generator())

@app.get("/metrics")
def metrics():
    with engine.begin() as conn:
        r1 = conn.execute(text("SELECT COUNT(*) FROM rfid_reads")).scalar()
        r2 = conn.execute(text("SELECT COUNT(*) FROM zone_status")).scalar()
        r3 = conn.execute(text("SELECT COUNT(*) FROM tamper_events")).scalar()
        r4 = conn.execute(text("SELECT COUNT(*) FROM vision_events")).scalar()
        lat = conn.execute(text("SELECT AVG(latency_ms) FROM (SELECT latency_ms FROM rfid_reads UNION ALL SELECT latency_ms FROM zone_status UNION ALL SELECT latency_ms FROM tamper_events UNION ALL SELECT latency_ms FROM vision_events)")).scalar()
    return {"rfid_reads": r1, "zone_updates": r2, "tampers": r3, "vision": r4, "avg_latency_ms": lat}

@app.get("/report/location")
def report_location():
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT tag, gate, MAX(ts_server) as last_seen
            FROM rfid_reads
            GROUP BY tag, gate
            ORDER BY last_seen DESC
        """)).mappings().all()
    return {"last_locations": list(rows)}

@app.post("/command/{device}/{cmd}")
def send_command(device: str, cmd: str):
    ts_server = now_iso()
    mqttc.publish("mottu/actuator/cmd", json.dumps({"device": device, "cmd": cmd, "ts": ts_server}), qos=1)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO commands (ts_server, device, cmd) VALUES (:a,:b,:c)"),
                     {"a": ts_server, "b": device, "c": cmd})
    return {"status": "sent", "device": device, "cmd": cmd, "ts": ts_server}

@app.post("/vision/detect")
async def vision_detect(file: UploadFile = File(...), confidence: float = 0.35):
    img_bytes = await file.read()
    ts_now = now_iso()

    try:
        if VISION_MODE.lower() == "local":
            if YOLO is None:
                raise RuntimeError("YOLO model not loaded. Set VISION_MODE=local and rebuild the API image.")

            arr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("Failed to decode image bytes (cv2.imdecode returned None).")

            results = YOLO.predict(source=frame, conf=confidence, verbose=False)
            preds_out = []
            for r in results:
                names = r.names
                for b in r.boxes:
                    cls_id = int(b.cls[0].item())
                    cls = names.get(cls_id, str(cls_id))
                    conf = float(b.conf[0].item())
                    x1, y1, x2, y2 = map(lambda t: float(t.item()), b.xyxy[0])
                    w, h = x2 - x1, y2 - y1
                    preds_out.append({
                        "class": cls,
                        "confidence": conf,
                        "x": x1 + w/2,
                        "y": y1 + h/2,
                        "width": w,
                        "height": h
                    })
            det = {"time": ts_now, "predictions": preds_out}

        else:
            b64 = base64.b64encode(img_bytes).decode()
            payload = {"model": ROBOFLOW_MODEL, "image": b64, "confidence": confidence}
            r = requests.post(f"{INFERENCE_URL}/infer", json=payload, timeout=60)
            r.raise_for_status()
            raw = r.json()
            preds = (raw.get("predictions")
                     or raw.get("preds")
                     or (raw.get("data") or {}).get("predictions")
                     or [])
            det = {"time": raw.get("time", ts_now), "predictions": preds}

        pub = {"ts": det.get("time", ts_now), "predictions": det.get("predictions", [])}
        mqttc.publish("mottu/vision/detections", json.dumps(pub), qos=1)
        print(f"[vision_detect] OK — {len(pub['predictions'])} preds, conf>={confidence}")
        return det

    except Exception as e:
        print("[vision_detect] ERROR:", repr(e))
        traceback.print_exc()
        return {"error": str(e), "trace": traceback.format_exc()}, 500