import time
import json
import threading
import paho.mqtt.client as mqtt
import random

# --- 1. MODELLO MATEMATICO PIÙ REALISTICO ---
class TumorModel:
    def __init__(self, initial_radius, initial_cellularity):
        self.radius = initial_radius
        self.cellularity = initial_cellularity
        
        # PARAMETRI RALLENTATI E VARIABILI
        # Prima era 0.05, ora 0.01 (molto più lento)
        self.base_proliferation_rate = 0.01    
        self.carrying_capacity = 100.0    
        self.drug_efficacy = 0.0          
        self.drug_decay = 0.005 # Decadimento farmaco più lento
        
        self.last_update_time = time.time()

    def update(self):
        current_time = time.time()
        dt = current_time - self.last_update_time
        
        # FATTORE RANDOMICO (CAOS BIOLOGICO)
        # La crescita varia del +/- 20% ogni volta per non sembrare robotica
        random_flux = random.uniform(0.8, 1.2)
        
        # 1. Crescita (Logistica) con random
        growth_term = (self.base_proliferation_rate * random_flux) * self.cellularity * (1 - (self.cellularity / self.carrying_capacity))
        
        # 2. Effetto Farmaco
        death_term = self.drug_efficacy * self.cellularity
        
        delta_cellularity = (growth_term - death_term) * dt
        self.cellularity += delta_cellularity
        
        # Il raggio cresce molto più lentamente rispetto alla cellularità
        self.radius += (delta_cellularity * 0.05) 
        
        # 3. Decadimento farmaco
        if self.drug_efficacy > 0:
            self.drug_efficacy -= (self.drug_decay * self.drug_efficacy * dt)
            if self.drug_efficacy < 0: self.drug_efficacy = 0

        self.last_update_time = current_time
        self.radius = max(0.0, self.radius)
        self.cellularity = max(0.0, self.cellularity)

        return {
            "radius": round(self.radius, 4),
            "cellularity": round(self.cellularity, 4),
            "drug_level": round(self.drug_efficacy, 4),
            "status": "growing" if delta_cellularity > 0 else "healing"
        }

# --- SERVER EDGE ---
class EdgeServer:
    def __init__(self, broker_address="localhost", broker_port=1883):
        self.is_running = False
        self.tick_rate = 0.1 

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="EdgeServer_Node")
        self.broker_address = broker_address
        self.broker_port = broker_port
        
        self.topic_pub = "digitaltwin/breast/tumor"
        self.topic_sub = "digitaltwin/breast/bootstrap"
        self.topic_status = "digitaltwin/system/status" # NUOVO TOPIC DI STATO
        
        self.mqtt_client.on_message = self.on_message

        try:
            self.mqtt_client.connect(self.broker_address, self.broker_port)
            self.mqtt_client.subscribe(self.topic_sub)
            self.mqtt_client.loop_start()
            
            # --- NOTIFICA DI DISPONIBILITÀ (HANDSHAKE) ---
            # retain=True significa: "tieni questo messaggio in memoria per chi arriva dopo"
            self.mqtt_client.publish(self.topic_status, "READY", retain=True)
            print(f"[MQTT] Connesso e inviato stato READY.")
            
        except Exception as e:
            print(f"[MQTT] ERRORE: {e}")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload_str = msg.payload.decode()
            data = json.loads(payload_str)
            
            if topic == self.topic_sub:
                if not self.is_running:
                    print(f"\n[Server] 📩 BOOTSTRAP RICEVUTO! Configurazione in corso...")
                    self.initialize_session(data)
                else:
                    print("[Server] Ignorato bootstrap (simulazione già attiva).")
        except Exception as e:
            print(f"[MQTT] Errore parsing: {e}")

    def initialize_session(self, patient_data):
        print(f"[Server] Paziente: {patient_data['meta']['patient_id']}")
        # Inizializza due tumori con parametri leggermente diversi
        self.tumors = {
            "left": TumorModel(initial_radius=0.5, initial_cellularity=10.0),
            "right": TumorModel(initial_radius=0.7, initial_cellularity=20.0) 
        }
        self.start_simulation()

    def start_simulation(self):
        self.is_running = True
        print(f"[Server] 🚀 Simulazione avviata.")
        simulation_thread = threading.Thread(target=self._run_loop)
        simulation_thread.start()

    def _run_loop(self):
        while self.is_running:
            start_time = time.time()
            
            status_left = self.tumors["left"].update()
            status_right = self.tumors["right"].update()

            payload = json.dumps({
                "timestamp": time.time(),
                "tumors": { "left": status_left, "right": status_right }
            })
            
            self.mqtt_client.publish(self.topic_pub, payload)
            
            # Debug ogni tanto
            if random.random() < 0.05:
                print(f">> [SIM] L: {status_left['radius']} | R: {status_right['radius']}")

            elapsed = time.time() - start_time
            sleep_time = self.tick_rate - elapsed
            if sleep_time > 0: time.sleep(sleep_time)

if __name__ == "__main__":
    server = EdgeServer()
    print("[Main] Server attivo. In attesa di Physical Twin...")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("Stop.")