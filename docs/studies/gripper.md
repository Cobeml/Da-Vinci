# Parallel-jaw gripper study

## Build plan

1. Freeze a three-part geometry contract: guide base and two symmetric sliding jaws. Each jaw has a fixed carriage/contact interface and an agent-designed graph of rectangular ribs.
2. Implement and independently test a 3D Euler–Bernoulli beam-frame solver. Evaluate pinch, payload, lateral and combined loads, nominal stress, contact displacement and compression buckling. Check exported STEP solids against the contract and actual BRep collisions at nine openings from 20 to 60 mm.
3. Run GPT-6 Astra with high reasoning and a larger output allowance, bounded by one $25 study budget. Archive proposals, failures, tool validations, policies, source commits and geometry through the existing Atlas/Git/GridFS services. Preserve all attempts and resume cached calls.
4. Generate a reusable member-sizing tool after initial feedback. Test it against independent analytic cases before reuse. Retrieve scoped prior outcomes with Atlas Vector Search and feed actual tool executions into later proposals.
5. Publish only after a passing candidate improves moving jaw mass by at least 15% over the conservative baseline. Replace the root gallery with interactive gripper models and opening controls; retain the sensor gallery at `/sensor`.

## Scope

This is a passive gripper mechanism study for an external opposed linear actuator. It does not design the motor, screw, controller or gripping-pad friction. The objective is moving jaw-pair mass; total three-part mass is reported separately. Nominal aluminium properties and ideal rigid beam joints are screening assumptions. The frame solver is not a continuum stress analysis of fillets, contacts or carriage bearings, and is not manufacturing certification.

The evaluator, load cases, geometry interfaces and acceptance limits remain fixed throughout the live study. The agent chooses rib connectivity, intermediate nodes, section sizes and extrusion depth within the declared domain; it does not rewrite its evaluator.
