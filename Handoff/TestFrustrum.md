# Plan: tests for the frustum culling library

Written 2026-10-15. A plan for review. **Nothing has been written yet.**

This is the next task. It tests the culling work that is now in the
library: the render trees (`Libraries.Game.Graphics.Trees`), item
reporting, `Item3D:GetRenderBounds`, the shadow distance, and `Layer3D`'s
trees and culled drawing. The design behind them is in
`Open/Layer3DTrees.md`.

Library paths are relative to
`quorum-language/Quorum/Library/Standard/Libraries`. The library is on
branch `FrustrumCull2`.

## Goals

1. Catch bugs before the work is merged: wrong boxes, items lost or seen
   twice by a walk, a tree that misses a moved item, wrong shadow casters.
2. Write the tests so they can later move into Quorum's own test suite with
   the physics tests (`PhysicsTestsMove.md`), unchanged.
3. Keep `AllTerrainVehicle/SourceCode/RenderingChecks/RenderTreeCheck` as a
   live check beside a running game. The tests here replace it as the main
   check, but it does not need to be deleted.

## How the tests are built

The physics tests already have two tiers, and these tests follow them
(see `PhysicsTestsMove.md` for how each tier moves into Quorum):

| Tier | Needs a window? | Style | Runner |
|---|---|---|---|
| **A: tree tests** | No | One class per test, `is Test`, `SetName` in `on create`, checks in `Run`. Same as the 93 Tier A physics tests. | A plain class with `action Main`, like `AllTerrainVehicle/SourceCode/RunPhysicsTests.quorum`, and a tester class in package `Libraries.Language.Compile.Test`, like `PhysicsTester`. |
| **B: layer tests** | Yes. `Layer3D` and `Camera` read the game display when they are created. | A base class like `PhysicsTests`' `PhysicsWorldTest`, with helpers to make a layer and step it. | A `Game` whose `CreateGame` runs the tests and prints the results, like `PhysicsTests/SourceCode/Main.quorum`. |

**What can be made without a window** (checked in the library source):

- `Item3D`, `BoundingBox`, `Matrix4`, `Vector3`: yes. The tree class
  examples already do this.
- `CameraMatrix4`: yes. Quorum's own `Matrix4SetToOrthographic` test makes
  one with no game. A view-projection matrix for a test camera is
  `PerspectiveProjection(near, far, fieldOfView, aspect)` times
  `SetToLookAt(position, target, up)`, and is passed to
  `CollectVisible(Matrix4, results)`.
- `DirectionalLight`, `PointLight`: probably. `Light` reads no game state
  when created. Check with the first test.
- `Camera`, `PerspectiveCamera`, `Layer3D`, `Terrain`, loading a `Model`:
  no. These go in Tier B.

**Where the code goes:** a new test project, `physics/FrustrumTests`, with
two main files (`RunTreeTests.quorum` for Tier A, `Main.quorum` for
Tier B), and folders `Tests/Trees/...` and `Tests/Layer/...`. Package
`Frustrum.Tests` for the tests, and `Libraries.Language.Compile.Test` for
the Tier A tester (`RenderTreeTester`), so it can be copied into Quorum.

**Checking against a hand count.** Many tests compare a tree's answer with
testing every item by hand, using `CullingVolume3D:Test` on each item's
world box (or a box or sphere test for `CollectInBox` and
`CollectInSphere`). `RenderTreeCheck.CompareWithVolume` already does this
and can be reused. A tree may return more than the hand count (an item that
only touches the edge), but never fewer.

**Each tree kind.** Every Tier A tree test is run three times, once each
with `DynamicVolumeRenderTree3D`, `QuadTree3D` and `Octree3D` (the last two
with `SetRegion` set). A helper `MakeTree(kind)` keeps each test written
once. The test name says which kind failed.

## Step 0: a quick check that Tier A works with no window

