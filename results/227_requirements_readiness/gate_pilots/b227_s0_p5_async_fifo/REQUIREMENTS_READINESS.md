# Requirements readiness: frozen

Level **standard**; checklist: procedures/requirements-review/pre-build-review@sha256:c6081e7cd937; limits: {'max_rounds': 4, 'max_calls': 60, 'max_questions': 25}. Rounds used: 3. Model calls: 17.

Frozen at 2026-11-26T17:25:57Z (version 1, hash `db913a16a8af450d9c76cf50`): 44 requirements. Later stages read this set; a change returns to stage 0 and is recorded.

| Round | Questions asked | Answered | Probes | Reader agreement | Disagreements | Gaps |
|---|---|---|---|---|---|---|
| 1 | 2 | 1 | 13 | 85% | 1 | 1 |
| 2 | 5 | 5 | 13 | 69% | 0 | 4 |
| 3 | 0 | 0 | 13 | 100% | 0 | 0 |

A probe set can be too small to find the ambiguity that matters: the number of probes and their categories are in `build/requirements/readiness.json`. Two readers who agree have read the requirements the same way; they can share a misreading, which is why the third reader is a different model and why the user's confirmation of each requirement from its show-back packet is a separate field (`validated_by_user`), never inferred from agreement.
