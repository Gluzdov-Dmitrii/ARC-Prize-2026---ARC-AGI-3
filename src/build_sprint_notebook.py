"""Build the self-contained, readable S10 Kaggle notebook from reviewed modules."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "notebooks"
PARENT = ROOT / "tmp/kernels/s4-no-impact/duck-qwen3-8-flash-next-nvfp4-mtp.ipynb"
MODEL = "keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": (text.strip() + "\n").splitlines(True)}


def module_cell(source: str, filename: str) -> dict:
    # A visible writefile cell is editable code, not a base64/compressed payload.
    return code(f"%%writefile /kaggle/working/{filename}\n" + source)


def build() -> Path:
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    original = lambda i: "".join(parent["cells"][i]["source"])
    s4_tree = ast.parse(original(13))
    champion_source = next(node.value.value for node in s4_tree.body
                           if isinstance(node, ast.Assign)
                           and any(isinstance(name, ast.Name) and name.id == "S4_SOURCE"
                                   for name in node.targets))
    panels = json.loads((ROOT / "src/eval_panels.json").read_text(encoding="utf-8"))
    modules = {
        "arc3_runtime.py": (ROOT / "src/sprint_runtime.py").read_text(encoding="utf-8"),
        "arc3_s4_baseline.py": champion_source,
        "arc3_s10_memory.py": (ROOT / "src/s10_scoped_no_impact.py").read_text(encoding="utf-8"),
        "arc3_evaluation.py": (ROOT / "src/sprint_evaluation.py").read_text(encoding="utf-8"),
    }
    cells = [md("""
<a id="top"></a>

# ARC-AGI-3

### S10 · Scoped memory

**Локальный агент для незнакомых интерактивных игр**  
Qwen3.8 Flash Next NVFP4 · Duck / TAAF · 22 сентября 2026

S10 уточняет память о действиях без видимого эффекта: каждый факт относится
к своей игре, текущему уровню и конкретному переходу. Базовый агент S4,
модель и производственные лимиты сохранены.

| Измеренная база S4 · Public LB | Новый кандидат S10 |
|:---|:---|
| **3.70 / 3.38** — два запуска | **Public / Private LB пока не измерены** |
| Среднее этих наблюдений: 3.54 | Короткая проверка подтверждает работу кода, не рост качества |

<a id="contents"></a>

### Навигация

