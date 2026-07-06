# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows desktop app (Tkinter) that generates filled-in office spreadsheets for a Russian social-services department. One launcher window (главное меню) exposes independent **features**, each producing an Excel/ODS file:

- **timesheet** (Табель) — Т-13 work-time sheet → `.xls`
- **reestr** (Реестр) — payment registry from input `.xls` files → `.ods` (multi-sheet). An **optional 4th input** — the contract journal «Отчёт по количеству заключённых договоров» (`reestr/journal.py`) — drives the новый/пересмотр/снят marks by comparing this month's contracts to last month's **by FIO** (`reestr_kv["prev_journal"]`; row-number `client_id` is unstable between months). «Пересмотр» can also be set/edited **manually** in a checklist window (`PeresmotrDialog`). Both feed `registry_builder.build(mark_new_fios, mark_peresmotr_fios)`, overriding the auto-heuristic; without a journal/manual edit the behaviour is unchanged.
- **prilozhenie** (Приложение к табелю) — person/day load per social worker, with redistribution on absence → `.xls`
- **proezd** (Проезд) — monthly travel-reimbursement packet (маршрутный лист + заявление) per worker; trips from a file, tickets from a scan (best-effort Windows OCR) → `.ods`. Trip dates are generated from the production calendar's working days with an org rule: **Wednesday is a day off (методический день) unless marked as a transferred working day** (`calendar_years.work_days`); see `proezd/service.travel_days`.
- **uslugi_dengi** (Услуги-Деньги) — services-and-money report from the «071» count report + a free/partial-clients `.xlsx`/`.xls` → `.xlsx` (3 sheets). The free/partial input is read via `parser._load_book` which accepts both `.xlsx` (openpyxl) and `.xls` (an xlrd adapter exposing an openpyxl-compatible cell/max_row/max_column API). Fills a **template that already contains formulas (D/F/G) and tariffs (E)** via `openpyxl` (only inputs C/H/I/J + client sheets are written; Excel recomputes formulas on open). Services matched **by name keyword** (`uslugi_dengi/model.canon_of`). The H/I/J columns (partial-count / partial-money / free-count) are **cumulative year-to-date**: current month = previous month's report + this month's new values from бесплатники-частичники. The previous report is taken from an optional "prev month" file picker, else auto-found in the documents archive (`service.find_prev_report`); January starts fresh. C (from 071) is **not** accumulated.
- **grafiki** (График проверок) — half-year inspection schedule of social workers → `.xlsx` (openpyxl, built from scratch). Columns = weeks (Thursdays) grouped by month, rows = soc-workers from the DB; checks assigned by **rotation** (one worker per week, cycling), «самоконтроль» workers (chosen via checkboxes) excluded. See `grafiki/service.build_schedule`.
- **protokol** (Протокол) — minutes of a department working meeting (методчас) → `.odt` (odfpy, built from scratch, Times New Roman 14). The window has month/year selectors; the **date auto-fills to the last working Wednesday of the month** (`service.last_working_wednesday`, via the production calendar) and the **agenda/topics come from the methodical-hour plan for that month** (`protokol/data/plan.json`, seeded from the real `.doc` plan; `service.default_body(month)` builds agenda + resolutions). Attendees from the DB (checkboxes, all checked); unchecked ones are listed under «Отсутствовали:». № and department also vary; everything is editable in the window before generating.
- **gos_zadanie** (Отчёт по госзаданию) — per-soc-worker «Отчёт о выполнении государственного задания» from the «Отчёт по количеству оказанных услуг … в разбивке» `.xls` → `.ods` (2 sheets: госзадание + дополнительные), built from scratch via `odfpy` (`OpenDocumentSpreadsheet`, merged title via `numbercolumnsspanned`+`CoveredTableCell`). Services are split between the two sheets by an **editable reference** (`gos_zadanie/data/services_seed.json`, `category` = main/dop/skip), matched **by normalized name** (`model.ServiceCatalog`); an unknown service auto-appends as `dop` (reclassifiable). Report columns = services actually present in the source (so it survives a changing service catalog month-to-month). Worker/dept/period auto-extracted from the source header (`parser.parse_source`), editable; «итого» on the main sheet = source «Всего услуг», on the dop sheet = row-sum of dop services.

Cross-cutting: every generated file (all features) is also **archived into the DB** (`documents` table) via `app/core/documents.py` (called from each `gui._generate`); the main menu (scrollable) has a **«Сохранённые документы»** window (`core/documents_gui.py`) to open/save-as/delete archived files.

Source code lives in **`tabel_app/`**. All code comments and UI text are in Russian; keep that convention.

