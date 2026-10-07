# Local LLM

Веб-чат с выбором LLM и RAG для каждого сообщения. История, ответы и метаданные генерации хранятся в локальной SQLite. По умолчанию используется полностью локальный режим `Qwen3 8B Local + RAG OFF`.

## Четыре режима

| Модель | RAG | Маршрут | Где обрабатываются данные |
| --- | --- | --- | --- |
| Qwen3 8B Local | OFF | backend напрямую вызывает Ollama | полностью локально |
| Qwen3 8B Local | ON | backend вызывает RAG, RAG использует Ollama | полностью локально |
| DeepSeek Flash Cloud | OFF | backend вызывает RAG без retrieval | история и вопрос передаются DeepSeek через RAG |
| DeepSeek Flash Cloud | ON | backend вызывает retrieval и DeepSeek через RAG | история, вопрос и найденный контекст передаются DeepSeek через RAG |

Настройки относятся только к текущей отправке: модель и RAG можно менять между сообщениями одного чата. DeepSeek API key находится только в проекте RAG. Этот проект не принимает, не хранит и не выводит ключ.

**Гарантия полностью локальной работы относится к двум режимам Qwen3.** В них LLM работает в локальной Ollama; при RAG ON embeddings, FAISS, filtering и reranking также выполняются локальным RAG-сервисом. Режимы DeepSeek являются облачными.

## Архитектура

```text
Browser :3000
    |
    v
Angular + Nginx
    |
    v
FastAPI :8000 ---------> SQLite persistent volume
    |
    +-- Qwen + RAG OFF -> Ollama bridge -> host Ollama :11434
    |
    +-- остальные режимы -> RAG :8010
                              |-- local retrieval/indexes
                              |-- Ollama :11434, или
                              +-- DeepSeek cloud
```

Frontend проксирует `/api/*` в backend. Backend передаёт RAG только упорядоченные предыдущие сообщения и отдельно текущий вопрос. Stateless endpoint RAG не записывает историю local-llm.

## Возможности

- создание, открытие и удаление чатов;
- выбор Qwen3/DeepSeek и RAG ON/OFF на каждый запрос;
- постоянная история и метаданные каждого assistant-ответа;
- Markdown-ответы, источники и точные цитаты;
- фактические token counts, latency и provider/retrieval metrics;
- correlation UUID `request_id` в метаданных и backend/RAG логах;
- адаптивный интерфейс и безопасный текстовый вывод sources/quotes;
- независимый degraded health: недоступность Ollama, RAG или DeepSeek не блокирует UI и операции с чатами.

## Запуск

Нужны Docker, Docker Compose и Ollama с моделью `qwen3:8b` на host-порту `11434`.

1. Запустите RAG на `8010`:

```bash
cd /home/slava/ai/rag
docker compose up -d --build
curl -sS http://localhost:8010/health
```

RAG самостоятельно управляет своей конфигурацией DeepSeek. Для полностью локальных Qwen-режимов ключ DeepSeek не нужен.

2. Запустите этот проект:

```bash
cd /home/slava/ai/local-llm
docker compose up -d --build
```

3. Проверьте и откройте:

- frontend: <http://localhost:3000>;
- backend API/Swagger: <http://localhost:8000/docs>;
- backend health: <http://localhost:8000/api/health>;
- RAG health: <http://localhost:8010/health>;
- Ollama: <http://localhost:11434/api/tags>.

Compose-сервис `ollama` является сетевым bridge к уже работающей host Ollama. Он не запускает второй Ollama server, не скачивает модель и не изменяет её хранилище. Backend и frontend стартуют даже при временно недоступных optional generation services; соответствующий запрос вернёт конечную читаемую ошибку.

## Health

`GET /api/health` всегда сообщает состояние backend отдельно от зависимостей:

```json
{
  "status": "degraded",
  "backend": "ok",
  "ollama": "available",
  "rag": "unavailable",
  "deepseek_configured": false,
  "model": "qwen3:8b"
}
```

Endpoint использует короткие конечные таймауты и возвращает HTTP 200, если сам backend работает. `deepseek_configured` поступает из RAG health только как boolean; ключ никогда не возвращается.

## Метрики и evidence

Каждый успешный assistant-ответ получает отдельную строку `message_metadata`, связанную с `messages` one-to-one и удаляемую cascade. Она содержит:

- `request_id`, provider, фактическую model, RAG flag и status;
- JSON metrics, sources и quotes;
- latency, реальные input/output tokens и rates, если provider их сообщил;
- для прямой Ollama: native durations в наносекундах, переведённые в миллисекунды, history size и prompt chars;
- для RAG: retrieval timings/counts/settings, context size и provider metrics из integration response.

Недоступные значения не оцениваются. UI показывает `—` только там, где значение отсутствует. `insufficient_context` сохраняется и отображается как отдельный status вместе с ответом RAG.

## Хранение данных

- SQLite: `/app/data/chats.db` в Docker volume `local-llm_chat_data`;
- таблицы `chats` и `messages` не изменяются;
- новая таблица метаданных создаётся через SQLAlchemy `Base.create_all`, поэтому существующая база продолжает работать;
- Ollama model остаётся в существующем хранилище host Ollama;
- indexes, embeddings cache и собственная SQLite RAG принадлежат `/home/slava/ai/rag`.

`docker compose down` сохраняет историю. Не используйте `docker compose down -v`, если volume чатов нужно оставить.

## Настройки backend

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:////app/data/chats.db` | SQLite history |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama bridge внутри Compose |
| `OLLAMA_MODEL` | `qwen3:8b` | локальная модель |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | таймаут прямой генерации |
| `RAG_SERVICE_URL` | `http://host.docker.internal:8010` | integration endpoint RAG |
| `RAG_TIMEOUT_SECONDS` | `180` | таймаут RAG/DeepSeek запроса |
| `HEALTH_TIMEOUT_SECONDS` | `3` | таймаут каждой health-проверки |
| `CORS_ORIGINS` | `http://localhost:3000` | разрешённый frontend origin |

Host-порт backend по умолчанию `8000`. Если он занят другим локальным stack, задайте, например,
`LOCAL_LLM_BACKEND_PORT=8080`; frontend продолжит обращаться к внутреннему `backend:8000`.

Retrieval settings integration фиксированы: `structural`, `enhanced`, `candidate_top_k=15`, `final_top_k=5`.

## Проверка

```bash
cd backend
pytest -q

# Если Python-зависимости локально не установлены:
cd ..
docker compose run --rm --no-deps backend pytest -q

cd frontend
npm run build

cd ..
docker compose config
```

Тесты backend используют fake Ollama/RAG и не выполняют сетевые LLM-запросы.

## Логи и остановка

```bash
docker compose logs -f backend frontend ollama
docker compose down
```

Логи генерации содержат `request_id`, route, provider/model, status и timings, но не полные сообщения, RAG context или secrets.
