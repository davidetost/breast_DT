import csv
import time
import json
import paho.mqtt.client as mqtt

# CONFIGURAZIONE
BROKER = "192.168.1.143" # L'IP della tua VM (o localhost se lo lanci da dentro)
PORT = 1883
TOPIC_ACTION = "digitaltwin/breast/action"

def main():
    # 1. Connessione
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="TherapyPump")
    try:
        client.connect(BROKER, PORT)
        client.loop_start()
        print("[Therapy] Pompa infusionale connessa. In attesa del piano terapeutico...")
    except Exception as e:
        print(f"[ERROR] Connessione fallita: {e}")
        return

    # 2. Lettura del Piano Terapeutico
    therapy_plan = []
    try:
        with open("therapy.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                therapy_plan.append(row)
        print(f"[Therapy] Caricati {len(therapy_plan)} cicli di terapia.")
    except FileNotFoundError:
        print("[ERROR] File therapy.csv non trovato!")
        return

    # 3. Esecuzione Simulazione Temporale
    start_time = time.time()
    
    # Ordiniamo per tempo di iniezione per sicurezza
    therapy_plan.sort(key=lambda x: float(x["time_delay"]))

    for dose in therapy_plan:
        injection_time = float(dose["time_delay"])
        amount = float(dose["dosage"])
        
        # Aspetta finché non è il momento giusto
        while (time.time() - start_time) < injection_time:
            time.sleep(0.5)
            print(f"[Therapy] Attesa ciclo... T={int(time.time() - start_time)}s", end='\r')

        # 4. INIEZIONE (Invio MQTT)
        payload = {
            "type": "THERAPY_INJECTION",
            "patient_id": dose["patient_id"],
            "drug_name": "Doxorubicin", # Fisso per ora
            "dosage": amount,
            "timestamp": time.time()
        }
        
        client.publish(TOPIC_ACTION, json.dumps(payload), qos=1)
        print(f"\n[Therapy] 💉 INIEZIONE SOMMINISTRATA: {amount}mg al tempo T={injection_time}")

    print("\n[Therapy] Piano terapeutico completato.")
    time.sleep(5)
    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()