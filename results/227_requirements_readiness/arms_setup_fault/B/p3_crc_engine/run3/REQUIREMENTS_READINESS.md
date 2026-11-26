# Requirements readiness: frozen

Level **standard**; checklist: procedures/requirements-review/pre-build-review@sha256:c6081e7cd937; limits: {'max_rounds': 4, 'max_calls': 60, 'max_questions': 25}. Rounds used: 2. Model calls: 9.

Frozen at 2026-11-26T16:21:58Z (version 1, hash `1f82de333d7d8b8245041973`): 30 requirements. Later stages read this set; a change returns to stage 0 and is recorded.

| Round | Questions asked | Answered | Probes | Reader agreement | Disagreements | Gaps |
|---|---|---|---|---|---|---|
| 1 | 6 | 4 | 12 | 50% | 1 | 5 |
| 2 | 0 | 0 | 0 | - | 0 | 0 |

A probe set can be too small to find the ambiguity that matters: the number of probes and their categories are in `build/requirements/readiness.json`. Two readers who agree have read the requirements the same way; they can share a misreading, which is why the third reader is a different model and why the user's confirmation of each requirement from its show-back packet is a separate field (`validated_by_user`), never inferred from agreement.
