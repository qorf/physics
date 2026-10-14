# Library staging: render tree culling in Layer3D

Written 2026-10-13. These are proposed changes to the Quorum standard library,
kept here for review. **Nothing here has been copied into the library, and
none of it has been compiled.**

The plan they follow is `../RenderTreeIntegration.md`.

## What is here

- `Libraries/` mirrors the library folder
  (`quorum-language/Quorum/Library/Standard/Libraries`). Each file here is
  the whole proposed version of that file.
- `RenderTreeLayer3D.diff` compares each file with the library as it was on
  branch `FrustrumCull` at `fdb481b8a`.

To see the changes:

```bash
less /Users/stefika/Repositories/physics/LibraryStaging/RenderTreeLayer3D.diff
```

To apply them, copy `Libraries/` over the library folder, after checking that
the library files have not changed since `fdb481b8a`.

## New files: package `Libraries.Game.Graphics.Trees`

The render tree classes from `AllTerrainVehicle/SourceCode/Rendering/`, with
only the package line changed. `RenderTree3D` is a blank base class; the
kinds that can be used are `DynamicVolumeRenderTree`, `QuadTree3D` and
`Octree`. See "The render tree classes" in `../RenderTreeIntegration.md`.

- `RenderTree3D`, `StaticDynamicRenderTree3D`
- `DynamicVolumeRenderTree`, `QuadTree3D`, `Octree`
- `RenderTreePart3D`, `RenderBoundingVolumeTree3D`, `RenderCellTree3D`
- `RenderTreeNode3D`, `RenderTreeCell3D`
- `CullingVolume3D`, `ShadowCasterCache3D`
- `QuadTree2D`, `QuadTreeCell2D`, `QuadTreeLeaf2D`: a loose quadtree of
  `Item2D`, for a later Layer2D integration. Nothing uses it yet.

`RenderTreeCheck` stays in the test project.

## Changed files

| File | Change |
|---|---|
| `Interface/Item3D.quorum` | New `renderLeaf` and `renderMoveQueued` fields. `NotifyTransformChanged` is called from every action that moves, rotates or scales an item, and from the physics write-back (`SetScreenPositionFromPhysicsPosition`); it is public for code that changes `GetTransform()` directly. `GetRenderLeaf`, `SetRenderLeaf`, `IsRenderMoveQueued`, `SetRenderMoveQueued`. `SetLayer` tells the old layer to remove the item and the new layer to add it. |
| `Game/Layer3D.quorum` | `EnableCulling`, `IsCullingEnabled`, `GetRenderTree` and `SetRenderTree` (starts as a `DynamicVolumeRenderTree`; can be swapped for a `QuadTree3D` or `Octree` at any time). `Draw` uses `DrawCulled` when culling is on. Called by `Item3D`, `Model` and `Terrain`: `AddToRenderTree`, `RemoveFromRenderTree`, `QueueRenderTreeMove`, `RenderBoundsChanged`. Private: `TellRenderTreeWhatMoved`, `RenderShadowCasters` (Vulkan), `GetLocalRenderBounds` (saved once per blueprint). |
| `Game/Graphics/Model.quorum` | `Load(blueprint, matrix)` tells the layer the model's bounds changed. |
| `Game/Graphics/Worlds/Terrain.quorum` | The same, after the terrain's blueprint is set. |
| `Game/Graphics/Painter3D.quorum` | New blueprint action `RenderShadowCaster(Model)`. |
| `Game/Graphics/OpenGL/OpenGLPainter3D.quorum` | `RenderShadowCaster` does nothing, since OpenGL has no shadows. |
| `Game/Graphics/Vulkan/VulkanPainter3D.quorum` | `RenderShadowCaster`. A shared private `GetPendingBatch`. |
| `Game/Graphics/Vulkan/VulkanPainter3DBatch.quorum` | A list of shadow-only models. Models that cast shadows and those that do not now get separate commands, which fixes the bug where the last model decided for the whole batch. Shadow-only models get shadow-only commands. The non-animated part moved into `AddStaticInstances`. |
| `Game/Graphics/Vulkan/VulkanDrawQueue3D.quorum` | `AddShadowOnlyDrawIndirectCommand`. |
| `Game/Graphics/Models/Vulkan/EnvironmentVulkan.quorum` | `projectionsDirty`, so the shadow projections are worked out once per change rather than once per swapchain image. A public `UpdateShadowProjections`, so Layer3D can get this frame's cascades before drawing. |
| `Game/Graphics/Models/OpenGL/ModelBlueprintOpenGL.quorum` | `ExtendBoundingBox` advances its counter. |
| `Game/Graphics/Models/Vulkan/ModelBlueprintVulkan.quorum` | `ExtendBoundingBox` checks the minimum and the maximum separately, without `elseif`. |

## Defaults chosen, for the open decisions in the plan

1. **Culling is off by default.** It is turned on with
   `Layer3D:EnableCulling(true)`. With it off, the only extra work is a few
   checks in `SetLayer` and when an item moves.
2. **Package:** `Libraries.Game.Graphics.Trees`, as asked. Names are not
   final. Layer3D starts with a `DynamicVolumeRenderTree`.
3. **Animated models are always drawn.** They are not put in the tree.
4. **The `transformDirty` fix is not included.** It is a separate change to
   measure on its own.
5. **Vulkan shadows: the first version only.** All lights share one list of
   casters, as today.

## Things to check when compiling and testing

- Whether Quorum allows the new `use` of
  `Libraries.Game.Graphics.Trees.RenderTreeNode3D` in `Item3D`. The `Trees`
  classes also use `Item3D`, so the two packages refer to each other. The
  library already does this between `Item3D` and `Layer3D`.
- Whether `EnvironmentVulkan.UpdateShadowProjections` works before the
  environment's buffers exist, on the first frame.
- Shadows from objects outside the camera's view, in Vulkan.
- A model added to a layer before it is loaded. It starts in the always-drawn
  list, and `Model.Load` moves it into the tree.
- Children added to and removed from items that are already on a culling
  layer.
