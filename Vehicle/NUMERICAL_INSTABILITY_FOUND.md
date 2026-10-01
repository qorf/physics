# Numerical Instability Issue Found

## Problem Identified

Debug output shows a clear pattern of failure:

**Frames 1-4 (WORKING):**
```
Raycast hit: true
Hard point Y: 0.8300000000000001
```

**Frames 5+ (FAILING):**
```
Raycast hit: false
Hard point Y: -8.179257697145882E10  (huge negative number!)
```

Then the values escalate exponentially to even larger magnitudes (10^12, 10^18, 10^21).

## Root Cause

The hard point Y coordinate calculation is becoming corrupted after the initial frames. This is likely due to:

1. **Physics Simulation Instability**: The chassis is falling rapidly, and the physics engine's internal state may be accumulating errors
2. **Transform Corruption**: The `chassisTransform:Transform(wheel:hardPointWS)` calculation is producing invalid values
3. **Lack of Contact**: Once suspension contact is lost, the chassis accelerates downward, and numerical errors compound

## Fixes Applied

1. **Sanity Checks**: Added bounds checking to prevent invalid coordinates (< -1000 or > 1000) from being used
2. **Raycast Safety**: Raycast is skipped if hard point is invalid
3. **Position Safety**: Wheels are not repositioned if the calculated position is invalid
4. **Return Statement Fixes**: Fixed `return now` to just `return` in early-exit paths

## Why Raycast Fails After Frame 4

The raycast hits correctly for the first 4 frames because:
- Chassis is resting on wheels
- Hard point coordinates are valid
- Raycast can detect the ground

After frame 4, one of these breaks:
- The chassis has fallen too far or moved unexpectedly
- The hard point calculation produces NaN/infinity values
- The coordinate system becomes degenerate

## Recommended Investigation

To determine the real cause, add logging to check:

```quorum
output "Chassis Y: " + chassis:GetY()
output "Chassis velocity Y: " + chassis:GetLinearVelocity():GetY()
output "Suspension force (wheel 0): " + wheels:Get(0):suspensionForce
```

This will show:
- Is the chassis falling continuously?
- What is the suspension force being applied?
- When does it stop being applied?

## Potential Solutions

### Option 1: Improve Physics Stability
- Check if suspension parameters are too extreme
- Verify chassis mass and inertia are reasonable
- Ensure time step is not too large

### Option 2: Add Fallback Positioning
- If raycast fails, position wheel at rest length below hard point
- This would keep wheels visible even if raycast breaks

### Option 3: Investigate Transform Calculation
- Add detailed logging of the transform matrix values
- Check if matrix is becoming singular or nearly singular
- Verify PhysicsPosition3D:Transform is implemented correctly

## Current Safeguards

The code now protects against crashes by:
- Skipping raycast if hard point is invalid (> ±1000)
- Not positioning wheels at invalid coordinates
- Logging warnings when hard points exceed bounds

This prevents the wheels from disappearing into infinity, but the underlying issue remains.
