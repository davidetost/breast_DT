using UnityEngine;
using System;
using System.Text;
using System.Threading;
using NetMQ;
using NetMQ.Sockets;
using System.Collections.Generic;

// --- CLASSI DATI CORRETTE PER JSONUTILITY ---
[Serializable]
public class ZMQTumorData
{
    public float radius;
    public float cellularity;
    public float drug_level;
    public string status;
}

// AGGIUNTA FONDAMENTALE: Wrapper per gestire l'oggetto "tumors" nel JSON
[Serializable]
public class ZMQTumorContainer 
{
    public ZMQTumorData left;
    public ZMQTumorData right;
}

[Serializable]
public class ZMQTumorState
{
    public string type;
    public double timestamp;
    
    // MODIFICA: Unity non trova "left" nella root, ma dentro "tumors"
    public ZMQTumorContainer tumors; 
}
// -------------------------------------------

public class DigitalTwinController_ZMQ : MonoBehaviour
{
    [Header("ZeroMQ Configuration")]
    public string serverAddress = "127.0.0.1";
    public int telemetryPort = 5555;
    public int commandPort = 5556;

    [Header("Visualization")]
    public TumorVisualization tumorVis;

    [Header("Therapy Settings")]
    public float manualTherapyDosage = 0.8f;

    [Header("Debug")]
    public bool showDebugGUI = true;

    private SubscriberSocket subSocket;
    private RequestSocket reqSocket;
    private Thread receiverThread;
    private bool isRunning = false;
    private bool isConnected = false;

    private Queue<ZMQTumorState> messageQueue = new Queue<ZMQTumorState>();
    private object queueLock = new object();

    private string lastStatusMessage = "In attesa...";
    private string lastDataMessage = "Nessun dato";
    private int updateCount = 0;
    private float lastLeftRadius = 0f;
    private float lastRightRadius = 0f;

    void OnEnable()
    {
        if (tumorVis == null)
            tumorVis = FindFirstObjectByType<TumorVisualization>();
        
        // --- FIX 1: INIZIALIZZAZIONE VISUALIZZAZIONE ---
        if (tumorVis != null)
        {
            tumorVis.InitializeFromData(); // <--- FONDAMENTALE PER TOGLIERE I WARNING GIALLI
        }
        else 
        {
            Debug.LogError("[ZMQ] ❌ TumorVisualization non trovato!");
        }
        // ----------------------------------------------

        Connect();
    }

    void Connect()
    {
        try
        {
            Debug.Log($"[ZMQ] Connessione a {serverAddress}:{telemetryPort}/{commandPort}...");

            AsyncIO.ForceDotNet.Force();

            subSocket = new SubscriberSocket();
            subSocket.Connect($"tcp://{serverAddress}:{telemetryPort}");
            subSocket.Subscribe("tumor_updates");

            reqSocket = new RequestSocket();
            reqSocket.Connect($"tcp://{serverAddress}:{commandPort}");

            isConnected = true;
            isRunning = true;

            Debug.Log("[ZMQ] ✓ Connesso!");

            receiverThread = new Thread(ReceiverLoop) { IsBackground = true };
            receiverThread.Start();
        }
        catch (Exception e)
        {
            Debug.LogError($"[ZMQ] Errore: {e.Message}");
            isConnected = false;
        }
    }

    void ReceiverLoop()
    {
        try
        {
            while (isRunning && subSocket != null)
            {
                var frames = new List<byte[]>();

                // Timeout breve per non bloccare il thread alla chiusura
                if (!subSocket.TryReceiveMultipartBytes(TimeSpan.FromSeconds(0.5), ref frames))
                    continue;

                if (frames.Count < 2) continue;

                string json = Encoding.UTF8.GetString(frames[1]);
                
                // Debug opzionale: decommenta se vedi ancora 0.00 per vedere il JSON grezzo
                // Debug.Log($"JSON RAW: {json}");

                ZMQTumorState state = JsonUtility.FromJson<ZMQTumorState>(json);

                if (state != null && state.type == "TUMOR_STATE")
                {
                    lock (queueLock)
                    {
                        messageQueue.Enqueue(state);
                    }
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[ZMQ] Thread error: {e.Message}");
        }
    }

    void Update()
    {
        if (!isConnected) return;
        lock (queueLock)
        {
            while (messageQueue.Count > 0)
            {
                ProcessTumorState(messageQueue.Dequeue());
            }
        }
    }

    void ProcessTumorState(ZMQTumorState state)
    {
        updateCount++;
        
        // --- FIX 2: LETTURA CORRETTA DELLA STRUTTURA JSON ---
        // Se il JSON ha "tumors": { "left": ... }, dobbiamo passare per state.tumors
        if (state.tumors != null)
        {
            lastLeftRadius = state.tumors.left?.radius ?? 0f;
            lastRightRadius = state.tumors.right?.radius ?? 0f;
        }
        // Fallback nel caso il JSON fosse piatto (senza "tumors")
        else 
        {
             // Tentativo disperato se la struttura fosse diversa, ma con la classe sopra non dovrebbe servire
             lastLeftRadius = 0f; 
             lastRightRadius = 0f;
        }
        // ----------------------------------------------------

        if (tumorVis != null)
        {
            tumorVis.UpdateLeftTumor(lastLeftRadius);
            tumorVis.UpdateRightTumor(lastRightRadius);
        }

        lastDataMessage = $"L: {lastLeftRadius:F2} | R: {lastRightRadius:F2}";
    }

    public void SendTherapyCommandFromUI()
    {
        if (!isConnected) return;

        try
        {
            var command = $"{{\"type\":\"INJECT\",\"dosage\":{manualTherapyDosage}}}";
            reqSocket.SendFrame(command);
            
            // TryReceiveFrameString è bloccante, usiamolo con cautela nel main thread
            if (reqSocket.TryReceiveFrameString(TimeSpan.FromSeconds(0.5), out string response))
            {
                Debug.Log($"[ZMQ] 💉 Terapia inviata. Risposta: {response}");
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[ZMQ] Errore invio terapia: {e.Message}");
        }
    }

    void OnDisable() => Disconnect();
    void OnApplicationQuit() => Disconnect();

    void Disconnect()
    {
        isRunning = false;
        // Aspettiamo che il thread finisca gentilmente
        if (receiverThread != null && receiverThread.IsAlive)
        {
            receiverThread.Join(500); 
        }

        subSocket?.Close();
        subSocket?.Dispose();
        reqSocket?.Close();
        reqSocket?.Dispose();
        NetMQConfig.Cleanup(false);
        isConnected = false;
    }

    void OnGUI()
    {
        if (!showDebugGUI) return;

        GUIStyle style = new GUIStyle { fontSize = 16 };
        style.normal.textColor = Color.white;

        GUILayout.BeginArea(new Rect(10, 10, 600, 200));
        GUILayout.Label("━━━ ZeroMQ TWIN ━━━", style);

        style.normal.textColor = isConnected ? Color.green : Color.red;
        GUILayout.Label($"Status: {(isConnected ? "✓ OK" : "✗ OFF")}", style);

        style.normal.textColor = Color.cyan;
        GUILayout.Label($"Data: {lastDataMessage}", style);
        GUILayout.Label($"Updates: {updateCount}", style);

        if (GUILayout.Button($"💉 THERAPY ({manualTherapyDosage}mg)"))
            SendTherapyCommandFromUI();

        GUILayout.EndArea();
    }
}