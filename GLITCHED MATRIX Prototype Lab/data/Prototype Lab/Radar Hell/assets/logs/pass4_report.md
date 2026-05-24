# Radar Hell Pass 4

## What changed
- Added projectile enemy behavior for ranged enemies.
- Added infernal hazard zones:
  - lava pits
  - ember lanes
- Added stronger mode-specific map divergence:
  - Purge adds denser central pressure
  - Survival adds ember-lane endurance pressure and heavier wave scaling
  - Relic Hunt adds shrine obstacles and trap-oriented routing
- Rebuilt encounter reset so the world geometry is rebuilt with the new layout/mode instead of only swapping enemies.
- HUD now reports mode and active threat count.

## Validation
- syntax compile: PASS
- Panda3D xvfb runtime smoke: PASS
- fresh screenshot: PASS
- fresh crash log on latest run: none

## Next best pass
- give ranged enemies more visible projectile reads and impact FX
- add hazard-specific ambient props and sound routing
- make mode-specific reward flows stronger so each mode changes the economy, not just the objective text
