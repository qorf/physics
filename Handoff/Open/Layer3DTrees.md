# Plan: trees and culling inside Layer3D

Written 2026-10-14. **All three batches are done, compiled and ran** (2026-10-14, snapshots `Default-2026-10-14-shutdown-4` and `-5`). Testing is still open; see `../TestFrustrum.md`.

Library paths are relative to
`quorum-language/Quorum/Library/Standard/Libraries`.

## Goal

Make `Layer3D` work the way `TreeLayer3D` does in AllTerrainVehicle, and
then retire TreeLayer3D and CullingLayer3D:

- **No array.** The layer's items live in trees:
  - a rendering tree holding every item added to the layer;
  - an awake tree and a sleeping tree for the items with physics.
- **Walks follow the trees.** Every loop that went through the array walks
  one of the trees, leaf to leaf, by parent and child links.
  - Physics walks only the awake tree.
  - Update, input and drawing use the rendering tree.
- **Drawing culls:**
  - what the camera sees (`CollectVisible`);
  - each directional light's shadow casters, within its shadow distance
    (`CollectDirectionalShadowCasters(light, camera, results)`);
  - each point light's casters (`CollectPointShadowCasters`).
- **Items report their own changes.** The hooks already in the library
  (`ItemMoved`, `ItemResized`, `ItemPhysicsChanged`, `ItemSimulationChanged`)
  are filled in. So there is no once-per-frame checking, and no special
  handling for items that do not report, since every `Item3D` now reports.

Out of scope here: painter changes (a shadow-only path, a caster list per
cascade), shader and Vulkan work, and `Layer2D`.

## What already exists

| Piece | Where | State |
|---|---|---|
| Render trees, `CullingVolume3D`, iterator, leaf walking | `Game/Graphics/Trees` | In the library |
| Item reports: `NotifyMoved`, `HasReportedMove`, `SetReportedMove`, `SimulationChanged`, and the size and physics reports | `Item3D`, `PhysicsProperties3D` | In the library |
| `ItemMoved`, `ItemResized`, `ItemPhysicsChanged`, `ItemSimulationChanged`, which do nothing | `Layer3D` | In the library |
| Shadow distance on the light, and the column search | `DirectionalLight`, `CullingVolume3D`, `StaticDynamicRenderTree3D` | In the library |
| Physics with awake and sleeping trees, the `grouped` list, the bug fixes (a) and (b), `changedBodies` | `TreeLayer3D` | Test project |
| Culled drawing, `alwaysDrawn`, `unmeasured` | `TreeLayer3D` | Test project |

## Decisions

1. **Culling is always on.** There is no flag. `Draw` always culls.
2. **The actions that use an index are removed from Layer3D:**
   - `Add(integer, Item3D)` and `AddToFront`
   - `Get(integer)`, `GetFromFront` and `GetFromEnd`
   - `Set(integer, Item3D)`
   - `RemoveAt`, `RemoveFromFront` and `RemoveFromEnd`

   The trees have no positions, so these would have had to walk the tree,
   and their meaning ("the item at place 3") would change as items move.
   `Add(Item3D)`, `Remove(Item3D)`, `GetIterator`, `GetSize`, `IsEmpty`
   and `Empty` stay. A new `Has(Item3D)` is added, since finding whether an
   item is on the layer was one use of the index actions, and the
   rendering tree can answer it with one lookup.

   Who uses them today:
   - **EditorLayer3D** overrides `Add(index, item)` and `AddToFront`, only
     to pass them on and set the item's input group. Both overrides are
     removed. `Add(Item3D)` stays and does the same work.
   - **Layer3D's own documentation examples** for each removed action.
     They go with the actions.
   - Nothing else in the library, Quorum Studio, or the example games
     calls them. The base `Layer` class declares none of them.
   - **Games written by users** may call them, so this is a breaking
     change. They would need to keep their own list if they want an order.
3. **Bounds that are not centered on the item: the item supplies them**
   (option b below). `Item3D` gets `GetRenderBounds`, and `Terrain`
   overrides it. The code is in batch 1.
4. **Children are culled with their parent.** Accepted. A child far outside
   its parent's box is culled with it. This is documented on Layer3D.

### Bounds that are not centered on the item

To cull an item, the tree needs the box around it in the item's own
coordinates. For an item it knows nothing else about, it uses a box of the
item's width, height and depth, centered on the item's position. That is
right for an item whose shape is centered on its position, such as a
`LoadBox` model.

