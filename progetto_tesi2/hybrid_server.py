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
        self.radius = max(0.1, float(r))
        self.alpha  = float(c) * 0.005
        self.k      = 30.0
        self.drug_efficacy = 0.0
        self.drug_decay    = 0.02
        self.emax          = 0.05
        self.ic50  = 0.2 * max(1.0, 1.0 + float(c) / 20.0)
        # ✅ setta NOW → primo dt sarà ~0, nessun salto
        self.last_update_time = time.time()

    def update(self, max_dt=2.0):
        now = time.time()
        dt  = min(now - self.last_update_time, max_dt)   # ← CAP fondamentale

        growth_rate = (self.alpha * self.radius * math.log(self.k / self.radius)
                       if 0 < self.radius < self.k else 0.0)

        death_rate = 0.0
        if self.drug_efficacy > 0:
            death_rate = (self.emax * self.radius * self.drug_efficacy
                          / (self.ic50 + self.drug_efficacy)) * self.radius

        self.radius += (growth_rate - death_rate) * dt
        self.radius  = max(0.1, min(self.radius, self.k))

        if self.drug_efficacy > 0:
            self.drug_efficacy = max(0.0, self.drug_efficacy - self.drug_decay * dt)

        self.last_update_time = now
        return {
            "radius":      round(self.radius, 4),
            "cellularity": round(self.alpha * 100, 2),
            "drug_level":  round(self.drug_efficacy, 4),
            "status":      "growing" if growth_rate > death_rate else "shrinking"
        }

    def inject_drug(self, amount):
        self.drug_efficacy = min(2.0, self.drug_efficacy + float(amount))


# ═══════════════════════════════════════════════════════════════════
# STATO CONDIVISO
# ═══════════════════════════════════════════════════════════════════
simulations = {
    "MQTT": {"left": TumorModel(15.0, 10.0), "right": TumorModel(16.5, 12.0)},
    "gRPC": {"left": TumorModel(15.0, 10.0), "right": TumorModel(16.5, 12.0)},
    "ZMQ":  {"left": TumorModel(15.0, 10.0), "right": TumorModel(16.5, 12.0)},
}
locks       = {k: threading.Lock() for k in simulations}
bootstrapped = {"MQTT": False, "gRPC": False, "ZMQ": False}

MQTT_BROKER  = os.getenv("BROKER_ADDRESS", "mosquitto")
MQTT_PORT    = 1883
GRPC_PORT    = 50051
ZMQ_PUB_PORT = 5555
ZMQ_REP_PORT = 5556


def apply_bootstrap(proto, r_l, c_l, r_r, c_r, patient_id):
    with locks[proto]:
        simulations[proto]["left"]  = TumorModel(r_l, c_l)
        simulations[proto]["right"] = TumorModel(r_r, c_r)
    bootstrapped[proto] = True
    print(f"\n{'='*60}")
    print(f"[{proto}] 🏁 Bootstrap ricevuto")
    print(f"  Patient : {patient_id}")
    print(f"  Left    : R={r_l:.2f} mm, C={c_l:.2f}%")
    print(f"  Right   : R={r_r:.2f} mm, C={c_r:.2f}%")
    print(f"{'='*60}\n")


def parse_bootstrap(payload):
    data = payload.get("initial_state", payload)
    r_l  = float(data.get("left_radius",      data.get("left_tumor_radius",       15.0)))
    c_l  = float(data.get("left_cellularity",  data.get("left_tumor_cellularity",  10.0)))
    r_r  = float(data.get("right_radius",     data.get("right_tumor_radius",       16.5)))
    c_r  = float(data.get("right_cellularity", data.get("right_tumor_cellularity", 12.0)))
    return r_l, c_l, r_r, c_r, payload.get("patient_id", "Unknown")


