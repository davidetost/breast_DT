import threading
import time
import os 
import grpc
import zmq
import math
from concurrent import futures
import paho.mqtt.client as mqtt
import json
import logging

import breast_dr_pb2
import breast_dr_pb2_grpc

class TumorModel:
    def __init__(self, r, c):
        self.radius = float(r)
        if self.radius < 0.1: self.radius = 0.1
        self.alpha = float(c) * 0.005
        self.k = 30.0
        self.drug_efficacy = 0.0
        self.drug_decay=0.02
        self.emax=0.05
        resistance_factor = (float(c) / 20.0)
        base_ic50 = 0.2
        self.ic50 = base_ic50 * max(1.0, 1.0 + resistance_factor)
        
        self.last_update_time = time.time()

    def update(self):
        now =time.time()
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
            if self.drug_efficacy < 0: self.drug_efficacy = 0.0

        self.radius = max(0.1, min(self.radius, self.k))
        self.last_update_time = now

        return {
            "radius": round(self.radius, 4),
            "cellularity": round(self.alpha * 100, 2),
            "drug_level": round(self.drug_efficacy, 4),
            "status": "growing" if (growth_rate > death_rate) else "shrinking"
        }
    
MQTT_BROKER = os.getenv('BROKER_ADDRESS', '127.0.0.1')
MQTT_PORT = 1883
GRPC_PORT = 50051
ZMQ_PUB_PORT = 5555
ZMQ_REP_PORT = 5556

