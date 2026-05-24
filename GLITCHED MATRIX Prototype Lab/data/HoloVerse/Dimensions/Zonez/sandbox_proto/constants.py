from dataclasses import dataclass


CHUNK_SIZE = 16
LOAD_RADIUS = 2.55
FADE_RADIUS = LOAD_RADIUS + 0.9
UNLOAD_RADIUS = LOAD_RADIUS + 1.9
FORWARD_PRELOAD_BIAS = 0.0
FORWARD_PRELOAD_RADIUS = FADE_RADIUS
MAX_CHUNK_REBUILDS_PER_FRAME = 12
MAX_CHUNK_GENERATIONS_PER_FRAME = 14
MAX_CACHED_CHUNKS = 180
INITIAL_BOOTSTRAP_RADIUS = LOAD_RADIUS + 0.2
FORCE_READY_RADIUS = LOAD_RADIUS + 0.55
WORLD_BOUNDARY_CHUNK_RADIUS = 6
MIN_WORLD_SIZE_CHUNKS = 4
MAX_WORLD_SIZE_CHUNKS = 10
WORLD_BOUNDARY_WALL_HEIGHT = 30.0
WORLD_BOUNDARY_MARGIN = 1.4
WORLD_HEIGHT_LIMIT = 24
WATER_LEVEL = 3
DEFAULT_SEED = 1337

PLAYER_HEIGHT = 1.85
PLAYER_RADIUS = 0.35
PLAYER_EYE_HEIGHT = 1.55
PLAYER_STEP_HEIGHT = 1.05
PLAYER_STEP_DOWN = 0.74
PLAYER_ACCEL_GROUND = 44.0
PLAYER_DECEL_GROUND = 40.0
PLAYER_ACCEL_AIR = 16.0
PLAYER_DECEL_AIR = 3.5
PLAYER_MAX_AIR_SPEED = 8.2
PLAYER_GROUND_STICK_FORCE = 2.6
PLAYER_COYOTE_TIME = 0.12
PLAYER_JUMP_BUFFER = 0.14
PLAYER_TURN_SPEED = 780.0
GRAVITY = 30.0
JUMP_SPEED = 9.25
MOVE_SPEED = 7.0
SPRINT_MULTIPLIER = 1.65
DRONE_MOVE_SPEED = 11.0
DRONE_ASCEND_SPEED = 7.5
DRONE_SPRINT_MULTIPLIER = 1.85
DRONE_ACCEL = 30.0
DRONE_DECEL = 22.0
MOUSE_SENSITIVITY = 0.105
CAMERA_MOUSE_SMOOTHING = 16.0

CAMERA_DISTANCE = 7.4
CAMERA_HEIGHT = 2.2
CAMERA_SMOOTHING = 12.0
CAMERA_POSITION_SMOOTHING = 15.0
CAMERA_LOOKAHEAD = 4.8
CAMERA_SHOULDER_OFFSET = 0.84
CAMERA_VERTICAL_OFFSET = 0.34
CAMERA_COLLISION_PADDING = 0.26
MAX_RAY_DISTANCE = 10.0

ATLAS_TILE_SIZE = 32
ATLAS_COLUMNS = 4
ATLAS_ROWS = 4


@dataclass(frozen=True)
class BlockDef:
    block_id: int
    name: str
    color: tuple[float, float, float, float]
    solid: bool = True
    alpha: float = 1.0


@dataclass(frozen=True)
class ZoneDef:
    key: str
    name: str
    folder_name: str
    seed_offset: int
    background_color: tuple[float, float, float, float]
    fog_color: tuple[float, float, float]
    fog_density: float
    ambient_color: tuple[float, float, float, float]
    sun_color: tuple[float, float, float, float]
    sun_hpr: tuple[float, float, float]
    atlas_variant: str = 'default'
    grayscale_player: bool = False


BLOCK_DEFS = {
    0: BlockDef(0, 'Air', (0.0, 0.0, 0.0, 0.0), False, 0.0),
    1: BlockDef(1, 'Grass', (1.0, 1.0, 1.0, 1.0)),
    2: BlockDef(2, 'Dirt', (1.0, 1.0, 1.0, 1.0)),
    3: BlockDef(3, 'Stone', (1.0, 1.0, 1.0, 1.0)),
    4: BlockDef(4, 'Sand', (1.0, 1.0, 1.0, 1.0)),
    5: BlockDef(5, 'Brick', (1.0, 1.0, 1.0, 1.0)),
    6: BlockDef(6, 'Wood', (1.0, 1.0, 1.0, 1.0)),
    7: BlockDef(7, 'Glass', (1.0, 1.0, 1.0, 0.42), alpha=0.42),
    8: BlockDef(8, 'Leaves', (1.0, 1.0, 1.0, 1.0), alpha=1.0),
    9: BlockDef(9, 'Planks', (1.0, 1.0, 1.0, 1.0)),
}

HOTBAR_IDS = [1, 3, 5, 6, 7, 8, 9]

ZONE_ORDER = ['day_zone', 'night_zone', 'dread_zone', 'hell_zone', 'candy_zone', 'desert_zone', 'tropical_zone', 'tech_zone', 'polar_zone']

