# Vulkan renderer: bugs and changes for later

Written 2026-10-17 during the Open Worlds work, and added to since. These
are all standard library changes, so each one needs the user's go-ahead
before it is made. The order they're done in, and their status, is in
`LibraryChangesPlan.md`.

**Applied on `TerrainShader` (2026-10-18, not committed):** #3
(`Item7.md`), #6 (`Item9.md`), #23, and the model half of #21. Everything
else is not started.

Paths:
- **G/** = `quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`
- **J/** = `quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`

Line numbers were right on 2026-10-17. Orders 7, 9 and 12 have since moved
lines in `MeshVulkan`, `ModelManagerVulkan`, `VulkanPainter3D` and
`VulkanPainter3DBatch`, so line numbers there are approximate.

## Summary

| # | Problem | Kind | Size of fix | Needed for |
|---|---|---|---|---|
| 1 | `StopMapping` passes the wrong handle to VMA | Bug (Java) | A few lines | Any freeing of buffers |
| 2 | Mesh GPU memory is never freed | Missing feature | ~200–250 lines, ~6 files | Tier 3 (regions loading and unloading) |
| 3 | A mesh can't be updated after it is made (**applied**) | Missing feature | ~60–80 lines, 2 files | Tier 1 step 5 (editing) |
| 4 | Copy barrier misses the vertex shader stage | Bug | A few lines | Any mesh upload, more so with updates |
| 5 | Animated models leak buffers when their blueprint changes | Bug | Part of #2 | Animated models |
| 6 | `Model:SetShaderProgram` is ignored (**applied**) | Missing feature | Medium | Tier 2 (terrain shader) |
| 7 | No mipmaps | Missing feature | Medium | Tier 2 (tiled ground textures) |
| 8 | Anisotropic filtering is off | Setting | Small | Tier 2 (ground at low angles) |
| 9 | Only `R8G8B8A8_UNORM` textures | Limitation | Medium | Only if terrain maps move into textures |
| 10 | Textures can't be read in vertex shaders | Limitation | One or two lines | Only for the vertex-shader route in Tier 3 |
| 11 | Skybox not implemented | Missing feature | Medium | Open worlds, later |
| 12 | Unused "global buffer index" code | Leftover code | Remove | Nothing; tidying |
| 13 | Texture override writes the global index | Bug (latent, Java) | 1 line | More than one texture group |
| 14 | Animation compute pass isn't ordered before drawing | Bug (latent) | Small | Animated models; a compute clipmap |
| 15 | Painter batches are never removed | Missing feature | Small | Streaming (with #2) |
| 16 | No camera-relative drawing | Missing feature | ~40 lines (Java) | Large worlds |
| 17 | No fog or distance fade | Missing feature | ~20-40 lines | Hiding the far edge |
| 18 | Draw queues fixed at 8192 instances | Limitation | Small | Many objects |
| 19 | Texture groups sized by the uniform buffer limit (31 on the user's Mac); multi-group drawing broken | Bug (confirmed) | Small for the limit; the multi-group path needs review | Any game with more than about 30 textures |
| 20 | Textures can't be updated; texture places never reused (**same-size updates applied**) | Missing feature | Medium | Painting splat maps |
| 21 | Resources are recorded into a command buffer that isn't recording while the window is minimized (**models and textures fixed**) | Bug | Small | Any loading while minimized |
| 22 | The default draw loops count frames in flight instead of texture groups, so groups 3 and up are never drawn | Bug (found reading the code) | A few lines | Any game with more than about 90 textures |
| 23 | Models keep piling into batches while the window is minimized, and the first frame after restoring overflows the instance buffer (**applied**) | Bug (crash, confirmed) | About 6 lines | Any 3D game that is minimized for a few seconds |
| 24 | Materials can't use texture sets (separate color, normal, roughness, AO and height maps) | Missing feature | Medium (Quorum, Java helper, 4 shaders) | Terrain materials; any model with an AmbientCG set. **Applied** 2026-10-19 (`Item24.md`) |

## 1. `StopMapping` passes the wrong handle (bug)

**Where:** J/Vulkan/VulkanBuffer.java, `StopMapping` (about line 146).

```java
vmaUnmapMemory(pluginMemoryAllocator.GetAllocatorPointer(), mappedMemoryPointer);
```

`vmaUnmapMemory` takes the **allocation handle** (`memoryHandle`), not the
pointer to the mapped memory. The pointer is also never reset, so
`IsMapping()` stays true afterward.

**Effects:**
- This is almost certainly the "crash" in the comment at
  G/Models/Vulkan/MeshVulkan.quorum:161, which is why staging buffers are
  never unmapped.
- `Dispose` calls `StopMapping` first, so disposing any mapped buffer is
  unsafe today.

**Fix:**

```java
vmaUnmapMemory(pluginMemoryAllocator.GetAllocatorPointer(), memoryHandle);
mappedMemoryPointer = 0;
```

Also make `Dispose` do nothing when the buffer was never created or was
already disposed (for example, when `bufferHandle` is 0), and set the handles
to 0 after `vmaDestroyBuffer`.

Once this is fixed, the commented-out `StopMapping` calls in `MeshVulkan`
can be tried again.

## 2. Mesh GPU memory is never freed (missing feature)

**What happens now:**
- `MeshVulkan:Load` (G/Models/Vulkan/MeshVulkan.quorum:48-165) makes a
  CPU-visible staging buffer and a GPU-only buffer, for vertices, indices
  and animation data each. The staging buffers are kept forever after the
  copy.
- `ModelManagerVulkan` caches every blueprint by key in `cachedBlueprints`
  (G/Models/Vulkan/ModelManagerVulkan.quorum:35, 116-138) and never removes
  one.
- `VulkanBuffer` has `Dispose` (G/Vulkan/VulkanBuffer.quorum:70), but
  nothing in `Models/Vulkan` calls it.
- `MaterialManagerVulkan` has its cache commented out (lines 20-38) and no
  way to free.
- `Model:Dispose` doesn't touch the blueprint.

**Why freeing must wait:**
- Several frames are in flight at once, one per swapchain image (usually 2
  or 3). Each has its own command buffer and fence.
- `VulkanGraphics:BeginNextFrame` (G/Vulkan/VulkanGraphics.quorum:410-415)
  waits on the fence for the frame slot it is about to reuse.
- A buffer used in frame N may still be read by the GPU until frame N's
  fence signals. Freeing it right away can crash the GPU or show garbage.
- Today the only freeing happens at shutdown and on swapchain rebuild, after
  `device:WaitUntilIdle()`.

**Good news:** the painter reads each mesh's buffer addresses fresh every
frame (G/Vulkan/VulkanPainter3DBatch.quorum about line 162;
J/Vulkan/VulkanDrawQueue3DInstanceMappedMemory.java lines 31-42). So
replacing a mesh's buffers is safe for later frames. Only the old buffers
need to be kept alive a little longer.

**Fix, in order:**
1. Fix bug #1 first.
2. **Deferred-deletion queue** in `VulkanGraphics`:
   - `QueueForDisposal(VulkanBuffer buffer)` stores the buffer with the
     frame number after which it is safe (the current frame plus the
     swapchain image count).
   - In `BeginNextFrame`, after the fence wait, dispose every queued buffer
     whose frame has passed.
   - About 40 lines.
3. **`MeshVulkan:Dispose`** queues the vertex, index and animation buffers
   and their staging buffers.
4. **Free staging buffers after the first copy**, unless the mesh is marked
   as one that changes (see #3).
5. **`ModelBlueprintVulkan:Dispose`** disposes its meshes.
6. **`ModelManagerVulkan:RemoveBlueprint(text key)`** removes the blueprint
   from `cachedBlueprints`, disposes it, and removes its meshes from
   `pendingMeshes` if they haven't been copied yet.
7. **Optional:** count how many models use each blueprint. Add one in
   `Model:Load` and remove one in `Model:Dispose`, and free the blueprint
   when the count reaches 0. Without this, the game decides when to call
   `RemoveBlueprint`.
8. **`ModelResourcesVulkan:Dispose`** (see #5).

**Rule:** never free anything on the spot. Swap in the new buffers first,
so the next frame records the new addresses. Then queue the old ones, and
free them only once every frame that might use them has finished.

## 3. A mesh can't be updated after it is made (missing feature)

**Status (2026-10-18): applied on branch `TerrainShader`, waiting for a
run.** The design and exact code are in `Item7.md`. It also adds a pause
guard to `ModelManagerVulkan` (item 21) and a barrier after mesh copies, which
covers #4 for meshes.

**What happens now:** `MeshVulkan:TransferBuffers`
(G/Models/Vulkan/MeshVulkan.quorum:183-211) copies only once, because of a
`dataTransferred` flag. To change a mesh today, a game must build a whole
new blueprint under a new key. Because of #2, the old one leaks.

**Smallest fix (for editable terrain, same vertex count):**
- In `MeshVulkan`:
  - Move the vertex packing loop (lines 73-103, 14 floats per vertex) into
    its own action.
  - Add `UpdateVertices(MeshData data)`. It checks that the vertex count is
    the same, packs the new vertices into the staging buffer (still mapped,
    because of #1), and clears `dataTransferred`.
  - On a re-upload, `TransferBuffers` copies only the vertex buffer.
- In `ModelManagerVulkan`, add `QueueMeshUpdate(MeshVulkan mesh)`. It adds
  the mesh to `pendingMeshes` and skips handing out buffer numbers again
  (see #12).
- Fix the barriers (#4).
- About 60 to 80 lines, 2 files, no Java change.

**Hazards:**
- **The GPU buffer:** frames still in flight may be drawing from it while
  the new copy overwrites it. At worst this is one frame of torn ground.
  A barrier before the copy (#4) makes it correct.
- **The staging buffer:** the CPU must not write it while the last copy
  from it is still running. This is safe if each mesh is updated at most
  once per frame, after `BeginNextFrame` has waited on its fence.
- **Fully safe version:** one staging buffer per frame in flight, chosen by
  `GetCurrentResourceIndex`. About 30 more lines.

**Fuller fix (a different vertex count):** `ReplaceData(MeshData)` makes new
buffers, swaps them in, and queues the old ones for disposal. This needs #2.

## 4. The copy barrier misses the vertex shader stage (bug)

**Where:** G/Vulkan/VulkanPainter3D.quorum:1065-1078.

After mesh data is copied, a barrier makes drawing wait for the copy. Its
destination stage is `PIPELINE_STAGE_VERTEX_INPUT_BIT`. The 3D vertex shader
doesn't use vertex input; it reads vertices by buffer address in the
**vertex shader** stage. So the barrier doesn't strictly cover the reads.
This works today mostly by luck of timing.

The barrier also only runs when there are pending batches to draw, not when
there were copies.

**Fix:**
- Make the destination stage include `PIPELINE_STAGE_VERTEX_SHADER_BIT`
  (and the compute stage if animated meshes read the data).
- Record the barrier whenever `ProcessPendingResources` recorded a copy
  this frame.
- For in-place updates (#3), also add a barrier **before** the copy: from
  vertex shader reads to transfer writes.

## 5. Animated models leak buffers (bug)

**Where:** G/Models/Vulkan/ModelResourcesVulkan.quorum:95-121,
`SetFromBlueprint`.

For an animated model, this makes one GPU buffer per mesh for the animated
vertices. The compute shader writes them each frame
(G/Vulkan/VulkanPainter3D.quorum about lines 1528-1550). Calling
`SetFromBlueprint` again, as `Model:Load` does, replaces the array without
freeing the old buffers. Nothing frees them when the model is disposed,
either.

**Fix:** add `ModelResourcesVulkan:Dispose`, which queues these buffers for
disposal (#2). Call it from `Model:Dispose` and at the start of
`SetFromBlueprint`. Because compute writes these buffers, freeing must also
wait for the animation fence (`animationFence`, VulkanPainter3D about lines
1492-1494).

This pattern (a per-model GPU buffer written every frame) is also a model
for a compute-based terrain mesh in Tier 3.

## 6. `Model:SetShaderProgram` is ignored (missing feature)

**Status (2026-10-18): applied on branch `TerrainShader`, waiting for a
run.** See `Item9.md`.

**Where:** G/Vulkan/VulkanPainter3D.quorum:1099-1100. Every model in the
geometry pass is drawn with one default pipeline. The shadow pass also uses
one fixed pipeline (about line 1236). `Model` has `SetShaderProgram`
(G/Model.quorum about line 2348), but the Vulkan painter never reads it.

**Fix:** group batches by shader program and bind each program's pipeline
before drawing its batches, falling back to the default. A custom program
must write the same four geometry-pass outputs (position, color, normal,
PBR values), so lighting keeps working.

**Simpler alternative for terrain only:** add a terrain flag to the material
and branch in the default fragment shader. It's smaller, but every model
pays for it.

## 7. No mipmaps (missing feature)

**Applied with #8 in `Item25.md` (2026-10-19), waiting for a run.**

**Where:** G/Vulkan/VulkanTextureManager.quorum, `ProcessPendingTextures`
(about lines 115-200). Images are made with one mip level, and the shared
sampler uses nearest mip mode. Repeating textures, like ground, shimmer and
look noisy in the distance.

**Fix:** make images with a full mip chain, generate the levels with
`vkCmdBlitImage` after upload (or on the CPU), and set the sampler's mip
mode to linear and its maximum level of detail to match.

## 8. Anisotropic filtering is off (setting)

**Applied with #7 in `Item25.md`.** The device feature is already turned on
when supported (`VulkanDevice.java`); only the sampler needs it.

**Where:** the default sampler in `VulkanTextureManager.quorum` (about line
73) uses `VulkanSamplerInfo` defaults, which turn anisotropy off. The device
feature check exists (`VulkanPhysicalDeviceFeatures:HasSamplerAnisotropy`).

**Fix:** when the device supports it, turn the feature on at device
creation and set the sampler's anisotropy (for example, 8 or 16). Ground
seen at a low angle gets much sharper.

## 9. Only RGBA8 textures (limitation)

**Where:** `VulkanTextureManager.quorum:135` and `:184` always use
`FORMAT_R8G8B8A8_UNORM`. The line that would read the `PixelMap`'s format is
commented out (`:121`).

**Effect:** no 16-bit, float or integer textures. Terrain3D keeps heights in
32-bit float textures and its control map in 32-bit integers. The plan is to
keep these in GPU buffers read by address instead, so this only matters if
that plan changes.

## 10. Textures can't be read in vertex shaders (limitation)

**Where:** `VulkanTextureManager.quorum:61` makes the global texture array
fragment-only, and the upload barrier (`:169`) only targets the fragment
stage.

**Fix, if needed:** add the vertex stage to both. This only matters if Tier
3 takes the vertex-shader route instead of the compute route.

## 11. Skybox not implemented (missing feature)

**Applied as `Item26.md` (2026-10-19), waiting for a run with
`SkyboxCheck`.** OpenGL and Vulkan draw it through `SkyboxShaderProgram`.

**Where:** G/Vulkan/VulkanPainter3D.quorum:1689-1690, `SetSkybox` prints
"NYI". Needed for open worlds later.

## 12. Unused global buffer index code (leftover code)

**Where:** G/Models/Vulkan/ModelManagerVulkan.quorum about lines 59-61 and
91-104.
- Meshes are handed "global" vertex and index buffer numbers, but the
  global arrays are commented out and nothing reads the numbers.
- The `recycledVertexIDs` branch is marked "TO-DO".
- Rendering uses buffer addresses directly, so there is no buffer table to
  maintain.

**Fix:** remove it, or at least make sure an update (#3) doesn't hand out
new numbers.

## Suggested order

**Superseded** by `LibraryChangesPlan.md`, which covers every item here.
Kept as the first idea:

1. **#1** on its own. It's a real bug and a small change.
2. **#3 and #4** when Tier 1 reaches editing (step 5).
3. **#2 and #5** together as their own piece of work, before Tier 3.
4. **#6, #7 and #8** at the start of Tier 2.
5. **#9, #10, #11 and #12** when they are needed.

## 13. Texture override writes the global index (latent bug)

**Where:** J/Vulkan/VulkanDrawQueue3DInstanceMappedMemory.java:52 writes
`texture.GetVulkanTextureIndex()`, the global index. But the draw queue, and
so the bound texture set, is chosen by `GetVulkanTextureGroupIndex()`, and
materials use the local index in the group (`GetVulkanTextureLocalIndex`,
MaterialVulkan.quorum:139). The two agree only while every texture is in
group 0.

**Fix:** write the local index in the group. Matters once more textures are
loaded than one descriptor set holds. This is L4 in
`OpenWorldTier2Handoff.md`.

## 14. Animation compute pass isn't ordered before drawing (bug)

**Where:** G/Vulkan/VulkanPainter3D.quorum `ComputeAnimations` (about
1488-1569). The compute shader writes animated vertices on the compute
queue and is submitted with only `animationFence`. The graphics pass has no
barrier or semaphore waiting for those writes; its only barrier is transfer
to vertex input (about 1069-1077). The compute queue is usually the same
family as graphics, which hides the problem.

**Fix:** record the compute work into the frame's render command buffer,
before the scene pass, with a barrier from compute-shader write to
vertex-shader read; or signal a semaphore from the compute submit that the
graphics submit waits on.

## 15. Painter batches are never removed (missing feature)

**Where:** G/Vulkan/VulkanPainter3DBatch.quorum (`age`, lines 20 and 64),
`VulkanPainter3D:GetBatch` (about 864-886). Batches are made per blueprint
and kept forever. Once blueprints can be freed (#2), batches that haven't
been used for a while should be removed too.

## 16. No camera-relative drawing (missing feature)

**Where:** J/Vulkan/VulkanDrawQueue3DInstanceMappedMemory.java (about line
72 onward) casts each model matrix to float. The camera's matrix goes
through `MatrixToArray` (VulkanPainter3D about 1720-1738). World positions
are worked out in float in the shader, so objects jitter far from the
origin.

**Fix (about 40 lines):** subtract the camera position from each model's
translation in 64-bit before the cast to float, and send the shader a view
matrix with no translation.

## 17. No fog or distance fade (missing feature)

**Where:** no Vulkan shader has a distance term apart from point-light
falloff (DefaultLightingFragmentShaderVulkan.quorum about 198-200).

**Fix:** distance fog in the deferred lighting shader, from the G-buffer
position and the camera position. About 20-40 lines plus settings.

## 18. Draw queues are fixed at 8192 instances (limitation)

**Where:** `DEFAULT_MAX_INSTANCES = 8192` (VulkanPainter3D.quorum:108), used
for every queue (about 1676-1682), with no growth.

**Fix:** grow a queue (or add another) when it fills.

## 19. Texture groups are sized by the uniform buffer limit (suspected bug)

**Where:** G/Vulkan/VulkanGraphics.quorum `GetMaxDescriptorsPerStage`
(about line 894) uses `limits:GetMaxPerStageDescriptorUniformBuffers()`. It
sizes the global texture array and texture groups in
`VulkanTextureManager:Create`. The binding holds sampled images, so the
limit should be `maxPerStageDescriptorSampledImages` (or the update-after-bind
version, since the set is update-after-bind). On Apple GPUs through MoltenVK
the uniform buffer limit can be small, so groups would be small, and any
game with more textures than that falls into the multi-group path, which has
bugs (#13).

**Status: confirmed 2026-10-17** on the user's Mac: `31 textures per group`.
With about 125 textures loaded before it (the splatting prototype's first
design), the car's materials were in group 4, and **the car wasn't drawn at
all**. Splat textures beyond group 0 didn't show properly either (#13). So
the multi-group path is broken for materials too, not only for the texture
override, and this limit makes any game with more than about 30 textures
hit it.

## 20. A texture can't be updated, and texture places are never reused (missing feature)

**Status (2026-10-19): applied on `TerrainShader`** for same-size reloads
(`Item20.md`): a texture loaded again at the same size keeps its image and
index. Different sizes still get a new place, and nothing is freed (#2).

**Confirmed blocking (2026-10-18):** in `TerrainEditor`, each paint stroke's
new splat texture lands at index 72 and up (group 2), after the labels'
glyph textures, so the splat shader can't read it and the ground turns grey.
Updating the splat texture in place would keep it at its first index (5).

**Where:** G/Vulkan/VulkanTextureManager.quorum `ProcessPendingTextures`
(about lines 186-195). Every load, including loading new pixels into an
existing `Texture`, makes a new image and takes the next texture place
(`nextTextureID`). The `recycledTextureIDs` branch is an unfinished TO-DO.
So anything that changes a texture often, like a painted splat map, uses up
places, and with #19 it soon leaves the first group.

**Fix:** a way to write new pixels into an existing texture's image
(staging copy plus barriers, like a first load, keeping its place). And
reuse places of freed textures once frames in flight are done (with #2's
deferred deletion).


## 21. Recording while the window is minimized (bug)

**Where:** G/Vulkan/VulkanGraphics.quorum:410-428 and Game.quorum about
lines 801-806.

When the window is minimized, `BeginNextFrame` returns before it resets and
begins the frame's command buffer. `Game` still calls
`textures:ProcessPendingTextures()` and `models:ProcessPendingResources()`,
which record copy commands into that command buffer while it isn't
recording. That is invalid Vulkan use.

**Fixed for models** in Item 7: `ModelManagerVulkan:ProcessPendingResources`
returns early while rendering is paused and keeps its waiting work. **Still
open for textures:** `VulkanTextureManager` needs the same guard.


## 22. The draw loops count frames, not texture groups (bug)

**Where:** G/Vulkan/VulkanPainter3D.quorum, the geometry pass loop and the
shadow pass's list of default queues (`i < drawQueues:GetSize()`).

`drawQueues` has one entry per frame in flight (usually 3), and each entry
is an array of queues indexed by texture group. The loops use the outer size
as the number of groups. So only groups 0 to 2 are ever drawn, and a model
whose textures are in group 3 or later silently disappears. Groups 0 to 2
also get queues made even when unused.

**Fix:** loop to `drawQueues:Get(resourceIndex):GetSize()`. It changes which
models are drawn, so it's its own reviewed item. The custom-program loops
added in #6 already loop over texture groups.


## 23. Minimizing piles models into batches, then crashes (bug)

**Seen:** 2026-10-18. DriveOpen was minimized, then restored, and crashed
with `BufferOverflowException` in
`VulkanDrawQueue3DInstanceMappedMemory.TransferInstanceData`, called from
`VulkanPainter3DBatch:ProcessBatch` in `VulkanPainter3D:End`.

**Why:** while the window is minimized, `VulkanPainter3D:Begin` and `End`
return early, but `Layer3D:Draw` still calls `Render(model)` for every
visible model. `Render` adds the model to its batch, and only `End` (through
`PrepareForNextFrame`) empties the batches. So every paused frame adds every
model again. With about 100 models, a little over a second at 60 frames a
second passes the 8192 instances a draw queue holds. The first frame after
restoring tries to write them all and overflows. Animated models pile up in
`animatedModels` the same way.

This predates Items 7 and 9; nothing they changed is on this path.

**Fix (applied 2026-10-18 on `TerrainShader`, waiting for a run):**
- a new field `boolean framePaused`;
- `Begin` sets it from `graphics:IsRenderingPaused()` and returns early when
  it's true, as before;
- `Render` returns right away when it's true.

Since `Begin` runs before every `Render` in `Layer3D:Draw`, the paused frame
adds nothing to the batches.

## 25. No anti-aliasing for 3D (missing feature)

**Applied as `Item27.md` (2026-10-19), waiting for a run.** MSAA for the
scene (G-buffer) pass, resolved in the pass, with coverage-aware lighting;
`Game:SetMultisampling(samples)`, Vulkan only, off by default. Also fixed
there: the lighting pass listed the scene's albedo attachment instead of its
own `lightColorAttachment` (identical until MSAA). Plan: `MSAAPlan.md`.

## 26. The 3D view is stretched and blurry after a resize (bug)

Found 2026-10-19 (the user confirmed it in DriveOpen). `RegenerateSwapchain`
remade the swapchain's framebuffers, but `VulkanPainter3D` kept its G-buffer,
lighting and MSAA images at the first window size, and never freed old
images when it remade them. **Applied as `Item28.md`, waiting for a run:**
the painter remembers its framebuffer size, remakes everything when the
swapchain's size or the MSAA count changes, and frees the old images.

## 27. Lit models turn black after the 3D passes are remade (bug)

Found 2026-10-19: with 3D MSAA on, a resize turned every lit model black
(the sky still showed). Two old bugs, exposed once Item 28 made the passes
get remade: the shadow projection buffers are linked only once
(`shadowProjectionResourcesLinked` never cleared), and the shadow maps are
linked only when their framebuffers are first made (the disposal loop in
`RegenerateRenderPasses` walks an empty array). **Applied as `Item30.md`,
waiting for a run:** the flag is cleared and the existing shadow maps are
linked into the new descriptor sets.

## 28. `VulkanPainter3DBatch` boxes integers every frame (performance)

Raised by the user (2026-10-19): `drawQueueUses` was an `Array<integer>`,
so every `Set` while counting meshes per texture group made a boxed
`Integer`, a steady stream of garbage each frame. **Applied on
`TerrainShader` (2026-10-19, uncommitted), waiting for a run:**
- an `Integer32BitArray` with a capacity (4 to start), grown by doubling
  and copying when a higher texture group appears (`EnsureUsesCapacity`),
  so the size never has to be known ahead and nothing is made after the
  first frames;
- `drawQueueUseCount`, one past the highest group used, bounds the loops;
- the draw loop now looks up a group's draw queue only when that group was
  used. Looking one up makes the queue if it doesn't exist, so before this
  a batch using only group 2 also made queues for groups 0 and 1.

Noticed while there: `Integer32BitArray.java`'s `Set` checks
`index > ints.length` instead of `>=`, so setting one past the end throws a
Java `ArrayIndexOutOfBoundsException` rather than Quorum's
`InvalidLocationError`. Harmless here (the batch never does it), but worth
fixing with item B (`LibraryChangesPlan.md` order 1).

## 29. `vSyncEnabled` was ignored under Vulkan (bug)

Found 2026-10-19 while looking into TerrainWalk. Vulkan always used FIFO
(`VulkanSwapchainInfo`'s default), and `DesktopDisplay.SetVSync` only acts for
OpenGL, so `DesktopConfiguration.vSyncEnabled` and `Game:SetVSync` did
nothing under Vulkan. **Applied on `TerrainShader` (2026-10-19, uncommitted,
Java changed), waiting for a run:**
- `VulkanGraphics:Initialize` sets the present mode from `vSyncEnabled`:
  true gives FIFO, false gives IMMEDIATE;
- `VulkanSwapchain.java` checks the surface's present modes and falls back
  to FIFO (always available) when the requested one isn't offered, writing
  the mode used back to the swapchain info;
- the default stays `false` (the user's choice), so **Vulkan games now run
  uncapped (IMMEDIATE) by default**, as OpenGL already did. A game sets
  `vSyncEnabled = true` or calls `SetVSync(true)` for FIFO;
- `SetVSync`'s documentation said vSync was on by default, and now says off;
- setting the present mode through `DesktopConfiguration.vulkanOptions` is
  now always overridden by `vSyncEnabled`.

Related, in TerrainWalk (project only): the ball's "snap back" was the camera
being placed before the physics step; `CameraFollower` places it after.

## Other library bugs found along the way

These aren't in the Vulkan renderer, but they were found during the same
work and need fixing the same way, with the user's go-ahead.

### A. `FileReader:ReadLines` always fails (bug)

**Where:** J/../System/QuorumFileReader.java, `ReadLinesNative` (about lines
134-157). Note this is under `Libraries/System`, not `Game/Graphics`.

```java
do {
    line = bufferedReader.readLine();
    if (line == null) {
        if (atEOF) {
            throw new EOFException();
        }
        atEOF = true;
        line = "";
        readSoFar = fileSize;
    } else {
        lines += line + newLine;
        ...
    }
} while (line != null);
```

At the end of the file, `line` is set to `""`, so the loop runs once more.
`readLine()` returns null again, `atEOF` is now true, and it throws
`EndOfFileError`. Every non-empty file hits this, so `ReadLines` never
returns. Found 2026-10-17 when `TerrainData:Load` used it (DriveOpen's save
check).

**Fix:** end the loop when `readLine()` returns null, and don't throw:

```java
String line = bufferedReader.readLine();
while (line != null) {
    lines += line + newLine;
    readSoFar += line.length() + newLine.length();
    line = bufferedReader.readLine();
}
atEOF = true;
readSoFar = fileSize;
return lines;
```

**Workaround used now:** `TerrainData:Load` reads one line at a time with
`ReadLine` until `IsAtEndOfFile` is true. `ReadLine` handles the end of the
file correctly.

### B. `Integer32BitArray` and `Number32BitArray` fail before `SetSize` (bug)

**Where:** J/../Containers/Integer32BitArray.java, `GetSize` (line 33)
returns `ints.length`, but `ints` is null until `SetSize` is called (line
38). So asking a new array its size throws a null pointer error, instead of
answering 0. Found 2026-10-17 in `TerrainCollision:ChooseCells` (the
"Terrain collision squares" test). `Number32BitArray` is built the same way
and should be checked.

**Fix:** start with an empty array (`ints = new int[0]`), or have `GetSize`
return 0 when it is null. `Get` and `Set` already check for null.

**Workaround used now:** `TerrainCollision` keeps its own count of how much
room its arrays have, and `TerrainRegion` checks its region size before
asking its array.

### C. An item removed from a Layer3D and added again doesn't collide (bug)

**Where:** G/../Game/Layer3D.quorum `Remove` (about lines 583-606) calls
`item:SetCollidable(false)` after destroying the item's collision nodes.
`Add` (about line 459) never sets it back, and `Item3D:SetLayer` only makes
collision nodes for collidable items. So an item taken out of a layer and
put back, which is the natural way to reuse objects, is drawn and simulated
but nothing collides with it, silently. Found 2026-10-17: reused terrain
collision pieces let the vehicle fall through the ground.

**Fix:** in `Remove`, destroy the nodes without changing the item's
collidable setting. The setting is the game's choice, not the layer's.
(Or restore it in `Add`, but then a game that turned collision off on
purpose would get it back.)

**Workaround used now:** `TerrainCollision` and `WorldTerrain` call
`SetCollidable` before adding an item again.


### D. `EditorLayer3D` input-group overrides (checked: not a bug)

**Checked 2026-10-18** while reading Quorum Studio for Tier 4. Studio's copy
of the library (2026-09-25) has three `EditorLayer3D` overrides that put
added items in the scene editor's input group: `Add(Item3D)`,
`Add(integer, Item3D)` and `AddToFront`. The current library keeps
`Add(Item3D)`, which still sets the group (line 219). The other two went
because the frustum-culling change removed those actions from `Layer3D`
itself. So nothing is lost.

### E. `PixelMap:SetPixel` blends by default (surprising; to discuss)

**Found:** 2026-10-19, while finding why terrain splatting never showed.

`PixelMap` keeps one blending setting shared by every PixelMap, and it
starts as source-over (`PixelMap.java`, `SetBlend(BLEND_SOURCE_OVER)`).
libGDX's `gdx2d_set_pixel` blends the new pixel with the old one when
blending is on. So `SetPixel` with a color whose alpha is 0 leaves a new
(empty) map unchanged.

That's reasonable for drawing pictures, but surprising for writing raw data
into pixels (splat weights, packed numbers), where every byte should be
stored as given. The project works around it by setting `Blending:NONE`
while writing, then putting the old setting back.

**Options to discuss:**
- document it on `SetPixel`;
- add a `SetPixelExactly` (or a parameter) that never blends;
- make blending a per-PixelMap setting instead of a shared one.

### F. `GetPixel` and `SetPixel` on a converted image use an invalid pointer (latent bug)

**Found:** 2026-10-19, while writing `Item24.md`.

Under Vulkan, `PixelMap.LoadPixelMap` (Java, about line 92) converts any image
that isn't RGBA8888 (gray, RGB, JPG) into a new Java buffer with
`LoadFromByteBuffer`, and returns. `basePointer` is never set on that path,
so it stays -1. But `GetPixel`, `SetPixel`, `Fill` and the drawing actions
pass `basePointer` to the native code, which would read or write through an
invalid pointer. The native image that was loaded is also never freed.

Nothing has hit it yet, since nothing calls `GetPixel` on loaded gray or RGB
images. Fix: make the native helpers work on `pixelPointer` for converted
images, or keep the converted pixels in a native pixmap. To discuss.

### G. 16-bit PNGs can't be loaded (limitation)

**Found:** 2026-10-19, running `TextureSetCheck` (`Item24.md`).

`PixelMap.LoadPixelMap`'s native loader fails on 16-bit PNGs with "Error
loading PixelMap: decoder init failed for stream". Texture sets often ship
16-bit normal and displacement maps (AmbientCG does).

**Options:**
- Convert assets to 8-bit beforehand.
- Library: when the native load fails, fall back to `javax.imageio.ImageIO`,
  which reads 16-bit PNGs, and turn the result into RGBA8888
  (`LoadFromByteBuffer`). This works on desktop only (no ImageIO on
  Android). Small Java change, reviewed first.


### H. A new Material's diffuse is a zero vector, so hand-built models are invisible (bug)

`Material` declares `Vector4 diffuse` without `= undefined`, so Quorum
creates it as (0, 0, 0, 0). `MaterialVulkan` checks `diffuse not= undefined`
to fall back to white, and that check never fails. A Material that never gets
`SetDiffuse` packs a diffuse of (0, 0, 0, 0): its color is multiplied by zero
and its alpha is zero, so the model can't be seen. Its position, size and
`IsShowing` all look right. Found in TextureSetCheck (2026-10-19). `LoadBox`
and other built-in shapes aren't affected, because ModelBuilder's own
materials set a diffuse.

- **Fix:** in `Material`, `Vector4 diffuse = undefined` (and the same for
  `emissive` if the same pattern applies there), so the white fallback works.
  Callers that read `GetDiffuse()` would need checking for undefined.
- **Project workaround:** always call `SetDiffuse` with (1, 1, 1, 1) on hand-built
  materials, as TerrainBrushPreview, TerrainRegionModel and TextureSetCheck
  do.
