using UnityEngine;
using System;
using System.Threading;
using System.Net.Http;
using Grpc.Net.Client;
using Grpc.Net.Client.Web;
using Grpc.Core;
using BreastDt;
using System.Collections.Concurrent;

public class DigitalTwinController_gRPC_Debug : MonoBehaviour
{
    [Header("gRPC-Web Configuration")]
    public string envoyAddress = "http://127.0.0.1:8080";

    [Header("Visualization")]
    public TumorVisualization tumorVis;

    [Header("Therapy")]
    public float manualTherapyDosage = 0.8f;

    [Header("Debug & GUI")]
    public bool showDebugGUI = true;

    private GrpcChannel channel;
    private DigitalTwinService.DigitalTwinServiceClient client;
    private CancellationTokenSource cts;
    private ConcurrentQueue<TumorState> tumorStateQueue = new ConcurrentQueue<TumorState>();

    private bool isConnected = false;
    private int updateCount = 0;
    private float lastLeftRadius = 0f;
    private float lastRightRadius = 0f;

    private Transform leftTumorDirect;
    private Transform rightTumorDirect;

    void OnEnable()
    {
        Application.targetFrameRate = 60;

        if (tumorVis == null)
        {
            tumorVis = FindFirstObjectByType<TumorVisualization>();
            if (tumorVis == null)
            {
                Debug.LogError("[gRPC]  TumorVisualization not found!");
                enabled = false;
                return;
            }
        }

    
        leftTumorDirect = tumorVis.leftTumor;
        rightTumorDirect = tumorVis.rightTumor;

        Debug.Log($"[gRPC] ✓ Sfere trovate:");
        Debug.Log($"  Left:  {leftTumorDirect?.name} ({leftTumorDirect?.GetInstanceID()})");
        Debug.Log($"  Right: {rightTumorDirect?.name} ({rightTumorDirect?.GetInstanceID()})");
        Debug.Log($"  Scala iniziale Left: {leftTumorDirect?.localScale}");

        ConnectToServer();
    }

    void ConnectToServer()
    {
        try
        {
            Debug.Log($"[gRPC-Web] Connection to {envoyAddress}...");

            var httpHandler = new HttpClientHandler();
            var grpcWebHandler = new GrpcWebHandler(GrpcWebMode.GrpcWebText, httpHandler);

            channel = GrpcChannel.ForAddress(envoyAddress, new GrpcChannelOptions
            {
                HttpHandler = grpcWebHandler
            });

            client = new DigitalTwinService.DigitalTwinServiceClient(channel);
            isConnected = true;
            Debug.Log("[gRPC-Web] Connected!");

            StreamTumorUpdatesAsync();
        }
        catch (Exception e)
        {
            Debug.LogError($"[gRPC-Web] Error: {e.Message}");
            isConnected = false;
        }
    }

    private async void StreamTumorUpdatesAsync()
    {
        cts = new CancellationTokenSource();
        try
        {
            using var call = client.StreamTumorUpdates(new Empty(), cancellationToken: cts.Token);
            Debug.Log("[gRPC-Web]  Stream started");

            while (await call.ResponseStream.MoveNext(cts.Token))
            {
                tumorStateQueue.Enqueue(call.ResponseStream.Current);
            }
        }
        catch (RpcException e) when (e.StatusCode == StatusCode.Cancelled)
        {
            Debug.Log("[gRPC-Web] Stream cancelled");
        }
        catch (Exception e)
        {
            Debug.LogError($"[gRPC-Web] Stream error: {e.Message}");
            isConnected = false;
        }
    }

    void Update()
    {
        if (!isConnected) return;

        while (tumorStateQueue.TryDequeue(out TumorState state))
        {
            ProcessTumorState(state);
        }
    }

