using UnityEngine;
using System;
using System.Text;
using uPLibrary.Networking.M2Mqtt; // Libreria M2Mqtt
using uPLibrary.Networking.M2Mqtt.Messages;

public class DigitalTwinClient : MonoBehaviour
{
    [Header("Visualizzazione")]
    public Transform tumorObject; // Trascina qui la sfera rossa

    [Header("Configurazione Rete")]
    public string brokerAddress = "127.0.0.1"; // Localhost (Bridge verso VM)
    public string topic = "digitaltwin/breast/tumor";

    private MqttClient client;
    
    // Variabili per la sincronizzazione (Thread Safety)
    // MQTT gira su un thread diverso da Unity, quindi non possiamo modificare 
    // la grafica direttamente nel callback di ricezione.
    private float targetRadius = 0.0f;
    private bool updateReceived = false;

    void Start()
    {
        ConnectToBroker();
    }

    void ConnectToBroker()
    {
        try
        {
            // Creiamo il client
            client = new MqttClient(brokerAddress);

            // Registriamo l'evento "Messaggio Ricevuto"
            client.MqttMsgPublishReceived += OnMessageReceived;

            // Ci connettiamo con un ID casuale
            string clientId = Guid.NewGuid().ToString();
            client.Connect(clientId);

            // Ci iscriviamo al topic
            client.Subscribe(new string[] { topic }, new byte[] { MqttMsgBase.QOS_LEVEL_AT_LEAST_ONCE });

            Debug.Log($"<color=green>Connesso al Broker MQTT: {brokerAddress}</color>");
        }
        catch (Exception e)
        {
            Debug.LogError($"Errore connessione MQTT: {e.Message}");
        }
    }

    // Questo viene eseguito dal Thread di rete (background)
    void OnMessageReceived(object sender, MqttMsgPublishEventArgs e)
    {
        string jsonMessage = Encoding.UTF8.GetString(e.Message);
        // Debug.Log("MSG: " + jsonMessage); // Scommenta per debuggare

        // Il JSON arriva così: 
        // {"timestamp": 1234.5, "status": {"healthy": false, "radius": 1.2}}
        
        // Usiamo il parser nativo di Unity
        try 
        {
            RootData data = JsonUtility.FromJson<RootData>(jsonMessage);
            
            if (!data.status.healthy)
            {
                // Salviamo il dato per usarlo nel prossimo Update()
                targetRadius = data.status.radius;
                updateReceived = true;
            }
        }
        catch (Exception ex)
        {
            Debug.LogError("Errore parsing JSON: " + ex.Message);
        }
    }

    // Questo viene eseguito dal Main Thread di Unity (ogni frame)
void Update()
    {
        if (updateReceived)
        {
            // Calcolo dimensione base
            float targetDiameter = targetRadius * 2.0f;
            
            // Effetto "Respiro/Pulsazione":
            // Aggiungiamo una piccola variazione sinusoidale al diametro
            float pulsation = Mathf.Sin(Time.time * 5.0f) * 0.05f; // 5.0f è la velocità, 0.05f l'intensità
            
            float finalScale = targetDiameter + pulsation;

            // Applichiamo la scala in modo fluido (Lerp)
            tumorObject.localScale = Vector3.Lerp(tumorObject.localScale, 
                                                  new Vector3(finalScale, finalScale, finalScale), 
                                                  Time.deltaTime * 5f);
        }
    }

    void OnApplicationQuit()
    {
        if (client != null && client.IsConnected)
        {
            client.Disconnect();
        }
    }

    // --- STRUTTURE DATI PER IL JSON ---
    [Serializable]
    public class RootData
    {
        public double timestamp;
        public StatusData status;
    }

    [Serializable]
    public class StatusData
    {
        public bool healthy;
        public float radius;
    }
}