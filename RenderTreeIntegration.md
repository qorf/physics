# Plan: adding RenderTree3D culling to Layer3D

Written 2026-10-13. This is an investigation and a plan only. No library code
for it has been written yet. Read `Handoff.md` first for the working rules.

All library paths are relative to
`/Users/stefika/Repositories/quorum-language/Quorum/Library/Standard/Libraries`.
Line numbers were correct on branch `FrustrumCull` at `fdb481b8a`.

## Summary

- **OpenGL** needs almost nothing: give the painter only the visible models.
- **Layer3D and Item3D** need moderate work: keep the tree's membership up to
  date and tell it when items move.
- **Vulkan shadows** are the hard part. Today the shadow passes draw only the
  models passed to `Render`, so culling the camera view alone would make
  shadows from off-screen objects disappear.

## What the code does today

### Layer3D and Item3D

- **The layer holds only top-level items.** `Layer3D.items` is at
  `Game/Layer3D.quorum:98`.
  - `Layer3D.Draw` (1236-1269) calls `camera:Update()`, then `painter:Begin()`,
    then `items:Get(i):Draw(painter)` for each item, then `painter:End()`.
  - `Model.Draw` (`Game/Graphics/Model.quorum:2196-2203`) calls
    `painter:Render(me)`, then `parent:Item3D:Draw(painter)`, which draws
    the children.
  - `Item3D.Draw` (`Interface/Item3D.quorum:2278-2288`) stops if the item is
    hidden, then draws each child.
- **`Item3D.SetLayer` (2360-2386) runs for every descendant**, with the layer
  when items are added and with `undefined` when they are removed. This
  covers every way in and out:
  - `Layer3D`: `Add` (406), `Add(integer, item)` (464), `AddToFront` (522),
    `Set` (1149), `Remove` (633), `RemoveAt` (698), `RemoveFromFront` (765),
    `RemoveFromEnd` (831), `Empty` (569).
  - `Item3D`: adding children (1063, 1096) and removing them (1131, 1180).
- **Nothing tells anything when an item moves.** There is no listener or
  layer callback.
  - Moving changes `transform` directly, without `transformDirty`:
    - `MoveX/Y/Z` (499, 524, 549)
    - `Move(x, y, z)` (578), `Move(Vector3)` (610)
    - `SetOffsetX/Y/Z` (638, 672, 706), `SetOffset` (743, 781)
    - `SetX/Y/Z` and `SetPosition` go through these.
  - These set `transformDirty = true` (the only six places):
    - `SetRotationTransform` (1043)
    - `Rotate` (1607), which all other rotations go through
    - `SetYawPitchRoll` (2037)
    - `Scale` (2132)
    - `SetScale` (2253)
    - `SetScreenPositionFromPhysicsPosition` (3412), the physics write-back
  - `Model.Load(ModelBlueprint, Matrix4)` (2162) overwrites the transform with
    `GetTransform():Set(matrix)` and marks nothing.
  - The existing `hasMoved` flag (94, set in `MoveX/Y/Z` and `Move(x, y, z)`)
    belongs to physics. It misses rotation, scale, offsets and the physics
    write-back.
- **Every item's transform is already in world space.** There is no
  parent-times-child matrix. A parent's move goes down to its children through
  `SetOffset`, and its rotation through `RotateChildren` (1757) and
  `RotateItemArray` (1976-2030). So each descendant can be culled on its own,
  with no boxes covering whole hierarchies.
- **Only `Item3D` and `Model` define `Draw`.** `Terrain`, `Grid3D` and the
  editor classes (`EditorModel` and those built on it) all draw through
  `Model.Draw`. `PointLight` and `Audio3D` are `Item3D`s that draw nothing.
