# Build a local Telegram wingman agent with a web administration interface

The completed application is Wingman 5.3.0. This document describes the product requirements that define the implementation.

The current implementation also includes controlled model memory and planning tools, memory proposals, source-linked notes, rolling conversation summaries, retrieval inspection, a responsive dashboard, editable context guidance, local settings editing, JSON import and export, backups, lifecycle controls, port fallback, temporary attachment handling, and release diagnostics.

You are building a complete but intentionally small self-hosted application.

The application is a private relationship wingman. A user talks to it through Telegram about someone they like. It remembers useful information, keeps track of places, dates, preferences, observations, ideas, and important events. It later uses that knowledge to provide thoughtful advice and suggestions.

The application must run on one Linux machine. It must use the OpenAI API for the language model and embeddings.

Do not make this project more ambitious than necessary. Favor a reliable, understandable monolith over distributed systems, multiple agents, microservices, complex frameworks, or unnecessary abstractions.

## Primary success criteria

The completed project must allow me to do the following.

1. Run one command on Linux to start the application.

2. Start the Telegram bot and local web interface together.

3. Automatically open the web interface in the default browser when possible.

4. Talk naturally to the bot through Telegram.

5. Save useful memories through visible Telegram memory cards.

6. Delete a memory by pressing a button under its Telegram card.

7. Review, add, edit, delete, and organize memories through the web interface.

8. Review the Telegram conversation history through the web interface.

9. Inspect the context supplied to the model for individual turns.

10. Inspect model requests, model responses, tool calls, retrieval results, token usage, latency, and errors.

11. Configure Telegram and OpenAI credentials through the web interface.

12. Pause, resume, restart, and stop the Telegram bot through the web interface.

13. Update the application by pulling the latest version from its configured Git repository.

14. Preserve data across application restarts.

15. Run safely as a private application for one owner.

## Product definition

The assistant should feel like a thoughtful friend rather than a database interface.

It should support conversations such as this.

```text
User

I found a restaurant called Casa Verde. I think Penelope might like it.

Bot

That sounds worth keeping. Do you know the address?

User

Yes, 125 Main Street.

Bot

Nice. What made you think she would enjoy it?

User

It looks quiet and romantic.

Bot

That sounds like a good option for a relaxed date.

Bot memory card

📍 Casa Verde

125 Main Street
Quiet and romantic
Possible date place for Penelope

[Delete]
```

Several weeks later, this should be possible.

```text
User

Penelope finished her exams. I want to take her somewhere relaxing. Where should we go?

Bot

What about Casa Verde? You saved it a few weeks ago because it looked quiet and romantic. That seems suitable after a stressful exam period.
```

The assistant should also support observations and uncertain inferences.

```text
User

Penelope posted a quote from Solaris on her story.

Bot

Interesting. That might mean she likes science-fiction novels, although one post is not enough to be certain.

Bot memory card

📖 Penelope shared a quote from Solaris

[Delete]

Bot memory card

💭 Penelope may like science-fiction novels

Based on her Solaris story

[Confirm] [Delete]
```

The system must distinguish confirmed facts, observations, and inferences.

## Explicit non-goals

Do not implement any of the following in the first version.

- Instagram integration
- Instagram scraping
- Social media account access
- Web shopping
- Restaurant discovery from the internet
- Product searches
- Booking systems
- Restaurant reservations
- Map provider integration beyond a basic address link
- Automatic messages to the person being discussed
- Voice messages
- Image analysis
- Multiple agents
- Multiple romantic profiles
- A skill or plugin system
- Autonomous browsing
- Graph databases
- GraphRAG
- Fine-tuning
- Mobile applications
- Cloud deployment automation
- Kubernetes
- Microservices
- Redis unless a concrete need appears
- Celery unless a concrete need appears

Do not add a feature simply because it might be useful later.

## Technical assumptions

Use these defaults unless an existing repository already establishes a different compatible stack.