It is wrong for a shape that starts at its position instead of being
centered on it:

- **A terrain's mesh** runs from its position, at one corner, out to its
  width and depth. A centered box covers only a quarter of the terrain, so
  the terrain is culled whenever that quarter is out of view, even though
  the rest of it is on screen. AllTerrainVehicle works around this today by
  calling `SetRenderBounds(terrain, box)` with the corner-based box.
- **A loaded model whose origin is not its center,** such as a character
  with its origin at its feet, has the same problem to a lesser degree. The
  box is in the wrong place by half the model's height.

Two ways to supply the right box were considered:

- **(a) The game tells the layer**, with `Layer3D:SetRenderBounds(item, box)`,
  as AllTerrainVehicle does. Every game with a terrain has to know to do
  this, or the terrain disappears at the edges of the view.
- **(b) The item knows its own box (chosen).** A new action on `Item3D`,
  `GetRenderBounds(BoundingBox local) returns boolean`, fills in the box,
  or returns false if the item has none.
  - **`Item3D`'s version** gives the centered box used today.
  - **`Terrain`** overrides it with the corner-based box.
  - **`Model`** could later override it with its blueprint's measured
    corners, which fixes off-center models too. That needs the blueprint
    bounds bugs fixed first (`ExtendBoundingBox` in both blueprints).

  The layer asks every item the same way, and no game needs to know.

With (b), `SetRenderBounds` and the layer's hash table of given bounds are
not needed. The game only adds the terrain, as any other item.

---

## Batch 1: Layer3D without the array

**Status: done, compiled and ran**, on branch `FrustrumCull2`, as described below. Two differences from the plan as first written:

- There is no list of items without bounds yet. An item with no box goes
  in the rendering tree with a box of no size, and `ItemResized` places it
  again when it gets a size, so no list is needed.
- `movedItems` is used in batch 1 already, for collision boxes after
  physics, and is cleared at the end of `TestForCollisions` (also when the
  layer is not colliding, so it never grows).

The trees replace the array. Drawing still draws everything. This batch is
about getting every walk right, and can be tested on its own.

### Fields

**Remove** `Array<Item3D> items`.

**Add:**

```
    // Every item added to the layer. Its children are reached through it.
    RenderTree3D renderTree = undefined
    DynamicVolumeRenderTree3D defaultRenderTree

    // The items with physics, split by whether physics is moving them.
    RenderTree3D awakeBodies = undefined
    RenderTree3D sleepingBodies = undefined
    DynamicVolumeRenderTree3D defaultAwakeBodies
    DynamicVolumeRenderTree3D defaultSleepingBodies

    // Bodies put in a group in the last physics step, so their group flags
    // can be cleared without visiting every body.
    Array<Item3D> grouped

    // Bodies that woke or fell asleep, moved to the matching physics tree
    // once no walk is under way.
    Array<Item3D> changedBodies

    // A box of no size at an item's own position, for items with no bounds.
    BoundingBox emptyBounds
```

`on create` sets the three trees to their defaults.

### Actions that change

They are listed with their current line numbers. The new bodies are
TreeLayer3D's, with `parent:Layer3D:field` written as just `field`, now that
the code is inside Layer3D.

