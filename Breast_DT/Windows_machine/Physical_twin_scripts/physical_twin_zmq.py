import time
import csv
import random
import os
import zmq

SERVER_ADDRESS = "tcp://127.0.0.1:5556"  
CSV_PATH       = "data.csv"

def get_patient_data(csv_path=CSV_PATH):
    """Legge prima riga CSV. Genera dati random se manca."""
    if not os.path.exists(csv_path):
        print(f"[Data] WARNING {csv_path} not found - random data will be generated.")
        return {
            "patient_id":   f"RAND_{random.randint(100000, 999999)}",
            "radius_mean":  round(random.uniform(10.0, 20.0), 2),
            "texture_mean": round(random.uniform(8.0, 15.0), 2)
        }

    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row    = next(reader)
            
            p_id = row.get("id", row.get("patient_id", "PT_UNKNOWN"))
            return {
                "patient_id":   p_id,
                "radius_mean":  float(row.get("radius_mean",  15.0)),
                "texture_mean": float(row.get("texture_mean", 10.0))
            }
    except Exception as e:
        print(f"[Data] Errore lettura CSV: {e}")
        return None


def main():
    print("=" * 60)
    print("PHYSICAL TWIN → ZMQ Bootstrap")
    print("=" * 60)

    patient = get_patient_data()
    if not patient:
        print(" Dati paziente non disponibili.")
        return

    print(f"\n Selected patient: {patient['patient_id']}")
    print(f"   Radius  : {patient['radius_mean']:.2f} mm")
    print(f"   Texture : {patient['texture_mean']:.2f}%")


    payload = {
        "type": "BOOTSTRAP",
        "patient_id": patient["patient_id"],
        "left_tumor_radius":       patient["radius_mean"],
        "left_tumor_cellularity":  patient["texture_mean"],
        "right_tumor_radius":      patient["radius_mean"] * 1.05,
        "right_tumor_cellularity": patient["texture_mean"]
    }

    ctx    = zmq.Context()
    socket = ctx.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, 5000)  
    socket.setsockopt(zmq.LINGER, 0)

    try:
        print(f"\n Connecting to {SERVER_ADDRESS}...")
        socket.connect(SERVER_ADDRESS)

        print(f"Sending BOOTSTRAP...")
        socket.send_json(payload)

        
        response = socket.recv_json()

        print(f"\n BOOTSTRAP SENT!")
        print(f"   Server   : {response.get('message', response.get('status'))}")
        print(f"   Patient  : {patient['patient_id']}")
        print(f"   Left  tumor: R={patient['radius_mean']:.2f}mm, C={patient['texture_mean']:.2f}%")
        print(f"   Right tumor: R={patient['radius_mean']*1.05:.2f}mm, C={patient['texture_mean']:.2f}%")

    except zmq.Again:
        print(f"Timeout: no response from the server, verify if it is active")
    except Exception as e:
        print(f" Error: {e}")
    finally:
        socket.close()
        ctx.term()
        print("\n" + "=" * 60)
        print("Session ended.")
        print("=" * 60)

if __name__ == "__main__":
    main()
