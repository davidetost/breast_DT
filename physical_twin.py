import time
import json
import random

# Simulazione di un Database Ospedaliero
def get_patient_data(patient_id):
    print(f"[Mondo Fisico] Recupero dati MRI per paziente: {patient_id}...")
    
    # Simuliamo un ritardo di lettura disco/database
    time.sleep(0.5)
    
    # In una tesi reale, qui leggeresti un file CSV o DICOM.
    # Per ora, generiamo dati verosimili:
    
    # Generiamo dimensioni casuali ma realistiche per il seno (in cm)
    radius = round(random.uniform(10.0, 16.0), 2)
    
    # Densità del tessuto (0.0 = grasso, 1.0 = denso/fibroso)
    # Un seno denso è più difficile da analizzare
    density = round(random.uniform(0.3, 0.9), 2)
    
    # Creiamo il pacchetto JSON (Payload)
    initial_state = {
        "meta": {
            "timestamp": time.time(),
            "packet_id": "BOOTSTRAP_001",
            "patient_id": patient_id
        },
        "morphology": {
            "breast_radius_cm": radius,
            "tissue_density": density,
            "position_offset": {"x": 0, "y": 1.5, "z": 0} # Posizione rispetto al centro
        },
        "config": {
            "simulation_tick_rate": 10, # Hz richiesti dall'Edge
            "risk_factors": {
                "genetic": 0.05, # BRCA1/2 probabilità
                "environmental": 0.01
            }
        }
    }
    
    return initial_state

if __name__ == "__main__":
    # Testiamo la generazione
    paziente = "PAZIENTE_TESI_01"
    payload = get_patient_data(paziente)
    
    print("\n[Mondo Fisico] Dati pronti per l'invio all'Edge:")
    print(json.dumps(payload, indent=4))
    
    # TODO: Qui inseriremo il codice gRPC per inviare 'payload' all'Edge