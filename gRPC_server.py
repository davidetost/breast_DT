import time
import os
import math
import grpc
import json
from concurrent import futures

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
        self.last_update_time = time.time()

    def update(self):
        now = time.time()
        dt  = min(now - self.last_update_time, 2.0)   # ← CAP fondamentale

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

GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))
STREAM_HZ  = float(os.getenv("STREAM_HZ", "1.0"))

class GRpcService(breast_dt_pb2_grpc.DigitalTwinServiceServicer):
    def __init__(self):
        self.left = TumorModel(15.0, 10.0)
        self.right = TumorModel(16.5, 12.0)
        self.bootstrapped = False

    def SendBootstrap(self, request, context):
        self.left = TumorModel(request.left_radius, request.left_cellularity)
        self.right = TumorModel(request.right_radius, request.right_cellularity)
        self.bootstrapped = True

        print(f"\n{'{='*50}")
        print(f"\n[gRPC-Server]Bootstrapped Patient {request.patient_id}")
        print(f" Left : R={request.left_radius:.2f}mm, C={request.left_cellularity:.2f}%")
        print(f" Right: R={request.right_radius:.2f}mm, C={request.right_cellularity:.2f}%")
        print(f"{'{='*50}\n")

        return breast_dt_pb2.Response(success="True", message="Bootstrap successful")

    def StreamTumorUpdates(self, request, context):
        print("[gRPC-Server] Stream started")
        interval = 1.0/STREAM_HZ
        while context.is_active():
            l=self.left.update()
            r=self.right.update()
            flag = "running" if self.bootstrapped else "waiting"
            print (f"[gRPC] {flag} L:{l['radius']:.4f}mm ({l['status']})"
                   f" | R:{r['radius']:.4f}mm ({r['status']})")
            
            yield breast_dt_pb2.TumorState(
                timestamp=time.time(),
                left=breast_dt_pb2.TumorData(**l),
                right=breast_dt_pb2.TumorData(**r),
            )
            time.sleep(interval)

        print("[gRPC-Server] Stream ended")

    def SendTherapy(self, request, context):
        self.left.inject_drug(request.dosage)
        self.right.inject_drug(request.dosage)
        print(f"[gRPC-Server] Therapy: {request.dosage}mg")
        return breast_dt_pb2.Response(success="True", message="Therapy applied")

def main():
    print(f"\n{'{='*50}")
    print(f"\n[gRPC-Server]")
    print(f" Port: {GRPC_PORT}")
    print(f" Rate: {STREAM_HZ}update/s")
    print(f"{'{='*50}\n")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    breast_dt_pb2_grpc.add_DigitalTwinServiceServicer_to_server(GRpcService(), server)
    server.add_insecure_port(f'[::]:{GRPC_PORT}')
    server.start()

    print(f"[gRPC-Server] Listening on port {GRPC_PORT}...")
    print(f"[gRPC-Server] Waiting for bootstrap data from gRPC server...")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[gRPC-Server] Shutting down...")
        server.stop(0)

if __name__ == "__main__":
    main()


