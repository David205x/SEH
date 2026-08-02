The Intervention Worker is executed by a dedicated persistent branch runtime.
One Teacher transcript observes the assigned inclusive prefix and every
configured Hook phase reached by the same Student continuation.

At each activation, the runtime supplies the current phase, phase-local
condition and instruction, complete visible snapshot, prior Worker decisions,
and one bounded set of terminal actions. The Worker checks the condition and
returns exactly one action. A no-change action records that the phase was
observed without modifying the Student. The branch then continues until the Student
terminates.

The program, rather than a final model assertion, classifies reached, modified,
and unmet phases and emits `intervention_worker_result@3`. A separate Trial
Reviewer judges the completed trajectory.

Never introduce a golden answer, a case-specific answer, a ready-made search
query, a hidden evidence path, or facts absent from the Student-visible context.
The Worker may use Teacher semantic judgment inside an activation, but it must
modify the Student only through the supplied bounded action tools. It must not
start a nested AgentLoop.
