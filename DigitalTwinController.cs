using UnityEngine;
using System;
using System.Text;
using System.Security.Authentication;
using uPLibrary.Networking.M2Mqtt;
using uPLibrary.Networking.M2Mqtt.Messages;
using System.Collections.Generic;

[Serializable]
public class TumorData
{
    public float radius;
    public float cellularity;
    public float drug_level;
    public string status;
}

[Serializable]
public class TumorsPayload
{
    public TumorData left;
    public TumorData right;
}

[Serializable]
public class MQTTMessage
{
    public string type;
    public double timestamp;
    public TumorsPayload tumors;
}

public class DigitalTwinController : MonoBehaviour
{
    [Header("MQTT Configuration")]
    public string brokerAddress = "127.0.0.1";
    public int brokerPort = 1884;  // ← Port Forward VirtualBox
    public string tumorTopic = "digitaltwin/breast/tumor";
    public string actionTopic = "digitaltwin/breast/action";

    [Header("Visualization")]
    public TumorVisualization tumorVis;

    [Header("Therapy Settings")]
    public float manualTherapyDosage = 0.8f;

    [Header("Debug")]
    public bool showDebugGUI = true;

    private MqttClient client;
    private Queue<string> messageQueue = new Queue<string>();
    private object queueLock = new object();

    private string lastStatusMessage = "In attesa...";
    private string lastDataMessage = "Nessun dato";
    private float lastLeftRadius = 0f;
    private float lastRightRadius = 0f;
    private int updateCount = 0;
    private bool visualizationInitialized = false;

    void OnEnable()
    {
        Application.targetFrameRate = 60;

        if (tumorVis == null)
        {
            tumorVis = FindFirstObjectByType<TumorVisualization>();
            if (tumorVis == null)
            {
                Debug.LogError("[MQTT] ❌ TumorVisualization non trovato!");
                return;
            }
        }

        Connect();
    }

    void Connect()
    {
        try
        {
            Debug.Log($"[MQTT] Connessione a {brokerAddress}:{brokerPort}...");

            client = new MqttClient(brokerAddress, brokerPort, false, null, null, MqttSslProtocols.None);
            client.MqttMsgPublishReceived += OnMessage;

            string clientId = "UnityTwin_" + UnityEngine.Random.Range(1000, 9999);
            client.Connect(clientId);

            if (client.IsConnected)
            {
                Debug.Log("[MQTT] ✓ CONNESSO!");
                client.Subscribe(
                    new string[] { tumorTopic },
                    new byte[] { MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE }
                );
                lastStatusMessage = "MQTT: Connesso";
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[MQTT] ❌ Errore: {e.Message}");
            lastStatusMessage = "MQTT: Errore";
        }
    }

    void OnMessage(object sender, MqttMsgPublishEventArgs e)
    {
        string msg = Encoding.UTF8.GetString(e.Message);
        lock (queueLock)
        {
            messageQueue.Enqueue(msg);
        }
    }

    void Update()
    {
        if (client==null || !client.IsConnected) return;
        lock (queueLock)
        {
            while (messageQueue.Count > 0)
            {
                ProcessMessage(messageQueue.Dequeue());
            }
        }
    }

    void ProcessMessage(string msg)
    {
        try
        {
            MQTTMessage data = JsonUtility.FromJson<MQTTMessage>(msg);

            if (data != null && data.type == "TUMOR_STATE" && data.tumors != null)
            {
                if (!visualizationInitialized && tumorVis != null)
                {
                    tumorVis.InitializeFromData();
                    visualizationInitialized = true;
                }

                updateCount++;
                lastLeftRadius = data.tumors.left?.radius ?? 0f;
                lastRightRadius = data.tumors.right?.radius ?? 0f;

                UpdateVisuals(data.tumors);

                lastStatusMessage = "MQTT: Streaming";
                lastDataMessage = $"L: {lastLeftRadius:F2} | R: {lastRightRadius:F2}";
            }
        }
        catch { }
    }

    void UpdateVisuals(TumorsPayload tumors)
    {
        if (tumorVis == null) return;

        if (tumors.left != null) tumorVis.UpdateLeftTumor(tumors.left.radius);
        if (tumors.right != null) tumorVis.UpdateRightTumor(tumors.right.radius);
    }

    public void SendTherapyCommandFromUI()
    {
        if (client == null || !client.IsConnected)
        {
            Debug.LogError("[MQTT] ❌ Non connesso!");
            return;
        }

        // ✅ FIX: Server Python legge payload.get("amount")
        string jsonPayload = $"{{\"amount\": {manualTherapyDosage}}}";

        try
        {
            client.Publish(actionTopic, Encoding.UTF8.GetBytes(jsonPayload), MqttMsgBase.QOS_LEVEL_EXACTLY_ONCE, false);
            Debug.Log($"[MQTT] 💉 Terapia inviata: {manualTherapyDosage}mg");
        }
        catch (Exception e)
        {
            Debug.LogError($"[MQTT] ❌ Errore: {e.Message}");
        }
    }

    void OnDisable()
    {
        if (client != null && client.IsConnected)
        {
            client.Disconnect();
            Debug.Log("[MQTT] Disconnesso.");
        }
    }

    void OnApplicationQuit()
    {
        if (client != null && client.IsConnected)
            client.Disconnect();
    }
    public bool IsConnected()
    {
        return client != null && client.IsConnected;
    }
    void OnGUI()
    {
        if (!showDebugGUI) return;

        GUIStyle style = new GUIStyle { fontSize = 16 };
        style.normal.textColor = Color.white;

        GUILayout.BeginArea(new Rect(10, 10, 600, 200));
        GUILayout.Label("━━━ MQTT TWIN ━━━", style);

        style.normal.textColor = (client != null && client.IsConnected) ? Color.green : Color.red;
        GUILayout.Label($"Status: {(client != null && client.IsConnected ? "✓ OK" : "✗ OFF")}", style);

        style.normal.textColor = Color.cyan;
        GUILayout.Label($"Data: {lastDataMessage}", style);
        GUILayout.Label($"Updates: {updateCount}", style);

        if (GUILayout.Button($"💉 THERAPY ({manualTherapyDosage}mg)"))
            SendTherapyCommandFromUI();

        GUILayout.EndArea();
    }

}