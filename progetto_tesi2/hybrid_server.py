import threading
import time
import os 
import grpc
import zmq
import math
from concurrent import futures
import paho.mqtt.client as mqtt
import json

import breast_dt_pb2
import breast_dt_pb2_grpc

# ═══════════════════════════════════════════════════════════════════
# TUMOR MODEL
# ═══════════════════════════════════════════════════════════════════
class TumorModel:
    def __init__(self, r, c):
        self.radius = float(r)
        if self.radius < 0.1: 
            self.radius = 0.1
        
        self.alpha = float(c) * 0.005
        self.k = 30.0
        self.drug_efficacy = 0.0
        self.drug_decay = 0.02
        self.emax = 0.05
        
        resistance_factor = (float(c) / 20.0)
        base_ic50 = 0.2
        self.ic50 = base_ic50 * max(1.0, 1.0 + resistance_factor)
        
        self.last_update_time = time.time()

    def update(self):
        now = time.time()
        dt = now - self.last_update_time

        if 0 < self.radius < self.k:
            growth_rate = self.alpha * self.radius * math.log(self.k / self.radius)
        else:
            growth_rate = 0.0

        death_rate = 0.0
        if self.drug_efficacy > 0:
            drug_effect = self.emax * self.radius * self.drug_efficacy / (self.ic50 + self.drug_efficacy)
            death_rate = drug_effect * self.radius

        delta_radius = (growth_rate - death_rate) * dt
        self.radius += delta_radius

        if self.drug_efficacy > 0:
            self.drug_efficacy -= (self.drug_decay * dt)
            if self.drug_efficacy < 0: 
                self.drug_efficacy = 0.0

        self.radius = max(0.1, min(self.radius, self.k))
        self.last_update_time = now

        return {
            "radius": round(self.radius, 4),
            "cellularity": round(self.alpha * 100, 2),
            "drug_level": round(self.drug_efficacy, 4),
            "status": "growing" if (growth_rate > death_rate) else "shrinking"
        }
    
    def inject_drug(self, amount):
        self.drug_efficacy += float(amount)
        if self.drug_efficacy > 2.0:
            self.drug_efficacy = 2.0

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
simulations ={
    "MQTT": {"left": TumorModel(15, 10.0), "right": TumorModel(16.5, 12.0)},
    "gRPC": {"left": TumorModel(15, 10.0), "right": TumorModel(16.5, 12.0)},
    "ZMQ": {"left": TumorModel(15, 10.0), "right": TumorModel(16.5, 12.0)}
}
locks = {
    "MQTT": threading.Lock(),
    "gRPC": threading.Lock(),
    "ZMQ": threading.Lock()
}
MQTT_BROKER = os.getenv('BROKER_ADDRESS', 'mosquitto')  # ← FIX 1: Nome container Docker
MQTT_PORT = 1883
GRPC_PORT = 50051
ZMQ_PUB_PORT = 5555
ZMQ_REP_PORT = 5556



