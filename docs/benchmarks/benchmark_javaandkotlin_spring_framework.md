# Benchmark: Java/Kotlin — Spring Framework

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `spring-projects/spring-framework` |
| Language | Java / Kotlin |
| Files scanned | 9,576 |
| Total lines | ~1,530,000 |
| Entities indexed | 25,059 |
| Scan time | 19.4 s |
| Throughput | ~79,100 lines/sec |

Geometric mean savings: **~94% token reduction (Full) · ~95% token reduction (Slim)** · **~76× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — ApplicationContext Hierarchy

**Question:** *"What ApplicationContext implementations does Spring provide?"*

**Standard Workflow (Grep + Read):** `grep "implements ApplicationContext"` or `grep "extends.*ApplicationContext"` across spring-context, spring-web, spring-webmvc, spring-webflux, spring-test. Each grep returns matches in a different module; requires 5+ reads to understand each implementation's role. Cross-module results are easily missed.

**With Project Mapper:** `pm_impact "ApplicationContext" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial, misses cross-module stubs | 6 — direct impls, cross-module | 6 — complete |
| Token Cost | ~5,000 | ~277 | ~247 |
| Token Reduction | — | **−94%** | **−95%** |
| Execution Time | ~4s | 37ms | 37ms |
| Speedup | — | **~108×** | **~108×** |

---

## Test 2 — Bean Wiring Path (BeanFactory → BeanDefinition)

**Question:** *"How does Spring's BeanFactory connect to a BeanDefinition — what is the call chain?"*

**Standard Workflow (Grep + Read):** Read `BeanFactory.java`, follow the interface hierarchy through `AutowireCapableBeanFactory.java` and `AbstractAutowireCapableBeanFactory.java` (~1,750 lines), then trace through `ConstructorResolver` and `AbstractBeanDefinition.java` (~1,200 lines). 6 large files, all in spring-beans.

**With Project Mapper:** `pm_path from_entity="BeanFactory" to_entity="BeanDefinition"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | No (requires reading 1,750-line class) | 6-hop path confirmed | 6-hop path confirmed |
| Token Cost | ~18,000 | ~64 | ~64 |
| Token Reduction | — | **−99.6%** | **−99.6%** |
| Execution Time | ~6s | 140ms | 140ms |
| Speedup | — | **~43×** | **~43×** |

---

## Test 3 — Handler Mapping Hierarchy (MVC + WebFlux)

**Question:** *"What HandlerMapping implementations does Spring provide, across MVC and WebFlux?"*

**Standard Workflow (Grep + Read):** Search spring-webmvc and spring-webflux separately for HandlerMapping implementations. Read `AbstractHandlerMapping.java`, `RequestMappingHandlerMapping.java`, `RouterFunctionMapping.java` and their WebFlux counterparts. 4–5 reads across two separate modules.

**With Project Mapper:** `pm_impact "HandlerMapping" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | Partial, one module at a time | 10 — MVC + WebFlux unified | 10 — complete |
| Token Cost | ~8,000 | ~490 | ~440 |
| Token Reduction | — | **−94%** | **−94%** |
| Execution Time | ~4s | 37ms | 37ms |
| Speedup | — | **~108×** | **~108×** |

---

## Test 4 — Transaction Management Context

**Question:** *"I'm about to work on Spring's transaction management — what components should I know about?"*

**Standard Workflow (Grep + Read):** Read `TransactionManager.java`, `PlatformTransactionManager.java`, `TransactionTemplate.java`, `TransactionSynchronizationManager.java`, `@Transactional`, `TransactionDefinition.java`, `TransactionStatus.java`, `AbstractPlatformTransactionManager.java` — all in spring-tx. 8 large Java files, returned as raw content with no ranking.

**With Project Mapper:** `pm_context "transaction management"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8+ | 1 | 1 |
| Entities found | 8 files, unranked | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~12,000 | ~1,482 | ~1,064 |
| Token Reduction | — | **−88%** | **−91%** |
| Execution Time | ~6s | 250ms | 250ms |
| Speedup | — | **~24×** | **~24×** |

---

## Test 5 — AOP Advice Hierarchy

**Question:** *"What Advice types does Spring AOP provide?"*

**Standard Workflow (Grep + Read):** Browse `spring-aop/src/main/java/org/springframework/aop/` and `org/aopalliance/intercept/`, read core advice interfaces, then trace through spring-aop, spring-aspects, and spring-tx for concrete implementations. 15+ files across 3 modules; many entries still missed.

**With Project Mapper:** `pm_impact "Advice" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 15+ | 1 | 1 |
| Entities found | ~15–20, misses TX/aspects | 22 — complete, cross-module | 22 — complete |
| Token Cost | ~24,000 | ~994 | ~879 |
| Token Reduction | — | **−96%** | **−96%** |
| Execution Time | ~8s | 37ms | 37ms |
| Speedup | — | **~216×** | **~216×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | ApplicationContext hierarchy | ~5,000 tok | ~277 tok | ~247 tok | **−94%** | **−95%** | ~108× |
| Test 2 | BeanFactory → BeanDefinition | ~18,000 tok | ~64 tok | ~64 tok | **−99.6%** | **−99.6%** | ~43× |
| Test 3 | HandlerMapping hierarchy | ~8,000 tok | ~490 tok | ~440 tok | **−94%** | **−94%** | ~108× |
| Test 4 | Transaction management | ~12,000 tok | ~1,482 tok | ~1,064 tok | **−88%** | **−91%** | ~24× |
| Test 5 | AOP Advice hierarchy | ~24,000 tok | ~994 tok | ~879 tok | **−96%** | **−96%** | ~216× |

---

Geometric mean savings: **~94% token reduction (Full) · ~95% token reduction (Slim)** · **~76× faster navigation**

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/spring-projects/spring-framework /path/to/spring-framework

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/spring-framework" db="spring" incremental=false

# Test 1
pm_impact entity="ApplicationContext" db="spring" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 2
pm_path from_entity="BeanFactory" to_entity="BeanDefinition" db="spring"

# Test 3
pm_impact entity="HandlerMapping" db="spring" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 4
pm_context query="transaction management" db="spring"

# Test 5
pm_impact entity="Advice" db="spring" depth=1 via_kinds=["extends"] exclude_tests=true
```
