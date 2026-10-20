# Vulkan renderer: bugs and changes

Written 2026-10-17 during the Open Worlds work, and kept up to date since.
These are all standard library changes, so each one needs the user's
go-ahead (larger ones as an `ItemN.md` with the exact code) before it is
made. The order and status are also in `LibraryChangesPlan.md`.

Paths:
- **G/** = `quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`
- **J/** = `quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`

Line numbers were right when each item was written. Much of
`VulkanPainter3D`, `VulkanGraphics` and `VulkanTextureManager` has moved
since, so treat them as approximate and search for the action names.

## Status at a glance (2026-10-19)

**Everything marked done is committed** on `quorum-language` branch
`TerrainShader`:
- `804c85c40`: Items 7, 9 and 20, and #23;
- `3e6fde7e0`: Item 24;
- `768335de9`: Items 25 and 26;
- `7ad442acb`: Items 27-30, #28 and #29;
- `8d0ca607f`: Item 31 (memory: safe disposal and the retirement queue).

- `b1d8e1a8e`: Items 32 to 35 (memory);
- `8a656d7c3`: the white-texture fix;
- `0b5de0b62` (branch `MakeAWish`): Item 37, spotlights and the point light fix.

Most are confirmed on screen. Those still waiting for a run are listed under
the table.

| # | Problem | Status |
|---|---|---|
| 1 | `StopMapping` passes the wrong handle to VMA | Done (`Item31.md`) |
| 2 | Mesh GPU memory is never freed | Applied (`Item33.md`, `Model:Dispose` and blueprint reference counts); run on 2026-10-19 |
| 3 | A mesh can't be updated after it is made | Done (`Item7.md`) |
| 4 | Copy barrier misses the vertex shader stage | Mostly covered by Item 7's barrier; the painter's own barrier is unchanged |
| 5 | Animated models leak buffers | Applied (`Item33.md`); run on 2026-10-19 |
| 6 | `Model:SetShaderProgram` is ignored | Done (`Item9.md`) |
| 7 | No mipmaps | Done (`Item25.md`) |
| 8 | Anisotropic filtering is off | Done (`Item25.md`) |
| 9 | Only RGBA8 textures | Open, only if needed |
| 10 | Textures can't be read in vertex shaders | Open, only if needed |
| 11 | Skybox not implemented | Done (`Item26.md`, OpenGL and Vulkan) |
| 12 | Unused global buffer index code | Open, tidying |
| 13 | Texture override writes the global index | Open (latent; with #19 and #22) |
| 14 | Animation compute pass isn't ordered before drawing | Open (latent) |
| 15 | Painter batches are never removed | Applied (`Item33.md`: batches of released blueprints are dropped); run on 2026-10-19 |
| 16 | No camera-relative drawing | Open, for very large worlds |
| 17 | No fog or distance fade | Open; the next visual item after memory |
| 18 | Draw queues fixed at 8192 instances | Open, before foliage |
| 19 | Texture groups sized by the uniform buffer limit (31 on the Mac) | Open (confirmed) |
| 20 | Textures can't be updated; places never reused | Same-size updates done (`Item20.md`); places reused, and kept on a reload at a new size (`Item34.md`) |
| 21 | Recording while the window is minimized | Done (models in Item 7, textures in Item 20) |
| 22 | Draw loops count frames, not texture groups | Applied (`Item32.md`); run on 2026-10-19 |
| 23 | Minimizing piles models into batches, then crashes | Done |
| 24 | Materials can't use texture sets | Done (`Item24.md`) |
| 25 | No anti-aliasing for 3D | Done (`Item27.md`, MSAA); 2D MSAA too (`Item29.md`) |
| 26 | 3D view blurry after a resize | Done (`Item28.md`) |
| 27 | Lit models black after the passes are remade | Done (`Item30.md`) |
| 28 | `VulkanPainter3DBatch` boxes integers every frame | Done |
| 29 | `vSyncEnabled` ignored under Vulkan | Done (the default, `false`, means IMMEDIATE) |
| 30 | Point lights lit from the wrong direction: `calculatePointLight` uses `normalize(tmpSub - worldPos)`, where `tmpSub` is already `lightPos - worldPos` | Done (`Item37.md`, `0b5de0b62`); waiting for a run |
| 31 | No spotlights | Vulkan, without shadows: done (`Item37.md`, `0b5de0b62`), waiting for a run. Shadows, OpenGL, scenes: `SpotlightPlan.md` phases 3 to 5 |
| 32 | No water; no time or camera position in 3D shaders; transparent models only blend albedo | Planned (`WaterPlan.md`); time and camera data in `Item38.md` (for review) |

**Committed but not yet confirmed on screen:**
- #27: re-linking the shadows after a resize;
- #28;
- #29;
- 2D MSAA (Item 29).

## Next: freeing memory everywhere

The user's next goal (2026-10-19) is to make sure GPU and CPU memory is
freed everywhere, so streaming, resizing and long play sessions don't grow
without bound. This section gathers every leak found so far. It needs its
own plan, now written: **`MemoryPlan.md`**, with exact code in `Item31.md` to `Item36.md`. As of 2026-10-19, Items 31 to 35 are committed (`8d0ca607f`, `b1d8e1a8e`) and run, and Item 36 is for review. Everything in the table below is covered by them; the plan supersedes the table where they differ.

**The rule (from #2):** never free on the spot.
1. Swap the new resource in.
2. Queue the old one.
3. Free it once every frame that might use it has finished (the frame
   slot's fence in `VulkanGraphics:BeginNextFrame`).

Freeing on the spot is only safe after `WaitUntilIdle`, as on a resize.

**Known leaks and missing frees:**

| Where | What isn't freed | Item |
|---|---|---|
| `VulkanBuffer.java` `StopMapping` | Unmapping passes the wrong handle, so mapped buffers can't be safely disposed | #1 |
| `MeshVulkan`, `ModelBlueprintVulkan`, `ModelManagerVulkan` | Mesh buffers and their staging buffers; cached blueprints are never removed (streamed-out regions, regions made again at a new size) | #2 |
| `ModelResourcesVulkan` | Animated models' per-model vertex buffers, when the blueprint changes or the model is disposed | #5 |
| `VulkanPainter3D` batches | Batches per blueprint are kept forever | #15 |
| `VulkanTextureManager` | A texture loaded again at a new size gets a new image and place; old images and places are never freed or reused (`recycledTextureIDs` is a TO-DO) | #20 |
| `VulkanTextureManager` | `stagingBuffers` (first loads, and Item 26's cube sides) are added to and, as far as read so far, never disposed | new |
| `MaterialVulkan` | Each material's staging buffer is kept; `MaterialManagerVulkan` has no cache and no free | new |
| `VulkanRenderPass:Dispose` | Not written (alerts "NYI"), so every pass made again leaks: resizes, and MSAA and 2D MSAA changes. Items 27-29 let old passes go on purpose | new |
| `VulkanPainter3D:RegenerateRenderPasses` | Shadow cubemap framebuffers and images are kept (on purpose, Item 30); the disposal loop there walks an empty array | new |
| `Skybox` under Vulkan | The cube image from `RequestCubeLoad` isn't freed by `Skybox:Dispose` (Item 26) | new |
| `VulkanGraphics` swapchain stage | The old render pass, on each 2D sample count change (Item 29) | new |

**Already freed, for reference:**
- the 3D painter's G-buffer, lighting and MSAA images, on a resize or a
  sample count change (Item 28);
- the swapchain's depth image and 2D MSAA images (Item 29);
- framebuffers, when they are made again.

**CPU garbage made every frame** is part of the same goal. #28 fixed one
case (boxing in `VulkanPainter3DBatch`). Others to look for:
- `Array<integer>` or `Array<number>` in per-frame paths;
- objects made in every `Update` or `End`. For example,
  `VulkanGraphics:DisplayCurrentImage` makes four arrays and a
  `VulkanSubmitInfo` every frame, as its own TO-DO notes.

## Open items in detail

### 1. `StopMapping` passes the wrong handle (bug)

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

### 2. Mesh GPU memory is never freed (missing feature)

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

### 4. The copy barrier misses the vertex shader stage (bug)

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

### 5. Animated models leak buffers (bug)

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

### 9. Only RGBA8 textures (limitation)

**Where:** `VulkanTextureManager.quorum:135` and `:184` always use
`FORMAT_R8G8B8A8_UNORM`. The line that would read the `PixelMap`'s format is
commented out (`:121`).

**Effect:** no 16-bit, float or integer textures. Terrain3D keeps heights in
32-bit float textures and its control map in 32-bit integers. The plan is to
keep these in GPU buffers read by address instead, so this only matters if
that plan changes.

### 10. Textures can't be read in vertex shaders (limitation)

**Where:** `VulkanTextureManager.quorum:61` makes the global texture array
fragment-only, and the upload barrier (`:169`) only targets the fragment
stage.

**Fix, if needed:** add the vertex stage to both. This only matters if Tier
3 takes the vertex-shader route instead of the compute route.

### 12. Unused global buffer index code (leftover code)

**Where:** G/Models/Vulkan/ModelManagerVulkan.quorum about lines 59-61 and
91-104.
- Meshes are handed "global" vertex and index buffer numbers, but the
  global arrays are commented out and nothing reads the numbers.
- The `recycledVertexIDs` branch is marked "TO-DO".
- Rendering uses buffer addresses directly, so there is no buffer table to
  maintain.

**Fix:** remove it, or at least make sure an update (#3) doesn't hand out
new numbers.

### 13. Texture override writes the global index (latent bug)

**Where:** J/Vulkan/VulkanDrawQueue3DInstanceMappedMemory.java:52 writes
`texture.GetVulkanTextureIndex()`, the global index. But the draw queue, and
so the bound texture set, is chosen by `GetVulkanTextureGroupIndex()`, and
materials use the local index in the group (`GetVulkanTextureLocalIndex`,
MaterialVulkan.quorum:139). The two agree only while every texture is in
group 0.

**Fix:** write the local index in the group. Matters once more textures are
loaded than one descriptor set holds. This is L4 in
`OpenWorldTier2Handoff.md`.

### 14. Animation compute pass isn't ordered before drawing (bug)

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

### 15. Painter batches are never removed (missing feature)

**Where:** G/Vulkan/VulkanPainter3DBatch.quorum (`age`, lines 20 and 64),
`VulkanPainter3D:GetBatch` (about 864-886). Batches are made per blueprint
and kept forever. Once blueprints can be freed (#2), batches that haven't
been used for a while should be removed too.

### 16. No camera-relative drawing (missing feature)

**Where:** J/Vulkan/VulkanDrawQueue3DInstanceMappedMemory.java (about line
72 onward) casts each model matrix to float. The camera's matrix goes
through `MatrixToArray` (VulkanPainter3D about 1720-1738). World positions
are worked out in float in the shader, so objects jitter far from the
origin.

**Fix (about 40 lines):** subtract the camera position from each model's
translation in 64-bit before the cast to float, and send the shader a view
matrix with no translation.

### 17. No fog or distance fade (missing feature)

**Where:** no Vulkan shader has a distance term apart from point-light
falloff (DefaultLightingFragmentShaderVulkan.quorum about 198-200).

**Fix:** distance fog in the deferred lighting shader, from the G-buffer
position and the camera position. About 20-40 lines plus settings.

### 18. Draw queues are fixed at 8192 instances (limitation)

**Where:** `DEFAULT_MAX_INSTANCES = 8192` (VulkanPainter3D.quorum:108), used
for every queue (about 1676-1682), with no growth.

**Fix:** grow a queue (or add another) when it fills.

### 19. Texture groups are sized by the uniform buffer limit (confirmed bug)

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

### 20. A texture can't be updated, and texture places are never reused (missing feature)

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


### 22. The draw loops count frames, not texture groups (bug)

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


## Done

Short records; the Items and git history hold the details.

- **3. A mesh can't be updated after it is made (missing feature)** Mesh update in place (same vertex count): `MeshVulkan:UpdateVertices`, `ModelManagerVulkan:QueueMeshUpdate`, per-frame staging, barriers. `Item7.md`.
- **6. `Model:SetShaderProgram` is ignored (missing feature)** The 3D painter draws each model with its own shader program; the terrain uses its splat program. `Item9.md`.
- **7. No mipmaps (missing feature)** Full mip chains made on the CPU (Java), with packed-normal averaging that keeps AO. `Item25.md`.
- **8. Anisotropic filtering is off (setting)** Linear mip mode, and anisotropy up to 16, on the shared sampler. `Item25.md`.
- **11. Skybox not implemented (missing feature)** Skybox on Quorum's shader system, for OpenGL and Vulkan. A full-screen sky from the camera's directions, Vulkan cube images, and front and back faces placed for the left-handed world. `Item26.md`.
- **21. Recording while the window is minimized (bug)** Models (Item 7) and textures (Item 20) wait while the window is minimized.
- **23. Minimizing piles models into batches, then crashes (bug)** `VulkanPainter3D` ignores `Render` while the frame is paused.
- **25. No anti-aliasing for 3D (missing feature)** MSAA for the 3D scene: a multisampled G-buffer resolved in the pass, coverage-aware lighting, `Game:SetMultisampling`. `Item27.md`. For 2D and the screen's final image: `Game:SetMultisampling2D`, `Item29.md`.
- **26. The 3D view is stretched and blurry after a resize (bug)** The 3D painter makes its passes and framebuffers again when the swapchain's size or a sample count changes, and frees the old images. `Item28.md`.
- **27. Lit models turn black after the 3D passes are remade (bug)** Shadow projection buffers and shadow maps are linked into the new descriptor sets when the passes are made again. `Item30.md`.
- **28. `VulkanPainter3DBatch` boxes integers every frame (performance)** `drawQueueUses` is a growing `Integer32BitArray`, and draw queues are only looked up for groups that were used. Noticed there: `Integer32BitArray.java`'s `Set` checks `index > ints.length` instead of `>=` (fix with item B).
- **29. `vSyncEnabled` was ignored under Vulkan (bug)** `vSyncEnabled` picks the present mode under Vulkan (true is FIFO, false is IMMEDIATE), with a Java fallback to FIFO. The default stays `false`, so Vulkan games run uncapped by default; `SetVSync`'s documentation now says so.

## Found while testing the memory Items

- **A white texture per material** (fixed with Item 34, 2026-10-19).
  `MaterialVulkan:Preload` made its own `SharedTextureManager`, which isn't a
  shared class, so every material without a texture made a new unit texture.
  It now uses the game's (`GameStateManager:GetSharedTextureManager()`).
- **DriveOpen's point light costs about 2.6 GB.** Point lights still need six
  faces per cascade (2048 pixels square, 3 cascades, 3 frame slots). Item 35
  only shrank directional lights. Options, not decided: a smaller shadow map
  for point lights, fewer cascades for them, or one set of maps shared by the
  frame slots.

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
