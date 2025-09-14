#!/usr/bin/env python3
"""
Pixelmon-like Pygame MVP (v3)
- Tiled maps loaded from text files in /levels (G,S,W,.)
- 3x3 overworld (9 areas). Move to an edge to transition to the adjacent area.
- PNG assets for tiles/player/items/mons.
- Respawning mons per area and bush (apricorn) regrowth in grass tiles.
- Victory when all species in creatures.json are caught (persists while exploring).

Tile legend in level files:
  G = grass, S = sand, W = water, . = empty (drawn as grass for now)

A single area fills the screen; each level file must be 32 columns x 18 rows when TILE=30.
"""

from __future__ import annotations
import os, random, json
import pygame

WIDTH, HEIGHT = 960, 540
TILE = 30
GRID_W, GRID_H = WIDTH//TILE, HEIGHT//TILE
FPS = 60

WHITE=(255,255,255); BLACK=(0,0,0); RED=(220,70,70); YELLOW=(240,220,120); GREENBAR=(100,220,120)

# Assets
ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
def load_img(name, scale_to=None):
    img = pygame.image.load(os.path.join(ASSET_DIR, name)).convert_alpha()
    if scale_to:
        img = pygame.transform.smoothscale(img, scale_to)
    return img

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pixelmon Pygame MVP v3")
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 18)

TILE_IMG = {
    "grass": load_img("grass.png", (TILE, TILE)),
    "sand":  load_img("sand.png", (TILE, TILE)),
    "water": load_img("water.png", (TILE, TILE)),
}
PLAYER_IMG = load_img("player.png", (TILE-6, TILE-6))
BALL_IMG = load_img("ball.png", (22,22))
APRICORN_IMG = load_img("apricorn.png", (22,22))
BUSH_IMG = load_img("bush.png", (TILE-8, TILE-8))
MON_IMG = {
    "grass": load_img("mon_grass.png", (TILE-6, TILE-6)),
    "water": load_img("mon_water.png", (TILE-6, TILE-6)),
    "sand":  load_img("mon_sand.png", (TILE-6, TILE-6)),
}

DATA_PATH = os.path.join(os.path.dirname(__file__), "creatures.json")
CREATURES = json.load(open(DATA_PATH, "r", encoding="utf-8"))
ALL_SPECIES = sorted(set(sum(CREATURES.values(), [])))

LEVEL_DIR = os.path.join(os.path.dirname(__file__), "levels")
def load_level(idx):
    path = os.path.join(LEVEL_DIR, f"level{idx}.txt")
    with open(path, "r", encoding="utf-8") as f:
        rows = [line.rstrip("\n") for line in f]
    assert len(rows)==GRID_H and all(len(r)==GRID_W for r in rows), "Level must be 32x18 characters"
    grid = []
    for y in range(GRID_H):
        row = []
        for x in range(GRID_W):
            c = rows[y][x]
            if c == 'G' or c == '.':
                row.append('grass' if c=='G' else 'grass')
            elif c == 'S':
                row.append('sand')
            elif c == 'W':
                row.append('water')
            else:
                row.append('grass')
        grid.append(row)
    return grid

class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = PLAYER_IMG.copy()
        self.rect = self.image.get_rect(topleft=(x, y))
        self.speed = 140
        self.run = False
        self.apricorns = 0
        self.balls = 3
        self.team = []
        self.caught_species = set()

    def handle_move(self, dt):
        keys = pygame.key.get_pressed()
        vx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        vy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        vel = pygame.Vector2(vx, vy)
        if vel.length_squared(): vel = vel.normalize()
        speed = self.speed * (1.6 if self.run else 1.0)
        self.rect.x += int(vel.x * speed * dt)
        self.rect.y += int(vel.y * speed * dt)
        self.rect.clamp_ip(pygame.Rect(0,0,WIDTH,HEIGHT))

