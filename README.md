# Local LLM

Локальный технический AI-ассистент для Java, backend, Docker, SQL, архитектуры,
RAG/LLM, объяснения технических вопросов и работы с кодом. Angular-интерфейс,
FastAPI, SQLite, Ollama и `qwen3:8b` запускаются локально, без cloud API и API keys.

## Day 29 - Local LLM Optimization

Day 29 добавляет ручное сравнение неизменённого поведения Day 27 и профиля,
оптимизированного под короткие практические ответы разработчику.

| Setting | Baseline | Optimized |
| --- | --- | --- |
| Ollama model | `qwen3:8b` | `qwen3-dev:8b` (alias тех же весов) |
| Application system prompt | отсутствует | developer-assistant prompt |
| Temperature в запросе | не передаётся | `0.2` |
| Context в запросе | не передаётся | `4096` |
| Max output в запросе | не передаётся | `512` |
| `top_p` в запросе | не передаётся | `0.9` |
| `repeat_penalty` в запросе | не передаётся | `1.08` |
| Thinking | `false` | `false` по умолчанию, можно включить |
| Advanced settings | read-only | temperature `0.0-1.0`, output `256/512/1024`, context `2048/4096`, thinking On/Off |

Baseline сохраняет точный payload Day 27: `model`, полная обычная история,
`stream: false`, `think: false`. Backend не добавляет system message и не передаёт
`options`. Поэтому в метриках его temperature/context/max output показаны как `—`,
а не выдаются за явно заданные значения. Установленная модель содержит defaults
Ollama `temperature=0.6`, `top_p=0.95`, `top_k=20`, `repeat_penalty=1`.

Optimized использует следующий короткий system prompt:

> Ты краткий и практичный помощник разработчика по Java, Spring, SQL, Docker,
> backend, REST, Linux, LLM, RAG и архитектуре. Отвечай на языке пользователя.
> Сначала давай решение, не повторяй вопрос и избегай длинных вступлений. Оформляй
> код в Markdown-блоках, пиши современный читаемый код. Если информации
> недостаточно, прямо скажи об этом; не выдумывай API. Кратко объясняй
> существенные компромиссы и оставайся лаконичным.

`models/qwen3-dev-optimized.Modelfile` воспроизводимо задаёт optimized defaults.
System prompt отправляется backend отдельно, чтобы для каждого запроса сохранить
его точный размер и не применить prompt дважды.

## Quantization

Проверено локально с Ollama `0.35.1`:

```text
architecture        qwen3
parameters          8.2B
context length      40960
embedding length    4096
quantization        Q4_K_M
thinking levels     false, true
```

Официальный `qwen3:8b` уже квантован как `Q4_K_M`. Дополнительная ручная
квантизация не выполнялась: она потребовала бы другой набор весов, усложнила бы
честное сравнение и не нужна для 8 GB VRAM. `qwen3-dev:8b` ссылается на тот же
blob `sha256:a3de86...`, поэтому его quantization также `Q4_K_M`; веса не
копируются.

## Архитектура

```text
Browser :3000
    |
Angular + Nginx
    |
FastAPI :8080
    |-- SQLite /app/data/chats.db
    `-- Ollama :11434
          |-- qwen3:8b
          `-- qwen3-dev:8b
```

- `local-llm_chat_data` хранит существующие чаты и метрики.
- `local-llm_ollama_data` хранит model manifests и общий blob весов.
- `ollama-init` скачивает `qwen3:8b` только при отсутствии и создаёт optimized
  model только при отсутствии.
- Startup migration добавляет `messages.comparison_id` и таблицу
  `message_metrics`, не удаляя историю Day 27.

## Запуск

Обычный воспроизводимый запуск:

```bash
docker compose up -d --build
```

Первый запуск скачивает около 5.2 GB. Следующие запуски используют persistent
volume и не скачивают модель повторно.

Для NVIDIA GPU должен быть установлен NVIDIA Container Toolkit и Docker runtime
должен поддерживать GPU. Тогда запустите Compose с override:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

Проверка offload:

```bash
docker exec ollama ollama ps
nvidia-smi
```

В `ollama ps` ожидается `100% GPU`. Если Docker отвечает `could not select device
driver ... gpu`, NVIDIA runtime недоступен: базовый Compose продолжит работать на
CPU, но будет заметно медленнее. В среде финальной проверки этого репозитория
наблюдалось `100% CPU`; GPU override добавлен, но не может исправить конфигурацию
Docker Engine на хосте.

