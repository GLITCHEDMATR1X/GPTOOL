import math
import random
import sys

import pygame


WIDTH = 960
HEIGHT = 540
FPS = 60

COLUMN_WIDTH = 6
BEDROCK_Y = HEIGHT - 70
BASE_DIRT_HEIGHT = 20

NIGHT_TOP = (12, 18, 40)
NIGHT_BOTTOM = (30, 50, 90)
DAY_TOP = (70, 140, 220)
DAY_BOTTOM = (150, 210, 255)
DIRT_BASE = (126, 84, 52)
DIRT_DARK = (96, 60, 36)
STONE_BASE = (110, 110, 120)
STONE_DARK = (80, 80, 90)
GRASS = (62, 168, 74)
WATER = (40, 80, 160)
LAVA = (220, 90, 40)


def lerp_color(color_a, color_b, t):
    return (
        int(color_a[0] + (color_b[0] - color_a[0]) * t),
        int(color_a[1] + (color_b[1] - color_a[1]) * t),
        int(color_a[2] + (color_b[2] - color_a[2]) * t),
    )


def hash_noise(value):
    random.seed(value * 17)
    return random.random()


class World:
    def __init__(self):
        self.columns = {}
        self.plants = []
        self.creatures = []
        self.exotics = []
        self.dinosaurs = []
        self.clouds = []
        self.lightning = []
        self.fires = []
        self.volcanoes = []
        self.lava_splats = []
        self.earthquake_timer = random.uniform(18, 32)
        self.earthquake_time_left = 0.0
        self.ufo = {"active": False, "x": 0.0, "y": 80.0, "timer": 0.0, "cooldown": 20.0}
        self.powerups = []
        self.raining = False
        self.rain_timer = 0
        self.next_rain = random.randint(14, 24)
        self.snowing = False
        self.snow_timer = 0
        self.next_snow = random.randint(20, 34)
        self.elapsed_time = 0.0
        self.first_tree_time = None
        self.evolution_stage = 0
        self.last_snow_time = 0.0

    def get_column(self, idx):
        if idx not in self.columns:
            self.columns[idx] = {
                "height": BASE_DIRT_HEIGHT,
                "grass": 0.0,
                "water": 0.0,
                "crater": 0.0,
                "crater_type": "none",
                "snow": 0.0,
                "water_age": 0.0,
                "lava_tunnel": 0.0,
            }
        return self.columns[idx]

    def ground_y(self, idx):
        column = self.get_column(idx)
        return BEDROCK_Y - column["height"]

    def add_mound(self, center_idx, radius, peak_height):
        for offset in range(-radius, radius + 1):
            idx = center_idx + offset
            column = self.get_column(idx)
            t = 1 - abs(offset) / radius
            mound = peak_height * (math.cos((1 - t) * math.pi) + 1) / 2
            clump = random.uniform(0.4, 1.1) * mound
            column["height"] += clump
            column["grass"] = max(0.0, column["grass"] - 0.3)
            column["crater"] = max(0.0, column["crater"] - 0.2)

    def add_snow(self, center_idx, radius, peak_height):
        for offset in range(-radius, radius + 1):
            idx = center_idx + offset
            column = self.get_column(idx)
            t = 1 - abs(offset) / radius
            mound = peak_height * (math.cos((1 - t) * math.pi) + 1) / 2
            column["snow"] += random.uniform(0.6, 1.2) * mound
            column["grass"] = max(0.0, column["grass"] - 0.2)

    def carve_crater(self, center_idx, radius, depth):
        for offset in range(-radius, radius + 1):
            idx = center_idx + offset
            column = self.get_column(idx)
            t = 1 - abs(offset) / radius
            crater = depth * (math.cos((1 - t) * math.pi) + 1) / 2
            column["height"] = max(2.0, column["height"] - crater)
            column["grass"] = 0.0
            column["water"] = 0.0
            column["crater"] = max(column["crater"], crater / 10)
            column["snow"] = 0.0

    def raise_rim(self, center_idx, radius, height):
        for offset in range(-radius, radius + 1):
            idx = center_idx + offset
            column = self.get_column(idx)
            t = 1 - abs(offset) / radius
            mound = height * (math.sin(t * math.pi) ** 2)
            column["height"] += mound
            column["grass"] = max(0.0, column["grass"] - 0.4)

    def spawn_volcano_clouds(self, center_x):
        for _ in range(random.randint(4, 7)):
            self.clouds.append(
                {
                    "x": center_x + random.uniform(-20, 20),
                    "y": random.uniform(70, 140),
                    "vx": random.uniform(8, 18),
                    "size": random.uniform(18, 36),
                    "time": 60.0,
                }
            )
        for _ in range(3):
            self.fires.append(
                {
                    "x": center_x + random.uniform(-18, 18),
                    "y": BEDROCK_Y - random.uniform(6, 14),
                    "time": 10.0,
                }
            )
        self.register_volcano(center_x)

    def register_volcano(self, center_x):
        self.volcanoes.append(
            {"x": center_x, "timer": random.uniform(1.5, 3.5)}
        )

    def spawn_cloud(self, center_x):
        self.clouds.append(
            {
                "x": center_x + random.uniform(-30, 30),
                "y": random.uniform(60, 120),
                "vx": random.uniform(6, 16),
                "size": random.uniform(20, 40),
                "time": 60.0,
            }
        )

    def update_clouds(self, dt, camera_x):
        for cloud in self.clouds:
            cloud["x"] += cloud["vx"] * dt
            cloud["time"] -= dt
        self.clouds = [
            cloud
            for cloud in self.clouds
            if cloud["x"] > camera_x - 200 and cloud["time"] > 0
        ]

    def update_volcanoes(self, dt):
        for volcano in self.volcanoes:
            volcano["timer"] -= dt
            if volcano["timer"] <= 0:
                self.spawn_cloud(volcano["x"])
                self.lava_splats.append(
                    {
                        "x": volcano["x"] + random.uniform(-10, 10),
                        "y": BEDROCK_Y - 12,
                        "vy": random.uniform(-220, -140),
                        "time": 1.2,
                    }
                )
                volcano["timer"] = random.uniform(2.5, 5.0)
        for splat in self.lava_splats[:]:
            splat["vy"] += 420 * dt
            splat["y"] += splat["vy"] * dt
            splat["time"] -= dt
            if splat["y"] > BEDROCK_Y or splat["time"] <= 0:
                self.lava_splats.remove(splat)

    def update_earthquakes(self, dt, visible_indices):
        if not self.volcanoes:
            return
        if self.earthquake_time_left > 0:
            self.earthquake_time_left -= dt
            for idx in visible_indices:
                column = self.get_column(idx)
                if column["height"] > BASE_DIRT_HEIGHT + 12:
                    avalanche = (column["height"] - BASE_DIRT_HEIGHT) * 0.01
                    column["height"] = max(2.0, column["height"] - avalanche)
                    left = self.get_column(idx - 1)
                    right = self.get_column(idx + 1)
                    left["height"] += avalanche * 0.5
                    right["height"] += avalanche * 0.5
            return
        self.earthquake_timer -= dt
        if self.earthquake_timer <= 0:
            self.earthquake_time_left = random.uniform(1.5, 3.0)
            self.earthquake_timer = random.uniform(20, 40)

    def spawn_powerup(self, center_idx):
        kind = random.choice(["life", "jump", "speed", "beast"])
        x = center_idx * COLUMN_WIDTH + COLUMN_WIDTH // 2
        self.powerups.append(
            {
                "x": x,
                "y": self.ground_y(center_idx) - 14,
                "kind": kind,
                "time": 12.0,
            }
        )

    def update_ufo(self, dt, is_night):
        if not is_night:
            self.ufo["active"] = False
            self.ufo["cooldown"] = max(0.0, self.ufo["cooldown"] - dt)
            return
        if not self.ufo["active"]:
            self.ufo["cooldown"] -= dt
            if self.ufo["cooldown"] <= 0:
                self.ufo["active"] = True
                self.ufo["timer"] = random.uniform(6, 10)
                self.ufo["x"] = random.uniform(-200, 200)
                self.ufo["y"] = random.uniform(70, 110)
                self.ufo["cooldown"] = random.uniform(20, 35)
            return
        self.ufo["timer"] -= dt
        if self.ufo["timer"] <= 0:
            self.ufo["active"] = False
            return
        self.ufo["x"] += math.sin(self.elapsed_time * 0.6) * dt * 25
        abduct_x = self.ufo["x"]
        self.creatures = [
            creature for creature in self.creatures if abs(creature["x"] - abduct_x) > 10
        ]
        self.exotics = [
            exotic for exotic in self.exotics if abs(exotic["x"] - abduct_x) > 10
        ]
        self.dinosaurs = [
            dino for dino in self.dinosaurs if abs(dino["x"] - abduct_x) > 14
        ]

    def update_terrain(self, visible_indices):
        for idx in visible_indices:
            column = self.get_column(idx)
            left = self.get_column(idx - 1)
            right = self.get_column(idx + 1)

            for neighbor in (left, right):
                diff = column["height"] - neighbor["height"]
                if diff > 6:
                    transfer = diff * 0.03
                    column["height"] -= transfer
                    neighbor["height"] += transfer

    def update_water(self, dt, visible_indices):
        for idx in visible_indices:
            column = self.get_column(idx)
            if column["water"] <= 0:
                continue
            if not self.raining and not self.snowing:
                column["water_age"] += dt
            left = self.get_column(idx - 1)
            right = self.get_column(idx + 1)

            surface = column["height"] + column["water"]
            for neighbor in (left, right):
                neighbor_surface = neighbor["height"] + neighbor["water"]
                if surface - neighbor_surface > 1.5:
                    transfer = (surface - neighbor_surface) * 0.08
                    column["water"] -= transfer
                    neighbor["water"] += transfer
            if column["water_age"] > 120:
                column["water"] = max(0.0, column["water"] - 0.05)
                if column["water"] <= 0:
                    column["water_age"] = 0.0
                    self.spawn_cloud(idx * COLUMN_WIDTH)

    def update_rain(self, dt, visible_indices, is_night):
        self.elapsed_time += dt
        self.next_rain -= dt
        if is_night:
            self.raining = False
            return
        if not self.raining and self.next_rain <= 0:
            self.raining = True
            self.rain_timer = random.uniform(5, 9)

        if self.raining:
            self.rain_timer -= dt
            for idx in visible_indices:
                column = self.get_column(idx)
                left_ground = self.ground_y(idx - 1)
                right_ground = self.ground_y(idx + 1)
                ground_y = self.ground_y(idx)
                dip_depth = ground_y - min(left_ground, right_ground)
                if dip_depth > 4:
                    column["water"] += 0.05
                elif column["water"] > 0:
                    column["water"] += 0.01
                column["water_age"] = 0.0
                column["grass"] = min(1.0, column["grass"] + 0.01)
                if column["grass"] > 0.4 and random.random() < 0.02:
                    self.spawn_plant(idx)
            if self.rain_timer <= 0:
                self.raining = False
                self.next_rain = random.uniform(18, 32)
                self.evolve_exotics()
                self.evolve_creatures()
                if (
                    self.first_tree_time is not None
                    and self.elapsed_time - self.first_tree_time >= 60
                ):
                    self.spawn_creatures(visible_indices)
        else:
            for idx in visible_indices:
                column = self.get_column(idx)
                if column["grass"] > 0.6 and random.random() < 0.004:
                    self.spawn_plant(idx)

    def update_snow(self, dt, visible_indices, is_night):
        if is_night:
            self.next_snow -= dt
            if not self.snowing and self.next_snow <= 0:
                self.snowing = True
                self.snow_timer = random.uniform(5, 9)
        else:
            self.snowing = False
        if self.snowing:
            self.snow_timer -= dt
            for idx in visible_indices:
                column = self.get_column(idx)
                column["snow"] += 0.03
                column["water_age"] = 0.0
            if self.snow_timer <= 0:
                self.snowing = False
                self.next_snow = random.uniform(24, 40)
                self.last_snow_time = self.elapsed_time
        else:
            if self.elapsed_time - self.last_snow_time > 120:
                for idx in visible_indices:
                    column = self.get_column(idx)
                    if column["snow"] > 0:
                        melt = min(0.02, column["snow"])
                        column["snow"] -= melt
                        column["water"] += melt * 0.8

    def erode(self, dt, visible_indices, wind_strength):
        erosion_rate = abs(wind_strength) * 0.00015
        if erosion_rate <= 0:
            return
        for idx in visible_indices:
            column = self.get_column(idx)
            if column["grass"] < 0.2:
                column["height"] = max(2.0, column["height"] - erosion_rate)
            if column["snow"] > 0:
                column["snow"] = max(0.0, column["snow"] - erosion_rate * 0.6)

    def spawn_plant(self, idx):
        x = idx * COLUMN_WIDTH + COLUMN_WIDTH // 2
        nearby = sum(1 for plant in self.plants if abs(plant["x"] - x) < 40)
        if nearby > 4 and random.random() < 0.7:
            return
        size = random.uniform(6, 14)
        kind = random.choices(
            ["grass", "flower", "tree", "shrub", "palm", "pine", "cherry"],
            weights=[4, 2, 1, 2, 1, 1, 0.3],
        )[0]
        self.plants.append({"x": x, "size": size, "kind": kind, "growth": 1.0})
        if kind == "tree" and self.first_tree_time is None:
            self.first_tree_time = self.elapsed_time

    def spawn_creatures(self, visible_indices):
        for _ in range(random.randint(2, 5)):
            idx = random.choice(visible_indices)
            x = idx * COLUMN_WIDTH + COLUMN_WIDTH // 2
            self.creatures.append(
                {
                    "x": x,
                    "y": self.ground_y(idx) - 6,
                    "vx": random.choice([-1, 1]) * random.uniform(0.4, 1.2),
                    "generation": random.randint(1, 4),
                    "size": random.uniform(4, 6),
                    "hostile": False,
                }
            )

    def spawn_exotics(self, center_idx):
        for _ in range(random.randint(3, 6)):
            idx = center_idx + random.randint(-4, 4)
            x = idx * COLUMN_WIDTH + COLUMN_WIDTH // 2
            self.exotics.append(
                {
                    "x": x,
                    "y": self.ground_y(idx) - 6,
                    "vx": random.choice([-1, 1]) * random.uniform(0.3, 0.9),
                    "type": "seed",
                }
            )

    def spawn_dinosaurs(self, center_idx):
        for _ in range(random.randint(2, 4)):
            idx = center_idx + random.randint(-6, 6)
            x = idx * COLUMN_WIDTH + COLUMN_WIDTH // 2
            self.dinosaurs.append(
                {
                    "x": x,
                    "y": self.ground_y(idx) - 8,
                    "vx": random.choice([-1, 1]) * random.uniform(0.4, 1.0),
                    "age_days": 0.0,
                }
            )

    def evolve_exotics(self):
        for exotic in self.exotics:
            if exotic["type"] == "seed":
                exotic["type"] = random.choice(["glider", "crawler", "hopper"])

    def evolve_creatures(self):
        self.evolution_stage += 1
        for creature in self.creatures:
            creature["generation"] += 1
            if self.evolution_stage >= 2 and random.random() < 0.3:
                creature["size"] = min(14, creature["size"] + random.uniform(3, 6))
            if self.evolution_stage >= 3 and random.random() < 0.25:
                creature["hostile"] = True
            if creature["size"] >= 12:
                creature["hostile"] = True

    def ignite_fire(self, x):
        self.fires.append({"x": x, "y": BEDROCK_Y - 8, "time": 6.0})

    def update_fire(self, dt):
        if self.raining:
            self.fires = []
            return
        for fire in self.fires[:]:
            fire["time"] -= dt
            if fire["time"] <= 0:
                self.fires.remove(fire)
        if not self.fires:
            return
        for fire in self.fires:
            self.plants = [
                plant
                for plant in self.plants
                if not (fire["x"] - 18 <= plant["x"] <= fire["x"] + 18)
            ]

    def update_lightning(self, dt):
        for strike in self.lightning[:]:
            strike["time"] -= dt
            if strike["time"] <= 0:
                self.lightning.remove(strike)

    def draw(self, surface, camera_x):
        visible_start = int(camera_x // COLUMN_WIDTH) - 5
        visible_end = visible_start + WIDTH // COLUMN_WIDTH + 10
        visible_indices = list(range(visible_start, visible_end))

        for idx in visible_indices:
            column = self.get_column(idx)
            x = idx * COLUMN_WIDTH - camera_x
            ground_y = self.ground_y(idx)
            stone_thickness = 22 + int(hash_noise(idx + 21) * 28)
            stone_top = max(ground_y, BEDROCK_Y - stone_thickness)

            noise = hash_noise(idx)
            dirt_color = lerp_color(DIRT_DARK, DIRT_BASE, noise)
            if ground_y < stone_top:
                pygame.draw.rect(
                    surface,
                    dirt_color,
                    pygame.Rect(x, ground_y, COLUMN_WIDTH, stone_top - ground_y),
                )

            stone_color = lerp_color(STONE_DARK, STONE_BASE, hash_noise(idx + 7))
            pygame.draw.rect(
                surface,
                stone_color,
                pygame.Rect(x, stone_top, COLUMN_WIDTH, BEDROCK_Y - stone_top),
            )
            if column["crater_type"] == "volcano":
                glow_height = 6
                pygame.draw.rect(
                    surface,
                    (120, 90, 80),
                    pygame.Rect(x, ground_y, COLUMN_WIDTH, 6),
                )
                pygame.draw.rect(
                    surface,
                    (220, 120, 60),
                    pygame.Rect(x, ground_y - glow_height, COLUMN_WIDTH, glow_height),
                )
            if column["lava_tunnel"] > 0:
                pygame.draw.rect(
                    surface,
                    LAVA,
                    pygame.Rect(x, ground_y, COLUMN_WIDTH, BEDROCK_Y - ground_y),
                )

            if column["grass"] > 0.1:
                grass_height = 4 + int(column["grass"] * 6)
                grass_color = lerp_color(
                    GRASS,
                    (120, 210, 120),
                    column["grass"],
                )
                pygame.draw.rect(
                    surface,
                    grass_color,
                    pygame.Rect(x, ground_y - grass_height, COLUMN_WIDTH, grass_height),
                )

            if column["snow"] > 0.1:
                snow_height = min(12, column["snow"] * 0.5)
                pygame.draw.rect(
                    surface,
                    (235, 245, 250),
                    pygame.Rect(x, ground_y - snow_height, COLUMN_WIDTH, snow_height),
                )
                if column["crater_type"] == "volcano":
                    pygame.draw.rect(
                        surface,
                        (90, 90, 90),
                        pygame.Rect(x, ground_y - snow_height, COLUMN_WIDTH, snow_height),
                    )

            if column["water"] > 0.2:
                left_ground = self.ground_y(idx - 1)
                right_ground = self.ground_y(idx + 1)
                rim_height = min(left_ground, right_ground)
                water_height = min(60, column["water"] * 24)
                water_height = min(water_height, max(0, ground_y - rim_height))
                if water_height <= 0:
                    continue
                pygame.draw.rect(
                    surface,
                    WATER,
                    pygame.Rect(x, ground_y - water_height, COLUMN_WIDTH, water_height),
                )

        pygame.draw.rect(
            surface,
            LAVA,
            pygame.Rect(0, BEDROCK_Y, WIDTH, HEIGHT - BEDROCK_Y),
        )

        for plant in self.plants:
            x = plant["x"] - camera_x
            if -50 < x < WIDTH + 50:
                size = plant["size"] * plant.get("growth", 1.0)
                if plant["kind"] == "grass":
                    pygame.draw.line(
                        surface,
                        (100, 200, 90),
                        (x, self.ground_y(int(plant["x"] // COLUMN_WIDTH)) - 2),
                        (x, self.ground_y(int(plant["x"] // COLUMN_WIDTH)) - size),
                        2,
                    )
                elif plant["kind"] == "flower":
                    stem_top = self.ground_y(int(plant["x"] // COLUMN_WIDTH)) - size
                    pygame.draw.line(
                        surface,
                        (90, 180, 90),
                        (x, stem_top + size),
                        (x, stem_top),
                        2,
                    )
                    pygame.draw.circle(surface, (240, 120, 170), (int(x), int(stem_top)), 4)
                elif plant["kind"] == "tree":
                    trunk_height = size * 1.8
                    base_y = self.ground_y(int(plant["x"] // COLUMN_WIDTH))
                    pygame.draw.rect(
                        surface,
                        (90, 60, 40),
                        pygame.Rect(x - 3, base_y - trunk_height, 6, trunk_height),
                    )
                    pygame.draw.circle(
                        surface,
                        (50, 140, 60),
                        (int(x), int(base_y - trunk_height)),
                        int(size),
                    )
                elif plant["kind"] == "shrub":
                    base_y = self.ground_y(int(plant["x"] // COLUMN_WIDTH))
                    pygame.draw.circle(surface, (80, 160, 90), (int(x), int(base_y - 4)), int(size * 0.6))
                elif plant["kind"] == "palm":
                    base_y = self.ground_y(int(plant["x"] // COLUMN_WIDTH))
                    trunk_height = size * 2.2
                    pygame.draw.rect(
                        surface,
                        (90, 70, 50),
                        pygame.Rect(x - 2, base_y - trunk_height, 4, trunk_height),
                    )
                    pygame.draw.circle(
                        surface,
                        (70, 160, 110),
                        (int(x), int(base_y - trunk_height)),
                        int(size * 0.6),
                    )
                elif plant["kind"] == "pine":
                    base_y = self.ground_y(int(plant["x"] // COLUMN_WIDTH))
                    trunk_height = size * 1.6
                    pygame.draw.rect(
                        surface,
                        (80, 60, 40),
                        pygame.Rect(x - 2, base_y - trunk_height, 4, trunk_height),
                    )
                    pygame.draw.polygon(
                        surface,
                        (40, 120, 70),
                        [
                            (x, base_y - trunk_height - size * 0.2),
                            (x - size * 0.7, base_y - trunk_height + size * 0.8),
                            (x + size * 0.7, base_y - trunk_height + size * 0.8),
                        ],
                    )
                else:
                    base_y = self.ground_y(int(plant["x"] // COLUMN_WIDTH))
                    trunk_height = size * 1.5
                    pygame.draw.rect(
                        surface,
                        (90, 60, 40),
                        pygame.Rect(x - 2, base_y - trunk_height, 4, trunk_height),
                    )
                    pygame.draw.circle(
                        surface,
                        (220, 160, 190),
                        (int(x), int(base_y - trunk_height)),
                        int(size * 0.7),
                    )

        for creature in self.creatures:
            x = creature["x"] - camera_x
            if -50 < x < WIDTH + 50:
                color_shift = creature["generation"] * 15
                if creature["hostile"]:
                    color = (210, 80 + color_shift, 60)
                else:
                    color = (160 - color_shift, 120 + color_shift, 80)
                size = creature["size"]
                pygame.draw.ellipse(
                    surface,
                    color,
                    pygame.Rect(x - size, creature["y"] - size / 2, size * 2, size),
                )
                if size >= 10:
                    pygame.draw.line(
                        surface,
                        (120, 70, 60),
                        (x + size * 0.4, creature["y"] - size * 0.4),
                        (x + size * 0.8, creature["y"] - size * 0.7),
                        2,
                    )

        for exotic in self.exotics:
            x = exotic["x"] - camera_x
            if -50 < x < WIDTH + 50:
                if exotic["type"] == "glider":
                    color = (140, 220, 240)
                elif exotic["type"] == "crawler":
                    color = (220, 180, 240)
                elif exotic["type"] == "hopper":
                    color = (200, 240, 160)
                else:
                    color = (180, 220, 200)
                pygame.draw.circle(surface, color, (int(x), int(exotic["y"])), 4)

        for dino in self.dinosaurs:
            x = dino["x"] - camera_x
            if -80 < x < WIDTH + 80:
                scale = min(8.0, 1.0 + dino["age_days"])
                body_len = 8 * scale
                body_height = 4 * scale
                body_color = (90, 190, 120)
                if scale >= 4:
                    body_color = (80, 170, 110)
                if scale >= 6:
                    body_color = (70, 150, 100)
                pygame.draw.ellipse(
                    surface,
                    body_color,
                    pygame.Rect(x - body_len * 0.5, dino["y"] - body_height, body_len, body_height),
                )
                if scale >= 3:
                    pygame.draw.circle(
                        surface,
                        (70, 130, 90),
                        (int(x + body_len * 0.35), int(dino["y"] - body_height * 0.6)),
                        int(max(2, scale * 0.4)),
                    )
                if scale >= 5:
                    pygame.draw.polygon(
                        surface,
                        (60, 110, 80),
                        [
                            (x - body_len * 0.2, dino["y"] - body_height),
                            (x - body_len * 0.1, dino["y"] - body_height - body_height * 0.6),
                            (x, dino["y"] - body_height),
                        ],
                    )

        for fire in self.fires:
            x = fire["x"] - camera_x
            if -50 < x < WIDTH + 50:
                pygame.draw.circle(surface, (255, 160, 60), (int(x), int(fire["y"])), 6)
                pygame.draw.circle(surface, (255, 210, 90), (int(x), int(fire["y"])), 3)

        for splat in self.lava_splats:
            x = splat["x"] - camera_x
            if -50 < x < WIDTH + 50:
                pygame.draw.circle(surface, (255, 120, 40), (int(x), int(splat["y"])), 5)

        for powerup in self.powerups:
            x = powerup["x"] - camera_x
            if -30 < x < WIDTH + 30:
                if powerup["kind"] == "life":
                    color = (120, 255, 160)
                elif powerup["kind"] == "jump":
                    color = (120, 200, 255)
                elif powerup["kind"] == "speed":
                    color = (255, 220, 120)
                else:
                    color = (200, 120, 255)
                pygame.draw.circle(surface, color, (int(x), int(powerup["y"])), 6)
                pygame.draw.circle(surface, (255, 255, 255), (int(x), int(powerup["y"])), 2)

        if self.ufo["active"]:
            x = self.ufo["x"] - camera_x
            if -100 < x < WIDTH + 100:
                pygame.draw.ellipse(
                    surface,
                    (180, 200, 220),
                    pygame.Rect(x - 14, self.ufo["y"], 28, 10),
                )
                pygame.draw.ellipse(
                    surface,
                    (140, 180, 210),
                    pygame.Rect(x - 8, self.ufo["y"] - 6, 16, 8),
                )
                beam_surface = pygame.Surface((40, 120), pygame.SRCALPHA)
                pygame.draw.polygon(
                    beam_surface,
                    (120, 220, 200, 80),
                    [(20, 0), (0, 120), (40, 120)],
                )
                surface.blit(beam_surface, (x - 20, self.ufo["y"] + 8))
    def draw_clouds(self, surface, camera_x):
        for cloud in self.clouds:
            x = cloud["x"] - camera_x
            if -200 < x < WIDTH + 200:
                cloud_surface = pygame.Surface((80, 50), pygame.SRCALPHA)
                alpha = int(160 * max(0.0, min(1.0, cloud["time"] / 60)))
                pygame.draw.circle(
                    cloud_surface,
                    (210, 210, 220, alpha),
                    (20, 25),
                    int(cloud["size"] * 0.6),
                )
                pygame.draw.circle(
                    cloud_surface,
                    (220, 220, 230, alpha),
                    (40, 20),
                    int(cloud["size"] * 0.75),
                )
                pygame.draw.circle(
                    cloud_surface,
                    (200, 200, 210, alpha),
                    (55, 28),
                    int(cloud["size"] * 0.55),
                )
                surface.blit(cloud_surface, (x, cloud["y"]))

        for strike in self.lightning:
            x = strike["x"] - camera_x
            if -200 < x < WIDTH + 200:
                pygame.draw.line(
                    surface,
                    (240, 250, 255),
                    (x, strike["start_y"]),
                    (x, strike["end_y"]),
                    2,
                )


class Meteor:
    def __init__(self, x, y, vx, vy, kind):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.kind = kind
        self.trail = []
        if kind == "metal_large":
            self.size = 10
        elif kind == "dino_egg":
            self.size = 7
        elif kind == "comet":
            self.size = 8
        else:
            self.size = 6

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.trail.append((self.x, self.y))
        if len(self.trail) > 8:
            self.trail.pop(0)

    def draw(self, surface, camera_x):
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(180 * (i / len(self.trail)))
            if self.kind == "ice":
                color = (190, 230, 255, alpha)
            elif self.kind == "metal":
                color = (200, 210, 230, alpha)
            elif self.kind == "dino_egg":
                color = (230, 210, 150, alpha)
            elif self.kind == "comet":
                color = (180, 255, 200, alpha)
            else:
                color = (255, 180, 90, alpha)
            trail_surface = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(trail_surface, color, (3, 3), 3)
            surface.blit(trail_surface, (tx - camera_x - 3, ty - 3))
        is_metal = self.kind in ("metal", "metal_large")
        if self.kind == "ice":
            core_color = (200, 240, 255)
        elif self.kind == "dino_egg":
            core_color = (230, 210, 160)
        elif self.kind == "comet":
            core_color = (180, 255, 210)
        else:
            core_color = (210, 230, 255) if is_metal else (255, 200, 110)
        pygame.draw.circle(
            surface,
            core_color,
            (int(self.x - camera_x), int(self.y)),
            self.size,
        )
        if is_metal:
            pygame.draw.circle(
                surface,
                (130, 160, 190),
                (int(self.x - camera_x), int(self.y)),
                max(3, self.size // 2),
            )


class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.on_ground = False
        self.anim_time = 0
        self.alive = True
        self.lives = 1
        self.jump_boost = 0.0
        self.speed_boost = 0.0
        self.beast = False

    def update(self, dt, world, keys):
        if not self.alive:
            return
        speed = 120 + (80 if self.speed_boost > 0 else 0)
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.vx = -speed
        elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.vx = speed
        else:
            self.vx = 0

        if (keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]) and self.on_ground:
            jump_strength = 260 + (120 if self.jump_boost > 0 else 0)
            self.vy = -jump_strength
            self.on_ground = False

        self.vy += 520 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        column_idx = int(self.x // COLUMN_WIDTH)
        ground_y = world.ground_y(column_idx) - 8
        if self.y >= ground_y:
            self.y = ground_y
            self.vy = 0
            self.on_ground = True

        self.anim_time += dt
        if self.jump_boost > 0:
            self.jump_boost -= dt
        if self.speed_boost > 0:
            self.speed_boost -= dt

    def respawn(self, world):
        self.x = WIDTH * 0.5
        self.y = world.ground_y(int(self.x // COLUMN_WIDTH)) - 8
        self.vx = 0
        self.vy = 0
        self.on_ground = False
        self.alive = True

    def draw(self, surface, camera_x):
        x = self.x - camera_x
        y = self.y
        stride = math.sin(self.anim_time * 8) * 2
        if self.beast:
            pygame.draw.circle(surface, (120, 90, 70), (int(x), int(y - 22)), 8)
            pygame.draw.rect(surface, (90, 70, 50), pygame.Rect(x - 8, y - 20, 16, 18))
        else:
            pygame.draw.circle(surface, (210, 180, 140), (int(x), int(y - 18)), 6)
            pygame.draw.rect(surface, (160, 120, 90), pygame.Rect(x - 5, y - 16, 10, 14))
        pygame.draw.line(surface, (120, 80, 60), (x - 2, y - 2), (x - 6, y + stride), 3)
        pygame.draw.line(surface, (120, 80, 60), (x + 2, y - 2), (x + 6, y - stride), 3)
        pygame.draw.line(surface, (120, 80, 60), (x - 5, y - 12), (x - 12, y - 6), 2)
        pygame.draw.line(surface, (120, 80, 60), (x + 5, y - 12), (x + 12, y - 6), 2)


def draw_background(surface, day_phase):
    daylight = 0.5 - 0.5 * math.cos(day_phase * math.pi * 2)
    for y in range(HEIGHT):
        t = y / HEIGHT
        top = lerp_color(NIGHT_TOP, DAY_TOP, daylight)
        bottom = lerp_color(NIGHT_BOTTOM, DAY_BOTTOM, daylight)
        color = lerp_color(top, bottom, t)
        pygame.draw.line(surface, color, (0, y), (WIDTH, y))
    if daylight > 0.55:
        pygame.draw.circle(surface, (255, 220, 120), (WIDTH - 140, 80), 36)
        pygame.draw.circle(surface, (255, 240, 180), (WIDTH - 140, 80), 18)
    else:
        pygame.draw.circle(surface, (220, 230, 240), (WIDTH - 140, 90), 28)
        pygame.draw.circle(surface, (200, 210, 220), (WIDTH - 130, 80), 8)


def main():
    pygame.init()
    pygame.display.set_caption("Meteor Genesis")
    clock = pygame.time.Clock()

    # --- Windowing / scaling (fixed virtual resolution, no world expansion) ---
    flags = pygame.RESIZABLE

    info = pygame.display.Info()
    start_w = max(640, int(info.current_w) - 16)
    start_h = max(480, int(info.current_h) - 16)

    vsync_requested = True
    try:
        window = pygame.display.set_mode((start_w, start_h), flags, vsync=1)
    except TypeError:
        vsync_requested = False
        window = pygame.display.set_mode((start_w, start_h), flags)

    # Try to start maximized (decorated, not exclusive fullscreen)
    try:
        from pygame._sdl2 import Window  # type: ignore
        Window.from_display_module().maximize()
    except Exception:
        pass

    # Fixed virtual canvas (authoritative game space)
    game_surf = pygame.Surface((WIDTH, HEIGHT)).convert()

    def compute_view(win_w, win_h):
        scale = min(win_w / WIDTH, win_h / HEIGHT) if (win_w > 0 and win_h > 0) else 1.0
        if scale <= 0:
            scale = 1.0
        view_w = max(1, int(WIDTH * scale))
        view_h = max(1, int(HEIGHT * scale))
        view_x = (win_w - view_w) // 2
        view_y = (win_h - view_h) // 2
        return scale, pygame.Rect(view_x, view_y, view_w, view_h)

    def window_to_virtual(mx, my, scale, view_rect):
        # Convert window mouse coords -> virtual coords; ignore black bars.
        if not view_rect.collidepoint(mx, my):
            return None
        vx = (mx - view_rect.x) / scale
        vy = (my - view_rect.y) / scale
        vx = max(0.0, min(WIDTH - 1.0, vx))
        vy = max(0.0, min(HEIGHT - 1.0, vy))
        return vx, vy

    win_w, win_h = window.get_size()
    scale, view_rect = compute_view(win_w, win_h)
    scaled_surf = pygame.Surface((view_rect.w, view_rect.h)).convert()

    quit_prompt = False
    font_big = pygame.font.Font(None, 60)
    font_small = pygame.font.Font(None, 30)
    shade = None  # lazy-created when prompt opens

    # --- Game state ---
    world = World()
    player = Player(WIDTH * 0.5, world.ground_y(int(WIDTH * 0.5 // COLUMN_WIDTH)) - 8)
    meteors = []
    meteor_timer = 0.0
    rain_drops = []
    wind_strength = 0.0
    wind_target = 0.0
    next_gust = random.uniform(3, 6)
    rain_spawn_accumulator = 0.0
    rain_spawn_rate = 140.0
    day_time = 0.0
    day_length = 90.0
    apocalypse_timer = 1800.0

    camera_x = 0.0

    running = True
    day_count = 0
    previous_day_phase = 0.0

    while running:
        dt_frame = clock.tick(FPS) / 1000.0

        # --- Events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                # Recreate the window surface for reliable sizing behavior.
                try:
                    if vsync_requested:
                        window = pygame.display.set_mode(event.size, flags, vsync=1)
                    else:
                        window = pygame.display.set_mode(event.size, flags)
                except TypeError:
                    window = pygame.display.set_mode(event.size, flags)

                win_w, win_h = window.get_size()
                scale, view_rect = compute_view(win_w, win_h)
                scaled_surf = pygame.Surface((view_rect.w, view_rect.h)).convert()
                shade = None  # rebuild overlay to match size

            elif event.type == pygame.KEYDOWN:
                if quit_prompt:
                    if event.key in (pygame.K_ESCAPE, pygame.K_n):
                        quit_prompt = False
                    elif event.key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                        running = False
                else:
                    if event.key == pygame.K_ESCAPE:
                        quit_prompt = True
                        shade = None

        # --- Simulation (paused while quit prompt is open) ---
        dt = 0.0 if quit_prompt else dt_frame

        # Update day/night for rendering (time only advances when not paused)
        if dt > 0:
            day_time += dt

        day_phase = (day_time % day_length) / day_length
        daylight = 0.5 - 0.5 * math.cos(day_phase * math.pi * 2)
        is_night = daylight < 0.45

        if dt > 0:
            apocalypse_timer -= dt

            if day_phase < previous_day_phase:
                day_count += 1
                for plant in world.plants:
                    plant["growth"] = min(2.5, plant.get("growth", 1.0) + 0.05)
                world.evolve_creatures()
            previous_day_phase = day_phase

            keys = pygame.key.get_pressed()
            player.update(dt, world, keys)

            camera_x = player.x - WIDTH * 0.5

            visible_start = int(camera_x // COLUMN_WIDTH) - 5
            visible_end = visible_start + WIDTH // COLUMN_WIDTH + 10
            visible_indices = list(range(visible_start, visible_end))

            world.update_terrain(visible_indices)
            world.update_water(dt, visible_indices)
            world.update_rain(dt, visible_indices, is_night)
            world.update_snow(dt, visible_indices, is_night)
            world.erode(dt, visible_indices, wind_strength)
            world.update_volcanoes(dt)
            world.update_earthquakes(dt, visible_indices)
            world.update_ufo(dt, is_night)
            world.update_fire(dt)
            world.update_lightning(dt)
            world.update_clouds(dt, camera_x)

            meteor_timer -= dt
            if meteor_timer <= 0:
                spawn_x = camera_x + random.uniform(200, WIDTH + 200)
                angle = random.uniform(math.radians(70), math.radians(120))
                speed = random.uniform(260, 360)
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed
                roll = random.random()
                if roll < 0.02:
                    kind = "dino_egg"
                elif roll < 0.05:
                    kind = "metal_large"
                elif roll < 0.17:
                    kind = "metal"
                elif roll < 0.27:
                    kind = "ice"
                elif roll < 0.35:
                    kind = "comet"
                else:
                    kind = "dirt"
                meteors.append(Meteor(spawn_x, -80, vx, vy, kind))
                meteor_timer = random.uniform(1.8, 3.8)

            for meteor in meteors[:]:
                meteor.update(dt)
                column_idx = int(meteor.x // COLUMN_WIDTH)
                ground_y = world.ground_y(column_idx)
                if meteor.y >= ground_y:
                    impact_radius = 6
                    if meteor.kind in ("metal", "metal_large"):
                        if meteor.kind == "metal_large":
                            radius = random.randint(14, 20)
                            depth = random.uniform(36, 52)
                            crater_type = "volcano"
                        elif random.random() < 0.2:
                            radius = random.randint(9, 14)
                            depth = random.uniform(18, 30)
                            crater_type = "medium"
                        else:
                            radius = random.randint(5, 8)
                            depth = random.uniform(10, 18)
                            crater_type = "small"
                        impact_radius = radius
                        world.carve_crater(column_idx, radius, depth)
                        for offset in range(-radius, radius + 1):
                            world.get_column(column_idx + offset)["crater_type"] = crater_type
                        if crater_type == "volcano":
                            world.raise_rim(column_idx, radius + 6, random.uniform(16, 28))
                            world.spawn_volcano_clouds(column_idx * COLUMN_WIDTH)
                            for offset in range(-3, 4):
                                world.get_column(column_idx + offset)["lava_tunnel"] = 1.0
                    elif meteor.kind == "ice":
                        radius = random.randint(6, 10)
                        peak = random.uniform(8, 16)
                        impact_radius = radius
                        world.add_snow(column_idx, radius, peak)
                    elif meteor.kind == "dino_egg":
                        impact_radius = 6
                        world.spawn_dinosaurs(column_idx)
                    elif meteor.kind == "comet":
                        impact_radius = 7
                        world.spawn_exotics(column_idx)
                    else:
                        radius = random.randint(6, 12)
                        peak = random.uniform(10, 26)
                        impact_radius = radius
                        world.add_mound(column_idx, radius, peak)

                    impact_min = (column_idx - impact_radius) * COLUMN_WIDTH - 10
                    impact_max = (column_idx + impact_radius) * COLUMN_WIDTH + 10
                    world.plants = [
                        plant for plant in world.plants if not (impact_min <= plant["x"] <= impact_max)
                    ]
                    world.creatures = [
                        creature for creature in world.creatures if not (impact_min <= creature["x"] <= impact_max)
                    ]
                    world.exotics = [
                        exotic for exotic in world.exotics if not (impact_min <= exotic["x"] <= impact_max)
                    ]
                    world.dinosaurs = [
                        dino for dino in world.dinosaurs if not (impact_min <= dino["x"] <= impact_max)
                    ]
                    meteors.remove(meteor)

                if player.alive and abs(meteor.x - player.x) < 8 and abs(meteor.y - player.y) < 10:
                    player.alive = False
                if meteor.kind == "comet" and meteor.y >= ground_y:
                    if random.random() < 0.35:
                        world.spawn_powerup(column_idx)

            for exotic in world.exotics:
                exotic["x"] += exotic["vx"]
                idx = int(exotic["x"] // COLUMN_WIDTH)
                exotic["y"] = world.ground_y(idx) - 6
                if random.random() < 0.01:
                    exotic["vx"] *= -1

            for dino in world.dinosaurs:
                dino["x"] += dino["vx"]
                idx = int(dino["x"] // COLUMN_WIDTH)
                dino["y"] = world.ground_y(idx) - 8
                dino["age_days"] = min(7.0, dino["age_days"] + dt / day_length)
                if random.random() < 0.01:
                    dino["vx"] *= -1

            for powerup in world.powerups[:]:
                powerup["time"] -= dt
                if powerup["time"] <= 0:
                    world.powerups.remove(powerup)
                    continue
                if abs(powerup["x"] - player.x) < 10 and abs(powerup["y"] - player.y) < 12:
                    if powerup["kind"] == "life":
                        player.lives += 1
                    elif powerup["kind"] == "jump":
                        player.jump_boost = 6.0
                    elif powerup["kind"] == "speed":
                        player.speed_boost = 6.0
                    else:
                        player.beast = True
                    world.powerups.remove(powerup)

            if player.alive:
                player_idx = int(player.x // COLUMN_WIDTH)
                if world.get_column(player_idx)["lava_tunnel"] > 0:
                    player.alive = False
                for splat in world.lava_splats:
                    if abs(player.x - splat["x"]) < 8 and abs(player.y - splat["y"]) < 10:
                        player.alive = False
                        break
                for fire in world.fires:
                    if abs(player.x - fire["x"]) < 10 and abs(player.y - fire["y"]) < 12:
                        player.alive = False
                        break

            for creature in world.creatures:
                creature["x"] += creature["vx"]
                idx = int(creature["x"] // COLUMN_WIDTH)
                creature["y"] = world.ground_y(idx) - 6
                if random.random() < 0.01:
                    creature["vx"] *= -1
                if creature["hostile"]:
                    for prey in world.creatures[:]:
                        if prey is creature:
                            continue
                        if abs(prey["x"] - creature["x"]) < 12 and abs(prey["y"] - creature["y"]) < 8:
                            world.creatures.remove(prey)
                    for prey in world.exotics[:]:
                        if abs(prey["x"] - creature["x"]) < 12 and abs(prey["y"] - creature["y"]) < 8:
                            world.exotics.remove(prey)
                    if player.alive and abs(player.x - creature["x"]) < 12 and abs(player.y - creature["y"]) < 12:
                        player.alive = False

            next_gust -= dt
            if next_gust <= 0:
                wind_target = random.uniform(-60, 60)
                next_gust = random.uniform(4, 8)
            wind_strength += (wind_target - wind_strength) * min(1, dt * 0.6)

            if world.raining:
                rain_spawn_accumulator += rain_spawn_rate * dt
                spawn_count = int(rain_spawn_accumulator)
                rain_spawn_accumulator -= spawn_count
                for _ in range(spawn_count):
                    rx = random.uniform(camera_x - 120, camera_x + WIDTH + 120)
                    ry = random.uniform(-HEIGHT, 0)
                    rain_drops.append(
                        [
                            rx,
                            ry,
                            random.uniform(320, 420),
                            random.uniform(1.0, 2.2),
                            random.uniform(0.4, 1.0),
                            random.uniform(-8, 8),
                        ]
                    )
                if world.clouds and random.random() < 0.02:
                    cloud = random.choice(world.clouds)
                    strike_x = cloud["x"] + random.uniform(10, 50)
                    world.lightning.append(
                        {"x": strike_x, "start_y": cloud["y"] + 10, "end_y": BEDROCK_Y - 5, "time": 0.12}
                    )
                    world.ignite_fire(strike_x)
                    if player.alive and abs(player.x - strike_x) < 10:
                        player.alive = False

            if world.snowing:
                rain_spawn_accumulator += (rain_spawn_rate * 0.6) * dt
                spawn_count = int(rain_spawn_accumulator)
                rain_spawn_accumulator -= spawn_count
                for _ in range(spawn_count):
                    rx = random.uniform(camera_x - 120, camera_x + WIDTH + 120)
                    ry = random.uniform(-HEIGHT, 0)
                    rain_drops.append(
                        [
                            rx,
                            ry,
                            random.uniform(160, 240),
                            random.uniform(1.0, 2.6),
                            random.uniform(0.3, 0.8),
                            random.uniform(-6, 6),
                        ]
                    )

            for drop in rain_drops[:]:
                drop[5] += (wind_strength - drop[5]) * min(1, dt * 2.5)
                drop[0] += drop[5] * dt
                drop[1] += drop[2] * dt
                if drop[1] > HEIGHT or drop[0] < camera_x - 240 or drop[0] > camera_x + WIDTH + 240:
                    rain_drops.remove(drop)

            if not player.alive:
                if player.lives > 0:
                    player.lives -= 1
                    player.respawn(world)

            if apocalypse_timer <= 0:
                world = World()
                player.respawn(world)
                meteors.clear()
                rain_drops.clear()
                meteor_timer = 0.0
                apocalypse_timer = 1800.0

        # --- Rendering (always) ---
        draw_background(game_surf, day_phase)

        world.draw_clouds(game_surf, camera_x)

        for drop in rain_drops:
            x = drop[0] - camera_x
            size = drop[3]
            alpha = int(140 * drop[4])
            droplet_surface = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(droplet_surface, (170, 210, 255, alpha), (3, 3), int(size))
            game_surf.blit(droplet_surface, (x, drop[1]))

        world.draw(game_surf, camera_x)

        for meteor in meteors:
            meteor.draw(game_surf, camera_x)

        player.draw(game_surf, camera_x)

        # Present (letterbox/pillarbox, fixed virtual resolution)
        win_w, win_h = window.get_size()
        new_scale, new_view_rect = compute_view(win_w, win_h)
        if new_view_rect.size != view_rect.size:
            scale, view_rect = new_scale, new_view_rect
            scaled_surf = pygame.Surface((view_rect.w, view_rect.h)).convert()
            shade = None
        else:
            scale, view_rect = new_scale, new_view_rect

        window.fill((0, 0, 0))
        if view_rect.w == WIDTH and view_rect.h == HEIGHT:
            window.blit(game_surf, (view_rect.x, view_rect.y))
        else:
            pygame.transform.scale(game_surf, (view_rect.w, view_rect.h), scaled_surf)
            window.blit(scaled_surf, (view_rect.x, view_rect.y))

        # Quit prompt overlay (modal)
        if quit_prompt:
            if shade is None or shade.get_size() != (view_rect.w, view_rect.h):
                shade = pygame.Surface((view_rect.w, view_rect.h), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 170))
            window.blit(shade, (view_rect.x, view_rect.y))

            title = font_big.render("Quit?", True, (255, 255, 255))
            hint = font_small.render("Y/Enter = Yes,  N/Esc = No", True, (255, 255, 255))
            tx = view_rect.x + (view_rect.w - title.get_width()) // 2
            ty = view_rect.y + (view_rect.h - title.get_height()) // 2 - 30
            hx = view_rect.x + (view_rect.w - hint.get_width()) // 2
            hy = ty + title.get_height() + 12
            window.blit(title, (tx, ty))
            window.blit(hint, (hx, hy))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
