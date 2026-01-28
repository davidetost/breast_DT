using UnityEngine;
using System;
using System.Text;
using uPLibrary.Networking.M2Mqtt;
using uPLibrary.Networking.M2Mqtt.Messages;
using System.Collections.Generic;

[Serializable]
public class TumorData
{
    public float radius;
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
    [Header("MQTT")]
    public string brokerAddress = "localhost";
    public int brokerPort = 1883;
    public string tumorTopic = "digitaltwin/breast/tumor";
    public string statusTopic = "digitaltwin/system/status";
    public string bootstrapTopic = "digitaltwin/breast/bootstrap";

    [Header("References")]
    public TumorVisualization tumorVisualizer;

    [Header("Debug")]
    public bool debugLogs = true;

    private MqttClient client;
    private bool visualizationReady = false;

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
            client = new MqttClient(brokerAddress, brokerPort, false, null, null, MqttSslProtocols.None);
            client.MqttMsgPublishReceived += OnMessage;

            string id = "UnityTwin_" + UnityEngine.Random.Range(1000, 9999);
            client.Connect(id);

            client.Subscribe(
                new string[] { tumorTopic, statusTopic },
                new byte[] {
                    MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE,
                    MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE
                }
            );

            if (debugLogs)
                Debug.Log("[DigitalTwin] Connected to MQTT");

        }
        catch (Exception e)
        {
            Debug.LogError("[DigitalTwin] MQTT error: " + e.Message);
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
        if (msg == "READY")
        {
            SendBootstrap();
            return;
        }

        MQTTMessage data;
        try
        {
            data = JsonUtility.FromJson<MQTTMessage>(msg);
        }
        catch
        {
            return;
        }

        if (data?.tumors == null) return;

        if (!visualizationReady)
        {
            tumorVisualizer.InitializeFromData();
            visualizationReady = true;
        }

        if (data.tumors.left != null)
            tumorVisualizer.UpdateLeftTumor(data.tumors.left.radius);

        if (data.tumors.right != null)
            tumorVisualizer.UpdateRightTumor(data.tumors.right.radius);
    }

    void SendBootstrap()
    {
        string bootstrap = @"{
            ""meta"": { ""source"": ""unity"" },
            ""initial_state"": {
                ""left_tumor_radius"": 0.5,
                ""right_tumor_radius"": 0.7
            }
        }";

        client.Publish(
            bootstrapTopic,
            Encoding.UTF8.GetBytes(bootstrap),
            MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE,
            false
        );

        if (debugLogs)
            Debug.Log("[DigitalTwin] Bootstrap sent");
    }

    void OnApplicationQuit()
    {
        if (client != null && client.IsConnected)
            client.Disconnect();
    }
}
