# Speeding up box against terrain triangles

> **Status, 2026-10-15: done.** Items 1, 3 and 5 applied; 2 and 4 declined as harder to read.

Written 2026-10-14 from the AllTerrainVehicle snapshot taken with TreeLayer3D
and Model2 (`Default-2026-10-14-shutdown-1.snapshot`). These are proposed
changes to the standard library.

**Status, 2026-10-14:** items 1, 3 and 5 were made on branch `FrustrumCull`.
Items 2 and 4 were declined: they are correct, but make the code much harder
to read. Item 5's `sidesReady = false` line in `LoadCorners` belongs to item
2, so it was not needed.

Library paths are relative to
`quorum-language/Quorum/Library/Standard/Libraries/Game/Collision`.

## Where the time goes

`SharedNarrowSolver.CollideTriangle` is 7,860 samples, about 15% of the
frame. Its caller, `HeightmapTerrainShape.ProcessTriangle`, spends about
4,060 more before calling it.

| Part | Samples |
|---|---|
| `BoxTriangleCollider.FindBestAxis` | 2,400 |
| `BoxTriangleCollider.ReportKept` | 1,360 |
| `LoadTriangle`: world corners, then `TriangleGeometry3D.Calculate` | 1,080 |
| `localTriangle:Load`: `Calculate` again, in the box's space | 960 |
| `Box.GetHalfExtentsWithoutMargin`, once per triangle | 480 |
| Caller: `FillAtPixel` | 1,380 |
| Caller: `SetTriangleBox` | 1,340 |
| Caller: `Intersects` | 680 |
| Caller: `TransformWorldCoordinate` | 660 |

## Summary

| Item | Change | Files | Estimated saving |
|---|---|---|---|
| 1 | Test only the cells under the shape's grown box | `HeightmapTerrainShape` | about 2,500 |
| 2 | Load only the corners in world space; compute the geometry once, in the box's space | `TriangleGeometry3D`, `TriangleCollider3D`, `BoxTriangleCollider` | about 900 |
| 3 | Read the box's size once per shape, not once per triangle | `BoxTriangleCollider`, `SharedNarrowSolver`, `HeightmapTerrainShape` | about 450 |
| 4 | Separating axis test on plain numbers | `BoxTriangleCollider` | about 1,000 to 1,400 |
| 5 | Work out side normals only when asked for | `TriangleGeometry3D` | about 200 to 400 |

Items 2, 3, 4 and 5 compute exactly the same numbers in the same order, so
contacts are unchanged. Item 1 changes only which triangles are rejected
before the collider is called; the triangles that reach it are the same.

To check each step, run the Tier A tests in AllTerrainVehicle
(`Tests/Physics/Colliders` and the rest of `RunPhysicsTests.quorum`) and the
PhysicsTests world tests before and after, then profile again.

---

## Item 1: test only the cells under the shape's box

**File:** `Shapes/HeightmapTerrainShape.quorum`, `ProcessAllTriangles`, about
line 294.

`tempShapeBox` has already been grown by the terrain's margin plus the
contact threshold, a few lines above. Cell `i` covers the grid from `i` to
`i + 1`, so the cells from `floor(min)` to `floor(max)` cover all of it. The
extra cell on each side is rejected by `SetTriangleBox` and `Intersects`
every time, but only after `FillAtPixel` and three transforms. For a box
about 1 unit across on cells 0.5 apart, this tests about 5 × 5 cells (50
triangles) where 3 × 3 (18) cover it.

Before:

```
        //Expand by a cell each way, as Bullet does, so a box that falls between
        //grid points still tests the cells on either side of it.
        integer xmin = cast(integer, math:Floor(xLocalMin)) - 1
        integer xmax = cast(integer, math:Floor(xLocalMax)) + 1
        integer zmin = cast(integer, math:Floor(zLocalMin)) - 1
        integer zmax = cast(integer, math:Floor(zLocalMax)) + 1
```

After:

```
        // Cell i covers the grid from i to i + 1, so the cells from
        // floor(min) to floor(max) cover the shape's box. The box has already
        // been grown by the margin and the contact threshold, so nothing
        // within reach lies outside these cells. Bullet widens its range by a
        // cell each way because it rounds the box's corners to the nearest
        // grid point instead of flooring them, and stops one short of its end.
        integer xmin = cast(integer, math:Floor(xLocalMin))
        integer xmax = cast(integer, math:Floor(xLocalMax))
        integer zmin = cast(integer, math:Floor(zLocalMin))
        integer zmax = cast(integer, math:Floor(zLocalMax))
```

The clamping to the map's edges that follows is unchanged.

---

## Item 2: one geometry calculation per triangle, not two

`BoxTriangleCollider.Collide` calls `LoadTriangle`, which moves the corners
into the world and runs `TriangleGeometry3D.Calculate`: the normal, three
side normals and four square roots. `CollideLoaded` then uses only the world
corners (`world:GetCorner`), moves them into the box's space, and runs
`Calculate` again there. The world calculation is never used by the box
collider. The sphere and cylinder colliders do use it, so they keep
`LoadTriangle`.

### `Narrowphase/TriangleGeometry3D.quorum`: new action after `Load(Vector3 a, ...)`

```
    /*
    This action sets only the triangle's corners, moved into the world by
    the given transform. Nothing else about the triangle is worked out, so
    until Load is called, only GetCorner gives correct values. It is for
    colliders that only need the corners, such as BoxTriangleCollider,
    which works out the rest in the box's own space.

    Attribute: Parameter triangle The triangle, with its corners in its own space.
    Attribute: Parameter transform Where the triangle is in the world.
    */
    action LoadCorners(Triangle triangle, PhysicsPosition3D transform)
        corner0:Set(triangle:GetVertex(0))
        corner1:Set(triangle:GetVertex(1))
        corner2:Set(triangle:GetVertex(2))
        transform:Transform(corner0)
        transform:Transform(corner1)
        transform:Transform(corner2)
        sidesReady = false
    end
```

(`sidesReady` comes from item 5. Without item 5, leave that line out.)

### `Narrowphase/TriangleCollider3D.quorum`: new action after `LoadTriangle(Vector3 a, ...)`

```
    /*
    This action loads only a triangle's corners, moved into the world using
    the given transform, and takes its margin from the triangle. The rest of
    the loaded geometry is not worked out, so only its corners may be used.

    Attribute: Parameter triangle The triangle, with its corners in its own space.
    Attribute: Parameter transform Where the triangle is in the world.
    */
    action LoadTriangleCorners(Triangle triangle, PhysicsPosition3D transform)
        geometry:LoadCorners(triangle, transform)
        triangleMargin = triangle:GetMargin()
    end
```

### `Narrowphase/BoxTriangleCollider.quorum`, `Collide`

Before:

```
        Begin(collisionPoints, result, boxIsItemA)
        LoadTriangle(triangle, triangleTransform)
        CollideLoaded(box, transform)
```

After:

```
        Begin(collisionPoints, result, boxIsItemA)
        // Only the corners are needed here. The rest is worked out once, in
        // the box's own space, by CollideLoaded.
        LoadTriangleCorners(triangle, triangleTransform)
        CollideLoaded(box, transform)
```

And in `CollideLoaded`'s comment, "Begin and LoadTriangle must have been
called first" becomes "Begin and LoadTriangle or LoadTriangleCorners must
have been called first. Only the loaded triangle's corners are used."

This also speeds up the two other box-against-triangle paths in
`SharedNarrowSolver` (lines 150 and 171), which call the same `Collide`.

---

## Item 3: read the box's size once per shape

`CollideLoaded` reads the box's half sizes and adds its margin for every
triangle. Across one call to `ProcessAllTriangles`, the box is the same for
every triangle.

### `Narrowphase/BoxTriangleCollider.quorum`

New field, next to `half`:

```
    // The box whose size is in half, set by PrepareBox, so a run of
    // triangles against the same box reads its size once. Undefined when no
    // box is prepared.
    Box preparedBox = undefined
```

