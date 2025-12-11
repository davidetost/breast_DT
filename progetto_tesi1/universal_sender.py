import time
import pandas as pd
import json
import argparse
import sys
from concurrent import futures

# --- IMPORT PROTOCOLLI ---
# 1. MQTT
import paho.mqtt.client as mqtt

# 2. ZeroMQ
import zmq

# 3. gRPC (Importiamo i file generati)
try:
    import grpc
    import bio_data_pb2
    import bio_data_pb2_grpc
except ImportError:
    print("⚠️  File gRPC non trovati. Esegui il comando protoc se vuoi usare gRPC.")

# --- CONFIGURAZIONE ---
CSV_FILENAME = "data.csv"
PUBLISH_INTERVAL = 0.5  # Secondi tra un invio e l'altro (es. 2Hz)

# Configurazione Rete
MQTT_BROKER = "broker.hivemq.com" # O il tuo IP locale/Hotspot
MQTT_TOPIC = "digitaltwin/breast/data"
ZMQ_PORT = 5555
GRPC_PORT = 50051

class BioSender:
    def __init__(self, csv_file):
        print(f"📂 Caricamento dataset: {csv_file}...")
        self.df = pd.read_csv(csv_file)
        self.total_records = len(self.df)
        print(f"✅ Dataset caricato: {self.total_records} record trovati.")
        
    def get_record(self, index):
        """Restituisce il record corrente come dizionario"""
        real_index = index % self.total_records
        record = self.df.iloc[real_index].to_dict()
        # Convertiamo i tipi numpy in tipi nativi python per JSON/Protobuf
        for key, value in record.items():
            if pd.isna(value): record[key] = 0.0
        return record

    # --- LOGICA MQTT ---
    def run_mqtt(self):
        print(f"🚀 Avvio modalità MQTT verso {MQTT_BROKER}...")
        client = mqtt.Client("BioSender_Python")
        try:
            client.connect(MQTT_BROKER, 1883, 60)
            client.loop_start()
            
            i = 0
            while True:
                data = self.get_record(i)
                payload = json.dumps(data, default=str) # Serializzazione JSON
                client.publish(MQTT_TOPIC, payload)
                
                print(f"[MQTT] Inviato ID: {data.get('id', 'N/A')} ({i})")
                i += 1
                time.sleep(PUBLISH_INTERVAL)
                
        except KeyboardInterrupt:
            client.loop_stop()
            print("\n⏹️  Stop MQTT.")

    # --- LOGICA ZeroMQ ---
    def run_zeromq(self):
        print(f"🚀 Avvio modalità ZeroMQ (PUB) sulla porta {ZMQ_PORT}...")
        context = zmq.Context()
        socket = context.socket(zmq.PUB)
        socket.bind(f"tcp://*:{ZMQ_PORT}")
        
        print("⏳ Attesa connessioni ZeroMQ...")
        time.sleep(2)  # Attesa per connessioni
        i = 0
        try:
            while True:
                data = self.get_record(i)
                # ZeroMQ invia byte, usiamo JSON come stringa
                payload = json.dumps(data, default=str)
                socket.send_string(payload)
                
                print(f"[ZeroMQ] Pubblicato ID: {data.get('id', 'N/A')} ({i})")
                i += 1
                time.sleep(PUBLISH_INTERVAL)
        except KeyboardInterrupt:
            socket.close()
            context.term()
            print("\n⏹️  Stop ZeroMQ.")

    # --- LOGICA gRPC ---
    def run_grpc(self):
        print(f"🚀 Avvio Server gRPC sulla porta {GRPC_PORT}...")
        
        # Classe interna per gestire il servizio
        # Nota: serve 'self' esterno, quindi usiamo una closure o passiamo il df
        parent_sender = self

        class BioServiceHandler(bio_data_pb2_grpc.BioServiceServicer):
            def GetBioStream(self, request, context):
                print("🔗 Client Unity connesso allo stream gRPC!")
                i = 0
                try:
                    while context.is_active():
                        record = parent_sender.get_record(i)
                        
                        # Creiamo il pacchetto Protobuf strettamente tipizzato
                        packet = bio_data_pb2.BioPacket(
                            id=int(record.get('id', 0)),
                            diagnosis=str(record.get('diagnosis', '')),
                            radius_mean=float(record.get('radius_mean', 0)),
                            texture_mean=float(record.get('texture_mean', 0)),
                            perimeter_mean=float(record.get('perimeter_mean', 0)),
                            area_mean=float(record.get('area_mean', 0)),
                            concavity_mean=float(record.get('concavity_mean', 0))
                        )
                        
                        yield packet # 'yield' invia il dato nello stream
                        print(f"[gRPC] Stream ID: {packet.id}")
                        
                        i += 1
                        time.sleep(PUBLISH_INTERVAL)
                except Exception as e:
                    print(f"❌ Errore Stream: {e}")

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        bio_data_pb2_grpc.add_BioServiceServicer_to_server(BioServiceHandler(), server)
        server.add_insecure_port(f'[::]:{GRPC_PORT}')
        server.start()
        try:
            server.wait_for_termination()
        except KeyboardInterrupt:
            print("\n⏹️  Stop gRPC.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BioData Sender per Tesi")
    parser.add_argument("mode", choices=["mqtt", "zmq", "grpc"], help="Protocollo da usare")
    args = parser.parse_args()

    sender = BioSender(CSV_FILENAME)

    if args.mode == "mqtt":
        sender.run_mqtt()
    elif args.mode == "zmq":
        sender.run_zeromq()
    elif args.mode == "grpc":
        sender.run_grpc()