- Python 3.12
- FastAPI
- Uvicorn
- SQLAlchemy 2
- Alembic
- PostgreSQL with pgvector
- SQLite fallback for simple local development and tests
- Pydantic 2
- OpenAI Python SDK
- OpenAI Responses API
- A maintained Python Telegram framework such as aiogram
- Jinja templates with HTMX for the web interface
- Minimal vanilla JavaScript
- Bootstrap or a similarly small CSS framework
- Pytest
- Ruff
- MyPy
- Docker Compose for optional PostgreSQL startup
- A local process supervisor implemented inside the application where practical

Avoid React, Vue, Next.js, Node build pipelines, or a separate frontend service. The interface should be server-rendered and simple to maintain.

## Repository behavior

First inspect the repository.

If it is empty, initialize the complete project.

If it already contains code, preserve its conventions where reasonable and make surgical changes.

Do not replace working infrastructure without a clear reason.

Before writing code, create or update these files.

```text
README.md
ARCHITECTURE.md
IMPLEMENTATION_PLAN.md
SECURITY.md
.env.example
```

Record important decisions in `ARCHITECTURE.md`.

Record the implementation phases and completed work in `IMPLEMENTATION_PLAN.md`.

Do not only create a plan. Implement the application.

## Proposed project structure

Use approximately this structure.

```text
wingman/
    __init__.py
    main.py
    cli.py
    config.py
    logging_config.py

    agent/
        __init__.py
        orchestrator.py
        context_builder.py
        prompts.py
        schemas.py
        model_client.py
        model_router.py
        token_budget.py

    telegram/
        __init__.py
        bot.py
        handlers.py
        callbacks.py
        renderers.py
        lifecycle.py

    web/
        __init__.py
        app.py
        routes/
            dashboard.py
            conversations.py
            memories.py
            places.py
            events.py
            agent_runs.py
            settings.py
            system.py
        templates/
        static/

    database/
        __init__.py
        base.py
        session.py
        models.py
        repositories/
        migrations/

    retrieval/
        __init__.py
        query_builder.py
        search.py
        ranking.py
        embeddings.py

    services/
        __init__.py
        memory_service.py
        place_service.py
        event_service.py
        reminder_service.py
        conversation_service.py
        summary_service.py
        settings_service.py
        system_service.py

    tools/
        __init__.py
        schemas.py
        executor.py
        registry.py

    workers/
        __init__.py
        reminder_worker.py
        maintenance_worker.py

    tests/
        unit/
        integration/
        conversation_cases/

scripts/
    install.sh
    start.sh
    stop.sh
    restart.sh
    update.sh

docker-compose.yml
pyproject.toml
README.md
ARCHITECTURE.md
IMPLEMENTATION_PLAN.md
SECURITY.md
.env.example
```

Keep the final structure as small as practical. Do not create empty abstraction layers.

## Command-line experience

Provide a command named `wingman`.

The installation instructions should make this possible.

```bash
wingman start
```

The following commands are required.

```bash
wingman start
wingman stop
wingman restart
wingman status
wingman update
wingman doctor
```

### Start behavior

`wingman start` must do the following.

1. Validate configuration.

2. Initialize or migrate the database.

3. Start the FastAPI web server.

4. Start the Telegram bot.

5. Start the reminder worker.

6. Open the web interface in the default browser unless `--no-browser` is provided.

7. Print the local web address.

8. Keep running in the foreground by default so logs remain visible.

Support this option.

```bash
wingman start --daemon
```

Daemon mode may use a PID file and log files. Keep the implementation straightforward.

### Update behavior

`wingman update` must do the following.

1. Check whether the working directory has uncommitted changes.

2. Refuse to overwrite uncommitted changes.

3. Show the current branch and remote.

4. Run a safe fast-forward-only Git pull.

5. Install updated Python dependencies.

6. Run database migrations.

7. Restart the application if it was running.

The same update operation should be available through the web interface.

Never run arbitrary shell commands supplied through a web request.

## Authentication and access

This application is intended for one owner.

Implement local web authentication with a password.

Requirements include

