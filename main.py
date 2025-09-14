#!/usr/bin/env python3
"""
Pixelmon-like Pygame MVP (v4)
- One BIG scrollable map per level (levels/levelN.txt), any size.
- Camera/viewport follows player (screen=960x540, tile=30px).
- Toggleable minimap (M) in top-left showing whole level.
- Biome letters: G=grass, S=sand, W=water, .=empty (treated as grass).
- --level N command-line arg (default 1). Prints loaded level size on start.
- Mons respawn, bushes regrow, crafting (3 apricorns -> 1 ball), victory when all species caught.
- Designed to work with pygbag build.

Controls: WASD/Arrows move • E interact • F attack • SPACE throw ball • B bag • C craft • R run • M minimap • ESC quit
"""

from __future__ import annotations
import os, sys, argparse, random, json
import pygame

WIDTH, HEIGHT = 960, 540
TILE = 30
FPS = 60

WHITE=(255,255,255); BLACK=(0,0,0); RED=(220,70,70); YELLOW=(240,220,120); GREENBAR=(100,220,120)

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
LEVEL_DIR = os.path.join(os.path.dirname(__file__), "levels")
DATA_PATH = os.path.join(os.path.dirname(__file__), "creatures.json")

def load_img(name, scale_to=None):
    img = pygame.image.load(os.path.join(ASSET_DIR, name)).convert_alpha()
    if scale_to:
        img = pygame.transform.smoothscale(img, scale_to)
    return img

def parse_args():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--level", type=int, default=1)
    try:
        args, _ = p.parse_known_args()
    except SystemExit:
        # pygbag or environments without CLI
        class A: level=1
        args=A()
    return args

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pixelmon Pygame MVP v4")
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

CREATURES = json.load(open(DATA_PATH, "r", encoding="utf-8"))
ALL_SPECIES = sorted(set(sum(CREATURES.values(), [])))

def draw_text(surf, text, pos, color=WHITE):
    surf.blit(font.render(text, True, color), pos)

def load_level_any_size(idx):
    path = os.path.join(LEVEL_DIR, f"level{idx}.txt")
    if not os.path.exists(path):
        print(f"[WARN] {os.path.basename(path)} not found. Falling back to level1.txt")
        path = os.path.join(LEVEL_DIR, "level1.txt")
    with open(path, "r", encoding="utf-8") as f:
        rows = [line.rstrip("\n") for line in f if line.strip()!='']
    h = len(rows); w = len(rows[0]) if h>0 else 0
    # normalize row widths
    rows = [r.ljust(w, '.') for r in rows]
    # convert to biome names
    grid = []
    for y in range(h):
        row = []
        for x in range(w):
            c = rows[y][x]
            if c == 'G' or c == '.':
                row.append('grass')
            elif c == 'S':
                row.append('sand')
            elif c == 'W':
                row.append('water')
            else:
                row.append('grass')
        grid.append(row)
    print(f"Loaded {os.path.basename(path)} ({w}x{h} tiles)")
    return grid, w, h

class Camera:
    def __init__(self, map_w_tiles, map_h_tiles):
        self.w_px = map_w_tiles * TILE
        self.h_px = map_h_tiles * TILE
        self.x = 0
        self.y = 0
    def center_on(self, rect):
        self.x = rect.centerx - WIDTH//2
        self.y = rect.centery - HEIGHT//2
        self.x = max(0, min(self.x, self.w_px - WIDTH))
        self.y = max(0, min(self.y, self.h_px - HEIGHT))
    def apply(self, pos):
        # world (px) -> screen (px)
        return (pos[0]-self.x, pos[1]-self.y)

class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = PLAYER_IMG.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = 160
        self.run = False
        self.apricorns = 0
        self.balls = 3
        self.team = []
        self.caught_species = set()
    def handle_move(self, dt, map_w_px, map_h_px):
        keys = pygame.key.get_pressed()
        vx = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        vy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        vel = pygame.Vector2(vx, vy)
        if vel.length_squared(): vel = vel.normalize()
        speed = self.speed * (1.6 if self.run else 1.0)
        self.rect.centerx += int(vel.x * speed * dt)
        self.rect.centery += int(vel.y * speed * dt)
        self.rect.left = max(0, self.rect.left)
        self.rect.top = max(0, self.rect.top)
        self.rect.right = min(map_w_px, self.rect.right)
        self.rect.bottom = min(map_h_px, self.rect.bottom)

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
    def update(self, dt, map_w_px, map_h_px):
        self.rect.centerx += int(self.v.x * dt)
        self.rect.centery += int(self.v.y * dt)
        if self.rect.left < 0 or self.rect.right > map_w_px: self.v.x *= -1
        if self.rect.top < 0 or self.rect.bottom > map_h_px: self.v.y *= -1
        self.rect.left = max(0, self.rect.left)
        self.rect.top = max(0, self.rect.top)
        self.rect.right = min(map_w_px, self.rect.right)
        self.rect.bottom = min(map_h_px, self.rect.bottom)

