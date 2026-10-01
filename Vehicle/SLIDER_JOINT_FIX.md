# SliderJoint3D Motor Control - Missing Action Fixed

## Issue Found

The Quorum `SliderJoint3D` class in the standard library was missing the `ConfigureLinearMotor` action, which is essential for controlling the linear motor that drives the fork lift mechanism.

**File:** `/Users/stefika/Repositories/quorum-language/Quorum/Library/Standard/Libraries/Game/Physics/Joints/SliderJoint3D.quorum`

**Impact:** Without this action, the fork carriage cannot be raised or lowered because the lift mechanism relies on a linear motor controlled by `ConfigureLinearMotor`.

## Solution Implemented

Added the `ConfigureLinearMotor` action to SliderJoint3D with the following signature:

```quorum
action ConfigureLinearMotor(boolean enabled, number targetVelocity, number maxForce)
    poweredLinMotor = enabled
    targetLinMotorVelocity = targetVelocity
    maxLinMotorForce = maxForce
    if enabled
        accumulatedLinMotorImpulse = 0
    end
end
```

## Parameters

- **enabled** (boolean): Whether to enable the linear motor
- **targetVelocity** (number): The desired velocity along the slider axis
- **maxForce** (number): The maximum force the motor can apply

## Behavior

1. Sets `poweredLinMotor` to enable/disable the motor
2. Sets `targetLinMotorVelocity` to the desired velocity
3. Sets `maxLinMotorForce` to the force limit
4. Resets the accumulated impulse accumulator when the motor is first enabled (prevents sudden jerks)

## Correspondence with Bullet

This action maps to three separate Bullet methods in btSliderConstraint:
- `setPoweredLinMotor(bool onOff)` → `enabled` parameter
- `setTargetLinMotorVelocity(btScalar velocity)` → `targetVelocity` parameter
- `setMaxLinMotorForce(btScalar force)` → `maxForce` parameter

## Usage in Main.quorum

The forklift demo uses this action to lift and lower the cargo:

```quorum
// Lift the fork carriage upward
forkSlider:ConfigureLinearMotor(true, 1.0, 45)

// Stop the lift
forkSlider:ConfigureLinearMotor(false, 0, 45)
```

## Related Actions

HingeJoint3D already has the corresponding `EnableAngularMotor` action for the mast hinge, which works the same way:

```quorum
action EnableAngularMotor(boolean enableMotor, number targetVelocity, number maxMotorImpulse)
```

## Testing

When the vehicle demo runs, test the following:
- Shift+Up/Down should smoothly raise/lower the fork carriage
- The lift should respect the maxForce limit and not behave violently
- The lift should stop when the upper/lower limits are reached
