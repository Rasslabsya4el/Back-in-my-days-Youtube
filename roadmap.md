# Дорожная карта Back in my days Youtube

## Сводка проекта

Back in my days Youtube - локальное десктопное приложение для постановки YouTube-ссылок в очередь, выбора сохраненного качества и выпуска детерминированного итогового файла. Основной UI-контур - React + TypeScript + Vite внутри `pywebview`; резервный диагностический контур - Tkinter поверх того же Python-контроллера.

## Критерии успеха

- приложение стабильно запускается в режиме `bridge` при наличии собранного фронтенда и корректно деградирует при отсутствии GUI-бэкенда;
- пользователь может добавить URL, выбрать `Quality` и `File format`, указать выходную папку и запустить загрузку без ручного редактирования состояния;
- итоговый контракт сохраняется как `video -> .mp4`, `audio -> .m4a`;
- аудио-выход сохраняет `title` и `artist`, а обложка добавляется best-effort без падения пайплайна;
- ошибки `yt-dlp`, `ffmpeg`, `ffprobe`, `pywebview` и невалидных URL доходят до UI как короткие пользовательские сообщения, а не как traceback;
- узкие smoke-проверки и компиляционная sanity-проверка проходят на целевой среде.

## Область работ и non-goals

### In scope

- локальная concurrent-очередь загрузок с несколькими параллельными job;
- сохранение и восстановление состояния очереди;
- выбор форматов из сохраненного probe-снимка;
- выпуск финального медиафайла через `yt-dlp` + `ffmpeg`;
- React-shell, bridge-контракт и Tk fallback;
- минимальные smoke-проверки для основных сценариев.

### Non-goals

- облачная синхронизация, аккаунты и многопользовательская работа;
- плейлист-менеджмент, библиотека медиа и каталогизация;
- точный байтовый прогресс по сети и продвинутая телеметрия;
- мобильные клиенты;
- поддержка произвольных видеохостингов вне контракта `yt-dlp` без явного отдельного этапа.

## Предположения и открытые вопросы

- текущая целевая среда по умолчанию - локальный Windows desktop с Poetry-окружением и доступными `ffmpeg`/`ffprobe`;
- `pywebview` остается основным desktop-host, Tk используется как диагностический fallback, а не как равноправный UI-контур;
- текущая активная волна изменений касается аудио-постобработки: метаданные `title`/`artist`, best-effort загрузка thumbnail и вложение cover art;
- поведение новой аудио-ветки пока считать `validation-open`, потому что в рабочем дереве есть незавершенный diff и нет подтвержденного targeted smoke на итоговом `.m4a`;
- требуется решение, должен ли проект коммитить `frontend/dist` как runtime-артефакт или собирать его только локально/в CI;
- требуется уточнить финальный дистрибуционный контракт для bundled `ffmpeg`/`ffprobe` на Windows.

## Кластеры

| Код | Название | Назначение | Зависимости |
| --- | --- | --- | --- |
| `CORE` | Media Core | `yt-dlp` probe/download, ffmpeg postprocess, финальный медиа-контракт | `REL` |
| `PIPE` | App Pipeline | контроллер, очередь, state-store, orchestration glue между UI и core | `CORE`, `OBS` |
| `UI` | Shell Surfaces | React shell, bridge client, Tk fallback, пользовательский поток действий | `PIPE` |
| `OBS` | Diagnostics | smoke-команды, runtime info, inspect-output, классификация ошибок | `CORE`, `PIPE` |
| `REL` | Runtime Packaging | Poetry/bootstrap, бинарные зависимости, desktop-host runtime contract | `CORE`, `UI` |
| `ER` | Validation Runs | targeted smoke, compile sanity, repro-команды и acceptance evidence | `CORE`, `PIPE`, `UI`, `OBS` |
| `EH` | Hardening | пост-валидационная зачистка дефектов, cleanup и совместимость | `ER`, `CORE`, `PIPE` |

## Этапы

### Этап 1. Рабочий baseline

- запуск bridge-shell и Tk fallback без traceback;
- стабильное добавление URL в очередь и восстановление state-файла;
- базовый video/audio pipeline с детерминированным финальным расширением.

