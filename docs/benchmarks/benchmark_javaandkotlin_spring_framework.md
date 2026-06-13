# Benchmark: Java/Kotlin — Spring Framework

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `spring-projects/spring-framework` |
| Language | Java / Kotlin |
| Files scanned | 9,622 |
| Total lines | ~1,800,000 |
| Entities indexed | 25,060 |
| Scan time | 20.8 s |
| Throughput | ~86,500 lines/sec |

Geometric mean savings: **~90% token reduction (Full) · ~91% token reduction (Slim)** · **~76× faster navigation**

---

## Test 1 — ApplicationContext Hierarchy

**Question:** *"What ApplicationContext implementations does Spring provide?"*

**Standard Workflow (Grep + Read):** `grep "implements ApplicationContext"` or `grep "extends.*ApplicationContext"` across spring-context, spring-web, spring-webmvc, spring-webflux, spring-test. Each grep returns matches in a different module; requires 5+ reads to understand each implementation's role. Cross-module results are easily missed.

**With Project Mapper:** `pm_impact "ApplicationContext" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial, misses cross-module stubs | 11 — complete, cross-module | 11 — complete, cross-module |
| Token Cost | ~5,000 | ~295 | ~281 |
| Token Reduction | — | **−94%** | **−94%** |
| Execution Time | ~4s | 38ms | 34ms |
| Speedup | — | **~105×** | **~118×** |

---

## Test 2 — Bean Wiring Path (BeanFactory → BeanDefinition)

**Question:** *"How does Spring's BeanFactory connect to a BeanDefinition — what is the call chain?"*

**Standard Workflow (Grep + Read):** Read `BeanFactory.java`, follow the interface hierarchy through `AutowireCapableBeanFactory.java` and `AbstractAutowireCapableBeanFactory.java` (~1,750 lines), then trace through `ConstructorResolver` and `AbstractBeanDefinition.java` (~1,200 lines). 6 large files, all in spring-beans.

**With Project Mapper:** `pm_path from_entity="BeanFactory" to_entity="BeanDefinition"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | No (requires reading 1,750-line class) | 6-hop path confirmed | 6-hop path confirmed |
| Token Cost | ~18,000 | ~74 | ~74 |
| Token Reduction | — | **−99.6%** | **−99.6%** |
| Execution Time | ~6s | 139ms | 139ms |
| Speedup | — | **~43×** | **~43×** |

---

## Test 3 — Handler Mapping Hierarchy (MVC + WebFlux)

**Question:** *"What HandlerMapping implementations does Spring provide, across MVC and WebFlux?"*

**Standard Workflow (Grep + Read):** Search spring-webmvc and spring-webflux separately for HandlerMapping implementations. Read `AbstractHandlerMapping.java`, `RequestMappingHandlerMapping.java`, `RouterFunctionMapping.java` and their WebFlux counterparts. 4–5 reads across two separate modules.

**With Project Mapper:** `pm_impact "HandlerMapping" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | Partial, one module at a time | 15 — MVC + WebFlux unified | 15 — complete |
| Token Cost | ~8,000 | ~488 | ~466 |
| Token Reduction | — | **−94%** | **−94%** |
| Execution Time | ~4s | 36ms | 35ms |
| Speedup | — | **~111×** | **~114×** |

---

## Test 4 — Transaction Management Context

**Question:** *"I'm about to work on Spring's transaction management — what components should I know about?"*

**Standard Workflow (Grep + Read):** Read `TransactionManager.java`, `PlatformTransactionManager.java`, `TransactionTemplate.java`, `TransactionSynchronizationManager.java`, `@Transactional`, `TransactionDefinition.java`, `TransactionStatus.java`, `AbstractPlatformTransactionManager.java` — all in spring-tx. 8 large Java files, returned as raw content with no ranking.

**With Project Mapper:** `pm_context "transaction management"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8+ | 1 | 1 |
| Entities found | 8 files, unranked | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~12,000 | ~1,616 | ~1,262 |
| Token Reduction | — | **−87%** | **−89%** |
| Execution Time | ~6s | 285ms | 281ms |
| Speedup | — | **~21×** | **~21×** |

---

## Test 5 — AOP Advice Hierarchy

**Question:** *"What Advice types does Spring AOP provide?"*

**Standard Workflow (Grep + Read):** Browse `spring-aop/src/main/java/org/springframework/aop/` and `org/aopalliance/intercept/`, read core advice interfaces, then trace through spring-aop, spring-aspects, and spring-tx for concrete implementations. 15+ files across 3 modules; many entries still missed.

**With Project Mapper:** `pm_impact "Advice" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 15+ | 1 | 1 |
| Entities found | ~30–40, misses TX/aspects | 84 — complete, cross-module | 84 — complete |
| Token Cost | ~24,000 | ~905 | ~853 |
| Token Reduction | — | **−96%** | **−96%** |
| Execution Time | ~8s | 37ms | 35ms |
| Speedup | — | **~216×** | **~229×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | ApplicationContext hierarchy | ~5,000 tok | ~295 tok | ~281 tok | **−94%** | **−94%** | ~105× |
| Test 2 | BeanFactory → BeanDefinition | ~18,000 tok | ~74 tok | ~74 tok | **−99.6%** | **−99.6%** | ~43× |
| Test 3 | HandlerMapping hierarchy | ~8,000 tok | ~488 tok | ~466 tok | **−94%** | **−94%** | ~111× |
| Test 4 | Transaction management | ~12,000 tok | ~1,616 tok | ~1,262 tok | **−87%** | **−89%** | ~21× |
| Test 5 | AOP Advice hierarchy | ~24,000 tok | ~905 tok | ~853 tok | **−96%** | **−96%** | ~216× |

---

Geometric mean savings: **~90% token reduction (Full) · ~91% token reduction (Slim)** · **~76× faster navigation**

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
