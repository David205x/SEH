Role input:
{{role_input}}

Program-provided resource context:
{{resource_context}}

Use `candidate_trajectory_view` as the primary evidence and
`reference_observations` only to calibrate the expected mechanism behavior.
For each entered declared phase, independently assess the trace-visible trigger
inputs before judging its activation or fallback. Compare the resulting behavior
with the supplied MechanismSpec, then submit one conformance finding for this
Candidate rollout only.