Full reference docs are in **`tabel_app/docs/`**: [`АРХИТЕКТУРА.md`](tabel_app/docs/АРХИТЕКТУРА.md) (MVC/SOLID layers, subsystems — **the load-bearing doc**), [`ОБЗОР.md`](tabel_app/docs/ОБЗОР.md) (whole-app overview), [`БАЗА_ДАННЫХ.md`](tabel_app/docs/БАЗА_ДАННЫХ.md) (DB schema + ER diagram), and one file per feature under `docs/функции/`.

**Architecture rule:** the app follows MVC (`storage`/domain/writers = Model, `service.py` = Controller, `gui.py`/`shell.py` = View; dependencies go View→Controller→Model only) and SOLID. Before adding/changing functionality, read [`docs/АРХИТЕКТУРА.md`](tabel_app/docs/АРХИТЕКТУРА.md), fit the change into the layers, and **update that file** to reflect it.

## Commands

Run all commands from `tabel_app/`.

```
python main.py                                       # launch the app (main menu)
powershell -ExecutionPolicy Bypass -File build.ps1                 # build FULL Tabel.exe (all 8 features, OCR)
powershell -ExecutionPolicy Bypass -File build.ps1 -Variant lite   # build LITE Tabel.exe (7 features, no proezd/cv2/winrt)
```

Two delivery variants are built from one codebase (Open/Closed): **full** (all 8 features incl. proezd + OCR, ~73 MB) and **lite** (7 features, excludes `app.features.proezd`/`cv2`/`winrt`/`numpy`, ~25 MB). `registry.py` registers features softly (try/except), so the lite build with proezd excluded just shows one card fewer; the other 7 (incl. grafiki/protokol/uslugi_dengi/gos_zadanie) are picked up automatically by PyInstaller's static import analysis — no build.ps1 change needed when adding a feature that bundles no resources. Final packaging into a delivery folder (`Табель.exe` + `data/` + `Инструкция.txt`) and `.zip` is done outside the ASCII-only `build.ps1` (Cyrillic names); finished archives live in repo-root `Сборки/`.

There is **no test framework**. Validation is done via hidden self-test entry points in `main.py` (windowed `.exe` has no console, so these write a result/traceback to a `.txt` next to the program):

```
python main.py --selftest                       # build a timesheet → selftest_result.txt
python main.py --selftest-reestr <folder>       # build a reestr from a folder of inputs
python main.py --selftest-pril                  # seed DB + build a prilozhenie
python main.py --selftest-proezd                # build a proezd packet from template tickets
python main.py --selftest-uslugi <folder>       # build a uslugi-dengi report from a folder (071.xls + бесплатники-частичники.xlsx)
python main.py --selftest-protokol              # build a protokol .odt from the first dept's soc-workers in the DB
python main.py --selftest-gos <source.xls>      # build a gos-zadanie report from a «…услуг…в разбивке» .xls
# (grafiki has no self-test: its input is the DB; verify via the GUI)
```

Each self-test writes its output and a `selftest*_result.txt` (an `OK <path>` line or a traceback) next to the program — in source runs, into `tabel_app/`. The repo-root `Реестрыы/` folder is itself a ready set of reestr inputs (gos `_054`, доп `_055`, ИППСУ `402` files); pass it to `--selftest-reestr`.

When changing generation logic, run the relevant self-test and compare the output against a known-good sample: timesheet → `табель май.xls`, reestr → `Реестрыы/РЕЕСТР май.ods`, prilozhenie → root `Приложение_9_Июнь_2026.xls` / `Реестрыы/приложение к табелю.xls`, proezd → samples in root `Проезд/`.

## Hard constraints (read before building or generating)

