
import os, time, json, random, datetime
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST","localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT","1883"))

def on_msg(client, userdata, msg):
    print("Actuator command received:", msg.payload.decode())

def loop():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tamper_sensor_sim")
    client.on_message = on_msg
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.subscribe("mottu/actuator/cmd")
    client.loop_start()
    states = ["OK","OPENED","VIBRATION","CUT"]
    while True:
        payload = {
            "device": "locker-01",
            "state": random.choice(states),
            "ts": datetime.datetime.utcnow().isoformat()+"Z"
        }
        client.publish("mottu/tamper", json.dumps(payload), qos=1)
        time.sleep(5)
