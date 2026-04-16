# Helldivers 2 VRChat Map Relay

This repo template builds a live-ish Helldivers 2 galactic map for VRChat and deploys it to GitHub Pages.

## What this includes

- GitHub Actions workflow for Pages deployment
- Python relay that fetches HD2 data and generates:
  - `state.json`
  - `map.png`
  - `index.html`
- Sample `planet_coords.json`
- Placeholder `base_map.png`
- UdonSharp scripts for VRChat:
  - `vrchat/GalacticMapManager.cs`
  - `vrchat/PlanetHotspot.cs`

## Quick setup

1. Create a new GitHub repo.
2. Extract this zip into the repo root.
3. Replace `assets/base_map.png` with your actual galactic map art.
4. Push to `main`.
5. In GitHub:
   - Settings -> Pages -> Source -> **GitHub Actions**
   - Settings -> Secrets and variables -> Actions -> Variables
     - `HD2_SUPER_CLIENT` = something like `dakota-vrchat-map`
     - optional `HD2_SUPER_CONTACT` = your contact/site
6. Run the workflow once from the **Actions** tab.

## Notes

- GitHub Actions scheduled workflows run every 5 minutes at best, so the map will not update every minute on GitHub Pages.
- `planet_coords.json` uses normalized coordinates from `0.0` to `1.0`.
- Any planet missing from `planet_coords.json` falls back to auto-projected coordinates from the API.

## VRChat URLs

For a normal project repo:
- `https://YOURNAME.github.io/REPO_NAME/state.json`
- `https://YOURNAME.github.io/REPO_NAME/map.png`

For a user-site repo named `YOURNAME.github.io`:
- `https://YOURNAME.github.io/state.json`
- `https://YOURNAME.github.io/map.png`

## Unity

- Put `GalacticMapManager` on a parent object.
- Put `PlanetHotspot` on your pooled hotspot objects.
- Set `jsonUrl` to your Pages `state.json`.
- Enable `useBackgroundImageFromJson`.

## Next step

After you swap in your real map art, adjust `data/planet_coords.json` so the hotspots line up with the planets on your chosen map.
