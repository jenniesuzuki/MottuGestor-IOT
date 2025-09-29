
import os, time, json, random, datetime
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST","localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT","1883"))

zones = ["Z-A1","Z-A2","Z-B1","Z-C3"]

def loop():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="zone_beacon_sim")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    while True:
        zone = random.choice(zones)
        count = random.randint(0, 25)
        payload = {
            "zone": zone,
            "count": count,
            "ts": datetime.datetime.utcnow().isoformat()+"Z"
        }
        client.publish("mottu/zone/heartbeat", json.dumps(payload), qos=0)
        time.sleep(1.5)
