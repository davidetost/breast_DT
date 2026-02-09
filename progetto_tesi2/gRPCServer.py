import time 
import math
import grpc
from concurrent import futures
import breast_dt_pb2
import breast_dt_pb2_grpc

# Same Gompertz Model as the one used for MQTT
class TumorModel:
    def __init__(self, r, c):
        self.radius = r
        self.alpha = c* 0.005
        self.k = 30.0
        self.drug_efficacy = 0.0
        self.drug_decay=0.02
        self.emax=0.05

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
    
    def inject_drug(self, amount):
        self.drug_efficacy += float(amount)
        if self.drug_efficacy > 2.0: self.drug_efficacy = 2.0

        #gRPC Server Implementation
class DigitalTwinService(breast_dt_pb2_grpc.DigitalTwinService):
    def __init__(self):
        self.left = TumorModel(15.0, 10.0)
        self.right = TumorModel(16.5, 12.0)
        self.running = False
    def StreamTumorUpdates(self, request, context):
        print ("Client connected for tumor updates")
        self.running = True

        while self.running and context.is_active():
            #if the client is still connected, update the tumor status
            r_l= self.left.update()
            r_r= self.right.update()

            #a protobuf message is created with the updated tumor status and sent to the client
            response = breast_dt_pb2.TumorStatus(
                left_radius=r_l["radius"],
                right_radius=r_r["radius"],
                drug_level= self.left.drug_efficacy,
                timestamp = time.time(),
                status = "GROWING"
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
def serve():
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        breast_dt_pb2_grpc.add_DigitalTwinServiceServicer_to_server(DigitalTwinService(), server)
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
    serve()
   