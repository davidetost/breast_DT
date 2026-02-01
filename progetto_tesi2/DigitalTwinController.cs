using UnityEngine;
using System;
using System.Text;
using uPLibrary.Networking.M2Mqtt;
using uPLibrary.Networking.M2Mqtt.Messages;
using System.Collections.Generic;

// --- CLASSI DATI ---
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
public class MetaPayload
{
    public string patient_id;
    public string source;
}

[Serializable]
public class MQTTMessage
{
    public string type;
    public double timestamp;
    public MetaPayload meta;
    public TumorsPayload tumors;
}

public class DigitalTwinController : MonoBehaviour
{
    [Header("MQTT")]
    public string brokerAddress = "192.168.1.143"; // IP della VM
    public int brokerPort = 1883;
    public string tumorTopic = "digitaltwin/breast/tumor";
    public string actionTopic = "digitaltwin/breast/action";

    [Header("Visuals")]
    public GameObject leftSphere;   // Trascina la Sfera SX qui
    public GameObject rightSphere;  // Trascina la Sfera DX qui
    public float sphereScaleFactor = 0.5f; // Moltiplicatore grandezza

    [Header("Debug")]
    public bool debugLogs = true;

    private MqttClient client;
    private Queue<string> messageQueue = new Queue<string>();
    private object queueLock = new object();

    void Start()
    {
        Connect();
    }

    void Connect()
    {
        try
        {
            client = new MqttClient(brokerAddress);
            client.MqttMsgPublishReceived += OnMessage;
            string id = "UnityTwin_" + UnityEngine.Random.Range(1000, 9999);
            client.Connect(id);
            
            client.Subscribe(
                new string[] { tumorTopic, "digitaltwin/system/status" },
                new byte[] { MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE, MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE }
            );

            if (debugLogs) Debug.Log($"[DigitalTwin] Connesso a {brokerAddress}");
        }
        catch (Exception e)
        {
            Debug.LogError("[DigitalTwin] Errore connessione: " + e.Message);
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
        // 1. Elabora messaggi dalla coda
        lock (queueLock)
        {
            while (messageQueue.Count > 0)
            {
                ProcessMessage(messageQueue.Dequeue());
            }
        }

        // 2. Input Terapia (Barra Spaziatrice)
        // NOTA: Se questo da errore, vai su Edit -> Project Settings -> Player -> Active Input Handling -> Imposta su "Both"
        if (Input.GetKeyDown(KeyCode.Space))
        {
            SendTherapyCommand();
        }
    }

    void ProcessMessage(string msg)
    {
        // Ignora messaggi di stato o bootstrap per la visualizzazione
        if (msg.Contains("READY") || msg.Contains("BOOTSTRAP")) return;

        try
        {
            MQTTMessage data = JsonUtility.FromJson<MQTTMessage>(msg);

            if (data != null && data.tumors != null)
            {
                UpdateVisuals(data.tumors);
            }
        }
        catch
        {
            // Ignora errori di parsing su messaggi non pertinenti
        }
    }

    void UpdateVisuals(TumorsPayload tumors)
    {
        // --- SFERA SINISTRA ---
        if (leftSphere != null && tumors.left != null)
        {
            // Aggiorna Dimensione
            float scale = tumors.left.radius * 2 * sphereScaleFactor;
            leftSphere.transform.localScale = new Vector3(scale, scale, scale);

            // Aggiorna Colore (Verde = Cura, Rosso = Male)
            Renderer rend = leftSphere.GetComponent<Renderer>();
            if (rend != null)
                rend.material.color = (tumors.left.status == "shrinking") ? Color.green : Color.red;
        }

        // --- SFERA DESTRA ---
        if (rightSphere != null && tumors.right != null)
        {
            float scale = tumors.right.radius * 2 * sphereScaleFactor;
            rightSphere.transform.localScale = new Vector3(scale, scale, scale);

            Renderer rend = rightSphere.GetComponent<Renderer>();
            if (rend != null)
                rend.material.color = (tumors.right.status == "shrinking") ? Color.green : Color.red;
        }
    }

    void SendTherapyCommand()
    {
        if (client != null && client.IsConnected)
        {
            string jsonPayload = "{\"type\": \"MANUAL_THERAPY\", \"dosage\": 0.8}";
            client.Publish(actionTopic, Encoding.UTF8.GetBytes(jsonPayload), MqttMsgBase.QOS_LEVEL_EXACTLY_ONCE, false);
            Debug.Log("[Unity] 💉 Terapia Inviata!");
        }
    }

    void OnApplicationQuit()
    {
        if (client != null && client.IsConnected)
            client.Disconnect();
    }
}