### Этап 2. Media contract stabilization

- закрепить контракт выбора форматов из сохраненного probe-состояния;
- довести `.mp4` и `.m4a` postprocess до предсказуемого результата;
- закрыть текущую аудио-волну с evidence по тегам, cover art и cleanup.

### Этап 3. Validation and hardening

- дешевые targeted smoke для startup, probe, bridge и download;
- нормализованные пользовательские ошибки по внешним зависимостям;
- контроль деградации между bridge-shell и Tk fallback.

### Этап 4. Packaging readiness

- зафиксировать runtime contract для `pywebview`, `frontend/dist`, `ffmpeg`, `ffprobe`;
- определить, какие артефакты считаются обязательными для локального запуска и будущей упаковки.

## Начальная очередь задач

| Task ID | Кластер | Задача | Статус |
| --- | --- | --- | --- |
| `TZ-CORE-AUDIO-01` | `CORE` | Верифицировать новую ветку `AudioMetadata`/cover art в `downloader.py` и `postprocess.py`, включая fallback без thumbnail и без channel | `accepted` |
| `TZ-ER-AUDIO-01` | `ER` | Запустить узкий audio smoke с `inspect_output`/`ffprobe` и подтвердить `format_tags` + `attached_pic` на итоговом `.m4a` | `accepted` |
| `TZ-EH-AUDIO-01` | `EH` | После валидации добрать совместимость и cleanup для staged-output/artwork temp files, если найдутся ошибки на реальном ffmpeg | `not_needed` |
| `TZ-OBS-ERROR-01` | `OBS` | Проверить, что блокеры внешних инструментов и сбои postprocess читаемо доходят до UI и smoke-режимов | `accepted` |
| `TZ-REL-RUNTIME-01` | `REL` | Зафиксировать контракт поставки `frontend/dist` и bundled media tools для локального запуска и упаковки | `accepted` |
| `TZ-PIPE-QUEUE-01` | `PIPE` | Подтвердить, что persisted queue/state корректно переживает повторный запуск после смены режима, качества и формата | `accepted` |

## Стратегия валидации

- сначала дешевые и узкие проверки: `py_compile`, targeted smoke, минимальный repro;
- не запускать широкие наборы тестов по умолчанию;
- для любых изменений runtime-поведения требовать минимум одну узкую smoke-проверку на затронутую ветку;
- для media-изменений использовать `inspect_output` или `ffprobe`, а не только факт существования файла;
- acceptance считать неполным, пока нет команды, результата и краткой интерпретации результата.

## Ключевые риски

- поведение `ffmpeg` и контейнера `m4a` различается между версиями, особенно для embedded artwork и copy/transcode fallback;
- `yt-dlp` и доступность YouTube-форматов меняются во времени, из-за чего сохраненные `format_id` могут устаревать;
- `pywebview` зависит от локального GUI backend и может ломать старт even when Python code is healthy;
- наличие `frontend/dist` и зависимость от локальной сборки пока не оформлены как явный release contract;
- обработка временных файлов и замена staged-output требует целенаправленной проверки на Windows path/locking behavior.

## Текущий оркестраторский статус

- проект больше не считать "без плана": корневая дорожная карта заведена;
- активная волна `audio metadata/artwork` принята по `TZ-CORE-AUDIO-01` и `TZ-ER-AUDIO-01`;
- error-surface волна по `TZ-OBS-ERROR-01` принята: наружные контракты для `ffmpeg`, `ffprobe`, `pywebview` и smoke-режимов нормализованы;
- runtime-contract волна по `TZ-REL-RUNTIME-01` принята: README и фактический порядок bridge-launch/tool-resolution выровнены;
- persistence-contract волна по `TZ-PIPE-QUEUE-01` принята: `selected_item_id`, `mode`, `quality` и `selected_format_id` устойчиво переживают restart для active item;
- отчёт с идентификатором `ТЗ-DOS-AUDIO-01` учтён как acceptance-пакет по действующей кластерной схеме `CORE/ER`;
- текущая стартовая волна закрыта; дальнейшие follow-up задачи ставить только по новым дефектам или новой продуктовой инициативе.
