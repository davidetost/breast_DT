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
    public float smoothingSpeed = 5f;

    [Header("Material")]
    public Color tumorColor = new Color(1f, 0.2f, 0.2f, 0.7f);
    public float emissionIntensity = 0.3f;

    private Material leftMat;
    private Material rightMat;

    private bool initialized = false;

    // ❌ NON facciamo nulla allo start
    void Start() {}

    // 🔐 Inizializzazione SOLO quando arrivano dati reali
    public void InitializeFromData()
    {
        if (initialized) return;

        if (leftTumor != null)
        {
            SetupTumor(leftTumor, ref leftMat);
        }

        if (rightTumor != null)
        {
            SetupTumor(rightTumor, ref rightMat);
        }

        initialized = true;
        Debug.Log("[TumorVisualization] Initialized from first data");
    }

    private void SetupTumor(Transform tumor, ref Material mat)
    {
        tumor.localScale = Vector3.zero;
        tumor.gameObject.SetActive(true);

        Renderer r = tumor.GetComponent<Renderer>();
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
        UpdateTumor(leftTumor, radius);
    }

    public void UpdateRightTumor(float radius)
    {
        UpdateTumor(rightTumor, radius);
    }

    private void UpdateTumor(Transform tumor, float radius)
    {
        if (!initialized || tumor == null) return;

        if (radius <= 0.001f)
        {
            tumor.localScale = Vector3.Lerp(
                tumor.localScale,
                Vector3.zero,
                Time.deltaTime * smoothingSpeed
            );
            return;
        }

        float diameter = Mathf.Clamp(
            radius * 2f * visualScaleFactor,
            0.01f,
            maxDiameterLimit
        );

        Vector3 target = Vector3.one * diameter;

        tumor.localScale = Vector3.Lerp(
            tumor.localScale,
            target,
            Time.deltaTime * smoothingSpeed
        );
    }
}