| Action | Line | Change |
|---|---|---|
| `Add(Item3D)` | 406 | Add to the rendering tree; if physics is on, to the awake or sleeping tree |
| `Add(integer, Item3D)` | 464 | **Removed** |
| `AddToFront` | 522 | **Removed** |
| `Empty` | 569 | Walks the rendering tree, then empties all three trees and the lists |
| `Remove(Item3D)` | 633 | Removes from all three trees |
| `RemoveAt`, `RemoveFromFront`, `RemoveFromEnd` | 698, 765, 831 | **Removed** |
| `Get`, `GetFromFront`, `GetFromEnd` | 898, 939, 980 | **Removed** |
| `GetIterator` | 1021 | `renderTree:GetIterator()` |
| `GetSize`, `IsEmpty` | 1062, 1107 | `renderTree:GetSize()` |
| `Set(integer, Item3D)` | 1149 | **Removed** (this also removes its bug, where the new item was cleared instead of the old one) |
| `Has(Item3D)` | new | `renderTree:Has(item)` |
| `Update` | 1222 | Walks the rendering tree, holding the next leaf in case an item removes itself |
| `Draw` | 1236 | Walks the rendering tree (batch 2 replaces this with culling) |
| `ProcessMouseEvent`, `GetItemWithInput`, `ProcessTouchEvent`, `ProcessGestureEvent` | 1351, 1463, 1523, 1627 | The first loop, which gathers items and their children, walks the rendering tree |
| `TestForCollisions` | 2847 | Moves changed bodies between trees before physics. After physics, brings collision boxes up to date: only items without physics and moved bodies, or every item with physics off (see below) |
| `RequireSimulation` | 3002 | Walks the sleeping tree |
| `ClearForces`, `ApplyGravity`, `SaveKinematicState`, `IntegrateTransforms`, `SynchronizeTransforms`, `SetScreenPositionsFromPhysicsPositions` | 3030, 3382, 3399, 3415, 3337, 3444 | Walk the awake tree |
| `SolvePhysics` | 3165 | TreeLayer3D's version: groups start from awake bodies; clears only last step's `grouped` flags; notes woken and sleeping bodies; moves them after the groups are solved; updates collision boxes for `grouped` only |
| `PredictUnconstrainedMotion` | 3143 | Private and never called. Remove it, or have it walk the awake tree |

### Collision boxes after physics, without a per-frame walk

TreeLayer3D checks a list of moved items for this. In Layer3D, the layer
keeps `movedItems`, filled by `ItemMoved`:

- **With physics on:** for each moved item with no parent, update its
  collision box if it has no physics, or has physics and is marked as moved
  (`HasMoved`). Awake bodies were already updated in `SolvePhysics`.
- **With physics off:** every item, as today.

### The hooks, filled in

| Hook | Does |
|---|---|
| `ItemMoved(item)` | Adds the item to `movedItems` |
| `ItemResized(item)` | Gets the item's bounds again; re-adds it to the rendering tree, or notes it as having no bounds yet |
| `ItemPhysicsChanged(item)` | Adds it to, or removes it from, the physics trees |
| `ItemSimulationChanged(item)` | Adds it to `changedBodies` |

`movedItems` is emptied once per frame, at the end of `TestForCollisions`.
Each item's report is cleared with `SetReportedMove(false)` as it is
handled. In batch 2 the rendering tree is told about each item at the same
time (fix (a), below).

### Physics without the copy-back reporting

Every item reports now, so the copy-back no longer tells the rendering tree
about moves. `SetScreenPositionFromPhysicsPosition` ends in `SetOffset`,
which reports.

### Bounds from the item: `Item3D`, `Terrain` and `RenderTree3D`

**`Interface/Item3D.quorum`**, a new action, near `GetWidth`:

```
    /*
    This action fills in the box around this item's shape, in its own
    coordinates, for a layer that culls what it draws. It returns false if
    the item has no shape to cull by.

    This version gives a box of the item's width, height and depth,
    centered on the item. A model gets its width, height and depth from its
    blueprint when it loads, so this works for most models. An item whose
    shape is not centered on it, such as a terrain, whose mesh starts at its
    corner, should replace this action with one that gives its real box.

    An item with no size has no box, and neither has one with a negative
    size, which a blueprint with a bug in its measuring could give. A flat
    box, such as a plane's, is allowed.

    Attribute: Parameter local The box to fill in.
    Attribute: Returns True if the box was filled in, false if the item has
    none.
    */
    action GetRenderBounds(BoundingBox local) returns boolean
        number halfWidth = width / 2
        number halfHeight = height / 2
        number halfDepth = depth / 2
        if halfWidth < 0 or halfHeight < 0 or halfDepth < 0
            return false
        end
        if halfWidth = 0 and halfHeight = 0 and halfDepth = 0
            return false
        end
        Vector3 minimum
        minimum:Set(-halfWidth, -halfHeight, -halfDepth)
        Vector3 maximum
        maximum:Set(halfWidth, halfHeight, halfDepth)
        local:Set(minimum, maximum)
        return true
    end
```

This is the rule that `RenderTree3D.GetBounds` uses today, moved onto the
item. The two vectors are made each time it is called, which is when an item
is added or changes size, not every frame.

**`Game/Graphics/Worlds/Terrain.quorum`**, an override:

