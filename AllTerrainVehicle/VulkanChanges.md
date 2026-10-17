# Vulkan renderer: bugs and changes for later

Written 2026-10-17 during the Open Worlds work. **Nothing here has been
changed.** These are all standard library changes, so each one needs the
user's go-ahead before it is made.

Paths:
- **G/** = `quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`
- **J/** = `quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`

Line numbers were right on 2026-10-17.

## Summary

| # | Problem | Kind | Size of fix | Needed for |
|---|---|---|---|---|
| 1 | `StopMapping` passes the wrong handle to VMA | Bug (Java) | A few lines | Any freeing of buffers |
| 2 | Mesh GPU memory is never freed | Missing feature | ~200–250 lines, ~6 files | Tier 3 (regions loading and unloading) |
| 3 | A mesh can't be updated after it is made | Missing feature | ~60–80 lines, 2 files | Tier 1 step 5 (editing) |
| 4 | Copy barrier misses the vertex shader stage | Bug | A few lines | Any mesh upload, more so with updates |
| 5 | Animated models leak buffers when their blueprint changes | Bug | Part of #2 | Animated models |
| 6 | `Model:SetShaderProgram` is ignored | Missing feature | Medium | Tier 2 (terrain shader) |
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

**Where:** G/Vulkan/VulkanTextureManager.quorum, `ProcessPendingTextures`
(about lines 115-200). Images are made with one mip level, and the shared
sampler uses nearest mip mode. Repeating textures, like ground, shimmer and
look noisy in the distance.

**Fix:** make images with a full mip chain, generate the levels with
`vkCmdBlitImage` after upload (or on the CPU), and set the sampler's mip
mode to linear and its maximum level of detail to match.

## 8. Anisotropic filtering is off (setting)

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

