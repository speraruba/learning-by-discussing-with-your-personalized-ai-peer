# Learning Partner Experiment Agent

[中文版本](README_CN.md)

This learning-partner agent runs a two-topic, three-round discussion experiment. Participants talk with the agent in a web interface; full conversation history (including cognitive-conflict flags), search records, and exam responses are stored in a MySQL database.

## Experiment flow

After the start page, the experiment covers two topics in order. Each topic follows **read one article → (discussion → independent search) × 3**. Topic 1 ends at a **break page**; Topic 2 ends at an **exam page**; submitting the exam leads to the thank-you page. The page header displays the current topic, discussion round, and stage.

```
Topic 1: Read article 1 → Discussion 1 → Search 1 → Discussion 2 → Search 2 → Discussion 3 → Search 3 → Break
Topic 2: Read article 2 → Discussion 1 → Search 1 → Discussion 2 → Search 2 → Discussion 3 → Search 3 → Exam → Thank you
```

1. **Reading** — At the start of each topic, participants read the pro-position article: the `Reading Material` in `materials/article_{t}_P1_user`. Changes take effect on refresh. The system prompt receives the opposing material from `materials/article_{t}_ai`, which participants cannot see.
2. **Onboarding (Topic 1 only)** — After reading article 1, the agent explains the procedure and encourages active participation. Discussion starts only after the participant explicitly confirms readiness, determined through the model's `advance` field. After Topic 2's article, the agent begins directly with `topic_open`.
3. **Discussion / debate** — The agent debates using only its material for that round. It may reason from it, but may not introduce outside facts. Each round it self-assesses whether it triggered cognitive conflict, and the server counts the result. The prompt also supplies a hidden **BRIDGING GOAL**: while discussing the current learning goal, naturally lead toward the next round's goal within the same topic.
4. **Guided reflection** — Once **3** cognitive conflicts have been triggered, the agent asks the participant to summarize disagreements and reflections; agreement is explicitly not required.
5. **Independent search** — After the discussion summary, the participant asks a neutral search agent questions. It searches authoritative online sources and answers with citations. Selecting “End Search” begins the next discussion, or proceeds to the break/exam after round 3.
6. **Exam** — Following Topic 2, participants answer the questions on the exam page. Questions are defined by `EXAM_QUESTIONS` in `materials.py`.

## Setup and running

Secrets and connection details are read **only from environment variables**, never from source code. Use `.env.example` as a template:

```bash
cp .env.example .env      # fill in real values; .env is gitignored
set -a && source .env && set +a
```

Or export values individually:

```bash
pip install -r requirements.txt

# 1) OpenAI API key (required; calls return 503 with guidance if missing)
export OPENAI_API_KEY="sk-..."        # optional: export OPENAI_MODEL="gpt-4o"
# Optional model timeout and retry settings (fault-tolerance defaults)
export OPENAI_TIMEOUT=60               # request timeout in seconds; search uses OPENAI_SEARCH_TIMEOUT (default 120)
export OPENAI_MAX_RETRIES=3            # exponential-backoff retries for 429/5xx/connection errors

# 2) MySQL connection (defaults shown below)
export MYSQL_HOST=127.0.0.1           # default: 127.0.0.1
export MYSQL_PORT=3306                # default: 3306
export MYSQL_USER=root                # default: root
export MYSQL_PASSWORD=yourpassword    # default: empty
export MYSQL_DB=learning_partner      # default: learning_partner

uvicorn app:app --port 8000
```

Open `http://localhost:8000` and sign in with the participant's name and researcher-assigned Participant ID.

- For a new ID, the participant consents, completes demographic information (date of birth, age, gender, years of education, native-English status, and ethnicity), then completes background information (the 12-item, seven-point AI Literacy Scale) before entering Topic 1.
- For an existing ID, the name is verified case-insensitively. Completed participants go directly to the thank-you page; otherwise, the interrupted stage and conversation history are restored. Each participant may complete the experiment only once.

### Fault tolerance

Progress is server-side, so it survives a disconnected page, browser crash, device change, and server restart.

