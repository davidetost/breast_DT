import time
import json
import random
import paho.mqtt.client as mqtt

# Variabile per coordinare l'invio
server_is_ready = False

def on_connect(client, userdata, flags, rc):
    print(f"[Mondo Fisico] Connesso al Broker (Code: {rc})")
    # Ci iscriviamo al canale di stato per sapere quando l'Edge è vivo
    client.subscribe("digitaltwin/system/status")

def on_message(client, userdata, msg):
    global server_is_ready
    payload = msg.payload.decode()
    if msg.topic == "digitaltwin/system/status" and payload == "READY":
        print("[Mondo Fisico] ✅ Rilevato segnale: EDGE SERVER PRONTO!")
        server_is_ready = True

# --- GENERAZIONE DATI ---
def get_patient_data(patient_id):
    radius = round(random.uniform(10.0, 16.0), 2)
    return {
        "meta": { "timestamp": time.time(), "patient_id": patient_id },
        "config": { "risk_factors": { "genetic": 0.05 } }
    }

if __name__ == "__main__":
    BROKER = "127.0.0.1"
    PORT = 1883

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "PhysicalTwin_Sender")
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start() # Avvia il thread di ascolto
        
        print("[Mondo Fisico] In attesa del segnale 'READY' dall'Edge Server...")
        
        # CICLO DI ATTESA (HANDSHAKE)
        timeout = 0
        while not server_is_ready:
            time.sleep(1)
            timeout += 1
            if timeout % 5 == 0:
                print(f"... in attesa ({timeout}s) ...")
            if timeout > 30:
                print("❌ TIMEOUT: L'Edge Server non risponde. È acceso?")
                exit()

        # SE SIAMO QUI, IL SERVER È PRONTO
        paziente = "PAZIENTE_TESI_01"
        payload = get_patient_data(paziente)
        msg = json.dumps(payload)
        
        client.publish("digitaltwin/breast/bootstrap", msg)
        print(f"[Mondo Fisico] 🚀 PAYLOAD INVIATO con successo!")
        
        time.sleep(1) # Diamo tempo al messaggio di partire
        client.loop_stop()
        client.disconnect()
        
    except Exception as e:
        print(f"❌ ERRORE: {e}")