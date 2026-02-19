import time
import os
import math
import json
import paho.mqtt.client as mqtt

# ═══════════════════════════════════════════════════════════════════
# TUMOR MODEL
# ═══════════════════════════════════════════════════════════════════
class TumorModel:
    def __init__(self, r, c):
        self.radius = max(0.1, float(r))
        self.alpha  = float(c) * 0.005
        self.k      = 30.0
        self.drug_efficacy = 0.0
        self.drug_decay    = 0.02
        self.emax          = 0.05
        self.ic50          = 0.2 * max(1.0, 1.0 + float(c) / 20.0)
        self.last_update   = time.time()

    def update(self):
        now = time.time()
        dt  = min(now - self.last_update, 2.0)
        self.last_update = now

        growth = (self.alpha * self.radius * math.log(self.k / self.radius)
                  if 0 < self.radius < self.k else 0.0)
        death  = 0.0
        if self.drug_efficacy > 0:
            death = (self.emax * self.radius * self.drug_efficacy
                     / (self.ic50 + self.drug_efficacy)) * self.radius

        self.radius = max(0.1, min(self.radius + (growth - death) * dt, self.k))
        if self.drug_efficacy > 0:
            self.drug_efficacy = max(0.0, self.drug_efficacy - self.drug_decay * dt)

        return {
            "radius":      round(self.radius, 4),
            "cellularity": round(self.alpha * 100, 2),
            "drug_level":  round(self.drug_efficacy, 4),
            "status":      "growing" if growth > death else "shrinking"
        }

    def inject_drug(self, amount):
        self.drug_efficacy = min(2.0, self.drug_efficacy + float(amount))

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
BROKER      = os.getenv("BROKER_ADDRESS", "mosquitto")
PORT        = int(os.getenv("BROKER_PORT", 1883))
T_BOOTSTRAP = "digitaltwin/breast/bootstrap"
T_PUB       = "digitaltwin/breast/tumor"
T_ACTION    = "digitaltwin/breast/action"
PUBLISH_HZ  = float(os.getenv("PUBLISH_HZ", 0.5))

left  = TumorModel(15.0, 10.0)
right = TumorModel(16.5, 12.0)
bootstrapped = False

# ═══════════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════════
def on_connect(client, userdata, flags, rc, props=None):
    ok = (rc == 0 or str(rc) == "ReasonCode.SUCCESS")
    print(f"[MQTT-SERVER] {'✓ Connected' if ok else f'✗ rc={rc}'}")
    if ok:
        client.subscribe(T_BOOTSTRAP)
        client.subscribe(T_ACTION)

def on_message(client, userdata, msg):
    global left, right, bootstrapped
    try:
        payload = json.loads(msg.payload.decode())

        if msg.topic == T_BOOTSTRAP:
            data = payload.get("initial_state", payload)
            r_l  = float(data.get("left_radius",      data.get("left_tumor_radius",       15.0)))
            c_l  = float(data.get("left_cellularity",  data.get("left_tumor_cellularity",  10.0)))
            r_r  = float(data.get("right_radius",     data.get("right_tumor_radius",       16.5)))
            c_r  = float(data.get("right_cellularity", data.get("right_tumor_cellularity", 12.0)))
            p_id = payload.get("patient_id", "Unknown")

            left  = TumorModel(r_l, c_l)
            right = TumorModel(r_r, c_r)
            bootstrapped = True

            print(f"\n{'='*50}")
            print(f"[MQTT-SERVER] 🏁 Bootstrap — Patient: {p_id}")
            print(f"  Left : R={r_l:.2f}mm, C={c_l:.2f}%")
            print(f"  Right: R={r_r:.2f}mm, C={c_r:.2f}%")
            print(f"{'='*50}\n")

        elif msg.topic == T_ACTION:
            amount = float(payload.get("amount", payload.get("dosage", 0)))
            left.inject_drug(amount)
            right.inject_drug(amount)
            print(f"[MQTT-SERVER] 💉 Therapy: {amount}mg")

    except Exception as e:
        print(f"[MQTT-SERVER] on_message error: {e}")

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="MqttServer")
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"\n{'='*50}")
    print(f"🔵  MQTT SERVER")
    print(f"    Broker : {BROKER}:{PORT}")
    print(f"    Topic  : {T_PUB}")
    print(f"    Rate   : {PUBLISH_HZ} msg/s")
    print(f"{'='*50}\n")

    client.connect(BROKER, PORT, 60)
    client.loop_start()

    interval = 1.0 / PUBLISH_HZ

    while True:
        l_data = left.update()
        r_data = right.update()

        payload = {
            "type":      "TUMOR_STATE",
            "timestamp": time.time(),
            "tumors":    {"left": l_data, "right": r_data}
        }
        client.publish(T_PUB, json.dumps(payload))

        flag = "🏃" if bootstrapped else "⏳"
        print(f"[MQTT] {flag} L:{l_data['radius']:.4f}mm ({l_data['status']}) "
              f"| R:{r_data['radius']:.4f}mm ({r_data['status']})")

        time.sleep(interval)

if __name__ == "__main__":
    main()
