# Open Worlds: handoff

Kept up to date as work goes on. The starting position, comparison and full
feature list are in `OpenWorlds.md`.

Last updated: 2026-10-17

## Where we are

- Research done. Terrain3D (MIT) chosen as the reference and cloned to
  `/Users/stefik/Repositories/Terrain3D`.
- Quorum's terrain classes and Terrain3D compared; features listed in five
  tiers in `OpenWorlds.md`.
- Checked what Quorum's Vulkan renderer can support for terrain (below).
- **No code changed yet.**

## Working on now

**Tier 1 is complete** (committed in `d9ef406`); its record is in
`OpenWorldTier1Handoff.md`. **Tier 2 (texturing)** is planned in
`OpenWorldTier2Handoff.md`, and on hold by the user's choice. **Tier 3
(open worlds)** is planned in `OpenWorldTier3Handoff.md`; step 1 (collision
only near the player) is done and checked. Step 2 (streaming regions, with
settings saved as JSON) is done and checked. Step 3 (floating origin) is
deferred as not needed yet. Distant terrain (coarse far models with skirts)
is written and waiting for a run. All code goes in AllTerrainVehicle first, and
the standard library is not changed unless the user asks.

## Next steps

1. Tier 1, following `OpenWorldTier1Handoff.md`.
2. Before Tier 2, decide how the terrain gets its own shader (see
   "Renderer changes needed" below).

## Renderer check (2026-10-17)

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
  Quorum Studio.

## Known issues in the current code

- `Terrain` sets every texture coordinate to `(0,0)`.
- `Terrain` stores `stickWidth` and `stickDepth` but never uses them.
- `TextureSplat` is not read by the renderer, so splatting is not drawn.
- `Model:SetShaderProgram` is ignored by the Vulkan 3D painter.
- Vulkan textures have no mipmaps.

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