- Password hash stored securely
- Secure session cookie
- CSRF protection for modifying actions
- Rate limiting for login attempts
- Web interface bound to `127.0.0.1` by default
- Clear warning before binding to a public interface
- Telegram allowlist containing the owner's Telegram user ID
- Ignore messages from unauthorized Telegram users
- Never use Telegram usernames as the authorization mechanism
- Redact API keys and bot tokens in logs and the interface

Provide a first-run setup flow.

The first-run page should ask for

- Administrator password
- Telegram bot token
- Allowed Telegram user ID
- OpenAI API key
- User name
- Name of the primary person
- User timezone
- Preferred model names

Store sensitive configuration encrypted at rest when feasible.

At minimum, encrypt API keys and Telegram tokens using an application secret stored in a local file with restrictive permissions.

Document the security limitations clearly.

## Application lifecycle

The web application and Telegram bot run in the same monolithic application, but their lifecycle should be separately controllable.

The dashboard should show

- Web application status
- Telegram bot status
- Reminder worker status
- Database status
- OpenAI configuration status
- Current application version
- Current Git branch
- Last update check
- Last successful Telegram update
- Last successful OpenAI request
- Recent error count

The Telegram bot controls should include

- Start
- Pause
- Resume
- Restart
- Stop

Pausing means the bot remains connected but does not process ordinary user messages. It may respond with a short paused message.

Stopping the bot must not stop the web interface.

Restarting the whole application from inside itself may require a supervisor or wrapper process. Implement the simplest safe approach and document it.

Do not pretend that an in-process restart is reliable if it is not. Use a small launcher or supervisor when necessary.

## OpenAI integration

Use the OpenAI Responses API.

Keep all model names configurable.

Use separate settings for

```text
Main conversation model
Summarization model
Embedding model
Optional stronger fallback model
```

Do not hardcode a model that may later disappear.

The main model should handle most turns. The stronger fallback model should be optional and disabled by default.

Use structured output and tool calling.

The model must not directly write to the database. It may request tool actions, and the application validates and executes those actions.

Implement timeout handling, retries with backoff, and clear error messages.

Do not endlessly retry.

Log these fields for each model request.

- Internal run ID
- Conversation ID
- Model name
- Start time
- End time
- Latency
- Input token count when available
- Output token count when available
- Cached token count when available
- Estimated or reported cost when possible
- Number of retrieved records
- Requested tools
- Executed tools
- Error information
- Redacted request snapshot
- Redacted response snapshot

Never log API keys.

## Agent responsibilities

The LLM should be responsible for

- Natural conversation
- Understanding user intent
- Asking useful follow-up questions
- Choosing whether a detail is worth remembering
- Distinguishing fact, observation, and inference
- Requesting memory and event changes through tools
- Combining retrieved knowledge into advice
- Explaining why suggestions fit
- Expressing uncertainty naturally
- Avoiding repetitive or clinical responses

The harness should be responsible for

- Durable storage
- Context construction
- Retrieval
- Time awareness
- Token limits
- Tool validation
- Authorization
- Telegram cards
- Deletion
- Database consistency
- Cost logging
- Error handling
- Security

## Agent behavior

The assistant should feel friendly, attentive, and natural.

It should not behave like an intake form.

It should generally ask no more than one follow-up question at a time.

It should not announce internal operations such as retrieval, embeddings, database records, confidence scores, context windows, or memory IDs.

It may say natural phrases such as

```text
You mentioned a quiet Italian restaurant a few weeks ago.
```

It should not say

```text
Memory record 391 has a similarity score of 0.87.
```

The assistant should support care, attention, communication, and thoughtful planning.

It must not recommend manipulation, deception, pressure, surveillance, emotional coercion, or attempts to control the other person.

It must not treat the other person as an optimization target.

The assistant should separate these ideas carefully.

```text
Odysseus likes Penelope's black dress.
Penelope likes black dresses.
```

The first statement does not imply the second.

The assistant should not convert a single observation into a certain preference.

## Static context

Always provide a small static context to the main model.

It should include