New actions, after `CollideLoaded`:

```
    /*
    This action reads a box's size once, before it is tested against many
    triangles in a row. Until ReleaseBox is called, CollideLoaded uses the
    size read here for this box, so the box must not change size in
    between.

    Attribute: Parameter box The box about to be tested.
    */
    action PrepareBox(Box box)
        SetHalfSize(box)
        preparedBox = box
    end

    /*
    This action ends a run of triangles started by PrepareBox.
    */
    action ReleaseBox
        preparedBox = undefined
    end

    /*
    This action sets half to the box's full half size: its half extents
    plus its margin.

    Attribute: Parameter box The box.
    */
    private action SetHalfSize(Box box)
        number boxMargin = box:GetMargin()
        half:Set(box:GetHalfExtentsWithoutMargin()):Add(boxMargin, boxMargin, boxMargin)
    end
```

In `CollideLoaded`, before:

```
        boxTransform = transform
        number boxMargin = box:GetMargin()
        half:Set(box:GetHalfExtentsWithoutMargin()):Add(boxMargin, boxMargin, boxMargin)
```

After:

```
        boxTransform = transform
        if box not= preparedBox
            SetHalfSize(box)
        end
```

### `Narrowphase/SharedNarrowSolver.quorum`: new actions after `CollideTriangle`

```
    /*
    This action prepares for a run of CollideTriangle calls with the same
    shape, so the shape's fixed values are read once. Call ReleaseShape after
    the run.

    Attribute: Parameter shape The shape about to be tested against many triangles.
    */
    action PrepareShape(CollisionShape3D shape)
        if shape:GetType() = shape:BOX
            boxTriangleSolver:PrepareBox(cast(Box, shape))
        end
    end

    /*
    This action ends a run of CollideTriangle calls started by PrepareShape.
    */
    action ReleaseShape
        boxTriangleSolver:ReleaseBox()
    end
```

### `Shapes/HeightmapTerrainShape.quorum`, `ProcessAllTriangles`

Before:

```
        Matrix4 terrainNormalTransform = terrain:GetTransform()
        i = xmin
        j = zmin
        repeat while i <= xmax
            ...
        end

        result:FinishGathering()
```

After:

```
        Matrix4 terrainNormalTransform = terrain:GetTransform()
        narrowSolver:PrepareShape(shape)
        i = xmin
        j = zmin
        repeat while i <= xmax
            ...
        end
        narrowSolver:ReleaseShape()

        result:FinishGathering()
```

There is no early return inside the loop, so `ReleaseShape` is always
reached.

---

## Item 4: the separating axis test on plain numbers

Most of `FindBestAxis`'s 2,400 samples are action calls, not arithmetic:
`BoxReach` (620, six getters and three `AbsoluteValue` calls each time),
`GetComponent` (460), `DotProduct` (220), and `TestAxis`' own overhead.
Every `Vector3` getter is an action call in Quorum, and so is every read of
a constant.

The rewrite reads the three corners and the half sizes into numbers once,
and writes out the nine "box axis crossed with an edge" directions with
numbers. The test is unchanged: the same 13 directions, in the same order,
with the same tie rule (a later direction must be strictly better), and the
same arithmetic in the same order, so the results are identical.

### `Narrowphase/BoxTriangleCollider.quorum`

**Remove:** the field `Vector3 axis`, and the actions `BoxReach` and
`SetToBoxAxisCrossEdge`. Nothing else uses them.

**New fields**, after `testThreshold`:

```
    // Copies of constants used in the separating axis test, which runs for
    // every triangle. Reading a constant is an action call.
    integer triangleFaceKind = TRIANGLE_FACE
    integer boxFaceKind = BOX_FACE
    integer edgePairKind = EDGE_PAIR
    number edgePenalty = EDGE_PENALTY
    number smallAxis = SMALL_AXIS
```

**Replace `FindBestAxis`** (keep its comment, and add the last paragraph
below to it):

