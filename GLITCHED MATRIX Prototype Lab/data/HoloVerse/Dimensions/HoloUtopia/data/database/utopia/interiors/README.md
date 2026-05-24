# HoloUtopia Interiors

Safe-edit interior blueprint files for HoloUtopia buildings.

Pass 11 policy:

- Interior files are authored data only.
- Runtime should load an interior only when its building is highlighted/selected.
- Runtime state must not overwrite these files.
- Full interiors are still abstract: floors, units, activity nodes, entry nodes, and room anchors.
- Detailed modeled rooms can be added later without changing NPC home/job references.

Recommended runtime pattern:

```python
from holoutopia_town_blocks import load_interior_blueprint, attach_holoutopia_highlighted_interior

interior = load_interior_blueprint("res_alpha_lot_07_interior", ROOT)
node = attach_holoutopia_highlighted_interior(render, ROOT, "residential_alpha_neighborhood_01", "res_alpha_lot_07")
# node.removeNode() when a different building is highlighted.
```
