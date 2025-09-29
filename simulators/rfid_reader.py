
import os, time, json, random, datetime
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST","localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT","1883"))

tags = ["E200341201", "E200341202", "E200341203", "E200341204"]
gates = ["ENTRADA_A", "SAIDA_A", "ENTRADA_B"]

def loop():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="rfid_reader_sim")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    while True:
        tag = random.choice(tags)
        gate = random.choice(gates)
        payload = {
            "tag": tag,
            "gate": gate,
            "rssi": round(random.uniform(-70,-30),1),
            "ts": datetime.datetime.utcnow().isoformat()+"Z"
        }
        client.publish("mottu/rfid/read", json.dumps(payload), qos=1)
        time.sleep(0.7)
