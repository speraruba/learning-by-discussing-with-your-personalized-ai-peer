# Knowledge-graph pipeline (`kg/`)

This pipeline turns a participant's own words into a concept graph in Neo4j. It uses **traditional NLP only**: spaCy part-of-speech tags, dependency parses and NER, plus rules. It makes no LLM calls. Every relation comes from a real grammatical structure in the text and stores the source sentence as evidence, so the pipeline cannot invent relations.

## Where graphs come from

Each topic session has four build points (`stage`):

| stage    | text used |
|----------|-----------|
| `recall` | free-recall transcript (`free_recalls`, `kind=baseline`, `status=done`) |
| `phase1`–`phase3` | the **participant's** messages in that discussion round (`role=participant`, `state` ∈ debate/summary) |

The agent's messages are excluded because they come from the agent's own material, not from what the participant knows. Onboarding and search messages are also excluded.

This module does **not** decide when to build. Whoever owns the study flow calls:

```python
from kg.pipeline import build_for_session, NotReady
build_for_session(session_id, "recall")      # raises NotReady if there's no text yet
```

## Stages

```
preprocess → extract_mentions (NER) → normalize → extract_relations → apply_ontology → Neo4j
```

1. **Preprocess.** Removes spoken fillers (um/uh/erm/hmm), which are common in Whisper output.
2. **NER and mention detection.** Mentions come from three sources, in priority order:
   - **Ontology lexicon matches.** These come first because the small spaCy model mislabels this domain: it tags "AI" as a place (GPE) and "AGI" as an organisation.
   - **spaCy named entities.**
   - **Noun phrases.** If a phrase contains two different ontology concepts, it becomes a compound concept ("AI learning", with `head=learning`) so contrasts like "AI learning is different from human learning" survive.
3. **Normalization.**
   - Common nouns are lemmatized (models → model).
   - Determiners, pronouns and adverbs are stripped.
   - Synonyms map to the ontology's canonical key (ChatGPT / LLM / language model → `llm`).
   - Generic words ("thing", "way") are dropped.
   - "Light" nouns ("the use **of** AI", "a lot **of** data") resolve to the noun after "of".
4. **Relation extraction.** Dependency patterns:
   - active subject–verb–object
   - passive with "by" (direction is flipped to the real agent)
   - passive or active verb + preposition (`rely_on`, `train_on`)
   - copula ("X is a Y")
   - adjective + preposition (`different_from`)
   - coordinated verbs (the second verb inherits the subject)
   - relative clauses (`which`/`that` resolve to the noun they modify)

   Each relation also records:
   - `negated`, including "I **don't** think AI understands X", where the negation is raised into the clause
   - `modal` (can/could/may…)
   - `stance`: `attributed` when the participant reports someone else's claim ("the article says…"), otherwise `asserted`
5. **Ontology stage.**
   - Concepts get a class from `ontology.yaml` (or `Unclassified`).
   - Predicates map to relation types (`REDUCES`, `DEPENDS_ON`, …). Unmapped predicates become `RELATED_TO`, and the original verb is kept.
   - `policy` in the YAML can drop unclassified concepts or untyped relations.

### Core and emergent concepts

Concepts in `ontology.yaml` are **core**. Anything else a participant talks about can still enter the graph as an **emergent** concept, so ideas outside our list are captured. To keep filler out, an emergent concept has to pass three checks:

1. Its main word is a noun ("tweak", "refining" are dropped).
2. It isn't a generic or meta-talk word ("thing", "topic", "vocabulary", "testing testing").
3. The participant actually used it: it takes part in a relation, or it's mentioned at least `emergent_min_mentions` times (default 2). A word dropped once in passing doesn't count.

Emergent concepts keep:
- `core_parts`, the core concepts inside the phrase ("AI tutor" → `ai`)
- up to two example sentences, for review

Labels drop leading words like "the", "any", "how".

**Growing the list.** `python -m kg candidates` lists emergent concepts across all participants, ranked by how many participants used them, with example sentences. A researcher adds the useful ones to `ontology.yaml`, then runs `python -m kg rebuild` so every stored graph is rebuilt with them as core. Nothing is added automatically.

### Expert concept maps

`kg/expert_maps/topic_<n>.yaml` holds a topic's expert map, copied from the reading material:
- the required concepts per round
- every statement, written as source → verb → target

Topic 2 (AI & Cognition) is copied from the reading material. Topic 1 (AGI) is a **draft** built from the older readings in `materials/article_1_*`, marked `draft: true`; scores for it carry `map_draft: true` until the research team replaces it with the official map.

When a topic has a map, each build is scored against it:
- **Concept coverage**: which required concepts the participant mentioned, overall and for the current round.
- **Statements between two required concepts** (9 for topic 2). Each one gets a status:
  - `matched`: the participant said it, in their own words (any relation type listed under `accept`)
  - `negated`: the participant said the opposite (denied a statement, or affirmed one the material states as negative, like "the Turing Test does not measure understanding")
  - `linked`: they connected the two concepts some other way
  - `similar`: no edge in the graph, but a sentence closely matches the statement (see below). This catches sentences the parser misreads.
  - `missing`: none of the above
- **Statements whose target is a description** ("a person's limited mental energy") can't be checked edge by edge, so they are checked by sentence similarity instead. Each gets `similar`, `not_found` (the concept came up but the statement wasn't said) or `not_mentioned`.

