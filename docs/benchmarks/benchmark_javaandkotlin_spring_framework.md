# Benchmark: Java/Kotlin — Spring Framework 7.x

**Date:** 2026-06-10 · **Project Mapper:** v1.5.0

> Real numbers from the [Spring Framework source repository](https://github.com/spring-projects/spring-framework) (main branch, version `7.1.0-SNAPSHOT`). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `spring-projects/spring-framework` |
| Version | `7.1.0-SNAPSHOT` |
| Date tested | **2026-06-10** |
| Project Mapper | **v1.5.0** |
| Java/Kotlin files analyzed | **9,622** |
| Spring modules | **28** (spring-core, spring-beans, spring-context, spring-web, spring-webmvc, spring-webflux, spring-aop, spring-tx, …) |

---

## Test Environment

| | |
|:---|:---|
| OS | Windows 11 |
| Python | 3.10.11 |
| Hardware | Desktop PC · Intel i9-13900K (24C/32T) · RTX 4090 |
| PM server | Standalone · `python -m uvicorn server:app --port 7474` |
| Analysis | Static AST only (no LLM calls) |

> **Windows note:** NTFS and Defender I/O overhead inflates scan time vs Linux/macOS (est. 3–5× faster on Linux).

---

## Indexing

### Full Scan (cold start)

| | |
|:---|:---|
| Java/Kotlin files analyzed | **9,622** |
| Entities indexed | **28,604** |
| Relations mapped | **59,356** |
| Stubs resolved | 13 · Relations rewired: 18 |
| Errors | **0** |
| Snapshot size | **26.22 MB** |
| Entity files on disk | **0** (PMEntityStore) |
| **Full scan time** | **335 s (~5.6 min)** |

### Incremental Scan (zero file changes)

| | |
|:---|:---|
| Files skipped (hash unchanged) | **9,622** |
| **Incremental scan time** | **5.0 s** |
| **Speedup vs full scan** | **67×** |

> Spring is 2.3× larger than Django (28,604 vs 12,140 entities, 59,356 vs 34,950 relations) but scan time scales sub-linearly — the bottleneck is concurrency-limited AST analysis, not file I/O.

---

## Query Benchmarks

The primary purpose of Project Mapper is **token reduction**. Each test below compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

> **"Normal" baseline:** Spring's modules are spread across 28 subprojects. On first contact an agent must grep across modules and read large Java files (often 500–2,000 lines each). Token estimates assume the agent already knows which module contains the target class.
>
> **Query latency (v1.5.0):** cold miss ~390 ms (26 MB snapshot load); warm hits 20–290 ms.

---

### J1 — ApplicationContext Hierarchy

**Question:** *"What ApplicationContext implementations does Spring provide?"*

**Normal approach:** `grep "implements ApplicationContext"` or `grep "extends.*ApplicationContext"` across spring-context, spring-web, spring-webmvc, spring-webflux, spring-test. Read each implementing class to understand its role. 5+ reads across 5 separate modules.

**PM approach:** `impact("ApplicationContext", via_kinds=["extends"], exclude_tests=True)`

**11 implementations returned (cross-module):**
```
ConfigurableApplicationContext     spring-context/…/ConfigurableApplicationContext.java
AbstractApplicationContext         spring-context/…/support/AbstractApplicationContext.java
ConfigurableWebApplicationContext  spring-web/…/ConfigurableWebApplicationContext.java
GenericApplicationContext          (stub — resolved via name index)
AbstractRefreshableApplicationContext
GenericWebApplicationContext
AbstractRefreshableWebApplicationContext
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 5+ | **1** | **1** |
| Tokens consumed | ~5,000 | **~671** | **~402** |
| Implementations found | Partial (misses stubs / cross-module) | **11 — complete, cross-module** | **11 — complete** |
| Savings vs Normal | — | **~7.5×** | **~12.4×** |

---

### J2 — Bean Wiring Path: BeanFactory → BeanDefinition

**Question:** *"How does Spring's BeanFactory connect to a BeanDefinition — what is the call chain?"*

**Normal approach:** Read `BeanFactory.java`, follow the interface hierarchy through `AutowireCapableBeanFactory.java` and `AbstractAutowireCapableBeanFactory.java` (1,750 lines), then trace through `ConstructorResolver` and `AbstractBeanDefinition.java` (1,200 lines) to reach `BeanDefinition`. 6 files, all in spring-beans, many hundreds to thousands of lines each.

**PM approach:** `path("BeanFactory", "BeanDefinition")`

**Result (6-hop semantic path):**
```
BeanFactory
  --[extends]--> AutowireCapableBeanFactory
  --[extends]--> AbstractAutowireCapableBeanFactory
  --[calls via instantiateUsingFactoryMethod]--> ConstructorResolver
  --[calls via autowireConstructor]--> ConstructorArgumentValues
  --[calls via getConstructorArgumentValues]--> AbstractBeanDefinition
  --[extends]--> BeanDefinition
```

The bridging methods `instantiateUsingFactoryMethod` and `autowireConstructor` are surfaced directly — no file read required.

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6 | **1** | **1** |
| Tokens consumed | ~18,000 | **~419** | **~242** |
| Full path discovered | No (requires reading 1,750-line class) | **Yes — 6 hops, bridging methods named** | **Yes** |
| Savings vs Normal | — | **~43×** | **~74×** |

---

### J3 — Spring MVC/WebFlux Handler Mapping Hierarchy

**Question:** *"What HandlerMapping implementations does Spring provide, across MVC and WebFlux?"*

**Normal approach:** Search spring-webmvc and spring-webflux separately for HandlerMapping implementations. Read `AbstractHandlerMapping.java`, `RequestMappingHandlerMapping.java`, `RouterFunctionMapping.java` and their WebFlux equivalents. 4–5 reads across two modules.

**PM approach:** `impact("HandlerMapping", via_kinds=["extends"], exclude_tests=True)`

**15 implementations returned (MVC + WebFlux unified):**
```
AbstractHandlerMapping           AbstractHandlerMethodMapping (WebFlux)
RequestMappingHandlerMapping     RouterFunctionMapping
AbstractUrlHandlerMapping        MatchableHandlerMapping
EmptyHandlerMapping              ...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 4–5 | **1** | **1** |
| Tokens consumed | ~8,000 | **~1,036** | **~662** |
| Implementations found | Partial (one module at a time) | **15 — MVC + WebFlux unified** | **15 — complete** |
| Savings vs Normal | — | **~7.7×** | **~12.1×** |

---

### J4 — Pre-Task Context: Transaction Management

**Question:** *"I'm about to work on Spring's transaction management — what entities should I know about?"*

**Normal approach:** Read `TransactionManager.java`, `PlatformTransactionManager.java`, `TransactionTemplate.java`, `TransactionSynchronizationManager.java`, `@Transactional` annotation, `TransactionDefinition.java`, `TransactionStatus.java`, and `AbstractPlatformTransactionManager.java` in spring-tx. 8 large Java files, ~12,000 tokens. Returns raw file content with no entity ranking.

**PM approach:** `context("transaction management")`

**30 entities returned (8 seeds), ranked by relevance:**
```
[class]  PlatformTransactionManager
[class]  AbstractPlatformTransactionManager
[class]  TransactionTemplate
[class]  TransactionSynchronizationManager
[module] spring-tx/…/TransactionDefinition.java
[class]  ReactiveTransactionManager (WebFlux reactive tx)
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 8 | **1** | **1** |
| Tokens consumed | ~12,000 | **~2,290** | **~1,368** |
| Entities surfaced | 8 files (unranked) | **30 entities (ranked by relevance)** | **30 entities (ranked)** |
| Savings vs Normal | — | **~5.2×** | **~8.8×** |

---

### J5 — AOP Advice Hierarchy

**Question:** *"What Advice types does Spring AOP provide?"*

**Normal approach:** Browse `spring-aop/src/main/java/org/springframework/aop/` and `org/aopalliance/intercept/`, read core advice interfaces, then trace down through spring-aop, spring-aspects, and spring-tx for concrete implementations. 15+ files across 3 modules, many entries still missed.

**PM approach:** `impact("Advice", via_kinds=["extends"], exclude_tests=True)`

**84 advice types returned (complete, cross-module):**
```
Core interfaces:  Interceptor, BeforeAdvice, AfterAdvice, DynamicIntroductionAdvice, ...
AOP Alliance:     ConstructorInterceptor, MethodInterceptor, ...
AspectJ advice:   AspectJAfterAdvice, AspectJAfterReturningAdvice, AspectJAfterThrowingAdvice, ...
Adapters:         AfterReturningAdviceInterceptor, ThrowsAdviceInterceptor, ...
TX integration:   TransactionInterceptor, ...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 15+ | **1** | **1** |
| Tokens consumed | ~24,000 | **~5,810** | **~3,690** |
| Advice types found | Partial (~30–40, misses TX/aspects) | **84 — complete, cross-module** | **84 — complete** |
| Savings vs Normal | — | **~4.1×** | **~6.5×** |

---

## Headline Numbers

| Test | Question | Normal | PM (Full) | PM (Slim) | Savings (Full) | Savings (Slim) |
|:---|:---|:---|:---|:---|:---|:---|
| J1 | ApplicationContext hierarchy | ~5,000 tok | **~671 tok** | **~402 tok** | **7.5×** | **12.4×** |
| J2 | BeanFactory → BeanDefinition path | ~18,000 tok | **~419 tok** | **~242 tok** | **43×** | **74×** |
| J3 | HandlerMapping hierarchy | ~8,000 tok | **~1,036 tok** | **~662 tok** | **7.7×** | **12.1×** |
| J4 | Transaction management context | ~12,000 tok | **~2,290 tok** | **~1,368 tok** | **5.2×** | **8.8×** |
| J5 | AOP Advice hierarchy | ~24,000 tok | **~5,810 tok** | **~3,690 tok** | **4.1×** | **6.5×** |

**Geometric mean savings:** PM Full **~9×** · PM Slim **~14×** across all five tests.

> J2 (path query) dominates the arithmetic mean — tracing a 6-hop call chain through Spring's bean wiring infrastructure requires reading multiple 1,000–1,750-line Java files manually. The geometric mean is the more representative figure for mixed workloads.
>
> J5 (Advice hierarchy) has the lowest ratio because the PM response itself is large (84 entities). The completeness advantage is significant: a manual search would find 30–40 of 84 advice types; PM returns all 84 in one call.

---

## Reproducing

```bash
# 1. Clone Spring Framework
git clone https://github.com/spring-projects/spring-framework
# (this benchmark uses 7.1.0-SNAPSHOT)

# 2. Start PM server
cd /path/to/aethvion-project-mapper
python -m uvicorn server:app --port 7474

# IMPORTANT: always use 127.0.0.1, not localhost

# 3. Full scan
curl -X POST http://127.0.0.1:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/spring-framework","db":"spring","incremental":false}'

# 4. J1 — ApplicationContext hierarchy
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"ApplicationContext","db":"spring","via_kinds":["extends"],"exclude_tests":true}'

# 5. J2 — BeanFactory → BeanDefinition path
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/path \
  -H "Content-Type: application/json" \
  -d '{"from_entity":"BeanFactory","to_entity":"BeanDefinition","db":"spring"}'

# 6. J4 — Transaction context
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"transaction management","db":"spring","depth":1,"max_results":30}'
```

---

*Benchmark conducted 2026-06-10 · Aethvion Project Mapper v1.5.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
