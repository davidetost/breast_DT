import threading
import time
import os
import json
import math
import zmq
import grpc
import paho.mqtt.client as mqtt
from concurrent import futures

# Import gRPC
import breast_dt_pb2
import breast_dt_pb2_grpc

# ==========================
# 1. MODELLO TUMORALE (Classe Base)
# ==========================
class TumorModel:
    def __init__(self, r=0.5, c=10.0):
        self.radius = float(r)
        if self.radius < 0.1: self.radius = 0.1
        self.alpha = float(c) * 0.005
        self.k = 30.0
        self.drug_efficacy = 0.0
        self.drug_decay = 0.02
        self.emax = 0.05
        self.ic50 = 0.2 * max(1.0, 1.0 + (float(c) / 20.0))
        self.last_update_time = time.time()

    def update(self):
        now = time.time()
        dt = now - self.last_update_time
        
        # Gompertz
        if 0 < self.radius < self.k:
            growth = self.alpha * self.radius * math.log(self.k / self.radius)
        else:
            growth = 0.0
            
        # Terapia
        death = 0.0
        if self.drug_efficacy > 0:
            death = (self.emax * self.radius * self.drug_efficacy) / (self.ic50 + self.drug_efficacy) * self.radius
            self.drug_efficacy = max(0, self.drug_efficacy - (self.drug_decay * dt))

        self.radius = max(0.1, min(self.k, self.radius + (growth - death) * dt))
        self.last_update_time = now
        
        return {
            "radius": round(self.radius, 4),
            "status": "growing" if growth > death else "shrinking"
        }

    def inject(self, amount):
        self.drug_efficacy += float(amount)
        if self.drug_efficacy > 2.0: self.drug_efficacy = 2.0

# ==========================
# 2. STATO SEPARATO (3 MONDI PARALLELI)
# ==========================
# Ogni protocollo ha il SUO paziente personale da gestire
simulations = {
    "MQTT": {"left": TumorModel(), "right": TumorModel()},
    "ZMQ":  {"left": TumorModel(), "right": TumorModel()},
    "GRPC": {"left": TumorModel(), "right": TumorModel()}
}
# Lock separati per non influenzare le performance tra protocolli
locks = {
    "MQTT": threading.Lock(),
    "ZMQ":  threading.Lock(),
    "GRPC": threading.Lock()
}

# Configurazione Rete
MQTT_BROKER = os.getenv('BROKER_ADDRESS', '127.0.0.1')
ZMQ_PUB_PORT = 5555
ZMQ_REP_PORT = 5556
GRPC_PORT = 50051