global_tumor = {
    "left": TumorModel(0.5, 10.0),
    "right": TumorModel(0.5, 10.0)
}
state_lock = threading.Lock() #simple lock to protect global tumor state
class MqttWorker(threading.Thread):
    def __init__ (self):
        threading.Thread.__init__(self)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,"HybridServer_MQTT")
        self.running = True

        self.patient_id = "Waiting..."

        # Topics
        self.topic_status = "digitaltwin/system/status"
        self.topic_bootstrap = "digitaltwin/breast/bootstrap"
        self.topic_pub = "digitaltwin/breast/tumor"
        self.topic_action = "digitaltwin/breast/action"
        self.topic_command = "digitaltwin/command" 

    def run(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        try:
            print(f"[MQTT] Connecting to broker at {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()

            while self.running:
                with state_lock:
                    pass

                with state_lock:
                    l= global_tumor["left"]
                    r= global_tumor["right"]
                    payload ={
                        "left":{"radius": l.radius, "status": "active"},
                        "right":{"radius": r.radius, "status": "active"}
                    }

                self.client.publish(self.topic_pub, json.dumps(payload))
                time.sleep(1)
        except Exception as e:
            print(f"[MQTT] Error: {e}")

    def on_connect(self, client, userdata, flags, rc, properties=None):
        print(f"[MQTT] Connected with result code {rc}")
        self.client.subscribe(self.topic_bootstrap)
        self.client.subscribe(self.topic_action)
        self.client.subscribe(self.topic_command)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if msg.topic == self.topic_bootstrap:
                print(f"[MQTT] Bootstrap received for patient ID: {payload.get('patient_id', 'Unknown')}")
                with state_lock:
                    global_tumor["left"] = TumorModel(payload["left_radius"], payload["left_cellularity"])
                    global_tumor["right"] = TumorModel(payload["right_radius"], payload["right_cellularity"])
                    self.patient_id = payload.get("patient_id", "Unknown")
                print(f"[MQTT] Tumor models initialized: Left radius={global_tumor['left'].radius}mm, cellularity={global_tumor['left'].alpha*100}%, Right radius={global_tumor['right'].radius}mm, cellularity={global_tumor['right'].alpha*100}%")

            elif msg.topic == self.topic_action:
                action_type = payload.get("action_type")
                amount = payload.get("amount", 0)
                print(f"[MQTT] Action received: {action_type} with amount {amount}")
                if action_type == "INJECT":
                    with state_lock:
                        global_tumor["left"].inject_drug(amount)
                        global_tumor["right"].inject_drug(amount)

            elif msg.topic == self.topic_command:
                command = payload.get("command")
                print(f"[MQTT] Command received: {command}")
                if command == "STOP":
                    self.running = False
                    print("[MQTT] Stopping simulation as per command.")
        except Exception as e:
            print(f"[MQTT] Error processing message: {e}")  

class ZmqWorker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.context = zmq.Context()
        self.pub_socket = self.context.socket(zmq.PUB)
        self.rep_socket = self.context.socket(zmq.REP)

    def run(self):
        self.pub_socket.bind(f"tcp://*:{ZMQ_PUB_PORT}")
        self.rep_socket.bind(f"tcp://*:{ZMQ_REP_PORT}")
        poller = zmq.Poller()
        poller.register(self.rep_socket, zmq.POLLIN)
        print(f"[ZMQ] Publisher bound to port {ZMQ_PUB_PORT}, Responder bound to port {ZMQ_REP_PORT}")

        while self.running:
            with state_lock:
                l_data= global_tumor["left"].update()
                r_data= global_tumor["right"].update()

            payload ={
                "type": "TUMOR_STATE",
                "meta": { "patient_id": self.patient_id },
                "timestamp": time.time(),
                "tumors": { "left": l_data, "right": r_data }
            }
            
            self.pub_socket.send_string(f"tumor {json.dumps(payload)}")
            socks = dict(poller.poll(100))
            if self.rep_socket in socks:
                message = self.rep_socket.recv_json()
                amount  = float(message.get("amount", 0))
                with state_lock:
                    print (f"[ZMQ] Therapy: {amount}mg")
                    l_data= global_tumor["left"].inject_drug(amount)
                    r_data= global_tumor["right"].inject_drug(amount)
                self.rep_socket.send_json({"status": "OK"})
                socks = dict(poller.poll(100))
                if self.rep_socket in socks:
                    message = self.rep_socket.recv_json()
                    amount= float(message.get("amount", 0))
                    with state_lock:
                        print (f"[ZMQ] Therapy: {amount}mg")
                        l_data= global_tumor["left"].inject_drug(amount)
                        r_data= global_tumor["right"].inject_drug(amount)
                    self.rep_socket.send_json({"status": "OK"})

                    time.sleep(1)   

class GrpcService(breast_dt_pb2_grpc.DigitalTwinService):
    def __init__(self):
        self.left = None
        self.right = None
        self.running = False
        print ("[Server] Waiting for bootstrap data...")
    def SendBootstrap(self,request,context):
        print (f"[gRPC] Bootstrap request received for the patient with the ID: {request.patient_id}")
        print(f"[gRPC] Initial tumor status - Left: radius={self.left.radius}mm, cellularity={self.left.alpha*100}%, Right: radius={self.right.radius}mm, cellularity={self.right.alpha*100}%")

        self.left= TumorModel(request.left_radius, request.left_cellularity)
        self.right= TumorModel(request.right_radius, request.right_cellularity)
        self.running = True
        return breast_dt_pb2.BootstrapResponse(success=True, status="Bootstrap successful")

    def StreamTumorUpdates(self, request, context):
        print ("Client connected for tumor updates")
        self.running = True

        while self.running and context.is_active():
            if self.left is None or self.right is None:
                print ("[gRPC] Tumor models not initialized, waiting for bootstrap data...")
                time.sleep(1)
                continue
            #if the client is still connected, update the tumor status
            r_l= self.left.update()
            r_r= self.right.update()

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

            #a protobuf message is created with the updated tumor status and sent to the client
            response = breast_dt_pb2.TumorState(
                left=left_data,
                right=right_data,
                drug_level= self.left.drug_efficacy,
            )
            yield response #it forwards data to Unity
            time.sleep(1)

        print ("[gRPC] Streaming stopped")

    def SendAction (self, request, context):
        if request.action_type == "STOP":
            self.running = False
            print ("[gRPC] Received STOP command, stopping simulation")
        elif request.action_type == "START":
            self.running = True
            print ("[gRPC] Received START command, starting simulation")
        elif request.action_type == "INJECT":
            self.left.inject_drug(request.amount)
            self.right.inject_drug(request.amount)
            print (f"[gRPC] Received INJECT command, drug amount: {request.amount}mg")

        return breast_dt_pb2.ActionResponse(success= True, status="OK")

   #server startup 
def start_grpc():
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        breast_dt_pb2_grpc.add_DigitalTwinServiceServicer_to_server(GrpcService(), server)
        server.add_insecure_port('[::]:50051')
        print ("[gRPC] Starting server on port 50051...")
        server.start()
        try:
            while True:
                time.sleep(86400) # Keep the server running
        except KeyboardInterrupt:
            print ("[gRPC] Stopping server...")
            server.stop(0)

            server.wait_for_termination()
    
    
if __name__ == '__main__':
    print("---HYBRID SERVER STARTING---")

    mqtt_thread = MqttWorker()
    mqtt_thread.daemon=True
    mqtt_thread.start()

    zmq_thread = ZmqWorker()
    zmq_thread.daemon=True
    zmq_thread.start()

    try:
        start_grpc()
    except KeyboardInterrupt:
        print("Shutting down Hybrid Server...")