```
    /*
    (existing comment, unchanged, then:)

    The corners and the box's half sizes are read into plain numbers once,
    and the directions are worked out with numbers, since every Vector3
    action is a call.
    */
    private action FindBestAxis returns boolean
        bestKind = NO_AXIS
        bestScore = 1.0e100
        testMargin = GetTriangleMargin()
        testThreshold = GetContactThreshold()

        number ax = localCorner0:GetX()
        number ay = localCorner0:GetY()
        number az = localCorner0:GetZ()
        number bx = localCorner1:GetX()
        number by = localCorner1:GetY()
        number bz = localCorner1:GetZ()
        number cx = localCorner2:GetX()
        number cy = localCorner2:GetY()
        number cz = localCorner2:GetZ()
        number hx = half:GetX()
        number hy = half:GetY()
        number hz = half:GetZ()

        if not localTriangle:IsDegenerate()
            Vector3 normalAxis = localTriangle:GetNormal()
            number nx = normalAxis:GetX()
            number ny = normalAxis:GetY()
            number nz = normalAxis:GetZ()
            number along = nx * ax + ny * ay + nz * az
            if not TestAxis(triangleFaceKind, -1, -1, nx, ny, nz, Reach(nx, ny, nz, hx, hy, hz), along, along)
                return false
            end
        end

        if not TestBoxAxis(0, 1, 0, 0, hx, ax, bx, cx)
            return false
        end
        if not TestBoxAxis(1, 0, 1, 0, hy, ay, by, cy)
            return false
        end
        if not TestBoxAxis(2, 0, 0, 1, hz, az, bz, cz)
            return false
        end

        // Edge j runs from corner j to corner j + 1.
        number e0x = bx - ax
        number e0y = by - ay
        number e0z = bz - az
        number e1x = cx - bx
        number e1y = cy - by
        number e1z = cz - bz
        number e2x = ax - cx
        number e2y = ay - cy
        number e2z = az - cz

        // Each box axis crossed with each edge, box axis on the outside and
        // edge on the inside, as before. For edge j, corner j and the
        // corner opposite the edge, j + 2, are measured.
        // The x axis crossed with an edge is (0, -z, y).
        if not TestEdgeAxis(0, 0, 0, -e0z, e0y, ax, ay, az, cx, cy, cz, hx, hy, hz)
            return false
        end
        if not TestEdgeAxis(0, 1, 0, -e1z, e1y, bx, by, bz, ax, ay, az, hx, hy, hz)
            return false
        end
        if not TestEdgeAxis(0, 2, 0, -e2z, e2y, cx, cy, cz, bx, by, bz, hx, hy, hz)
            return false
        end

        // The y axis crossed with an edge is (z, 0, -x).
        if not TestEdgeAxis(1, 0, e0z, 0, -e0x, ax, ay, az, cx, cy, cz, hx, hy, hz)
            return false
        end
        if not TestEdgeAxis(1, 1, e1z, 0, -e1x, bx, by, bz, ax, ay, az, hx, hy, hz)
            return false
        end
        if not TestEdgeAxis(1, 2, e2z, 0, -e2x, cx, cy, cz, bx, by, bz, hx, hy, hz)
            return false
        end

        // The z axis crossed with an edge is (-y, x, 0).
        if not TestEdgeAxis(2, 0, -e0y, e0x, 0, ax, ay, az, cx, cy, cz, hx, hy, hz)
            return false
        end
        if not TestEdgeAxis(2, 1, -e1y, e1x, 0, bx, by, bz, ax, ay, az, hx, hy, hz)
            return false
        end
        if not TestEdgeAxis(2, 2, -e2y, e2x, 0, cx, cy, cz, bx, by, bz, hx, hy, hz)
            return false
        end

        return bestKind not= NO_AXIS
    end
```

**New helpers**, replacing `BoxReach` and `SetToBoxAxisCrossEdge`:

```
    /*
    This action tests one of the box's own axes. Along it, a corner's
    distance is just its x, y or z, and the box reaches exactly its half
    size.

    Attribute: Parameter boxAxis Which axis: 0 for x, 1 for y, 2 for z.
    Attribute: Parameter dx The axis's x.
    Attribute: Parameter dy The axis's y.
    Attribute: Parameter dz The axis's z.
    Attribute: Parameter reach The box's half size along the axis.
    Attribute: Parameter value0 Corner 0's distance along the axis.
    Attribute: Parameter value1 Corner 1's distance along the axis.
    Attribute: Parameter value2 Corner 2's distance along the axis.
    Attribute: Returns False if the box and triangle are separated along it.
    */
    private action TestBoxAxis(integer boxAxis, number dx, number dy, number dz, number reach,
            number value0, number value1, number value2) returns boolean
        number low = value0
        number high = value0
        if value1 < low
            low = value1
        end
        if value1 > high
            high = value1
        end
        if value2 < low
            low = value2
        end
        if value2 > high
            high = value2
        end
        return TestAxis(boxFaceKind, boxAxis, -1, dx, dy, dz, reach, low, high)
    end

    /*
    This action tests one box axis crossed with one triangle edge. A
    direction too short to use, from an axis and an edge that are parallel,
    is skipped. Both corners of the edge are the same distance along the
    direction, so only the edge's first corner and the corner opposite the
    edge are measured.

    Attribute: Parameter boxAxis Which box axis: 0, 1 or 2.
    Attribute: Parameter triangleEdge Which edge: 0, 1 or 2.
    Attribute: Parameter dx The direction's x, before it is made unit length.
    Attribute: Parameter dy The direction's y, before it is made unit length.
    Attribute: Parameter dz The direction's z, before it is made unit length.
    Attribute: Parameter px The x of the edge's first corner.
    Attribute: Parameter py The y of the edge's first corner.
    Attribute: Parameter pz The z of the edge's first corner.
    Attribute: Parameter qx The x of the corner opposite the edge.
    Attribute: Parameter qy The y of the corner opposite the edge.
    Attribute: Parameter qz The z of the corner opposite the edge.
    Attribute: Parameter hx The box's half size along x.
    Attribute: Parameter hy The box's half size along y.
    Attribute: Parameter hz The box's half size along z.
    Attribute: Returns False if the box and triangle are separated along it.
    */
    private action TestEdgeAxis(integer boxAxis, integer triangleEdge, number dx, number dy, number dz,
            number px, number py, number pz, number qx, number qy, number qz,
            number hx, number hy, number hz) returns boolean
        number lengthSquared = dx * dx + dy * dy + dz * dz
        if lengthSquared <= smallAxis
            return true
        end
        number scale = 1 / math:SquareRoot(lengthSquared)
        number ux = dx * scale
        number uy = dy * scale
        number uz = dz * scale

        number first = ux * px + uy * py + uz * pz
        number opposite = ux * qx + uy * qy + uz * qz
        number low = first
        number high = opposite
        if opposite < first
            low = opposite
            high = first
        end
        return TestAxis(edgePairKind, boxAxis, triangleEdge, ux, uy, uz, Reach(ux, uy, uz, hx, hy, hz), low, high)
    end

    /*
    This action returns how far the box reaches from its center along a unit
    direction: each half size times how much the direction lines up with
    that axis.

    Attribute: Parameter dx The direction's x.
    Attribute: Parameter dy The direction's y.
    Attribute: Parameter dz The direction's z.
    Attribute: Parameter hx The box's half size along x.
    Attribute: Parameter hy The box's half size along y.
    Attribute: Parameter hz The box's half size along z.
    Attribute: Returns How far the box reaches along the direction.
    */
    private action Reach(number dx, number dy, number dz, number hx, number hy, number hz) returns number
        number absoluteX = dx
        if dx < 0
            absoluteX = -dx
        end
        number absoluteY = dy
        if dy < 0
            absoluteY = -dy
        end
        number absoluteZ = dz
        if dz < 0
            absoluteZ = -dz
        end
        return hx * absoluteX + hy * absoluteY + hz * absoluteZ
    end
```

**Change `TestAxis`** to take the direction as three numbers. Only the
signature, the edge check and the recording of `bestNormal` change:

```
    private action TestAxis(integer kind, integer boxAxis, integer triangleEdge,
            number dx, number dy, number dz, number boxReach, number low, number high) returns boolean
        number triangleAbove = (low - testMargin) - boxReach
        number triangleBelow = -boxReach - (high + testMargin)
        number separation = triangleAbove
        if triangleBelow > separation
            separation = triangleBelow
        end

        if separation > testThreshold
            return false
        end

        number overlap = -separation
        number score = overlap
        if kind = edgePairKind
            if overlap > 0
                score = overlap * edgePenalty
            else
                score = overlap / edgePenalty
            end
        end

        if score < bestScore
            bestScore = score
            bestKind = kind
            bestBoxAxis = boxAxis
            bestTriangleEdge = triangleEdge
            if triangleAbove >= triangleBelow
                // The triangle is on the positive side, so the box is pushed
                // toward the negative side.
                bestNormal:Set(-dx, -dy, -dz)
            else
                bestNormal:Set(dx, dy, dz)
            end
        end

        return true
    end
```

**Notes on matching the old results exactly:**

- The old code made the crossed axis unit length with
  `axis:Scale(1 / SquareRoot(lengthSquared))`, which multiplies each
  component by the same value, as `scale` does here.
- `DotProduct` and the old `BoxReach` add x, then y, then z, as here.
- `bestNormal:Set(direction)` followed by `Scale(-1)` gives the same numbers
  as setting the negated components.

---

## Item 5: side normals only when asked for

`TriangleGeometry3D.Calculate` works out three side normals and offsets
(three cross products, three square roots) for every triangle. Only
`ContactClipper3D.ClipToTriangle` uses them, through `GetSideNormal` and
`GetSideOffset`, and only when the triangle's face is the best direction.
Triangles the separating axis test rejects, and those with box-face or edge
contacts, never need them. `ClosestPoint` does not use them.

### `Narrowphase/TriangleGeometry3D.quorum`

New field, after `degenerate`:

```
    // True once the side normals and offsets have been worked out for the
    // loaded triangle. They are worked out the first time they are asked
    // for, since many triangles are rejected before they are needed.
    boolean sidesReady = false
```

In `Calculate`, the degenerate branch sets the sides to zero as now, and
ends with `sidesReady = true`. The rest of `Calculate`, before:

```
        normal:Normalize()
        planeOffset = normal:DotProduct(corner0)

        // The normal crossed with an edge lies in the triangle's plane, at a
        // right angle to the edge, and points into the triangle.
        sideNormal0:Set(normal):CrossProduct(edge0):Normalize()
        sideNormal1:Set(normal):CrossProduct(edge1):Normalize()
        sideNormal2:Set(normal):CrossProduct(edge2):Normalize()
        sideOffset0 = sideNormal0:DotProduct(corner0)
        sideOffset1 = sideNormal1:DotProduct(corner1)
        sideOffset2 = sideNormal2:DotProduct(corner2)
    end
```

After:

```
        normal:Normalize()
        planeOffset = normal:DotProduct(corner0)
        sidesReady = false
    end

    /*
    This action works out the side normals and offsets of a triangle that is
    not degenerate. The normal crossed with an edge lies in the triangle's
    plane, at a right angle to the edge, and points into the triangle.
    */
    private action CalculateSides
        sideNormal0:Set(normal):CrossProduct(edge0):Normalize()
        sideNormal1:Set(normal):CrossProduct(edge1):Normalize()
        sideNormal2:Set(normal):CrossProduct(edge2):Normalize()
        sideOffset0 = sideNormal0:DotProduct(corner0)
        sideOffset1 = sideNormal1:DotProduct(corner1)
        sideOffset2 = sideNormal2:DotProduct(corner2)
        sidesReady = true
    end
```

`GetSideNormal` and `GetSideOffset` each start with:

```
        if not sidesReady
            CalculateSides()
        end
```

`SideDistance` goes through both, so it needs no change. The values are
computed from the same normal and edges as before, so they are identical.