One Tier A test that builds a `DynamicVolumeRenderTree3D`, an `Item3D`, a
`CameraMatrix4` projection and a `DirectionalLight`, and runs one
`CollectVisible(Matrix4, ...)`. If it runs from a plain `Main`, the plan
holds. If `DirectionalLight` needs a game, the light tests move to Tier B.

## Tier A: tree tests (no window)

### `CullingVolume3D`

1. **Identity matrix:** a box inside the unit cube is `INSIDE`, one far
   away is `OUTSIDE`, one across an edge is `INTERSECTING`. Five planes.
2. **Perspective view:** a box in front of the camera is inside; behind
   the camera, outside; to the side, past the field of view, outside;
   across the left edge, intersecting.
3. **No near plane:** a box between the camera and the near plane is not
   outside. This is on purpose (shadow casters behind the near plane), so
   the test records the rule.
4. **Shadow column** (`SetShadowColumn`), light shining down and to the
   side:
   - a box beside the center, within the distance, is inside;
   - a box past the distance to the side is outside;
   - a box far toward the light (high up) is inside, since the column has
     no end that way;
   - a box past the distance away from the light is outside.
5. **Column edge cases:** a direction of no length returns false and the
   volume finds nothing. A light straight down uses the other "up" and
   still gives five planes.

### The trees (each kind)

6. **Add, Has, Remove, GetSize, Empty.** Static and dynamic counts add up.
   Adding an item twice leaves it in the tree once (check what `Add`
   returns; the test records it). `Remove` of an item not in the tree
   returns false.
7. **Items with no box:** `Add(item)` for an item with no size returns
   false. `Add(item, box)` with a given box works.
8. **Off-center boxes:** an item added with its own box (as terrain is,
   corner at its position) is found where its box is, not around its
   position.
9. **Moved:** an item moved out of view is no longer found once `Moved` is
   called, and is found at its new place. Both `Moved(item)` and
   `Moved(leaf)`.
10. **Rotation and scale:** a long thin item turned 90 degrees, and an item
    scaled by 4, are found where their turned or scaled box reaches.
11. **Static and dynamic:** a static item that moves becomes dynamic. A
    dynamic item that stays still for `FRAMES_UNTIL_STATIC` (120) frames of
    `EndFrame` becomes static again, checked every `CHECK_INTERVAL` (30).
    `GetStaticVersion` changes when the static part changes.
12. **CollectVisible against a hand count:** 500 items at seeded random
    places, sizes and turns, viewed from several cameras. Nothing the hand
    count finds is missing. Repeat after moving half of them.
13. **CollectInBox and CollectInSphere against a hand count,** the same
    way.
14. **Walking:** `GetFirstLeaf` and `GetNextLeaf` visit every item exactly
    once. With the next leaf found first, removing the current item during
    the walk still visits every other item once. `GetIterator` gives the
    same items.
15. **IsShowing and IsShowingWithParents:** a hidden item, and an item
    whose parent is hidden.
16. **Children:** a child of an item in the tree is not in the tree itself;
    the parent is.
17. **Quadtree and octree region:** an item outside the region set with
    `SetRegion` is still found. (Check what the code does first; the test
    records it.)

### Shadow casters

18. **Point light:** `CollectPointShadowCasters` finds the items within the
    light's range (`PointLight:GetRange`) and not those past it, against a
    hand count.
19. **Point light cache:** a second search with nothing changed gives the
    same items. After a static item moves, the result changes.
    `ShadowCasterCache3D:Matches` is false when the light moves or its
    range changes.
20. **Directional light by cascade:** `CollectDirectionalShadowCasters(light,
    cascade, results)` with a light that has no shadow data adds nothing.

### Item and sorting

21. **`Item3D:GetRenderBounds`:** a centered box of the item's size; false
    for no size; false for a negative size; true for a flat box.
22. **`Item3DBackToFrontComparison`:** items sort farthest first from the
    origin; equal distances compare as 0; moving the origin changes the
    order. Uses `Sort(comparison, temp)` with a temp array large enough.

## Tier B: layer tests (window)

