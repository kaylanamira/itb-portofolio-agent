# Bab 4 Experiment Execution Plan 

## Role

You are an agent responsible for implementing, running, and writing up architectural experiments for Bab 4 of this thesis, plus reorganizing existing evaluation work into a supporting "functional testing" section.

## Governing Principle


1. Why does this system need an **Agentic AI architecture** instead of a simpler one?
2. Why does the **Text-to-SQL pipeline** need additional grounding mechanisms instead of a simpler pipeline?

---


## TASK: Build and Run Experiment I — Agentic AI Architecture

### 2.1 Objective
Evaluate the contribution of the Planner-Orchestrator-Iterative Reasoning architecture by comparing it against simpler orchestration paradigms capable of solving the same academic portfolio analysis tasks.

### 2.2 Research Question (fixed)
> Does the proposed Agentic AI architecture provide measurable improvements over simpler architectures for academic portfolio analysis?

### 2.3 Configurations to implement

Each configuration changes only the orchestration strategy. The table below defines what each configuration includes or excludes based on the actual nodes in the system architecture.

| Config | Architecture Label | Planner (include/exclude) | Step Reasoner (include/exclude) | Tool Routing Mechanism | Multi-Tool Execution Strategy | Synthesizer Variant |
|---|---|---|---|---|---|---|
| A1 | Direct Tool Calling | Exclude `planner`;  | Exclude `step_reasoner`. | Single eval adapter `direct_tool_workflow_eval` routes to `sql_pipeline`,  `chart_interpreter`, or `clarification_handler` based on the predicted primary tool. | One tool call only; no dependent second step; no observation loop. Multi-tool cases are forced to the primary tool and expected to expose baseline limitations. | Same production `synthesizer`, but receives one observation only. |
| A2 | ReAct-style Agent + iterative reasoning | Exclude production `planner`; use eval-only `react_controller_eval` that chooses the next action from tool descriptions at each iteration. | Include an eval-only observation loop, but not production `step_reasoner`. | LLM chooses one action at a time using ReAct-style thought/action/observation format. | Iterative up to three tool calls; each next tool is selected after observing the previous result. No initial plan is stored. | Same production `synthesizer`, receiving accumulated ReAct observations converted into `steps_completed`. |
| A3 | Plan-Execute Agent | Include production `planner`. | Exclude `step_reasoner`; use eval-only sequential executor that follows the initial plan exactly. | `planner` creates all steps once; executor runs step 1 to step n without early stop or replanning. | Multi-tool execution follows the initial plan order. Results from previous steps are passed as context, but the plan cannot be shortened or adjusted. | Same production `synthesizer`, receiving all planned step outputs. |
| A4 | Proposed Planner-Orchestrator + iterative reasoning | Include production `planner`. | Include production `step_reasoner`. | Production `route_next_step` uses `plan`, `current_step_index`, `tool`, and `required` fields to route to `sql_pipeline`, `, `catalog_lookup`, `rag_retriever`, `chart_interpreter`, `clarification_handler`, or `synthesizer`. | Multi-tool execution is plan-guided and observation-aware. `step_reasoner` records each result, can advance steps, and can stop early when evidence is sufficient. | Same production `synthesizer`, receiving validated `steps_completed` from the proposed workflow. |
 

**Constraint:** Only the orchestration layer changes between A1/A2/A3/A4. Database, Retriever, SQL Pipeline, and Chart Interpreter must remain byte-identical across all four runs. If a configuration requires changing anything outside orchestration to make it work, stop and flag it; that would invalidate the isolation the experiment depends on.

### 2.3.1 Execution Implementation Plan

| Step | Implementation Detail | Files to Add or Modify |
|---|---|---|
| 1 | Add an end-to-end dataset with expected query type, orchestration complexity, domain, expected tool sequence, expected answer facts, and expected clarification behavior. | Add `evals/datasets/architecture_orchestration_cases.json`. |
| 2 | Add Pydantic schema for the architecture cases so each case has explicit `query_type`, `orchestration_complexity`, expected tools, rubric, and optional gold SQL facts. | Modify `evals/datasets/schemas.py`. |
| 3 | Add eval-only orchestration adapters for A1, A2, and A3. These adapters must call existing production tools and must not fork SQL, database, chart, or retriever code. | Add `tests/helpers/orchestration_variants.py`. |
| 4 | Run A4 through the existing production graph | Reuse `agent/orchestrator.py`, `agent/graph.py`. |
| 5 | Record per-case traces: selected tools, number of tool calls, latency, token use if available, final answer, and judge scores. | Add `tests/test_e2e/test_architecture_orchestration.py`. |
| 6 | Aggregate Experiment I into four evaluations: routing quality, task success, answer quality, and efficiency. | Extend `evals/scorer.py` or add `evals/architecture_scorer.py`. |

### 2.4 Dataset construction

The dataset is designed in two stages. First, it covers representative analytical query types handled by the system. Second, within each query type, cases are distributed across different levels of orchestration complexity. This prevents the experiment from accidentally proving only that the system works for one query type or only that it handles complex orchestration cases.

Canonical dataset schema for AI-agent dataset generation: `docs/TA/schemas/experiment_1_architecture_dataset.schema.json`.

Total dataset size: 80 manually curated questions.

#### 2.4.1 Query Type Distribution

The first stratification axis is `QueryType`. Use the fixed labels below so the experiment aligns with the planner output schema and can be reported consistently with the system implementation.

| Query Type | Description | Example Question Pattern | Portion | n |
|---|---|---|---|---|
| `data_lookup` | Factual retrieval of academic portfolio indicators. | "Berapa rata-rata nilai evaluasi kelas IF2210 pada semester 2024-1?" | 10 percent | 8 |
| `text_lookup` | Retrieval of textual evidence from comments, reflections, or portfolio text. | "Apa komentar mahasiswa yang paling sering muncul untuk kelas IF2210?" | 10 percent | 8 |
| `analytical_numeric` | Numerical analysis requiring aggregation, ranking, trend, or threshold reasoning. | "Mata kuliah apa yang mengalami penurunan evaluasi terbesar dalam tiga semester terakhir?" | 10 percent | 8 |
| `analytical_text` | Analysis over textual evidence, such as theme identification or sentiment-style interpretation. | "Tema keluhan apa yang paling sering muncul pada komentar mahasiswa IF2210?" | 10 percent | 8 |
| `analytical_hybrid` | Integrated analysis over structured numerical data and unstructured textual evidence. | "Kelas mana yang nilainya turun dan komentar apa yang mendukung penurunan tersebut?" | 10 percent | 8 |
| `diagnostic` | Explanation of possible causes using measured results and supporting evidence. | "Mengapa evaluasi kelas IF2210 menurun dibanding semester sebelumnya?" | 10 percent | 8 |
| `comparative` | Comparison across courses, lecturers, classes, programs, faculties, or semesters. | "Bandingkan rata-rata evaluasi IF2210 dan IF2220 pada semester 2024-1." | 10 percent | 8 |
| `summarization` | Summarization of a set of retrieved records or text evidence. | "Ringkas komentar mahasiswa untuk kelas IF2210 semester 2024-1." | 10 percent | 8 |
| `chart_interpret` | Query that depends on dashboard chart context. | "Dari grafik ini, kelas mana yang perlu diperiksa lebih lanjut dan apa data pendukungnya?" | 10 percent | 8 |
| `clarification_needed` | Query that cannot be executed safely because required context is missing or ambiguous. | "Bagaimana hasilnya?" | 10 percent | 8 |

#### 2.4.2 Orchestration Complexity Distribution Within Each Query Type

Each query type contains the same orchestration complexity distribution: 2 single-tool cases, 2 parallel multi-tool cases, 2 sequential cases, and 2 dependent multi-step cases. With ten query types, this produces 80 cases in total.

| Orchestration Complexity | Description | Expected Mechanism | n per Query Type | Total n |
|---|---|---|---|---|
| C1 Single-tool | Only one tool or one terminal response is required. The answer can be produced from one SQL query, one retrieval, one chart interpretation, one synthesis over provided context, or one clarification response. | Direct routing to one tool should be sufficient. | 2 | 20 |
| C2 Parallel multi-tool | More than one tool may be needed, but the outputs are independent evidence items that can be synthesized together. For `clarification_needed`, this means multiple independent missing slots that can be asked in one clarification response. | The architecture must select all relevant tools or missing slots without requiring dependency between outputs. | 2 | 20 |
| C3 Sequential reasoning | The output of one step determines the next step, but the dependency is shallow. For `clarification_needed`, this means a context-dependent ambiguity such as a pronoun or chart reference that must be resolved before analysis. | The architecture must pass prior step context into the next step. | 2 | 20 |
| C4 Dependent multi-step reasoning | The query requires a chain of dependent decisions, such as finding a subset, comparing it, retrieving supporting evidence, and synthesizing a diagnostic explanation. For `clarification_needed`, this means multiple dependent missing constraints that would make execution unsafe without clarification. | The architecture must plan, observe, continue, and stop based on evidence sufficiency. | 2 | 20 |

#### 2.4.3 Dataset Matrix

| Query Type | C1 Single-tool | C2 Parallel Multi-tool | C3 Sequential | C4 Dependent Multi-step | Total |
|---|---|---|---|---|---|
| `data_lookup` | 2 | 2 | 2 | 2 | 8 |
| `text_lookup` | 2 | 2 | 2 | 2 | 8 |
| `analytical_numeric` | 2 | 2 | 2 | 2 | 8 |
| `analytical_text` | 2 | 2 | 2 | 2 | 8 |
| `analytical_hybrid` | 2 | 2 | 2 | 2 | 8 |
| `diagnostic` | 2 | 2 | 2 | 2 | 8 |
| `comparative` | 2 | 2 | 2 | 2 | 8 |
| `summarization` | 2 | 2 | 2 | 2 | 8 |
| `chart_interpret` | 2 | 2 | 2 | 2 | 8 |
| `clarification_needed` | 2 | 2 | 2 | 2 | 8 |
| Total | 20 | 20 | 20 | 20 | 80 |

#### 2.4.4 Example Case Patterns

| Query Type | C1 Single-tool Example | C2 Parallel Multi-tool Example | C3 Sequential Example | C4 Dependent Multi-step Example |
|---|---|---|---|---|
| `data_lookup` | "Berapa rata-rata evaluasi kelas IF2210 pada semester 2024-1?" | "Tampilkan rata-rata evaluasi IF2210 dan jumlah respondennya." | "Cari kelas IF2210 semester terakhir, lalu tampilkan rata-rata evaluasinya." | "Cari kelas IF2210 dengan evaluasi terendah dalam tiga semester terakhir, lalu tampilkan indikator utama yang paling rendah." |
| `text_lookup` | "Apa komentar mahasiswa yang menyebutkan beban tugas pada IF2210?" | "Ambil komentar terkait beban tugas dan komentar terkait kejelasan materi pada IF2210." | "Cari kelas IF2210 semester terakhir, lalu ambil komentar mahasiswa untuk kelas tersebut." | "Cari kelas dengan komentar negatif terbanyak, lalu ambil tema komentar paling dominan." |
| `analytical_numeric` | "Mata kuliah apa yang memiliki rata-rata evaluasi tertinggi pada semester 2024-1?" | "Tampilkan mata kuliah dengan rata-rata tertinggi beserta jumlah kelasnya." | "Cari fakultas dengan rata-rata evaluasi terendah, lalu tampilkan lima mata kuliah penyumbang utamanya." | "Identifikasi tren penurunan evaluasi terbesar, cari kelas penyebab utama, lalu tentukan komponen evaluasi yang paling terdampak." |
| `analytical_text` | "Apa tema utama komentar mahasiswa IF2210?" | "Analisis tema komentar mahasiswa dan ringkas contoh komentar pendukungnya." | "Cari kelas dengan komentar terbanyak, lalu analisis tema komentar untuk kelas tersebut." | "Cari mata kuliah dengan komentar negatif terbanyak, kelompokkan tema komentar, lalu jelaskan tema dominan." |
| `analytical_hybrid` | "Apakah kelas IF2210 dengan nilai evaluasi rendah juga memiliki komentar negatif?" | "Tampilkan nilai evaluasi IF2210 dan tema komentar mahasiswa terkait." | "Cari kelas dengan evaluasi terendah, lalu ambil komentar mahasiswa untuk menjelaskan hasil tersebut." | "Identifikasi tren penurunan evaluasi, cari kelas penyebab utama, ambil komentar pendukung, lalu susun analisis terpadu." |
| `diagnostic` | "Apa indikator evaluasi terendah untuk IF2210?" | "Apa indikator evaluasi terendah dan bagaimana ringkasan komentar mahasiswa terkait indikator tersebut?" | "Cari kelas dengan indikator terendah, lalu ambil komentar mahasiswa yang relevan untuk kelas tersebut." | "Identifikasi penurunan evaluasi, telusuri komponen penyebab, ambil bukti komentar, lalu susun diagnosis singkat." |
| `comparative` | "Bandingkan rata-rata evaluasi IF2210 dan IF2220 pada semester 2024-1." | "Bandingkan rata-rata evaluasi dua mata kuliah dan tampilkan jumlah responden masing-masing." | "Cari dua kelas dengan penurunan terbesar, lalu bandingkan komponen evaluasinya." | "Identifikasi dua program studi dengan tren evaluasi paling berbeda, lalu jelaskan komponen yang paling berkontribusi." |
| `summarization` | "Ringkas komentar mahasiswa untuk kelas IF2210." | "Ringkas komentar mahasiswa dan refleksi dosen untuk IF2210." | "Cari kelas IF2210 semester terakhir, lalu ringkas komentar mahasiswanya." | "Cari kelas dengan komentar paling banyak, kelompokkan komentar, lalu susun ringkasan masalah utama." |
| `chart_interpret` | "Jelaskan anomali utama dari grafik evaluasi ini." | "Jelaskan grafik ini dan ambil data pendukung untuk kelas yang paling menonjol." | "Dari grafik ini, pilih kelas yang perlu diperiksa, lalu tampilkan data evaluasi detailnya." | "Dari grafik tren ini, identifikasi anomali, cari kelas penyebab, ambil indikator pendukung, lalu susun rekomendasi pemeriksaan." |
| `clarification_needed` | "Bagaimana hasilnya?" | "Bandingkan hasilnya dan jelaskan penyebabnya." | "Dari grafik tadi, kenapa kelas itu turun?" | "Bandingkan mata kuliah itu dengan semester sebelumnya dan jelaskan penyebab turunnya." |

#### 2.4.5 Dataset JSON Schema Summary

The dataset file should be generated as `evals/datasets/architecture_orchestration_cases.json` using the schema in `docs/TA/schemas/experiment_1_architecture_dataset.schema.json`.

| Field Group | Required Fields | Purpose |
|---|---|---|
| Dataset metadata | `dataset_name`, `version`, `description`, `total_cases` | Identifies the dataset and freezes the evaluated version. |
| Distribution | `query_type_counts`, `orchestration_complexity_counts` | Verifies that the dataset follows the 10 query types and 4 orchestration complexity levels. |
| Case identity | `id`, `query_type`, `orchestration_complexity`, `domain` | Supports stratified reporting by query type and complexity. |
| Input | `raw_query`, `language`, `user_scope`, `input_context` | Reconstructs the agent invocation. |
| Expected behavior | `expected_query_type`, `expected_tool_sequence`, `expected_node_sequence`, `expected_plan_steps`, `expected_response_type` | Provides ground truth for routing, planning, and response-type evaluation. |
| Answer rubric | `required_answer_facts`, `acceptable_answer_patterns`, `scoring_rubric` | Supports task success, correctness, faithfulness, and completeness scoring. |

### 2.5 Metrics to compute

| Tier | Metric | Definition |
|---|---|---|
| Evaluation I.1 - Routing Quality | Tool Selection Accuracy | Percentage of cases where the selected tool set matches the expected tool set, ignoring order for parallel cases and preserving order for sequential/dependent cases. |
| Evaluation I.1 - Routing Quality | Tool Sequence Accuracy | Percentage of cases where the tool order exactly matches the expected sequence for sequential and dependent cases. |
| Evaluation I.2 - Task Completion | Task Success Rate | Percentage of cases where the final response satisfies the case rubric and contains the required facts or clarification behavior. |
| Evaluation I.2 - Task Completion | Correctness | Percentage of required factual claims that match the gold SQL result, chart context, or rubric facts. |
| Evaluation I.3 - Answer Quality | Faithfulness | LLM-as-a-Judge score measuring whether the final answer is supported by tool outputs in `steps_completed`. |
| Evaluation I.3 - Answer Quality | Completeness | LLM-as-a-Judge score measuring whether the answer covers all required parts of the user request. |
| Evaluation I.4 - Efficiency | Number of Tool Calls | Mean number of tool calls per case. Lower is better only when task success remains comparable. |
| Evaluation I.4 - Efficiency | Average Latency | Mean wall-clock runtime per case. |
| Evaluation I.4 - Efficiency | Token Consumption | Mean prompt and completion token count if provider metadata is available. |

### 2.6 Output table template

```
Tabel 4.X Hasil Eksperimen I.1 - Routing Quality