```
    /*
    This action fills in the box around the terrain's mesh, in its own
    coordinates. The mesh starts at the terrain's position, at one corner,
    and runs one unit per height sample across and deep, as tall as its
    highest point. The terrain's scale is in its transform, so it is not
    applied here.

    Attribute: Parameter local The box to fill in.
    Attribute: Returns True, or false if the terrain has not been built yet.
    */
    action GetRenderBounds(BoundingBox local) returns boolean
        if GetPixelWidth() <= 0 or GetPixelHeight() <= 0
            return false
        end
        Vector3 minimum
        minimum:Set(0, 0, 0)
        Vector3 maximum
        maximum:Set(GetPixelWidth() - 1, GetHeight(), GetPixelHeight() - 1)
        local:Set(minimum, maximum)
        return true
    end
```

This is the box AllTerrainVehicle passes to `SetRenderBounds` today.
`GetHeight` is the terrain's highest point, which it sets when built.
Building a terrain sets its width, height and depth, which reports a resize,
so a terrain added before it is built gets this box once it is.

**`Game/Graphics/Trees/RenderTree3D.quorum`:**

- `Add(item, isStatic)` asks the item:

  ```
        BoundingBox local
        if not item:GetRenderBounds(local)
            return false
        end
        return Add(item, local, isStatic)
  ```

- The private `GetBounds` and the `minimum` and `maximum` fields it used are
  removed.
- `Add(item)`'s comment changes from "a box of the item's width, height and
  depth, centered on the item" to "the box the item gives with
  GetRenderBounds".

The other `Add` actions, which take a box, are unchanged, for anything that
wants to give its own.

### EditorLayer3D (`Interface/Controls/Scenes/Layers/EditorLayer3D.quorum`)

Remove its `Add(integer, Item3D)` (line 231) and `AddToFront` (line 243)
overrides. They only pass the call on and set the item's input group, which
its `Add(Item3D)` override already does. Nothing else in it uses the array
or an index. Its `Update` and `ProcessMouseEvent` overrides call the
parent's, which now walk the tree.

### Testing batch 1

- PhysicsTests (28 world tests) and the Tier A tests. Physics is the most
  changed part.
- AllTerrainVehicle with a plain Layer3D: driving, stacks falling and
  settling, and the rain balls being removed.
- BoxDestroy and the four joint examples.
- GroundFlightTactics, and the scene editor (EditorLayer3D, saving and
  loading a scene).

---

## Batch 2: culling in Layer3D

**Status: done, compiled and ran.** As described below, with fix
(a) for moved items. Small differences from the text:

- `DrawTransparent` takes only the painter; it reads the layer's camera.
- `sortSpace` is grown to the number of transparent models before sorting,
  since `Sort(comparison, temp)` writes into `temp` by index. It only
  grows, since shrinking an array makes a new one.
- A private `CastsShadows(item)` skips models with `CastsShadows` false in
  the shadow pass; other items are drawn, since their children may cast.
- `GetRenderTree` and `SetRenderTree` have examples.
- `Layer3D`'s class comment describes culling, and that children are
  culled with their parent (decision 4).
- There are no "items drawn" counts on `Layer3D`, since they were not in
  the plan. See Testing batch 2.

### Fields

```
    // Reused every frame. Emptied with Empty(false), which keeps their
    // storage.
    Array<Item3D> found
    Array<Item3D> transparentItems
    Array<Item3D> sortSpace

    // Sorts transparent items from farthest to nearest.
    Item3DBackToFrontComparison backToFront

    // Counts frames, so an item found by more than one search is drawn once.
    integer frame = 0
```

**Moved items: fix (a), chosen 2026-10-14.** Batch 1 empties `movedItems`
at the end of `TestForCollisions`, which runs before `Draw`, so `Draw` would
never see a move. Instead, the rendering tree is told about each moved item
where the list is emptied:

- Batch 1's `ClearMovedItems` becomes `UpdateRenderTree`: for each item,
  `renderTree:Moved(item)` (which skips children and items no longer in the
  tree), then `SetReportedMove(false)`, then `Empty(false)`.
- `TestForCollisions` calls it where it called `ClearMovedItems`, in both
  places. The game loop runs input, `Update`, `TestForCollisions`, then
  `Draw`, so every move of the frame is in the tree before drawing.
- `Draw` also calls it first. `Game` only calls the layer's
  `TestForCollisions` when its collisions are on, so with them off, moves
  would otherwise never reach the tree. When collisions are on, the list is
  already empty and this does nothing.

### Actions

