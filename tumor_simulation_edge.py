import time
import json
import numpy as np
import threading

# --- Parametri del Modello Matematico (ispirati al paper MRI-based [cite: 16641, 17197]) ---
# Equazione semplificata per la tesi: dN/dt = k*N*(1 - N/theta) - lambda*N
class TumorModel:
    def __init__(self, initial_radius, initial_cellularity):
        self.radius = initial_radius      # Raggio del tumore (cm o mm)
        self.cellularity = initial_cellularity # Densità cellulare (N)
        
        # Parametri biologici
        self.proliferation_rate = 0.05    # k: Tasso di crescita naturale
        self.carrying_capacity = 100.0    # theta: Dimensione massima sostenibile
        self.drug_efficacy = 0.0          # lambda: Inizialmente 0 (nessun farmaco)
        self.drug_decay = 0.01            # beta: Quanto velocemente il farmaco svanisce
        
        self.last_update_time = time.time()

    def update(self):
        """Calcola il prossimo stato del tumore (Step 2 & 3)"""
        current_time = time.time()
        dt = current_time - self.last_update_time
        
        # 1. Calcolo Crescita Logistica (Progressione)
        # Formula: Crescita = k * N * (1 - N/theta)
        growth_term = self.proliferation_rate * self.cellularity * (1 - (self.cellularity / self.carrying_capacity))
        
        # 2. Calcolo Effetto Farmaco (Guarigione)
        # Formula: Morte = alpha * C(t) * N -> Semplificato in drug_efficacy * N
        death_term = self.drug_efficacy * self.cellularity
        
        # Aggiornamento Densità
        delta_cellularity = (growth_term - death_term) * dt
        self.cellularity += delta_cellularity
        
        # Il raggio cambia in funzione della massa cellulare (semplificazione geometrica)
        # Se la cellularità aumenta, il raggio aumenta
        self.radius += (delta_cellularity * 0.1) 
        
        # 3. Decadimento del farmaco nel tempo (Farmacocinetica)
        if self.drug_efficacy > 0:
            self.drug_efficacy -= (self.drug_decay * self.drug_efficacy * dt)
            if self.drug_efficacy < 0: self.drug_efficacy = 0

        self.last_update_time = current_time
        
        # Clamping per evitare valori negativi
        self.radius = max(0.0, self.radius)
        self.cellularity = max(0.0, self.cellularity)

        return {
            "radius": round(self.radius, 4),
            "cellularity": round(self.cellularity, 4),
            "drug_level": round(self.drug_efficacy, 4),
            "status": "growing" if delta_cellularity > 0 else "healing"
        }

    def inject_drug(self, efficacy):
        """Simula l'arrivo del farmaco (Passo 3)"""
        print(f"💉 FARMACO RILEVATO! Efficacia: {efficacy}")
        self.drug_efficacy += efficacy # Accumulo o set, dipende dal modello

# --- Gestione Input Dati (Dal tuo CSV) ---
# Qui userai il tuo 'BioSender' per inviare i dati iniziali a questo script
# Questo script agirà da SERVER per la simulazione e CLIENT verso Unity

def simulation_loop(protocol_sender_func):
    # Inizializziamo il tumore con dati medi dal tuo CSV (es. radius_mean ~17)
    # - Usiamo i dati del dataset per l'init
    tumor = TumorModel(initial_radius=17.0, initial_cellularity=50.0)
    
    print("🚀 Avvio Simulazione Edge...")
    
    try:
        while True:
            # 1. Calcola la fisica
            data = tumor.update()
            
            # 2. Prepara payload per Unity
            payload = json.dumps({
                "type": "sim_update",
                "data": data,
                "timestamp": time.time()
            })
            
            # 3. Invia a Unity (usando la funzione passata come argomento)
            protocol_sender_func(payload)
            
            # Simuliamo a 10Hz (real-time fluido)
            time.sleep(0.1)
            
            # SIMULAZIONE INTERAZIONE: Dopo 10 secondi, iniettiamo il farmaco
            # Nella tesi reale, questo arriverà via MQTT dal "Drug Twin"
            if 10.0 < time.time() % 20.0 < 10.2 and tumor.drug_efficacy < 0.1:
                tumor.inject_drug(2.0) # Efficacia alta per vedere l'effetto
                
    except KeyboardInterrupt:
        print("Stop Simulazione.")

# Esempio di integrazione con il tuo codice MQTT esistente
import paho.mqtt.client as mqtt

def run_mqtt_edge():
    client = mqtt.Client("Edge_Simulator")
    client.connect("broker.hivemq.com", 1883, 60)
    client.loop_start()
    
    # Funzione wrapper per inviare
    def send_wrapper(payload):
        client.publish("digitaltwin/breast/simulation", payload)
        
    simulation_loop(send_wrapper)

if __name__ == "__main__":
    run_mqtt_edge()