# ═══════════════════════════════════════════════════════════════════
# MQTT WORKER
# ═══════════════════════════════════════════════════════════════════
class MqttWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.client    = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                     client_id="HybridServer_MQTT")
        self.running   = True
        self.connected = False
        self.T_BOOT    = "digitaltwin/breast/bootstrap"
        self.T_PUB     = "digitaltwin/breast/tumor"
        self.T_ACT     = "digitaltwin/breast/action"

    def on_connect(self, client, userdata, flags, rc, props=None):
        ok = (rc == 0 or str(rc) == "ReasonCode.SUCCESS")
        self.connected = ok
        print(f"[MQTT] {'✓ Connected' if ok else f'✗ rc={rc}'}")
        if ok:
            client.subscribe(self.T_BOOT)
            client.subscribe(self.T_ACT)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if msg.topic == self.T_BOOT:
                apply_bootstrap("MQTT", *parse_bootstrap(payload))
            elif msg.topic == self.T_ACT:
                amount = float(payload.get("amount", payload.get("dosage", 0)))
                print(f"[MQTT] 💉 Therapy: {amount}mg")
                with locks["MQTT"]:
                    simulations["MQTT"]["left"].inject_drug(amount)
                    simulations["MQTT"]["right"].inject_drug(amount)
        except Exception as e:
            print(f"[MQTT] on_message error: {e}")

    def run(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        try:
            print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
            while self.running:
                if self.connected:
                    with locks["MQTT"]:
                        l = simulations["MQTT"]["left"].update()
                        r = simulations["MQTT"]["right"].update()
                    payload = {"type": "TUMOR_STATE", "timestamp": time.time(),
                               "tumors": {"left": l, "right": r}}
                    self.client.publish(self.T_PUB, json.dumps(payload))
                    flag = "🏃" if bootstrapped["MQTT"] else "⏳"
                    print(f"[MQTT] {flag} L:{l['radius']:.4f}mm ({l['status']}) | R:{r['radius']:.4f}mm ({r['status']})")
                time.sleep(2.0)
        except Exception as e:
            print(f"[MQTT] Fatal: {e}")


# ═══════════════════════════════════════════════════════════════════
# ZMQ WORKER
# ═══════════════════════════════════════════════════════════════════
class ZmqWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        ctx = zmq.Context()
        self.pub = ctx.socket(zmq.PUB)
        self.rep = ctx.socket(zmq.REP)

    def run(self):
        self.pub.bind(f"tcp://0.0.0.0:{ZMQ_PUB_PORT}")
        self.rep.bind(f"tcp://0.0.0.0:{ZMQ_REP_PORT}")
        poller = zmq.Poller()
        poller.register(self.rep, zmq.POLLIN)
        print(f"[ZMQ] ✓ Ready (PUB:{ZMQ_PUB_PORT}, REP:{ZMQ_REP_PORT})")

        while self.running:
            with locks["ZMQ"]:
                l = simulations["ZMQ"]["left"].update()
                r = simulations["ZMQ"]["right"].update()
            self.pub.send_multipart([
                b"tumor_updates",
                json.dumps({"type":"TUMOR_STATE","timestamp":time.time(),"left":l,"right":r}).encode()
            ])

            for sock, _ in poller.poll(10):
                try:
                    msg = self.rep.recv_json()
                    if msg.get("type") == "BOOTSTRAP":
                        apply_bootstrap("ZMQ", *parse_bootstrap(msg))
                        self.rep.send_json({"status":"OK"})
                    elif msg.get("type") == "INJECT":
                        amt = float(msg.get("dosage", msg.get("amount", 0)))
                        print(f"[ZMQ] 💉 Therapy: {amt}mg")
                        with locks["ZMQ"]:
                            simulations["ZMQ"]["left"].inject_drug(amt)
                            simulations["ZMQ"]["right"].inject_drug(amt)
                        self.rep.send_json({"status":"OK"})
                    else:
                        self.rep.send_json({"status":"ERROR","msg":"Unknown"})
                except Exception as e:
                    print(f"[ZMQ] REP error: {e}")
                    try: self.rep.send_json({"status":"ERROR"})
                    except: pass
            time.sleep(0.04)


# ═══════════════════════════════════════════════════════════════════
# gRPC SERVICE
# ═══════════════════════════════════════════════════════════════════
class GrpcService(breast_dt_pb2_grpc.DigitalTwinServiceServicer):

    def SendBootstrap(self, request, context):
        apply_bootstrap("gRPC", request.left_radius, request.left_cellularity,
                        request.right_radius, request.right_cellularity, request.patient_id)
        return breast_dt_pb2.Response(success=True, message="Bootstrap OK")

    def StreamTumorUpdates(self, request, context):
        print("[gRPC] ▶️  Stream started")
        while context.is_active():
            with locks["gRPC"]:
                l = simulations["gRPC"]["left"].update()
                r = simulations["gRPC"]["right"].update()
            flag = "🏃" if bootstrapped["gRPC"] else "⏳"
            print(f"[gRPC] {flag} L:{l['radius']:.4f}mm ({l['status']}) | R:{r['radius']:.4f}mm ({r['status']})")
            yield breast_dt_pb2.TumorState(
                timestamp=time.time(),
                left=breast_dt_pb2.TumorData(**l),
                right=breast_dt_pb2.TumorData(**r)
            )
            time.sleep(1)
        print("[gRPC] ⏹️  Stream stopped")

    def SendTherapy(self, request, context):
        print(f"[gRPC] 💉 Therapy: {request.dosage}mg")
        with locks["gRPC"]:
            simulations["gRPC"]["left"].inject_drug(request.dosage)
            simulations["gRPC"]["right"].inject_drug(request.dosage)
        return breast_dt_pb2.Response(success=True, message="OK")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def start_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    breast_dt_pb2_grpc.add_DigitalTwinServiceServicer_to_server(GrpcService(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    print(f"[gRPC] ✓ Listening on :{GRPC_PORT}")
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔷  HYBRID DIGITAL TWIN SERVER  v4")
    print("="*60)
    MqttWorker().start()
    ZmqWorker().start()
    print("[SYSTEM] ✅ Workers avviati — in attesa bootstrap...\n")
    try:
        start_grpc()
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutdown.")