- The main agent instructions
- User name
- Primary person's name
- User timezone
- Relationship stage when configured
- Conversation tone preference
- Memory behavior preferences
- Current date and time
- Relevant safety rules

Do not put every long-term memory into the system prompt.

Static context must remain compact.

## Dynamic context

Build dynamic context for every turn from

- Recent raw messages
- Rolling conversation summary
- Pending conversational state
- Results returned by model-requested memory searches
- Results returned by model-requested planning searches
- Recent completed events
- Upcoming important events

The context builder must enforce configurable token budgets.

Do not send the entire database to the model. Do not preload unrelated saved records.

## Conversation history and summarization

Store every Telegram user and assistant message.

Keep recent raw messages in the model context.

When the recent context exceeds a configurable token threshold, summarize the oldest section.

Use rolling summarization.

```text
Existing summary
plus
messages leaving the recent window
becomes
updated summary
```

Do not repeatedly summarize the entire conversation from the beginning.

Use a structured summary containing

- Current conversational topic
- Recent developments
- User goal
- Relevant emotional context
- Decisions
- Corrections
- Open questions
- Pending commitments
- Referenced people, events, places, and objects
- Temporarily useful details not yet stored as permanent memory

Do not duplicate permanent memories unnecessarily inside the summary.

Keep the newest raw messages unchanged.

The web interface must show

- Current summary
- Recent raw context
- Summary update history
- Token estimates
- Which messages were summarized

## Pending conversational state

Implement short-lived pending state.

Examples include

- Waiting for a restaurant address
- Waiting for a book name
- Clarifying whether an observed preference is general
- Confirming whether two objects are the same
- Waiting for a reminder date
- Waiting for a correction

Pending state should include

- Type
- Related entity ID when available
- Missing information
- Question asked
- Creation time
- Expiration time
- Resolution status

Pending state is not permanent memory.

Expired pending state should not confuse future conversations.

## Knowledge model

Use relational records with embeddings where useful.

Do not implement a graph database.

The minimum domain entities are

```text
User
User settings
Person
Conversation
Message
Conversation summary
Memory
Memory note
Place
Saved idea
Event
Reminder
Pending state
Telegram card
Agent run
Tool execution
```

## Memory model

A memory should contain at least

- ID
- Owner user ID
- Subject person ID
- Type
- Statement
- Status
- Confidence
- Importance
- Created time
- Updated time
- Last retrieved time
- Soft deletion time
- Embedding text
- Embedding vector
- Current Telegram card message ID
- Manual ordering position
- Optional parent or group ID

Supported statuses should include

```text
confirmed
observed
inferred
uncertain
corrected
superseded
deleted
```

Supported initial memory types should include

```text
fact
preference
dislike
interest
observation
inference
communication_preference
sensitivity
promise
gift_clue
style_clue
food_clue
entertainment_clue
relationship_detail
```

Avoid a large rigid taxonomy. Store an optional short tag list for additional organization.

## Memory notes

A memory may contain multiple notes.

Each note should contain

- Text
- Note type
- Creation time
- Optional source message ID
- Optional source event ID
- Optional related object
- Optional confidence
- Manual order

Note types should include

```text
evidence
context
correction
source
interpretation
```

Example memory

```text
Penelope appears to like small silver earrings.
```

Example notes

```text
She wore them at Helena's birthday.
She wore the same pair on the Italian dinner date.
```

## Place model

Places should be stored separately from ordinary memories.

A place should contain

- Name
- Type
- Address
- City
- Optional latitude and longitude
- Optional source URL
- Description
- Atmosphere tags
- Optional price level
- Status
- Created time
- Updated time
- Embedding
- Telegram card ID

Place statuses should include

```text
candidate
saved
visited
dismissed
deleted
```

A saved date idea should link

- User
- Primary person
- Place
- Reason it might fit
- Status
- Whether it has been used
- Optional event where it was used

## Event model

Events should include

- Title
- Event type
- Participants
- Start time
- End time
- Timezone
- Status
- Description
- Emotional context
- Whether the user has discussed the outcome
- Related memories
- Related places
- Related reminders