- **No Microsoft Excel (or any office suite) required.** All file writers are pure-Python: `.xls` (timesheet, prilozhenie) via `xlwt`, `.ods` (reestr, proezd) via `odfpy`. The timesheet harvests its `.xls` template's formatting with `xlrd` (`open_workbook(..., formatting_info=True)`) and replicates rows in `xlwt`. Reading source `.xls` (reestr inputs) also uses `xlrd`. Output extensions are unchanged (`.xls` / `.ods`). Shared `.xls` helpers (RGB-palette allocator + template-style harvester) live in `app/core/xls_util.py`; ODS logical row/cell helpers + Russian number-to-words in `app/features/reestr/ods_build.py` / `num2words_ru.py` (reused by proezd).
- **The project path contains Cyrillic, which breaks PyInstaller.** `build.ps1` works around this by `robocopy`-ing sources to an ASCII build dir (`C:\Users\<user>\tabel_build`), building there, and emitting `dist\Tabel.exe`. Rename to `Табель.exe` for delivery. **Keep `build.ps1` ASCII-only** — Windows PowerShell 5.1 misreads UTF-8-without-BOM.
- Requires `xlrd`, `xlwt`, `odfpy`, `openpyxl` (`pip install -r tabel_app/requirements.txt`). `openpyxl` is used by **uslugi_dengi** to fill an `.xlsx` template **preserving its formulas** (xlwt can't). `pywin32` is **no longer needed** (COM removed) — Excel COM is used only as a one-off dev step to convert the `.xls` sample into the `.xlsx` template, never at runtime. Proezd's ticket OCR is **optional and best-effort** via Windows OCR (`winrt`) + `cv2`; when unavailable it degrades to reading tickets from the trips file. The standalone `neuro/` CRNN OCR experiment is **not wired into the app**.

## Architecture

### Launcher + feature contract
`app/shell.py` renders one card per feature from `app/features/registry.py`. A feature is registered with a single `Feature(...)` line and must provide:
- `app/features/<name>/__init__.py` exporting `FEATURE_KEY`, `FEATURE_TITLE`, `FEATURE_DESCRIPTION`
- `app/features/<name>/gui.py` exporting `open_<name>(master) -> tk.Toplevel`

To add a feature: create the package, implement the opener, add the `Feature(...)` line to `registry.py` (registration is soft — try/except, so a feature excluded from a build is just skipped), and add `--add-data` lines to `build.ps1` for any bundled `data/`/`templates/` resources (destination `features/<name>/...`). See `tabel_app/README.md` for the full step-by-step.

Shared UI component: every feature window shows a **«Отзывы, жалобы и пожелания»** button via `app/core/feedback.py` (`feedback.add_button(parent, window, FEATURE_TITLE)`). It sends an email to `farcrystas@gmail.com` **directly from the app** via **Web3Forms** (`_post_web3forms`, `WEB3FORMS_KEY`; HTTPS POST, no own server, no password in the `.exe`) with diagnostic context (feature, version from `app/core/version.py`, OS); falls back to `mailto`/clipboard if offline. NB: Web3Forms returns 403 to a server-side request without a browser `User-Agent`, so one is set in the request headers. Architecture follows MVC; full details in `tabel_app/docs/АРХИТЕКТУРА.md`.

Clipboard on non-Latin layouts: `app/core/clipboard.py` `enable_cyrillic_clipboard(root)` is called once in `shell.py`. On a Russian keyboard layout Tkinter reports Cyrillic keysyms (`Cyrillic_es/em/che/ef`) for Ctrl+С/М/Ч/Ф, so the default `<<Copy>>/<<Paste>>/<<Cut>>/<<SelectAll>>` (bound to Latin `c/v/x/a`) never fire — copy/paste appears broken. The helper `event_add`s the Cyrillic combos to those virtual events app-wide (one call covers all windows; no double-action since one keypress = one keysym).

Auto-update (so users don't manually copy the .exe around): `app/core/updater.py` + `updater_gui.py`. Single version source = `tabel_app/VERSION` (semver); `build.ps1` stamps it into `version.py` `_EMBEDDED_VERSION` (one-file .exe has no VERSION file) and into Inno via `ISCC /DAppVer=`. Channel = a **public Yandex.Disk folder** holding `version.json` (manifest: per-variant version/path/size/sha256/notes) + both installers; the updater resolves a direct download link via Yandex's public API (no token, stdlib `urllib` like `feedback.py`), compares versions, downloads the installer (streamed, sha256-checked, https-only) and runs it — the Inno installer updates in place via `AppMutex=TabelAppRunningMutex`. `installation_kind()` returns installed/portable/source; **portable** only downloads (never installs over a running one-file exe). Silent check on startup (threaded, UI via `after`) + a "Проверить обновления" button in `shell.py`. `updater.YANDEX_PUBLIC_KEY` is already set to the live public folder (`https://disk.yandex.ru/d/Gb0wzbmbP8rrqw`); on each release bump `tabel_app/VERSION`, build both variants, and regenerate `version.json` with `tools/make_manifest.ps1` before uploading. Bootstrap (1.3.0, first version with the updater) has shipped; current `VERSION` is past it, so 1.3.1+ auto-update. Local test: serve a `version.json` via `python -m http.server`, point `TABEL_UPDATE_MANIFEST` at it and set `TABEL_UPDATE_INSECURE=1`.

Reliability/data: `db.py` `backup_db()` (rotating copies of `app.db` into `data/backups/` on startup before schema migration) and `export_db`/`import_db` (move the whole DB between PCs as one file; "Перенос данных" button in `shell.py`). `app/core/logging_setup.py` logs uncaught exceptions + Tk callback errors to `data/logs/app.log`.

Comfort: `app/core/ui_state.py` persists small UI state to `data/_app/ui_state.json`. Every feature's file dialogs remember the last-used folder via `ui_state.last_dir("save"|"open")` (passed as `initialdir`) + `ui_state.set_last_dir(path, kind)` after a pick — applied across all `app/features/*/gui.py`. The last-selected department is remembered per feature (`ui_state.set_last_dept`/`dept_index`) and restored on window open (timesheet/reestr/prilozhenie/grafiki/protokol).

Archive (Сохранённые документы): `documents_gui.py` supports search-by-title, filter-by-feature, click-to-sort columns, a «Период» column rendered by `documents.params_brief(params_json)`, and a totals line. `documents.last_params(feature)` returns the most recent doc's params for autofill.

Reference data editor: `app/reference_gui.py` (`ReferenceWindow`, opened by the «Справочники» button in `shell.py`) is a single launcher that **reuses** the existing editors scattered in feature GUIs — `timesheet.gui.DepartmentManager/CalendarDialog/SettingsDialog` and `reestr.gui.ClientsManager` — plus DB export/import. It lives at the `app/` View layer (not `core`) since it imports from `features` (keeps `core` free of feature deps).

### Shared core (`app/core/`) — the part that requires cross-file reading
- **`db.py` is the single source of truth.** One SQLite file at `<program dir>/data/app.db` backs the shared features: departments, employees, settings, production calendar, prilozhenie tables (`pril_*`), and reestr clients/workers (`reestr_*`). Each feature's `storage.py` is a thin wrapper over `db.py` — it does **not** own its data. (Proezd keeps its small state — settings, declined-name forms — in per-feature JSON, not the DB.) Full schema + ER diagram: [`tabel_app/docs/БАЗА_ДАННЫХ.md`](tabel_app/docs/БАЗА_ДАННЫХ.md).
- **Seeding/migration is idempotent and flag-gated** via the `meta` table (`seeded`, `ts_migrated`, `reestr_seeded`). `ensure_seeded()` runs once per process. On a fresh DB it seeds from the bundled JSON; on an existing DB it migrates JSON edits in **once**. Crucially, employees are matched by `tab_number`/FIO so their `id`s are preserved — this keeps `pril_*` rows (linked by `employee_id` with `ON DELETE CASCADE`) from being orphaned. Preserve this behavior when touching department/employee sync (`replace_departments` / `_replace_employees`).
- **JSON files are seed defaults only.** After first run the live data is in `app.db`; the `data/<feature>/*.json` files are fallback defaults, not the runtime store. Don't "fix" data by editing JSON expecting it to take effect on an existing install.

### Frozen vs. source path handling (`app/core/storage.py`)
Everything must work both from source and from the PyInstaller one-file `.exe`:
- **User data** → `<program dir>/data/<feature>/` (next to `sys.executable` when frozen; repo `tabel_app/` otherwise).
- **Bundled read-only resources** (templates, default JSON) → `_MEIPASS/features/<feature>/` when frozen, the source package dir otherwise.
Use the `app_base_dir()` / `feature_resource_dir()` / `feature_data_dir()` helpers rather than computing paths ad hoc.

### Spreadsheet writers (pure-Python, no Excel)
Each writer replicates a **template's prototype rows** (header + one model employee/client row + signatures) to the needed count while preserving formatting, then fills data. Layout is hard-coded by cell coordinate (e.g. timesheet day 1 → column E, totals in column U); see the constants block at the top of each writer.
- **timesheet** (`excel_writer.py`, `xlwt`): reads `t13_template.xls` with `xlrd`, translates each cell's XF into an `xlwt.XFStyle` (`app/core/xls_util.TemplateStyles`), copies header rows 1:1, replicates the prototype employee pair N times, and shifts the signature block down by `2*(N-1)`. Weekend fill RGB(51,51,153) via a custom palette slot (`xls_util.ColourPalette`).
- **prilozhenie** (`excel_writer.py`, `xlwt`): built from scratch (Calibri 11) — styles cached by signature, merges via `write_merge`, gray weekend fill `0xE6E6E6`, landscape fit-to-1-page.
- **reestr** (`ods_writer.py`, `odfpy`): loads `reestr_template.ods`, clones prototype `<table:table-row>` elements per sheet (Гос_/Доп/деньги/пересмотр), fills typed cell values, inserts them before each sheet's signature tail. Logical row/column addressing (expanding `number-rows/columns-repeated`), subtree cloning (odfpy nodes can't be `deepcopy`d — they hold `ownerDocument`/sibling back-refs), and `<text:s>` space encoding live in `ods_build.py`.
- **proezd** (`ods_writer.py`, `odfpy`): loads `proezd_template.ods`, fills two sheets (маршрутный лист = trip rows cloned from a prototype, заявление = a statement with the sum in digits and words). Reuses `reestr/ods_build.py` (logical rows/clone) and `reestr/num2words_ru.py` (rubles-in-words). Tickets map 1st→1st onto trips; price is looked up by ticket series, not the scanned number.

- **uslugi_dengi** (`writer.py`, `openpyxl`): loads `uslugi_dengi_template.xlsx` (which keeps its formulas D/F/G + tariffs E), writes only input cells (C from 071; H/I from частичники; J from бесплатники) on the «Услуги-Деньги» sheet and fills the Бесплатники/Частичники sheets (unmerging cells first, since you can't write into merged cells). Output `.xlsx`; Excel recomputes formulas on open.
- **protokol** (`writer.py`, `odfpy`): builds an `.odt` **from scratch** (`OpenDocumentText`) reproducing the sample layout — named paragraph styles (centered-bold title / left body, Times New Roman 14pt), attendees one-per-line, then the editable body lines, then the signature. Bundles **no** template/data (so build.ps1 needs no `--add-data` for it); runs of 2+ spaces are encoded as `<text:s>` (ODT collapses raw spaces).

timesheet/reestr/prilozhenie were validated cell-by-cell against the previous Excel-COM output on identical input (timesheet & prilozhenie: values + fills + merges + fonts identical; reestr: every populated cell identical across all 4 sheets). When changing a writer, regenerate via the matching self-test and diff against a known-good sample.

## Repo layout outside `tabel_app/`
- `Программа Табель/` — the delivered build: `Табель.exe` + its live `data/` (including `app.db`) + `Инструкция.txt` (user manual).
- Root-level `*.xls` / `*.xlsx` and `Реестрыы/` — sample inputs and known-good output files used to verify generation against hand-filled originals.
- `Проезд/` — sample ticket scans and `.ods` outputs for the proezd feature.
- `услуги деньги/` — inputs/samples for the uslugi_dengi feature: «…071.xls» (service counts), `бесплатники-частичники.xlsx` (free/partial clients), sample outputs, and `услуги-деньги_основа.xlsx` (the `.xlsx` the template was derived from). Pass this folder to `--selftest-uslugi`.
- `графики/Графики отд№9/` — sample `.doc` inspection schedules (`график проверок 1-е/2-е полугодие.doc`) the grafiki feature reproduces (1st is a blank template, 2nd is filled with the `///` rotation + «самоконтроль»).
- `протокол/` — samples for the protokol feature: `Протоколы/протоколы отд №5,№9/1-12.odt` (the monthly meeting minutes whose layout protokol reproduces) and `Методический час/План…2025…doc` (the methodical-hour plan; not used at runtime — agenda/resolutions are fixed template text).
- `Сборки/` — packaged portable deliveries: `Табель_полная_portable.zip` (full) and `Табель_без_проезда_portable.zip` (lite); each zip holds a folder with `Табель.exe` + `data/` + `Инструкция.txt`.
- `Установщики/` — Inno Setup installers (`Табель_полная_setup.exe`, `Табель_без_проезда_setup.exe`): install per-user into `%LOCALAPPDATA%\Tabel` / `…\Tabel-lite` (no admin), desktop+Start-menu shortcuts, uninstaller; `data` installed `onlyifdoesntexist`. **Re-running an installer UPDATES the existing install in place (not a second copy)**: fixed `AppId` + `UsePreviousAppDir=yes` + `DisableDirPage=yes` (forced location) + `CloseApplications=yes`; the app creates a named mutex `TabelAppRunningMutex` (`main._create_app_mutex`) that the installer's `AppMutex` detects to ask the user to close it before updating. Build scripts: `tabel_app/installer/{full,lite}.iss` (keep UTF-8 **with BOM** — Inno mangles Cyrillic otherwise; use ASCII `Source` + Cyrillic `DestName`). Compile with `ISCC.exe` (Inno Setup 6, via `winget install JRSoftware.InnoSetup`).
- `neuro/` — a standalone PyTorch CRNN experiment for OCR-ing dot-matrix ticket numbers. **Not imported by the app**; the live proezd OCR uses Windows OCR in `proezd/parser.py`.
