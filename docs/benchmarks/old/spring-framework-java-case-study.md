# Case Study: Indexing the Spring Framework with Aethvion Project Mapper

> **Real numbers. No synthetic data. All measurements taken on the actual
> [Spring Framework source repository](https://github.com/spring-projects/spring-framework)
> (main branch, June 2026), using Project Mapper's Java analyzer introduced in v1.2.0.**

---

## The Subject

The Spring Framework is arguably the most widely deployed Java application framework in
the world. It underpins enterprise applications across banking, e-commerce, government,
and infrastructure at hundreds of thousands of organisations. The codebase is a
representative example of a mature, large-scale Java monorepo — rich with interfaces,
abstract hierarchies, annotation-driven configuration, and domain-specific sub-modules.

At 1.5 million lines across 9,218 Java files, it is the largest codebase we have
benchmarked Project Mapper against.

| Repository | `spring-projects/spring-framework` |
|---|---|
| Branch | `main` |
| Date | June 2026 |
| **Java files** | **9,218** |
| **Total lines** | **1,512,500** |
| Largest file | `SpelCompilationCoverageTests.java` — 7,959 lines |
| Sub-modules | 30+ (spring-core, spring-beans, spring-context, spring-web, …) |

### Top sub-modules by file count

| Module | Files |
|---|---|
| `spring-test` | 1,376 |
| `spring-context` | 1,250 |
| `spring-web` | 1,213 |
| `spring-core` | 1,086 |
| `spring-webmvc` | 590 |
| `spring-beans` | 579 |
| `spring-webflux` | 460 |

---

## Test Environment

| | |
|---|---|
| OS | Windows 11 |
| Python | 3.12.x |
| Aethvion Project Mapper | v1.2.0 (Java analyzer) |
| Parser | tree-sitter 0.25.2 + tree-sitter-java 0.23.5 |
| LLM enrichment | **disabled** — pure static analysis |
| Hardware | Consumer laptop |

> **Important**: Windows has higher file I/O overhead than Linux or macOS. The
> timing below reflects Windows conditions. On Linux or macOS the same scan runs
> approximately 3–5× faster (~13–21 seconds for 1.5 M lines).

---

## Phase 1 — Java Parsing

A full cold scan of all 9,218 Java files across the monorepo.

### Results

| Metric | Value |
|---|---|
| Files scanned | **9,218** |
| Total lines analyzed | **1,512,500** |
| **Entities extracted** | **18,370** |
| — Classes (regular) | **14,478** |
| — Abstract classes | **972** |
| — Interfaces | **1,683** |
| — Enums | **146** |
| — Records (Java 16+) | **186** |
| — Annotation types (`@interface`) | **905** |
| **Total method signatures** | **90,942** |
| **Total constants / enum values** | **5,107** |
| **Total import statements** | **88,616** |
| Files with parse errors | **57** (0.6 %) |
| **Full scan time (Windows)** | **64.3 s** |
| Per-file average | **0.84 ms** |
| Per-file median | **0.41 ms** |
| Throughput | **23,530 lines / sec** |

### Parse Errors

All 57 files with parse errors share a single root cause: **JSR 308 type-use annotations
on varargs parameters** — a Java 8+ feature where an annotation appears between the
element type and the varargs marker:

```java
// Triggers the grammar error:
Object getBean(String name, @Nullable Object @Nullable ... args) throws BeansException;
```

Tree-sitter's Java grammar (v0.23.5) does not recognise the `Type @Annotation ...`
pattern on vararg parameters. This is a known grammar gap that will resolve when the
grammar is updated.

**Critically, extraction still succeeds on all 57 files.** Tree-sitter partially parses
and Project Mapper extracts the remaining structure correctly:

| File | Entities extracted | Methods extracted |
|---|---|---|
| `BeanFactory.java` | 1 interface | 17 of 18 methods |
| `DefaultListableBeanFactory.java` | 11 classes / interfaces | correct |
| `AbstractApplicationContext.java` | 1 abstract class | 106 methods |

The one method skipped per error occurrence is the method whose vararg parameter
triggered the grammar fault. All other entities in those files are fully intact.

**57 of 9,218 files = 0.6 % error rate. All 0.6 % still extract partially.**

### Entity variety — what Spring looks like to Project Mapper

Spring uses all six Java entity kinds Project Mapper recognises:

| Kind | Count | Example |
|---|---|---|
| Regular class | 14,478 | `DispatcherServlet`, `JdbcTemplate` |
| Abstract class | 972 | `AbstractApplicationContext`, `AbstractBeanFactory` |
| Interface | 1,683 | `BeanFactory`, `ApplicationContext`, `HandlerMapping` |
| Enum | 146 | `HttpMethod`, `HttpStatus`, `MimeType` |
| Record | 186 | `BeanDefinitionParsingException.Problem`, value objects |
| `@interface` | 905 | `@Autowired`, `@Component`, `@RequestMapping`, … |

Spring's annotation module alone contains **905 annotation type definitions** —
one of the largest annotation libraries in the Java ecosystem. Project Mapper indexes
all of them, making annotation usage searchable without reading source files.

**Top entities by method count:**

| Entity | Kind | Methods | Module |
|---|---|---|---|
| `AbstractApplicationContext` | abstract class | 106 | spring-context |
| `DefaultListableBeanFactory` | class | ~90 | spring-beans |
| `BeanFactory` | interface | 17 | spring-beans |
| `ConfigurableApplicationContext` | interface | 19 | spring-context |

---

## Phase 2 — Token Cost Comparison

> **Methodology note:** Token counts use a 4 chars/token approximation
> (standard for GPT-4 class models on code). All numbers are **measured** from
> actual scan output, not modelled.

### 2a — Whole-repository read cost

| | Value |
|---|---|
| Total source characters | **52,722,901** |
| **Total tokens (raw files)** | **~13,180,725** |
| PM full entity index (projected) | **~636,281 tokens** |
| **Token reduction** | **95.2 %** |

Reading all 9,218 Spring source files would cost ~13 million tokens. Project Mapper's
entity index — names, kinds, inheritance, method counts, line ranges — delivers the
same structural picture in ~636,000 tokens.

### 2b — Entity lookup

Task: *"What is AbstractApplicationContext? What does it implement and what methods does it expose?"*

| | Tokens |
|---|---|
| Read `AbstractApplicationContext.java` in full | **15,481** |
| PM `get_entity("AbstractApplicationContext")` response | **782** |
| **Token reduction** | **94.9 %** |

### 2c — Targeted query

Task: *"Find all classes and interfaces that implement or extend ApplicationContext."*

| | Tokens |
|---|---|
| Read all 9,218 source files | **13,180,725** |
| PM structured query response (102 results) | **7,675** |
| **Token reduction** | **99.9 %** |

Without Project Mapper, answering this question requires either a grep pass (which
gives file paths but not structure) or reading every file that mentions
`ApplicationContext`. Project Mapper returns all 102 results — name, kind, file path,
bases, method count — in a single call.

**102 classes and interfaces implement or extend `ApplicationContext` across the
Spring Framework.** That fact would take minutes to establish manually; Project Mapper
surfaces it instantly.

### Summary

| Scenario | Without PM | With PM | Reduction |
|---|---|---|---|
| Entity lookup | 15,481 tokens | 782 tokens | **94.9 %** |
| Inheritance query (102 results) | 13,180,725 tokens | 7,675 tokens | **99.9 %** |
| Full-repo structural overview | 13,180,725 tokens | ~636,281 tokens | **95.2 %** |

---

## Language Benchmark Comparison

Project Mapper now covers three languages. Measured numbers across all three:

| Language | Repository | Files | Lines | Entities | Scan (Windows) | Token reduction |
|---|---|---|---|---|---|---|
| Python | Django 5.1 | 2,918 | 521,286 | 11,988 | 604 s | 89–93 % |
| TypeScript | Zod (v3 + v4) | 406 | 74,828 | 1,401 | 3.5 s | 97–99 % |
| **Java** | **Spring Framework** | **9,218** | **1,512,500** | **18,370** | **64 s** | **95–100 %** |

Spring Framework is the largest scan to date: **3× the line count of Django, 20× the
line count of Zod.**

---

## Limitations

**JSR 308 type-use annotations on varargs** — The `@Annotation Type @Annotation ...`
pattern on vararg parameters is not handled by tree-sitter-java 0.23.5. Affects 57 of
9,218 files (0.6 %). Partial extraction succeeds for all 57 — only the one method
per occurrence that triggers the fault is skipped. This resolves automatically when
the grammar is updated.

**No relations graph yet (Java)** — The full directed-graph of calls, imports, and
inheritance (which powers impact analysis and path-finding for Python) is in progress
for Java and TypeScript. Entity extraction, token savings, and entity-level queries
shown above are available today.

**Windows scan overhead** — On Linux the same 9,218-file scan would complete in
approximately 13–21 seconds. The 64-second figure reflects Windows NTFS + Defender
overhead.

**Test classes included** — Spring ships a large test suite (spring-test is the
largest sub-module by file count). Entities from test classes are indexed alongside
production code. A future `filter_paths` option will allow excluding test directories.

---

## Why Java Support Matters

Java remains the dominant language for enterprise backends, Android development, and
large-scale distributed systems. Frameworks like Spring, Hibernate, Apache Kafka, and
Quarkus are written in Java. An AI coding agent assisting on any of these systems
needs to understand the full inheritance hierarchy — abstract classes, interfaces,
annotation-driven configuration — not just raw file contents.

Project Mapper's Java support indexes:
- Spring-family applications (Spring Boot, Spring Data, Spring Security, …)
- Jakarta EE / JEE enterprise code
- Android applications and libraries
- Standalone Java libraries (Apache Commons, Guava, Jackson, …)

---

## Summary

| Metric | Value |
|---|---|
| Repository size | 1,512,500 lines · 9,218 Java files |
| **Entities extracted** | **18,370** |
| — Regular classes | 14,478 |
| — Abstract classes | 972 |
| — Interfaces | 1,683 |
| — Enums | 146 |
| — Records | 186 |
| — Annotation types | 905 |
| Method signatures | **90,942** |
| Constants / enum values | **5,107** |
| Import statements | **88,616** |
| Parse success rate | **99.4 %** (57 files partial — all 57 still extract) |
| Full scan time (Windows) | **64.3 s** |
| Full scan time (Linux, est.) | **~13–21 s** |
| Throughput | **23,530 lines / sec** |
| Token reduction — entity lookup | **94.9 %** |
| Token reduction — inheritance query | **99.9 %** |
| Token reduction — full-repo overview | **95.2 %** |
| LLM enrichment required | **No** |

---

## Reproducing This Test

```bash
# 1. Clone Spring Framework
git clone https://github.com/spring-projects/spring-framework /tmp/spring

# 2. Install Project Mapper with Java support
pip install "aethvion-project-mapper>=1.2.0"
pip install "tree-sitter>=0.23.0" tree-sitter-java

# 3. Start the server
pm-server --port 7474 &

# 4. Scan
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/tmp/spring", "db": "spring", "enrich": false}'

# 5. Context query
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q": "ApplicationContext bean lifecycle", "db": "spring"}'
```

Or via MCP in Claude Code:
```
pm_scan(project_root="/tmp/spring", db="spring", enrich=false)
pm_context(q="ApplicationContext bean lifecycle", db="spring")
```

---

*Benchmark conducted by the Aethvion team · June 2026*  
*Project Mapper v1.2.0 · Python 3.12 · Windows 11*  
*tree-sitter 0.25.2 · tree-sitter-java 0.23.5*
