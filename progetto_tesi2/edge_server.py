import time
import json
import threading
import paho.mqtt.client as mqtt  # [MQTT] Importiamo la libreria

# --- MOCK DELLA CLASSE TUMORE (Lo stesso di prima) ---
import random
class PredictiveTumorModel:
    def __init__(self, initial_risk_factor=0.001):
        self.is_healthy = True
        self.radius = 0.0
        self.volume = 0.0
        self.risk_factor = initial_risk_factor
        self.growth_rate = 0.1

    def step(self):
        if self.is_healthy:
            if random.random() < self.risk_factor:
                self.is_healthy = False
                self.radius = 1.0
        else:
            self.radius += self.growth_rate
        return {"healthy": self.is_healthy, "radius": round(self.radius, 2)}
# ---------------------------------------------------------------------------

class EdgeServer:
    def __init__(self, broker_address="localhost", broker_port=1883):
        self.active_session = None
        self.is_running = False
        self.tick_rate = 0.1 # 10 Hz

        # [MQTT] Configurazione del Client
        self.mqtt_client = mqtt.Client(client_id="EdgeServer_Publisher")
        self.broker_address = broker_address
        self.broker_port = broker_port
        self.mqtt_topic = "digitaltwin/breast/tumor"
        
        # [MQTT] Connessione al Broker (non bloccante all'avvio)
        try:
            self.mqtt_client.connect(self.broker_address, self.broker_port)
            self.mqtt_client.loop_start() # Avvia il thread di rete in background
            print(f"[MQTT] Connesso al Broker {self.broker_address}:{self.broker_port}")
        except Exception as e:
            print(f"[MQTT] ERRORE connessione: {e}")

    def initialize_session(self, patient_data):
        print(f"[Server] Ricevuto bootstrap per paziente: {patient_data['meta']['patient_id']}")
        risk_genetic = patient_data['config']['risk_factors']['genetic']
        self.active_session = PredictiveTumorModel(initial_risk_factor=risk_genetic)
        print("[Server] Digital Twin inizializzato e pronto.")
        self.start_simulation()

    def start_simulation(self):
        self.is_running = True
        print(f"[Server] Avvio simulazione a {1/self.tick_rate} Hz...")
        simulation_thread = threading.Thread(target=self._run_loop)
        simulation_thread.start()

    def _run_loop(self):
        while self.is_running:
            start_time = time.time()

            # A. Calcolo del nuovo stato
            current_state = self.active_session.step()

            # B. Output -> [MQTT] Pubblicazione
            # Creiamo il payload JSON da spedire
            payload = json.dumps({
                "timestamp": time.time(),
                "status": current_state
            })
            
            # Pubblichiamo sul topic
            self.mqtt_client.publish(self.mqtt_topic, payload)

            # Log locale (solo per debug)
            if not current_state['healthy']:
                print(f" >> [MQTT] Inviato update: Raggio {current_state['radius']}mm")

            # C. Mantenimento del tempo
            elapsed = time.time() - start_time
            sleep_time = self.tick_rate - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

if __name__ == "__main__":
    # Nota: Assicurati che il Broker sia attivo su localhost (o cambia IP)
    server = EdgeServer()
    
    mock_incoming_data = {
        "meta": {"patient_id": "PAZIENTE_TESI_01"},
        "config": {"risk_factors": {"genetic": 0.05}}
    }
    
    server.initialize_session(mock_incoming_data)