- **`GetRenderTree`**, and **`SetRenderTree(RenderTree3D)`**, so a game can
  swap in a `QuadTree3D` or `Octree3D`. Setting it adds every item to the
  new tree, since a tree cannot be copied into another.
- **`Draw`**, as TreeLayer3D's, without its always-drawn and unmeasured
  lists:
  1. `UpdateRenderTree()`, for any moves not handed over in
     `TestForCollisions` (see "Moved items" above).
  2. `CollectVisible(camera, found)`. Draw each item found once, using the
     leaf's `LastDrawnFrame`. Transparent models are set aside instead (see
     Transparency).
  3. In Vulkan, shadow casters:
     - each directional light, with
       `CollectDirectionalShadowCasters(light, camera, found)`;
     - each point light, with `CollectPointShadowCasters`.

     Each caster not yet drawn this frame is drawn, skipping models whose
     `CastsShadows` is false.
  4. Sort the set-aside transparent models and draw them.
  5. `EndFrame`.

### Animated models

Animated models are culled by their box like any other item. A pose that
reaches outside the box can be culled at the edge of the view. A game that
needs this changed can give the model a larger box by overriding
`GetRenderBounds`.

### Items with no box

An item with no box, such as a light, sound or grouping item, is in the
tree as a box of no size at its position. It is drawn when that point is in
view. Such items draw nothing themselves, but their children are drawn
through them, so a group whose position is off screen hides its children.
This is the same rule as for children outside their parent's box (decision
4).

### Transparency

#### How the two painters handle it today

**OpenGL** (`OpenGLPainter3D.Flush`, line 196): every part of every model is
put in one list and sorted (`Renderable.Compare`): opaque parts first, then
blended parts from farthest to nearest. The order models are handed to the
painter does not matter. **Culling changes nothing here.**

**Vulkan** (`VulkanPainter3D`) is a deferred renderer. The scene pass writes
each pixel's color, position, normal and surface values to separate images.
A lighting pass then lights each pixel from those. Only the color image
blends (`AddDefaultInfo3D` in `VulkanPipelineInfoCreator`: source alpha, one
minus source alpha). Position, normal and depth are replaced by whichever
surface is drawn last and passes the depth test. So in Vulkan:

1. **Order matters.** A transparent surface blends over whatever color was
   already in the pixel. If something behind it is drawn after it, the
   depth test rejects that later surface, and it does not show through.
2. **Models are drawn by blueprint, then by texture group:**
   - `Render` puts each model in a batch for its blueprint, with transparent
     models in separate batches (`GetBatch`, line 864).
   - Transparent batches are processed after opaque ones, in the order each
     blueprint was first rendered that frame. Within a batch, models stay in
     the order they were rendered.
   - But all batches write into the same draw queues, one per texture
     group, and each queue is drawn with one command, in texture group
     order (about line 1200). So a transparent model in texture group 0 is
     drawn before an opaque model in texture group 1. **This is a problem
     today, unrelated to culling.**
3. **Lighting uses the nearest surface.** A transparent surface's position
   and normal replace those behind it, so what shows through is lit as if
   it were at the transparent surface. This is how deferred renderers
   behave without a separate pass for transparent objects.

With the array, models were handed to the painter in the order they were
added, so a game could get a stable result by adding far transparent models
first. With the tree, the order is the tree's, and it changes as things
move. **Without a fix, overlapping transparent models can swap order from
frame to frame and flicker.**

#### Proposed for batch 2: the layer sorts what it hands the painter

1. While drawing what the camera sees, a model that `HasTransparency` is set
   aside in `transparentItems` instead of being drawn.
2. After everything else, the set-aside models are sorted from farthest to
   nearest, by distance from the camera to each model's position, and drawn
   in that order.
3. Shadow casters are drawn as found, even if transparent. They are off
   screen, so their order in the main pass makes no difference.

**`Game/Layer3D.quorum`, in `Draw`'s visible loop:**

```
            Item3D item = found:Get(i)
            RenderTreeNode3D leaf = renderTree:GetLeaf(item)
            if leaf not= undefined and leaf:GetLastDrawnFrame() not= frame
                leaf:SetLastDrawnFrame(frame)
                if IsTransparent(item)
                    // Drawn last, from farthest to nearest. See DrawTransparent.
                    transparentItems:Add(item)
                else
                    item:Draw(painter)
                end
            end
```

**After the shadow casters:**

```
        DrawTransparent(painter, camera)
```

**New private actions:**