Examples include

```text
Dinner date
Birthday
Exam period
Party
Movie night
Important conversation
Gift deadline
```

## Reminder model

Reminders should include

- Title
- Scheduled time
- Timezone
- Optional recurrence
- Related person
- Related event
- Related memory
- Status
- Last triggered time
- Telegram delivery status

Keep reminders basic.

Support one-time reminders first.

Recurring reminders may be added only when the implementation remains straightforward.

## Retrieval

Implement simple hybrid retrieval.

Do not implement GraphRAG.

Retrieval should combine

- Metadata filtering
- Exact entity matching
- Keyword matching
- Embedding similarity
- Importance
- Confidence
- Recency
- Event relevance
- Whether a saved idea has already been used

For each user turn, derive an internal retrieval request containing

- User goal
- People mentioned
- Entities mentioned
- Memory types likely needed
- Event context
- Time range
- Keywords
- Semantic query

Retrieve a small candidate set.

Rerank it deterministically using a weighted score.

Keep weights configurable.

A reasonable initial scoring formula is

```text
0.40 semantic similarity
0.20 entity match
0.15 keyword match
0.10 goal or type match
0.05 importance
0.05 confidence
0.05 recency or event relevance
```

Do not over-optimize the first version.

Log retrieval candidates and their score components so they can be inspected through the web interface.

## Embeddings

Generate embeddings for

- Memories
- Places
- Saved ideas
- Events when useful

No document chunking is needed.

Each item should have one concise embedding text assembled from its structured fields.

Example memory embedding text

```text
Penelope may like science-fiction novels. Evidence. She shared a quote from Solaris on Instagram.
```

Example place embedding text

```text
Casa Verde. Restaurant at 125 Main Street. Quiet and romantic. Odysseus saved it as a possible date place for Penelope.
```

The structured database fields remain the source of truth.

Regenerate an embedding only when the relevant source text changes.

## Tool definitions

Implement a small validated tool set.

### Memory tools

```text
create_memory
update_memory
add_memory_note
delete_memory
confirm_memory
merge_memories
```

### Place and idea tools

```text
create_place
update_place
delete_place
save_date_idea
mark_place_visited
```

### Event tools

```text
create_event
update_event
link_memory_to_event
mark_event_discussed
```

### Reminder tools

```text
create_reminder
update_reminder
delete_reminder
```

### Profile tools

```text
update_user_profile
update_person_profile
```

### Conversation tools

```text
create_pending_state
resolve_pending_state
cancel_pending_state
```

The application should normally perform retrieval before calling the model.

Do not require the model to call a memory search tool on every turn.

All modifying tool calls must be validated for

- Ownership
- Existing IDs
- Allowed fields
- Maximum string lengths
- Valid status transitions
- Duplicate requests
- Idempotency
- Soft-deleted records
- Authorization

Record every tool execution.

## Structured model output

Define strict Pydantic schemas for model output.

A turn result should support

```json
{
  "messages": [
    {
      "type": "chat",
      "text": "That sounds worth keeping. Do you know the address?"
    }
  ],
  "actions": [],
  "pending_state": {
    "type": "complete_place",
    "missing_fields": ["address"]
  },
  "needs_stronger_model": false
}
```

Model output message types should include

```text
chat
memory_card_reference
place_card_reference
reminder_card_reference
```

The model should request semantic actions.

It must not generate Telegram callback payloads, database IDs, SQL, or HTML.

The Telegram renderer should build cards from stored records.

## Telegram behavior

Support normal text messages.

Store Telegram message identifiers.

Use inline buttons.

### Memory card buttons

Confirmed memory

```text
Edit
Delete
```

Inferred memory

```text
Confirm
Edit
Delete
```

### Place card buttons

```text
Open map
Mark visited
Edit
Delete
```

### Reminder card buttons

```text
Change
Delete
```

Callback payloads should contain opaque identifiers and short action names.

On delete

1. Validate that the memory belongs to the authorized user.

2. Soft-delete the database record.