class Mon(pygame.sprite.Sprite):
    def __init__(self, name, level, biome, pos):
        super().__init__()
        self.name = name
        self.level = level
        self.biome = biome
        self.max_hp = 10 + level * 3
        self.hp = self.max_hp
        self.image = MON_IMG.get(biome).copy()
        self.rect = self.image.get_rect(center=pos)
        self.v = pygame.Vector2(random.uniform(-1,1), random.uniform(-1,1))
        if self.v.length_squared()==0: self.v = pygame.Vector2(1,0)
        self.v = self.v.normalize() * random.uniform(20, 35)

    def update(self, dt):
        self.rect.centerx += int(self.v.x * dt)
        self.rect.centery += int(self.v.y * dt)
        if not pygame.Rect(0,0,WIDTH,HEIGHT).contains(self.rect):
            self.v *= -1
            self.rect.clamp_ip(pygame.Rect(0,0,WIDTH,HEIGHT))

class Area:
    TARGET_MON_COUNT = 5
    RESPAWN_INTERVAL = 6.0
    BUSH_RESPAWN_SEC = 6.0
    MAX_BUSHES = 10

    def __init__(self, grid):
        self.grid = grid  # GRID_H x GRID_W of biome strings
        self.bushes = []
        self.mons = pygame.sprite.Group()
        self._respawn_t = 0.0
        self._bush_t = 0.0
        self._init_bushes()
        self._init_mons()

    def _init_bushes(self):
        for _ in range(6):
            self._spawn_bush()

    def _init_mons(self):
        for _ in range(self.TARGET_MON_COUNT):
            self.mons.add(self.spawn_mon())

    def draw(self, surf):
        for y in range(GRID_H):
            for x in range(GRID_W):
                biome = self.grid[y][x]
                surf.blit(TILE_IMG[biome], (x*TILE, y*TILE))
        for r in self.bushes:
            surf.blit(BUSH_IMG, r.topleft)

    def biome_at(self, pos):
        x, y = int(pos[0]//TILE), int(pos[1]//TILE)
        x = max(0, min(GRID_W-1, x)); y = max(0, min(GRID_H-1, y))
        return self.grid[y][x]

    def _spawn_bush(self):
        # Place on a grass tile
        for _ in range(100):
            x, y = random.randrange(GRID_W), random.randrange(GRID_H//3)  # more likely upper rows
            if self.grid[y][x] != 'grass': 
                continue
            r = pygame.Rect(x*TILE+4, y*TILE+4, TILE-8, TILE-8)
            if not any(r.colliderect(b) for b in self.bushes):
                self.bushes.append(r); return

    def pick_bush(self, player):
        for r in list(self.bushes):
            if player.rect.colliderect(r):
                self.bushes.remove(r)
                return True
        return False

    def spawn_mon(self, near_pos=None):
        if near_pos is None:
            x, y = random.randrange(GRID_W), random.randrange(GRID_H)
        else:
            px, py = int(near_pos[0]//TILE), int(near_pos[1]//TILE)
            x = max(0, min(GRID_W-1, px + random.randint(-4,4)))
            y = max(0, min(GRID_H-1, py + random.randint(-3,3)))
        biome = self.grid[y][x]
        name = random.choice(CREATURES.get(biome, ["Critter"]))
        level = random.randint(1, 10)
        pos = (x*TILE + TILE//2, y*TILE + TILE//2)
        return Mon(name, level, biome, pos)

    def timers_update(self, dt, player):
        self._respawn_t += dt; self._bush_t += dt
        if self._respawn_t >= self.RESPAWN_INTERVAL:
            self._respawn_t = 0.0
            while len(self.mons) < self.TARGET_MON_COUNT:
                self.mons.add(self.spawn_mon(player.rect.center))
        if self._bush_t >= self.BUSH_RESPAWN_SEC:
            self._bush_t = 0.0
            if len(self.bushes) < self.MAX_BUSHES:
                self._spawn_bush()

class Battle:
    def __init__(self, player: Player, wild: Mon):
        self.player = player
        self.wild = wild
        self.active = True
        self.message = f"A wild {wild.name} (Lv{wild.level}) appeared!"
        self.cooldown = 0.0

    def update(self, dt): self.cooldown = max(0.0, self.cooldown - dt)

    def draw(self, surf):
        pygame.draw.rect(surf, (30,90,60), (0, HEIGHT-170, WIDTH, 170))
        pygame.draw.rect(surf, WHITE, (10, HEIGHT-160, WIDTH-20, 150), 2)
        self._hp_box(surf, (40, HEIGHT-150), f"{self.wild.name} Lv{self.wild.level}", self.wild.hp, self.wild.max_hp)
        if self.player.team:
            my = self.player.team[0]
            self._hp_box(surf, (WIDTH-360, HEIGHT-110), f"{my['name']} Lv{my['level']}", my['hp'], my['max_hp'])
        surf.blit(MON_IMG[self.wild.biome], (WIDTH-140, HEIGHT-230))
        surf.blit(PLAYER_IMG, (80, HEIGHT-230))
        draw_text(surf, self.message, (30, HEIGHT-80))
        draw_text(surf, "[F] Attack   [SPACE] Throw Ball   [B] Bag   [ESC] Run", (30, HEIGHT-52))

    def _hp_box(self, surf, pos, label, hp, maxhp):
        pygame.draw.rect(surf, WHITE, (*pos, 320, 48), 2)
        draw_text(surf, label, (pos[0]+10, pos[1]+6))
        ratio = max(0, hp)/maxhp
        w = int(300*ratio)
        color = RED if ratio<0.3 else YELLOW if ratio<0.6 else GREENBAR
        pygame.draw.rect(surf, color, (pos[0]+10, pos[1]+26, w, 12))
        pygame.draw.rect(surf, WHITE, (pos[0]+10, pos[1]+26, 300, 12), 2)

    def attack(self):
        if self.cooldown>0: return
        dmg = random.randint(2, 4) + len(self.player.team)
        self.wild.hp = max(0, self.wild.hp - dmg)
        self.message = f"You hit {self.wild.name} for {dmg}!"
        self.cooldown = 0.5
        if self.wild.hp <= 0:
            self.message = f"{self.wild.name} fainted. You found an apricorn!"
            self.player.apricorns += 1
            self.active = False

    def throw_ball(self):
        if self.cooldown>0: return
        if self.player.balls <= 0:
            self.message = "No balls left! Craft with [C]."; return
        self.player.balls -= 1
        hp_ratio = max(0.05, self.wild.hp / self.wild.max_hp)
        base = 0.5 * (1.0 - hp_ratio)
        level_penalty = max(0.1, 1.0 - (self.wild.level-1)*0.05)
        chance = base * level_penalty + 0.15
        if random.random() < chance:
            self.message = f"Gotcha! {self.wild.name} was caught!"
            self.player.team.append({"name": self.wild.name, "level": self.wild.level, "max_hp": self.wild.max_hp, "hp": self.wild.hp})
            self.player.caught_species.add(self.wild.name)
            self.active = False
        else:
            self.message = "Oh no! It broke free."
        self.cooldown = 0.8

def draw_text(surf, text, pos, color=WHITE):
    surf.blit(font.render(text, True, color), pos)

def main():
    # 3x3 world grid
    idx_for = lambda ax, ay: ay*3 + ax + 1
    areas = {}
    for ay in range(3):
        for ax in range(3):
            grid = load_level(idx_for(ax, ay))
            areas[(ax,ay)] = Area(grid)

    current = (1,1)  # start in middle area (level5)
    area = areas[current]
    player = Player(WIDTH//2, HEIGHT//2)

    battle = None
    show_help = True
    bag_open = False
    victory = False

    running = True
    while running:
        dt = clock.tick(FPS)/1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if victory: victory = False
                    elif battle and battle.active: battle.active=False; battle=None
                    else: running=False
                elif e.key == pygame.K_r: player.run = not player.run
                elif e.key == pygame.K_m: show_help = not show_help
                elif e.key == pygame.K_b: bag_open = not bag_open
                elif e.key == pygame.K_c:
                    if player.apricorns>=3:
                        player.apricorns-=3; player.balls+=1
                elif e.key == pygame.K_p:
                    area.mons.add(area.spawn_mon(player.rect.center))
                elif e.key == pygame.K_e:
                    if not battle and not victory:
                        for m in area.mons:
                            if player.rect.colliderect(m.rect.inflate(10,10)):
                                battle = Battle(player, m); break
                elif e.key == pygame.K_SPACE:
                    if victory: victory=False
                    elif battle and battle.active: battle.throw_ball()
                elif e.key == pygame.K_f:
                    if battle and battle.active: battle.attack()

        # update
        if not battle and not victory:
            player.handle_move(dt)
            area.mons.update(dt)
            if area.pick_bush(player): player.apricorns += 1
            area.timers_update(dt, player)

            # edge transitions (3x3 grid)
            moved = False
            if player.rect.right >= WIDTH:
                if current[0] < 2:
                    current = (current[0]+1, current[1]); area = areas[current]; player.rect.left = 2; moved=True
            if player.rect.left <= 0:
                if current[0] > 0:
                    current = (current[0]-1, current[1]); area = areas[current]; player.rect.right = WIDTH-2; moved=True
            if player.rect.bottom >= HEIGHT:
                if current[1] < 2:
                    current = (current[0], current[1]+1); area = areas[current]; player.rect.top = 2; moved=True
            if player.rect.top <= 0:
                if current[1] > 0:
                    current = (current[0], current[1]-1); area = areas[current]; player.rect.bottom = HEIGHT-2; moved=True

        else:
            if battle:
                battle.update(dt)
                if not battle.active:
                    try: area.mons.remove(battle.wild)
                    except Exception: pass
                    battle=None

        # victory condition
        if not victory and len(player.caught_species) >= len(ALL_SPECIES):
            victory=True

        # draw
        area.draw(screen)
        area.mons.draw(screen)
        screen.blit(PLAYER_IMG, player.rect)

        draw_text(screen, f"Area {current[0]+1},{current[1]+1}  Balls:{player.balls}  Apricorns:{player.apricorns}  Team:{len(player.team)}  Species:{len(player.caught_species)}/{len(ALL_SPECIES)}", (10,8))
        if show_help and not victory:
            pygame.draw.rect(screen, (0,0,0,160), (0, HEIGHT-56, WIDTH, 56))
            draw_text(screen, "Edges change areas (3x3). E: interact  F: attack  SPACE: ball  B: bag  C: craft  R: run  P: spawn  M: help  ESC: quit", (10, HEIGHT-40))

        if battle: battle.draw(screen)
        if bag_open and not battle and not victory:
            panel = pygame.Rect(WIDTH-260, 10, 250, 160)
            pygame.draw.rect(screen, (25,25,25,220), panel); pygame.draw.rect(screen, WHITE, panel, 2)
            draw_text(screen, "Bag", (panel.x+10, panel.y+8))
            screen.blit(BALL_IMG, (panel.x+10, panel.y+34)); draw_text(screen, f"x {player.balls}", (panel.x+38, panel.y+36))
            screen.blit(APRICORN_IMG, (panel.x+10, panel.y+62)); draw_text(screen, f"x {player.apricorns}", (panel.x+38, panel.y+64))
            draw_text(screen, "Craft [C]: 3 apricorns -> 1 ball", (panel.x+10, panel.y+100))

        if victory:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0,0,0,170)); screen.blit(overlay, (0,0))
            pygame.draw.rect(screen, WHITE, (WIDTH//2-240, HEIGHT//2-90, 480, 180), 2)
            draw_text(screen, "You caught ALL species! 🎉", (WIDTH//2-200, HEIGHT//2-60))
            draw_text(screen, "SPACE/ESC to continue exploring.", (WIDTH//2-200, HEIGHT//2-30))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
