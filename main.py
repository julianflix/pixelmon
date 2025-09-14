#!/usr/bin/env python3
"""
Pixelmon-like Pygame MVP (v5)
- One big scrollable level per file: levels/levelN.txt (any size, letters G/S/W/.)
- Camera + true zoom rendering (default 2.0x). Minimap toggle (M).
- Terrain variety: multiple PNG variants per biome (assets/grass1.png..grass3.png, etc.); deterministic per tile.
- creatures.json schema: { "grass": [{"name":"Bulbasaur","sprite":"bulbasaur.png"}, ...], "water":[...], "sand":[...] }
- Unique mon sprites loaded from assets/mons/<sprite>, with placeholder fallback.
- Overworld HUD above wild mons: name, level, HP bar.
- Battle popup: choose team mon (↑/↓ + Enter); both sides deal damage; fainting & reselection.
- Active mon follower: floats within a radius around the player.
- Bush regrowth, wild mon respawn, craft balls (3 apricorns → 1 ball), victory when all species caught.

Run examples:
  python main.py                 # loads level1.txt, zoom 2.0
  python main.py --level 3       # loads level3.txt
  python main.py --zoom 2.5      # bigger on-screen sprites
"""

from __future__ import annotations
import os, sys, argparse, random, json, math
import pygame

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
WIDTH, HEIGHT = 960, 540
TILE = 30
FPS = 60
MON_SCALE = 2
PLAYER_SCALE = 3.5



WHITE=(255,255,255); BLACK=(0,0,0); RED=(220,70,70); YELLOW=(240,220,120); GREENBAR=(100,220,120)
ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
MONS_DIR  = os.path.join(ASSET_DIR, "mons")
LEVEL_DIR = os.path.join(os.path.dirname(__file__), "levels")
DATA_PATH = os.path.join(os.path.dirname(__file__), "creatures.json")

# ------------------------------------------------------------
# Utility + graceful fallbacks
# ------------------------------------------------------------
def load_img(path, scale_to=None):
    try:
        img = pygame.image.load(path).convert_alpha()
        img.fill((255,255,255,255), None, pygame.BLEND_RGBA_MULT)  # ensures full alpha
        if scale_to: img = pygame.transform.smoothscale(img, scale_to)
        return img
    except Exception:
        # transparent fallback
        surf = pygame.Surface(scale_to if scale_to else (TILE, TILE), pygame.SRCALPHA)
        return surf

def make_tile_variant_surface(base_rgb, noise_rgb, seed=0):
    # procedural tile if PNGs are missing
    surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    surf.fill((*base_rgb, 255))
    rnd = random.Random(seed)
    for _ in range(80):
        x, y = rnd.randrange(TILE), rnd.randrange(TILE)
        surf.set_at((x,y), (*noise_rgb, 90))
    for x in range(0, TILE, 6):
        pygame.draw.line(surf, (0,0,0,25), (x,0), (x,TILE))
    return surf

def variant_index(tx, ty, count):
    return abs((tx*73856093) ^ (ty*19349663)) % count

def parse_args():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--zoom", type=float, default=2.0)
    try:
        args, _ = p.parse_known_args()
    except SystemExit:
        class A: level=1; zoom=2.0
        args=A()
    return args

