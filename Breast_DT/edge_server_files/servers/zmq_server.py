import time
import os
import math
import json
import zmq

class TumorModel:
    def __init__(self, r, c):
        self.radius = max(0.1, float(r))
        self.alpha  = float(c) * 0.005
        self.k      = 30.0
        self.drug_efficacy = 0.0
        self.drug_decay    = 0.02
        self.emax          = 0.05
        self.ic50          = 0.2 * max(1.0, 1.0 + float(c) / 20.0)
        self.last_update   = time.time()

    def update(self):
        now = time.time()
        dt  = min(now - self.last_update, 2.0)
        self.last_update = now

        growth = (self.alpha * self.radius * math.log(self.k / self.radius)
                  if 0 < self.radius < self.k else 0.0)
        death  = 0.0
        if self.drug_efficacy > 0:
            death = (self.emax * self.radius * self.drug_efficacy
                     / (self.ic50 + self.drug_efficacy)) * self.radius

        self.radius = max(0.1, min(self.radius + (growth - death) * dt, self.k))
        if self.drug_efficacy > 0:
            self.drug_efficacy = max(0.0, self.drug_efficacy - self.drug_decay * dt)

        return {
            "radius":      round(self.radius, 4),
            "cellularity": round(self.alpha * 100, 2),
            "drug_level":  round(self.drug_efficacy, 4),
            "status":      "growing" if growth > death else "shrinking"
        }

    def inject_drug(self, amount):
        self.drug_efficacy = min(2.0, self.drug_efficacy + float(amount))

PUB_PORT   = int(os.getenv("ZMQ_PUB_PORT", 5555))
REP_PORT   = int(os.getenv("ZMQ_REP_PORT", 5556))
PUBLISH_HZ = float(os.getenv("PUBLISH_HZ", 50))

def main():
    left  = None
    right = None
    bootstrapped = False

    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    rep = ctx.socket(zmq.REP)
    pub.bind(f"tcp://0.0.0.0:{PUB_PORT}")
    rep.bind(f"tcp://0.0.0.0:{REP_PORT}")

    poller = zmq.Poller()
    poller.register(rep, zmq.POLLIN)

    print(f"\n{'='*50}")
    print(f"  ZMQ SERVER")
    print(f"    PUB port : {PUB_PORT}")
    print(f"    REP port : {REP_PORT}")
    print(f"    Rate     : {PUBLISH_HZ} Hz")
    print(f"{'='*50}\n")
    print(f"[ZMQ-SERVER]  Waiting for bootstrap from Windows...\n")

    interval = 1.0 / PUBLISH_HZ
    tick = 0

    while True:
    
        events = dict(poller.poll(0))
        if rep in events:
            try:
                msg = rep.recv_json()
                mtype = msg.get("type", "")

                if mtype == "BOOTSTRAP":
                    data = msg.get("initial_state", msg)
                    r_l  = float(data.get("left_radius",      data.get("left_tumor_radius")))
                    c_l  = float(data.get("left_cellularity",  data.get("left_tumor_cellularity")))
                    r_r  = float(data.get("right_radius",     data.get("right_tumor_radius")))
                    c_r  = float(data.get("right_cellularity", data.get("right_tumor_cellularity")))
                    p_id = msg.get("patient_id", "Unknown")

                    left  = TumorModel(r_l, c_l)
                    right = TumorModel(r_r, c_r)
                    bootstrapped = True

                    print(f"\n{'='*50}")
                    print(f"[ZMQ-SERVER] 🏁 Bootstrap — Patient: {p_id}")
                    print(f"  Left : R={r_l:.2f}mm, C={c_l:.2f}%")
                    print(f"  Right: R={r_r:.2f}mm, C={c_r:.2f}%")
                    print(f"{'='*50}\n")

                    rep.send_json({"status": "OK", "message": "Bootstrap applied"})

                elif mtype == "INJECT":
                    amount = float(msg.get("dosage", msg.get("amount", 0)))
                    left.inject_drug(amount)
                    right.inject_drug(amount)
                    print(f"[ZMQ-SERVER] 💉 Therapy: {amount}mg")
                    rep.send_json({"status": "OK"})

                else:
                    rep.send_json({"status": "ERROR", "message": f"Unknown type: {mtype}"})

            except Exception as e:
                print(f"[ZMQ-SERVER] REP error: {e}")
                try:
                    rep.send_json({"status": "ERROR", "message": str(e)})
                except:
                    pass

        
        if not bootstrapped or left is None or right is None:
            time.sleep(0.1)
            continue

       
        l = left.update()
        r = right.update()

        pub.send_multipart([
            b"tumor_updates",
            json.dumps({
                "type":      "TUMOR_STATE",
                "timestamp": time.time(),
                "left":      l,
                "right":     r
            }).encode()
        ])

        tick += 1
        log_every = max(1, int(PUBLISH_HZ * 2))
        if tick % log_every == 0:
            print(f"[ZMQ]  L:{l['radius']:.4f}mm ({l['status']}) "
                  f"| R:{r['radius']:.4f}mm ({r['status']})")

        time.sleep(interval)

if __name__ == "__main__":
    main()
