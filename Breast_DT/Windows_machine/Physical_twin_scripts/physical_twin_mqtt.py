import time
import json
import csv
import random
import os
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1884  
TOPIC_BOOTSTRAP = "digitaltwin/breast/bootstrap"
csv_path="data.csv"

def get_patient_data():
    
    if not os.path.exists(csv_path):
        print(f"[Data] WARNING {csv_path} not found. Random patient data will be generated.")
        return {
            "patient_id": f"RAND_{random.randint(10000,99999)}",
            "radius_mean": round(random.uniform(10.0, 20.0),2),
            "texture_mean": round(random.uniform(8.0, 15.0),2)
        }
    
    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row = next(reader)
            
            p_id = row.get("id", row.get("patient_id", "PT_UNKNOWN"))
            return {
                "patient_id": p_id,
                "radius_mean": float(row.get("radius_mean", 10.0)),
                "texture_mean": float(row.get("texture_mean", 15.0))
            }
    except Exception as e:
        print(f"[Data] CSV Error: {e}")
        return None
    
def main():
    print("=" *60)
    print(" PHYSICAL TWIN -> MQTT Bootstrap")
    print("=" *60)

    patient = get_patient_data()
    if not patient:
        print("Data not available")
        return
    
    print(f"\n Selected patient: {patient['patient_id']}")
    print(f" Radius: {patient['radius_mean']:.2f} mm")
    print(f" Texture: {patient['texture_mean']:.2f}%")

    payload={
        "patient_id": patient["patient_id"],
        "initial_state":{
            "left_tumor_radius": patient["radius_mean"],
            "left_tumor_cellularity": patient["texture_mean"],
            "right_tumor_cellularity":patient["radius_mean"] *1.05,
            "right_tumor_cellularity": patient["texture_mean"]
        },
        "timestamp": time.time()
    }

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="DigitalTwin_MQTT")

    try:
        print(f"\n Connecting to {BROKER}: {PORT}... ")
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        time.sleep(1)

        print (f"Sending bootstrap...")
        result = client.publish(TOPIC_BOOTSTRAP, json.dumps(payload), qos=1)
        result.wait_for_publish()

        print(f"\n BOOTSRAP SENT")
        print(f"Topic: {TOPIC_BOOTSTRAP}")
        print(F" Patient: {patient['patient_id']}")
        print(f" Left tumor: R={patient['radius_mean']:.2f}mm, C={patient['texture_mean']:.2f}%")
        print(f" Right tumor: R={patient['radius_mean']*1.05:.2f}mm, C={patient['texture_mean']:.2f}%")

        time.sleep(1)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()
        print("\n" + "=" *60)
        print("Session ended")
        print("=" *60)
if __name__ == "__main__":
    main()
