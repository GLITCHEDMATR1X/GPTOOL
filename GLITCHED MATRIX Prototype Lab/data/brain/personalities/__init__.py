from typing import Dict

from .nyx import PERSONALITY as NYX
from .solace import PERSONALITY as SOLACE
from .vanta import PERSONALITY as VANTA
from .archivist import PERSONALITY as ARCHIVIST
from .ember import PERSONALITY as EMBER
from .mirror import PERSONALITY as MIRROR
from .orbit import PERSONALITY as ORBIT
from .sable import PERSONALITY as SABLE

PERSONALITIES: Dict[str, dict] = {
    "NYX": NYX,
    "SOLACE": SOLACE,
    "VANTA": VANTA,
    "ARCHIVIST": ARCHIVIST,
    "EMBER": EMBER,
    "MIRROR": MIRROR,
    "ORBIT": ORBIT,
    "SABLE": SABLE,
}
