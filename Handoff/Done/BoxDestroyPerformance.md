# BoxDestroy performance: last release against current

> **Status, 2026-10-15: a record.** The per-frame estimate was never confirmed with a benchmark run.

Snapshots: `snapshots/old.snapshot` (the last Quorum release) and
`snapshots/new.snapshot` (all physics changes since then), both taken on
2026-10-12 with the same task.

## Summary

- Measured: over runs of about the same length, total physics time fell from
  13.3 s to 8.5 s, about 1.6 times less.
- Estimated: the current build draws about 4 times as many frames, so it does
  about 6 times less physics work per frame. How this is estimated, and what
  could make it wrong, is explained below.

## Measured totals

Both runs are about 16 seconds, with similar total CPU time sampled (15.5 s
old, 14.2 s new). These are the sampled times, in milliseconds:

| | Old | New | Change |
|---|---|---|---|
| All physics (`Layer3D.TestForCollisions`) | 13,340 | 8,500 | 1.6 times less |
| Box against box | 7,720 (GJK) | 2,100 (`BoxBoxCollider`) | 3.7 times less |
| Creating `Vector3` objects | 2,340 | 100 | 23 times less |
| Contact solver | 2,260 | 3,140 | 1.4 times more |
| Broadphase overlap checks | 500 | 640 | 1.3 times more |
| Drawing (`Game.DrawAll`) | 1,140 | 4,620 | 4 times more |

As a share of each run:

| | Old | New |
|---|---|---|
| Physics | 86% | 60% |
| Drawing | 7% | 33% |
| GJK, the general collision test | 45% | 0.6% |
| Creating `Vector3` objects | 15% | under 1% |

Garbage collection fell from 2.0 collections a second, averaging 5.2 ms, to
0.74 a second, averaging 3.2 ms. Old-generation memory peaks at 68 MB instead
of 135 MB.

The causes:
- Every box pair used to go through the general GJK test. It now goes
  through the dedicated box collider, `BoxBoxCollider`.
- Temporary vectors are now reused instead of created on every call, which
  is also why garbage collection dropped.

The solver and broadphase take more total time in the new run because they
run once per frame and the new run has more frames (see below). Per frame,
both cost less.

## Estimated per frame

A sampling profile records how long each method ran in total, but not how
many frames there were. The number of frames can be estimated from drawing:

- Drawing time = drawing per frame × number of frames.
- Physics time = physics per frame × number of frames.
- So physics time ÷ drawing time = physics per frame ÷ drawing per frame. The
  number of frames cancels out.

If drawing one frame costs the same in both builds, then comparing physics ÷
drawing between the builds compares physics per frame. On that basis:

| Per frame (sampled time ÷ drawing time) | Old | New | Change |
|---|---|---|---|
| All physics | 11.7 | 1.84 | 6.4 times less |
| Box against box | 6.8 | 0.45 | 15 times less |
| Creating `Vector3` objects | 2.1 | 0.02 | about 100 times less |
| Contact solver | 2.0 | 0.68 | 3 times less |
| Broadphase | 0.44 | 0.14 | 3 times less |

Drawing took 4,620 ÷ 1,140 = about 4 times as long in the new run, so under
the same assumption, the new build drew about 4 times as many frames.

### What could make the estimate wrong

1. Drawing time may include waiting. The profiler counts time spent inside
   the graphics calls. If the faster build reaches the display's frame cap
   (vsync), the call that shows the frame waits, and the waiting is counted
   as drawing time without any extra frames being drawn. That would make the
   4 times and the 6 times too large.
2. The scenes may not draw the same amount. If the new build shows more
   boxes, or boxes in different places, drawing one frame costs a different
   amount, and the estimate shifts.
3. There is no second check. In the AllTerrainVehicle comparison, two
   separate per-frame costs agreed on the number of frames. BoxDestroy has
   only drawing to go on. `ClearScreen`, also called once per frame, went
   down (160 ms to 60 ms) instead of up, which does not fit 4 times as many
   frames.

The measured totals above do not depend on any of this. A fixed-length run
that reports its own frame count and frame times, like AllTerrainVehicle's
`benchmark` mode, would confirm or correct the per-frame numbers.

## Structure

The old version ran collision detection once per frame, outside the physics
step. The new version runs it inside each physics step, as Bullet does. With
one step per frame, the default, the amount of work is the same. It differs
only when a frame takes more than one step.
