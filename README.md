# Pixelmon-like Pygame MVP

A tiny, working prototype of a Minecraft + Pokémon–style game using **Pygame**, designed so you can **export to the web with pygbag**.

> This is intentionally simple: walk around, find wild mons, enter a battle, attack or throw a ball to catch them. Collect **apricorns** from bushes and craft balls (3 apricorns → 1 ball).

## Controls

- **WASD / Arrows** — move
- **E** — interact (start a battle when close to a wild mon)
- **F** — attack (in battle)
- **SPACE** — throw ball (in battle)
- **B** — open/close Bag
- **C** — craft 1 Poké Ball from 3 apricorns
- **R** — toggle run
- **P** — spawn a nearby mon (debug)
- **M** — toggle on-screen help
- **ESC** — quit / escape battle

## How to Run (Desktop)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## How to Export with pygbag (Web)

```bash
pip install pygbag
python -m pygbag --build main.py
# Serve the folder, then open the "build/web" output:
python -m http.server 8000
# Go to http://localhost:8000/build/web/
```

## Files

- `main.py` — game code (single-file for easy pygbag export)
- `creatures.json` — small roster grouped by biome
- `requirements.txt` — Python deps (Pygame only)

## Notes & Next Steps

- Add proper art/audio assets and replace placeholder shapes.
- Turn the Bag into a full inventory UI and add more item types.
- Expand the map and biomes; add spawning rules per time/region.
- Implement XP/level ups for your team and evolution rules.
- Add a Poké Ball crafting GUI (this prototype uses **C** as a shortcut).
