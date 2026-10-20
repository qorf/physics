# Freeing memory everywhere (plan)

**Status (2026-10-19):**
- **Item 31** is committed (`8d0ca607f`).
- **Items 32 to 35** are committed (`b1d8e1a8e`), and the white-texture fix
  (`8a656d7c3`).
- **Item 36** (per-frame garbage) is written and waiting for review.
- **Run on 2026-10-19:**
  - **MemoryCheck (M, N, A):** GPU memory moves between 536 and 650 MB as the
    sample counts change and settles back; "waiting" drains to 0.
  - **DriveOpen:** memory is flat at about 3.29 GB (mostly the lamp's shadow
    maps), textures are steady at 16, and blueprints level off as the map
    fills. It looked normal.
  - **Fixed along the way:** four compile errors (reserved words, a
    parameter-name clash, a missing `use`), and a white-texture-per-material
    leak from before this work.
- **Not yet seen:** cached region models being freed by distance (the 8x8
  test map is too small), and a sawtooth in the Java heap over a long idle
  run.

**Points settled while writing them:**
- `Model:Dispose` already exists, as `Item:Dispose`, which does nothing.
  Item 33 overrides it, so there's no new public action.
- A texture loaded again at a new size keeps its place. It waits for the
  device to be idle first, since frames in flight read that descriptor
  slot (Item 34).
- Pixels passed to `LoadFromPixelMap` are kept, unlike OpenGL. Item 20's
  updates and WorldTerrain reuse them.
- Item 35 fixes the cascade array overflow and the ambient fallback. The
  cascade snapping bugs stay with #14.

Written 2026-10-19, for review. **Vulkan only; OpenGL is not touched**,
except where an action shared by both renderers gains a Vulkan branch, and
those changes are named. Nothing is changed yet. Once the design is
settled, the work goes in Items (31 onward) with the exact code, one area
at a time.

