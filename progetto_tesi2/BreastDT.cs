using UnityEngine;

public class TumorVisualization : MonoBehaviour
{
    [Header("Tumor Settings")]
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
    
    [Range(0f, 0.5f)]
    public float embeddingDepth = 0.15f; // How deep inside the breast mesh
    
    [Header("Animation Settings")]
    [Range(0f, 0.1f)]
    public float pulsationIntensity = 0.02f;
    
    [Range(0f, 5f)]
    public float pulsationSpeed = 2.0f;
    
    [Range(1f, 10f)]
    public float smoothingSpeed = 3f;
    
    [Header("Material Settings")]
    public Color tumorColor = new Color(1f, 0.2f, 0.2f, 0.7f);
    
    [Range(0f, 2f)]
    public float emissionIntensity = 0.3f;
    
    private Material leftTumorMaterial;
    private Material rightTumorMaterial;
    private Vector3 leftOriginalPosition;
    private Vector3 rightOriginalPosition;

    void Start()
    {
        InitializeTumors();
    }

    void InitializeTumors()
    {
        if (leftTumor != null)
        {
            leftOriginalPosition = leftTumor.localPosition;
            SetupTumorMaterial(leftTumor, ref leftTumorMaterial);
            EmbedTumor(leftTumor, leftOriginalPosition);
        }
        
        if (rightTumor != null)
        {
            rightOriginalPosition = rightTumor.localPosition;
            SetupTumorMaterial(rightTumor, ref rightTumorMaterial);
            EmbedTumor(rightTumor, rightOriginalPosition);
        }
    }

    void SetupTumorMaterial(Transform tumor, ref Material tumorMat)
    {
        Renderer renderer = tumor.GetComponent<Renderer>();
        if (renderer == null)
        {
            Debug.LogError($"No Renderer found on {tumor.name}");
            return;
        }
        
        // Create a new material instance to avoid modifying the shared material
        tumorMat = new Material(Shader.Find("Standard"));
        renderer.material = tumorMat;
        
        // Configure material properties
        tumorMat.SetFloat("_Mode", 3); // Set to Transparent mode
        tumorMat.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
        tumorMat.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
        tumorMat.SetInt("_ZWrite", 0);
        tumorMat.DisableKeyword("_ALPHATEST_ON");
        tumorMat.EnableKeyword("_ALPHABLEND_ON");
        tumorMat.DisableKeyword("_ALPHAPREMULTIPLY_ON");
        tumorMat.renderQueue = 3000;
        
        // Set color and transparency
        tumorMat.color = tumorColor;
        
        // Add emission for better visibility
        tumorMat.EnableKeyword("_EMISSION");
        Color emissionColor = new Color(tumorColor.r, tumorColor.g, tumorColor.b) * emissionIntensity;
        tumorMat.SetColor("_EmissionColor", emissionColor);
        
        // Smooth surface
        tumorMat.SetFloat("_Smoothness", 0.8f);
        tumorMat.SetFloat("_Metallic", 0.1f);
    }

    void EmbedTumor(Transform tumor, Vector3 originalPosition)
    {
        // Move tumor slightly inward along its local normal direction
        // This assumes the tumor is positioned on the surface initially
        Vector3 directionToCenter = (breastModel.position - tumor.position).normalized;
        tumor.position += directionToCenter * embeddingDepth;
    }

    void Update()
    {
        // Update transparency in real-time if changed in inspector
        UpdateMaterialProperties();
    }

    void UpdateMaterialProperties()
    {
        if (leftTumorMaterial != null)
        {
            Color color = tumorColor;
            color.a = tumorTransparency;
            leftTumorMaterial.color = color;
            
            Color emissionColor = new Color(tumorColor.r, tumorColor.g, tumorColor.b) * emissionIntensity;
            leftTumorMaterial.SetColor("_EmissionColor", emissionColor);
        }
        
        if (rightTumorMaterial != null)
        {
            Color color = tumorColor;
            color.a = tumorTransparency;
            rightTumorMaterial.color = color;
            
            Color emissionColor = new Color(tumorColor.r, tumorColor.g, tumorColor.b) * emissionIntensity;
            rightTumorMaterial.SetColor("_EmissionColor", emissionColor);
        }
    }

    // Call this method when you receive data from your edge server
    public void UpdateTumorSize(Transform tumor, float radius)
    {
        if (tumor == null) return;
        
        // If radius is almost zero, hide the tumor
        if (radius <= 0.01f)
        {
            tumor.localScale = Vector3.Lerp(tumor.localScale, Vector3.zero, Time.deltaTime * 5f);
            return;
        }
        
        // Calculate diameter with constraints
        float rawDiameter = Mathf.Max(radius * 2.0f, 0.1f);
        float scaledDiameter = rawDiameter * visualScaleFactor;
        
        // Clamp to maximum size
        if (scaledDiameter > maxDiameterLimit) 
            scaledDiameter = maxDiameterLimit;
        
        // Add subtle pulsation effect
        float pulsation = Mathf.Sin(Time.time * pulsationSpeed + tumor.position.x) * 
                         (pulsationIntensity * visualScaleFactor);
        
        float finalSize = scaledDiameter + pulsation;
        
        // Smooth transition to new size
        Vector3 targetScale = new Vector3(finalSize, finalSize, finalSize);
        tumor.localScale = Vector3.Lerp(tumor.localScale, targetScale, Time.deltaTime * smoothingSpeed);
    }

    // Convenience methods for updating individual tumors
    public void UpdateLeftTumor(float radius)
    {
        UpdateTumorSize(leftTumor, radius);
    }

    public void UpdateRightTumor(float radius)
    {
        UpdateTumorSize(rightTumor, radius);
    }

    // Example: Update both tumors with different radii
    public void UpdateBothTumors(float leftRadius, float rightRadius)
    {
        UpdateLeftTumor(leftRadius);
        UpdateRightTumor(rightRadius);
    }

    // Optional: Visualize the embedding in the editor
    void OnDrawGizmos()
    {
        if (leftTumor != null && breastModel != null)
        {
            Gizmos.color = Color.yellow;
            Vector3 directionToCenter = (breastModel.position - leftTumor.position).normalized;
            Gizmos.DrawLine(leftTumor.position, leftTumor.position + directionToCenter * embeddingDepth);
        }
        
        if (rightTumor != null && breastModel != null)
        {
            Gizmos.color = Color.yellow;
            Vector3 directionToCenter = (breastModel.position - rightTumor.position).normalized;
            Gizmos.DrawLine(rightTumor.position, rightTumor.position + directionToCenter * embeddingDepth);
        }
    }
}