# ==========================
# 3. WORKER MQTT (Loop Indipendente)
# ==========================
class MqttPipeline(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "Server_MQTT")
        self.running = True

    def run(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        try:
            self.client.connect(MQTT_BROKER, 1883, 60)
            self.client.loop_start()
            
            while self.running:
                # 1. CALCOLO (Simulazione carico CPU per MQTT)
                with locks["MQTT"]:
                    l_data = simulations["MQTT"]["left"].update()
                    r_data = simulations["MQTT"]["right"].update()
                
                # 2. TRASMISSIONE
                payload = {
                    "type": "TUMOR_STATE",
                    "tumors": {"left": l_data, "right": r_data},
                    "timestamp": time.time()
                }
                self.client.publish("digitaltwin/breast/tumor", json.dumps(payload))
                
                time.sleep(0.1) # 10 Hz
        except Exception as e:
            print(f"[MQTT] Error: {e}")

    def on_connect(self, client, userdata, flags, rc, props=None):
        print(f"[MQTT] Ready.")
        client.subscribe("digitaltwin/breast/action")
        client.subscribe("digitaltwin/breast/bootstrap")

    def on_message(self, client, userdata, msg):
        payload = json.loads(msg.payload.decode())
        
        # BOOTSTRAP: Questo è il segnale di START per TUTTI i protocolli
        if "bootstrap" in msg.topic:
            data = payload.get("initial_state", payload)
            r_l, c_l = data.get("left_tumor_radius", 0.5), data.get("left_tumor_cellularity", 10)
            r_r, c_r = data.get("right_tumor_radius", 0.5), data.get("right_tumor_cellularity", 10)
            
            print(f"[SYSTEM] 🏁 BOOTSTRAP RECEIVED -> Starting ALL Simulations")
            
            # Inizializza TUTTE e 3 le simulazioni allo stesso stato iniziale
            for proto in ["MQTT", "ZMQ", "GRPC"]:
                with locks[proto]:
                    simulations[proto]["left"] = TumorModel(r_l, c_l)
                    simulations[proto]["right"] = TumorModel(r_r, c_r)

        # ACTION: Colpisce SOLO la simulazione MQTT
        elif "action" in msg.topic:
            amt = float(payload.get("amount", 0))
            with locks["MQTT"]:
                print(f"[MQTT] 💉 Injecting {amt}mg")
                simulations["MQTT"]["left"].inject(amt)
                simulations["MQTT"]["right"].inject(amt)

# ==========================
# 4. WORKER ZEROMQ (Loop Indipendente)
# ==========================
class ZmqPipeline(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.context = zmq.Context()
        self.running = True

    def run(self):
        pub = self.context.socket(zmq.PUB)
        pub.bind(f"tcp://0.0.0.0:{ZMQ_PUB_PORT}")
        
        rep = self.context.socket(zmq.REP)
        rep.bind(f"tcp://0.0.0.0:{ZMQ_REP_PORT}")
        poller = zmq.Poller()
        poller.register(rep, zmq.POLLIN)

        print(f"[ZMQ] Ready (PUB:{ZMQ_PUB_PORT}, REP:{ZMQ_REP_PORT})")

        while self.running:
            # 1. CALCOLO (Simulazione carico CPU per ZMQ)
            with locks["ZMQ"]:
                l_data = simulations["ZMQ"]["left"].update()
                r_data = simulations["ZMQ"]["right"].update()

            # 2. TRASMISSIONE
            payload = {
                "type": "TUMOR_STATE", 
                "timestamp": time.time(),
                "tumors": {"left": l_data, "right": r_data}
            }
            pub.send_string(f"tumor {json.dumps(payload)}")

            # 3. RICEZIONE COMANDI (Colpisce SOLO ZMQ)
            socks = dict(poller.poll(10))
            if rep in socks:
                msg = rep.recv_json()
                amt = float(msg.get("amount", 0))
                with locks["ZMQ"]:
                    print(f"[ZMQ] 💉 Injecting {amt}mg")
                    simulations["ZMQ"]["left"].inject(amt)
                    simulations["ZMQ"]["right"].inject(amt)
                rep.send_json({"status": "OK"})
            
            time.sleep(0.04) # 25 Hz (ZMQ è più veloce)

# ==========================
# 5. WORKER GRPC (Simulazione Fisica + Servizio)
# ==========================
# gRPC ha bisogno di un thread separato per calcolare la fisica
# altrimenti il tumore cresce solo quando il client chiede dati.
class GrpcPhysicsLoop(threading.Thread):
    def run(self):
        while True:
            with locks["GRPC"]:
                simulations["GRPC"]["left"].update()
                simulations["GRPC"]["right"].update()
            time.sleep(0.1) # 10 Hz Update Rate

class GrpcService(breast_dt_pb2_grpc.DigitalTwinServiceServicer):
    def StreamTumorUpdates(self, request, context):
        print("[gRPC] Stream Start")
        while context.is_active():
            with locks["GRPC"]:
                l = simulations["GRPC"]["left"]
                r = simulations["GRPC"]["right"]
                # Leggiamo lo stato calcolato dal thread GrpcPhysicsLoop
                msg = breast_dt_pb2.TumorState(
                    timestamp=time.time(),
                    left=breast_dt_pb2.TumorData(radius=l.radius, status="active"),
                    right=breast_dt_pb2.TumorData(radius=r.radius, status="active")
                )
            yield msg
            time.sleep(0.1) # Transmission Rate

    def SendTherapy(self, request, context):
        with locks["GRPC"]:
            print(f"[gRPC] 💉 Injecting {request.dosage}mg")
            simulations["GRPC"]["left"].inject(request.dosage)
            simulations["GRPC"]["right"].inject(request.dosage)
        return breast_dt_pb2.Response(success=True, message="OK")

    # Il Bootstrap gRPC è opzionale se usiamo MQTT per startare tutto
    # Ma se lo usiamo, inizializza SOLO la parte gRPC (o tutte, scelta tua)
    def SendBootstrap(self, req, ctx):
        # Per coerenza, facciamo che anche questo resetta tutti
        # (omesso per brevità, assumiamo start da MQTT Physical Twin)
        return breast_dt_pb2.Response(success=True)

def start_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    breast_dt_pb2_grpc.add_DigitalTwinServiceServicer_to_server(GrpcService(), server)
    server.add_insecure_port(f'[::]:{GRPC_PORT}')
    print(f"[gRPC] Listening on {GRPC_PORT}")
    server.start()
    server.wait_for_termination()

# ==========================
# MAIN
# ==========================
if __name__ == '__main__':
    print("--- UNIVERSAL SERVER (3 INDEPENDENT PIPELINES) ---")

    # Avvia i 3 motori paralleli
    MqttPipeline().start()
    ZmqPipeline().start()
    GrpcPhysicsLoop().start() # Fisica indipendente per gRPC

    try:
        start_grpc() # Bloccante
    except KeyboardInterrupt:
        pass
