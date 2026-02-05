import time
import json
import csv
import random
import os
import paho.mqtt.client as mqtt

# =====================
# CONFIGURAZIONE RETE
# =====================
BROKER = "127.0.0.1"
PORT = 1884  # <--- PORTA DEL PORT FORWARDING

TOPIC_STATUS = "digitaltwin/system/status"
TOPIC_BOOTSTRAP = "digitaltwin/breast/bootstrap"

server_ready = False

# =====================
# LETTURA DATI (Fix ID)
# =====================
def get_patient_data(csv_path="data.csv"):
    """Legge il CSV gestendo 'id' vs 'patient_id'"""
    data = {}
    valid = False
    
    if os.path.exists(csv_path):
        try:
            with open(csv_path, newline='', encoding='utf-8') as f:
                # Usa la virgola come separatore
                reader = csv.DictReader(f, delimiter=',')
                row = next(reader, None)
                
                if row:
                    # FIX: Mappa 'id' in 'patient_id'
                    if "id" in row and "patient_id" not in row:
                        row["patient_id"] = row["id"]
                    
                    # Se ancora non c'è, mettiamo un default per non crashare
                    if "patient_id" not in row:
                        row["patient_id"] = "UNKNOWN"

                    data = row
                    valid = True
                    print(f"[Data] ✅ Letto paziente {data['patient_id']} dal CSV.")
                else:
                    print("[Data] ⚠️ CSV vuoto.")
        except Exception as e:
            print(f"[Data] Errore CSV: {e}")
    
    if not valid:
        print("[Data] 🎲 Uso dati casuali.")
        data = {
            "patient_id": f"PATIENT_{random.randint(100,999)}",
            "radius_mean": 15.0,
            "texture_mean": 10.0
        }
    
    # Conversione sicura a numeri
    try:
        data["radius_mean"] = float(data.get("radius_mean", 15.0))
        data["texture_mean"] = float(data.get("texture_mean", 10.0))
    except:
         data["radius_mean"] = 15.0
         data["texture_mean"] = 10.0
         
    return data

# =====================
# MQTT
# =====================
def on_connect(client, userdata, flags, rc, props):
    if rc == 0:
        print(f"[Client] Connesso al tunnel (Porta {PORT})")
        client.subscribe(TOPIC_STATUS)
        print(f"[Client] In attesa di segnale READY...")
    else:
        print(f"[Client] Errore connessione: {rc}")

def on_message(client, userdata, msg):
    global server_ready
    payload = msg.payload.decode()
    
    is_ready = False
    try:
        if json.loads(payload).get("status") == "READY": is_ready = True
    except:
        if payload == "READY": is_ready = True

    if is_ready and not server_ready:
        print("[Client] ✅ EDGE SERVER PRONTO! Invio dati...")
        server_ready = True

# =====================
# MAIN
# =====================
if __name__ == "__main__":
    patient_data = get_patient_data("data.csv")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="PhysicalTwin_Win")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"❌ ERRORE: {e}")
        exit()

    # Handshake
    start = time.time()
    while not server_ready:
        time.sleep(0.5)
        if time.time() - start > 30:
            print("❌ TIMEOUT: Server non trovato.")
            exit()

    # Invio
    payload = {
        "meta": { "patient_id": patient_data["patient_id"], "timestamp": time.time() },
        "initial_state": {
            "radius_mean": patient_data["radius_mean"],
            "texture_mean": patient_data["texture_mean"]
        }
    }
    client.publish(TOPIC_BOOTSTRAP, json.dumps(payload))
    print(f"[Client] 🚀 Dati inviati per paziente {patient_data['patient_id']}")

    time.sleep(2)
    client.loop_stop()
    client.disconnect()