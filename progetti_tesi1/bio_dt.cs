using UnityEngine;
using System.Collections.Concurrent;
using System.Threading;
using System;

// Import delle librerie di rete
using NetMQ;
using NetMQ.Sockets;

public class BioDigitalTwin : MonoBehaviour
{
    public enum ProtocolType { ZeroMQ, MQTT }

    [Header("Configurazione Rete")]
    public ProtocolType protocol = ProtocolType.ZeroMQ;
    [Tooltip("L'IP del computer che invia i dati")]
    public string sourceIP = "localhost"; 
    
    [Header("Visualizzazione")]
    public Transform breastModel;
    public float smoothingSpeed = 5f;

    // Riferimento interno al materiale (gestito automaticamente)
    private Material _activeMaterial;

    // Coda thread-safe
    private ConcurrentQueue<BioData> _dataQueue = new ConcurrentQueue<BioData>();

    // Thread per la gestione della rete
    private Thread _networkThread;
    private bool _isRunning = true;

    // Variabili per l'interpolazione
    private Vector3 _targetScale;
    private Color _targetColor;
    private float _baseRadius = 14.12f;

    [Serializable]
    public class BioData
    {
        public int id;
        public string diagnosis;
        public float radius_mean;
        public float texture_mean;
    }

    void Start()
    {
        Debug.Log("=== BioDigitalTwin Start() ===");
        
        // 1. AUTO-CONFIGURAZIONE MODELLO
        if (breastModel == null)
        {
            // Se lo script è attaccato a una sfera, usa quella
            if (GetComponent<Renderer>() != null)
            {
                breastModel = transform;
            }
            else
            {
                // Altrimenti ne crea una al volo
                GameObject sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                sphere.name = "BreastModel_Auto";
                sphere.transform.SetParent(this.transform);
                sphere.transform.localPosition = Vector3.zero;
                breastModel = sphere.transform;
            }
            Debug.Log("✅ Modello 3D configurato.");
        }

        // 2. AUTO-CONFIGURAZIONE MATERIALE
        // Recuperiamo il Renderer per poter cambiare colore
        Renderer renderer = breastModel.GetComponent<Renderer>();
        if (renderer != null)
        {
            // Prendiamo l'istanza del materiale
            _activeMaterial = renderer.material;
            Debug.Log("✅ Materiale acquisito per il cambio colore.");
        }
        else
        {
            Debug.LogError("❌ ERRORE: Il modello non ha un MeshRenderer!");
        }
        
        // Stato iniziale
        _targetScale = Vector3.one;
        _targetColor = Color.white;

        // 3. AVVIO RETE
        if (protocol == ProtocolType.ZeroMQ)
        {
            _networkThread = new Thread(RunZeroMQListener);
            _networkThread.IsBackground = true;
            _networkThread.Start();
            Debug.Log($"✅ [ZeroMQ] Thread avviato su {sourceIP}");
        }
    }


    void Update()
    {
        // 1. CONSUMA LA CODA: Preleva i dati arrivati dalla rete
        if (_dataQueue.TryDequeue(out BioData data))
        {
            ApplyDataVisuals(data);
        }

        // 2. INTERPOLAZIONE (Movimento fluido)
        if (breastModel != null)
        {
            breastModel.localScale = Vector3.Lerp(breastModel.localScale, _targetScale, Time.deltaTime * smoothingSpeed);
        }

        // 3. CAMBIO COLORE
        if (_activeMaterial != null)
        {
            _activeMaterial.color = Color.Lerp(_activeMaterial.color, _targetColor, Time.deltaTime * smoothingSpeed);
        }
    }

    // Traduce i numeri del CSV in proprietà grafiche
    void ApplyDataVisuals(BioData data)
    {
        // CALCOLO SCALA
        float raggio = data.radius_mean;
        if (raggio <= 0.1f) raggio = _baseRadius; // Protezione dati zero

        // Moltiplico per 3 per rendere l'effetto evidente nel video
        float scaleFactor = (raggio / _baseRadius) * 3.0f; 
        
        // Blocco di sicurezza (Clamp) per evitare che sparisca o diventi enorme
        scaleFactor = Mathf.Clamp(scaleFactor, 0.5f, 5.0f);

        _targetScale = Vector3.one * scaleFactor;

        // CALCOLO COLORE
        if (data.diagnosis == "M") 
            _targetColor = Color.red;   // Maligno
        else 
            _targetColor = Color.green; // Benigno

        // Log di verifica visiva
        Debug.Log($"[VISUAL] Aggiornato -> Diagnosi: {data.diagnosis} | Scala Target: {scaleFactor:F2}");
    }
    // ---------------------------------------------------------

    void RunZeroMQListener()
    {
        try 
        {
            AsyncIO.ForceDotNet.Force();
            using (var subSocket = new SubscriberSocket())
            {
                string address = $"tcp://{sourceIP}:5555";
                subSocket.Connect(address);
                subSocket.Subscribe(""); // Ascolta tutto
                
                while (_isRunning)
                {
                    // Ricezione bloccante (attende qui finché non arriva un dato)
                    string messageJson = subSocket.ReceiveFrameString();
                    
                    if (!string.IsNullOrEmpty(messageJson))
                    {
                        try
                        {
                            BioData data = JsonUtility.FromJson<BioData>(messageJson);
                            if (data != null)
                            {
                                // Mette il dato nella coda per il Main Thread (Update)
                                _dataQueue.Enqueue(data);
                            }
                        }
                        catch (Exception) { /* Ignora errori di parsing */ }
                    }
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[ZeroMQ Thread Error]: {e.Message}");
        }
        finally 
        {
            NetMQConfig.Cleanup();
        }
    }
    
    void OnDestroy()
    {
        _isRunning = false;
        if (_networkThread != null && _networkThread.IsAlive)
        {
            _networkThread.Join(200); 
        }
        NetMQConfig.Cleanup();
    }
}
