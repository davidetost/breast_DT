using UnityEngine;
using System;
using System.Threading;
using System.Threading.Tasks; // Importante per Task
using System.Net.Http;
using Grpc.Net.Client;
using Grpc.Net.Client.Web;
using Grpc.Core;
using BreastDt;
using System.Collections.Concurrent;

public class DigitalTwinController_gRPC_Modern : MonoBehaviour
{
    [Header("gRPC-Web Configuration")]
    public string envoyAddress = "http://127.0.0.1:8080"; 
    
    [Header("Visualization")]
    public TumorVisualization tumorVis;

    // --- Variabili gRPC ---
    private GrpcChannel channel;
    private DigitalTwinService.DigitalTwinServiceClient client;
    private CancellationTokenSource cts;
    
    // Coda thread-safe
    private ConcurrentQueue<TumorState> tumorStateQueue = new ConcurrentQueue<TumorState>();
    
    [Header("Therapy")]
    public float manualTherapyDosage = 0.8f;
    
    [Header("Debug & GUI")]
    public bool showDebugGUI = true;
    private string lastStatusMessage = "In attesa...";
    private string lastDataMessage = "Nessun dato...";
    
    // Metriche
    private bool isConnected = false;
    private int updateCount = 0;
    private float lastLeftRadius = 0f;
    private float lastRightRadius = 0f;
    private DateTime lastUpdateTime;
    private float avgLatencyMs = 0f;
    private int latencySamples = 0;

    void OnEnable()
    {
        Application.targetFrameRate = 60;
        
        if (tumorVis == null)
            tumorVis = FindFirstObjectByType<TumorVisualization>();
        
        if (tumorVis == null){Debug.LogError("[DigitalTwin] ❌ TumorVisualization non trovato!");
        } 
        else
        {
            tumorVis.InitializeFromData();
        }
        ConnectToServer();
    }
    
    void ConnectToServer()
    {
        try 
        {
            Debug.Log($"[gRPC-Web] Connessione a {envoyAddress}...");

            var httpHandler = new HttpClientHandler();
            // GrpcWebText è più compatibile con i proxy, GrpcWeb (binario) è più veloce.
            // Envoy li supporta entrambi. Usiamo GrpcWebText per sicurezza.
            var grpcWebHandler = new GrpcWebHandler(GrpcWebMode.GrpcWebText, httpHandler);
            
            channel = GrpcChannel.ForAddress(envoyAddress, new GrpcChannelOptions
            {
                HttpHandler = grpcWebHandler
            });
            
            client = new DigitalTwinService.DigitalTwinServiceClient(channel);
            
            isConnected = true;
            lastStatusMessage = "Connesso (gRPC-Web)";
            Debug.Log("[gRPC-Web] ✓ Connesso! Avvio stream...");
            
            // --- CORREZIONE 1: Dobbiamo lanciare lo stream qui! ---
            StreamTumorUpdatesAsync(); 
        }
        catch (Exception e) 
        {
            Debug.LogError($"[gRPC-Web] Errore Connessione: {e.Message}");
            isConnected = false;
            lastStatusMessage = "Errore Connessione";
        }
    }
    
    // Metodo "Fire and Forget" per lo streaming
    private async void StreamTumorUpdatesAsync()
    {
        cts = new CancellationTokenSource();
        try 
        {
            using var call = client.StreamTumorUpdates(new Empty(), cancellationToken: cts.Token);
            
            Debug.Log("[gRPC-Web] Streaming avviato");
            lastUpdateTime = DateTime.UtcNow;
            
            // Loop di lettura asincrono
            while (await call.ResponseStream.MoveNext(cts.Token))   
            {
                TumorState state = call.ResponseStream.Current;
                
                // Calcolo Latenza
                var now = DateTime.UtcNow;
                var latency = (float)(now - lastUpdateTime).TotalMilliseconds;
                lastUpdateTime = now;
                latencySamples++;
                avgLatencyMs = ((avgLatencyMs * (latencySamples - 1)) + latency) / latencySamples;

                // Mettiamo in coda per il Main Thread
                tumorStateQueue.Enqueue(state);
            }
        }
        catch (RpcException e) when (e.StatusCode == StatusCode.Cancelled) 
        {
            Debug.Log("[gRPC-Web] Stream cancellato.");
        }
        catch (Exception e) 
        {
            Debug.LogError($"[gRPC-Web] Stream Error: {e.Message}");
            isConnected = false;
            lastStatusMessage = "Stream Interrotto";
        }
    }
    
    // --- CORREZIONE 2: Unity Update Loop per svuotare la coda ---
    void Update()
    {
        if (!isConnected) return;
        // Consumiamo tutti i pacchetti arrivati in questo frame
        while (tumorStateQueue.TryDequeue(out TumorState state))
        {
            ProcessTumorState(state);
        }
    }

    void ProcessTumorState(TumorState state)
    {
        updateCount++;
        
        if (state.Left != null) lastLeftRadius = state.Left.Radius;
        if (state.Right != null) lastRightRadius = state.Right.Radius;
        
        // Aggiorna stringa debug
        lastDataMessage = $"L: {lastLeftRadius:F2} | R: {lastRightRadius:F2}";

        // Aggiorna sfere
        if (tumorVis != null)
        {
            tumorVis.UpdateLeftTumor(lastLeftRadius);
            tumorVis.UpdateRightTumor(lastRightRadius);
        }
        
        lastStatusMessage = "Streaming Attivo";
    }
    
    public async void SendTherapyCommandFromUI()
    {
        if (!isConnected || client == null)
        {
            Debug.LogError("[gRPC-Web] Non connesso!");
            return;
        }
        
        try 
        {
            var request = new TherapyRequest {
                Type = "INJECT", // Usa "CHEMO" o "INJECT" in base a cosa si aspetta il server Python
                Dosage = manualTherapyDosage
            };
            
            // Attendiamo la risposta
            var response = await client.SendTherapyAsync(request);
            
            if (response.Success)
                Debug.Log($"[gRPC-Web] 💉 Terapia inviata: {manualTherapyDosage}mg - Server: {response.Message}");
            else
                Debug.LogError($"[gRPC-Web] Terapia fallita: {response.Message}");
        }
        catch (Exception e) 
        {
            Debug.LogError($"[gRPC-Web] Errore Terapia: {e.Message}");
        }
    }
    
    void OnGUI()
    {
        if (!showDebugGUI) return;

        GUIStyle style = new GUIStyle();
        style.fontSize = 20; // Testo più leggibile
        style.normal.textColor = Color.white;

        // Box di sfondo semitrasparente
        GUI.Box(new Rect(10, 10, 500, 300), "Digital Twin Control");

        GUILayout.BeginArea(new Rect(20, 40, 480, 260));
        
        style.normal.textColor = isConnected ? Color.green : Color.red;
        GUILayout.Label($"Stato: {lastStatusMessage}", style);
        
        style.normal.textColor = Color.cyan;
        GUILayout.Label($"Dati ({updateCount}): {lastDataMessage}", style);
        GUILayout.Label($"Latenza media: {avgLatencyMs:F1} ms", style);
        
        GUILayout.Space(20);
        
        // Bottone Terapia
        if (GUILayout.Button($"💉 INIEZIONE ({manualTherapyDosage}mg)", GUILayout.Height(40)))
        {
            SendTherapyCommandFromUI();
        }

        GUILayout.EndArea();
    }
    
    async void OnApplicationQuit()
    {
        cts?.Cancel();
        if (channel != null)
            await channel.ShutdownAsync();
    }
}