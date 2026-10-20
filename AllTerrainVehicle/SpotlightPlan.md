# Spotlights (plan)

Written 2026-10-19. **Phases 1 and 2 are done:** `Item37.md`, committed as
`0b5de0b62` on `MakeAWish`, with the recommended answers. They are Vulkan
only, with `EnvironmentOpenGL` unchanged at the user's request: adding a
spotlight under OpenGL alerts until phase 4. They are not yet reported on
screen. DriveOpen has headlights (H, with N for night) to see them.
Phases 3 (shadows), 4 (OpenGL) and 5 (scenes and the editor) are not
started. Once the decisions
at the end are settled, this becomes `ItemN.md` files with the exact code.

**Quorum has no spotlight.** It has `DirectionalLight` (sun) and `PointLight`
(a bulb shining every way). A spotlight is a point light limited to a cone:
- car headlights;
- a torch;
- street lamps pointing down;
- stage lights.

The only "spot" code in the library is three unused OpenGL constants, and
leftover uniform names in the old web shader (`Game.js`).

Paths: **G/** = `quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`.

## How lights work today (summary of the investigation)

**Classes:**
- `Light` holds color, the environment and shadow data. There is one
  `CascadeShadowData` per cascade, each with 6 matrices and a split
  distance.
- `DirectionalLight is Light`: direction, intensity and a culling range.
- `PointLight is Light, Item3D`: position from the item, intensity, and a
  range computed from intensity.
- **How each is added.** A point light, as an `Item3D`, reaches the
  environment through `Item3D:GetLights`, which only collects
  `PointLight`. A directional light is added straight to the environment.

**Vulkan** (`G/Models/Vulkan/EnvironmentVulkan.quorum`):
- **One storage buffer of lights**, 8 words each:
  - position or direction (3 words);
  - `isDirectional`;
  - intensity;
  - color (3 words).
- **Order:** all directional lights first, then all point lights.
  `EnsureShadowMaps`, the shadow pass and the shader all rely on that
  order.
- **Shadows** are variance shadow maps, one per light:
  - a directional light gets one layer per cascade, with an orthographic
    projection;
  - a point light gets six faces per cascade, each with a 90° perspective
    projection.

**The lighting shader** (`G/Shaders/Vulkan/Fragment/DefaultLightingFragmentShaderVulkan.quorum`):
- It loops over every light, branching on `isDirectional`.
- It uses Cook-Torrance PBR.
- Point lights fall off by inverse square, with no cut-off at their range.

**OpenGL:**
- Per-vertex lighting: up to 2 directional and 5 point lights, with no
  shadows.
- Lights beyond those limits are folded into an ambient cube.

**Scenes and the editor:**
- `PointLight` is saved and loaded as an item (`DefaultSceneManager`).
- It has an editor blueprint, preview, highlight and properties dialog
  (`Interface/Controls/Scenes/...`).

## A bug found here (fix first, with this work)

`calculatePointLight` in the lighting shader:

```glsl
vec3 tmpSub = light.positionDirection - worldPos;
vec3 L = normalize(tmpSub - worldPos);   // subtracts worldPos twice
```

The light direction should be `normalize(tmpSub)`.
- **As written,** a point light lights surfaces from the wrong direction,
  unless they are near the world's origin.
- **On the open world,** hundreds of units from the origin, point lights
  (DriveOpen's lamp) shade nearly as if the light came from the origin.
- **This is a one-line fix.** Spotlights reuse this function, so it goes in
  first.

Two smaller things in the same code:
- an unused `float intensity = 10.0f`;
- point lights have no smooth cut-off at their range. Inverse square never
  reaches zero, so a light far away still costs a full calculation, and
  can't be culled cleanly.

The plan adds the usual windowed falloff, `(1 - (d/range)^4)^2`, clamped to 0
to 1, for point lights and spotlights. It changes how point lights look
near their edge (softer, then zero), so it's decision 5.

## The design

### The class: `G/SpotLight.quorum`

`class SpotLight is Light, Item3D`, like `PointLight`, so it can be placed,
moved, and attached to a model, such as a car's headlights.

**Actions,** each calling `environment:LightChanged(me)` as point lights do:
- **Direction:** `SetDirection(x, y, z)`, `SetDirection(Vector3)` and
  `GetDirection`. The direction the cone points, in the light's own space
  (decision 2).
- **Cone angles:** `SetConeAngles(number inner, number outer)` (degrees,
  half-angles), with `GetInnerAngle` and `GetOuterAngle`.
  - Full brightness inside `inner`, fading to nothing at `outer`.
  - Defaults are 20° and 30°.
- **Intensity:** `SetIntensity` and `GetIntensity`, as `PointLight`.
- **Range:** `SetRange` and `GetRange`.
  - Explicit, unlike `PointLight`'s computed range. A headlight needs a set
    reach.
  - 0 means "from intensity", the point light formula.
- `SetLight(Color color, Vector3 position, Vector3 direction, number intensity, number outerAngle)`.
- `Copy`.
- The movement overrides that call `LightChanged`, as in `PointLight`.

### Getting it to the renderer

- `Item3D:GetLights` also collects `SpotLight`, so adding one to a layer,
  or as a child of a model, works like a point light.
- `Environment` gains:
  - `Add(SpotLight)` and `Remove(SpotLight)`;
  - `GetSpotLightIterator`, `GetSpotLightCount` and `GetSpotLight(i)`.
  - These are blueprints, implemented in `EnvironmentVulkan` and
    `EnvironmentOpenGL`.
- `EnvironmentVulkan:LightChanged`, `Add(Light)` and `Remove(Light)` accept
  `SpotLight`.
- `Layer3D` and `Game` get `Add(SpotLight)` and `Remove(SpotLight)`
  wrappers, as for `PointLight`.

### Vulkan: the light buffer

The light record grows from 8 words to 16 (64 bytes, one aligned record per
light), keeping existing fields at the same places:

| Word | Field | Point | Directional | Spot |
|---|---|---|---|---|
| 0–2 | position or direction | position | direction | position |
| 3 | `type` (was `isDirectional`) | 0 | 1 | 2 |
| 4 | intensity | ✓ | ✓ | ✓ |
| 5–7 | color | ✓ | ✓ | ✓ |
| 8–10 | spot direction | — | — | ✓ (world space, normalized) |
| 11 | range | ✓ | — | ✓ |
| 12 | cos(inner) | — | — | ✓ |
| 13 | cos(outer) | — | — | ✓ |
| 14–15 | spare | | | |

`type` keeps today's values (0 for point, 1 for directional), so existing
lights pack the same way.

**Order:** directional, then point, then spot. The three places that count
lights by index all follow it:
- the light and shadow upload in `EnvironmentVulkan`;
- `EnsureShadowMaps`;
- the shadow pass in `VulkanPainter3D`.

Each gains a third range. `maxLights` (16 by default) still caps the total.

### Vulkan: lighting

The shader's light loop becomes a three-way branch on `type`. A spotlight
is a point light times a cone factor:

```glsl
vec3 toLight = light.positionDirection - worldPos;
float distance = length(toLight);
vec3 L = toLight / distance;
float cosAngle = dot(-L, light.spotDirection);
float cone = clamp((cosAngle - light.cosOuter) / (light.cosInner - light.cosOuter), 0.0, 1.0);
cone = cone * cone;   // a softer edge
radiance = light.color * light.intensity * attenuation(distance, light.range) * cone;
```

The BRDF part is shared with `calculatePointLight`, which is split so both
can call it. Fragments outside the cone (`cone = 0`) skip the BRDF and the
shadow lookup.

### Vulkan: shadows (decision 3)

**A spotlight casts shadows like a one-face point light.**
- One perspective projection: field of view = 2 × outer angle, from
  `0.05` to the range, looking along the direction.
- It is stored in `matrix[0]` of each cascade's shadow data, as directional
  lights do.
- One layer (recommended): no cascades. A spotlight's range is short, so
  one map covers it.
  - The shadow data still has a slot per cascade, so indexing doesn't
    change. Only cascade 0 is used.

**What reuses existing code:**
- **The shader** samples it exactly as `calculateDirectionalVisibility`
  does: `matrix[0]`, a perspective divide, layer 0. That function is
  generalized to take the layer.
- **The geometry shader and the two-stage vertex shader** treat it like a
  directional light (`isPointLight = 0`, one face).
- **The geometry shader** still runs one invocation per cascade. For a
  spotlight, invocations past 0 write a layer that doesn't exist. Rather
  than that, the push constant gains a "cascades to draw" count, and
  invocations past it emit nothing.

**Memory:**
- One 2048² layer (RG32F plus D32) is 48 MB per frame slot, so 144 MB with
  3 slots.
- With `shadowMapSize` 2048, two headlights cost about 290 MB. A per-light
  size (decision 4) could halve that.

**Culling shadow casters.** `Layer3D:CollectShadowCasters` and the render
trees gain `CollectSpotShadowCasters`. It is a frustum query built from the
spotlight's projection, the same way the directional per-cascade query
uses `matrix[0]`.

### OpenGL (decision 1)

**Per-vertex like the others, without shadows:**
- `SpotLightsAttribute`, mirroring `PointLightsAttribute`;
- `EnvironmentOpenGL` support;
- up to 4 spotlights in `DefaultVertexShader3DOpenGL` (a `u_spotLights[4]`
  array, with position, direction, color, cosInner, cosOuter and range);
- the cone factor above;
- `DefaultShaderMapping3DOpenGL:BindLights` binds them, folding extras into
  the ambient cube as it does for point lights.

**Per-vertex lighting can't show a sharp cone on a big, coarse triangle.**
A headlight on a large ground quad lights it only at its corners. It works
on detailed meshes, and on the terrain, which is finely tessellated. A
note in the class says so.

### Scenes and the editor (later, decision 6)

- **`DefaultSceneManager`:** save and load `"SpotLight"` items (direction,
  angles, range, intensity), as for `"PointLight"`.
- **Scene editor:** a `SpotLightBlueprint`, `EditorSpotLight`, preview,
  highlight and properties dialog, copied from the point light ones.
- The library's two "spot" leftovers stay as they are.

## Phases (each its own reviewed Item)

1. **The point light direction fix** (one line), and the windowed range
   falloff if decision 5 is yes.
2. **SpotLight under Vulkan, without shadows:**
   - the class;
   - the environment, layer and game wiring;
   - the 16-word light record;
   - the shader branch.
   - A check program shows it.
3. **Spotlight shadows under Vulkan:**
   - projections;
   - the map layer count in `EnsureShadowMaps`;
   - the shadow pass;
   - the cascade count push constant;
   - caster culling.
4. **OpenGL spotlights** (per-vertex, no shadows).
5. **Scene save and load, and the editor** (if wanted now).

**Phases 1 to 3** are the Vulkan core. They are about 400 lines across 10
files, plus shader text.

**Project side:**
- headlights on DriveOpen's car: two `SpotLight`s as children of the
  chassis, with a key to switch them;
- **`SpotlightCheck.quorum`:** a dark scene, low ambient light, a few boxes
  and pillars on a ground plane. One spotlight sweeps slowly, and a second
  is fixed.
  - **Keys:** cone angles, range, intensity, shadows on or off, and
    switching between spotlight and point light.
  - **What to look for:**
    - a round pool of light with a soft edge;
    - shadows pointing away from the light;
    - nothing lit behind it or outside the cone.

## Decisions for the user

1. **OpenGL:** support spotlights there too (per-vertex, no shadows), as
   the skybox did (recommended)? Or Vulkan only, with OpenGL ignoring them?
2. **Direction space:** should the cone direction turn with the light's
   item rotation, and its parent's, like a headlight on a car
   (recommended)? Or always be a world direction?
3. **Shadows:** one shadow layer per spotlight, no cascades (recommended),
   or cascades like point lights?
4. **Shadow map size:** keep one size for all lights (today), or add a
   per-light size (`SetShadowMapSize` on the light, rounded to a power of
   two)? Recommended: later, with the point light memory question.
5. **Range falloff for point lights too:** apply the windowed falloff
   (smooth fade to zero at the range) to point lights as well
   (recommended; it changes their look slightly near the edge)? Or only to
   spotlights?
6. **Scenes and editor:** include saving, loading and the editor now, or
   after the renderer work (recommended)?
