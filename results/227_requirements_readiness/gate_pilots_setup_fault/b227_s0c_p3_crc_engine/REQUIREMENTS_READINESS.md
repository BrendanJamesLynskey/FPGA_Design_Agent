# Requirements readiness: NOT ready

Level **standard**; checklist: procedures/requirements-review/pre-build-review@sha256:c6081e7cd937; limits: {'max_rounds': 4, 'max_calls': 60, 'max_questions': 25}. Rounds used: 1. Model calls: 5.

**Stopped: no answer was available for the open questions.** See `REQUIREMENTS_NEEDED.md`.

| Round | Questions asked | Answered | Probes | Reader agreement | Disagreements | Gaps |
|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 12 | 83% | 1 | 1 |

A probe set can be too small to find the ambiguity that matters: the number of probes and their categories are in `build/requirements/readiness.json`. Two readers who agree have read the requirements the same way; they can share a misreading, which is why the third reader is a different model and why the user's confirmation of each requirement from its show-back packet is a separate field (`validated_by_user`), never inferred from agreement.
