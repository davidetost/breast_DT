import csv
import time
import json
import paho.mqtt.client as mqtt

# =====================
# THERAPY PUMP SIMULATOR
# =====================
# Simula una pompa infusionale che segue un piano terapeutico predefinito

class TherapyPump:
    def __init__(self, broker_address="127.0.0.1", port=1883):
        self.broker_address = broker_address
        self.port = port
        self.topic_action = "digitaltwin/breast/action"
        
        self.client = None
        self.therapy_plan = []
        self.injections_sent = 0
        
    def connect(self):
        """Connette il pump al broker MQTT"""
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="TherapyPump")
            self.client.on_connect = self.on_connect
            self.client.on_publish = self.on_publish
            
            print(f"[Pump] Connessione a {self.broker_address}:{self.port}...")
            self.client.connect(self.broker_address, self.port)
            self.client.loop_start()
            
            # Aspetta conferma connessione
            time.sleep(1)
            return True
            
        except Exception as e:
            print(f"[ERROR] Connessione fallita: {e}")
            return False
    
    def on_connect(self, client, userdata, flags, rc, props):
        if rc == 0:
            print("[Pump] ✓ Connesso al broker MQTT")
        else:
            print(f"[Pump] ✗ Connessione fallita con codice: {rc}")
    
    def on_publish(self, client, userdata, mid, rc, props):
        """Callback quando un messaggio viene pubblicato"""
        if rc == 0:
            print(f"[Pump] ✓ Messaggio #{mid} pubblicato con successo")
    
    def load_therapy_plan(self, csv_file="therapypump.csv"):
        """Carica il piano terapeutico dal CSV"""
        try:
            with open(csv_file, "r") as f:
                reader = csv.DictReader(f)
                self.therapy_plan = list(reader)
            
            print(f"\n[Pump] ✓ Piano terapeutico caricato:")
            print(f"  - File: {csv_file}")
            print(f"  - Cicli: {len(self.therapy_plan)}")
            
            # Mostra il piano
            print("\n[Pump] Piano dettagliato:")
            for i, dose in enumerate(self.therapy_plan, 1):
                print(f"  #{i}: T={dose['time_delay']}s → {dose['dosage']}mg (Patient: {dose['patient_id']})")
            
            # Ordina per tempo
            self.therapy_plan.sort(key=lambda x: float(x["time_delay"]))
            
            return True
            
        except FileNotFoundError:
            print(f"[ERROR] File {csv_file} non trovato!")
            print("[Pump] Assicurati che therapypump.csv sia nella stessa cartella dello script.")
            return False
        except Exception as e:
            print(f"[ERROR] Errore lettura CSV: {e}")
            return False
    
    def send_injection(self, patient_id, dosage, cycle_number, total_cycles):
        """Invia un'iniezione via MQTT"""
        if not self.client or not self.client.is_connected():
            print("[ERROR] Client non connesso!")
            return False
        
        payload = {
            "type": "THERAPY_INJECTION",
            "patient_id": str(patient_id),
            "drug_name": "Doxorubicin",
            "dosage": float(dosage),
            "timestamp": time.time(),
            "cycle": cycle_number,
            "total_cycles": total_cycles
        }
        
        try:
            result = self.client.publish(
                self.topic_action, 
                json.dumps(payload), 
                qos=1
            )
            
            self.injections_sent += 1
            return True
            
        except Exception as e:
            print(f"[ERROR] Invio fallito: {e}")
            return False
    
    def execute_therapy_plan(self):
        """Esegue il piano terapeutico con timing reale"""
        if not self.therapy_plan:
            print("[ERROR] Nessun piano terapeutico caricato!")
            return
        
        print("\n" + "="*60)
        print("🚀 AVVIO SIMULAZIONE TERAPIA")
        print("="*60)
        
        start_time = time.time()
        total_cycles = len(self.therapy_plan)
        
        for i, dose in enumerate(self.therapy_plan, 1):
            injection_time = float(dose["time_delay"])
            dosage = float(dose["dosage"])
            patient_id = dose["patient_id"]
            
            # Aspetta il momento giusto
            while (time.time() - start_time) < injection_time:
                elapsed = int(time.time() - start_time)
                remaining = int(injection_time - elapsed)
                print(f"[Pump] ⏳ Prossima iniezione tra {remaining}s (ciclo {i}/{total_cycles})...", end='\r')
                time.sleep(0.5)
            
            # INIEZIONE
            elapsed = time.time() - start_time
            print(f"\n[Pump] 💉 INIEZIONE #{i}/{total_cycles}")
            print(f"  ├─ Tempo: T={elapsed:.1f}s (previsto: {injection_time}s)")
            print(f"  ├─ Dosaggio: {dosage}mg")
            print(f"  ├─ Paziente: {patient_id}")
            print(f"  └─ Farmaco: Doxorubicin")
            
            success = self.send_injection(patient_id, dosage, i, total_cycles)
            
            if success:
                print(f"[Pump] ✓ Iniezione #{i} inviata con successo\n")
            else:
                print(f"[Pump] ✗ Errore nell'invio dell'iniezione #{i}\n")
        
        print("\n" + "="*60)
        print("✓ PIANO TERAPEUTICO COMPLETATO")
        print("="*60)
        print(f"  - Iniezioni totali: {self.injections_sent}/{total_cycles}")
        print(f"  - Durata simulazione: {time.time() - start_time:.1f}s")
        print("="*60 + "\n")
    
    def disconnect(self):
        """Disconnette il pump dal broker"""
        if self.client:
            print("[Pump] Disconnessione in corso...")
            time.sleep(2)  # Aspetta che gli ultimi messaggi vengano inviati
            self.client.loop_stop()
            self.client.disconnect()
            print("[Pump] ✓ Disconnesso\n")


def main():
    # =====================
    # CONFIGURAZIONE
    # =====================
    BROKER = "127.0.0.1"  # Cambia con l'IP della VM se necessario (es. "192.168.0.200")
    PORT = 1883
    CSV_FILE = "therapypump.csv"
    
    print("\n" + "="*60)
    print("💊 THERAPY PUMP SIMULATOR")
    print("="*60)
    print(f"Broker: {BROKER}:{PORT}")
    print(f"Plan File: {CSV_FILE}")
    print("="*60 + "\n")
    
    # =====================
    # INIZIALIZZAZIONE
    # =====================
    pump = TherapyPump(broker_address=BROKER, port=PORT)
    
    # Connetti
    if not pump.connect():
        print("[FATAL] Impossibile connettersi al broker. Uscita.")
        return
    
    # Carica piano
    if not pump.load_therapy_plan(CSV_FILE):
        print("[FATAL] Impossibile caricare il piano terapeutico. Uscita.")
        pump.disconnect()
        return
    
    # Countdown
    print("\n[Pump] ⏱️  Avvio simulazione tra...")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print("  GO!\n")
    
    # =====================
    # ESECUZIONE
    # =====================
    try:
        pump.execute_therapy_plan()
    except KeyboardInterrupt:
        print("\n\n[Pump] ⚠️ Simulazione interrotta dall'utente")
    except Exception as e:
        print(f"\n[ERROR] Errore durante l'esecuzione: {e}")
    finally:
        pump.disconnect()


if __name__ == "__main__":
    main()