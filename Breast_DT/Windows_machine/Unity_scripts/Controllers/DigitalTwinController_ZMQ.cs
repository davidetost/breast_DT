using UnityEngine;
using System;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using NetMQ;
using NetMQ.Sockets;
using TMPro;
using UnityEngine.UI;

public class DigitalTwinController_ZMQ_Scene : MonoBehaviour
{

    [Serializable] 
    public class ZmqTumorData  
    { 
        public float radius; 
        public float cellularity; 
        public float drug_level; 
        public string status; 
    }

    [Serializable] 
    public class ZmqTumorState 
    { 
        public string type; 
        public double timestamp; 
        public ZmqTumorData left; 
        public ZmqTumorData right; 
    }
    // ──────────────────────────────────────────────────────────────

    [Header("── ZeroMQ ────────────────────────")]
    public string serverAddress = "127.0.0.1";
    public int    telemetryPort = 5555;
    public int    commandPort   = 5556;

    [Header("── Visualization ─────────────────")]
    public TumorVisualization tumorVis;

    [Header("── Therapy ──────────────────────")]
    public float therapyDosage = 0.8f;

    [Header("── UI References ────────────────")]
    public TextMeshProUGUI connectionText;
    public TextMeshProUGUI tumorDataText;
    public TextMeshProUGUI metricsText;
    public TextMeshProUGUI statusText;
    public Button          therapyButton;
    public Image           therapyButtonImage;

    [Header("── Debug GUI Overlay ───────────")]
    public bool showDebugOverlay = true;


    private SubscriberSocket sub;
    private RequestSocket    req;
    private Thread           rxThread;
    private bool             running   = false;
    private bool             connected = false;

    private Queue<ZmqTumorState> msgQueue  = new Queue<ZmqTumorState>();
    private object               queueLock = new object();

    private float  lastLeft  = 0f, lastRight = 0f;
    private string leftSt    = "—", rightSt   = "—";

    private int   updateCount = 0;
    private float latCur = 0f, latSum = 0f, latMin = float.MaxValue, latMax = 0f, latAvg = 0f;

    private bool  flash = false;
    private float flashT = 0f;
    private const float FLASH_DUR = 0.4f;

    // ── lifecycle ─────────────────────────────────────────────────
    void Start()
    {
        if (tumorVis == null) tumorVis = FindFirstObjectByType<TumorVisualization>();
        if (tumorVis != null) tumorVis.InitializeFromData();
        if (therapyButton != null) therapyButton.onClick.AddListener(SendTherapy);
        SetConnStatus("Connecting...", Color.yellow);
        Connect();
    }

    void Update()
    {
        if (!connected) return;

        lock (queueLock)
            while (msgQueue.Count > 0) Process(msgQueue.Dequeue());

        if (flash)
        {
            flashT += Time.deltaTime;
            if (therapyButtonImage != null)
                therapyButtonImage.color = Color.Lerp(Color.green, Color.white, flashT / FLASH_DUR);
            if (flashT >= FLASH_DUR) { flash = false; flashT = 0f; }
        }
    }

    void OnDisable() => Disconnect();
    void OnApplicationQuit() => Disconnect();


    void Connect()
    {
        try
        {
            AsyncIO.ForceDotNet.Force();

            sub = new SubscriberSocket();
            sub.Connect($"tcp://{serverAddress}:{telemetryPort}");
            sub.Subscribe("");

            req = new RequestSocket();
            req.Connect($"tcp://{serverAddress}:{commandPort}");

            connected = true;
            running   = true;

            rxThread = new Thread(ReceiveLoop) { IsBackground = true };
            rxThread.Start();

            SetConnStatus("● CONNECTED", Color.green);
            Debug.Log("[ZMQ] ✓ Connected.");
        }
        catch (Exception e)
        {
            SetConnStatus("✗ ERROR", Color.red);
            Debug.LogError($"[ZMQ] {e.Message}");
        }
    }

    void Disconnect()
    {
        running = false;
        rxThread?.Join(600);
        sub?.Close(); sub?.Dispose(); sub = null;
        req?.Close(); req?.Dispose(); req = null;
        try { NetMQConfig.Cleanup(false); } catch { }
        connected = false;
    }