3. Delete or edit the Telegram card.

4. Acknowledge the callback immediately.

5. Record the action.

If Telegram message deletion fails, keep the database correct and edit the card when possible to show that it was deleted.

When an existing memory gains new evidence, update its existing Telegram card instead of creating a duplicate card.

## Web interface

Build a clean local administration interface.

Do not design a public social product.

Use server-rendered pages with HTMX where helpful.

The interface should be usable on desktop and mobile browsers.

### Dashboard

Show

- Overall status
- Telegram status
- Worker status
- Database status
- OpenAI status
- Recent conversations
- Recent memories
- Upcoming reminders
- Recent errors
- Token usage today
- Estimated API cost today
- Current application version
- Git branch and commit
- Start, pause, resume, restart, and stop bot controls
- Update application control

### Conversation history

Provide

- Conversation list
- Message history
- Filters by date and sender
- Search
- Associated memory cards
- Associated events
- Agent run details for each turn
- Raw recent context
- Rolling summary
- Retrieved memories
- Model output
- Tool calls
- Token usage
- Latency
- Error details

Sensitive request data should be redacted where necessary.

### Memory management

Provide

- Search
- Filtering
- Sorting
- Grouping by type, status, tag, and person
- Add memory
- Edit memory
- Delete memory
- Restore soft-deleted memory
- Confirm an inferred memory
- Add, edit, delete, and reorder notes
- Change memory type
- Change status
- Change confidence
- Change importance
- Add tags
- Reorder memories manually
- Merge duplicate memories
- View linked events and messages
- View embedding text
- Regenerate embedding
- See when the memory was last retrieved
- See the Telegram card status

Use drag-and-drop only if it can be implemented simply. Otherwise provide move-up and move-down controls.

### Places and ideas

Provide

- List of saved places
- Add and edit places
- Delete and restore
- Address
- Description
- Atmosphere tags
- Candidate, saved, visited, or dismissed status
- Related date idea
- Related events
- Mark as visited
- Open address in a map URL
- Retrieval history

### Events and reminders

Provide

- Calendar-like list or chronological table
- Add, edit, and delete events
- Mark event discussed
- Add reminders
- Mark reminders completed
- Show related memories and places

Do not build a complex calendar application.

### Agent inspector

For every model turn, show

- Static profile snapshot
- Current time
- Conversation summary
- Recent messages
- Pending state
- Retrieval query
- Retrieved candidate records
- Score components
- Final selected records
- Estimated context tokens
- Final redacted model input
- Raw structured model output
- Requested tools
- Executed tools
- Telegram outputs
- Model name
- Token use
- Latency
- Errors

Add a copy button for JSON sections.

### Settings

Provide settings for

- OpenAI API key
- Telegram bot token
- Allowed Telegram user ID
- Main model
- Summary model
- Embedding model
- Optional stronger model
- Stronger model enabled
- User name
- Primary person's name
- Timezone
- Relationship stage
- Preferred reply length
- Conversation tone
- Automatic visible memory cards
- Retrieval limit
- Context token budgets
- Summary threshold
- Web host and port
- Logging level

API keys and tokens must appear masked.

Changing a secret should require entering the complete new value.

Do not return the existing secret to the browser.

### System page

Provide

- Application version
- Git remote
- Git branch
- Git commit
- Update check
- Safe update action
- Database migration status
- Database backup action
- Downloadable JSON export
- Import from validated JSON
- Log viewer
- Health checks
- Restart controls

Require password confirmation before update, import, destructive reset, or credential changes.

## Import, export, and backup

Implement a complete JSON export containing

- User settings without plaintext secrets
- People
- Memories
- Notes
- Places
- Ideas
- Events
- Reminders
- Conversations
- Messages
- Summaries

Implement import with schema validation.

Do not import arbitrary executable content.

Provide a database backup action.

Document how to restore a backup manually.

## Logging and observability

Use structured logs.

Logs should include

- Timestamp
- Severity
- Component
- Request or run ID
- Conversation ID where applicable
- Safe event details

Redact