| Запуск | Устройство | Проверка и развитие |
|:---|:---|:---|
| [01 · Быстрый старт](#quick-start) | [03 · Цикл агента и память](#agent-memory) | [06 · Результаты](#results) |
| [02 · Среда и модель](#environment) | [04 · Профили и лимиты](#profiles) | [07 · Следующий эксперимент](#next-experiment) |
| [05 · Исполнение](#execution) | [Исходный код модулей](#modules) | [Источники и авторство](#credits) |

Ноутбук самодостаточен при подключённых Kaggle Inputs. Весь добавленный код
доступен ниже; отдельные локальные файлы проекта для запуска не нужны.
"""), md("""
<a id="quick-start"></a>

## 01 · Быстрый старт

1. Выберите **NVIDIA RTX PRO 6000**, установите **Internet → Off** и подключите входы из таблицы.
2. Оставьте `PROFILE="s10_scoped"`, `OFFLINE_MODE="smoke"` в следующей ячейке.
3. Выполните **Save & Run All**. Phase A проверит две публичные игры, максимум по четыре действия.
4. После успешного завершения выберите **Submit to Competition → submission.parquet** для отдельной официальной оценки Phase B.

| Тип Input | Источник |
|:---|:---|
| Competition | `arc-prize-2026-arc-agi-3` |
| Dataset · исходники Duck/TAAF | `keithtyser/duck-qwen38-nvfp4-mtp-vllm-smoke-v1` |
| Dataset · vLLM runtime | `keithtyser/qwen38-flash-next-vllm-nvfp4-runtime-v1` |
| Model · версия 1 | `keithtyser/qwen3-8-flash-next-nvfp4/PyTorch/radixark-modelopt-fp4/1` |

`kernel-metadata.json` содержит эти входы, исходный Kaggle slug и образ Docker.
Модель работает локально внутри Kaggle, без внешнего API.

> **Два разных запуска.** Phase A — проверка исполнения; Phase B — оценка на
> скрытых играх, до 9 часов. В Phase B автоматически включаются полный бюджет,
> все игры gateway и исходная стохастическая генерация.

После изменения профиля выполните **Restart Session**, затем запустите все ячейки по порядку.
"""), code('''# Единственная ячейка повседневных настроек.
PROFILE = "s10_scoped"          # "s4_baseline" — точный алгоритм контрольного S4
OFFLINE_MODE = "smoke"          # "smoke" | "panel" | "public25"
EVAL_PANEL = "validation"       # development | validation | held_public
EVAL_SEED = -1                  # -1: исходная стохастика; 101/202/303: offline A/B
PANEL_SECONDS = 600.0           # Только panel: лимит одной игры
PANEL_ACTIONS = 80              # Только panel: лимит действий одной игры
PANEL_CONCURRENCY = 4           # Только panel: одновременно запущенные игры
'''), md("""
### Основание для выбора S4

| Вариант | Собственный Public LB | Статус |
|:---|---:|:---|
| Flash v3 | 3.39 / 2.95 | исходный агент и serving |
| S4 · память no-impact | **3.70 / 3.38** | контрольная база |
| Внешний Duck Anim · собственный повтор | 2.92 | ниже базы |
| Сокращение истории / scheduler | 2.82 / 2.82 | отклонены |
| Анимации / ACTION7 / RESET guard | 3.13 / 3.10 / 2.81 | отклонены |
| S10 · изоляция и атрибуция памяти | — | новый кандидат |

Это история собственных отправок, проверенная 22.09.2026. Двух повторов
недостаточно для надёжного вывода о величине улучшения или переносе на Private LB.
"""), md("""
<a id="environment"></a>

## 02 · Среда и модель

Сохранены настройки S4: **vLLM · NVFP4 · MTP=3**. MTP ускоряет генерацию
предложением нескольких токенов; веса в этом ноутбуке не обучаются.
Общий девятичасовой бюджет отсчитывается до установки зависимостей.

[↑ Содержание](#contents)
"""), code(original(3)), code('''import hashlib
import importlib
import platform

if PROFILE not in {"s10_scoped", "s4_baseline"}:
    raise ValueError("Unknown PROFILE")
if not TRUE_SUBMISSION and OFFLINE_MODE not in {"smoke", "panel", "public25"}:
    raise ValueError("Unknown OFFLINE_MODE")
print({"profile": PROFILE, "mode": "competition" if TRUE_SUBMISSION else OFFLINE_MODE,
       "python": platform.python_version()})
'''), md("""
### Пакеты из competition wheelhouse

Зависимости устанавливаются из приложенных колёс без интернета. При ошибке
проверьте Competition Input и выбранный Kaggle image.
"""), code(original(5)), md("""
### Исходники Duck/TAAF и локальный vLLM

Bundle содержит runner и сохранённую конфигурацию. Проверка требует ровно
один подходящий bundle; затем setup запускает сервер модели.
""")]
    bundle = original(7).replace(
        '    for marker in Path("/kaggle/input").rglob(DATASET_BUNDLE_MARKER):\n        return marker.parent\n    raise RuntimeError("TAAF source bundle not found under /kaggle/input.")',
        '    markers = sorted(Path("/kaggle/input").rglob(DATASET_BUNDLE_MARKER))\n'
        '    if len(markers) != 1:\n'
        '        raise RuntimeError(f"Expected one TAAF bundle, found {len(markers)}: {markers}")\n'
        '    return markers[0].parent')
    cells += [code(bundle), code(original(9)), code(original(11)), md("""
<a id="agent-memory"></a>

## 03 · Цикл агента и память

**Наблюдение → рассуждение и Python → действие → новое наблюдение → память → следующий ход**

| Шаг | Что происходит |
|:---|:---|
| **1 · Наблюдать** | Duck получает поле, состояние уровня и доступные действия. |
| **2 · Выбрать** | Локальная модель анализирует сцену и пишет Python для проверки идеи или выбора хода. |
| **3 · Выполнить** | TAAF передаёт действие игре и сохраняет новое наблюдение. |
| **4 · Проверить** | S10 сопоставляет свежие снимки до и после одного исполненного действия. |
| **5 · Запомнить** | После двух повторов без изменения игровой области появляется подсказка для этого состояния. |

### Что исправляет S10

| Риск в S4 | Поведение S10 |
|:---|:---|
| Общая память параллельных игр | Отдельная память для агента, пути состояния и уровня |
| Старая сводка после Python без действия | Принимается только свежий исполненный переход |
| Серия LEFT → RIGHT вернула поле назад | Не приписывает суммарный эффект последнему действию |
| Старые координаты и факты после RESET | Координаты входят в ключ; RESET и смена уровня очищают память |

Подсказка действует только для текущего состояния. Она не запрещает команды
и не записывает устаревший совет в постоянные знания модели.

> **Сохранившееся допущение.** Две верхние строки кадра считаются HUD, как в S4.
> Это требует отдельной проверки на новых играх. Универсальных значений цветов,
> таблицы готовых решений и правил выбора действий по game ID здесь нет.

<a id="modules"></a>

### Исходный код модулей

Четыре ячейки `%%writefile` сохраняют показанный код в `/kaggle/working`.
Для запуска менять их не требуется. В HTML-версии длинные модули свёрнуты;
их можно раскрыть для чтения. Профиль выбирается в [быстром старте](#quick-start).

[↑ Содержание](#contents)
"""), md("""
#### 3.1 · Режимы запуска

Офлайн-настройки не изменяют бюджет и выбор игр Phase B.
"""), module_cell(modules["arc3_runtime.py"], "arc3_runtime.py"),
              md("""
#### 3.2 · Контрольный S4

Исходный алгоритм памяти для сравнения с кандидатом.
"""), module_cell(modules["arc3_s4_baseline.py"], "arc3_s4_baseline.py"),
              md("""
#### 3.3 · Память S10

Изоляция состояний, проверка свежести перехода и ограниченный объём памяти.
"""), module_cell(modules["arc3_s10_memory.py"], "arc3_s10_memory.py"),
              md("""
#### 3.4 · Оценка и сравнение

Экспорт нативных результатов TAAF и сравнение совпадающих игр при одинаковых настройках.
"""), module_cell(modules["arc3_evaluation.py"], "arc3_evaluation.py")]
    cells += [md("""
<a id="profiles"></a>

## 04 · Профили и лимиты

В одной сессии устанавливается один профиль: `s10_scoped` или `s4_baseline`.
`run_manifest.json` сохраняет параметры и SHA-256 фактических исходников.
Это позволяет заметить обновление Inputs даже при неизменных названиях datasets.

| Режим | Игры | Секунд / игру | Действий / игру | Параллельность |
|:---|:---|---:|---:|---:|
| `smoke` | первые 2 публичные | 180 | 4 | 2 |
| `panel` | выбранные 8 или 9 | 600 по умолчанию | 80 | 4 |
| `public25` | все 25 публичных | 7920 | без лимита | 28 |
| `competition` | все из gateway | 7920 | без лимита | 28 |

Seed задаётся только для offline. Phase B сохраняет стохастику S4.
Даже одинаковый seed не гарантирует битовую воспроизводимость GPU/vLLM.

[↑ Содержание](#contents)
"""), code('''if str(WORKING_DIR) not in sys.path:
    sys.path.insert(0, str(WORKING_DIR))
from arc3_runtime import resolve_run_config, apply_run_config, source_fingerprints, write_manifest
from arc3_evaluation import write_run_summary
from inference.agent import tool_agent as ta

if globals().get("_ARC3_PROFILE_INSTALLED"):
    raise RuntimeError("Restart Session before reinstalling or changing the profile")
RUN_CONFIG = resolve_run_config(
    true_submission=TRUE_SUBMISSION, profile=PROFILE, offline_mode=OFFLINE_MODE,
    panel=EVAL_PANEL, eval_seed=EVAL_SEED, panel_seconds=PANEL_SECONDS,
    panel_actions=PANEL_ACTIONS, panel_concurrency=PANEL_CONCURRENCY,
)
apply_run_config(bm, target, RUN_CONFIG)
# This module constant is what the actual payload builder reads.
ta._LOCAL_ANALYZER_SEED = RUN_CONFIG["seed"]
hook_module = importlib.import_module(
    "arc3_s10_memory" if PROFILE == "s10_scoped" else "arc3_s4_baseline"
)
install = getattr(hook_module, "install_s10_hooks" if PROFILE == "s10_scoped" else "install_s4_hooks")
install(bm, target=target, working_dir=WORKING_DIR, bundle_dir=BUNDLE_DIR,
        extra={"profile": PROFILE, "mode": RUN_CONFIG["mode"], "parent_public_scores": [3.70, 3.38]},
        source_text=Path(hook_module.__file__).read_text(encoding="utf-8"))
_ARC3_PROFILE_INSTALLED = PROFILE

from inference.agent import prompts as prompt_module
INPUT_HASHES = source_fingerprints({
    "tool_agent": Path(ta.__file__), "prompts": Path(prompt_module.__file__),
    "serving_setup": BUNDLE_DIR / "serving_setup.py",
    "benchmark_initial": BUNDLE_DIR / "benchmark_initial.pkl",
    "deploy_target": BUNDLE_DIR / "deploy_target.pkl",
    "setup_commands": BUNDLE_DIR / "setup_commands.json",
})
EVALUATION_CONFIG = {
    "model": "''' + MODEL + '''", "seed": RUN_CONFIG["seed"],
    "budgets": RUN_CONFIG["budgets"], "panel": RUN_CONFIG["panel"],
    "serving_profile": PUBLIC25_VLLM_PROFILE_ENV, "input_hashes": INPUT_HASHES,
}
write_manifest(WORKING_DIR / "run_manifest.json", {
    "schema_version": 1, "profile": PROFILE, "run_config": RUN_CONFIG,
    "evaluation_config": EVALUATION_CONFIG, "true_submission": TRUE_SUBMISSION,
    "candidate_source_sha256": hashlib.sha256(Path(hook_module.__file__).read_bytes()).hexdigest(),
    "parent_notebook_sha256": "''' + hashlib.sha256(PARENT.read_bytes()).hexdigest() + '''",
    "historical_lb": {"S4": [3.70, 3.38], "S10": None},
})
print(json.dumps(RUN_CONFIG, indent=2))
''')]
    old_run = original(15)
    prefix = old_run.split('if TRUE_SUBMISSION:\n')[0]
    # PUBLIC_GAME_IDS is preserved exactly as the parent; used offline only.
    cells += [md("""
<a id="execution"></a>

## 05 · Исполнение

**Phase B** получает список игр только от gateway. **Offline** выбирает
публичные игры по фиксированной панели. Каждый проход создаёт игру один раз;
RESET не обнуляет уже потраченные действия.

`held_public` — отложенная часть известных публичных игр, а не приватный набор.
Все уровни одной игры остаются в одной панели.

[↑ Содержание](#contents)
"""), code(prefix), code('EVAL_PANELS = ' + repr(panels) + '\n'), code('''from arc3_runtime import select_offline_ids

if TRUE_SUBMISSION:
    os.environ.setdefault("ARC_API_KEY", "test-key-123")
    os.environ.setdefault("ARC_BASE_URL", "http://gateway:8001/")
    _wait_for_gateway(os.environ["ARC_BASE_URL"])
    bm.games = _competition_games()
else:
    offline_games = _offline_games(str(COMPETITION_ROOT / "environment_files"))
    offline_by_id = {game.env_name: game for game in offline_games}
    if len(offline_by_id) != len(offline_games):
        raise RuntimeError("Duplicate offline game IDs")
    if set(offline_by_id) != set(PUBLIC_GAME_IDS):
        raise RuntimeError("Public input changed; review the pinned game list before evaluation")
    selected_ids = select_offline_ids(list(PUBLIC_GAME_IDS), EVAL_PANELS, RUN_CONFIG)
    bm.games = [offline_by_id[game_id] for game_id in selected_ids]

EXPECTED_GAME_IDS = [game.env_name for game in bm.games]
if not EXPECTED_GAME_IDS or len(set(EXPECTED_GAME_IDS)) != len(EXPECTED_GAME_IDS):
    raise RuntimeError("Empty or duplicate game selection")
print({"mode": RUN_CONFIG["mode"], "games": len(EXPECTED_GAME_IDS)})

budget = float(target.max_runtime_s)
soft_end = datetime.fromtimestamp(NOTEBOOK_START_EPOCH) + timedelta(seconds=budget - 600.0)
if datetime.now() >= soft_end:
    raise RuntimeError("Setup exhausted the notebook budget")
'''), md("""
### Запуск и сохранение

Watchdog исходного решения восстанавливает локальный vLLM при сбое.
Мягкий дедлайн оставляет **10 минут** на сохранение и завершение процессов.

Offline-отчёт проверяет полноту выбранного набора и сохраняет нулевые результаты.
В Phase B ошибка диагностического экспорта отмечается отдельно и не отменяет
уже выполненную игру: официальный балл вычисляет Kaggle.
"""), code('''if str(BUNDLE_DIR) not in sys.path:
    sys.path.insert(0, str(BUNDLE_DIR))
import vllm_server_watchdog as vllm_watchdog

vllm_watchdog_setup = vllm_watchdog.load_setup(BUNDLE_DIR / "serving_setup.py")
vllm_watchdog.start_background(
    vllm_watchdog_setup,
    vllm_watchdog.WatchdogConfig(interval_seconds=15.0, request_timeout_seconds=5,
                                failure_threshold=4, max_restart_attempts=2),
)
run_started = time.monotonic()
try:
    await bm.run(soft_end_time=soft_end, runtime_environment=target, minimal_diagnostics=True)
    bm._save_json()
    try:
        summary = write_run_summary(
            bm, WORKING_DIR / "run_summary.json", profile=PROFILE, mode=RUN_CONFIG["mode"],
            expected_game_ids=EXPECTED_GAME_IDS, elapsed_s=time.monotonic() - run_started,
            config=EVALUATION_CONFIG,
        )
    except Exception as export_error:
        if not TRUE_SUBMISSION:
            raise
        # A diagnostic failure must not discard successfully played hidden games.
        # TAAF can return partial results after an individual game crashes.
        summary = {"valid": False, "mode": "competition", "games": [],
                   "diagnostic_error": repr(export_error),
                   "interpretation": "Operational export failed; official scoring is performed by Kaggle."}
        print(summary)
        try:
            write_manifest(WORKING_DIR / "run_summary.json", summary)
        except OSError as write_error:
            print(f"Optional diagnostic write failed: {write_error!r}")
    if not TRUE_SUBMISSION:
        if PROFILE == "s10_scoped":
            telemetry = json.loads((WORKING_DIR / "s10_telemetry.json").read_text())
            if telemetry["counters"]["internal_errors"]:
                raise RuntimeError("S10 instrumentation errors: inspect s10_telemetry.json")
        total_actions = sum(len(run.history) for run in bm.game_runs)
        if total_actions <= 0:
            raise RuntimeError("Model produced no actions; empty smoke cannot pass")
        if RUN_CONFIG["mode"] == "public25":
            from inference.tools.eval import evaluate_runs, save_score_file
            frozen = evaluate_runs([WORKING_DIR])
            save_score_file(frozen, run_dirs=[WORKING_DIR], output_path=WORKING_DIR / "score.json")
        # Platform placeholder for Phase A; this is NOT an evaluation result.
        # Phase B plays the actual gateway and never takes this branch.
        import pandas as pd
        pd.DataFrame([["1_0", "1", True, 1]],
                     columns=["row_id", "game_id", "end_of_game", "score"]).to_parquet(
                         WORKING_DIR / "submission.parquet", index=False)
        print(f"OFFLINE_AUDIT mode={RUN_CONFIG['mode']} games={len(bm.game_runs)} actions={total_actions}")
finally:
    try:
        vllm_watchdog.stop_background(timeout_seconds=15.0)
    finally:
        for command in json.loads((BUNDLE_DIR / "teardown_commands.json").read_text()):
            try:
                subprocess.run(command, shell=True, check=False, cwd=WORKING_DIR,
                               env=_command_env(), timeout=30.0)
            except subprocess.TimeoutExpired:
                print("Teardown exceeded 30 seconds; notebook exit will release its process")
'''), md("""
<a id="results"></a>

## 06 · Результаты

| Файл | Что смотреть |
|:---|:---|
| `run_manifest.json` | Профиль, лимиты, происхождение и хеши кода |
| `run_summary.json` | Игры, уровни, действия, время и нативный score TAAF; поле `valid` |
| `s10_telemetry.json` | События памяти и ошибки инструментации; у контроля — `s4_telemetry.json` |
| `benchmark.json` и артефакты Duck | Подробности исходного прогона |
| `score.json` | Результат exporter исходного harness, только в `public25` |
| `submission.parquet` | Файл для отправки; в offline это технический placeholder |

**Нулевой score в smoke допустим:** четырёх действий обычно недостаточно,
чтобы пройти уровень. Smoke проверяет исполнение; качество сравнивайте в `panel`
или `public25`, а Public / Private LB получайте отдельной конкурсной отправкой.

RHAE учитывает глубину прохождения и число действий. Балл не равен доле выигранных игр.

[↑ Содержание](#contents)
"""), code('''from IPython.display import display
import pandas as pd
report = summary
print({key: value for key, value in report.items() if key not in {"games", "config"}})
display(pd.DataFrame(report["games"]))
if RUN_CONFIG["mode"] == "smoke":
    print("SMOKE ONLY: подтверждает исполнение, не качество и не Public LB.")
'''), md("""
<a id="next-experiment"></a>

## 07 · Следующий эксперимент

1. **Зафиксировать контроль.** Запустить `s4_baseline` и `s10_scoped` в разных
   сессиях с одинаковыми Inputs, моделью, seed, бюджетом и concurrency.
2. **Сравнить на панели.** Выбрать `OFFLINE_MODE="panel"`: сначала development,
   затем validation. Повторить с seed 101, 202 и 303, не выбирать только лучший прогон.
3. **Сохранить доказательства.** Скачать два `run_summary.json` и сравнить их:

```bash
python -m src.sprint_evaluation baseline.json candidate.json --output comparison.json
```

Вне проекта сохраните содержимое ячейки `arc3_evaluation.py` как обычный Python-файл
и передайте те же аргументы. Сравнение проверяет настройки и набор игр, сохраняет
нули, показывает дельты по играм и bootstrap-интервал. Малая публичная выборка
не подтверждает перенос на Private LB.

4. **Проверить перенос.** После выбора конфигурации пройти `held_public`, затем
   при достаточном бюджете — `public25`. Полный public25 по умолчанию выключен.
5. **Изменить один механизм.** Следующие гипотезы: память проверенных правил,
   короткое планирование с проверкой результата или отказ от фиксированной маски HUD.
   Оценивать score вместе с уровнями, действиями, временем и ошибками.

Аргумент в пользу переноса S10 — общий алгоритм и факты из текущей среды.
Это свойство конструкции, а не гарантия высокого скрытого балла.

<a id="credits"></a>

## Источники и авторство

**Агент и harness:** [Tufa Labs · Duck](https://www.kaggle.com/code/jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner).  
**Модельный runtime:** [Keith Tyser · Flash Next NVFP4](https://www.kaggle.com/code/keithtyser/duck-qwen3-8-flash-next-nvfp4-mtp).  
**Изменения проекта:** S4/S10 memory hooks, конфигурация, отчётность и этот notebook.
Чужие компоненты сохраняют свои лицензии и авторство.

[Соревнование](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3) ·
[Метрика RHAE](https://docs.arcprize.org/methodology) ·
[Competition Mode](https://docs.arcprize.org/toolkit/competition_mode) ·
[Официальный Starter](https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter)

[↑ К началу](#top)
""")]
    for index, cell in enumerate(cells):
        cell["id"] = f"arc3-{index:03d}"
        if cell["cell_type"] == "code":
            text = "".join(cell["source"])
            if text.startswith("%%writefile"):
                text = text.split("\n", 1)[1]
            compile(text, f"notebook_cell_{index}", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    notebook = {"nbformat": 4, "nbformat_minor": 5,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                             "language_info": {"name": "python", "version": "3.12"}}, "cells": cells}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "arc3_s10_scoped_memory.ipynb"
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    meta = json.loads((PARENT.parent / "kernel-metadata.json").read_text(encoding="utf-8"))
    meta.pop("id_no", None)
    meta.update(id="dmitriigluzdov/arc3-s10-scoped-memory", title="ARC3 S10 Scoped Memory",
                code_file=path.name, is_private=True)
    (OUT / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (OUT / "build_manifest.json").write_text(json.dumps({
        "notebook_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "parent_sha256": hashlib.sha256(PARENT.read_bytes()).hexdigest(),
        "module_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in modules.items()},
        "cells": len(cells), "code_cells": sum(c["cell_type"] == "code" for c in cells),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Built {path}; cells={len(cells)}; all code compiled")
    return path


if __name__ == "__main__":
    build()