class LevelWorld:
    TARGET_MON_COUNT = 7
    RESPAWN_INTERVAL = 6.0
    BUSH_RESPAWN_SEC = 6.0
    MAX_BUSHES = 20

    def __init__(self, grid, w_tiles, h_tiles):
        self.grid = grid
        self.w_tiles = w_tiles
        self.h_tiles = h_tiles
        self.w_px = w_tiles * TILE
        self.h_px = h_tiles * TILE
        self.bushes = []  # list of rects in world px
        self.mons = pygame.sprite.Group()
        self._respawn_t = 0.0
        self._bush_t = 0.0
        self._init_bushes()
        self._init_mons()

    def _init_bushes(self):
        for _ in range(10):
            self._spawn_bush()

    def _init_mons(self):
        for _ in range(self.TARGET_MON_COUNT):
            self.mons.add(self.spawn_mon())

    def tile_biome(self, tx, ty):
        tx = max(0, min(self.w_tiles-1, tx)); ty = max(0, min(self.h_tiles-1, ty))
        return self.grid[ty][tx]

    def biome_at_pixel(self, px, py):
        tx, ty = int(px//TILE), int(py//TILE)
        return self.tile_biome(tx, ty)

    def draw(self, surf, cam: Camera):
        # only draw tiles in viewport
        first_tx = cam.x // TILE
        first_ty = cam.y // TILE
        tiles_x = WIDTH//TILE + 2
        tiles_y = HEIGHT//TILE + 2
        for ty in range(first_ty, min(first_ty+tiles_y, self.h_tiles)):
            sy = ty*TILE - cam.y
            for tx in range(first_tx, min(first_tx+tiles_x, self.w_tiles)):
                sx = tx*TILE - cam.x
                biome = self.grid[ty][tx]
                surf.blit(TILE_IMG[biome], (sx, sy))
        # bushes
        for r in self.bushes:
            sx, sy = cam.apply((r.x, r.y))
            surf.blit(BUSH_IMG, (sx, sy))

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
            if player.rect.colliderect(r):
                self.bushes.remove(r)
                return True
        return False

    def spawn_mon(self, near_pos=None):
        if near_pos is None:
            tx = random.randrange(self.w_tiles); ty = random.randrange(self.h_tiles)
        else:
            ntx = int(near_pos[0]//TILE) + random.randint(-6,6)
            nty = int(near_pos[1]//TILE) + random.randint(-4,4)
            tx = max(0, min(self.w_tiles-1, ntx))
            ty = max(0, min(self.h_tiles-1, nty))
        biome = self.grid[ty][tx]
        name = random.choice(CREATURES.get(biome, ["Critter"]))
        level = random.randint(1, 10)
        pos = (tx*TILE + TILE//2, ty*TILE + TILE//2)
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
    def __init__(self, player: "Player", wild: Mon):
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
        dmg = random.randint(2,4) + len(self.player.team)
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

def draw_minimap(surf, world: LevelWorld, player: Player, show=True):
    if not show: return
    # Fit minimap into ~200x120 px box
    max_w, max_h = 220, 140
    scale = min(max_w / world.w_px, max_h / world.h_px)
    mw, mh = int(world.w_px * scale), int(world.h_px * scale)
    mm = pygame.Surface((mw, mh), pygame.SRCALPHA)
    # draw terrain coarse (sample every 2 tiles for speed on big maps)
    step = max(1, int(2 / (scale if scale>0 else 1)))
    for ty in range(0, world.h_tiles, step):
        for tx in range(0, world.w_tiles, step):
            biome = world.grid[ty][tx]
            c = (60,140,220) if biome=='water' else (216,192,128) if biome=='sand' else (64,160,84)
            x = int(tx*TILE*scale); y = int(ty*TILE*scale)
            pygame.draw.rect(mm, c, (x, y, int(TILE*scale*step), int(TILE*scale*step)))
    # bushes (green dots)
    for r in world.bushes:
        x = int(r.centerx * scale); y = int(r.centery * scale)
        pygame.draw.circle(mm, (40, 220, 80), (x,y), max(1,int(3*scale)))
    # mons (colored by biome)
    for m in world.mons:
        x = int(m.rect.centerx * scale); y = int(m.rect.centery * scale)
        c = (90,200,120) if m.biome=='grass' else (90,150,230) if m.biome=='water' else (230,210,140)
        pygame.draw.circle(mm, c, (x,y), max(1,int(3*scale)))
    # player (bright)
    px = int(player.rect.centerx * scale); py = int(player.rect.centery * scale)
    pygame.draw.circle(mm, (255,255,255), (px,py), max(2,int(4*scale)))
    # blit to screen
    surf.blit(mm, (8,8))
    pygame.draw.rect(surf, WHITE, (8,8,mw,mh), 1)

def main():
    args = parse_args()
    grid, w_tiles, h_tiles = load_level_any_size(args.level)

    world = LevelWorld(grid, w_tiles, h_tiles)
    player = Player(world.w_px//2, world.h_px//2)
    cam = Camera(w_tiles, h_tiles)

    battle = None
    show_help = True
    bag_open = False
    minimap_on = False
    victory = False

    running = True
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
                elif e.key == pygame.K_m: minimap_on = not minimap_on
                elif e.key == pygame.K_b: bag_open = not bag_open
                elif e.key == pygame.K_c:
                    if player.apricorns>=3:
                        player.apricorns-=3; player.balls+=1
                elif e.key == pygame.K_p:
                    world.mons.add(world.spawn_mon(player.rect.center))
                elif e.key == pygame.K_e:
                    if not battle and not victory:
                        for m in world.mons:
                            if player.rect.colliderect(m.rect.inflate(10,10)):
                                battle = Battle(player, m); break
                elif e.key == pygame.K_SPACE:
                    if victory: victory=False
                    elif battle and battle.active: battle.throw_ball()
                elif e.key == pygame.K_f:
                    if battle and battle.active: battle.attack()

        # update
        if not battle and not victory:
            player.handle_move(dt, world.w_px, world.h_px)
            world.mons.update(dt, world.w_px, world.h_px)
            if world.pick_bush(player): player.apricorns += 1
            world.timers_update(dt, player)
            cam.center_on(player.rect)
        else:
            if battle:
                battle.update(dt)
                if not battle.active:
                    try: world.mons.remove(battle.wild)
                    except Exception: pass
                    battle=None

        if not victory and len(player.caught_species) >= len(ALL_SPECIES):
            victory=True

        # draw
        screen.fill(BLACK)
        world.draw(screen, cam)
        # draw mons and player with camera
        for m in world.mons:
            sx, sy = cam.apply(m.rect.topleft)
            screen.blit(m.image, (sx, sy))
        screen.blit(PLAYER_IMG, cam.apply(player.rect.topleft))

        draw_text(screen, f"Balls:{player.balls}  Apricorns:{player.apricorns}  Team:{len(player.team)}  Species:{len(player.caught_species)}/{len(ALL_SPECIES)}", (10, 8))
        draw_minimap(screen, world, player, show=minimap_on)

        if show_help and not victory:
            pygame.draw.rect(screen, (0,0,0,160), (0, HEIGHT-56, WIDTH, 56))
            draw_text(screen, "E: interact  F: attack  SPACE: ball  B: bag  C: craft  R: run  M: minimap  P: spawn  ESC: quit", (10, HEIGHT-40))

        if bag_open and not battle and not victory:
            panel = pygame.Rect(WIDTH-260, 10, 250, 160)
            pygame.draw.rect(screen, (25,25,25,220), panel); pygame.draw.rect(screen, WHITE, panel, 2)
            draw_text(screen, "Bag", (panel.x+10, panel.y+8))
            screen.blit(BALL_IMG, (panel.x+10, panel.y+34)); draw_text(screen, f"x {player.balls}", (panel.x+38, panel.y+36))
            screen.blit(APRICORN_IMG, (panel.x+10, panel.y+62)); draw_text(screen, f"x {player.apricorns}", (panel.x+38, panel.y+64))
            draw_text(screen, "Craft [C]: 3 apricorns -> 1 ball", (panel.x+10, panel.y+100))

        if battle: battle.draw(screen)

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
