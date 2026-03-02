using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using uPLibrary.Networking.M2Mqtt;
using uPLibrary.Networking.M2Mqtt.Messages;
using Newtonsoft.Json;


public class MQTTClientQoS : MonoBehaviour
{
    [Header("MQTT Configuration")]
    [Tooltip("Indirizzo IP del broker MQTT")]
    public string brokerAddress = "127.0.0.1";
    
    [Tooltip("Porta del broker MQTT")]
    public int brokerPort = 1884;
    
    [Tooltip("Livello QoS per publish e subscribe")]
    [Range(0, 2)]
    public int qosLevel = 0;
    
    [Header("Topics")]
    [Tooltip("Topic su cui ascoltare gli aggiornamenti continui (TUMOR_STATE)")]
    public string updateTopic = "digitaltwin/breast/tumor";
    
    [Tooltip("Topic su cui inviare i comandi di terapia (ACTION)")]
    public string actionTopic = "digitaltwin/breast/action";
    
    [Header("Statistiche Runtime")]
    [SerializeField] private int messagesSent = 0;
    [SerializeField] private int messagesReceived = 0;
    

    private MqttClient client;
    private bool isConnected = false;
    
    private Queue<string> messageQueue = new Queue<string>();
    private object queueLock = new object();
    

    public event Action<TumorStatePayload> OnTumorUpdateReceived;
    public event Action OnConnected;
    public event Action OnDisconnected;

    void Start()
    {
        ConnectToBroker();
    }

    void Update()
    {
 
        ProcessMessageQueue();
    }

    
    public void ConnectToBroker()
    {
        try
        {
            Debug.Log($"[MQTT QoS{qosLevel}] Connected to {brokerAddress}:{brokerPort}");
            
            client = new MqttClient(brokerAddress, brokerPort, false, null, null, MqttSslProtocols.None);
            
            client.MqttMsgPublishReceived += OnMessageReceived;
            client.ConnectionClosed += OnConnectionClosed;
            
            string clientId = $"UnityDT_{SystemInfo.deviceUniqueIdentifier}_{qosLevel}";
            
            client.Connect(clientId);
            
            if (client.IsConnected)
            {
                isConnected = true;
                Debug.Log($"<color=green>Connected to MQTT broker (QoS {qosLevel})</color>");
                PrintQoSInfo();
                SubscribeToTopics();
                OnConnected?.Invoke();
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[MQTT] Connection error: {e.Message}");
            isConnected = false;
        }
    }

    private void SubscribeToTopics()
    {
        byte qos = (byte)qosLevel;

        string[] topics = new string[] { updateTopic };
        byte[] qosLevels = new byte[] { qos };
        
        client.Subscribe(topics, qosLevels);
        Debug.Log($"<color=cyan>Subscribed to {updateTopic} (QoS {qosLevel})</color>");
    }

    private void PrintQoSInfo()
    {
        string[] descriptions = new string[]
        {
            "QoS 0: At most once - No ACKs",
            "QoS 1: At least once - At least one ACK",
            "QoS 2: Exactly once - Full Handshake protocol"
        };
        
        Debug.Log($"<color=yellow>═══════════════════════════════════════</color>");
        Debug.Log($"<color=yellow>{descriptions[qosLevel]}</color>");
        Debug.Log($"<color=yellow>═══════════════════════════════════════</color>");
    }


    private void OnMessageReceived(object sender, MqttMsgPublishEventArgs e)
    {
        string message = System.Text.Encoding.UTF8.GetString(e.Message);
        

        lock (queueLock)
        {
            messageQueue.Enqueue(message);
        }
        
        messagesReceived++;
    }


    private void ProcessMessageQueue()
    {
        lock (queueLock)
        {
            while (messageQueue.Count > 0)
            {
                string message = messageQueue.Dequeue();
                HandleMessage(message);
            }
        }
    }


    private void HandleMessage(string message)
    {
        try
        {
            TumorStatePayload update = JsonConvert.DeserializeObject<TumorStatePayload>(message);
            

            if (update != null && update.type == "TUMOR_STATE")
            {
                OnTumorUpdateReceived?.Invoke(update);
            }
        }
        catch (Exception ex)
        {

            Debug.LogError($"[MQTT] Errore parsing messaggio: {ex.Message}\nMessaggio: {message}");
        }
    }

    public void SendTherapy(float amount)
    {
        if (!isConnected) return;

        try
        {

            var actionData = new { amount = amount };
            string json = JsonConvert.SerializeObject(actionData);
            byte[] payload = System.Text.Encoding.UTF8.GetBytes(json);
            
            client.Publish(actionTopic, payload, (byte)qosLevel, false);
            messagesSent++;
            
            Debug.Log($" Therapy sent: {amount}mg (QoS {qosLevel})");
        }
        catch (Exception e)
        {
            Debug.LogError($"[MQTT] Error sending therapy: {e.Message}");
        }
    }

    private void OnConnectionClosed(object sender, EventArgs e)
    {
        isConnected = false;
        Debug.LogWarning("<color=orange> Disconnected from MQTT broker</color>");
        OnDisconnected?.Invoke();
    }

    public void Disconnect()
    {
        if (client != null && client.IsConnected)
        {
            client.Disconnect();
            Debug.Log(" Disconnected from broker");
        }
        isConnected = false;
    }

    void OnDestroy()
    {
        Disconnect();
    }

    void OnApplicationQuit()
    {
        Disconnect();
    }
}



[Serializable]
public class TumorStatePayload
{
    public string type;          
    public double timestamp;     
    public TumorsData tumors;     
}

[Serializable]
public class TumorsData
{
    public TumorModelData left;
    public TumorModelData right;
}

[Serializable]
public class TumorModelData
{
    public float radius;
    public float cellularity;
    public float drug_level;
    public string status;   
}