ZONE_DEFS = {
    'day_zone': ZoneDef(
        key='day_zone',
        name='Day Zone',
        folder_name='day_zone',
        seed_offset=0,
        background_color=(0.52, 0.72, 0.95, 1.0),
        fog_color=(0.52, 0.72, 0.95),
        fog_density=0.013,
        ambient_color=(0.47, 0.50, 0.58, 1.0),
        sun_color=(0.98, 0.94, 0.86, 1.0),
        sun_hpr=(35.0, -52.0, 0.0),
        atlas_variant='default',
        grayscale_player=False,
    ),
    'night_zone': ZoneDef(
        key='night_zone',
        name='Night Zone',
        folder_name='night_zone',
        seed_offset=25000,
        background_color=(0.03, 0.05, 0.11, 1.0),
        fog_color=(0.05, 0.08, 0.14),
        fog_density=0.011,
        ambient_color=(0.18, 0.22, 0.30, 1.0),
        sun_color=(0.34, 0.40, 0.56, 1.0),
        sun_hpr=(-18.0, -20.0, 0.0),
        atlas_variant='default',
        grayscale_player=False,
    ),
    'dread_zone': ZoneDef(
        key='dread_zone',
        name='Dread Zone',
        folder_name='dread_zone',
        seed_offset=51000,
        background_color=(0.01, 0.01, 0.01, 1.0),
        fog_color=(0.03, 0.03, 0.03),
        fog_density=0.022,
        ambient_color=(0.26, 0.26, 0.26, 1.0),
        sun_color=(0.72, 0.72, 0.72, 1.0),
        sun_hpr=(14.0, -18.0, 0.0),
        atlas_variant='grayscale',
        grayscale_player=True,
    ),
    'hell_zone': ZoneDef(
        key='hell_zone',
        name='Hell Zone',
        folder_name='hell_zone',
        seed_offset=79000,
        background_color=(0.22, 0.05, 0.02, 1.0),
        fog_color=(0.38, 0.12, 0.05),
        fog_density=0.015,
        ambient_color=(0.78, 0.30, 0.18, 1.0),
        sun_color=(1.0, 0.72, 0.30, 1.0),
        sun_hpr=(24.0, -28.0, 0.0),
        atlas_variant='hell',
        grayscale_player=False,
    ),
    'candy_zone': ZoneDef(
        key='candy_zone',
        name='Candy Zone',
        folder_name='candy_zone',
        seed_offset=108000,
        background_color=(0.98, 0.82, 0.90, 1.0),
        fog_color=(0.96, 0.76, 0.87),
        fog_density=0.008,
        ambient_color=(0.86, 0.76, 0.88, 1.0),
        sun_color=(1.0, 0.92, 0.98, 1.0),
        sun_hpr=(14.0, -38.0, 0.0),
        atlas_variant='candy',
        grayscale_player=False,
    ),
    'desert_zone': ZoneDef(
        key='desert_zone',
        name='Desert Zone',
        folder_name='desert_zone',
        seed_offset=137000,
        background_color=(0.90, 0.74, 0.50, 1.0),
        fog_color=(0.88, 0.70, 0.45),
        fog_density=0.010,
        ambient_color=(0.76, 0.66, 0.52, 1.0),
        sun_color=(1.0, 0.93, 0.78, 1.0),
        sun_hpr=(48.0, -36.0, 0.0),
        atlas_variant='default',
        grayscale_player=False,
    ),
    'tropical_zone': ZoneDef(
        key='tropical_zone',
        name='Tropical Sky Zone',
        folder_name='tropical_zone',
        seed_offset=164000,
        background_color=(0.40, 0.72, 0.98, 1.0),
        fog_color=(0.62, 0.84, 1.0),
        fog_density=0.0065,
        ambient_color=(0.52, 0.60, 0.68, 1.0),
        sun_color=(0.98, 0.95, 0.86, 1.0),
        sun_hpr=(28.0, -40.0, 0.0),
        atlas_variant='default',
        grayscale_player=False,
    ),
    'tech_zone': ZoneDef(
        key='tech_zone',
        name='Tech Zone',
        folder_name='tech_zone',
        seed_offset=191000,
        background_color=(0.01, 0.02, 0.05, 1.0),
        fog_color=(0.02, 0.05, 0.10),
        fog_density=0.014,
        ambient_color=(0.12, 0.14, 0.20, 1.0),
        sun_color=(0.16, 0.26, 0.44, 1.0),
        sun_hpr=(-28.0, -18.0, 0.0),
        atlas_variant='default',
        grayscale_player=False,
    ),
    'polar_zone': ZoneDef(
        key='polar_zone',
        name='Polar Zone',
        folder_name='polar_zone',
        seed_offset=219000,
        background_color=(0.54, 0.76, 0.99, 1.0),
        fog_color=(0.95, 0.97, 1.0),
        fog_density=0.025,
        ambient_color=(0.72, 0.78, 0.88, 1.0),
        sun_color=(0.88, 0.96, 1.0, 1.0),
        sun_hpr=(26.0, -42.0, 0.0),
        atlas_variant='polar',
        grayscale_player=False,
    ),
}

