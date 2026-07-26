# Controlled development loop

Wingman keeps development iteration separate from user conversations. The versioned task ledger is [DEVELOPMENT_TASKS.json](DEVELOPMENT_TASKS.json).

Each iteration should select one task, read its acceptance criteria, make the smallest safe change, run the listed verification command, and record the result. A human reviews changes before merge or deployment.

The loop must stop when tests fail repeatedly, credentials are required, a task needs a product decision, or a change would bypass ownership, privacy, safety, or application validation. It is not an autonomous runtime feature and it must never modify user conversations or saved data.