- OpenAI API keys
- Telegram tokens
- Session cookies
- Passwords
- Encryption secrets
- Authorization headers

Allow viewing recent logs through the web interface.

Limit log file size and rotate logs.

## Error behavior

Telegram users should receive a natural short error.

Example

```text
I ran into a problem while saving that. I did not add the memory. Please try again.
```

Do not expose stack traces through Telegram.

The web interface should show detailed errors to the authenticated owner.

Database transactions should prevent partially applied tool calls.

If an OpenAI call fails, do not invent a response or execute actions.

If card creation fails after a database memory is created, mark the card as unsynchronized and allow retrying through the web interface.

## Data integrity

Use database transactions.

Use soft deletion for important domain records.

Use stable opaque IDs.

Add created and updated timestamps.

Add foreign key constraints.

Add uniqueness constraints where appropriate.

Prevent duplicate callback execution.

Store source links from memories to messages when possible.

Maintain an audit log for manual web edits and model-requested edits.

## Privacy

This system stores sensitive personal information.

Implement

- Local-only web binding by default
- Owner-only Telegram allowlist
- Secure password storage
- Encrypted secrets
- Export
- Deletion
- Log redaction
- Configurable message retention
- Configurable agent-run retention

Add a clear privacy notice in the first-run setup and README.

Do not claim that the system is suitable for storing medical, legal, financial, or highly sensitive secrets.

## Tests

Write unit and integration tests.

At minimum, test

- Unauthorized Telegram user rejection
- Login authentication
- Secret masking
- Memory creation
- Memory deletion through callback
- Duplicate callback idempotency
- Memory confirmation
- Memory note creation
- Existing card update
- Place creation
- Retrieval ranking
- Retrieval ownership isolation
- Rolling summarization
- Pending state creation and expiration
- Tool validation
- Transaction rollback
- OpenAI timeout handling
- Bot pause and resume
- Settings updates
- JSON export
- Invalid import rejection
- Safe update refusal with uncommitted Git changes

Mock OpenAI and Telegram in automated tests.

Do not require live API credentials for the test suite.

## Conversation scenario tests

Create fixtures representing complete situations.

### Saved restaurant retrieval

Initial state

```text
Casa Verde is saved as a quiet, romantic restaurant for Penelope.
Penelope recently completed exams.
The place has not been visited.
```

User message

```text
I want to take her somewhere relaxing after exams. Where should we go?
```

Expected behavior

```text
Casa Verde should be retrieved.
The assistant should explain why it fits.
The assistant must not claim that Penelope already visited it.
No duplicate place should be created.
```

### Book observation and inference

User message

```text
Penelope posted a quote from Solaris.
```

Expected behavior

```text
Create an observation that Penelope shared a quote from Solaris.
Optionally create an uncertain inference that she may like science fiction.
Do not create a confirmed preference.
Show separate cards if both records are stored.
```

### Jewelry memory update

Initial state

```text
Penelope wore small silver sphere earrings at Helena's birthday.
```

User message

```text
She wore the same earrings on our date.
```

Expected behavior

```text
Retrieve the existing jewelry memory.
Add a new evidence note.
Update the existing card.
Do not create a duplicate jewelry memory.
```

### User preference separation

User message

```text
Her black dress looked amazing.
```

Expected behavior

```text
The system may store that Odysseus liked Penelope's black dress.
It must not store that Penelope likes black dresses.
```

### Natural conversation

For ordinary greetings and casual messages

```text
Do not create memories without a useful reason.
Do not send cards unnecessarily.
Do not interrogate the user.
```

## Code quality

Use type annotations.

Use small functions.

Use clear Pydantic schemas.

Avoid generic utility modules containing unrelated behavior.

Avoid premature dependency injection frameworks.

Avoid unnecessary repository classes if direct service logic is clearer.

Use migrations.

Use transactions.

Run formatting, linting, type checking, and tests.

Required commands should include

```bash
ruff check .
ruff format --check .
mypy wingman
pytest
```

Configure them in `pyproject.toml`.

