# Moving Model2's reporting into Item3D

> **Status, 2026-10-15: done.** Applied to the library and used by Layer3D. One small item is still open: `Model.Load(blueprint, matrix)` should call `NotifyMoved()`.

Written 2026-10-14. A proposal for review. **Nothing has been changed.**

Library paths are relative to
`quorum-language/Quorum/Library/Standard/Libraries`.

## What moves where

Model2, in AllTerrainVehicle, reports four kinds of change to its layer.
This moves that reporting into `Item3D`, so every item reports, and gives
`Layer3D` four actions that receive the reports and do nothing. A layer that
keeps its own records, such as TreeLayer3D, fills them in.

| Report | Model2 today | Proposed |
|---|---|---|
| Moved, turned or scaled | 9 overrides, then `ItemMoved` | `Item3D`: one line at the end of the same 9 actions |
| Size changed | 5 overrides, then `ItemResized` | `Item3D`: one line at the end of the same 5 actions |
| Physics turned on or off | `EnablePhysics` override | `Item3D.EnablePhysics`: one line at the end |
| Woke or fell asleep | `ReportingPhysicsProperties3D` | `PhysicsProperties3D.Simulate`: a few lines (see below) |

"Layer" here means `Layer3D`. `Item3D` holds its layer as a `Layer3D`, and the
base `Layer` class knows nothing about `Item3D`.

## A third file is needed: `PhysicsProperties3D`

You asked for changes to `Layer3D` and `Item3D` only. Waking and sleeping
can't be caught there. Most wakes start inside `PhysicsProperties3D`: its
velocity setters and its force, torque and impulse actions call
`Simulate(true)` on the properties, not on the item. `Item3D.Simulate` only
sees the solver's calls and direct calls. That is why Model2 needed
`ReportingPhysicsProperties3D`.

The options are:

1. **Change `PhysicsProperties3D.Simulate`** (proposed below). It is a few
   lines, and it catches every wake and sleep.
2. **Don't report waking and sleeping.** TreeLayer3D would keep checking
   its sleeping bodies once per frame, as it did before Model2 (about 340
   samples in that run).

## Part A: `Game/Layer3D.quorum`

Four new actions, after `DisableItemLighting`. They do nothing.

```
    /*
    This action is called by an item on this layer, or one of its
    children, the first time it moves, turns or changes scale after its
    move report was cleared with SetReportedMove(false). It does nothing
    here. A layer that keeps its own record of where its items are, such as
    one that culls, can fill it in.

    Attribute: Parameter item The item that moved.
    */
    action ItemMoved(Item3D item)
    end

    /*
    This action is called by an item on this layer, or one of its
    children, when its width, height or depth changes, such as when a model
    finishes loading. It does nothing here.

    Attribute: Parameter item The item whose size changed.
    */
    action ItemResized(Item3D item)
    end

    /*
    This action is called by an item on this layer when its physics is
    turned on or off. It does nothing here.

    Attribute: Parameter item The item whose physics changed.
    */
    action ItemPhysicsChanged(Item3D item)
    end

    /*
    This action is called by an item on this layer when physics starts or
    stops simulating it, that is, when it wakes or falls asleep. It does
    nothing here.

    Attribute: Parameter item The item that woke or fell asleep.
    */
    action ItemSimulationChanged(Item3D item)
    end
```

The names follow the existing `EnableItemLighting` style. TreeLayer3D's
`PhysicsChanged` and `BodySimulationChanged` would be renamed to
`ItemPhysicsChanged` and `ItemSimulationChanged` to override these.

## Part B: `Interface/Item3D.quorum`

### New field, after `Layer3D layer = undefined` (line 89)

```
    // True after this item has told its layer it moved, until the layer
    // clears it with SetReportedMove(false). This way the layer hears about
    // an item once, however many times it moves before the layer handles it.
    boolean moveReported = false
```

### New actions, after `GetLayer`

```
    /*
    This action tells the item's layer that its position, rotation or scale
    has changed, unless it already has and the layer has not cleared the
    report yet. The item calls it itself whenever it moves. Code that
    changes GetTransform() directly should call it too.
    */
    action NotifyMoved
        if moveReported or layer = undefined
            return now
        end
        moveReported = true
        layer:ItemMoved(me)
    end

    /*
    This action returns true if the item has reported a move that its layer
    has not cleared yet.

    Attribute: Returns True if a move report is waiting.
    */
    action HasReportedMove returns boolean
        return moveReported
    end

    /*
    This action sets whether the item has a move report waiting. A layer
    sets it back to false once it has handled the move, so the item reports
    its next move.

    Attribute: Parameter value False once the move has been handled.
    */
    action SetReportedMove(boolean value)
        moveReported = value
    end

    /*
    This action tells the item's layer that physics started or stopped
    simulating the item. The item's PhysicsProperties3D calls it.
    */
    action SimulationChanged
        if layer not= undefined
            layer:ItemSimulationChanged(me)
        end
    end

    /*
    This action tells the item's layer that its size changed.
    */
    private action NotifyResized
        if layer not= undefined
            layer:ItemResized(me)
        end
    end
```

### `NotifyMoved()` as the last line of these 9 actions

None of them has an early `return now`, so the last line is always reached.

