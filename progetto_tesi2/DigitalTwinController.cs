using UnityEngine;
using System;
using System.Text;
using uPLibrary.Networking.M2Mqtt;
using uPLibrary.Networking.M2Mqtt.Messages;

// Simple JSON classes for parsing
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
    public double timestamp;
    public TumorsPayload tumors;
}

public class DigitalTwinController : MonoBehaviour
{
    [Header("MQTT Configuration")]
    [Tooltip("MQTT Broker address (e.g., localhost or 192.168.1.100)")]
    public string brokerAddress = "localhost";
    
    [Tooltip("MQTT Broker port (default: 1883)")]
    public int brokerPort = 1883;
    
    [Tooltip("Topic to receive tumor updates")]
    public string subscribeTopic = "digitaltwin/breast/tumor";
    
    [Tooltip("Topic to send bootstrap message")]
    public string bootstrapTopic = "digitaltwin/breast/bootstrap";
    
    [Tooltip("Topic to check server status")]
    public string statusTopic = "digitaltwin/system/status";
    
    [Header("Patient Configuration")]
    public string patientId = "PATIENT_001";
    public int patientAge = 45;
    
    [Header("References")]
    public TumorVisualization tumorVisualizer;
    
    [Header("Debug")]
    public bool showDebugLogs = true;
    public bool autoConnectOnStart = true;
    
    private MqttClient mqttClient;
    private bool isConnected = false;
    private bool serverReady = false;
    
    // Thread-safe queue for processing messages on main thread
    private System.Collections.Generic.Queue<string> messageQueue = 
        new System.Collections.Generic.Queue<string>();
    private object queueLock = new object();

    void Start()
    {
        if (tumorVisualizer == null)
        {
            Debug.LogError("[DigitalTwin] TumorVisualization reference is missing!");
            return;
        }
        
        if (autoConnectOnStart)
        {
            ConnectToMQTT();
        }
    }

    public void ConnectToMQTT()
    {
        try
        {
            if (showDebugLogs)
                Debug.Log($"[DigitalTwin] Connecting to MQTT broker at {brokerAddress}:{brokerPort}...");
            
            mqttClient = new MqttClient(brokerAddress, brokerPort, false, null, null, MqttSslProtocols.None);
            
            // Set up callbacks
            mqttClient.MqttMsgPublishReceived += OnMessageReceived;
            
            // Connect with a unique client ID
            string clientId = $"UnityDigitalTwin_{UnityEngine.Random.Range(1000, 9999)}";
            mqttClient.Connect(clientId);
            
            isConnected = true;
            
            if (showDebugLogs)
                Debug.Log("[DigitalTwin] ✓ Connected to MQTT broker!");
            
            // Subscribe to topics
            mqttClient.Subscribe(new string[] { subscribeTopic }, new byte[] { MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE });
            mqttClient.Subscribe(new string[] { statusTopic }, new byte[] { MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE });
            
            if (showDebugLogs)
                Debug.Log($"[DigitalTwin] Subscribed to: {subscribeTopic} and {statusTopic}");
            
        }
        catch (Exception e)
        {
            Debug.LogError($"[DigitalTwin] MQTT Connection Error: {e.Message}");
            isConnected = false;
        }
    }

    public void SendBootstrap()
    {
        if (!isConnected || mqttClient == null)
        {
            Debug.LogWarning("[DigitalTwin] Not connected to MQTT. Cannot send bootstrap.");
            return;
        }
        
        // Create bootstrap message matching your Python format
        string bootstrapJson = $@"{{
            ""meta"": {{
                ""patient_id"": ""{patientId}"",
                ""age"": {patientAge},
                ""timestamp"": {DateTimeOffset.UtcNow.ToUnixTimeSeconds()}
            }},
            ""initial_state"": {{
                ""left_tumor_radius"": 0.5,
                ""right_tumor_radius"": 0.7
            }}
        }}";
        
        mqttClient.Publish(bootstrapTopic, Encoding.UTF8.GetBytes(bootstrapJson), 
                          MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE, false);
        
        if (showDebugLogs)
            Debug.Log($"[DigitalTwin] 📤 Bootstrap sent for patient {patientId}");
    }

    private void OnMessageReceived(object sender, MqttMsgPublishEventArgs e)
    {
        string message = Encoding.UTF8.GetString(e.Message);
        
        // Add to queue for main thread processing
        lock (queueLock)
        {
            messageQueue.Enqueue(message);
        }
    }

    void Update()
    {
        // Process MQTT messages on main thread
        lock (queueLock)
        {
            while (messageQueue.Count > 0)
            {
                string message = messageQueue.Dequeue();
                ProcessMessage(message);
            }
        }
    }

    private void ProcessMessage(string message)
    {
        try
        {
            // Check if it's a status message
            if (message == "READY")
            {
                serverReady = true;
                if (showDebugLogs)
                    Debug.Log("[DigitalTwin] 🟢 Edge Server is READY!");
                
                // Automatically send bootstrap when server is ready
                SendBootstrap();
                return;
            }
            
            // Parse tumor data
            MQTTMessage data = JsonUtility.FromJson<MQTTMessage>(message);
            
            if (data != null && data.tumors != null)
            {
                // Update tumor visualizations
                if (data.tumors.left != null)
                {
                    tumorVisualizer.UpdateLeftTumor(data.tumors.left.radius);
                }
                
                if (data.tumors.right != null)
                {
                    tumorVisualizer.UpdateRightTumor(data.tumors.right.radius);
                }
                
                // Optional: Log status changes
                if (showDebugLogs && UnityEngine.Random.value < 0.05f) // Log 5% of messages
                {
                    Debug.Log($"[DigitalTwin] L: {data.tumors.left.radius:F3} ({data.tumors.left.status}) | " +
                             $"R: {data.tumors.right.radius:F3} ({data.tumors.right.status})");
                }
            }
        }
        catch (Exception ex)
        {
            if (showDebugLogs)
                Debug.LogWarning($"[DigitalTwin] Error parsing message: {ex.Message}");
        }
    }

    void OnApplicationQuit()
    {
        if (mqttClient != null && isConnected)
        {
            mqttClient.Disconnect();
            if (showDebugLogs)
                Debug.Log("[DigitalTwin] Disconnected from MQTT broker.");
        }
    }

    // Public methods for UI buttons or external control
    public bool IsConnected() => isConnected;
    public bool IsServerReady() => serverReady;
    
    public void Disconnect()
    {
        if (mqttClient != null && isConnected)
        {
            mqttClient.Disconnect();
            isConnected = false;
            serverReady = false;
        }
    }
}