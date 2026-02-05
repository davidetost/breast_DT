import time
import json
import threading
import math
import paho.mqtt.client as mqtt

# =====================
# MODELLO TUMORALE (Gompertz)
# =====================
class TumorModel:
    def __init__(self, initial_radius, initial_cellularity):
        self.radius = float(initial_radius)
        if self.radius < 0.1: self.radius = 0.1
        
        # Parametri Gompertz
        self.alpha = float(initial_cellularity) * 0.005
        self.k = 30.0 # Capacità portante
        
        # Resistenza e Farmaco
        base_ic50 = 0.2
        resistance_factor = (float(initial_cellularity) / 20.0)
        self.ic50 = base_ic50 * max(1.0, 1.0 + resistance_factor)
        
        self.drug_efficacy = 0.0
        self.drug_decay = 0.02
        self.emax = 0.9 

        self.last_update_time = time.time()

    def update(self):
        current_time = time.time()
        dt = current_time - self.last_update_time

        # Crescita Gompertziana
        if 0 < self.radius < self.k:
            growth_rate = self.alpha * self.radius * math.log(self.k / self.radius)
        else:
            growth_rate = 0.0

        # Effetto Farmaco (Emax model)
        death_rate = 0.0
        if self.drug_efficacy > 0:
            drug_effect = self.emax * self.radius * self.drug_efficacy / (self.ic50 + self.drug_efficacy)
            death_rate = drug_effect * self.radius

        # Integrazione (Eulero)
        delta_radius = (growth_rate - death_rate) * dt
        self.radius += delta_radius

        # Decadimento farmaco
        if self.drug_efficacy > 0:
            self.drug_efficacy -= (self.drug_decay * dt)
            if self.drug_efficacy < 0: self.drug_efficacy = 0.0

        # Limiti fisici
        self.radius = max(0.1, min(self.radius, self.k))
        self.last_update_time = current_time

        return {
            "radius": round(self.radius, 4),
            "cellularity": round(self.alpha * 100, 2),
            "drug_level": round(self.drug_efficacy, 4),
            "status": "growing" if (growth_rate > death_rate) else "shrinking"
        }
    
    def inject_drug(self, amount):
        self.drug_efficacy += float(amount)
        if self.drug_efficacy > 2.0: self.drug_efficacy = 2.0

# =====================
# EDGE SERVER MQTT
# =====================
class EdgeServer:
    def __init__(self):
        self.broker_address = "127.0.0.1" # Interno alla VM
        self.port = 1883
        
        self.tumors = {}
        self.simulation_running = False
        self.patient_id = "Waiting..."

        # Topics
        self.topic_status = "digitaltwin/system/status"
        self.topic_bootstrap = "digitaltwin/breast/bootstrap"
        self.topic_pub = "digitaltwin/breast/tumor"
        self.topic_action = "digitaltwin/breast/action"

        # Client Setup
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="EdgeServer_Node")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def start(self):
        print(f"[Server] Avvio connessione a {self.broker_address}:{self.port}...")
        try:
            self.client.connect(self.broker_address, self.port)
            self.client.loop_start()
            
            # --- LOOP DI ATTESA (Handshake) ---
            print("[Server] In attesa di connessione dal Physical Twin...")
            while not self.simulation_running:
                # Invia READY ogni 2 secondi finché non riceve il Bootstrap
                payload = json.dumps({"status": "READY", "timestamp": time.time()})
                self.client.publish(self.topic_status, payload)
                print(f"[Server] 📡 Invio segnale READY... (in attesa dati)", end='\r')
                time.sleep(2.0)
            
            # --- SIMULAZIONE AVVIATA ---
            print(f"\n[Server] 🚀 Simulazione avviata per {self.patient_id}!")
            self.run_simulation_loop()

        except Exception as e:
            print(f"[Server] Errore critico: {e}")

    def run_simulation_loop(self):
        while True:
            left_data = self.tumors["left"].update()
            right_data = self.tumors["right"].update()

            payload = {
                "type": "TUMOR_STATE",
                "meta": { "patient_id": self.patient_id },
                "timestamp": time.time(),
                "tumors": { "left": left_data, "right": right_data }
            }
            
            self.client.publish(self.topic_pub, json.dumps(payload))
            
            # Log visuale
            icon = "🟢" if left_data["status"] == "shrinking" else "🔴"
            print(f"[SIM] {icon} L: {left_data['radius']:.3f} | R: {right_data['radius']:.3f}")
            
            time.sleep(1.0) # Tick rate

    def on_connect(self, client, userdata, flags, rc, props):
        if rc == 0:
            print(f"\n[Server] Connesso a Mosquitto!")
            client.subscribe(self.topic_bootstrap)
            client.subscribe(self.topic_action)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            
            # 1. RICEZIONE BOOTSTRAP
            if msg.topic == self.topic_bootstrap:
                print(f"\n[Server] 📩 BOOTSTRAP RICEVUTO!")
                self.initialize_tumors(payload)
                self.simulation_running = True # Sblocca il loop principale

            # 2. RICEZIONE AZIONE (Farmaco)
            elif msg.topic == self.topic_action:
                amount = float(payload.get("amount", 0.5))
                print(f"[Server] 💉 Iniezione ricevuta: {amount}mg")
                if "left" in self.tumors: self.tumors["left"].inject_drug(amount)
                if "right" in self.tumors: self.tumors["right"].inject_drug(amount)

        except Exception as e:
            print(f"[Server] Errore processamento messaggio: {e}")

    def initialize_tumors(self, data):
        self.patient_id = data.get("meta", {}).get("patient_id", "Unknown")
        # Supporto struttura nidificata o piatta
        state = data.get("initial_state", data)
        
        r = float(state.get("radius_mean", state.get("left_tumor_radius", 15.0)))
        c = float(state.get("texture_mean", state.get("left_tumor_cellularity", 10.0)))
        
        self.tumors = {
            "left": TumorModel(r, c),
            "right": TumorModel(r * 1.1, c * 1.2) # Leggera asimmetria
        }

if __name__ == "__main__":
    server = EdgeServer()
    server.start()