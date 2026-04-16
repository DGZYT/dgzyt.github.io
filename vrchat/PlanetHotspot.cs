using UdonSharp;
using UnityEngine;

public class PlanetHotspot : UdonSharpBehaviour
{
    private GalacticMapManager _manager;
    private int _planetIndex;

    [Header("Visual")]
    public Renderer hotspotRenderer;

    [Tooltip("Normal scale for this hotspot")]
    public float baseScale = 0.03f;

    [Tooltip("Extra scale for active event planets")]
    public float eventScale = 0.045f;

    public void Setup(
        GalacticMapManager manager,
        int planetIndex,
        string planetName,
        string sector,
        string owner,
        float liberation,
        int players,
        string eventType,
        Color color
    )
    {
        _manager = manager;
        _planetIndex = planetIndex;

        float scale = baseScale;
        if (eventType != "none")
        {
            scale = eventScale;
        }

        transform.localScale = new Vector3(scale, scale, scale);

        if (hotspotRenderer != null)
        {
            hotspotRenderer.material.color = color;
        }
    }

    public override void Interact()
    {
        if (_manager != null)
        {
            _manager.SelectPlanet(_planetIndex);
        }
    }
}
