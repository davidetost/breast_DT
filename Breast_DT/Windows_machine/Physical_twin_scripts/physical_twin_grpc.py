import time
import csv
import random
import os
import grpc

import breast_dt_pb2
import breast_dt_pb2_grpc


SERVER_ADDRESS = "localhost:50051"
CSV_PATH       = "data.csv"


def get_patient_data(csv_path=CSV_PATH):
 
    if not os.path.exists(csv_path):
        print(f"[Data] WARNING {csv_path} not found - random data will be generated")
        return {
            "patient_id":   f"RAND_{random.randint(100000, 999999)}",
            "radius_mean":  round(random.uniform(10.0, 20.0), 2),
            "texture_mean": round(random.uniform(8.0, 15.0), 2)
        }

    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row    = next(reader)
            # Mappa 'id' → 'patient_id'
            p_id = row.get("id", row.get("patient_id", "PT_UNKNOWN"))
            return {
                "patient_id":   p_id,
                "radius_mean":  float(row.get("radius_mean",  15.0)),
                "texture_mean": float(row.get("texture_mean", 10.0))
            }
    except Exception as e:
        print(f"[Data] CSV reading errore: {e}")
        return None

def main():
    print("=" * 60)
    print("PHYSICAL TWIN → gRPC Bootstrap")
    print("=" * 60)

    patient = get_patient_data()
    if not patient:
        print("Patient data not available")
        return

    print(f"\n Selected patient: {patient['patient_id']}")
    print(f"   Radius  : {patient['radius_mean']:.2f} mm")
    print(f"   Texture : {patient['texture_mean']:.2f}%")

  
    channel = grpc.insecure_channel(SERVER_ADDRESS)
    stub    = breast_dt_pb2_grpc.DigitalTwinServiceStub(channel)

   
    req = breast_dt_pb2.BootstrapRequest(
        patient_id       = patient["patient_id"],
        left_radius      = patient["radius_mean"],
        left_cellularity = patient["texture_mean"],
        right_radius     = patient["radius_mean"] * 1.05,
        right_cellularity= patient["texture_mean"]
    )

    try:
        print(f"\n Connecting to {SERVER_ADDRESS}...")
        print(f"Sending BOOTSTRAP...")

        response = stub.SendBootstrap(req)

        if response.success:
            print(f"\n BOOTSTRAP SENT!")
            print(f"   Server   : {response.message}")
            print(f"   Patient  : {patient['patient_id']}")
            print(f"   Left  tumor: R={patient['radius_mean']:.2f}mm, C={patient['texture_mean']:.2f}%")
            print(f"   Right tumor: R={patient['radius_mean']*1.05:.2f}mm, C={patient['texture_mean']:.2f}%")
        else:
            print(f"  Server response: {response.message}")

    except grpc.RpcError as e:
        print(f" Errore gRPC: {e.code()} - {e.details()}")
    finally:
        channel.close()
        print("\n" + "=" * 60)
        print("✓ Session ended.")
        print("=" * 60)

if __name__ == "__main__":
    main()
