import time
import os
import math
import zmq
import json

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
        dt  = min(now - self.last_update_time, 2.0)

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


PUB_PORT = int(os.getenv("ZMQ_PUB_PORT", 5555))
REP_PORT = int(os.getenv("ZMQ_REP_PORT", 5556))
PUBLISH_HZ = float(os.getenv("PUBLISH_HZ", 25.0))

def main():
    left = None
    right = None
    bootstrapped = False

    context = zmq.Context()
    pub = context.socket(zmq.PUB)
    rep = context.socket(zmq.REP)
    
    pub.bind(f"tcp://0.0.0.0:{PUB_PORT}")
    rep.bind(f"tcp://0.0.0.0:{REP_PORT}")

    poller = zmq.Poller()
    poller.register(rep, zmq.POLLIN)

    print(f"\n{'{='*50}")
    print(f" ZMQ SERVER")
    print(f" PUB port: {PUB_PORT}")
    print(f" REP port: {REP_PORT}")
    print(f"{'='*50}\n")
    print(f" [ZMQ-SERVER] Ready - waiting for bootstrap data...\n")

    interval = 1.0 / PUBLISH_HZ

    while True:
        # 1. Poll per messaggi in arrivo (Non bloccante)
        socks = dict(poller.poll(0))
        
        if rep in socks:
            try:
                msg = rep.recv_json()
                mtype = msg.get("type", "")

                if mtype == "BOOTSTRAP":
                    data = msg.get("initial_state", msg)
                    r_l = float(data.get("left_radius", 15.0))
                    c_l = float(data.get("left_cellularity", 10.0))
                    r_r = float(data.get("right_radius", 16.5))
                    c_r = float(data.get("right_cellularity", 12.0))
                    p_id = msg.get("patient_id", "Unknown")
                    
                    left = TumorModel(r_l, c_l)
                    right = TumorModel(r_r, c_r)
                    bootstrapped = True

                    print(f"\n{'{='*50}")
                    print(f"\n[ZMQ-Server] 🚀 Bootstrapped Patient {p_id}")
                    print(f" Left : R={r_l:.2f}mm, C={c_l:.2f}%")
                    print(f" Right: R={r_r:.2f}mm, C={c_r:.2f}%")
                    print(f"{'='*50}\n")

                    rep.send_json({"status": "OK", "message": "Bootstrap applied"})

                elif mtype == "INJECT":
                    if bootstrapped:
                        amount = float(msg.get("dosage", msg.get("amount", 0)))
                        left.inject_drug(amount)
                        right.inject_drug(amount)
                        print(f"[ZMQ-Server] 💉 Therapy: {amount}mg")
                        rep.send_json({"status": "OK"})
                    else:
                        rep.send_json({"status": "ERROR", "message": "Not bootstrapped yet"})

            except Exception as e:
                print(f"[ZMQ-Server] REP error: {e}")
                try: rep.send_json({"status": "ERROR", "message": str(e)}) 
                except: pass

        # 2. Aggiornamento e Pubblicazione
        if bootstrapped:
            l_data = left.update()
            r_data = right.update()

            payload = json.dumps({
                "type": "TUMOR_STATE",
                "timestamp": time.time(),
                "tumors": {
                    "left": l_data,
                    "right": r_data
                }
            })
            
        
            pub.send_multipart([
                b"tumor_updates",           # Frame 1: Topic
                payload.encode('utf-8')     # Frame 2: JSON Pulito
            ])
            
            # Debug visivo nel terminale: vedi i numeri crescere?
            print(f"[ZMQ] L:{l_data['radius']:.3f} | R:{r_data['radius']:.3f}", end='\r')
            
            time.sleep(interval)
        else:
            time.sleep(0.1)

if __name__ == "__main__":
    main()