using UnityEngine;

public class TumorVisualization : MonoBehaviour
{
    [Header("References")]
    public Transform leftTumor;
    public Transform rightTumor;
    public Transform breastModel;
    
    [Header("Visual Settings")]
    [Range(0.1f, 5f)]
    public float visualScaleFactor = 1.0f;
    
    [Range(0.1f, 10f)]
    public float maxDiameterLimit = 5.0f;
    
    [Range(0f, 1f)]
    public float tumorTransparency = 0.7f;
    
    [Header("Animation")]
    [Range(1f, 50f)]
    public float smoothingSpeed = 15f;  
    
    [Header("Material")]
    public Color tumorColor = new Color(1f, 0.2f, 0.2f, 0.7f);
    public float emissionIntensity = 0.3f;
    
    [Header("Debug")]
    public bool enableDebugLogs = false;
    
    private Material leftMat;
    private Material rightMat;
    private bool initialized = false;
  
    private Vector3 leftTargetScale = Vector3.zero;
    private Vector3 rightTargetScale = Vector3.zero;
    
    void Start() 
    {
        if (leftTumor != null) 
        {
            leftTumor.gameObject.SetActive(false);
        }
        if (rightTumor != null) 
        {
            rightTumor.gameObject.SetActive(false);
        }
        
        UnityEngine.Debug.Log("[TumorVis] Inizializzato - Tumori disattivati");
    }

    
    void Update()
    {
        if (!initialized) return;

   
        if (leftTumor != null)
        {
            leftTumor.localScale = Vector3.Lerp(leftTumor.localScale, leftTargetScale, Time.deltaTime * smoothingSpeed);
        }

        if (rightTumor != null)
        {
            rightTumor.localScale = Vector3.Lerp(rightTumor.localScale, rightTargetScale, Time.deltaTime * smoothingSpeed);
        }
    }
    
    public void InitializeFromData()
    {
        if (initialized) 
        {
            if (enableDebugLogs) UnityEngine.Debug.Log("[TumorVis] Già inizializzato, skip");
            return;
        }
        
        if (leftTumor != null)
        {
            SetupTumor(leftTumor, ref leftMat);
            UnityEngine.Debug.Log($"[TumorVis] ✓ Left tumor inizializzato: {leftTumor.name}");
        }
        else 
        {
            UnityEngine.Debug.LogWarning("[TumorVis] ⚠️ Left tumor Transform è NULL!");
        }
        
        if (rightTumor != null)
        {
            SetupTumor(rightTumor, ref rightMat);
            UnityEngine.Debug.Log($"[TumorVis] ✓ Right tumor inizializzato: {rightTumor.name}");
        }
        else 
        {
            UnityEngine.Debug.LogWarning("[TumorVis] ⚠️ Right tumor Transform è NULL!");
        }
        
        initialized = true;
        UnityEngine.Debug.Log("[TumorVis] ✓ Inizializzazione completata");
    }
    
    private void SetupTumor(Transform tumor, ref Material mat)
    {
        tumor.localScale = Vector3.zero;
        tumor.gameObject.SetActive(true);
        
        Renderer r = tumor.GetComponent<Renderer>();
        if (r == null)
        {
            UnityEngine.Debug.LogError($"[TumorVis] ❌ Renderer non trovato su {tumor.name}!");
            return;
        }
        
        mat = new Material(Shader.Find("Standard"));
        r.material = mat;
        

        mat.SetFloat("_Mode", 3);
        mat.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
        mat.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
        mat.SetInt("_ZWrite", 0);
        mat.DisableKeyword("_ALPHATEST_ON");
        mat.EnableKeyword("_ALPHABLEND_ON");
        mat.renderQueue = 3000;
        
 
        mat.color = tumorColor;
        mat.EnableKeyword("_EMISSION");
        mat.SetColor("_EmissionColor", tumorColor * emissionIntensity);
    }
    
    public void UpdateLeftTumor(float radius)
    {
        UpdateTumor(leftTumor, radius, "LEFT", ref leftTargetScale);
    }
    
    public void UpdateRightTumor(float radius)
    {
        UpdateTumor(rightTumor, radius, "RIGHT", ref rightTargetScale);
    }
   
    private void UpdateTumor(Transform tumor, float radius, string side, ref Vector3 targetScale)
    {
        if (!initialized)
        {
            if (enableDebugLogs) UnityEngine.Debug.LogWarning($"[TumorVis] {side} - Non ancora inizializzato!");
            return;
        }
        
        if (tumor == null) return;
        

        if (radius <= 0.001f)
        {
            targetScale = Vector3.zero;
            if (enableDebugLogs) UnityEngine.Debug.Log($"[TumorVis] {side} - Shrinking to zero");
            return;
        }
        

        float diameter = Mathf.Clamp(
            radius * 2f * visualScaleFactor,
            0.01f,
            maxDiameterLimit
        );
        
    
        targetScale = Vector3.one * diameter;
        
        if (enableDebugLogs)
        {
            UnityEngine.Debug.Log($"[TumorVis] {side} UPDATE: Radius: {radius:F3} -> Target Scale: {targetScale.x:F3}");
        }
    }
    
    public string GetDebugInfo()
    {
        if (!initialized) return "Not initialized";
        
        string info = "";
        if (leftTumor != null)
            info += $"Left: {leftTumor.localScale.x:F2} (target: {leftTargetScale.x:F2})\n";
        
        if (rightTumor != null)
            info += $"Right: {rightTumor.localScale.x:F2} (target: {rightTargetScale.x:F2})";
            
        return info;
    }
}
