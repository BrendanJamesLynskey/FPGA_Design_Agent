# Requirements readiness: NOT ready

Level **standard**; checklist: procedures/requirements-review/pre-build-review@sha256:c6081e7cd937; limits: {'max_rounds': 4, 'max_calls': 60, 'max_questions': 25}. Rounds used: 4. Model calls: 17.

**Stopped: the round limit (4) was reached with questions still open.** See `REQUIREMENTS_NEEDED.md`.

| Round | Questions asked | Answered | Probes | Reader agreement | Disagreements | Gaps |
|---|---|---|---|---|---|---|
| 1 | 2 | 1 | 12 | - | 0 | 0 |
| 2 | 8 | 6 | 13 | 46% | 5 | 2 |
| 3 | 1 | 1 | 13 | - | 0 | 0 |
| 4 | 1 | 1 | 13 | 92% | 1 | 0 |

A probe set can be too small to find the ambiguity that matters: the number of probes and their categories are in `build/requirements/readiness.json`. Two readers who agree have read the requirements the same way; they can share a misreading, which is why the third reader is a different model and why the user's confirmation of each requirement from its show-back packet is a separate field (`validated_by_user`), never inferred from agreement.