- **Resume** — Entering the same Participant ID restores the last stage and replays history. A browser refresh does this automatically.
- **Interrupted model response** — The participant message is persisted first. If the response fails, the session is marked `pending`; the client automatically calls `POST /api/session/{sid}/retry-turn` after restoration.
- **Safe duplicates** — Duplicate messages are not persisted twice. `done-reading`, `end-search`, `end-rest`, and `exam` are idempotent. Completed steps return `409`, causing the client to resync.
- **No lost text** — Failed requests restore the text to the input box and retry with backoff; the client also synchronizes when connectivity returns or the page regains focus.
- **Model calls** — Timeouts and exponential-backoff retries avoid prolonged upstream waits.
- **Database connections** — Idle MySQL connections reconnect automatically. Failed reads reconnect and retry once; writes rely on the idempotent endpoints to avoid duplicates.

Regression test (uses a fake agent and a separate test database, so it consumes no API credits):

```bash
MYSQL_DB=lp_test OPENAI_API_KEY=sk-test python test_fault_tolerance.py
```

### Automatic database initialization

MySQL 5.7+ or 8.0 is required because the schema uses `JSON` columns. No manual database or table creation is needed. At startup, `database.init_db()`:

1. Creates the database with `utf8mb4` / `utf8mb4_unicode_ci` if it does not exist.
2. Creates the `participants`, `sessions`, and `messages` tables if missing.
3. Adds missing columns, keys, and foreign-key constraints to existing tables using `ADD COLUMN`, `ADD KEY`, and `ADD CONSTRAINT`. It only adds; it never alters or removes existing data.
4. Makes no changes when the schema is current.

If MySQL is not ready at startup, the application retries automatically (10 attempts, 1.5 seconds apart), then exits with configuration guidance. The `SCHEMA` dictionary at the top of `database.py` is the sole source of truth; add a field there and restart to upgrade the schema.

## Experiment materials

All materials live in `materials/` and are parsed by `materials.py` at startup:

- **`article_{t}_ai`** — The AI learning partner's opposing material for topic *t*, injected only into the system prompt. It contains a `# Topic:` position statement and `## Phase 1-3` sections, each with a `### Learning Goal` and `### Reading Material`.
- **`article_{t}_P{n}_user(.md)`** — The participant-side material for topic *t*, round *n*, used to anticipate the participant's position. It contains `# Topic:`, `# Learning Goal`, and `# Reading Material`. P1's reading material is also shown on the reading page and is re-read on each request; changes take effect after refresh. Changes to other material require a server restart.
- **Exam questions** — `EXAM_QUESTIONS` in `materials.py` (currently placeholders; replace them).
- Set `CONFLICTS_REQUIRED = 3` to change the number of required cognitive conflicts per discussion round.

## Data export

- Each topic has a separate session, identified by `sessions.topic`. The Topic 1 session is marked `done` at the end of the break, then a Topic 2 session is created. Conversation and search records remain isolated per session.
- The `learning_partner` MySQL database contains `participants`, `sessions`, `messages`, `search_queries`, and `exam_answers`, plus legacy `causal_graphs` data, which is no longer generated but remains available through the history endpoint.
- `participants` has a case-insensitive unique `participant_id`, name and demographic information, academic background, 12 raw AILS responses plus reverse-scored `ails_score` (12–84), and LLM-use information. Multi-select LLM purposes and learning modes are stored as JSON arrays.
- Export one session through `GET /api/session/{session_id}/history`. Each message includes stage, activity, role, content, `conflict`, `meta.reason`, and timestamp.
- Conflict counts and reasons remain backend-only and are not displayed to participants.

## Cognitive-conflict evaluation

The agent uses structured self-evaluation and returns `{reply, conflict_triggered, reason}` each round. The system prompt sets strict criteria: a conflict must be a new argument, evidence, or challenge directed at an already expressed participant position. Repeated arguments, clarifying questions, and points already accepted by the participant do not count. For stricter evaluation, add an independent judge model in `agent.py`.

## Project structure

```
app.py         FastAPI backend, participant-ID API, and the two-topic × three-round state machine
agent.py       Prompt construction and GPT calls; reads secrets only from environment variables
.env.example   Environment-variable template; copy it to .env, which is gitignored
materials.py   Discussion configuration for two topics (three rounds each) and exam questions
materials/     Experiment materials: article_{t}_ai and article_{t}_P{n}_user
database.py    MySQL storage: SCHEMA declaration and automatic database/table/schema initialization
static/        Participant web UI: login, consent, forms, reading, discussion, search, break, exam, thank-you, and automatic reconnect
test_fault_tolerance.py  Fault-tolerance regression test; requires a separate test database
```
