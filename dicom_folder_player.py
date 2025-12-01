import os
import time
import json
import zmq
import pydicom
import numpy as np
import argparse

# --- CONFIGURAZIONE ---
DATASET_ROOT = r"C:\Users\Davide\OneDrive - Universita' degli Studi Mediterranea\Magistrale\Tesi Magistrale\Immagini\manifest-25vRPwyh8987165612391086998\TCGA-BRCA" 
ZMQ_PORT = 5555

def find_dicom_series(root_path):
    """
    Scende ricorsivamente nelle cartelle finché non trova 
    una cartella che contiene file .dcm
    """
    print(f"🔍 Cerco file DICOM partendo da: {root_path}")
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filtra solo i file .dcm
        dicom_files = [f for f in filenames if f.endswith('.dcm')]
        
        if len(dicom_files) > 0:
            print(f"✅ Trovata serie DICOM in: {dirpath}")
            print(f"📦 Numero immagini: {len(dicom_files)}")
            # Ordiniamo i file per essere sicuri che la sequenza sia corretta
            dicom_files.sort()
            # Ritorniamo il percorso completo di ogni file
            return [os.path.join(dirpath, f) for f in dicom_files]
            
    print("❌ Nessun file .dcm trovato nella struttura.")
    return []

def process_slice_for_unity(dcm_path):
    """
    Edge Processing: Legge un file pesante, estrae 3 numeri per Unity.
    """
    try:
        ds = pydicom.dcmread(dcm_path)
        
        # 1. Estrarre un valore rappresentativo per il RAGGIO
        # Usiamo la media dell'intensità dei pixel. 
        # Più il tessuto è denso (bianco), più grande diventa la sfera.
        if hasattr(ds, 'PixelData'):
            pixel_array = ds.pixel_array
            # Calcoliamo la media, normalizziamo per avere valori tra 10 e 20 circa
            avg_intensity = np.mean(pixel_array)
            # Formula empirica per adattare i valori DICOM (spesso 0-4096) alla scala Unity
            radius_proxy = 10.0 + (avg_intensity / 50.0) 
        else:
            radius_proxy = 14.0 # Fallback

        # 2. Estrarre Texture/Rugosità
        # Usiamo la deviazione standard (quanto varia l'immagine in quella fetta)
        if hasattr(ds, 'PixelData'):
            texture_proxy = np.std(pixel_array)
        else:
            texture_proxy = 5.0

        # 3. Diagnosi Simulata (per il colore)
        # Se c'è un punto molto luminoso (calcificazione/massa), segna come 'M'
        max_intensity = np.max(pixel_array) if hasattr(ds, 'PixelData') else 0
        diagnosis = "M" if max_intensity > 2000 else "B" # Soglia fittizia per demo

        # Costruiamo il pacchetto JSON leggero
        packet = {
            "id": 1, # ID fisso per il DT
            "slice_index": str(ds.InstanceNumber) if 'InstanceNumber' in ds else "0",
            "diagnosis": diagnosis,
            "radius_mean": float(radius_proxy),
            "texture_mean": float(texture_proxy)
        }
        return packet

    except Exception as e:
        print(f"⚠️ Errore lettura slice {dcm_path}: {e}")
        return None

def run_player():
    # 1. SETUP RETE
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://0.0.0.0:{ZMQ_PORT}")
    print(f"🚀 [Edge Node] Pronto su porta {ZMQ_PORT}")

    # 2. TROVA I FILE
    files = find_dicom_series(DATASET_ROOT)
    
    if not files:
        return

    print("▶️ Avvio streaming della scansione DICOM al Digital Twin...")
    print("   (Premi Ctrl+C per interrompere)")

    try:
        # Loop infinito: quando finisce la scansione, ricomincia (effetto loop)
        while True:
            for file_path in files:
                # EDGE PROCESSING: Da 500KB di immagine a 100 Byte di JSON
                data = process_slice_for_unity(file_path)
                
                if data:
                    socket.send_string(json.dumps(data))
                    print(f"📡 Slice {data['slice_index']} -> R: {data['radius_mean']:.2f} | D: {data['diagnosis']}")
                
                # Simuliamo la velocità della macchina (es. 10 slice al secondo)
                time.sleep(0.1) 
            
            print("🔄 Scansione completata. Riavvio loop...")
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n⏹️ Stop.")
        socket.close()

if __name__ == "__main__":
    run_player()