    void ProcessTumorState(TumorState state)
    {
        if (state?.Left == null || state?.Right == null) return;

        updateCount++;
        lastLeftRadius = state.Left.Radius;
        lastRightRadius = state.Right.Radius;

    
        Debug.Log($"\n[TEST 1] Before triggering TumorVisualization:");
        Debug.Log($"  leftTumorDirect.localScale = {leftTumorDirect.localScale}");

        tumorVis.UpdateLeftTumor(lastLeftRadius);
        tumorVis.UpdateRightTumor(lastRightRadius);

        Debug.Log($"[TEST 1] After triggering TumorVisualization:");
        Debug.Log($"  leftTumorDirect.localScale = {leftTumorDirect.localScale}");
        Debug.Log($"  tumorVis.leftTumor.localScale = {tumorVis.leftTumor.localScale}");
        Debug.Log($"  Sono lo stesso oggetto? {leftTumorDirect == tumorVis.leftTumor}");

 
        float directScale = lastLeftRadius * 0.1f; // Fattore scala 0.1
        leftTumorDirect.localScale = new Vector3(directScale, directScale, directScale);
        rightTumorDirect.localScale = new Vector3(directScale, directScale, directScale);

        Debug.Log($"[TEST 2] After direct scale:");
        Debug.Log($"  Set: {directScale}");
        Debug.Log($"  leftTumorDirect.localScale = {leftTumorDirect.localScale}");


        StartCoroutine(CheckScaleNextFrame());
    }

    System.Collections.IEnumerator CheckScaleNextFrame()
    {
        yield return null;

        Debug.Log($"[TEST 3] NEXT FRAME:");
        Debug.Log($"  leftTumorDirect.localScale = {leftTumorDirect.localScale}");
        
        if (leftTumorDirect.localScale.x > 4.5f)
        {
            Debug.LogError("Resetted scale!");
        }
        else
        {
            Debug.Log("Scale correctly preserved");
        }
    }

    public async void SendTherapyCommandFromUI()
    {
        if (!isConnected || client == null) return;

        try
        {
            var request = new TherapyRequest { Type = "INJECT", Dosage = manualTherapyDosage };
            var response = await client.SendTherapyAsync(request);
            Debug.Log($"[gRPC] Therapy: {response.Message}");
        }
        catch (Exception e)
        {
            Debug.LogError($"[gRPC] Therapy error: {e.Message}");
        }
    }

    void OnGUI()
    {
        if (!showDebugGUI) return;

        GUIStyle style = new GUIStyle { fontSize = 18 };
        style.normal.textColor = Color.white;

        GUI.Box(new Rect(10, 10, 500, 280), "gRPC DEBUG MODE");

        GUILayout.BeginArea(new Rect(20, 40, 480, 240));

        style.normal.textColor = isConnected ? Color.green : Color.red;
        GUILayout.Label($"Status: {(isConnected ? "ONLINE" : "OFFLINE")}", style);

        style.normal.textColor = Color.cyan;
        GUILayout.Label($"Updates: {updateCount}", style);
        GUILayout.Label($"Radius: L={lastLeftRadius:F4} R={lastRightRadius:F4}", style);

        if (leftTumorDirect != null)
        {
            style.normal.textColor = Color.yellow;
            GUILayout.Label($"Scale Direct: {leftTumorDirect.localScale.x:F6}", style);
        }

        if (tumorVis?.leftTumor != null)
        {
            style.normal.textColor = Color.magenta;
            GUILayout.Label($"Scale Via TumorVis: {tumorVis.leftTumor.localScale.x:F6}", style);
        }

        GUILayout.Space(10);

        if (GUILayout.Button($" THERAPY ({manualTherapyDosage}mg)", GUILayout.Height(40)))
            SendTherapyCommandFromUI();

        GUILayout.EndArea();
    }

    async void OnApplicationQuit()
    {
        cts?.Cancel();
        if (channel != null) await channel.ShutdownAsync();
    }

    void OnDisable()
    {
        cts?.Cancel();
    }
}
