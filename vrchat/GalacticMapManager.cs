using UdonSharp;
using UnityEngine;
using VRC.SDK3.StringLoading;
using VRC.SDK3.Image;
using VRC.SDK3.Data;
using VRC.SDKBase;
using VRC.Udon.Common.Interfaces;
using TMPro;

public class GalacticMapManager : UdonSharpBehaviour
{
    [Header("Remote Data")]
    [Tooltip("URL of the live JSON state file")]
    public VRCUrl jsonUrl;

    [Tooltip("If true, use the backgroundImage URL from JSON. If false, use fallbackImageUrl below.")]
    public bool useBackgroundImageFromJson = true;

    [Tooltip("Fallback image URL if JSON doesn't provide backgroundImage or you disable it")]
    public VRCUrl fallbackImageUrl;

    [Tooltip("Seconds between refreshes")]
    public float refreshSeconds = 60f;

    [Header("Board")]
    [Tooltip("Parent transform for all hotspot objects")]
    public Transform hotspotRoot;

    [Tooltip("Renderer that displays the galaxy map image")]
    public Renderer mapRenderer;

    [Tooltip("Width of the usable board area in local units")]
    public float boardWidth = 2.0f;

    [Tooltip("Height of the usable board area in local units")]
    public float boardHeight = 1.0f;

    [Tooltip("Local Z offset for hotspots so they sit slightly above the board")]
    public float hotspotZOffset = -0.01f;

    [Header("Planet Hotspot Pool")]
    [Tooltip("Pre-placed hotspot objects to reuse for planets")]
    public PlanetHotspot[] hotspotPool;

    [Header("Hotspot Colors")]
    public Color humanColor = new Color(0.2f, 0.5f, 1f);
    public Color terminidColor = new Color(1f, 0.8f, 0.2f);
    public Color automatonColor = new Color(1f, 0.2f, 0.2f);
    public Color illuminateColor = new Color(0.7f, 0.2f, 1f);
    public Color unknownColor = Color.gray;

    [Header("UI")]
    public TMP_Text planetNameText;
    public TMP_Text sectorText;
    public TMP_Text ownerText;
    public TMP_Text liberationText;
    public TMP_Text playersText;
    public TMP_Text eventText;

    private VRCImageDownloader _imageDownloader;
    private IVRCImageDownload _currentImageDownload;
    private DataDictionary _planetByIndex;
    private string _currentBackgroundImageUrl = "";

    void Start()
    {
        _imageDownloader = new VRCImageDownloader();
        RefreshAll();
    }

    public void RefreshAll()
    {
        VRCStringDownloader.LoadUrl(jsonUrl, (IUdonEventReceiver)this);
        SendCustomEventDelayedSeconds(nameof(RefreshAll), refreshSeconds);
    }

    public override void OnStringLoadSuccess(IVRCStringDownload result)
    {
        DataToken rootToken;
        if (!VRCJson.TryDeserializeFromJson(result.Result, out rootToken))
        {
            Debug.LogError("Failed to parse JSON");
            return;
        }

        if (rootToken.TokenType != TokenType.DataDictionary)
        {
            Debug.LogError("JSON root is not an object");
            return;
        }

        DataDictionary root = rootToken.DataDictionary;

        string backgroundUrl = "";
        DataToken bgToken;
        if (useBackgroundImageFromJson && root.TryGetValue("backgroundImage", out bgToken))
        {
            backgroundUrl = bgToken.String;
        }
        else
        {
            backgroundUrl = fallbackImageUrl.Get();
        }

        if (backgroundUrl != "" && backgroundUrl != _currentBackgroundImageUrl)
        {
            _currentBackgroundImageUrl = backgroundUrl;
            DownloadBackground(new VRCUrl(backgroundUrl));
        }

        DataToken planetsToken;
        if (!root.TryGetValue("planets", out planetsToken) || planetsToken.TokenType != TokenType.DataList)
        {
            Debug.LogError("Missing planets array");
            return;
        }

        DataList planets = planetsToken.DataList;
        _planetByIndex = new DataDictionary();

        int visibleCount = planets.Count;
        if (visibleCount > hotspotPool.Length)
        {
            visibleCount = hotspotPool.Length;
            Debug.LogWarning("Not enough hotspot objects in pool to display all planets");
        }

        for (int i = 0; i < visibleCount; i++)
        {
            DataDictionary p = planets[i].DataDictionary;

            int index = GetInt(p, "index", -1);
            string name = GetString(p, "name", "Unknown");
            string sector = GetString(p, "sector", "");
            string owner = GetString(p, "owner", "Unknown");
            float liberation = GetFloat(p, "liberation", 0f);
            int players = GetInt(p, "players", 0);
            float x = GetFloat(p, "x", 0.5f);
            float y = GetFloat(p, "y", 0.5f);
            string eventType = GetString(p, "eventType", "none");

            _planetByIndex.SetValue(index.ToString(), p);

            PlanetHotspot hotspot = hotspotPool[i];
            hotspot.gameObject.SetActive(true);

            if (hotspot.transform.parent != hotspotRoot)
            {
                hotspot.transform.SetParent(hotspotRoot, false);
            }

            float localX = (x - 0.5f) * boardWidth;
            float localY = (y - 0.5f) * boardHeight;

            hotspot.transform.localPosition = new Vector3(localX, localY, hotspotZOffset);

            Color planetColor = GetOwnerColor(owner);

            hotspot.Setup(
                this,
                index,
                name,
                sector,
                owner,
                liberation,
                players,
                eventType,
                planetColor
            );
        }

        for (int i = visibleCount; i < hotspotPool.Length; i++)
        {
            hotspotPool[i].gameObject.SetActive(false);
        }
    }

