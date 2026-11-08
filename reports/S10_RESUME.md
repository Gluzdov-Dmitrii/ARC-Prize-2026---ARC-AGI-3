# S10 — актуальная точка восстановления

Обновлено 22.09.2026 15:53 UTC.

## Текущий статус

**Сабмит уже принят: ref 56468831, статус PENDING. Повторять submit не нужно.**

- Notebook: https://www.kaggle.com/code/dmitriigluzdov/arc3-s10-scoped-memory
- Версия **3**, run ID `351866512`, private, RTX PRO 6000, Internet Off.
- GPU smoke **COMPLETE**: две игры × четыре действия, 8 действий всего.
- `internal_errors == 0`, распознано 6 одиночных переходов; батч действий пропущен.
- Источник S10 совпал с зафиксированным кодом. Parquet успешно прочитан: ожидаемые
  столбцы и одна техническая строка Phase A. Это placeholder, не результат LB.
- Запрос принят 22.09.2026 15:52:51 UTC; наличие ref и PENDING проверено через API.
- Public/Private score пока не получены. Рабочий чемпион остаётся S4: 3.70 / 3.38.

## Что делать дальше

Прочитать статус именно **56468831**, не создавать новую отправку:

```powershell
kaggle competitions submissions arc-prize-2026-arc-agi-3 --csv
```

После COMPLETE сохранить официальный score и сравнить с S4. При ERROR получить
ошибку/лог, разобраться в причине; не повторять тот же запуск вслепую. Обновить
`experiment_state.json`, текущий документ и журнал. Автоматическое наблюдение
или повтор не настроены.

## Зафиксированные доказательства

Каталог `output/releases/s10-v3/`:

- `arc3_s10_scoped_memory.ipynb`, `kernel-metadata.json`, `build_manifest.json` —
  точная отправленная версия, Inputs, модель, Docker и хеши;
- `artifact_validation.json`, `kaggle_upload_verification.json` — проверки сборки
  и обратное скачивание всех 33 клеток;
- `smoke_validation.json` и `smoke/` — успешная проверка, manifest, summary,
  telemetry и фактический `submission.parquet`;
- **`submit_after_smoke_20260922T155250Z.json`** — ответ ACCEPTED, ref 56468831;
- **`submission_verified.json`** — подтверждение ref в истории, статус PENDING;
- `submit_attempt.log`, `submit_receipt.json`,
  `submit_retry_20260922T134732Z.json` — история двух отказов до окончания smoke.

Точная причина прежних HTTP 400: `FAILED_PRECONDITION`,
`Did not find provided Notebook Output File`. После появления Output запрос принят.
Ранее заблокированный автоматической проверкой диагностический вызов не исполнялся
и не является дополнительной реальной попыткой. Всего: 2 отвергнутых запроса,
1 принятый сабмит.

SHA-256 notebook:
`a9b9773004c08a8d2914efd106326f1f776df26ca5fcbe90a68215c73b97e814`.
SHA-256 S10 memory:
`a247847f4a4b92eefab337940a13a7070b37c4298090aea4ec2e30f91cd6e7ec`.

## Для дальнейшей разработки

Все 17 исполняемых ячеек и 4 модуля v3 совпадают с проверенной v2; изменение v3 —
оформление. 53 теста + 20 subtests прошли на том же коде. Теперь дополнительно
подтверждён GPU smoke, но качество ещё требует официальной оценки.

Алгоритм: `src/s10_scoped_no_impact.py`; сборка/текст: `src/build_sprint_notebook.py`;
режимы: `src/sprint_runtime.py`; оценка: `src/sprint_evaluation.py`.
S4 сохранён в `tmp/kernels/s4-no-impact/` и встроен в notebook как контроль.

Работать с исходниками и создавать следующую версию отдельно. Frozen v3 не
перезаписывать. После нового push номер версии брать из ответа Kaggle. Не менять
одновременно память, модель, serving и бюджет; сохранять сопоставимость экспериментов.
