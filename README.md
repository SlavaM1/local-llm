# Local LLM

Локальный веб-чат для работы с `qwen3:8b` через Ollama. Приложение хранит диалоги в SQLite, передаёт модели всю историю выбранного чата и не использует облачные LLM или внешние API.

## Архитектура

```text
Browser
   │
   ▼
Angular + Nginx
   │
   ▼
FastAPI
   │
   ├── SQLite
   │
   ▼
Ollama
   │
   ▼
Qwen3 8B
```

- **Frontend:** Angular 22, TypeScript, CSS, `marked`, Nginx.
- **Backend:** Python 3.12, FastAPI, SQLAlchemy, SQLite, httpx.
- **LLM:** только локальная `qwen3:8b` через уже запущенную Ollama и её Chat API.
- **Инфраструктура:** Docker Compose и persistent Docker volumes.

Frontend проксирует `/api/*` в контейнер backend. Backend отправляет запросы по адресу `http://ollama:11434/api/chat` с `stream: false`. OpenAI, OpenRouter, Anthropic и другие облачные сервисы не используются.

## Возможности

- создание, открытие и удаление диалогов;
- автоматическое название по первому сообщению;
- постоянная история сообщений;
- передача всей истории текущего диалога модели;
- Markdown, списки, заголовки и блоки кода в ответах;
- обработка ошибок Ollama и SQLite;
- адаптивный интерфейс и блокировка повторной отправки во время ответа.

## Запуск

Требуются Docker, Docker Compose и уже запущенная Ollama с моделью `qwen3:8b`, доступная на host-порту `11434`. Это соответствует исходной конфигурации проекта; приложение не останавливает Ollama и не изменяет её хранилище.

```bash
docker compose up -d --build
```

Compose не скачивает модель и не изменяет существующее хранилище Ollama. Сервис `ollama` внутри этого Compose является лёгким сетевым bridge к уже запущенной Ollama на host-порту `11434`; благодаря этому backend всегда использует требуемый адрес `http://ollama:11434`, не создавая второй сервер и не дублируя модель. Ollama должна принимать соединения через Docker host gateway, как в текущей конфигурации проекта.

Проверить сервисы:

```bash
docker compose ps
```

Открыть после запуска:

- веб-интерфейс: <http://localhost:3000>;
- backend API и Swagger: <http://localhost:8080/docs>;
- health endpoint: <http://localhost:8080/api/health>;
- Ollama на хосте: <http://localhost:11434>.

Порт backend на хосте выбран `8080`; внутри Docker-сети backend слушает `8000`.

## Хранение данных

- история чатов: файл `/app/data/chats.db` в volume `local-llm_chat_data`;
- модель Ollama остаётся в существующем persistent volume запущенного Ollama-сервиса; приложение его не пересоздаёт и не изменяет.

Обычная команда `docker compose down` не удаляет volume истории и не затрагивает внешний volume Ollama. Не используйте флаг `-v`, если историю нужно оставить.

## Контекст диалога

При отправке сообщения backend:

1. сохраняет сообщение пользователя в SQLite;
2. загружает все сообщения текущего диалога по порядку;
3. преобразует их в массив Ollama `messages`;
4. вызывает `POST http://ollama:11434/api/chat`;
5. сохраняет ответ assistant в SQLite;
6. возвращает оба сообщения frontend.

Контексты разных диалогов не смешиваются.

## Настройки

Настройки backend задаются environment-переменными в `compose.yaml`:

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:////app/data/chats.db` | Путь к SQLite |
| `OLLAMA_URL` | `http://ollama:11434` | Адрес Ollama внутри Docker |
| `OLLAMA_MODEL` | `qwen3:8b` | Локальная модель |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | Таймаут ответа модели |
| `CORS_ORIGINS` | `http://localhost:3000` | Разрешённый origin |

## Остановка и логи

Остановить контейнеры с сохранением данных:

```bash
docker compose down
```

Посмотреть все логи:

```bash
docker compose logs -f
```

Логи конкретного сервиса:

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f ollama
```

## Структура

```text
local-llm/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/app/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── compose.yaml
├── .gitignore
└── README.md
```