- **Frame order** (`Game.ContinueGame`, `Game/Game.quorum:823-843`):
  1. input
  2. `UpdateAll` (layers' `Update`, which advances animations)
  3. the game's `Update`
  4. `TestForCollisions` (physics step and write-back)
  5. accessibility
  6. `DrawAll`
  
  So everything has moved before `Draw`.

### OpenGL

- **Painter:** `Game/Graphics/OpenGL/OpenGLPainter3D.quorum`.
  - `Render` (74-88) adds the model's renderables to a list.
  - `Flush` (196-251) sorts them (`Renderable.Compare`: opaque first, front to
    back; blended last, back to front) and draws them. The skybox is drawn
    before the first blended one, or in `End`.
- **Nothing is kept per model between frames.** The list is emptied each
  frame.
- **There are no shadows** in OpenGL 3D.
- **Light choice does not depend on drawn models.** At most 2 directional and
  5 point lights, taken in the order they were added
  (`DefaultShaderMapping3DOpenGL.quorum:52-53, 539-635`).
- **Culling also cuts garbage:**
  - `ModelResourcesOpenGL.GetRenderable` (471) creates a new `Renderable`
    for every mesh part of every model, every frame.
  - The sort creates two `Vector3`s per comparison (`GetTranslation`).
- **Giving OpenGL only visible models is safe.**

### Vulkan

- **Painter:** `Game/Graphics/Vulkan/VulkanPainter3D.quorum`.
  - `Render` (1698-1718) only records the model in its batch (per blueprint,
    opaque or transparent).
  - `End` (1032-1486) does everything else:
    - computes animations (1081)
    - runs `camera:Update()` and `environment:Update()` (1088-1089)
    - writes all instance data once, in `ProcessBatch` (1123-1140)
    - runs the scene pass (1143-1218), the shadow passes (1225-1362) and the
      lighting pass
- **Skipping a model is safe.**
  - Batches hold no GPU resources and are never removed.
  - Draw queues (one per texture group, `VulkanDrawQueue3D`) are fixed size
    and reused.
  - Age is never read in 3D.
- **Shadows replay the main pass.**
  - Every light, cascade and cube face draws the same instance buffer with the
    same shadow command list (1322, 1342-1343).
  - That list is built in `VulkanDrawQueue3D.AddDrawIndirectCommand` (118-128).
    It always writes a main-pass command, and a shadow command only as a copy
    of it. **There is no shadow-only path.**
  - If only camera-visible models reach `Render`, off-screen casters disappear
    from every shadow map.
- **Cascades are chosen on the graphics card**, depending on what the device
  supports (`GetDefaultShadowProgram`, 798-825):
  - Geometry shader path: one draw per light feeds every cascade.
  - Two-stage path: one draw per light, cascade and face.
- **Cascade matrices are worked out inside `End`** (`environment:Update`,
  `EnvironmentVulkan.CalculateShadowProjections`, 567-828). That is after
  `Layer3D` would collect shadow casters.
- **Animated models:**
  - `Render` adds them to `animatedModels`, and their skinning is computed in
    `End`.
  - Skipping one is safe: it is recomputed the next time it is drawn.
  - A model drawn only into shadows still needs this, or its shadow uses an
    old pose.
- **Transparency** is drawn after opaque batches, in the order first rendered,
  with no depth sorting. Culling does not change this.

## The plan

### Step 0: fixes to make first

These are library bugs found during the investigation.

1. **`transformDirty` is never set back to false** (`Item3D.quorum:86`,
   `RecalculateTransform` 995). Once an item has been rotated, every
   `GetTransform()` rebuilds the matrix. This is the `RecalculateTransform`
   cost in both AllTerrainVehicle profiles. Fixing it is a separate win,
   worth measuring on its own.
2. **Local bounds bugs:**
   - `ModelBlueprintOpenGL.ExtendBoundingBox`
     (`Game/Graphics/Models/OpenGL/ModelBlueprintOpenGL.quorum:510-518`)
     never advances its counter.
   - `ModelBlueprintVulkan.ExtendBoundingBox` uses `elseif` between its
     minimum and maximum checks.
   - Culling depends on correct local bounds.
3. **Layer3D bookkeeping bugs** (optional, but in the same code):
   - `Set` (1156, 1161) calls `SetLayer(undefined)` and removes accessibility
     on the new item instead of the old one.
   - `Add(integer, item)` and `AddToFront` skip `EnableItemLighting`.
   - `RemoveAt`, `RemoveFromFront` and `RemoveFromEnd` skip
     `DisableItemLighting`.
   - `Item3D.Remove` (1138, 1187) uses the layer without checking it is
     defined, so removing a child from an item not on a layer crashes.
4. **`VulkanPainter3DBatch` shadow flag:** `castsShadows` is overwritten
   inside the model loop (151). The whole batch then casts shadows or not
   based on its last model (171). Fix this in step 5.

### Step 1: move the classes into the library

- Move `RenderTree3D`, `RenderBoundingVolumeTree3D`, `RenderTreeNode3D`,
  `CullingVolume3D` and `ShadowCasterCache3D` from
  `AllTerrainVehicle/SourceCode/Rendering/` into a library package. The user
  picks the package and final names.
- `RenderTreeCheck` stays in the test project.

### Step 2: hooks in Item3D

The tree must not know anything about physics. Physics only moves items
through the actions below, so hooking those is enough.

- **Membership.** In `SetLayer`:
  - If the old layer is defined and the item is a `Model`, call
    `oldLayer:RemoveFromRenderTree(me)`.
  - If the new layer is defined, call `newLayer:AddToRenderTree(me)`.
  
  Because `SetLayer` runs for every descendant, this one place covers every
  way in and out.
- **The leaf handle.** A private `RenderTreeNode3D renderLeaf` field on
  `Item3D`, set by the layer when it adds the item. That makes the hash table
  lookup unnecessary from the start (see `RenderTree3D.GetLeaf` and
  `Moved(leaf)`).
- **Moves.** A private `NotifyMoved()`, called from each action that changes
  the transform:
  - `MoveX/Y/Z`, `Move` (both), `SetOffset*`
  - `Rotate`, `SetYawPitchRoll`, `SetRotationTransform`
  - `Scale`, `SetScale`
  - `SetScreenPositionFromPhysicsPosition`
  - `Model.Load`'s `GetTransform():Set(matrix)`
  
  ```
  if layer not= undefined and renderLeaf not= undefined and not queuedMove
      queuedMove = true
      layer:QueueMoved(me)
  end
  ```
  The flag means an item is queued at most once per frame.
- **Limit:** code that changes `GetTransform()` directly cannot be detected.
  `Layer3D` gets a public `ItemMoved(item)` for that, and its documentation
  says so.

### Step 3: a new Draw path in Layer3D, opt-in at first

- **New fields:**
  - `RenderTree3D renderTree`
  - `Array<Item3D> alwaysDrawn`, for models the tree does not take
  - `Array<Item3D> movedItems`
  - reused result arrays, emptied with `Empty(false)`
- **Every model is added as static.** The first `Moved` moves it to the
  dynamic half, and `EndFrame` moves it back once it is still. This needs no
  physics knowledge. It costs one reinsert per item that starts moving.
- **Local bounds come from Layer3D, not the tree.** The tree uses `Item3D`
  only.
  - For a `Model`: the blueprint's real minimum and maximum, through
    `Model:CalculateBoundingBox`, saved once per blueprint. This fixes the
    off-center problem of a centered width, height and depth box. It depends
    on the step 0 bounds fixes.
  - For `Terrain`: from its corner, (0, 0, 0) to (pixel width - 1, highest
    point, pixel height - 1), as in AllTerrainVehicle.
  - **Animated models:** skinning can move vertices outside the resting pose's
    bounds. The simplest safe choice is to put them in `alwaysDrawn`.
- **Draw with culling on:**
  ```
  camera:Update()
  for each item in movedItems: renderTree:Moved(its leaf), clear its flag
  visible:Empty(false)
  renderTree:CollectVisible(camera, visible)
  painter:Begin()
  for each visible Model: if IsShowingWithParents, painter:Render(model)
  for each alwaysDrawn Model: if IsShowingWithParents, painter:Render(model)
  (Vulkan) shadow casters, step 5
  painter:End()
  renderTree:EndFrame()
  ```
  - It calls `painter:Render` directly, not `item:Draw`. Each model is drawn
    once, and children are not drawn twice.
  - `IsShowingWithParents` keeps the rule that a hidden parent hides its
    children.
- **With culling off,** the current loop runs unchanged.

### Step 4: OpenGL

Nothing beyond step 3. Sorting and the skybox work as they do now.

### Step 5: Vulkan shadows, first version

- **Painter interface:** `Painter3D` (`Game/Graphics/Painter3D.quorum`) gets
  `RenderShadowCaster(Model)`. The OpenGL version does nothing.
- **Layer3D collects the casters:**
  - the union of `CollectDirectionalShadowCasters` for each cascade of each
    directional light, and `CollectPointShadowCasters` for each point light
  - only models with `CastsShadows()`
  - skipping models already drawn this frame, using a frame number stored on
    the leaf rather than a hash table
- **Order:** `Layer3D` calls `environment:Update()` right after
  `camera:Update()`, so the cascade matrices are this frame's.
  - Otherwise casters would lag a frame and pop in and out at cascade edges.
  - `EnvironmentVulkan.Update` (147-159) uses dirty flags, so the second call
    in `End` should be cheap. **Check this.**
- **Inside VulkanPainter3D:**
  - Shadow-only models go in a separate list in each batch.
  - `ProcessBatch` writes their instances as their own block. A new
    `VulkanDrawQueue3D.AddShadowOnlyDrawIndirectCommand` writes only to the
    shadow command buffer, but still moves `currentDrawInstanceIndex` forward.
    The instance and command positions must stay in step.
  - Shadow-only animated models also go into `animatedModels`.
  - Fix the `castsShadows` bug (step 0, item 4).
- **What this gains:** every light still draws one shared caster list, as
  today. It removes objects that are both off screen and outside every
  light's shadow area.

### Step 6: testing

- Port `RenderTreeCheck`'s hand test into a world test, in the PhysicsTests
  style.
- Add a test that the culled path draws the same models as the unculled path
  plus the exact test.
- Check by eye in both APIs, including shadows from off-screen casters.
- Run the benchmarks in BoxDestroy and AllTerrainVehicle with culling on and
  off.

### Step 7: later, separate shadow lists per light

- Separate shadow command buffers per light, and per cascade on the two-stage
  path.
- Each light's casters are not contiguous in the instance buffer. They need
  either single-instance commands with their own `firstInstance`, or a
  reordering of instances.
- On the geometry shader path, one draw feeds every cascade. Separate cascades
  there would mean drawing each cascade separately.
- Point lights gain the most: 6 faces times the cascades.

## Risks

- **Custom `Draw` overrides are skipped.** A user class that overrides `Draw`
  (none in the library) would not be called when culling is on. Opt-in limits
  this.
- **Changing `GetTransform()` directly** is not detected.
- **Drawing order changes.** OpenGL sorts anyway. Vulkan already orders by
  texture group and batch, with no depth sorting.
- **`camera:Update()` runs twice a frame** in Vulkan (`Layer3D.Draw` and the
  painter's `End`). That already happens today. Leave it.
- **Existing Vulkan pause hazard:** `Begin` and `End` return early while
  rendering is paused, but `Render` does not. Model lists grow until rendering
  resumes. Culling does not make this worse.
- **The library's `Frustum`** (`Compute/Frustum.quorum`) assumes OpenGL's -1
  to 1 depth. Do not use it for Vulkan. `CullingVolume3D` reads its planes
  straight from the camera's combined matrix and has no near plane, so it
  works with both.

## Decisions for the user

1. Should culling be opt-in at first (`Layer3D:EnableCulling(boolean)`, off by
   default), or on by default?
2. Which package, and what final names?
3. Animated models: always drawn for now, or bounds made larger by some
   amount?
4. Should the `transformDirty` fix go first, as its own measured change?
5. For Vulkan, is the first shadow version (step 5) enough for now, with
   separate lists per light (step 7) later?