Paths:
- **G/** = `quorum-language/Quorum/Library/Standard/Libraries/Game/Graphics/`
- **J/** = `quorum-language/Plugins/QuorumPlugins/src/main/java/plugins/quorum/Libraries/Game/Graphics/`

## Where this comes from

The library was read from end to end on 2026-10-19, in four parts:
- buffers and models;
- textures and materials;
- render passes, pipelines and painters;
- per-frame CPU allocations.

The key claims were checked again by hand; those are marked **(checked)**.
Line numbers are from that day.

## The short version

**Under Vulkan, almost nothing is ever freed.**
- `Texture:Dispose` does nothing under Vulkan (checked). It only acts on an
  OpenGL handle, which is always 0 there.
- No `Model:Dispose` exists.
- Blueprints, meshes, materials, batches, draw queues, samplers,
  descriptor sets and pools, render passes, pipelines and layouts are never
  destroyed.
- The only things freed today are the ones freed after a full
  `WaitUntilIdle`: framebuffers, and the images Items 28 and 29 track.

**Four things must be fixed before anything can be freed safely.** Today,
freeing would crash or corrupt memory:
1. **`VulkanBuffer.StopMapping`** passes the mapped pointer to
   `vmaUnmapMemory` instead of the allocation handle, and never clears the
   pointer (J/Vulkan/VulkanBuffer.java:147-157) **(checked)**.
   - `Dispose` unmaps first, so every dispose of a mapped buffer goes wrong.
   - This is very likely the "crash in some cases, for reasons unclear"
     that made `MeshVulkan` comment out its unmapping.
2. **`VulkanBuffer.Dispose`** isn't safe to call twice. Its handles are
   never zeroed **(checked)**.
3. **`VulkanDrawIndirectDataMappedMemory.Dispose`** calls `free()` on
   memory VMA owns (J/Vulkan/VulkanDrawIndirectDataMappedMemory.java:42-45),
   which corrupts the heap **(checked)**. It is reached from
   `VulkanDrawQueue3D:Dispose`.
4. **`VulkanPipeline:Dispose`** alerts "NYI" (G/Vulkan/VulkanPipeline.quorum:32)
   **(checked)**.
   - `VulkanShaderProgram:CreatePipeline` calls it whenever a pipeline
     already exists.
   - **So changing the MSAA count at runtime (Items 27 and 29) should
     alert the first time a pipeline is rebuilt:** M in MSAACheck, N in
     MSAA2DCheck. It's a gap in those Items, and the first thing to fix.

**The biggest single use of memory isn't a leak: shadow maps.**
- Every light gets a shadow color image (RG32F) and depth image (D32F),
  each `6 × cascades` layers, **for every frame slot**
  (`VulkanPainter3D:EnsureShadowCubemapFramebuffers`).
- At the defaults (2048, 3 cascades, 3 frame slots), that is about 0.9 GB
  per light per slot, or **about 2.7 GB per light** (checked arithmetic:
  2048² × 8 bytes × 18 layers for color, half that for depth).
- **Directional lights use only 1 of each 6 layers.** So five sixths of a
  sun's maps are never used.
- Removed lights keep their maps.

## The rule

From `VulkanChanges.md` #2. With up to *N* frames in flight (N = the
swapchain image count, usually 3), a resource used by frame F may be read
by the GPU until F's fence signals.
- `VulkanGraphics:BeginNextFrame` waits on exactly one slot's fence each
  frame. When frame F starts, only frame F − N is known to be finished.
- **So nothing is freed on the spot**, except after `WaitUntilIdle` (as on a
  resize).
- **Instead:**
  1. swap the new thing in;
  2. *retire* the old one;
  3. free it once every frame that could use it has finished.

## The design

### 1. A retirement queue in `VulkanGraphics` (the base for everything)

- **A frame counter,** `frameNumber`. It goes up by one in each
  `BeginNextFrame`.
- **`Retire(VulkanRetirable item)`** stores the item with
  `frameNumber + N`.
  - `VulkanRetirable` is a small interface with a `Release` action.
  - `VulkanBuffer`, `VulkanImage`, `VulkanImageView`, `VulkanPipeline`,
    `VulkanRenderPass`, `VulkanFramebuffer`, `VulkanDescriptorSetLayout`
    and `VulkanPipelineLayout` implement it, by calling their `Dispose`.
- **In `BeginNextFrame`,** after the fence wait, every item whose frame
  number has come is released.
- **After `WaitUntilIdle`,** everything queued is released at once.
- **Freed slots** are kept in a pool, so retiring makes no garbage.
- **Order of release:** views before images, framebuffers before passes.
  Items retired in the same frame are released in the order they were
  retired, so callers retire in that order.

### 2. Make every `Dispose` safe (Java, prerequisites)

| Class | Change |
|---|---|
| `VulkanBuffer.java` | `StopMapping` passes `memoryHandle` and clears the pointer; `Dispose` does nothing if already disposed, and zeroes handles |
| `VulkanImage.java`, `VulkanImageView.java` | Zero handles after destroy; ignore a second call |
| `VulkanDrawIndirectDataMappedMemory.java` | `Dispose` drops the wrapper; it never frees VMA's memory |
| `VulkanPushConstantBuffer.java` | Add the missing `Dispose` (`memFree`) |
| `VulkanPipeline` (Quorum, Java) | Write `Dispose`: `vkDestroyPipeline`, and the pipeline layout if it made its own |
| `VulkanPipelineLayout`, `VulkanDescriptorSetLayout` | Write `Dispose` (`vkDestroyPipelineLayout`, `vkDestroyDescriptorSetLayout`) |
| `VulkanRenderPass` | Write `Dispose` (`vkDestroyRenderPass`) |
| `VulkanSampler` | Add `Dispose` (`vkDestroySampler`) |
| `VulkanDescriptorPool` | Write `Dispose` (`vkDestroyDescriptorPool`) |

**`VulkanShaderProgram:CreatePipeline` retires the old pipeline** instead of
disposing it on the spot. That fixes the MSAA alert, and is safe whoever
calls it.

### 3. Models: meshes, blueprints, resources, batches

**Who owns what:**
- A `Model` uses a blueprint.
- A blueprint owns its meshes and materials.
- `ModelManagerVulkan` caches blueprints by key.

**Freeing:**
- **Reference counts on blueprints.**
  - `Model:Load` adds a reference to the new blueprint, and releases the
    old one if the model had another.
  - A new **`Model:Dispose`** releases it (decision 1).
  - When a blueprint's count reaches 0, `ModelManagerVulkan` removes it from
    the cache and retires it.
- **Primitive blueprints** (boxes, planes, spheres and cylinders of a given
  size) stay cached. They're small and reused often (decision 2).
- **`ModelBlueprintVulkan:Release`** releases its meshes, its materials (see
  textures below) and its animation frames.
- **`MeshVulkan:Release`** retires its device buffers (vertex, index,
  animation) and its per-slot update staging buffers.
- **Staging buffers are freed after the first copy.** `MeshVulkan` keeps its
  vertex, index and animation staging buffers forever today, mapped, only
  for an in-place update to take their size. After the first copy, they are
  retired, and the update path (Item 7) keeps just the size.
- **`ModelResourcesVulkan`:**
  - gains `Release`, which retires animated models' per-model vertex
    buffers;
  - `SetFromBlueprint` releases the old buffers, and clears the array when
    the new blueprint isn't animated (today a stale array is kept).
- **3D batches:**
  - when a blueprint is released, the painter drops its batches in every
    table;
  - the `age` bug, which stops an unused 3D batch ever aging past 1, is
    fixed with it.
- **Draw queues:** a fixed set per painter. `VulkanDrawQueue3D:Dispose`
  becomes safe through section 2, and is called only if a painter is ever
  thrown away. They aren't a growing leak.

**Project side, after this:** WorldTerrain calls `Model:Dispose` on:
- region and far models of regions that streamed out and aren't kept;
- models it makes again at a new grid size;
- old brush rings.

### 4. Textures, materials, skybox, fonts

**`Texture:Dispose` under Vulkan** gains a branch (the OpenGL branch is
unchanged) that calls a new `VulkanTextureManager:ReleaseTexture(texture)`:
- retire the image and view;
- point the texture's descriptor slot at the unit texture, so nothing reads
  a freed view;
- put its index on `recycledTextureIDs`, finishing that TO-DO, once the
  retirement frame has passed;
- remove the texture from `globalTextureArray`, `mipLevelTable` and
  `updateStagingBuffers`.

**Loading a texture again at a new size** keeps its index today only by
leaking: it takes a new index and leaves the old image in the old slot.
Instead:
- retire the old image and view;
- **keep the same index,** and re-link its descriptor slot to the new view.

So materials, which bake the index in once, keep showing the right image.
Today they show the old image (a bug the audit found).

**Staging buffers:**
- `stagingBuffers` (first loads and cube sides) is never emptied today.
  Each staging buffer is now retired right after its copy is recorded.
- Per-slot update staging buffers are retired with their texture.

**PixelMaps passed to textures** are disposed after the copy is recorded,
honouring `TextureData:DisposePixelMap()` as OpenGL already does. Today
Vulkan drops them without disposing, which leaks native memory for every
file loaded.

**Two Java fixes found here:**
- `TransferPixelData` copies with a relative `put`, which moves the source
  buffer's position. A second upload of the same `PixelMap` would copy
  nothing. It changes to an absolute copy.
- `PixelMap.LoadPixelMap`, for files that aren't RGBA8888 (such as JPG),
  converts them and returns before recording the native pointer. The
  original native buffer can then never be freed. It is freed after the
  conversion instead.

**`MaterialVulkan`** gains `Release`:
- it retires its GPU buffer, and frees its staging buffer after the first
  copy;
- it disposes the textures it made (a texture set's two packed textures, or
  the textures loaded from paths).

A small cache by path is decision 3. Separately, the material copy has no
barrier after it before drawing; one is added (found here).

**Skybox:**
- `Skybox:Dispose` under Vulkan retires the cube image and view, and
  disposes the six side `PixelMap`s.
- Those are disposed anyway once the cube is made.
- Loading a side again retires the old cube.

**Fonts:**
- `FontManager` keeps one font strategy, with its glyph atlas texture, for
  every font, size, angle and border ever used, and never lets one go.
- Animating a label's size, or the interface scale, keeps adding atlases.
- Freeing them needs a policy (decision 4).
- Separately, `FreeTypeStrategy:EmptyGlyphTable` disposes `imageSheet` even
  when it's undefined; a guard is added.

### 5. Render structure: passes, layouts, descriptor sets, shadows, semaphores

**`VulkanPainter3D:RegenerateRenderPasses`** runs on every resize and sample
count change. Today it leaks four render passes, three descriptor set
layouts, and four descriptor sets per frame slot each time. Instead:
- the old passes are retired, not let go;
- descriptor set layouts are made **once**, not on every regenerate;
- descriptor sets are **kept and linked again**, instead of being emptied and
  made anew. The linking code already runs every time;
- the shadow cubemap disposal loop, which walks an empty array, is fixed or
  removed. Shadow maps don't depend on the window's size and are kept (as
  Item 30 does).

**`VulkanGraphics`:**
- the old swapchain render pass is retired on a 2D sample change or a
  resize;
- the old image-acquired semaphores are disposed in `RegenerateSwapchain`
  (they leak one per swapchain image today).

**`VulkanPainter2D`:** the old pass is retired on a 2D sample change.

**Shadow maps** (decision 5):
- When a light is removed, its maps are retired, and the arrays are
  compacted (and linked again).
- **Directional lights get `cascades` layers, not `6 × cascades`.**
  - That saves five sixths of a sun's shadow memory: about 2.3 GB at the
    defaults with 3 frame slots.
  - It needs the lighting and shadow shaders to index directional and point
    lights' layers differently, so it is its own reviewed Item.
- **Optional:** shadow maps per frame slot are what let frames overlap. One
  set shared by all slots would divide the memory by N, at the cost of the
  next frame's shadow pass waiting for the previous frame's lighting.
  Measure first.

**Samplers:** the 3D painter makes two per painter, which is fine (they
aren't a growing leak). They are destroyed if a painter is thrown away.

### 6. Per-frame CPU garbage

These aren't leaks, since Java collects them. But they churn the garbage
collector every frame, which was the symptom the user saw with
`Array<integer>` (#28).

| Where | Made every frame | Change |
|---|---|---|
| `VulkanPainter3D:End` | About 60 to several hundred command and barrier objects: render pass begins and ends, binds, draws, barriers. Shadows without a geometry shader scale with lights × cascades × faces | Keep each command as a field and set it again; one field per kind and use, as `bindVertex` already does |
| `VulkanPainter2D:End` | About 7 command objects per draw, plus a few fixed; one `DrawIndexedCommand` (and a `Vector4` when clipped) per flush | Fields, and a pool of draw commands |
| `VulkanGraphics:DisplayCurrentImage` | A `VulkanSubmitInfo`, four `Array`s, a boxed integer (its own TO-DO) | Fields, one per frame slot |
| `EnvironmentVulkan:CalculateShadowProjections` | About 250 objects per directional light, and about 390 per point light, each time the camera moves | Scratch vectors and matrices as fields; a `Number32BitArray` for the cascade splits |
| `Layer3D` physics | About 16 objects per awake body per step: `SynchronizeTransforms` (whose result is thrown away), `ApplyGravity`, `Item3D:SynchronizeNodes`, `SetScreenPositionFromPhysicsPosition` | Fields; drop `SynchronizeTransforms`' unused work, or turn it into the drawn-position blending from the TerrainWalk findings |

This touches `Layer3D` and `Item3D`, which OpenGL games use too. These
changes keep behaviour identical, only allocating less (decision 6).

## Order of Items

1. **Item 31, prerequisites and the retirement queue** (sections 1 and 2).
   It fixes the MSAA-change alert and makes everything after it possible.
   Small; mostly Java.
2. **Item 32, render structure** (section 5, except the shadow layout
   change). This stops the leaks on every resize and sample change.
3. **Item 33, models** (section 3, with `Model:Dispose`), then the project's
   WorldTerrain change.
4. **Item 34, textures, materials and skybox** (section 4, with the two Java
   fixes).
5. **Item 35, shadow maps:** compact on light removal, and give directional
   lights fewer layers.
6. **Item 36, per-frame garbage** (section 6), one area at a time,
   measuring each.
7. **Later:** a font cache policy, and a full shutdown (`VulkanGraphics`
   destroying the device, pools and allocator on exit).

## Measuring: `MemoryCheck.quorum`

**Library helper** (Item 31): `VulkanGraphics:GetMemoryReport` returns:
- VMA's allocated bytes per heap (`vmaGetHeapBudgets`);
- counts of live textures, blueprints, retired-but-not-freed items, and
  descriptor pools.

**`MemoryCheck.quorum`** (project) loops through:
1. loading and disposing 100 textured models;
2. resizing the window and stepping MSAA counts;
3. streaming terrain regions in and out (DriveOpen's setup);
4. loading textures again at new sizes.

Every few seconds it prints GPU bytes, the Java heap (`Runtime`) and the
counts. **Pass:** after each loop settles, GPU memory and the counts return
to where they started, and the Java heap stays flat.

## Also found (not memory; fix with the nearest Item)

| Where | Problem | With |
|---|---|---|
| J/Vulkan/VulkanRenderPass.java:54-57 | Stencil load and store ops are written into `finalLayout`. Today it's harmless, since nothing sets stencil ops (Item 27's MSAA depth sets them, and its final layout is then overwritten with 1, GENERAL) (checked) | Item 31 |
| J/Vulkan/VulkanRenderPass.java:24 | Checks subpasses twice, and never checks dependencies | Item 31 |
| `VulkanPainter2DBatch` | One staging and output buffer shared by all frames in flight: the next frame's copy can overwrite what an earlier frame is still drawing | Item 32 |
| `VulkanPainter3D:End` | #22: texture groups looped up to the frame count | Item 32 |
| `EnvironmentVulkan` | The cascade transfer array is sized without the cascade count, so 6 or more lights overflow at 3 cascades; the ambient color is written to the same index three times | Item 35 |
| `EnvironmentVulkan` (#14 and the TerrainWalk findings) | Cascade snapping writes the wrong matrix entries; `lastSplitDistance` never advances | Item 35 |
| `VulkanGraphics` | Render-complete semaphores indexed by frame slot, not swapchain image; command buffers reset with RELEASE_RESOURCES every frame | Item 31 |
| `ModelManagerVulkan` | The animation compute pass isn't ordered before drawing (#14), and its output buffers are shared across frames in flight | Item 33 |

## Open decisions for the user

1. **`Model:Dispose`:** a new public action, Vulkan-only in effect (it
   releases the blueprint and resources; OpenGL keeps today's behaviour)?
   Recommended: yes. Also: should removing a model from a layer dispose it
   automatically? Recommended: no, since games re-add models; disposing
   stays explicit.
2. **Primitive blueprints:** keep them cached forever (recommended), or
   free them by reference count like file models?
3. **A material and texture cache by file path,** so two models loading the
   same image share one texture? Recommended: yes, with reference counts,
   in Item 34.
4. **Font atlases:** keep them all (today), free a size when no label uses
   it (reference counts on strategies), or keep the most recent few?
   Recommended: reference counts, later.
5. **Shadow maps:** reduce directional lights to `cascades` layers
   (recommended)? And measure whether one shared set across frame slots is
   worth the lost overlap?
6. **Per-frame garbage in `Layer3D` and `Item3D`** (shared with OpenGL): do
   it, keeping behaviour identical (recommended)? Or limit section 6 to the
   Vulkan classes?