    void ReceiveLoop()
    {
        try{
        while (running && sub != null)
        {
            var frames = new List<byte[]>();
            if (!sub.TryReceiveMultipartBytes(TimeSpan.FromSeconds(1), ref frames) || frames.Count < 2)
                continue;

            string json  = Encoding.UTF8.GetString(frames[1]);
            
            var state = JsonUtility.FromJson<ZmqTumorState>(json);

            if (state?.type == "TUMOR_STATE")
            {
                if (state.left == null || state.right == null)
                    Debug.LogWarning($"[ZMQ] Parsing failed: left={state.left}, right={state.right}");
                    
                lock (queueLock) msgQueue.Enqueue(state);
            }
        }
    } catch (Exception e)
        {
            UnityEngine.Debug.LogError($"[ZMQ] CRITICAL: reception thread crashed! {e.Message}\n{e.StackTrace}");
        } }


    void Process(ZmqTumorState st)
    {
        double nowUnix = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
        latCur = Mathf.Abs((float)((nowUnix - st.timestamp) * 1000f));
        latSum += latCur;
        updateCount++;
        latAvg = latSum / updateCount;
        if (latCur < latMin) latMin = latCur;
        if (latCur > latMax) latMax = latCur;

        if (st.left  != null) { lastLeft  = st.left.radius;  leftSt  = st.left.status  ?? "—"; }
        if (st.right != null) { lastRight = st.right.radius; rightSt = st.right.status ?? "—"; }

        tumorVis?.UpdateLeftTumor(lastLeft);
        tumorVis?.UpdateRightTumor(lastRight);
        RefreshUI();
    }


    public void SendTherapy()
    {
        if (!connected || req == null) return;
        try
        {
            req.SendFrame($"{{\"type\":\"INJECT\",\"dosage\":{therapyDosage}}}");
            req.TryReceiveFrameString(TimeSpan.FromSeconds(2), out string resp);
            Debug.Log($"[ZMQ] 💉 {therapyDosage}mg → {resp}");
            flash = true; flashT = 0f;
        }
        catch (Exception e) { Debug.LogError($"[ZMQ] Therapy: {e.Message}"); }
    }


    void RefreshUI()
    {
        if (tumorDataText != null)
            tumorDataText.text = $"Left:  {lastLeft:F4} mm  [{leftSt}]\nRight: {lastRight:F4} mm  [{rightSt}]";

        if (metricsText != null)
            metricsText.text =
                $"Updates : {updateCount}\n" +
                $"Latency : {latCur:F1} ms\n" +
                $"Avg     : {latAvg:F1} ms\n" +
                $"Min/Max : {latMin:F1} / {latMax:F1} ms";

        if (statusText != null)
            statusText.text = updateCount > 0 ? " STREAMING" : " WAITING BOOTSTRAP";
    }

    void SetConnStatus(string msg, Color col)
    {
        if (connectionText != null) { connectionText.text = msg; connectionText.color = col; }
    }


    void OnGUI()
    {
        if (!showDebugOverlay) return;

        GUI.Box(new Rect(8, 8, 330, 195), "");

        GUIStyle title = new GUIStyle { fontSize = 14, fontStyle = FontStyle.Bold };
        title.normal.textColor = new Color(0.5f, 0.9f, 0.3f);

        GUIStyle norm = new GUIStyle { fontSize = 13 };
        norm.normal.textColor = Color.white;

        GUIStyle ok = new GUIStyle { fontSize = 13 };
        ok.normal.textColor = Color.green;

        GUIStyle err = new GUIStyle { fontSize = 13 };
        err.normal.textColor = new Color(1f, 0.4f, 0.4f);

        GUILayout.BeginArea(new Rect(14, 14, 316, 182));
        GUILayout.Label("  ZeroMQ  DIGITAL  TWIN", title);
        GUILayout.Space(3);
        GUILayout.Label($"Status  : {(connected ? " ONLINE" : " OFFLINE")}", connected ? ok : err);
        GUILayout.Label($"Tumor L : {lastLeft:F4} mm  [{leftSt}]",  norm);
        GUILayout.Label($"Tumor R : {lastRight:F4} mm  [{rightSt}]", norm);
        GUILayout.Space(3);
        GUILayout.Label($"Updates : {updateCount}", norm);
        GUILayout.Label($"Latency : {latCur:F1} ms  (avg {latAvg:F1})", norm);
        GUILayout.Label($"Min/Max : {latMin:F1} / {latMax:F1} ms", norm);
        GUILayout.Space(5);
        if (GUILayout.Button($"  Inject Therapy  ({therapyDosage} mg)"))
            SendTherapy();
        GUILayout.EndArea();
    }
}
