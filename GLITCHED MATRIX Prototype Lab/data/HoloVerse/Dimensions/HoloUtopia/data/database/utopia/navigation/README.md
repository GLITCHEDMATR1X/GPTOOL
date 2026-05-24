# HoloUtopia Navigation

Pass 20 adds the first city-wide navigation layer for the living-world mechanics.

The route graph is intentionally simple and safe:

- every district has one center node and four gate nodes;
- atlas connections link neighboring gates;
- citizen home/work/social schedule nodes connect to their district center at route-build time;
- restricted routes are tagged, not blocked, so future Security Gate mechanics can decide what happens;
- authored navigation files are read-only during runtime.

This lets citizens move through understandable city routes before final street-level path meshes exist.
