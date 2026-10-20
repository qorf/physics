# Open Worlds: handoff

Kept up to date as work goes on. The starting position, comparison and full
feature list are in `OpenWorlds.md`.

Last updated: 2026-10-19 (end of session)

## Where we are (2026-10-19, end of session)

**Library branch: `MakeAWish`** in `quorum-language`, from Item 37 on.
Before that, `TerrainShader`; both held the same commit, `8a656d7c3`, when
the switch was made. **Never switch branches:** use the one checked out
(the user's rule).

**Library commits this round:**
- `8d0ca607f`: Item 31;
- `b1d8e1a8e`: Items 32 to 35;
- `8a656d7c3`: the white-texture fix;
- `0b5de0b62`: Item 37 (spotlights).

**Stopped here.** The current work is spotlights and water.
- **Spotlights (`SpotlightPlan.md`):**
  - Phases 1 and 2 are **committed** as `0b5de0b62` (`Item37.md`), Vulkan
    only, **not yet reported on screen**:
    - the point light direction fix;
    - a range falloff for point lights;
    - `SpotLight`, with no shadows.
  - **Under OpenGL,** adding a spotlight alerts. `EnvironmentOpenGL` was
    left unchanged at the user's request.
  - **Project:**
    - `SpotlightCheck.quorum` (A/Z cone, R/F range, S sweep, P point
      light);
    - **headlights in DriveOpen:** H switches them, N switches night. They
      are placed from the car's physics transform every frame.
- **Water (`WaterPlan.md`):** phase 1 is written as **`Item38.md`, for
  review, not applied**. It covers time, the camera position, screen size
  and near and far planes for every Vulkan 3D shader.
- **Memory:** done (`MemoryPlan.md`, Items 31 to 35, run and confirmed).
  `Item36.md` (per-frame garbage) is still for review.

**Next, in order:**
1. **Run SpotlightCheck and DriveOpen at night** (N, then H):
   - soft-edged cones;
   - the green cone turning with its platform;
   - the lamp lighting the ground around it correctly.
2. **Review and apply `Item38.md`.**
3. **Write `Item39.md`:** water phase 2, the water pass and `WaterSurface`,
   with `WaterCheck`.
4. **Later:** spotlight shadows (phase 3), OpenGL spotlights (phase 4), sky
   reflection on water (water phase 3), and fog (#17).

**Finished in this round (2026-10-19), all committed in the library:**
- **terrain materials:** AmbientCG texture sets with height blending;
- **mipmaps and anisotropic filtering;**
- **a skybox** on the shader system (OpenGL and Vulkan), and a generated day
  sky in DriveOpen;
- **MSAA** for 3D and 2D under Vulkan;
- **resize fixes:** a sharp 3D view, and shadows that survive it;
- **no boxing** in `VulkanPainter3DBatch`;
- **`vSyncEnabled` under Vulkan.**

In TerrainWalk (project), the ball snapping back was the camera being
placed before the physics step. `CameraFollower` places it after.

### What works, confirmed by the user

- **Tiers 1 and 3** (terrain data, collision near the player, streaming,
  distant terrain): see the Done table below.
- **Splatting:** four layers, painted in TerrainEditor and DriveOpen, with
  one splat texture updated in place (`Item20.md`).
- **Tier 4, stages 1 to 3** (`TierFour.md`):
  - the brush engine, and undo and redo (`RunWorldTests` 22 of 22);
  - `TerrainEditor.quorum`, with a keyboard control for every mouse control;
  - picking, the brush preview, presets, stamps, erosion and auto paint;
  - the user guide, `TerrainEditorInstructions.md`.
- **Texture sets** (`Item24.md`), on boxes and on the terrain:
  - grass is Ground037 and rock is Rocks002; dirt and sand are still plain;
  - B in the editor changes how softly they blend.
- **Mipmaps and anisotropy** (`Item25.md`): no shimmer in the distance.
- **Skybox** (`Item26.md`): SkyboxCheck under Vulkan, and the Day sky in
  DriveOpen (K toggles it).
- **3D MSAA** (`Item27.md`) and a **sharp view after a resize**
  (`Item28.md`).

### Waiting for a run

These are committed, but nobody has reported on them yet:
- **Item 30:** resize with 3D MSAA on; models stay lit and shadowed.
- **Item 29:** `MSAA2DCheck`; turned 2D squares are smooth at 4.
- **#28:** memory no longer climbing from batch boxing.
- **#29:**
  - Vulkan games now run uncapped by default (`vSyncEnabled = false`);
  - setting it to `true` gives FIFO.
- **Older items:**
  - DriveOpen: minimize and restore (#23), and the "Meshes so far" count;
  - TerrainEditor: Shift N, Shift X and Shift U.

### Commits

- **Library (`quorum-language`, `TerrainShader`):**
  - `804c85c40`: Items 7, 9 and 20, and #23;
  - `3e6fde7e0`: Item 24;
  - `768335de9`: Items 25 and 26;
  - `7ad442acb`: Items 27-30, #28 and #29.

  Nothing is uncommitted.
- **Project (`physics`):** `bb2f7c5` holds most of the work. Still
  uncommitted: TerrainWalk's `CameraFollower` and diagnostic keys, and some
  documents.

### Priority list (2026-10-19)

Each step says whether it is project work (AllTerrainVehicle) or a library
change (which needs an approved `ItemN.md` or a before-and-after first).

**Spotlights and water (the user's choice, 2026-10-19).**
- **`SpotlightPlan.md`:** a new `SpotLight` (a cone light, an `Item3D` like
  `PointLight`).
  - **Phases:**
    1. the point light direction fix;
    2. spotlights under Vulkan;
    3. their shadows;
    4. OpenGL;
    5. scenes and the editor.
  - **Status:** phases 1 and 2 are committed (`Item37.md`, `0b5de0b62`),
    not yet run. Phases 3 to 5 are not started.
- **`WaterPlan.md`:** a water pass after lighting, drawing `WaterSurface`
  models into the lit image.
  - **Effects:** depth color, a soft shore, scrolling normals, a sun glint,
    then sky reflection with fresnel.
  - **Status:** phase 1, `Item38.md` (time and camera data for 3D
    shaders), is for review. Phase 2 (`Item39.md`) is next to write.
  - Decision 6 is still open: whether fog (#17) comes first.

**A. Freeing memory (library): Items 31 to 35 done** (all committed;
the white-texture fix is `8a656d7c3`)
1. **Point light shadow maps** cost about 2.6 GB; pick an option in
   `VulkanChanges.md`.
2. **Review and apply `Item36.md`** (per-frame garbage), one part at a time,
   measuring each.
3. **Extend `MemoryCheck.quorum`** with the loops the Items describe: L
   (models), T (textures), S (lights).

**B. Small library fixes**

4. **#22 (order 13):** done in Item 32. #19 (the group size) is still open.
5. **H:** a new `Material`'s diffuse should be undefined.
6. **Batch 1:** orders 1 to 6 (B, A, #4, #14, #13).
7. **Physics:**
   - a game-level hook that runs after physics;
   - drawing positions blended between physics steps (the TerrainWalk
     findings).

**C. Better-looking ground (project)**

8. Texture sets for dirt and sand; per-set tint, roughness and detiling;
   triplanar projection on cliffs; a baked far color texture.
9. **Fog** (#17), to hide the far edge against the sky (library).

**D. World-making workflow (project)**

10. **Height layers;**
11. **rule-based painting** with derived maps;
12. **splines** for roads and rivers.

**E. Larger work, when its turn comes**

13. More than four materials (an index map, texture arrays).
14. Instancing at scale (#18), before foliage.
15. Tier 4 stage 4: brushes in Quorum Studio.
16. Moving the Worlds classes into the standard library.

**Paused tracks** (in `Handoff/Handoff.md`):
- the culling tests;
- the car model;
- shadow leftovers;
- older library bugs.

### Done

| Work | Record | Status |
|---|---|---|
| Tier 1: terrain data, queries, region meshes, editing, save and load | `OpenWorldTier1Handoff.md` | Done |
| Tier 3: collision near the player, streaming, distant terrain | `OpenWorldTier3Handoff.md` | Done |
| Texture splatting (Tier 2 goal 1) | `TextureSplattingPlan.md` | Done |
| Tier 4 stages 1 to 3 | `TierFour.md`, `TerrainEditorInstructions.md` | Done |
| Terrain materials (texture sets, height blending) | `TerrainMaterialsPlan.md`, `Item24.md` | Done |
| Library: mesh update in place, per-model shaders, minimize crash, textures in place | `Item7.md`, `Item9.md`, `Item20.md` | Committed, confirmed |
| Library: mipmaps and anisotropy | `Item25.md` | Committed, confirmed |
| Library: skybox (OpenGL and Vulkan) | `SkyboxPlan.md`, `Item26.md` | Committed, confirmed |
| Library: MSAA 3D and 2D; resize; shadows after a resize | `MSAAPlan.md`, `MSAA2DPlan.md`, `Item27.md` to `Item30.md` | Committed; 2D MSAA and Item 30 waiting for a run |
| Library: batch boxing (#28), `vSyncEnabled` under Vulkan (#29) | `VulkanChanges.md` | Committed, waiting for a run |

### Rules (unchanged)

- All code goes in AllTerrainVehicle first, in
  `Libraries.Game.Graphics.Worlds`, and moves to the standard library later.
- The standard library is changed only when the user approves that specific
  change, with the exact before and after shown first. Larger ones get an
  `ItemN.md`.
- Claude never runs the game or `Default.jar`. The user compiles, runs and
  pastes the output.
- Test main: `SourceCode/DriveOpen.quorum`. Headless tests:
  `RunWorldTests`.

## Renderer check (2026-10-17)

Kept as the record of what was found then. Since then: per-model shader
programs work (library order 9), and meshes can be updated in place (order
7).

Bugs and changes for the renderer are collected in `VulkanChanges.md`.

Paths are under `quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`.

### How 3D drawing works now

- **Deferred rendering.** A geometry pass writes four images: position,
  color, normal, and PBR values (roughness and metallic). A full-screen
  lighting pass then lights them. A terrain shader only has to fill those
  four outputs, and lighting and shadows from lights come for free.
- **Vertex pulling.** The vertex shader reads vertices and indices straight
  from GPU memory through pointers (`GL_EXT_buffer_reference`), not from
  bound vertex attributes. See `Shaders/Vulkan/Vertex/DefaultVertexShader3DVulkan.quorum`.
- **Bindless textures.** Every loaded texture sits in one global array,
  `globalTextures[]`, sized to the device's limit. Shaders pick a texture by
  index. See `Shaders/Vulkan/Fragment/DefaultFragmentShader3DVulkan.quorum`
  and `Vulkan/VulkanTextureManager.quorum`.
- **Materials** hold one diffuse color, one texture index, an optional
  normal map and an optional roughness map. One texture per material.
- **Shaders are GLSL compiled at runtime** to SPIR-V through shaderc
  (`Shaders/SPIRVShaderCompiler.quorum`). Vertex, fragment, geometry,
  compute and tessellation stages are all wired into the compiler.
- **Compute shaders are already used**: animated models are pre-processed
  by a compute shader that writes their vertices, and are then drawn by the
  normal pipeline (`Vulkan/VulkanPainter3D.quorum` near line 1080).

### The four questions

| Question | Answer |
|---|---|
| Read textures in the vertex shader? | **Not today, but a one-line change.** The global texture binding is fragment-only (`VulkanTextureManager.quorum:61`), and the upload barrier targets the fragment stage only (line 169). Adding the vertex stage to both would allow it. **Better option:** store heights in a GPU buffer and read them through a pointer, the same way vertices are read now. That needs no descriptor change. |
| Texture arrays? | **No real arrays** (every image is 2D with one layer). **Not needed**: the bindless global array already lets a shader pick any of many textures by index, which covers Terrain3D's 32 textures. |
| Unsigned integer textures (for the control map)? | **No.** Every texture is uploaded as `R8G8B8A8_UNORM` from a `PixelMap` (`VulkanTextureManager.quorum:135`, `:184`); the format line is commented out. 16-bit and float formats aren't supported either. **Workaround:** keep the control map (and heights) in GPU buffers of 32-bit unsigned integers and floats, read through pointers. |
| A custom shader and material for terrain? | **Not today.** `Model` has `SetShaderProgram`, but `VulkanPainter3D` ignores it: every model in the scene is drawn with one default pipeline (`VulkanPainter3D.quorum:1099-1100`). The shadow pass also uses one fixed pipeline. |

### Other things found

- **No mipmaps.** Textures have one level, and the one shared sampler uses
  nearest mip mode. Tiled terrain textures will shimmer and look noisy at a
  distance. Mipmap generation on upload is needed for good terrain
  texturing, and helps every model.
- **One sampler** for everything: linear filtering, repeat wrapping. Repeat
  suits tiled ground textures. Anisotropic filtering is off, even though the
  device feature query exists. Turning it on would make terrain seen at low
  angles much sharper.
- **Skybox is not implemented** in the Vulkan painter
  (`VulkanPainter3D.quorum:1690`). It matters for open worlds later.

### Renderer changes needed, by tier

- **Tier 1:** none. A CPU-built mesh with proper texture coordinates draws
  with the default pipeline and one texture, with shadows.
- **Tier 2 (splatting):** a terrain fragment shader, and either
  - **(a)** per-batch pipeline choice in `VulkanPainter3D`, which would
    also make `Model:SetShaderProgram` work for everyone (recommended); or
  - **(b)** a terrain flag in the default material and a branch in the
    default fragment shader (smaller, but grows the shader for every model).

  Also mipmaps, and preferably anisotropic filtering.
- **Tier 3 (camera-following mesh):** two possible routes.
  - **Compute route:** follow the animation pattern. A compute shader moves
    the clipmap grid's vertices to the right heights each frame, and the
    default pipeline draws them. Shadows and picking keep working unchanged.
  - **Vertex route:** a terrain vertex shader reads heights from a buffer.
    This is the Terrain3D way, but it needs its own geometry and shadow
    pipelines.

  The compute route reuses more of what exists.

## Decisions made

- Terrain3D is the guide, used the way Bullet was for physics.
- Terrain and world code goes in the standard library; brushing tools go in
  Quorum Studio (`TierFour.md`).
- Splatting uses one splat texture for the whole map, because of the
  renderer's texture groups (`VulkanChanges.md` #19, #20).
- The terrain is drawn with its own shader program (Route 2), not by
  replacing the default program (2026-10-18).
- Floating origin is deferred: the grid tops out near 8 km.

## Known issues in the current code

- `Terrain` sets every texture coordinate to `(0,0)`.
- `Terrain` stores `stickWidth` and `stickDepth` but never uses them.
- `TextureSplat` is not read by the renderer itself; our
  `TerrainSplatShaderProgram` draws the splatting.
- Texture groups 3 and up are never drawn (#22). Ground textures and
  texture sets must load before labels, or the splat shader can't reach
  them (WorldTerrain warns when one lands outside group 0).
- Meshes made for a new grid size, and streamed-out regions, can't be freed
  (order 11). This is part of the memory work next (`VulkanChanges.md`).
- A new `Material`'s diffuse is (0,0,0,0) (`VulkanChanges.md` H):
  hand-built materials must set a diffuse.
- Adding regions outside the splat texture's square makes a new splat
  texture, which lands outside group 0, and the ground turns grey until a
  restart (`TerrainEditorInstructions.md`). Reusing texture places (memory
  work) and #22 would fix it.
- Vulkan games now run uncapped by default (#29). Set `vSyncEnabled = true`
  for FIFO.

## Key places

| What | Where |
|---|---|
| Quorum terrain | `quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/Worlds/` |
| Terrain collision | `.../Libraries/Game/Collision/Shapes/HeightmapTerrainShape.quorum` |
| Noise | `.../Libraries/Compute/Noise/` |
| 3D painter (pipelines, passes) | `.../Libraries/Game/Graphics/Vulkan/VulkanPainter3D.quorum` |
| Texture upload and sampler | `.../Libraries/Game/Graphics/Vulkan/VulkanTextureManager.quorum` |
| 3D shaders | `.../Libraries/Game/Graphics/Shaders/Vulkan/` (Vertex, Fragment, Compute, Mapping) |
| Quorum Studio | `/Users/stefik/Repositories/quorum-studio/QuorumStudio` |
| Terrain3D source | `/Users/stefik/Repositories/Terrain3D/src` |
| Terrain3D design notes | `/Users/stefik/Repositories/Terrain3D/doc/docs` |
| Splatting test | `physics/TerrainSplatting` |