```
    /*
    This action returns true if an item is a model with transparency, so it
    must be drawn after the models behind it.

    Attribute: Parameter item The item.
    Attribute: Returns True if the item is a transparent model.
    */
    private action IsTransparent(Item3D item) returns boolean
        if item is Model
            Model model = cast(Model, item)
            return model:HasTransparency()
        end
        return false
    end

    /*
    This action draws the transparent models set aside while drawing, from
    farthest to nearest, so each blends over what is behind it.

    The models are sorted by the distance from the camera to each model's
    position. A model's position is usually its center. Two transparent
    models that overlap in depth can still blend in the wrong order, since
    each is drawn whole.

    Attribute: Parameter painter The layer's painter.
    Attribute: Parameter camera The camera the distances are measured from.
    */
    private action DrawTransparent(Painter3D painter, Camera camera)
        if transparentItems:IsEmpty()
            return now
        end

        Vector3 eye = camera:GetPosition()
        backToFront:SetOrigin(eye:GetX(), eye:GetY(), eye:GetZ())
        transparentItems:Sort(backToFront, sortSpace)

        integer i = 0
        repeat while i < transparentItems:GetSize()
            transparentItems:Get(i):Draw(painter)
            i = i + 1
        end
        transparentItems:Empty(false)
    end
```

`Array:Sort(comparison, temp)` takes an array to work in, so `sortSpace` is
reused and sorting makes no new arrays once it has grown to fit.

**New class, `Game/Item3DBackToFrontComparison.quorum`**, next to the
existing `Item3DDepthComparison`. That class sorts nearest first, for mouse
picking, and makes a new vector for every item it compares
(`GetGlobalPosition`). This one sorts farthest first, and reads the
position's numbers directly, since `GetGlobalX` and its partners read the
item's transform without rebuilding it.

```
package Libraries.Game

use Libraries.Interface.Item3D
use Libraries.Containers.Support.Comparison

/*
Item3DBackToFrontComparison sorts 3D items from farthest to nearest from a
point, such as the camera. Layer3D uses it to draw transparent models after
everything else, farthest first, so each blends over what is behind it.

Distances are measured to each item's position, and compared squared, so
no square roots are needed.

Attribute: Example

use Libraries.Game.Item3DBackToFrontComparison
use Libraries.Interface.Item3D
use Libraries.Containers.Array

Item3D near
near:SetPosition(0, 0, 2)
Item3D far
far:SetPosition(0, 0, 10)

Array<Item3D> items
items:Add(near)
items:Add(far)

Item3DBackToFrontComparison backToFront
backToFront:SetOrigin(0, 0, 0)
items:Sort(backToFront)
output items:Get(0):GetZ()
*/
class Item3DBackToFrontComparison is Comparison
    number originX = 0
    number originY = 0
    number originZ = 0

    /*
    This action sets the point distances are measured from.

    Attribute: Parameter x The point's x coordinate.
    Attribute: Parameter y The point's y coordinate.
    Attribute: Parameter z The point's z coordinate.
    */
    action SetOrigin(number x, number y, number z)
        originX = x
        originY = y
        originZ = z
    end

    /*
    This action compares two items by their distance from the origin. The
    farther item comes first.

    Attribute: Parameter a The first item.
    Attribute: Parameter b The second item.
    Attribute: Returns -1 if a is farther, 1 if b is farther, or 0 if they
    are the same distance.
    */
    action Compare(Object a, Object b) returns integer
        Item3D left = cast(Item3D, a)
        Item3D right = cast(Item3D, b)
        number leftDistance = DistanceSquared(left)
        number rightDistance = DistanceSquared(right)
        if leftDistance > rightDistance
            return -1
        elseif leftDistance = rightDistance
            return 0
        end
        return 1
    end

    /*
    This action returns the squared distance from the origin to an item's
    position.

    Attribute: Parameter item The item.
    Attribute: Returns The squared distance.
    */
    private action DistanceSquared(Item3D item) returns number
        number dx = item:GetGlobalX() - originX
        number dy = item:GetGlobalY() - originY
        number dz = item:GetGlobalZ() - originZ
        return dx * dx + dy * dy + dz * dz
    end
end
```

#### What this fixes, and what it does not

