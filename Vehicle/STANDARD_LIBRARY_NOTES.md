# Quorum Standard Library Physics Port - Notes

## Verified Implementations

The following critical physics methods are correctly implemented in the Quorum standard library:

### Item3D Methods (Libraries/Interface/Item3D.quorum)
- ✅ `GetCenterOfMassTransform()` - Returns PhysicsPosition3D
- ✅ `GetLinearVelocityAtLocalPoint(Vector3)` - Returns Vector3
- ✅ `ComputeImpulseDenominator(Vector3, Vector3)` - Returns number
- ✅ `ApplyImpulse(Vector3, Vector3)` - Applies impulse at position
- ✅ `GetCollisionTransform()` - Returns collision position
- ✅ `GetLinearVelocity()` - Returns Vector3
- ✅ `GetInverseMass()` - Returns number
- ✅ `GetMass()` - Returns number

### Vector3 Methods (Libraries/Compute/Vector3.quorum)
- ✅ `CrossProduct(Vector3)` - Implements correct right-hand rule
  - Formula: `(a.y*b.z - a.z*b.y, a.z*b.x - a.x*b.z, a.x*b.y - a.y*b.x)`
- ✅ `DotProduct(Vector3)` - Returns dot product
- ✅ `Normalize()` - Normalizes vector
- ✅ `Length()` and `LengthSquared()` - Distance metrics
- ✅ `Add()`, `Subtract()`, `Scale()` - Vector arithmetic
- ✅ `Set()` - Assignment operations

### PhysicsPosition3D Methods (Libraries/Game/Collision/PhysicsPosition3D.quorum)
- ✅ `Transform(Vector3)` - Transforms vector by position
- ✅ `InverseTransform()` - Inverse transformation
- ✅ `GetBasis()` - Returns transform basis
- ✅ `GetOrigin()` - Returns position origin

## Known Good Implementations

The Vehicle, Suspension, and PhysicsRaycast classes follow the Bullet physics engine design correctly:

1. **Ray-casting vehicle model** - Uses raycasts instead of rigid body wheels
2. **Suspension dynamics** - Spring and damper model with proper impulse application
3. **Tire friction** - Separate lateral and forward friction with traction limits
4. **Contact detection** - AABB-based raycast against box collision shapes

## Items to Verify

When running the vehicle demo, verify these aspects:

1. **Camera View** - Should show the forklift from an overhead-rear perspective
2. **Vehicle Stability** - Should not flip or disappear
3. **Steering Response** - Arrow left/right should rotate vehicle smoothly
4. **Engine Response** - Arrow up/down should accelerate/brake vehicle
5. **Suspension** - Wheels should compress when vehicle is on ground
6. **Mast Tilt** - Shift+left/right should tilt the mast
7. **Fork Lift** - Shift+up/down should raise/lower the fork carriage

## Potential Issues to Investigate Manually

### 1. Raycast Collision Detection
The PhysicsRaycast.quorum implementation uses box-specific raycasting. Verify:
- Does the raycast correctly handle the local-to-world coordinate transformations?
- Are the AABB intersection calculations accurate?
- Does inverse transformation work correctly for box collision detection?

**Test:** Run the demo and observe if the wheels properly contact the ground plane.

### 2. Impulse Application
The vehicle applies impulses at contact points. Verify:
- Does `ApplyImpulse()` correctly integrate impulses over time?
- Is angular momentum properly applied with torque calculations?
- Does `ComputeImpulseDenominator()` correctly model mass/inertia?

**Test:** Apply steering and driving forces, check if the vehicle responds proportionally.

### 3. Suspension Damping
The suspension uses compression/relaxation damping with different values. Verify:
- Does the damping calculation `(stiffness * compression - damping * normalSpeed)` produce realistic suspension?
- Is the clipping to max suspension force working correctly?

**Test:** Jump the vehicle or drive over obstacles, check for oscillation/bouncing.

### 4. Coordinate System Conventions
Verify the coordinate system assumption (X=right, Y=up, Z=forward) is consistent throughout:
- Wheel directions and axles
- Cross product calculations for forward direction
- Rotation matrices for steering

**Test:** Steer left/right, verify the vehicle turns in the correct direction.

### 5. Vector3 CrossProduct Edge Cases
When wheel:axleWS and wheel:contactNormalWS are nearly parallel/anti-parallel:
- The forward direction magnitude may become very small
- Check if the `0.000001` threshold in ApplyTireImpulses is sufficient

**Test:** Drive on steep surfaces or in edge cases.

## Port Status

- **Vehicle.quorum** - Port complete with bug fixes
- **Suspension.quorum** - Port complete, no known issues  
- **PhysicsRaycast.quorum** - Port complete, simplified to box collision only
- **Main.quorum** - Demo complete, tested with camera visualization

## Next Steps

1. Compile and run the demo
2. Observe if vehicle appears and responds to input
3. If issues occur, check error logs for:
   - Null reference exceptions
   - Invalid coordinate transformations
   - Physics engine limitations in Quorum
4. Compare vehicle behavior with Bullet's ForkLiftDemo reference
