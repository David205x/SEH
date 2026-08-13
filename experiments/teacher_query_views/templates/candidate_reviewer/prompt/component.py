"""Shadow Candidate Reviewer prompt assembled from formal semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.teacher_query_views.prompt import ShadowCandidateReviewerPrompt
from search_harness.evolution.research.roles.prompting import load_prompt_spec


def build(config: dict[str, Any], context: Any, tools: Any):
    del context, tools
    if config:
        raise ValueError("shadow Candidate Reviewer prompt does not accept config")
    formal_root = (
        Path(__file__).resolve().parents[5]
        / "harness_templates"
        / "teacher"
        / "candidate_reviewer"
        / "prompt"
    )
    formal = load_prompt_spec(
        formal_root,
        {"instructions": "system.md", "user_template": "user.md"},
    )
    instructions = formal.instructions.replace(
        "Treat the supplied compiler\nvalidation and conformance facts as authoritative within their stated scope;\ndo not override their recorded findings. They establish static validity and the\nreported implementation-conformance evidence, but do not by themselves prove",
        "Treat the stated Candidate Validation pass and supplied conformance facts\nas authoritative within their stated scope; do not override their recorded\nfindings. They establish static validity and reported implementation-conformance\nevidence, but do not by themselves prove",
    ).replace(
        "2. Call `list_candidate_changes` before making a recommendation.\n3. Call `get_candidate_harness_diff` to verify that the candidate implements the\n   supplied mechanism rather than a different behavior.\n4. Use `get_candidate_case` for the mechanism's cited or target-relevant cases\n   visible in the change list and for every gain or loss that is decisive to your\n   recommendation.\n5. Call `get_paired_student_trajectory` only when the case record cannot settle\n   whether a decisive change follows from the mechanism, its applicability, or a\n   regression. Do not read every trajectory by default.",
        "2. Call `list_candidate_changes` before making a recommendation. Its\n   default changed-first view omits unchanged rows; request an unchanged boundary\n   only when it is material.\n3. Call `get_candidate_harness_diff`. Small diffs are complete; if a large diff\n   returns only a directory, inspect each material changed path.\n4. Use `get_candidate_case` for target-relevant cases and decisive gains or losses.\n   Select replicates from its paired outcome map instead of guessing from a case\n   aggregate.\n5. Inspect at least one target-relevant paired trajectory. When improved examples\n   exist, inspect a truly improved replicate pair; when regressed examples exist,\n   inspect a truly regressed pair. A single trajectory may satisfy more than one\n   obligation. Do not read every trajectory by default.",
    ).replace("a visible positive\n  positive opportunity", "a visible positive opportunity")
    if instructions == formal.instructions:
        raise ValueError("formal Candidate Reviewer prompt changed unexpectedly")
    instructions += (
        "\n\n## Shadow Candidate evidence view\n\n"
        "The initial brief contains each aggregate only once. Candidate case and "
        "trajectory tools are paired delta views over unchanged underlying "
        "Artifacts. Behavior views preserve actual Student tool evidence, parsed "
        "actions, Hook decisions and effective context changes while removing "
        "duplicated cumulative snapshots and provider metadata. Base conclusions "
        "only on displayed facts; do not infer omitted raw reasoning. Preserve the "
        "Use `get_candidate_trajectory_text` only when a displayed preview is "
        "insufficient to decide a trigger, grounding, or attribution question. "
        "Do not expand long text by default. Preserve the "
        "formal revision boundary: `revise` is valid only when one bounded "
        "obligation can resolve the Candidate. Do not bundle multiple independent "
        "implementation changes, change the declared model profile, or invent a "
        "deterministic semantic pre-filter unless the supplied MechanismSpec already "
        "authorizes it. When observed harm and disproportionate cost require "
        "independent redesigns, use `reject`; when missing evidence alone blocks the "
        "decision, route only that obligation to `evidence`."
    )
    return ShadowCandidateReviewerPrompt(
        instructions=instructions,
        user_template="{{role_input}}\n{{resource_context}}",
        continuation_templates=formal.continuation_templates,
    )
