# Open Worlds: handoff

Kept up to date as work goes on. The starting position, comparison and full
feature list are in `OpenWorlds.md`.

Last updated: 2026-10-19

## Where we are (2026-10-19)

**Working on:** ground materials and texture filtering. Tier 4's in-game
editor is done and working. The terrain is splatted with AmbientCG
texture sets that blend by height. Mipmaps and anisotropic filtering
(`Item25.md`) were applied on 2026-10-19, and the user is testing them now.

### What works, confirmed by the user

- **Tiers 1 and 3** (terrain data, collision near the player, streaming,
  distant terrain): see the Done table below.
- **Splatting:** four layers, painted in TerrainEditor and DriveOpen.
  - One splat texture covers the whole map, updated in place (library
    #20, `Item20.md`).
  - The z mirror and PixelMap's blending were fixed in the project.
- **Tier 4, stages 1 to 3** (`TierFour.md`):
  - the brush engine, undo and redo (`RunWorldTests` 22 of 22);
  - `TerrainEditor.quorum`, with a keyboard control for every mouse
    control, picking, the brush preview, presets, stamps, erosion and auto
    paint;
  - user guide: `TerrainEditorInstructions.md`.
- **Texture sets** (`Material:SetTextureSet`, library item 24,
  `Item24.md`):
  - checked on boxes in `TextureSetCheck`: color, normal (GL and DX),
    roughness and AO;
  - then on the terrain (`TerrainMaterialsPlan.md` step 2):
    `WorldTerrain:SetLayerMaterial`, a layer table texture, and height
    blending in the splat shader;
  - grass is Ground037 and rock is Rocks002; dirt and sand are still plain
    speckled textures;
  - B in the editor changes how softly they blend.
- **DriveOpen, TerrainEditor and TextureUpdateCheck** all run as expected
  (2026-10-19).

### Being tested now

**Item 25: mipmaps and anisotropic filtering.**
- The library is on `TerrainShader`, uncommitted. The Java changed, so the
  plugins must be rebuilt.
- The project side: `textureGrad` in the splat shader, and mipmaps on the
  ground textures.
- Check in this order:
  1. `MipMapCheck.quorum`: the red floor crawls, the green floor fades to
     grey;
  2. `TextureSetCheck`: the boxes don't darken with distance;
  3. TerrainEditor: no shimmer, and no sparkles at layer edges.
- MoltenVK was checked by reading its source: every part maps directly
  onto Metal.

### Commits

- **Library (`quorum-language`, `TerrainShader`):**
  - `804c85c40` holds orders 7, 9, 12 and 15 (`Item7`, `Item9`, #23,
    `Item20`);
  - `3e6fde7e0` holds item 24;
  - item 25 is not committed.
- **Project (`physics`):** nothing has been committed since `7ea652a`
  (2026-10-17). That covers all of Tier 4, the editor, texture sets on the
  terrain, the checks and these documents, about 60 files.

### Priority list (2026-10-19)

The recommended order. Each step says whether it is project work
(AllTerrainVehicle) or a library change (which needs an approved
`ItemN.md` or before-and-after first).

**A. Finish and secure what's in flight**
1. **Confirm Item 25,** with the three checks above.
2. **Commit:** item 25 in the library, and the project's work since
   2026-10-17.
3. **Run the checks never reported on:**
   - DriveOpen: minimize for several seconds, then restore (#23), and the
     "Meshes so far" count while editing;
   - TerrainEditor: Shift N, Shift X and Shift U (world-wide preset,
     erosion and auto paint); smooth and ramp after their fixes.
4. **Small clean-ups from this round:**
   - Library, small: a new `Material`'s diffuse should be undefined, not
     (0,0,0,0) (`VulkanChanges.md` H). Hand-built models are invisible
     without the workaround.
   - Project: drop the splat shader's non-terrain branch and the
     metallic -1 marker, now that the terrain has its own program
     (`Item9.md` follow-up).

**B. Library fundamentals, small and blocking**

5. **#22 (order 13): draw every texture group,** with **#19** (group
   size). Today ground textures must load before any label, or they can't
   be drawn. More texture sets, and any game with more than about 90
   textures, run into this. A few lines; test on its own.
6. **Batch 1 bug fixes** (orders 1 to 6: B, A, #1, #4, #14, #13). Each is
   a few lines, and the project already works around them.

**C. Better-looking ground (project, no library change)**

7. **Texture sets for all four layers:** AmbientCG sets for dirt and sand
   (or Snow013 in their place), so no layer is flat.
8. **Per-set adjustments in the splat shader:** tint, roughness, AO
   strength, normal strength. Also detiling (rotating or offsetting tiles
   to hide repeats), as Terrain3D does.
9. **Triplanar or biplanar projection on steep slopes,** so cliffs don't
   stretch (GRW list 10).
10. **A baked far ("vista") color texture** for far models (GRW 8). Distant
    ground then matches near ground in one lookup.

**D. World-making workflow (project; GRW's biggest wins)**

11. **Height layers** (GRW 1): base, procedural and hand layers summed per
    region, each erasable. Stamps, erosion and generated features stop
    wiping hand work.
12. **Rule-based material distribution with derived maps** (GRW 3, 4):
    slope, height, curvature, flow and noise rules, re-runnable. This grows
    out of today's auto paint.
13. **Splines:** roads and rivers that flatten or carve the ground and
    paint it (GRW 5).

**E. Larger library work, when its turn comes**

14. **Freeing GPU memory** (order 11: #2, #5, #15). Streamed regions never
    give memory back. Needed before long play sessions or big worlds.
15. **Fog and a skybox** (#17, #11). The far edge of the world shows today.
    **Skybox applied** as `Item26.md` on `TerrainShader` (uncommitted),
    OpenGL and Vulkan on the shader system; check with `SkyboxCheck.quorum`,
    then BlockBreaker (OpenGL). SkyboxCheck ran under Vulkan. DriveOpen
    now loads a generated day sky (`Skyboxes/Day/`, `useSkybox`, K
    toggles it).
15b. **MSAA (Vulkan only):** applied as `Item27.md` on `TerrainShader`
    (uncommitted): G-buffer resolved in the scene pass, coverage-aware
    lighting, `Game:SetMultisampling`, off by default. Check with
    `MSAACheck.quorum`. The resize fix is `Item28.md` (applied). 2D MSAA
    (`MSAA2DPlan.md` option A, `Game:SetMultisampling2D`) is applied as
    `Item29.md`; check with `MSAA2DCheck.quorum`. Items 27-29 are
    uncommitted.
16. **More than four materials:** a material index (control) map, with
    texture arrays or a larger bindless budget (GRW 11, 12).
17. **Instancing at scale** (#18, GRW 17), before Tier 5's grass, rocks
    and trees.
18. **Tier 4 stage 4:** brushes in Quorum Studio (`TierFour.md`).
19. **Moving the Worlds classes into the standard library,** once the
    workarounds above can come out.

**Paused tracks** (in `Handoff/Handoff.md`):
- culling tests (`TestFrustrum.md`), then moving the tests into Quorum;
- the car model (`CarModel.md`) and `Model:LoadParts`;
- shadow leftovers and older library bugs.

### Done

| Work | Record | Status |
|---|---|---|
| Tier 1: terrain data, queries, region meshes, editing, save and load | `OpenWorldTier1Handoff.md` | Done, committed (`d9ef406`). |
| Tier 3 step 1: collision only near the player | `OpenWorldTier3Handoff.md` | Done, checked. |
| Tier 3 step 2: streaming regions, settings in `terrain.json` | `OpenWorldTier3Handoff.md` | Done, checked. |
| Tier 3: distant terrain (coarse far models with skirts) | `OpenWorldTier3Handoff.md` | Done, running in every DriveOpen run. |
| Texture splatting (Tier 2 goal 1): four layers, slope rule, painting | `TextureSplattingPlan.md` | Working; one splat texture, updated in place. |
| Tier 4 stages 1 to 3: brushes, undo, TerrainEditor, world-making tools | `TierFour.md`, `TerrainEditorInstructions.md` | Working. |
| Terrain materials: texture sets, height blending | `TerrainMaterialsPlan.md`, `Item24.md` | Working (2026-10-19). |
| Library order 7: meshes update in place | `Item7.md` | Committed (`804c85c40`). |
| Library order 9: per-model shader programs (Route 2) | `Item9.md` | Committed (`804c85c40`); splatting under it confirmed. |
| Library order 12: minimize crash (#23) | `VulkanChanges.md` | Committed (`804c85c40`); the minimize run isn't reported yet. |
| Library order 15: textures update in place (#20, #21) | `Item20.md` | Committed (`804c85c40`); confirmed. |
| Library item 24: texture-set materials | `Item24.md` | Committed (`3e6fde7e0`); confirmed. |
| Library item 25: mipmaps, anisotropic filtering (#7, #8) | `Item25.md` | Applied, uncommitted, being tested. |

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
  (order 11).
- A new `Material`'s diffuse is (0,0,0,0) (`VulkanChanges.md` H):
  hand-built materials must set a diffuse.
- Adding regions outside the splat texture's square makes a new splat
  texture, which lands outside group 0, and the ground turns grey until a
  restart (`TerrainEditorInstructions.md`).

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