These need a running game, but nothing is drawn to look at. To see what
`Layer3D.Draw` hands the painter, the tests add a small test class,
`CountingItem3D is Item3D`, whose `Draw(Painter3D)` counts how often it is
called and in what order. Models are needed for the shadow and transparency
tests, so there is also `CountingModel is Model`, with `HasTransparency` and
`CastsShadows` set by the test. No library change is needed for this.

Each test calls `layer:Draw()` itself after placing the camera, then reads
the counts.

### Layer contents (batch 1)

23. **Add, Remove, Has, GetSize, IsEmpty, Empty, GetIterator** on a layer,
    with and without physics.
24. **Removing during Update:** an item that removes itself, or another
    item, during `Update`. Every other item is still updated once. (Adding
    during a walk is a known risk in `Layer3DTrees.md`; this test shows
    what happens.)
25. **Physics changes:** turning physics on and off for an item on the
    layer, and a body falling asleep and waking. Physics keeps working.
    The 28 world tests in `PhysicsTests` cover physics itself.
26. **Resize after adding:** an item added with no size, then given one,
    is drawn once it is in view.
27. **Mouse picking** still finds the nearest item under the mouse.

### Culled drawing (batch 2)

28. **In view and out of view:** items in front are drawn once; items
    behind and to the side are not.
29. **Moves reach the tree:** an item moved into view in `Update` is drawn
    in the same frame. Run once with collisions on and once with the game's
    collisions off (the `Draw` path of fix (a)).
30. **Children:** a child far outside its parent's box is not drawn when
    the parent is out of view (decision 4), and is drawn when the parent
    is in view.
31. **Drawn once:** an item found by both the camera search and a shadow
    search is drawn once.
32. **Shadow casters (Vulkan only):**
    - an item behind the camera, inside the sun's column, is drawn; one
      past the shadow distance is not;
    - a model with `CastsShadows` false is not drawn as a caster;
    - with the sun's distance at 0, the cascades are searched instead;
    - an item within a point light's range is drawn.
33. **Transparency order:** three transparent models at different
    distances are drawn after every opaque item, farthest first. Moving the
    camera to the other side reverses the order.
34. **SetRenderTree:** after swapping to a `QuadTree3D` and an `Octree3D`,
    every item is still on the layer and culling gives the same counts.
35. **Terrain:** a terrain whose corner is out of view but whose middle is
    in view is drawn (its `GetRenderBounds`).
36. **Editor layer:** `EditorLayer3D` items (grid, cursor) are drawn.

## By eye and by benchmark (the user runs these)

These are not automated:

- Benchmark frame times in AllTerrainVehicle, batch 1 (library commit
  `581a60746`) against batch 2, with `benchmark = true`.
- Shadows from objects behind the camera, with the sun's distance at 0, 20
  and 50. Nothing should pop at the screen edges.
- Transparency in Vulkan: two transparent boxes while the camera circles
  them; a box and a sphere; a transparent box in front of an opaque one
  with a different texture (expected to be wrong, the texture-group bug).
- GroundFlightTactics, BoxDestroy and the joint examples look and behave as
  before. Scene editor: save and load a scene.

## Order of work

1. Step 0 (one Tier A test). Report whether it runs with no window.
2. Tier A tests 1 to 22, with `RenderTreeTester` and `RunTreeTests`.
3. Tier B base class, `CountingItem3D` and `CountingModel`, then tests 23
   to 36.
4. Fix what they find. Library fixes need the user's go-ahead, one at a
   time.
5. Move both tiers into Quorum with the physics tests
   (`PhysicsTestsMove.md`).

## Open questions for the user

1. Project name `FrustrumTests` and package `Frustrum.Tests`, or another
   name?
2. Should Tier B check exact draw counts (fragile if the tree finds an
   extra item at an edge), or only "at least these, none of those"? The
   plan uses the second.
3. Should `Layer3D` get "items drawn" counts for testing, instead of the
   counting test classes? That would be a library change.
