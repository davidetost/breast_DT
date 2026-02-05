import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1884 # La porta del tunnel verso la VM

def main():
    print("🧹 Avvio pulizia broker...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Cleaner")
    
    try:
        client.connect(BROKER, PORT, 60)
        
        # Per cancellare un messaggio retained, bisogna pubblicare 
        # un payload VUOTO con retain=True sullo stesso topic.
        topic = "digitaltwin/system/status"
        client.publish(topic, payload="", qos=1, retain=True)
        
        print(f"✅ Messaggio fantasma rimosso dal topic: {topic}")
        print("Ora puoi riavviare i tuoi script normali.")
        
        client.disconnect()
    except Exception as e:
        print(f"❌ Errore: {e}")
        print("Assicurati che la VM sia accesa!")

if __name__ == "__main__":
    main()