| Action | Line |
|---|---|
| `SetOffsetX(number)` | 638 |
| `SetOffsetY(number)` | 672 |
| `SetOffsetZ(number)` | 706 |
| `SetOffset(number, number, number)` | 743 |
| `SetRotationTransform(Matrix4)` | 1041 |
| `Rotate(Vector3, number, boolean)` | 1605 |
| `SetYawPitchRoll(number, number, number)` | 2032 |
| `Scale(Vector3, boolean)` | 2128 |
| `SetScale(number, number, number, boolean)` | 2249 |

Every other way of moving goes through one of these:

- `SetX`, `SetY`, `SetZ`, `SetPosition`, `MoveX`, `MoveY`, `MoveZ` and both
  `Move` actions end in a `SetOffset` action.
- `SetOffset(Vector3)` calls `SetOffset(number, number, number)`.
- The other `Rotate` overloads, and `RotateAround`, which goes through
  `RotateItemArray`, end in `Rotate(Vector3, number, boolean)` and
  `SetOffset`.
- The other `Scale` and `SetScale` overloads call the two listed.
- The physics copy-back, `SetScreenPositionFromPhysicsPosition`, ends with
  `SetOffset(offsetX, offsetY, offsetZ)`, so it needs no line of its own.
- A parent moving its children calls their `SetOffset` and `Rotate`.

For example, `SetOffsetX` becomes:

```
    action SetOffsetX(number xAmount)
        ... unchanged ...

        integer counter = 0
        repeat children:GetSize() times
            children:Get(counter):SetOffsetX(x + xAmount)
            counter = counter + 1
        end
        NotifyMoved()
    end
```

### `NotifyResized()` as the last line of these 5 actions

| Action | Line |
|---|---|
| `SetWidth(number)` | 304 |
| `SetHeight(number)` | 326 |
| `SetDepth(number)` | 348 |
| `SetDimensions(number, number, number)` | 372 |
| `SetDimensions(Vector3)` | 400 |

Loading a model goes through `SetDimensions(Vector3)`, so a model that
finishes loading reports its size.

### `EnablePhysics` (line 2626)

```
    action EnablePhysics(boolean flag)
        ... unchanged ...

        if layer not= undefined
            layer:ItemPhysicsChanged(me)
        end
    end
```

### `SetLayer` (line 2360): clear the report when the layer changes

```
    action SetLayer(Layer3D parentLayer)
        layer = parentLayer
        moveReported = false
        ... unchanged ...
```

Without this, an item that moved on a plain Layer3D would keep its report
set forever, since Layer3D never clears it. Moved to a TreeLayer3D later, it
would never report again.

## Part C: `Game/Physics/PhysicsProperties3D.quorum`, `Simulate`

Before:

```
    action Simulate(boolean flag)
        if flag
            if not simulated
                simulated = true
                sleepTime = 0
            end
        else
            simulated = false
            sleepTime = 0
            linearVelocity:SetZero()
            angularVelocity:SetZero()
            force:SetZero()
            torque:SetZero()
        end
    end
```

After:

```
    action Simulate(boolean flag)
        boolean before = simulated
        if flag
            if not simulated
                simulated = true
                sleepTime = 0
            end
        else
            simulated = false
            sleepTime = 0
            linearVelocity:SetZero()
            angularVelocity:SetZero()
            force:SetZero()
            torque:SetZero()
        end

        // Tell the item, and through it the item's layer, when the body
        // wakes or falls asleep.
        if before not= simulated and item not= undefined
            item:SimulationChanged()
        end
    end
```

Only an actual change is reported. Putting an asleep body to sleep again
still clears its speeds and forces, as before, but reports nothing.

## What is left out, and why

- **`Model.Load(blueprint, matrix)`** sets the transform directly, with
  `GetTransform():Set(matrix)`, and is in `Model`, which this proposal does
  not change. It then calls `SetDimensions`, which reports a resize, and
  TreeLayer3D re-adds a resized item using its current transform, so the
  move is still picked up. The exception is an item whose bounds were given
  with `SetRenderBounds`, which ignores resizes. Adding `NotifyMoved()` after
  that line in `Model.Load` would close the gap; it is one line, for later.

## Cost on a plain Layer3D

Every move now calls `NotifyMoved`. On a plain Layer3D, the first move sets
`moveReported`, calls the empty `ItemMoved`, and nothing ever clears the
flag, so every later move returns at the flag check: one boolean test.
Resizes, physics on or off, and wake or sleep changes are rare. The cost
should not be measurable. A before-and-after benchmark in AllTerrainVehicle
with a plain Layer3D would confirm it.

## Follow-ups in AllTerrainVehicle, once this is in

- **TreeLayer3D:**
  - Rename `PhysicsChanged` and `BodySimulationChanged` to
    `ItemPhysicsChanged` and `ItemSimulationChanged`.
  - Use `HasReportedMove` and `SetReportedMove` instead of casting to Model2.
  - Remove `silentItems` and `CheckSilentBodies`: every item, including
    `Terrain`, now reports.
  - Remove the render-tree move in the copy-back: the copy-back ends in
    `SetOffset`, which reports.
- **Delete** `Model2.quorum` and `ReportingPhysicsProperties3D.quorum`.
- **Main:** go back to `Model`.
