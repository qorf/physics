# Open Worlds: handoff

Kept up to date as work goes on. The starting position, comparison and full
feature list are in `OpenWorlds.md`.

Last updated: 2026-10-19

## Where we are (2026-10-19)

**Next: freeing memory everywhere** (the user's choice). Every leak found so
far is gathered in `VulkanChanges.md`, "Next: freeing memory everywhere":
- meshes, blueprints, batches, animated buffers and staging buffers;
- texture places;
- render passes (`VulkanRenderPass:Dispose` isn't written);
- the skybox cube;
- per-frame CPU garbage.

The first step is a plan, `MemoryPlan.md`. Then come Items with exact code.

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

**A. Next: freeing memory (library)**
1. **`MemoryPlan.md`:** the plan for every leak in `VulkanChanges.md`, with
   the rule that nothing is freed while a frame in flight may still use it.
2. **Then, in order:**
   - #1 (`StopMapping`);
   - the deferred-deletion queue;
   - meshes and blueprints (#2), animated buffers (#5), batches (#15);
   - texture places (#20);
   - `VulkanRenderPass:Dispose`, staging buffers, the skybox cube;
   - per-frame CPU garbage.
3. **A memory check main:**
   - streams regions in and out, resizes, and switches MSAA;
   - reports GPU and Java memory, so growth shows.

**B. Small library fixes**

4. **#22 (order 13):** draw every texture group, with #19 (the group size).
   Today, ground textures must load before any label.
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
