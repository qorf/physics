# Standard library changes: plan and order

Written 2026-10-17. Updated 2026-10-19.

**State on 2026-10-19,** on `TerrainShader`. Everything applied so far is
committed:
- `804c85c40`: orders 7, 9, 12 and 15;
- `3e6fde7e0`: item 24;
- `768335de9`: items 25 and 26, which include orders 8 and 10;
- `7ad442acb`: items 27-30, #28 and #29.

**Now: spotlights and water** (the user's choice, 2026-10-19; `SpotlightPlan.md`
and `WaterPlan.md`). The library branch is now **`MakeAWish`**: never switch
branches.
- **Spotlights for Vulkan** (`Item37.md`) are committed as `0b5de0b62`.
- **Water phase 1** (`Item38.md`) is for review.

Before that came **freeing memory everywhere**, now done. That is orders 3
and 11, plus the leaks found since. They are listed in `VulkanChanges.md`,
"Next: freeing memory everywhere". The plan is `MemoryPlan.md`.
The Items with exact code are `Item31.md` to `Item36.md` (2026-10-19).
Items 31 to 35 are committed (`8d0ca607f`, `b1d8e1a8e`) and run.
Item 36 awaits review.
Item 32 includes order 13 (#22). After that, the small open bugs B and H. See "Status" at the end.

Items are taken one at a time, when the user picks them; most still need
discussion first. Larger items get a written proposal (`Item7.md`,
`Item9.md`) with the exact before and after, reviewed before anything is
changed.

The user made the branch **`TerrainShader`** in `quorum-language` for this
work. Its working tree was clean apart from an untracked
`Quorum/resources/`.

The details of each item (where it is, why, how to fix) are in
`VulkanChanges.md`; the numbers and letters below match it. This file is
the order to do them in.

## How each change is made

These changes are reviewed more carefully than the project code, so each
one follows the same steps:

1. **Show the exact before and after** for the user to review. Nothing is
   written to the library before the user approves that specific change.
2. **Make only that change** on `TerrainShader`, one change per commit
   (when the user asks for commits).
3. **The user builds and tests:**
   - Quorum-only changes need the standard library rebuilt.
   - Java changes (in `Plugins/QuorumPlugins`) need the plugins rebuilt too.

   Claude doesn't run builds of the library or `Default.jar`.
4. **Check** with `RunWorldTests`, `RunPhysicsTests`, and `DriveOpen`, plus
   anything specific to the change, listed below.
5. **Workarounds:** where the project has a workaround for the bug, it can
   stay (it's harmless) or be removed later. Removing them is a separate
   step.
6. **Update this file** and `VulkanChanges.md`.

## The order

Smallest and most necessary first. "Necessary" means it's a real bug we've
hit, or it blocks work the user wants.

### Batch 1: small bug fixes

Each is a few lines and changes nothing for code that already works.

| Order | Item | What | Size | Why now |
|---|---|---|---|---|
| 1 | **B** | `Integer32BitArray` and `Number32BitArray`: `GetSize` returns 0 before `SetSize`, instead of failing on a null array | Java, 2 files, about 2 lines each | Hit in `TerrainCollision`. Nothing can rely on the crash. |
| 2 | **A** | `FileReader:ReadLines` stops failing at the end of every file | Java, 1 file, about 10 lines | Hit in `TerrainData:Load`. As written it can never succeed, so nothing relies on it. |
| 3 | **#1** (**next, with memory**) | `VulkanBuffer.StopMapping` passes the allocation handle to VMA, clears the pointer; `Dispose` guards against being called twice | Java, 1 file, about 6 lines | Needed before any GPU memory can be freed (#3's full form, S1). |
| 4 | **#4** | The barrier after mesh copies waits for the vertex shader stage, and is recorded whenever a copy was recorded | Quorum, `VulkanPainter3D`, about 5 lines | Correctness for every mesh upload. **Mostly covered by order 7:** `ModelManagerVulkan` now records its own barrier after mesh copies. The painter's barrier is left as it is; fixing it is now optional tidying. |
| 5 | **#14** | Make drawing wait for the animation compute shader's writes | Quorum, `VulkanPainter3D`, small | Latent race for animated models. Same kind of change as #4, so review them together. |
| 6 | **#13** | The texture override writes the texture's index in its group, not its global index | Java, 1 line | Latent. Only matters once there are more textures than one group holds, but it's one line. |

### Batch 2: small changes that remove a real limit

| Order | Item | What | Size | Why |
|---|---|---|---|---|
| 7 | **#3** (applied 2026-10-18, see `Item7.md`) | Update a mesh's vertices in place (same vertex count): `MeshVulkan:UpdateVertices` and `ModelManagerVulkan:QueueMeshUpdate`, using the staging buffer that stays mapped | Quorum, 2 files, about 60-80 lines | Ends the leak every time the ground is edited. Then `TerrainRegionModel` and `TerrainRegionFarModel` change to update instead of making a new blueprint (project code). Needs #4. |
| 8 | **#8** (applied in Item25.md, 2026-10-19) | Anisotropic filtering, and linear mip mode, on the default sampler | Quorum, about 5-10 lines | Sharper ground at low angles right away. Linear mip mode only matters after #10 (mipmaps). The sampler is built into every pipeline, so it must be set before any is made. |

### Batch 3: medium changes that open Tier 2 (texturing)

| Order | Item | What | Size | Why |
|---|---|---|---|---|
| 9 | **#6** (Tier 2 L1, Tier 3 S3; applied 2026-10-18, see `Item9.md`) | `VulkanPainter3D` draws each model with its own shader program when it has one, otherwise the default. Draw queues split per program; custom programs use the default layout; shadows unchanged. | Quorum, 2 files. Planned at 40-60 lines; came to about 230, most of it doc comments and the copied draw loop | Blocks all of Tier 2, and the GPU clipmap's vertex route. The branch's name suggests this is the goal. |
| 10 | **#7** (applied in Item25.md, 2026-10-19, levels made in Java instead of a blit) | Mipmaps: a new `BlitImageCommand` (Quorum and Java), full mip chains on upload | about 110 lines plus about 60 Java | Ground textures shimmer without them. Biggest visual gain for Tier 2. |

### Batch 4: the large one

| Order | Item | What | Size | Why |
|---|---|---|---|---|
| 11 | **#2 + #5 + #15** (Tier 3 S1; **next**: memory, with the new leaks in `VulkanChanges.md`) | Freeing GPU memory: deferred-deletion queue in `VulkanGraphics`; dispose for meshes, blueprints, model resources; remove from the blueprint cache; prune unused painter batches | about 200-250 lines, about 6 files, plus Java | Lets streamed regions give memory back. Today memory grows with every distinct region drawn. Needs #1. |

### Batch 4b: found along the way (2026-10-18)

Found while doing orders 7 and 9, or from a crash. Numbered after order 11
so the earlier numbers (and `Item7.md`, `Item9.md`) keep their meaning, but
**orders 12 and 13 come before the remaining earlier items** in priority.

| Order | Item | What | Size | Why |
|---|---|---|---|---|
| 12 | **#23** (applied 2026-10-18) | While the window is minimized, `VulkanPainter3D:Render` ignores models (`framePaused`, set in `Begin`) | Quorum, `VulkanPainter3D`, about 6 lines | **Crash:** minimizing for about a second, then restoring, overflowed a draw queue (`BufferOverflowException`). |
| 13 | **#22** | The default geometry and shadow loops go over the texture groups, not the frames in flight | Quorum, `VulkanPainter3D`, a few lines | Models with textures in group 3 or later are never drawn. With 31 textures per group (#19), that's any game with more than about 90 textures. Changes what gets drawn, so tested on its own. |
| 15 | **#20** (+ order 14), see `Item20.md` (applied 2026-10-19) | A texture loaded again at the same size is copied into its existing image, keeping its index; plus the paused-frame guard for textures | Quorum, `VulkanTextureManager`, about 110 lines with comments | **Blocks painting in TerrainEditor:** every new splat texture lands in group 2 and the ground turns grey. |
| 14 | **#21** (textures; folded into order 15) | `VulkanTextureManager:ProcessPendingTextures` does nothing while the window is minimized, like the model manager since order 7 | Quorum, about 4 lines | Textures loaded while minimized are recorded into a command buffer that isn't recording. Invalid Vulkan use; it hasn't crashed yet on the Mac. |

### Batch 5: when needed

- **#17** distance fog (about 20-40 lines): hides the far edge of the
  world.
- **#16** camera-relative drawing (about 40 lines, Java): only for worlds
  much larger than about 8 km.
- **#11** skybox for Vulkan (medium).
- **#18** draw queues that grow past 8192 instances: before foliage (Tier
  5).
- **Tier 3 S2 or S4**, the hooks for the GPU clipmap: after #6, once the
  route is chosen.
- **#12** removing unused buffer-index code: tidying, any time.
- **#9, #10** (more texture formats, vertex-stage textures): only if a
  design needs them.

### To discuss before doing

- **C, `Layer3D:Remove` turns collision off.**
  - This has been the behavior since the library's bootstrapping commit,
    and `Layer2D` does the same (lines 470, 544, 627). So it may be
    deliberate, and changing it affects every 2D and 3D game that removes
    and re-adds items.
  - The project already works around it.
  - Options: leave it and document it; restore the setting in `Add`; or
    stop changing the setting in `Remove`.
- **`JavaScriptObjectNotation` number getters.** `GetNumber(key)` refuses
  values written without a decimal point (and `GetInteger(key)` the
  reverse). Making `GetNumber` accept whole numbers would be friendlier,
  but it's a behavior change for an existing class. The project works
  around it.
- **`PerspectiveCamera` far plane 100 vs `Camera` 1000.** Not a bug, but it
  surprised us. A documentation note could help.

### Last: moving the project's classes into the library

`TerrainData`, `TerrainRegion`, `TerrainPatch`, `TerrainRegionModel`,
`TerrainRegionFarModel`, `TerrainCollision`, `TerrainCollisionPiece`,
`TerrainStreamer`, `WorldTerrain`, and their tests. They're already in
`Libraries.Game.Graphics.Worlds`. This is best done after the library fixes
they work around, so the workarounds can come out as they move. The user
decides when.

## Status

Every library change applied so far is committed on `TerrainShader`
(`804c85c40`, `3e6fde7e0`, `768335de9`, `7ad442acb`).

| Order or item | Change | Status |
|---|---|---|
| 7 | #3 mesh update in place | Done, confirmed |
| 9 | #6 per-model shader programs | Done, confirmed |
| 12 | #23 minimize crash | Done |
| 14, 15 | #21 textures while minimized; #20 texture update in place | Done, confirmed |
| 8, 10 | #8 anisotropy, #7 mipmaps (`Item25.md`) | Done, confirmed |
| Item 24 | Materials from texture sets | Done, confirmed |
| Item 26 | Skybox, OpenGL and Vulkan (#11) | Done, confirmed (SkyboxCheck, DriveOpen) |
| Items 27, 29 | MSAA for 3D and for 2D | Done; 3D confirmed, 2D waiting for a run |
| Item 28 | 3D view after a resize (#26) | Done |
| Item 30 | Shadows after the passes are made again (#27) | Done, waiting for a run |
| #28 | No boxing in `VulkanPainter3DBatch` | Done, waiting for a run |
| #29 | `vSyncEnabled` under Vulkan | Done, waiting for a run |
| 3, 11 | #1, #2, #5, #15, and the new leaks | **Next: memory** |
| 13 | #22 draw loops count frames | Not started |
| H | A new `Material`'s diffuse is (0,0,0,0) | Not started; the project works around it |
| 1, 2, 4-6 | B, A, #4, #14, #13 | Not started |
| C, JSON getters, far plane | To discuss | Not started |

**Project side** (done with the library changes):
- region and far models update their meshes in place;
- the terrain draws with its own splat program;
- texture set layers come through a layer table, with height blending;
- the splat shader reads with `textureGrad`.

**Still to do:** remove the splat shader's non-terrain branch and the
metallic -1 marker (`Item9.md` follow-up), then `InstallAsDefault`.
