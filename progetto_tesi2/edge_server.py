import time
import json
import threading
import random
import paho.mqtt.client as mqtt
import math  

# =====================
# MODELLO TUMORALE
# =====================
class TumorModel:
    def __init__(self, initial_radius, initial_cellularity):
        self.radius = float (initial_radius)

        # Gompertz does not support zero cellularity
        if self.radius <0.1: self.radius =0.1
# now alpha parameter will be defined as the growth rate that depends on cellularity, more cellularity means faster growth, it is divided to scale it prperly
        self.alpha= float(initial_cellularity) * 0.005
# another parameter is K, which represents the carrying capacity in mm
        self.k= 30.0
        base_ic50 = 0.2
        resistance_factor= (float(initial_cellularity)/20.0)
        self.ic50 = base_ic50 *max(1.0, 1.0 + resistance_factor)
        
        
        self.drug_efficacy = 0.0
        self.drug_decay = 0.02
        self.emax = 0.9 #maximum drug effect(90% cell kill)

        self.last_update_time = time.time()

    def update(self):
        current_time = time.time()
        dt = current_time - self.last_update_time

        #growth is defined by Gompertz model: dR/dt = alpha * R * ln (K/R)
        if 0< self.radius < self.k:
            growth_rate =self.alpha * self.radius * math.log(self.k / self.radius)
        else:
            growth_rate =0.0

        #drug_effect is the effect of the drug (Hill equation with real parameters), while death is emax *(dose/(IC50 + Dose))* Radius
        if self.drug_efficacy >0:
            drug_effect = self.emax * self.radius * self.drug_efficacy / (self.ic50 + self.drug_efficacy)
            death_rate = drug_effect* self.radius
        else:
            death_rate =0.0 

        #integration 
        delta_radius = (growth_rate - death_rate) * dt
        self.radius += delta_radius

        # drug effect decay
        if self.drug_efficacy > 0:
            self.drug_efficacy -= (self.drug_decay * dt)
            if self.drug_level <0: self.drug_efficacy =0.0

        #physical limits
        self.radius = max(0.1, min(self.radius, self.k))
        self.last_update_time = current_time

        return {
            "radius": round(self.radius, 4),
            "cellularity": round(self.alpha*100, 2),
            "drug_level": round(self.drug_efficacy, 4),
            "status": "growing" if delta_radius > 0 else "shrinking"
        }
    
    def inject_drug(self, amount):
        self.drug_efficacy += float(amount)
        if self.drug_efficacy > 2.0: self.drug_efficacy =2.0


# =====================
# EDGE SERVER
# =====================
class EdgeServer:
    def __init__(self, broker_address="localhost", broker_port=1883):
        self.broker_address = broker_address
        self.broker_port = broker_port

        self.tick_rate = 0.5
        self.is_running = False
        self.patient_id = None
        self.tumors = {}

        self.topic_pub = "digitaltwin/breast/tumor"
        self.topic_bootstrap = "digitaltwin/breast/bootstrap"
        self.topic_status = "digitaltwin/system/status"
        self.topic_action = "digitaltwin/breast/action" 

        self.mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="EdgeServer_Node"
        )
        self.mqtt_client.on_message = self.on_message

        self._connect()

    def _connect(self):
        self.mqtt_client.connect(self.broker_address, self.broker_port)
        self.mqtt_client.subscribe(self.topic_bootstrap)
        self.mqtt_client.loop_start()

        status_payload = {
            "type": "STATUS",
            "status": "READY",
            "timestamp": time.time()
        }
        self.mqtt_client.publish(
            self.topic_status,
            json.dumps(status_payload),
            retain=True
        )
        print("[MQTT] Connesso e inviato stato READY")

    # =====================
    # MQTT CALLBACK
    # =====================
    def on_connect(self, client, userdata,flags, reason_code,properties):

        if reason_code == 0:
            print(f"[MQTT] Successfully connected with code {reason_code}")
            client.subscribe(self.topic_bootstrap)
            client.subscribe(self.topic_action)
            print(f"[MQTT] Subscribed to topic: {self.topic_bootstrap}")

            status_payload = json.dumps({"type": "STATUS", "STATUS": "ready", "timestamp": time.time()})
            client.publish(self.topic_status, status_payload, retain=True)
            print("[MQTT] Published READY status")
        else:
            print(f"[MQTT] Connection failed with code {reason_code}")

        try:
            data = json.loads(msg.payload.decode())
        except Exception as e:
            print(f"[MQTT] JSON non valido: {e}")
            return
    def on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode()
            data = json.loads(payload_str)
        except Exception as e:
            print(f"[MQTT] JSON not valid: {e}")
            return
        if msg.topic == self.topic_bootstrap:
            if self.is_running:
                print("[Server] Bootstrap ignored: simulation already running")
                return

            if "initial_state"in data or data.get("type") != "BOOTSTRAP":
                print("[Server] Invalid BOOTSTRAP message")
                self.initialize_session(data)
            else:
                print("[Server] Invalid BOOTSTRAP message")
            
        if msg.topic == self.topic_action:
            print("[Server] Received action message, Drug injection...")
            if "left" in self.tumors: self.tumors["left"].inject_drug()
            if "right" in self.tumors: self.tumors["right"].inject_drug()


                

    # =====================
    # BOOTSTRAP
    # =====================
    def initialize_session(self, data):

        meta =data.get("meta", {})
        self.patient_id = meta.get("patient_id", "Unknown_patient")

        print(f"\n[Server] 📩 BOOTSTRAP per paziente {self.patient_id}")

        state = data.get("initial_state", {})

        r_left =state.get("left_tumor_radius", 0.5)
        c_left =state.get("left_tumor_cellularity", 10.0)

        r_right =state.get("right_tumor_radius", 0.5)
        c_right =state.get("right_tumor_cellularity", 10.0)

        print (f"[Server] Initializating tumors:")
        print (f"         Left  - Radius: {r_left} cm, Cellularity: {c_left} ")
        print (f"         Right - Radius: {r_right} cm, Cellularity: {c_right} ")
        
        self.tumors = {
            "left": TumorModel(r_left, c_left),
            "right": TumorModel(r_right, c_right)
        }
        self.start_simulation()

    # =====================
    # SIMULATION LOOP
    # =====================
    def start_simulation(self):
        self.is_running = True
        print("[Server] 🚀 Simulazione avviata")
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        while self.is_running:
            start = time.time()

            left = self.tumors["left"].update()
            right = self.tumors["right"].update()

            payload = {
                "type": "TUMOR_STATE",
                "meta": {
                    "patient_id": self.patient_id,
                    "source": "edge_server"
                },
                "timestamp": time.time(),
                "tumors": {
                    "left": left,
                    "right": right
                }
            }

            self.mqtt_client.publish(
                self.topic_pub,
                json.dumps(payload),
                qos=1
            )

            if random.random() < 0.05:
                print(f">> [SIM] L={left['radius']} | R={right['radius']}")

            dt = time.time() - start
            sleep = self.tick_rate - dt
            if sleep > 0:
                time.sleep(sleep)


# =====================
# ENTRY POINT
# =====================
if __name__ == "__main__":
    server = EdgeServer("127.0.0.1")
    print("[Main] Server attivo. In attesa di Physical Twin...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stop.")