Открыть после запуска:

- приложение: <http://localhost:3000>;
- API/Swagger: <http://localhost:8080/docs>;
- health: <http://localhost:8080/api/health>;
- Ollama: <http://localhost:11434>.

## Сравнение в UI

1. Создайте или откройте чат.
2. Выберите `Baseline` или `Optimized`.
3. При необходимости раскройте `Настройки модели`.
4. Отправьте обычный запрос либо нажмите `Сравнить Baseline / Optimized`.

Compare выполняет запросы последовательно на одном Ollama. Оба профиля получают
одинаковые user prompt и снимок истории; ответ Baseline не попадает в запрос
Optimized. Экспериментальная тройка сохраняется и отображается рядом, но целиком
исключается из будущего conversation context, чтобы не создавать две
конфликтующие ветки ответа. UI не выбирает победителя.

Для Optimized backend ограничивает историю консервативным char budget: удаляет
старые полные turns, сохраняет system prompt и последние сообщения. Это не
выдаётся за tokenizer estimate. Точные input/output tokens берутся только из
ответа Ollama. Baseline по-прежнему отправляет всю обычную историю Day 27.

## Metrics

Для каждого assistant response SQLite сохраняет реальные provider fields и
нормализованные значения:

- profile, model и фактически выбранные settings;
- request start и application latency;
- Ollama total/load/prompt-eval/generation duration;
- input, output и total tokens;
- prompt и generation tokens/s;
- history message count и chars;
- system, history, user и total prompt chars;
- success и error type.

Ollama durations переводятся из nanoseconds в milliseconds. Скорости считаются
как count / duration seconds. Отсутствующие значения остаются `null` и
показываются в UI как `—`. Failed Ollama attempts тоже сохраняются с
`message_id=null`, `success=false` и типом ошибки.

## CLI benchmark

Скрипт содержит пять prompts: технический факт, Java coding, debugging,
архитектурное сравнение и строгое следование формату.

```bash
python3 scripts/benchmark_profiles.py
python3 scripts/benchmark_profiles.py --runs 3
python3 scripts/benchmark_profiles.py --prompt "Свой вопрос" --runs 3
```

По умолчанию script пытается выгрузить обе модели, записывает первый cold/warm-up
цикл, затем выполняет warm runs. Если локальный Docker/Ollama недоступен для
выгрузки, фаза честно называется `initial`, а не `cold`. Для каждого ответа
печатаются полный текст, таблица metrics и агрегаты avg/min/max latency,
generation tok/s и success rate. `benchmark_results.json` содержит ответы,
metrics и доступные snapshots `nvidia-smi`/`docker stats`; runtime-файл
игнорируется Git.

## API

Обычный запрос:

```json
{
  "content": "Объясни transaction isolation",
  "profile": "optimized",
  "settings": {
    "temperature": 0.2,
    "max_tokens": 512,
    "context_window": 4096,
    "thinking": false
  }
}
```

Backend принимает только `baseline`/`optimized` и никогда не доверяет имени
модели от frontend. Конечный Ollama timeout равен 120 s; frontend использует
135 s для обычного запроса и 260 s для последовательного compare. `finalize`
сбрасывает loading state при timeout, Ollama error, network error и parse error.

## Tests

Backend tests не требуют реальной LLM:

```bash
docker run --rm -v "$PWD/backend:/workspace/backend" -w /workspace python:3.12-slim \
  sh -c 'pip install -q -r backend/requirements.txt -r backend/requirements-dev.txt && PYTHONPATH=backend python -m pytest -q backend/tests'
```

Покрыты профили, propagation параметров, validation, нормализация и persistence
metrics, безопасная migration, история/truncation, fairness compare и ошибки
Ollama. Frontend проверяется production Docker build.

## Диагностика

```bash
docker compose ps -a
docker exec ollama ollama list
docker exec ollama ollama show qwen3:8b
docker exec ollama ollama show --modelfile qwen3:8b
docker exec ollama ollama ps
docker compose logs --no-color backend frontend ollama ollama-init
```

Остановка без удаления истории и моделей:

```bash
docker compose down
```

Не используйте `docker compose down -v`, если volumes нужно сохранить.
