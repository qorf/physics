# Wheels Disappearance Issue - Diagnosis and Fixes

## Problem
Wheels appear on screen initially, then immediately disappear when the vehicle physics Update runs.

## Root Cause Analysis
The wheels disappear because they're being repositioned to their maximum suspension extension (approximately 0.88 units below their hard point), which places them off-screen or below the visible area.

This happens when the raycast doesn't detect the ground, causing the vehicle to think the wheels are not in contact.

## Fixes Applied

### 1. Array Initialization (Vehicle.quorum:31-40)
Added safety check to ensure the wheels array is initialized when the first wheel is added:
```quorum
if wheels = undefined
    Array<Suspension> temp
    wheels = temp
end
```

### 2. Raycast Safety Check (Vehicle.quorum:96-99)
Made raycast detection more robust:
```quorum
boolean hitDetected = false
if raycast not= undefined
    raycast:Cast(world, wheel:hardPointWS, rayEnd, chassis)
    hitDetected = raycast:hit
end
```

## Potential Issues and Debugging

### Issue 1: Raycast Not Finding Ground
**Symptom:** Wheels disappear and chassis falls

**Likely Cause:** The PhysicsRaycast may not be detecting the ground box collision

**To Debug:**
1. Add temporary debug output in UpdateWheel to check:
   - Is `raycast` null or non-null?
   - Is `raycast:hit` true or false?
   - What is the `raycast:fraction` value?

2. Check that the ground is properly created:
   - Ground should have a BOX collision shape
   - Ground should be in the Layer3D
   - Ground position should be (0, -0.5, 0)
   - Ground size should be 80x1x80

### Issue 2: Coordinate System Mismatch
**Symptom:** Wheels positioned incorrectly relative to ground

**Check:**
- Hard point Y should be ~0.83 for the front wheels (chassis at 1.25, connection at -0.42)
- Ray should go from Y=0.83 down to Y=-0.41
- Ground is at Y ∈ [-1, 0], so ray should hit the top surface at Y=0

### Issue 3: PhysicsRaycast Initialization
**Symptom:** Raycast object is null

**Current Status:** Object is declared but may not auto-instantiate in Quorum

**Current Mitigation:** Check `if raycast not= undefined` before using

## Recommended Next Steps

1. **Add Debug Output**
   ```quorum
   if (i = 0)  // Only output for first wheel
       output "Wheel 0: hard point Y = " + wheel:hardPointWS:GetY()
       output "Wheel 0: hit = " + hitDetected + ", fraction = " + raycast:fraction
   end
   ```

2. **Verify Ground Geometry**
   - Check that ground appears on screen
   - Check that ground doesn't move or disappear
   - Verify ground collision shape is correct

3. **Test Without Raycast**
   - Temporarily disable raycast and use fixed suspension length
   - If wheels appear at correct position, raycast is the problem
   - If wheels still don't appear, it's a different issue

## Expected Behavior When Fixed

When working correctly:
1. Wheels should appear on screen at initial positions
2. First Update should position wheels near the ground
3. Chassis should rest on suspended wheels
4. Wheels should not disappear
5. Mast and fork should be controllable

## Files Modified

- Vehicle.quorum - Array initialization and raycast safety
- SliderJoint3D.quorum (standard library) - Added ConfigureLinearMotor action
- Main.quorum - Disabled problematic camera setup
- Suspension.quorum - Tuned frictionSlip parameter
