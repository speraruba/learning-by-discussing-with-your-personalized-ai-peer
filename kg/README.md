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

### Deliberate limits

Where the pipeline isn't sure, it leaves the relation out.
- **No coreference resolution.** Sentences whose subject or object is *it* or *they* produce no relation.
- **No cross-sentence relations.**
- **Clausal objects are skipped** ("research shows that …").

A larger spaCy model (`KG_SPACY_MODEL=en_core_web_trf`, a parser rather than an LLM) gives better parses of messy speech.

## Ontology

`kg/ontology.yaml` defines the concept classes, the controlled vocabulary (canonical key + synonyms) and the relation types with their trigger verbs. The **initial version was seeded from the two topics' reading materials and needs review by the research team.** Edits take effect on the next run. The loader rejects:
- a term listed under two concepts
- a trigger listed under two relation types
- relation-type names that aren't `UPPER_SNAKE` (they are written into Cypher as-is)

## Neo4j model

```
(:Participant {id})-[:HAS_GRAPH]->(:Graph {id: "<session_id>:<stage>", session_id, topic, stage, source,
                                          text_sha256, ontology_version, pipeline_version, spacy_model, built_at})
(:Graph)-[:MENTIONS {count, surface_forms, sources, ner_labels}]->(:Concept {key, label, class, in_ontology, head})
(:Concept)-[:REDUCES|DEPENDS_ON|… {graph_id, negated, count, predicates, modals, stances, evidence}]->(:Concept)
```

- **Shared concepts.** `Concept` nodes are shared across all graphs, so the same idea can be compared across participants and stages. Which graph an edge belongs to is recorded in its `graph_id`.
- **Idempotent rebuilds.** Rebuilding a stage replaces that graph's edges and mentions in a single transaction.

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
docker run -d --name lp-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<password> neo4j:5-community
$env:NEO4J_PASSWORD = "<password>"     # also NEO4J_URI / NEO4J_USER / NEO4J_DATABASE if not default
```

## CLI

```bash
python -m kg text "AI reduces memory."          # print extraction as JSON; no databases
python -m kg build <session_id> recall          # one stage → Neo4j
python -m kg build <session_id> phase2 --dry-run
python -m kg build-all <session_id>             # every stage that has text
```

## Tests

```bash
MYSQL_DB=lp_test_kg NEO4J_PASSWORD=<password> python test_kg.py
```

The extraction checks always run. The MySQL → Neo4j end-to-end checks run only when `NEO4J_PASSWORD` is set, and they delete what they wrote afterwards.