## Documentation

The README must explain

- What the project does
- Its limitations
- Linux requirements
- Telegram bot creation
- How to find the Telegram user ID
- OpenAI API key setup
- Installation
- PostgreSQL startup
- First-run setup
- All CLI commands
- Data directories
- Backups
- Updates
- Troubleshooting
- Running tests
- Security limitations

The architecture document must explain

- Request lifecycle
- Context layers
- Summarization
- Retrieval
- Tool execution
- Telegram card synchronization
- Process lifecycle
- Data model
- Security boundaries

## Installation experience

Provide a documented path such as

```bash
git clone https://github.com/HalflingWizard/wingman.git
cd wingman
./scripts/install.sh
wingman start
```

The installation script should

- Check the Python version
- Create a virtual environment
- Install dependencies
- Create required local directories
- Copy `.env.example` only when appropriate
- Avoid overwriting existing configuration
- Explain whether PostgreSQL or Docker Compose is needed

Keep the install script safe and idempotent.

Do not silently install system packages with elevated privileges.

## Local directories

Use a predictable local data directory such as

```text
~/.local/share/wingman
```

Use a predictable configuration directory such as

```text
~/.config/wingman
```

Use a predictable log directory such as

```text
~/.local/state/wingman/logs
```

Allow these paths to be overridden.

Set restrictive permissions for secret files.

## Implementation sequence

Implement in this order.

### Phase 1

- Project setup
- Configuration
- Database
- CLI
- FastAPI health page
- Telegram connection
- Owner allowlist
- Basic OpenAI conversation
- Message persistence

### Phase 2

- Memory model
- Memory tools
- Memory cards
- Delete callbacks
- Memory web interface
- Agent run logging

### Phase 3

- Embeddings
- Hybrid retrieval
- Context builder
- Memory notes
- Memory confirmation
- Existing card updates
- Retrieval inspector

### Phase 4

- Rolling summaries
- Token budgets
- Pending state
- Conversation inspector
- Summary tests

### Phase 5

- Places
- Saved ideas
- Events
- Reminders
- Time-aware context
- Relevant web pages

### Phase 6

- Bot lifecycle controls
- Secure settings management
- Safe Git updates
- Export and backups
- Complete tests
- Documentation
- Final security review

Commit logical groups of work separately when Git access is available.

## Completion requirements

The work is complete only when all of the following are true.

- The application installs on Linux using documented commands.
- `wingman start` starts the web interface and Telegram bot.
- The browser opens automatically unless disabled.
- The owner can complete first-run setup.
- Unauthorized Telegram users are ignored or rejected.
- Natural Telegram conversation works.
- Memories can be created as visible cards.
- Memory cards can be deleted through Telegram.
- Memories can be edited through the web interface.
- Existing memory cards can be updated.
- Relevant memories are retrieved for later advice.
- Older conversations are summarized.
- Context and retrieval can be inspected.
- Places, events, and reminders work at a basic level.
- The bot can be paused and resumed through the interface.
- OpenAI and Telegram credentials can be changed securely.
- The application can perform a safe Git update.
- Data survives restarts.
- Exports and backups work.
- Automated tests pass.
- Documentation is complete.
- No out-of-scope integrations are present.

## Working method

Begin by inspecting the repository and environment.

Then do the following.

1. Write the architecture and implementation plan.

2. Identify any assumptions that prevent implementation.

3. Make the smallest reasonable assumptions instead of stopping for minor questions.

4. Implement one phase at a time.

5. Run tests after each phase.

6. Fix failures before proceeding.

7. Keep the application runnable throughout development.

8. Do not leave critical functions as placeholders.

9. Do not use fake implementations in production paths.

10. Clearly document any feature that could not be completed.

At the end, provide

- A summary of what was built
- The exact installation commands
- The exact startup command
- The local web address
- The configuration steps
- Test results
- Known limitations
- Recommended next improvements

The priority order is

```text
Correctness
Privacy
Natural conversation
Maintainability
Observability
Cost control
Convenience
Additional features
```