| Case | OpenGL | Vulkan with this change |
|---|---|---|
| Flicker from tree order changing as things move | Never happened | **Fixed**: the order is by distance every frame |
| Transparent models of one blueprint | Correct | **Correct**: drawn farthest first within their batch |
| Transparent models of different blueprints, apart in depth | Correct | **Correct**: batches are ordered by their first, farthest model |
| Transparent models of different blueprints, interleaved in depth (A far, B middle, A near) | Correct | **Wrong**: Vulkan draws all of A's batch together, so B is drawn before or after both |
| A transparent model whose texture group comes before an opaque model's | Correct | **Wrong** (as today): the queues are drawn by texture group, each holding opaque then transparent |
| A blueprint with several meshes | Correct | **Partly**: `ProcessBatch` draws mesh 0 for every model, then mesh 1, so the order holds per mesh |
| Lighting of what shows through | Correct (forward) | **As today**: lit as the nearest surface |
| A transparent child of an opaque parent | Correct | **Not sorted**: children are drawn with their parent |

The rows marked **Wrong** need painter changes, which are outside this
batch. In order of effort:

1. **Transparent draw queues drawn after every opaque queue.** Fixes the
   texture group problem. In `VulkanPainter3D`, transparent batches would
   write into a second set of queues, drawn after the first in the scene
   pass.
2. **One draw command per transparent model, in the order rendered.** Fixes
   interleaved blueprints and multi-mesh models, at the cost of instancing
   for transparent models only, which are usually few.
3. **A forward pass for transparent models after lighting.** Fixes
   lighting. A large change.

### Testing batch 2

- AllTerrainVehicle. Profile against the batch 1 run (snapshot
  `Default-2026-10-14-shutdown-4`, drawing everything), and run the
  benchmark for frame times. `Layer3D` has no "items drawn" counts, so the
  counts from TreeLayer3D's runs cannot be compared directly unless counts
  are added.
- Shadows from off-screen casters, with the sun's distance at 0, 20 and 50.
- Transparency, in both APIs:
  - two transparent boxes, one behind the other, while the camera circles
    them: the far one should show through the near one from every side,
    with no flicker;
  - the same with two different blueprints (a box and a sphere);
  - a transparent box in front of an opaque one with a different texture,
    to see the texture group problem.
- The scene editor's grid and cursor, which are items on its layer.

## Batch 3: clean-up in AllTerrainVehicle

**Status: done, compiled and ran.** `RenderTreeCheck` kept as it
was; it still runs its own tree beside the layer's. The terrain is added to
it with `Add(terrain, true, false)`, since the terrain now gives its own
bounds through `GetRenderBounds`.

- Delete `TreeLayer3D`, `CullingLayer3D`, `Model2` and
  `ReportingPhysicsProperties3D`, and `Main`'s `SetRenderBounds` calls for
  the terrain. `RenderTreeCheck` stays as a test tool,
  or is rewritten to read Layer3D's tree with `GetRenderTree`.
- `Main` goes back to the default layer and `Model`. Its only culling
  setting left is the sun's shadow distance.
- Update `Handoff.md`, `RenderTreeIntegration.md` and the LibraryStaging
  notes, which describe the earlier plan.

---

## Risks

- **Anything that relied on item order.** Drawing, updating, input
  tie-breaks and scene saving all now follow the tree's order.
  - Scenes still save every item, but in a different order each time.
  - Code that draws one item over another by adding it later, without
    depth, would change. Opaque 3D drawing uses depth, so only transparency
    is affected, and batch 2 sorts it.
- **Games that use the removed index actions** stop compiling. Nothing in
  the library, Quorum Studio, or the example games uses them. Tutorials
  and documentation pages outside the library might, and would need
  checking.
- **Adding or removing items during a walk:**
  - Removing the current item is safe, since every walk holds the next leaf.
  - Removing others, or adding, can make a walk skip an item or visit one
    twice. This is a change from the array, where adding during `Update`
    was safe (the new item was simply not updated that frame).
  - A fix, if needed, is to save up adds and removes made during a walk and
    apply them after it. This could be added in batch 1 if testing shows
    problems.
- **`EditorLayer3D`** keeps its overrides of `Add(Item3D)`, `Update` and
  `ProcessMouseEvent`, which call the parent's. Its selection and focus may
  depend on the order items were added in, and need testing.
- **Physics behavior.** The awake and sleeping trees change the order bodies
  are solved in, which can change results slightly, though not
  correctness. The PhysicsTests check positions with tolerances, so they
  should still pass. If any fail, the order is the first thing to look at.