Konfigurasi | C1 Single-tool (n=20) | C2 Parallel Multi-tool (n=20) | C3 Sequential (n=20) | C4 Dependent Multi-step (n=20) | Total
A1 (Direct Tool Calling)        | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc
A2 (ReAct-style)                | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc
A3 (Plan-Execute)               | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc
A4 (Proposed Orchestrator)      | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc | Tool Acc / Seq Acc

Tabel 4.X Hasil Eksperimen I.2 - Task Completion

Konfigurasi | C1 Single-tool (n=20) | C2 Parallel Multi-tool (n=20) | C3 Sequential (n=20) | C4 Dependent Multi-step (n=20) | Total
A1 (Direct Tool Calling)        | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness
A2 (ReAct-style)                | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness
A3 (Plan-Execute)               | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness
A4 (Proposed Orchestrator)      | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness | Success / Correctness

Tabel 4.X Hasil Eksperimen I.3 - Answer Quality

Konfigurasi | C1 Single-tool (n=20) | C2 Parallel Multi-tool (n=20) | C3 Sequential (n=20) | C4 Dependent Multi-step (n=20) | Total
A1 (Direct Tool Calling)        | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness
A2 (ReAct-style)                | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness
A3 (Plan-Execute)               | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness
A4 (Proposed Orchestrator)      | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness | Faithfulness / Completeness