# ═══════════════════════════════════════════════════════════════════
# MQTT WORKER
# ═══════════════════════════════════════════════════════════════════
class MqttWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id = "HybridServer_MQTT")
        self.running = True
        self.patient_id = "Unknown"

        # Topics
        self.topic_bootstrap = "digitaltwin/breast/bootstrap"
        self.topic_pub = "digitaltwin/breast/tumor"
        self.topic_action = "digitaltwin/breast/action"

    def run(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        try:
            print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()

            while self.running:
                # Update and publish
                with locks["MQTT"]:
                    l_data = simulations["MQTT"]["left"].update()
                    r_data = simulations["MQTT"]["right"].update()

                payload = {
                    "type": "TUMOR_STATE",
                    "timestamp": time.time(),
                    "tumors": {
                        "left": l_data,
                        "right": r_data
                    }
                }

                self.client.publish(self.topic_pub, json.dumps(payload))

                print(f"[MQTT] Running... L: {l_data['radius']:.2f}mm | R: {r_data['radius']:.2f}mm")
                time.sleep(2.0)
                
        except Exception as e:
            print(f"[MQTT] Error: {e}")

    def on_connect(self, client, userdata, flags, rc, properties=None):
        print(f"[MQTT] ✓ Connected (rc={rc})")
        self.client.subscribe(self.topic_bootstrap)
        self.client.subscribe(self.topic_action)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            
            if msg.topic == self.topic_bootstrap:
                # ✅ FIX 2: Supporta formato nested e flat
                if "initial_state" in payload:
                    data = payload["initial_state"]
                else:
                    data = payload
                
                r_l = float(data.get("left_radius", data.get("left_tumor_radius", 15.0)))
                c_l = float(data.get("left_cellularity", data.get("left_tumor_cellularity", 10.0)))
                r_r = float(data.get("right_radius", data.get("right_tumor_radius", 16.5)))
                c_r = float(data.get("right_cellularity", data.get("right_tumor_cellularity", 12.0)))
                
                p_id = payload.get("patient_id", "Unknown")
                
                print(f"\n{'='*60}")
                print(f"[MQTT] 🏁 Bootstrap received")
                print(f"  Patient: {p_id}")
                print(f"  Left:  R={r_l:.2f}, C={c_l:.2f}")
                print(f"  Right: R={r_r:.2f}, C={c_r:.2f}")
                print(f"{'='*60}\n")
                
                with locks["MQTT"]:
                    simulations["MQTT"]["left"] = TumorModel(r_l, c_l)
                    simulations["MQTT"]["right"] = TumorModel(r_r, c_r)
                    self.patient_id = p_id

            elif msg.topic == self.topic_action:
                # ✅ FIX 3: Supporta sia "amount" che "dosage"
                amount = float(payload.get("amount", payload.get("dosage", 0)))
                
                print(f"[MQTT] 💉 Therapy: {amount}mg")
                
                with locks["MQTT"]:
                    simulations["MQTT"]["left"].inject_drug(amount)
                    simulations["MQTT"]["right"].inject_drug(amount)
                    
        except Exception as e:
            print(f"[MQTT] Error processing message: {e}")

# ═══════════════════════════════════════════════════════════════════
# ZMQ WORKER
# ═══════════════════════════════════════════════════════════════════
class ZmqWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.running = True  # ← FIX 4: Aggiunto attributo mancante!
        self.context = zmq.Context()
        self.pub_socket = self.context.socket(zmq.PUB)
        self.rep_socket = self.context.socket(zmq.REP)
        self.patient_id = "Unknown"

    def run(self):
        self.pub_socket.bind(f"tcp://0.0.0.0:{ZMQ_PUB_PORT}")
        self.rep_socket.bind(f"tcp://0.0.0.0:{ZMQ_REP_PORT}")
        
        poller = zmq.Poller()
        poller.register(self.rep_socket, zmq.POLLIN)
        
        print(f"[ZMQ] ✓ Ready (PUB:{ZMQ_PUB_PORT}, REP:{ZMQ_REP_PORT})")

        while self.running:
            # Update and publish
            with locks["ZMQ"]:
                l_data = simulations["ZMQ"]["left"].update()
                r_data = simulations["ZMQ"]["right"].update()

            # ✅ FIX 5: Formato compatibile con Unity
            payload = {
                "type": "TUMOR_STATE",
                "timestamp": time.time(),
                "left": l_data,
                "right": r_data
            }
            
            # Multipart: [topic, json]
            self.pub_socket.send_multipart([
                b"tumor_updates",
                json.dumps(payload).encode()
            ])
            print(f"[ZMQ] Running... L: {l_data['radius']:.2f}mm | R: {r_data['radius']:.2f}mm")
            # Check for commands
            socks = dict(poller.poll(10))
            if self.rep_socket in socks:
                try:
                    message = self.rep_socket.recv_json()
                    
                    if message.get("type") == "BOOTSTRAP":
                        r_l = float(message.get("left_tumor_radius", message.get("left_radius", 15.0)))
                        c_l = float(message.get("left_tumor_cellularity", message.get("left_cellularity", 10.0)))
                        r_r = float(message.get("right_tumor_radius", message.get("right_radius", 16.5)))
                        c_r = float(message.get("right_tumor_cellularity", message.get("right_cellularity", 12.0)))
                        p_id = message.get("patient_id", "Unknown")
                        
                        print(f"\n{'='*60}")
                        print(f"[ZMQ] 🏁 Bootstrap received")
                        print(f"  Patient: {p_id}")
                        print(f"  Left:  R={r_l:.2f}, C={c_l:.2f}")
                        print(f"  Right: R={r_r:.2f}, C={c_r:.2f}")
                        print(f"{'='*60}\n")
                        
                        with locks["ZMQ"]:
                            simulations["ZMQ"]["left"] = TumorModel(r_l, c_l)
                            simulations["ZMQ"]["right"] = TumorModel(r_r, c_r)
                            self.patient_id = p_id
                        
                        self.rep_socket.send_json({"status": "OK", "message": "Bootstrap successful"})
                    
                    elif message.get("type") == "INJECT":
                        amount = float(message.get("dosage", message.get("amount", 0)))
                        
                        print(f"[ZMQ] 💉 Therapy: {amount}mg")
                        
                        with locks["ZMQ"]:
                            simulations["ZMQ"]["left"].inject_drug(amount)
                            simulations["ZMQ"]["right"].inject_drug(amount)
                        
                        self.rep_socket.send_json({"status": "OK"})
                    
                    else:
                        self.rep_socket.send_json({"status": "ERROR", "message": "Unknown command"})
                        
                except Exception as e:
                    print(f"[ZMQ] Command error: {e}")
                    self.rep_socket.send_json({"status": "ERROR", "message": str(e)})

            time.sleep(0.04)  # 25Hz

# ═══════════════════════════════════════════════════════════════════
# gRPC SERVICE
# ═══════════════════════════════════════════════════════════════════
class GrpcService(breast_dt_pb2_grpc.DigitalTwinServiceServicer):
    def __init__(self):
        self.left = TumorModel(15.0, 10.0)
        self.right = TumorModel(16.5, 12.0)
        self.running = False
        self.patient_id = "Unknown"
        print("[gRPC] Service initialized, waiting for bootstrap...")

    def SendBootstrap(self, request, context):
        p_id = request.patient_id
        r_l = request.left_radius
        c_l = request.left_cellularity
        r_r = request.right_radius
        c_r = request.right_cellularity
        
        print(f"\n{'='*60}")
        print(f"[gRPC] 🏁 Bootstrap received")
        print(f"  Patient: {p_id}")
        print(f"  Left:  R={r_l:.2f}, C={c_l:.2f}")
        print(f"  Right: R={r_r:.2f}, C={c_r:.2f}")
        print(f"{'='*60}\n")
        
        self.left = TumorModel(r_l, c_l)
        self.right = TumorModel(r_r, c_r)
        self.running = True
        self.patient_id = p_id
        
        # ✅ FIX 6: Ritorna Response (non BootstrapResponse)
        return breast_dt_pb2.Response(success=True, message="Bootstrap successful")

    def StreamTumorUpdates(self, request, context):
        print("[gRPC] Stream started")
        self.running = True

        while self.running and context.is_active():
            # Update models
            r_l = self.left.update()
            r_r = self.right.update()

            left_data = breast_dt_pb2.TumorData(
                radius=r_l["radius"],
                cellularity=r_l["cellularity"],
                drug_level=r_l["drug_level"],
                status=r_l["status"]
            )
            
            right_data = breast_dt_pb2.TumorData(
                radius=r_r["radius"],
                cellularity=r_r["cellularity"],
                drug_level=r_r["drug_level"],
                status=r_r["status"]
            )

            response = breast_dt_pb2.TumorState(
                timestamp=time.time(),
                left=left_data,
                right=right_data
            )
            
            yield response
            time.sleep(1)

        print("[gRPC] Stream stopped")

    def SendTherapy(self, request, context):
        amount = request.dosage
        
        print(f"[gRPC] 💉 Therapy: {amount}mg")
        
        self.left.inject_drug(amount)
        self.right.inject_drug(amount)
        
        return breast_dt_pb2.Response(success=True, message="Therapy applied")

# ═══════════════════════════════════════════════════════════════════
# GRPC STARTUP
# ═══════════════════════════════════════════════════════════════════
def start_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    breast_dt_pb2_grpc.add_DigitalTwinServiceServicer_to_server(GrpcService(), server)
    server.add_insecure_port(f'[::]:{GRPC_PORT}')
    
    print(f"[gRPC] ✓ Listening on port {GRPC_PORT}")
    
    server.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[gRPC] Stopping...")
        server.stop(0)

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🔷 HYBRID DIGITAL TWIN SERVER")
    print("="*60)
    print("Protocols: MQTT | gRPC | ZeroMQ")
    print("Ports: 1883 | 50051 | 5555/5556")
    print("="*60 + "\n")

    # Start MQTT worker
    mqtt_thread = MqttWorker()
    mqtt_thread.start()

    # Start ZMQ worker
    zmq_thread = ZmqWorker()
    zmq_thread.start()

    print("[SYSTEM] All workers started")
    print("[SYSTEM] Waiting for bootstrap...\n")

    # Start gRPC (blocking)
    try:
        start_grpc()
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutdown requested")
