# Benchmark: PHP — WordPress 7.x

**Date:** 2026-06-10 · **Project Mapper:** v1.5.0

> Real numbers from the [WordPress source repository](https://github.com/WordPress/WordPress) (trunk, version `7.1-alpha-62478`). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `WordPress/WordPress` |
| Version | `7.1-alpha-62478` |
| Date tested | **2026-06-10** |
| Project Mapper | **v1.5.0** |
| PHP files analyzed | **2,295** |
| Areas covered | Core, REST API, Widgets, Customizer, Admin, Themes |

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
| PHP files analyzed | **2,295** |
| Files skipped (unsupported) | 8 |
| Entities indexed | **8,650** |
| Stubs created | 192 |
| Relations mapped | **8,905** |
| Errors | **0** |
| Snapshot size | **6.43 MB** |
| Entity files on disk | **0** (PMEntityStore) |
| **Full scan time** | **37 s** |

### Incremental Scan (zero file changes)

| | |
|:---|:---|
| Files skipped (hash unchanged) | **2,295** |
| **Incremental scan time** | **1.4 s** |
| **Speedup vs full scan** | **26×** |

> **WordPress is primarily procedural PHP.** Its extension system relies on function-based hooks (`add_action` / `add_filter`) rather than class inheritance. PM indexes WordPress's OOP subsystems (Widgets, REST API, Customizer, Admin, Walker) which have well-defined class hierarchies. The broader "plugin activation" or "hook registration" patterns don't produce class-level relations and therefore yield a sparser relation graph (8,905 total) than comparably-sized Java or Python codebases.

---

## Query Benchmarks

The primary purpose of Project Mapper is **token reduction**. Each test below compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

> **"Normal" baseline:** token counts assume the agent already knows which directories contain the answer. On first contact with an unfamiliar codebase, actual reads are typically 2–3× higher.
>
> **Query latency (v1.5.0):** cold miss ~50 ms (6.4 MB snapshot load); warm hits 3–10 ms (in-memory cache, mtime-validated).
>
> **Query scope:** all 5 queries use `impact(via_kinds=["extends"])` — WordPress's OOP class hierarchies are the primary source of structural knowledge. Path and context queries have limited utility in a procedural PHP codebase; the class hierarchy queries are where PM delivers value here.

---

### W1 — Widget Hierarchy

**Question:** *"What widget types does WordPress provide?"*

**Normal approach:** `grep -r "extends WP_Widget"` across `wp-includes/widgets/` (13 files) and `wp-content/themes/` (theme-bundled widgets). Read the main `WP_Widget` base class plus 5–6 concrete widget implementations. Each file is 100–250 lines PHP.

**PM approach:** `impact("WP_Widget", via_kinds=["extends"], exclude_tests=True)`

**22 widget types returned (core + themes):**
```
WP_Widget_Media             WP_Widget_Calendar
WP_Widget_RSS               WP_Widget_Block
WP_Widget_Search            WP_Widget_Recent_Comments
WP_Widget_Nav_Menu          WP_Widget_Meta
WP_Widget_Recent_Posts      WP_Widget_Custom_HTML
WP_Widget_Categories        WP_Widget_Pages
WP_Widget_Archives          WP_Widget_Tag_Cloud
WP_Widget_Links             WP_Widget_Text
WP_Widget_Media_Audio       WP_Widget_Media_Image
WP_Widget_Media_Video       WP_Widget_Media_Gallery
Twenty_Eleven_Ephemera_Widget  Twenty_Fourteen_Ephemera_Widget
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~8,000 | **~1,246** | **~693** |
| Widget types found | Partial (misses theme widgets) | **22 — complete, cross-directory** | **22 — complete** |
| Savings vs Normal | — | **~6.4×** | **~11.5×** |

---

### W2 — REST API Endpoint Catalog

**Question:** *"What REST API endpoints does WordPress provide?"*

**Normal approach:** Browse `wp-includes/rest-api/endpoints/` (≈40 PHP files, 300–700 lines each). Read the base `WP_REST_Controller` class, then browse individual controllers for Posts, Users, Terms, Comments, Settings, Templates, Menus, and more. 8+ reads across a large directory.

**PM approach:** `impact("WP_REST_Controller", via_kinds=["extends"], exclude_tests=True)`

**44 REST controllers returned (complete API catalog):**
```
WP_REST_Posts_Controller        WP_REST_Users_Controller
WP_REST_Comments_Controller     WP_REST_Terms_Controller
WP_REST_Settings_Controller     WP_REST_Templates_Controller
WP_REST_Menus_Controller        WP_REST_Widgets_Controller
WP_REST_Font_Families_Controller WP_REST_Font_Faces_Controller
WP_REST_Global_Styles_Controller WP_REST_Themes_Controller
WP_REST_Plugins_Controller       WP_REST_Blocks_Controller
WP_REST_Attachments_Controller   WP_REST_Autosaves_Controller
WP_REST_Sidebars_Controller      WP_REST_Block_Types_Controller
WP_REST_Search_Controller        ...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 8+ | **1** | **1** |
| Tokens consumed | ~20,000 | **~2,820** | **~1,716** |
| REST controllers found | Partial (easy to miss newer additions) | **44 — complete, full catalog** | **44 — complete** |
| Savings vs Normal | — | **~7.1×** | **~11.7×** |

---

### W3 — Customizer Control Hierarchy

**Question:** *"What Customizer control types does WordPress provide?"*

**Normal approach:** Browse `wp-includes/customize/` for classes extending `WP_Customize_Control`. Read `class-wp-customize-control.php` (large base class), then browse several concrete control files. The Customizer directory contains both panels, sections, and controls — easy to conflate. 6+ reads, ~7,500 tokens.

**PM approach:** `impact("WP_Customize_Control", via_kinds=["extends"], exclude_tests=True)`

**20 Customizer control types returned:**
```
WP_Customize_Color_Control       WP_Customize_Upload_Control
WP_Customize_Image_Control       WP_Customize_Background_Image_Control
WP_Customize_Cropped_Image_Control  WP_Customize_Site_Icon_Control
WP_Customize_Header_Image_Control   WP_Customize_Media_Control
WP_Customize_Code_Editor_Control    WP_Customize_Date_Time_Control
WP_Widget_Form_Customize_Control    ...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~7,500 | **~1,254** | **~756** |
| Control types found | Partial (directory structure mixes panels, sections, controls) | **20 — complete hierarchy** | **20 — complete** |
| Savings vs Normal | — | **~6.0×** | **~9.9×** |

---

### W4 — Admin List Table Hierarchy

**Question:** *"What admin list table types does WordPress provide?"*

**Normal approach:** Search `wp-admin/includes/` for files matching `class-wp-*-list-table.php` (15 files). Read the base `WP_List_Table` class, then browse concrete implementations for Posts, Users, Comments, Plugins, Themes, Media, and Terms. 6+ reads across wp-admin.

**PM approach:** `impact("WP_List_Table", via_kinds=["extends"], exclude_tests=True)`

**21 admin list table types returned:**
```
WP_Posts_List_Table         WP_Users_List_Table
WP_Comments_List_Table      WP_Plugins_List_Table
WP_Themes_List_Table         WP_Media_List_Table
WP_Terms_List_Table          WP_Links_List_Table
WP_MS_Sites_List_Table       WP_MS_Users_List_Table
WP_MS_Themes_List_Table      WP_Plugin_Install_List_Table
WP_Theme_Install_List_Table  WP_Privacy_Requests_Table
_WP_List_Table_Compat        ...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~7,500 | **~1,234** | **~708** |
| List table types found | Partial (misses multisite MS_* tables without explicit search) | **21 — complete, inc. multisite** | **21 — complete** |
| Savings vs Normal | — | **~6.1×** | **~10.6×** |

---

### W5 — Walker Tree-Renderer Hierarchy

**Question:** *"What tree-rendering Walker implementations does WordPress provide?"*

**Normal approach:** `grep -r "extends Walker"` across `wp-includes/` and `wp-admin/includes/`. Walker is used for menus, categories, comments, and page dropdowns — spread across multiple files. Read the base Walker class plus 5–6 concrete implementations. 6+ reads, ~4,000 tokens.

**PM approach:** `impact("Walker", via_kinds=["extends"], exclude_tests=True)`

**10 Walker implementations returned:**
```
Walker_Nav_Menu          Walker_Nav_Menu_Edit
Walker_Nav_Menu_Checklist  Walker_Comment
Walker_Category          Walker_CategoryDropdown
Walker_Category_Checklist  Walker_Page
Walker_PageDropdown      TwentyNineteen_Walker_Comment
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~4,000 | **~568** | **~320** |
| Walker types found | Partial (theme walkers in `wp-content/` easily missed) | **10 — complete, inc. theme walkers** | **10 — complete** |
| Savings vs Normal | — | **~7.0×** | **~12.5×** |

---

## Headline Numbers

| Test | Question | Normal | PM (Full) | PM (Slim) | Savings (Full) | Savings (Slim) |
|:---|:---|:---|:---|:---|:---|:---|
| W1 | Widget hierarchy | ~8,000 tok | **~1,246 tok** | **~693 tok** | **6.4×** | **11.5×** |
| W2 | REST API endpoint catalog | ~20,000 tok | **~2,820 tok** | **~1,716 tok** | **7.1×** | **11.7×** |
| W3 | Customizer control hierarchy | ~7,500 tok | **~1,254 tok** | **~756 tok** | **6.0×** | **9.9×** |
| W4 | Admin list table hierarchy | ~7,500 tok | **~1,234 tok** | **~708 tok** | **6.1×** | **10.6×** |
| W5 | Walker tree-renderer hierarchy | ~4,000 tok | **~568 tok** | **~320 tok** | **7.0×** | **12.5×** |

**Geometric mean savings:** PM Full **~6.5×** · PM Slim **~11×** across all five tests.

> The savings ratios are consistent across all five queries (6–7× Full, 10–12× Slim) because WordPress's OOP subsystems are all "class hierarchy catalogs" — the same query pattern each time. There are no path queries here. WordPress's hook-based extension system (`add_action`, `add_filter`) connects plugins and themes through function calls that don't produce class-level relations, so path queries between major WP types (e.g., `WP_Query` → `wpdb`) return no result. The 6.5× Full / 11× Slim geomean is the realistic floor for a primarily procedural PHP codebase; more OOP-heavy PHP projects (Symfony, Laravel) would see higher multipliers from path and context queries.

---

## Reproducing

```bash
# 1. Clone WordPress
git clone https://github.com/WordPress/WordPress

# 2. Start PM server
cd /path/to/aethvion-project-mapper
python -m uvicorn server:app --port 7474

# IMPORTANT: always use 127.0.0.1, not localhost

# 3. Full scan
curl -X POST http://127.0.0.1:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/WordPress","db":"wordpress","incremental":false}'

# 4. W1 — Widget hierarchy
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"WP_Widget","db":"wordpress","via_kinds":["extends"],"exclude_tests":true}'

# 5. W2 — REST API catalog
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"WP_REST_Controller","db":"wordpress","via_kinds":["extends"],"exclude_tests":true}'

# 6. W5 — Walker tree renderers
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"Walker","db":"wordpress","via_kinds":["extends"],"exclude_tests":true}'
```

---

*Benchmark conducted 2026-06-10 · Aethvion Project Mapper v1.5.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