    public override void OnStringLoadError(IVRCStringDownload result)
    {
        Debug.LogError("JSON load failed: " + result.ErrorCode + " / " + result.Error);
    }

    private void DownloadBackground(VRCUrl url)
    {
        if (_currentImageDownload != null)
        {
            _currentImageDownload.Dispose();
            _currentImageDownload = null;
        }

        _currentImageDownload = _imageDownloader.DownloadImage(url, mapRenderer.material, (IUdonEventReceiver)this);
    }

    public override void OnImageLoadSuccess(IVRCImageDownload result)
    {
        Debug.Log("Background image loaded");
    }

    public override void OnImageLoadError(IVRCImageDownload result)
    {
        Debug.LogError("Background image load failed: " + result.Error + " / " + result.ErrorMessage);
    }

    public void SelectPlanet(int planetIndex)
    {
        if (_planetByIndex == null)
            return;

        DataToken token;
        if (!_planetByIndex.TryGetValue(planetIndex.ToString(), out token))
            return;

        DataDictionary p = token.DataDictionary;

        string name = GetString(p, "name", "Unknown");
        string sector = GetString(p, "sector", "");
        string owner = GetString(p, "owner", "Unknown");
        float liberation = GetFloat(p, "liberation", 0f);
        int players = GetInt(p, "players", 0);
        string eventType = GetString(p, "eventType", "none");

        if (planetNameText != null) planetNameText.text = name;
        if (sectorText != null) sectorText.text = sector != "" ? "Sector: " + sector : "";
        if (ownerText != null) ownerText.text = "Owner: " + owner;
        if (liberationText != null) liberationText.text = "Liberation: " + liberation.ToString("0.00") + "%";
        if (playersText != null) playersText.text = "Players: " + players.ToString();
        if (eventText != null) eventText.text = "Event: " + eventType;
    }

    public Color GetOwnerColor(string owner)
    {
        string o = owner.ToLower();

        if (o == "human" || o == "super earth")
            return humanColor;
        if (o == "terminid")
            return terminidColor;
        if (o == "automaton")
            return automatonColor;
        if (o == "illuminate")
            return illuminateColor;

        return unknownColor;
    }

    private string GetString(DataDictionary d, string key, string fallback)
    {
        DataToken t;
        if (d.TryGetValue(key, out t))
            return t.String;
        return fallback;
    }

    private int GetInt(DataDictionary d, string key, int fallback)
    {
        DataToken t;
        if (d.TryGetValue(key, out t))
            return (int)t.Double;
        return fallback;
    }

    private float GetFloat(DataDictionary d, string key, float fallback)
    {
        DataToken t;
        if (d.TryGetValue(key, out t))
            return (float)t.Double;
        return fallback;
    }

    void OnDestroy()
    {
        if (_currentImageDownload != null)
            _currentImageDownload.Dispose();

        if (_imageDownloader != null)
            _imageDownloader.Dispose();
    }
}