#### Sentence similarity

`kg/similarity.py` compares the participant's sentences with each statement. It only compares; it never generates text. Rules:

1. Only sentences that mention the statement's concept are considered (for concept-to-concept statements, both concepts).
2. The concept's own name is left out of the comparison, so every statement about one concept doesn't look alike.
3. Each sentence counts for at most one statement: the one it is closest to.
4. A score at or above the threshold counts as `similar`. The score and the sentence are stored for review.

The default model is spaCy's `en_core_web_md` word vectors (threshold 0.70, calibrated on paraphrases of the topic 2 statements). Setting `KG_SIM_MODEL=sbert:all-MiniLM-L6-v2` (after `pip install sentence-transformers`) uses a sentence-embedding model instead, which handles close paraphrases better. That option downloads the model from Hugging Face on first use and hasn't been tested in this repo yet. `KG_SIM_THRESHOLD` overrides the threshold. If no model is installed, scoring still runs and reports `similarity: unavailable`.

`python -m kg report <session_id>` shows each stage's coverage, matched statements, and the required concepts that are new since the recall.

### Deliberate limits

Where the pipeline isn't sure, it leaves the relation out.
- **No coreference resolution.** Sentences whose subject or object is *it* or *they* produce no relation.
- **No cross-sentence relations.**
- **Clausal objects are skipped** ("research shows that …").

A larger spaCy model (`KG_SPACY_MODEL=en_core_web_trf`, a parser rather than an LLM) gives better parses of messy speech.

### Why not a keyphrase package

We ran YAKE and TextRank (pytextrank) on the same two transcripts as the pipeline:
- **YAKE** ranked filler and fragments highly: "Testing", "Yeah", "split mental", "delegation leads".
- **TextRank** gave a better ranking, but still kept off-topic phrases ("fuelful sentences", "the actual full study flow"). It also doesn't merge variants ("Offloading" and "offloading" are listed separately).

Both packages only rank phrases. They don't normalize synonyms, extract relations, detect negation, or tell core concepts from emergent ones. So they would add a dependency without adding anything the pipeline needs.

KeyBERT needs a sentence-embedding model download and wasn't tested.

## Ontology

`kg/ontology.yaml` defines the concept classes, the controlled vocabulary (canonical key + synonyms) and the relation types with their trigger verbs. The **initial version was seeded from the two topics' reading materials and needs review by the research team.** Edits take effect on the next run. The loader rejects:
- a term listed under two concepts
- a trigger listed under two relation types
- relation-type names that aren't `UPPER_SNAKE` (they are written into Cypher as-is)

## Neo4j model

```
(:Participant {id})-[:HAS_GRAPH]->(:Graph {id: "<session_id>:<stage>", session_id, topic, stage, source,
                                          text_sha256, ontology_version, pipeline_version, spacy_model, built_at})
(:Graph)-[:MENTIONS {count, surface_forms, sources, ner_labels, examples}]->
        (:Concept {key, label, class, status, in_ontology, head, core_parts})
(:Concept)-[:REDUCES|DEPENDS_ON|… {graph_id, negated, count, predicates, modals, stances, evidence}]->(:Concept)
```

- **Shared concepts.** `Concept` nodes are shared across all graphs, so the same idea can be compared across participants and stages. Which graph an edge belongs to is recorded in its `graph_id`.
- **Idempotent rebuilds.** Rebuilding a stage replaces that graph's edges and mentions in a single transaction.
- **Scores on the Graph node.** When the topic has an expert map, the Graph node also stores:
  - `coverage_rate`
  - `concepts_covered`, `concepts_missing`
  - `propositions_matched`, `propositions_negated`, `propositions_linked`, `propositions_missing` (lists of statement ids)
  - `emergent_count`

Example query: everything participant P01 said reduces something, by stage.

```cypher
MATCH (:Participant {id:'P01'})-[:HAS_GRAPH]->(g:Graph)
MATCH (a:Concept)-[r:REDUCES {graph_id: g.id}]->(b:Concept)
RETURN g.stage, a.label, r.negated, b.label, r.evidence ORDER BY g.stage
```

## Setup

```powershell
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m spacy download en_core_web_md      # word vectors for the similarity check
docker run -d --name lp-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<password> neo4j:5-community
$env:NEO4J_PASSWORD = "<password>"     # also NEO4J_URI / NEO4J_USER / NEO4J_DATABASE if not default
```

## CLI

```bash
python -m kg text "AI reduces memory."          # print extraction as JSON; no databases
python -m kg text --file t.txt --topic 2        # same, plus the expert-map score
python -m kg build <session_id> recall          # one stage → Neo4j
python -m kg build <session_id> phase2 --dry-run
python -m kg build-all <session_id>             # every stage that has text
python -m kg report <session_id>                # coverage and new concepts per stage
python -m kg candidates --topic 2               # emergent concepts across participants
python -m kg rebuild                            # rebuild every stored graph after editing the ontology
```

## Tests

```bash
MYSQL_DB=lp_test_kg NEO4J_PASSWORD=<password> python test_kg.py
```

The extraction checks always run. The MySQL → Neo4j end-to-end checks run only when `NEO4J_PASSWORD` is set, and they delete what they wrote afterwards.