# ------------------------------------------------------------
# Data Loading
# ------------------------------------------------------------
def load_creatures():
    # Schema with {name, sprite}. Fallback to a tiny default set if file missing.
    defaults = {
        "grass": [{"name":"Bulbasaur","sprite":"bulbasaur.png"},
                  {"name":"Riolu","sprite":"riolu.png"},
                  {"name":"Grookey","sprite":"grookey.png"}],
        "water": [{"name":"Squirtle","sprite":"squirtle.png"},
                  {"name":"Lapras","sprite":"lapras.png"},
                  {"name":"Psyduck","sprite":"psyduck.png"}],
        "sand":  [{"name":"Sandshrew","sprite":"sandshrew.png"},
                  {"name":"Meowth","sprite":"meowth.png"},
                  {"name":"Trapinch","sprite":"trapinch.png"}],
    }
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
            # simple schema check
            if not isinstance(raw, dict): raw = defaults
    except Exception:
        raw = defaults
    # Load sprites (fallback to colored circle)
    def load_mon_sprite(sprite_file):
        path = os.path.join(MONS_DIR, sprite_file)
        size = int((TILE-6) * MON_SCALE)   # scale mons 1.5x bigger
        if os.path.exists(path):
            return load_img(path, (size, size))
        # placeholder
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (200,100,200), (size//2, size//2), size//2-2)
        pygame.draw.circle(surf, (40,40,40), (size//2, size//2), size//2-2, 2)
        return surf

    creatures = {}
    for biome in ("grass","water","sand"):
        creatures[biome] = []
        for entry in raw.get(biome, []):
            name = entry.get("name","Mon")
            sprite = load_mon_sprite(entry.get("sprite",""))
            creatures[biome].append({"name":name, "sprite":sprite})
    all_species = sorted({c["name"] for b in creatures.values() for c in b})
    return creatures, all_species

def load_level_any_size(idx):
    path = os.path.join(LEVEL_DIR, f"level{idx}.txt")
    if not os.path.exists(path):
        # generate a simple default if missing
        w, h = 64, 36
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                if y < h//3: row.append('G')
                elif y < 2*h//3: row.append('S' if (x+y)%5==0 else 'G')
                else: row.append('W' if (abs((x//2)-(y-(2*h//3)))<2) or y> (2*h//3)+3 else 'S')
            rows.append("".join(row))
    else:
        with open(path, "r", encoding="utf-8") as f:
            rows = [line.rstrip("\n") for line in f if line.strip()!='']
    h = len(rows); w = len(rows[0]) if h>0 else 0
    rows = [r.ljust(w, '.') for r in rows]
    grid = []
    for y in range(h):
        row = []
        for x in range(w):
            c = rows[y][x]
            row.append('water' if c=='W' else 'sand' if c=='S' else 'grass')
        grid.append(row)
    print(f"Loaded level{idx}.txt ({w}x{h} tiles)" if os.path.exists(path) else f"Loaded default level ({w}x{h} tiles)")
    return grid, w, h

# ------------------------------------------------------------
# World & Entities
# ------------------------------------------------------------
class Camera:
    def __init__(self, map_w_tiles, map_h_tiles, viewport_w, viewport_h):
        self.w_px = map_w_tiles * TILE
        self.h_px = map_h_tiles * TILE
        self.vw = viewport_w; self.vh = viewport_h
        self.x = 0; self.y = 0
    def center_on(self, rect):
        self.x = rect.centerx - self.vw//2
        self.y = rect.centery - self.vh//2
        self.x = max(0, min(self.x, self.w_px - self.vw))
        self.y = max(0, min(self.y, self.h_px - self.vh))
    def apply(self, pos):
        return (pos[0]-self.x, pos[1]-self.y)

class Player(pygame.sprite.Sprite):
    def __init__(self, x, y, img):
        super().__init__()
        self.image = img.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = 160; self.run = False
        self.apricorns = 0; self.balls = 3
        self.team = []     # dict: name, level, hp, max_hp, sprite
        self.caught_species = set()
        self.active_index = 0
    def handle_move(self, dt, map_w_px, map_h_px):
        keys = pygame.key.get_pressed()
        vx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        vy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        vel = pygame.Vector2(vx, vy)
        if vel.length_squared(): vel = vel.normalize()
        speed = self.speed * (1.6 if self.run else 1.0)
        self.rect.centerx += int(vel.x * speed * dt)
        self.rect.centery += int(vel.y * speed * dt)
        self.rect.left = max(0, self.rect.left); self.rect.top = max(0, self.rect.top)
        self.rect.right = min(map_w_px, self.rect.right); self.rect.bottom = min(map_h_px, self.rect.bottom)
    def get_active_mon(self):
        if not self.team: return None
        self.active_index = max(0, min(self.active_index, len(self.team)-1))
        return self.team[self.active_index]

class Follower:
    def __init__(self):
        self.pos = pygame.Vector2(0,0)
    def update(self, target_pos, target_radius=2*TILE, wander=28, dt=1/60):
        to_target = pygame.Vector2(target_pos) - self.pos
        dist = to_target.length()
        if dist > target_radius:
            d = to_target.normalize() if dist>0 else pygame.Vector2(0,0)
            self.pos += d * 120 * dt
        else:
            self.pos += pygame.Vector2(random.uniform(-1,1), random.uniform(-1,1)) * wander * dt

class Mon(pygame.sprite.Sprite):
    def __init__(self, name, sprite_surf, level, biome, pos):
        super().__init__()
        self.name = name; self.level = level; self.biome = biome
        self.max_hp = 10 + level * 3; self.hp = self.max_hp
        self.image = sprite_surf.copy()
        self.rect = self.image.get_rect(center=pos)
        self.v = pygame.Vector2(random.uniform(-1,1), random.uniform(-1,1))
        if self.v.length_squared() == 0: self.v = pygame.Vector2(1,0)
        self.v = self.v.normalize() * random.uniform(20, 35)
    def update(self, dt, map_w_px, map_h_px):
        self.rect.centerx += int(self.v.x * dt)
        self.rect.centery += int(self.v.y * dt)
        if self.rect.left < 0 or self.rect.right > map_w_px: self.v.x *= -1
        if self.rect.top < 0 or self.rect.bottom > map_h_px: self.v.y *= -1
        self.rect.left = max(0, self.rect.left); self.rect.top = max(0, self.rect.top)
        self.rect.right = min(map_w_px, self.rect.right); self.rect.bottom = min(map_h_px, self.rect.bottom)

class LevelWorld:
    TARGET_MON_COUNT = 7
    RESPAWN_INTERVAL = 6.0
    BUSH_RESPAWN_SEC = 6.0
    MAX_BUSHES = 20
    def __init__(self, grid, w_tiles, h_tiles, tile_variants, bush_img, creatures):
        self.grid = grid; self.w_tiles=w_tiles; self.h_tiles=h_tiles
        self.w_px = w_tiles*TILE; self.h_px = h_tiles*TILE
        self.variants = tile_variants
        self.bush_img = bush_img
        self.creatures = creatures
        self.bushes = []
        self.mons = pygame.sprite.Group()
        self._respawn_t=0.0; self._bush_t=0.0
        for _ in range(10): self._spawn_bush()
        for _ in range(self.TARGET_MON_COUNT): self.mons.add(self.spawn_mon())
    def draw(self, surf, cam):
        first_tx = cam.x // TILE; first_ty = cam.y // TILE
        tiles_x = cam.vw//TILE + 2; tiles_y = cam.vh//TILE + 2
        for ty in range(first_ty, min(first_ty+tiles_y, self.h_tiles)):
            sy = ty*TILE - cam.y
            for tx in range(first_tx, min(first_tx+tiles_x, self.w_tiles)):
                sx = tx*TILE - cam.x
                biome = self.grid[ty][tx]
                variants = self.variants[biome]
                idx = variant_index(tx, ty, len(variants))
                surf.blit(variants[idx], (sx, sy))
        for r in self.bushes:
            surf.blit(self.bush_img, cam.apply((r.x, r.y)))
    def _spawn_bush(self):
        for _ in range(200):
            tx = random.randrange(self.w_tiles)
            ty = random.randrange(self.h_tiles//3 if self.h_tiles>3 else self.h_tiles)
            if self.grid[ty][tx] != 'grass': continue
            r = pygame.Rect(tx*TILE+4, ty*TILE+4, TILE-8, TILE-8)
            if not any(r.colliderect(b) for b in self.bushes):
                self.bushes.append(r); return
    def pick_bush(self, player):
        for r in list(self.bushes):
            if player.rect.colliderect(r): self.bushes.remove(r); return True
        return False
    def spawn_mon(self, near_pos=None):
        if near_pos is None:
            tx = random.randrange(self.w_tiles); ty = random.randrange(self.h_tiles)
        else:
            ntx = int(near_pos[0]//TILE) + random.randint(-6,6)
            nty = int(near_pos[1]//TILE) + random.randint(-4,4)
            tx = max(0, min(self.w_tiles-1, ntx)); ty = max(0, min(self.h_tiles-1, nty))
        biome = self.grid[ty][tx]
        options = self.creatures.get(biome, [])
        if not options:
            name="Critter"; sprite=pygame.Surface((TILE-6,TILE-6), pygame.SRCALPHA); pygame.draw.circle(sprite,(200,200,200),(sprite.get_width()//2,sprite.get_height()//2),(TILE-8)//2)
        else:
            pick = random.choice(options); name=pick["name"]; sprite=pick["sprite"]
        level = random.randint(1, 10)
        pos = (tx*TILE + TILE//2, ty*TILE + TILE//2)
        return Mon(name, sprite, level, biome, pos)
    def timers_update(self, dt, player):
        self._respawn_t += dt; self._bush_t += dt
        if self._respawn_t >= self.RESPAWN_INTERVAL:
            self._respawn_t = 0.0
            while len(self.mons) < self.TARGET_MON_COUNT:
                self.mons.add(self.spawn_mon(player.rect.center))
        if self._bush_t >= self.BUSH_RESPAWN_SEC:
            self._bush_t = 0.0
            if len(self.bushes) < self.MAX_BUSHES: self._spawn_bush()

# ------------------------------------------------------------
# Battle System
# ------------------------------------------------------------
class Battle:
    def __init__(self, player: Player, wild: Mon, player_img):
        self.player = player; self.wild = wild; self.player_img = player_img
        self.active = True; self.cooldown = 0.0
        self.state = "select" if player.team else "fight"  # popup to select team mon
        self.cursor = 0
        self.message = f"A wild {wild.name} (Lv{wild.level}) appeared!"
        self.my_mon = player.get_active_mon()
    def update(self, dt): self.cooldown = max(0.0, self.cooldown - dt)
    def draw(self, surf, font, small_font):
        pygame.draw.rect(surf, (30,90,60), (0, HEIGHT-190, WIDTH, 190))
        pygame.draw.rect(surf, WHITE, (10, HEIGHT-180, WIDTH-20, 170), 2)
        self._hp_box(surf, small_font, (40, HEIGHT-170), f"{self.wild.name} Lv{self.wild.level}", self.wild.hp, self.wild.max_hp)
        if self.my_mon:
            self._hp_box(surf, small_font, (WIDTH-360, HEIGHT-130), f"{self.my_mon['name']} Lv{self.my_mon['level']}", self.my_mon['hp'], self.my_mon['max_hp'])
        surf.blit(self.wild.image, (WIDTH-140, HEIGHT-250))
        surf.blit(self.player_img, (80, HEIGHT-250))
        surf.blit(font.render(self.message, True, WHITE), (30, HEIGHT-90))
        if self.state == "select":
            self._draw_select_popup(surf, font, small_font)
        else:
            surf.blit(small_font.render("[F] Attack   [SPACE] Throw Ball   [B] Bag   [ESC] Run", True, WHITE), (30, HEIGHT-60))
    def _hp_box(self, surf, small_font, pos, label, hp, maxhp):
        pygame.draw.rect(surf, WHITE, (*pos, 320, 48), 2)
        surf.blit(small_font.render(label, True, WHITE), (pos[0]+10, pos[1]+6))
        ratio = 0 if maxhp<=0 else max(0, hp)/maxhp
        w = int(300*ratio)
        color = RED if ratio<0.3 else YELLOW if ratio<0.6 else GREENBAR
        pygame.draw.rect(surf, color, (pos[0]+10, pos[1]+26, w, 12))
        pygame.draw.rect(surf, WHITE, (pos[0]+10, pos[1]+26, 300, 12), 2)
    def _draw_select_popup(self, surf, font, small_font):
        box = pygame.Rect(WIDTH//2-220, HEIGHT//2-120, 440, 160)
        pygame.draw.rect(surf, (20,20,20), box); pygame.draw.rect(surf, WHITE, box, 2)
        surf.blit(font.render("Choose your mon (↑/↓, Enter):", True, WHITE), (box.x+10, box.y+10))
        if not self.player.team:
            surf.blit(small_font.render("You have no mons. Try throwing a ball.", True, YELLOW), (box.x+20, box.y+50))
            return
        for i, mon in enumerate(self.player.team):
            y = box.y + 40 + i*24
            label = f"{mon['name']}  Lv{mon['level']}  HP {mon['hp']}/{mon['max_hp']}"
            color = (255,255,0) if i==self.cursor else WHITE
            surf.blit(small_font.render(label, True, color), (box.x+20, y))
    def handle_input(self, event):
        if self.state == "select":
            if event.key in (pygame.K_UP, pygame.K_w):
                if self.player.team: self.cursor = (self.cursor - 1) % len(self.player.team)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                if self.player.team: self.cursor = (self.cursor + 1) % len(self.player.team)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.player.team:
                    self.player.active_index = self.cursor
                    self.my_mon = self.player.get_active_mon()
                    self.state = "fight"
        else:
            if event.key == pygame.K_f: self.attack_round()
            elif event.key == pygame.K_SPACE: self.throw_ball()
    def attack_round(self):
        if self.cooldown>0: return
        if not self.my_mon:
            self.message = "No team mon! Throw a ball or run."
            return
        dmg = random.randint(2, 4) + max(0, self.my_mon['level']//3)
        self.wild.hp = max(0, self.wild.hp - dmg)
        self.message = f"{self.my_mon['name']} dealt {dmg} to {self.wild.name}!"
        if self.wild.hp <= 0:
            self.message = f"{self.wild.name} fainted. You found an apricorn!"
            self.player.apricorns += 1
            self.active = False
        else:
            enemy_dmg = random.randint(1,3) + max(0, self.wild.level//4)
            self.my_mon['hp'] = max(0, self.my_mon['hp'] - enemy_dmg)
            self.message += f"  {self.wild.name} hits back for {enemy_dmg}!"
            if self.my_mon['hp'] <= 0:
                self.message = f"{self.my_mon['name']} fainted!"
                alive = [m for m in self.player.team if m['hp']>0]
                if alive:
                    self.state = "select"; self.cursor = 0
                else:
                    self.message += " You have no mons left!"
                    self.active = False
        self.cooldown = 0.6
    def throw_ball(self):
        if self.cooldown>0: return
        if self.player.balls <= 0:
            self.message = "No balls left! Craft with [C]."; return
        self.player.balls -= 1
        hp_ratio = max(0.05, self.wild.hp / self.wild.max_hp)
        base = 0.5 * (1.0 - hp_ratio); level_penalty = max(0.1, 1.0 - (self.wild.level-1)*0.05)
        chance = base * level_penalty + 0.15
        if random.random() < chance:
            self.message = f"Gotcha! {self.wild.name} was caught!"
            sprite = self.wild.image.copy()
            self.player.team.append({"name": self.wild.name, "level": self.wild.level, "max_hp": self.wild.max_hp, "hp": self.wild.hp, "sprite": sprite})
            self.player.caught_species.add(self.wild.name)
            if self.state == "select":
                self.player.active_index = len(self.player.team)-1
                self.my_mon = self.player.get_active_mon(); self.state="fight"
            self.active = False
        else:
            self.message = "Oh no! It broke free."
        self.cooldown = 0.8

# ------------------------------------------------------------
# Minimap & HUD
# ------------------------------------------------------------
def draw_minimap(surf, world, player, show=True):
    if not show: return
    max_w, max_h = 220, 140
    scale = min(max_w / world.w_px, max_h / world.h_px)
    mw, mh = max(1,int(world.w_px * scale)), max(1,int(world.h_px * scale))
    mm = pygame.Surface((mw, mh), pygame.SRCALPHA)
    step = max(1, int(2 / (scale if scale>0 else 1)))
    for ty in range(0, world.h_tiles, step):
        for tx in range(0, world.w_tiles, step):
            biome = world.grid[ty][tx]
            c = (60,140,220) if biome=='water' else (216,192,128) if biome=='sand' else (64,160,84)
            x = int(tx*TILE*scale); y = int(ty*TILE*scale)
            pygame.draw.rect(mm, c, (x, y, int(TILE*scale*step), int(TILE*scale*step)))
    for r in world.bushes:
        x = int(r.centerx * scale); y = int(r.centery * scale)
        pygame.draw.circle(mm, (40, 220, 80), (x,y), max(1,int(3*scale)))
    for m in world.mons:
        x = int(m.rect.centerx * scale); y = int(m.rect.centery * scale)
        c = (90,200,120) if m.biome=='grass' else (90,150,230) if m.biome=='water' else (230,210,140)
        pygame.draw.circle(mm, c, (x,y), max(1,int(3*scale)))
    px = int(player.rect.centerx * scale); py = int(player.rect.centery * scale)
    pygame.draw.circle(mm, (255,255,255), (px,py), max(2,int(4*scale)))
    surf.blit(mm, (8,8)); pygame.draw.rect(surf, WHITE, (8,8,mw,mh), 1)



def draw_world_mon_hud(surf, cam, mon, hud_font):
    label = f"{mon.name} Lv{mon.level}"
    pos = cam.apply((mon.rect.centerx - 30, mon.rect.top - 16))
    surf.blit(hud_font.render(label, True, WHITE), pos)
    ratio = 0 if mon.max_hp<=0 else max(0, mon.hp)/mon.max_hp
    w = 48; x = mon.rect.centerx - w//2; y = mon.rect.top - 6
    sx, sy = cam.apply((x, y))
    pygame.draw.rect(surf, WHITE, (sx, sy, w, 5), 1)
    pygame.draw.rect(surf, GREENBAR if ratio>0.6 else YELLOW if ratio>0.3 else RED, (sx+1, sy+1, int((w-2)*ratio), 3))

# ------------------------------------------------------------
# Terrain variants (load PNGs or procedural fallback)
# ------------------------------------------------------------
def build_tile_variants():
    def load_or_make(prefix, base_rgb, noise_rgb):
        variants = []
        for i in (1,2,3):
            path = os.path.join(ASSET_DIR, f"{prefix}{i}.png")
            img = load_img(path, (TILE,TILE))
            if img.get_width()==0 or img.get_height()==0:
                img = make_tile_variant_surface(base_rgb, noise_rgb, seed=100*i)
            variants.append(img)
        return variants
    return {
        "grass": load_or_make("grass", (64,160,84),  (40,120,60)),
        "sand":  load_or_make("sand",  (216,192,128),(140,110,70)),
        "water": load_or_make("water", (80,140,220), (40,80,140)),
    }

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    args = parse_args()
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Pixelmon Pygame MVP v5")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 18)
    small_font = pygame.font.SysFont("consolas", 14)
    hud_font = pygame.font.SysFont("consolas", 10) 

    # Load assets / fallbacks
    tile_variants = build_tile_variants()
    size = int((TILE-6) * PLAYER_SCALE)
    player_img = load_img(os.path.join(ASSET_DIR, "player.png"), (size, size))
    if player_img.get_width()==0:  # placeholder
        player_img = pygame.Surface((TILE-6, TILE-6), pygame.SRCALPHA)
        pygame.draw.rect(player_img, (240,240,255), player_img.get_rect())
        pygame.draw.rect(player_img, (80,80,200), player_img.get_rect(), 2)
    ball_img = load_img(os.path.join(ASSET_DIR,"ball.png"), (22,22))
    apricorn_img = load_img(os.path.join(ASSET_DIR,"apricorn.png"), (22,22))
    bush_img = load_img(os.path.join(ASSET_DIR,"bush.png"), (TILE-8, TILE-8))
    if bush_img.get_width()==0:
        bush_img = pygame.Surface((TILE-8, TILE-8), pygame.SRCALPHA)
        pygame.draw.rect(bush_img, (120,200,100), bush_img.get_rect())
        pygame.draw.rect(bush_img, (30,90,40), bush_img.get_rect(), 2)

    # Data
    CREATURES, ALL_SPECIES = load_creatures()
    grid, w_tiles, h_tiles = load_level_any_size(args.level)

    # True zoom: render to smaller viewport then scale up
    ZOOM = max(1.5, float(args.zoom))
    view_w = int(WIDTH / ZOOM); view_h = int(HEIGHT / ZOOM)
    view_surf = pygame.Surface((view_w, view_h)).convert_alpha()

    # World + player
    world = LevelWorld(grid, w_tiles, h_tiles, tile_variants, bush_img, CREATURES)
    player = Player(world.w_px//2, world.h_px//2, player_img)
    cam = Camera(w_tiles, h_tiles, view_w, view_h)
    follower = Follower(); follower.pos.update(player.rect.centerx-40, player.rect.centery+20)

    battle=None; bag=False; minimap=False; victory=False; show_help=True

    running=True
    while running:
        dt = clock.tick(FPS)/1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running=False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if victory: victory=False
                    elif battle and battle.active: battle.active=False; battle=None
                    else: running=False
                elif e.key == pygame.K_r: player.run = not player.run
                elif e.key == pygame.K_m: minimap = not minimap
                elif e.key == pygame.K_b: bag = not bag
                elif e.key == pygame.K_c:
                    if player.apricorns>=3: player.apricorns-=3; player.balls+=1
                elif e.key == pygame.K_p: world.mons.add(world.spawn_mon(player.rect.center))
                elif e.key == pygame.K_e:
                    if not battle and not victory:
                        for m in world.mons:
                            if player.rect.colliderect(m.rect.inflate(10,10)):
                                battle = Battle(player, m, player_img); break
                elif battle:
                    battle.handle_input(e)
                elif e.key == pygame.K_SPACE:
                    if victory: victory=False

        # Update
        if not battle and not victory:
            player.handle_move(dt, world.w_px, world.h_px)
            world.mons.update(dt, world.w_px, world.h_px)
            if world.pick_bush(player): player.apricorns += 1
            world.timers_update(dt, player)
            cam.center_on(player.rect)
            # follower
            active = player.get_active_mon()
            if active: follower.update(player.rect.center, target_radius=2*TILE, wander=28, dt=dt)
            else: follower.pos.update(player.rect.centerx-40, player.rect.centery+20)
        else:
            if battle:
                battle.update(dt)
                if not battle.active:
                    try: world.mons.remove(battle.wild)
                    except Exception: pass
                    battle=None

        if not victory and len(player.caught_species) >= len(ALL_SPECIES):
            victory=True

        # Draw world to view surface
        view_surf.fill(BLACK)
        world.draw(view_surf, cam)
        # wild mons + HUD
        for m in world.mons:
            view_surf.blit(m.image, cam.apply(m.rect.topleft))
            draw_world_mon_hud(view_surf, cam, m, hud_font)
        # player
        view_surf.blit(player_img, cam.apply(player.rect.topleft))
        # follower sprite (active mon)
        active = player.get_active_mon()
        if active:
            fx, fy = cam.apply((int(follower.pos.x)-(TILE-6)//2, int(follower.pos.y)-(TILE-6)//2))
            view_surf.blit(active['sprite'], (fx, fy))

        # scale to screen
        pygame.transform.scale(view_surf, (WIDTH, HEIGHT), screen)

        # overlays
        screen.blit(pygame.font.SysFont("consolas", 18).render(
            f"Zoom:{ZOOM:.2f}  Balls:{player.balls}  Apricorns:{player.apricorns}  Team:{len(player.team)}  Species:{len(player.caught_species)}/{len(ALL_SPECIES)}",
            True, WHITE), (10,8))
        draw_minimap(screen, world, player, show=minimap)

        if show_help and not victory:
            pygame.draw.rect(screen, (0,0,0,160), (0, HEIGHT-56, WIDTH, 56))
            screen.blit(pygame.font.SysFont("consolas", 18).render(
                "E: interact  F: attack  SPACE: ball  B: bag  C: craft  R: run  M: minimap  P: spawn  ESC: quit",
                True, WHITE), (10, HEIGHT-40))

        if bag and not battle and not victory:
            panel = pygame.Rect(WIDTH-280, 10, 270, 190)
            pygame.draw.rect(screen, (25,25,25,220), panel); pygame.draw.rect(screen, WHITE, panel, 2)
            screen.blit(pygame.font.SysFont("consolas", 18).render("Bag", True, WHITE), (panel.x+10, panel.y+8))
            screen.blit(ball_img, (panel.x+10, panel.y+34))
            screen.blit(pygame.font.SysFont("consolas", 18).render(f"x {player.balls}", True, WHITE), (panel.x+38, panel.y+36))
            screen.blit(apricorn_img, (panel.x+10, panel.y+62))
            screen.blit(pygame.font.SysFont("consolas", 18).render(f"x {player.apricorns}", True, WHITE), (panel.x+38, panel.y+64))
            screen.blit(pygame.font.SysFont("consolas", 18).render("Craft [C]: 3 apricorns -> 1 ball", True, WHITE), (panel.x+10, panel.y+100))

        if battle: battle.draw(screen, font, small_font)

        if victory:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0,0,0,170)); screen.blit(overlay, (0,0))
            pygame.draw.rect(screen, WHITE, (WIDTH//2-240, HEIGHT//2-90, 480, 180), 2)
            screen.blit(font.render("You caught ALL species! 🎉", True, WHITE), (WIDTH//2-200, HEIGHT//2-60))
            screen.blit(small_font.render("SPACE/ESC to continue exploring.", True, WHITE), (WIDTH//2-200, HEIGHT//2-30))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