Tabel 4.X Hasil Eksperimen I.3b - Task Success by Query Type

Konfigurasi | data_lookup | text_lookup | analytical_numeric | analytical_text | analytical_hybrid | diagnostic | comparative | summarization | chart_interpret | clarification_needed | Total
A1 (Direct Tool Calling)        | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success
A2 (ReAct-style)                | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success
A3 (Plan-Execute)               | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success
A4 (Proposed Orchestrator)      | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success | Success

Tabel 4.X Hasil Eksperimen I.4 - Efficiency

Konfigurasi | Tool Calls | Average Latency | Token Consumption | Notes
A1 (Direct Tool Calling)        | To be filled after run | To be filled after run | To be filled after run | One-tool baseline
A2 (ReAct-style)                | To be filled after run | To be filled after run | To be filled after run | Iterative, no upfront plan
A3 (Plan-Execute)               | To be filled after run | To be filled after run | To be filled after run | Upfront plan, no adaptive step reasoner
A4 (Proposed Orchestrator)      | To be filled after run | To be filled after run | To be filled after run | Production workflow
```
 

### 2.7 Result Analysis and Conclusion

- State which configuration wins overall, and by how much.
- Identify the category where A4's advantage over A1/A2/A3 is **largest**, and name the mechanism responsible (expected candidate: complex categories, attributable to planning plus step-wise reasoning; confirm or correct based on actual results, do not assume).
- Report whether the winning pattern is consistent across query types. If one query type benefits less from A4, state that limitation.
- Identify any category where A1/A2/A3 perform comparably to A4, and report it honestly. A bounded claim such as "necessary for complex cases, not for simple ones" is stronger than a blanket one.
- Close with one sentence answering the research question directly.

---

## TASK 2: Build and Run Experiment II — SQL Pipeline Architecture

### 3.1 Objective
Evaluate the contribution of the grounded SQL pipeline in improving SQL generation accuracy for complex academic portfolio databases.

### 3.2 Research Question
> Which grounding mechanisms contribute most significantly to SQL generation accuracy?

### 3.3 Configuration

| Config | Variant Label | Active Components | Disabled Components |
|---|---|---|---|
| S1 | Static Schema | `sql_generator`, `sql_validator`, `sql_executor`; fixed schema context supplied to generator; same database snapshot and `UserScope`. | `schema_linker`, fuzzy entity resolver, dynamic `describe_tables`, `catalog_lookup`, retrieved few-shot examples by query type, `answer_validator`, retry loop in `error_handler`. |
| S2 | Dynamic Schema Grounding | `schema_linker`, dynamic `describe_tables`, `sql_generator`, `sql_validator`, `sql_executor`; exact entity matching only. | Fuzzy entity resolver, `catalog_lookup`, `answer_validator`, retry loop in `error_handler`. |
| S3 | Full Grounded SQL Pipeline | Production SQL pipeline: `schema_linker`, fuzzy entity resolver, dynamic `describe_tables`, query-type few-shot examples, `catalog_lookup` when `required: true`, `sql_generator`, `sql_validator`, `sql_executor`, `answer_validator`, `error_handler` retry loop. | None. |


**Constraint:** Only the SQL pipeline block changes. Agent Orchestrator, Retriever Tool, and Chart Interpreter remain identical across S1/S2/S3.

### 3.3.1 Execution Implementation Plan

| Step | Implementation Detail | Files to Add or Modify |
|---|---|---|
| 1 | Add SQL experiment dataset with query text, expected SQL behavior, expected result facts, expected tables, expected entities, and complexity category. | Add `evals/datasets/sql_grounding_cases.json`. |
| 2 | Add SQL experiment variants that instantiate `SQLTool` or `build_sql_pipeline()` with S1, S2, and S3 configurations. | Add `tests/helpers/sql_pipeline_variants.py`. |
| 3 | Ensure S1, S2, and S3 use the same model, temperature, database snapshot, user role, and SQL executor. | Reuse `agent/llm.py`, `core/sql_executor.py`, and `core/scope.py`. |
| 4 | Run each generated SQL through the same validation and execution measurement harness. For S1/S2, disabled components must be disabled through eval-only configuration, not by editing production nodes. | Add `tests/test_e2e/test_sql_grounding_experiment.py`. |
| 5 | Aggregate metrics by complexity category and overall total. | Extend `evals/scorer.py` or add `evals/sql_grounding_scorer.py`. |

### 3.4 Dataset construction

Classify by the specific challenges each grounding component is designed to solve.

Canonical dataset schema for AI-agent dataset generation: `docs/TA/schemas/experiment_2_sql_grounding_dataset.schema.json`.
 
| schema Category                | Main View                          |
| ----------------------- | ---------------------------------- |
| Dosen Analytics      | v_akademik_statistik_dosen         |
| Prodi Analytics       | v_akademik_statistik_prodi         |
| Student Portfolio       | v_akademik_portofolio              |
| Course Information      | v_info_umum_kelas_matkul           |
| Lecturer Information    | v_info_umum_dosen                  |
| Evaluation Components   | v_akademik_komponen_evaluasi_kelas |
| Student Feedback        | v_akademik_komentar_mahasiswa      |
| Institution Information | v_info_umum_institusi              |

Total dataset size: 80 SQL questions.

| SQL Query Complexity | Description | Component It Is Meant to Isolate | Portion | n (given total dataset size) |
|---|---|---|---|---|
| Single Table Query | Simple selection and filtering | Baseline capability of `sql_generator`, `sql_validator`, and `sql_executor` | 15 percent | 12 |
| Multi-table Join | Multiple joins across academic portfolio views | Dynamic schema selection and join reasoning from schema context | 15 percent | 12 |
| Aggregation | COUNT, AVG, SUM, GROUP BY | SQL generation quality for analytical aggregation | 15 percent | 12 |
| Nested Query | EXISTS, IN, Subquery | SQL generation quality for complex query structure | 10 percent | 8 |
| Window Function | OVER(), RANK() | SQL generation quality for ranking and comparative analytics | 10 percent | 8 |
| Conditional Aggregation | CASE WHEN | SQL generation quality for conditional analytical logic | 10 percent | 8 |
| Ambiguous/typo Entity | Requires entity detection and value resolution | Fuzzy entity resolver in S3 | 15 percent | 12 |
| Questionnaire Metadata | Requires catalog lookup | `catalog_lookup` and prior-step context in S3 | 10 percent | 8 |

#### 3.4.1 Dataset JSON Schema Summary

The dataset file should be generated as `evals/datasets/sql_grounding_cases.json` using the schema in `docs/TA/schemas/experiment_2_sql_grounding_dataset.schema.json`.

| Field Group | Required Fields | Purpose |
|---|---|---|
| Dataset metadata | `dataset_name`, `version`, `description`, `total_cases` | Identifies the SQL grounding dataset and freezes the evaluated version. |
| Database snapshot | `database_snapshot.snapshot_id`, `database_snapshot.description` | Makes execution-accuracy results reproducible. |
| Distribution | `sql_complexity_counts` | Verifies that cases match the planned SQL complexity distribution. |
| Case identity | `id`, `sql_complexity`, `domain`, `language` | Supports stratified reporting by SQL challenge category. |
| Input | `question`, `user_scope`, `plan_step_context`, `prior_steps_context` | Reconstructs the SQL pipeline invocation for S1, S2, and S3. |
| Grounding expectation | `expected_tables`, `expected_entities`, `expected_catalog_references` | Supports schema selection, entity resolution, and catalog lookup scoring. |
| SQL expectation | `must_include_sql_patterns`, `must_not_include_sql_patterns`, `expected_result_facts`, `gold_sql` | Supports SQL validity, safety, and execution-accuracy scoring. |
| Scoring flags | `execution_accuracy_required`, `schema_selection_required`, `entity_resolution_required`, `catalog_lookup_required`, `retry_expected` | Clarifies which metric applies to each case. |

### 3.5 Metrics to compute

| Metric | Definition |
|---|---|
| Execution Accuracy | Percentage of cases where executed SQL returns the expected result facts or matches the gold result within the accepted tolerance. |
| Execution Success Rate | Percentage of cases where SQL executes without database error. |
| Valid SQL Rate | Percentage of generated SQL that passes syntax and security validation. |
| Retry Success Rate | Among cases that fail the first attempt, percentage fixed by later attempts. Applies to S3 only unless retry is enabled in another variant. |
| Number of Repair Iterations | Mean number of SQL regeneration attempts after validation or execution failure. |
| Schema Selection Accuracy | Percentage of cases where selected tables match expected tables. Applies to S2 and S3. |
| Average Generation Time | Mean wall-clock time from SQL pipeline start to final SQL output. |

### 3.6 Output table template

Results table template — fill in after running
 
```
Tabel 4.Y Hasil Eksperimen II — Perbandingan Konfigurasi SQL Pipeline
 
Konfigurasi | Single Table | Multi-table Join | Aggregation | Nested Query | Window Function | Conditional Aggregation | Ambiguous Entity | Questionnaire Metadata | Total
S1 (Static Schema)          | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run
S2 (Dynamic Schema)         | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run
S3 (Full Grounded Pipeline) | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run | To be filled after run
```

### 3.7 Result Analysis and Conclusion

- Report the overall accuracy progression from S1 to S2 to S3, with the size of each incremental jump.
- Identify which category shows the largest S1 to S2 jump, and confirm it is attributable to the component you assigned to S2.
- Identify which category shows the largest S2 to S3 jump, and confirm which S3-only component is responsible.
- Report any category with no improvement from added grounding as a legitimate finding — do not omit null results.
- Close with one sentence answering the RQ directly.

---

## TASK 4: Write 4.4 Discussion

- One paragraph tying Experiment I's result back to RQ1 ("why Agentic AI").
- One paragraph tying Experiment II's result back to RQ2 ("why grounded SQL pipeline").
- One closing paragraph stating that together, both experiments justify the two primary architectural decisions of the thesis — do not introduce new data here, only interpret what's already in 4.2/4.3.

---
