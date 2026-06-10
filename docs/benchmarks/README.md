# Project Mapper Benchmarks

Real-world query benchmarks measuring token reduction vs the normal Grep + Read approach.

> **Date format:** ISO 8601 — `YYYY-MM-DD` (year · month · day).

Geomean across 5 representative queries per benchmark. **Normal** = what an AI agent consumes via Grep + Read without Project Mapper.

| Report | Language | Files | Entities | Scan | Normal (tok) | PM Full | PM Slim | Savings |
|:---|:---|---:|---:|---:|---:|---:|---:|:---|
| [django](python-django.md) | Python | 2,418 | 12,140 | 39 s | ~12,000 | **~950** | **~400** | **~13× / ~30×** |
| [spring-framework](javaandkotlin-spring-framework.md) | Java/Kotlin | 9,622 | 28,604 | 335 s | ~12,000 | **~1,300** | **~800** | **~9× / ~14×** |
| [aspnetcore](csharp-aspnetcore.md) | C# | 11,083 | 32,936 | 464 s | ~8,200 | **~1,260** | **~640** | **~6.5× / ~13×** |
| [wordpress](php-wordpress.md) | PHP | 2,295 | 8,650 | 37 s | ~8,200 | **~1,250** | **~730** | **~6.5× / ~11×** |
| [redis](c-redis.md) | C | 781 | 9,647 | < 5 s | ~2,800 | **~710** | **~245** | **~4× / ~11.5×** |
| [jekyll](ruby-jekyll.md) | Ruby | 161 | 382 | < 3 s | ~2,000 | **~390** | **~190** | **~5× / ~10.5×** |
| [zod](typescriptjs-zod.md) | TypeScript/JS | 405 | 1,453 | ~6 s | ~4,800 | **~825** | **~385** | **~5.6× / ~12×** |
| [ripgrep](rust-ripgrep.md) | Rust | 101 | 800 | < 3 s | ~3,500 | **~810** | **~360** | **~4× / ~9.5×** |
| [leveldb](cplusplus-leveldb.md) | C++ | 133 | 216 | < 2 s | ~3,200 | **~550** | **~205** | **~6× / ~15×** |
| [swift-algorithms](swift-algorithms.md) | Swift | 57 | 341 | < 1 s | ~3,100 | **~670** | **~335** | **~4.5× / ~9×** |

> Across all 10 benchmarks the geometric-mean saving is **~6× Full** and **~13× Slim**. At 100,000 input tokens, PM Full costs ~17,000 tokens and PM Slim costs ~7,700 — cutting context by 83–92%.
