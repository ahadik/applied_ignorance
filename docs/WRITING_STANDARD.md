# Document writing rules

Use the [ASD-STE100 skill](../tools/ste/SKILL.md) for project documents outside `data/`.
The user selected this skill on September 10, 2026.

Use strict mode for procedures and agent instructions.
Use the skill's prose mode for explanations and reports.
Do not apply the skill to existing or future files under `data/`.

1. Preserve every fact, condition and requirement.
2. Preserve uncertainty, such as “may” and “could”.
3. Use one instruction per sentence.
4. Use no more than 20 words in an instruction.
5. Use no more than 25 words in a descriptive sentence.
6. Use active voice when the actor matters.
7. Keep one topic in each paragraph.
8. Use no more than six sentences in each paragraph.
9. Use a list for three or more steps.
10. Preserve exact commands, identifiers, numbers and source quotations.

Run the local checker after document changes:

```sh
python3 -m fantasy_agent check_docs
python3 -m fantasy_agent check_docs --json
```

The default command checks root documents, `docs/` and `tests/`.
It excludes data files and third-party skill files.
It reports vocabulary, possible passive voice and compound tenses as advisory findings.
Review these findings manually.
For example, “read-only” describes a property rather than passive voice.

The checker treats synonym findings as advisory under the skill's prose mode.
Some project terms describe different operations:

| Term | Project meaning |
|---|---|
| Check | Inspect a condition. |
| Validate | Test a proposal against its schema, evidence and rules. |
| Verify | Compare observed platform state with the intended result. |
| Collect | Read provider data and save its evidence. |
| Reconcile | Compare records and account for differences. |
| Snapshot | A saved copy of data at a stated time. |
| Proposal | A suggested action that does not prove execution. |

The checker uses patterns rather than a full language parser.
It does not prove that a revision preserves meaning.
It does not check the official ASD word dictionary.
Do not describe a passing result as certified ASD-STE100 compliance.

The repository includes skill version 0.4.0 and its linter under `tools/ste/`.
The [upstream repository](https://github.com/danyuchn/asd-ste100-skill) supplies the skill under the MIT license.
The local copy lets both Macs use the same rules without another Python package.
