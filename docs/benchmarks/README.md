# Project Mapper Benchmarks

Real-world query benchmarks measuring token reduction vs the normal Grep + Read approach.

> **Date format:** ISO 8601 — `YYYY-MM-DD` (year · month · day).

| Report | Language | Files | Entities | Full scan | Geomean savings |
|:---|:---|---:|---:|---:|:---|
| [python-django.md](python-django.md) | Python | 2,418 | 12,140 | 39 s | **~13× Full / ~30× Slim** |
| [javaandkotlin-spring-framework.md](javaandkotlin-spring-framework.md) | Java/Kotlin | 9,622 | 28,604 | 335 s | **~9× Full / ~14× Slim** |
| [csharp-aspnetcore.md](csharp-aspnetcore.md) | C# | 11,083 | 32,936 | 464 s | **~6.5× Full / ~13× Slim** |
| [php-wordpress.md](php-wordpress.md) | PHP | 2,295 | 8,650 | 37 s | **~6.5× Full / ~11× Slim** |
| [c-redis.md](c-redis.md) | C | 781 | 9,647 | < 5 s | **~4× Full / ~11.5× Slim** |
| [ruby-jekyll.md](ruby-jekyll.md) | Ruby | 161 | 382 | < 3 s | **~5× Full / ~10.5× Slim** |
