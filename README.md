# Stepik API MCP Server

MCP-сервер для управления курсами на [Stepik](https://stepik.org) — создание и редактирование курсов, секций, уроков и степов через Claude или любой MCP-клиент.

## Возможности

24 инструмента, покрывающих всю иерархию Stepik: Course → Section → Unit → Lesson → Step.

### Курсы
| Инструмент | Описание |
|---|---|
| `stepik_list_courses` | Список ваших курсов (как автора) |
| `stepik_get_course` | Детали курса по ID |
| `stepik_create_course` | Создать курс (черновик) |
| `stepik_update_course` | Обновить метаданные курса |
| `stepik_publish_course` | Опубликовать курс |

### Секции
| Инструмент | Описание |
|---|---|
| `stepik_get_sections` | Список секций (модулей) курса |
| `stepik_create_section` | Создать секцию |
| `stepik_update_section` | Обновить название/позицию секции |
| `stepik_delete_section` | Удалить секцию |

### Уроки
| Инструмент | Описание |
|---|---|
| `stepik_get_lessons` | Список уроков в секции |
| `stepik_get_lesson` | Детали урока |
| `stepik_create_lesson` | Создать урок (макс. 64 символа в названии) |
| `stepik_update_lesson` | Обновить урок |
| `stepik_delete_lesson` | Удалить урок |

### Юниты
| Инструмент | Описание |
|---|---|
| `stepik_create_unit` | Привязать урок к секции |

### Степы
| Инструмент | Описание |
|---|---|
| `stepik_get_steps` | Список степов в уроке |
| `stepik_create_text_step` | Текстовый степ (HTML) |
| `stepik_update_text_step` | Обновить текстовый степ (с защитой от перезаписи quiz) |
| `stepik_create_quiz_step` | Квиз (выбор из вариантов) с per-option feedback |
| `stepik_update_quiz_step` | Обновить квиз — вопрос, варианты, фидбэк |
| `stepik_create_matching_step` | Степ на соответствие (matching) |
| `stepik_create_string_step` | Степ с вводом строки (поддержка regex) |
| `stepik_delete_step` | Удалить отдельный степ |

### Прочее
| Инструмент | Описание |
|---|---|
| `stepik_health_check` | Проверить подключение и авторизацию |

## Настройка

Создайте OAuth2 приложение на [Stepik](https://stepik.org/oauth2/applications/) (тип: `client_credentials`) и получите `client_id` и `client_secret`.

## Подключение

### Через uvx (рекомендуется)

Не требует клонирования репозитория — `uvx` сам скачает и запустит сервер:

```json
{
  "mcpServers": {
    "stepik": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/germanKoch/stepik-api-mcp.git",
        "stepik-mcp"
      ],
      "env": {
        "STEPIK_CLIENT_ID": "ваш_client_id",
        "STEPIK_CLIENT_SECRET": "ваш_client_secret"
      }
    }
  }
}
```

### Локальная установка

```bash
git clone https://github.com/germanKoch/stepik-api-mcp.git
cd stepik-api-mcp
uv venv && uv pip install -e .
```

```json
{
  "mcpServers": {
    "stepik": {
      "command": "/path/to/stepik-api-mcp/.venv/bin/stepik-mcp",
      "env": {
        "STEPIK_CLIENT_ID": "ваш_client_id",
        "STEPIK_CLIENT_SECRET": "ваш_client_secret"
      }
    }
  }
}
```

## Примеры использования

### Создать квиз с фидбэком

```
stepik_create_quiz_step(
    lesson_id=123456,
    question="<p>Какой тип данных используется для хранения текста в Python?</p>",
    choices=["int", "str", "list", "dict"],
    correct_indices=[1],
    feedbacks=[
        "int — это целые числа",
        "Верно! str — строковый тип",
        "list — это список",
        "dict — это словарь"
    ]
)
```

### Создать степ на соответствие

```
stepik_create_matching_step(
    lesson_id=123456,
    question="<p>Сопоставьте язык и его создателя:</p>",
    pairs=[
        {"first": "Python", "second": "Гвидо ван Россум"},
        {"first": "C++", "second": "Бьярне Страуструп"},
        {"first": "Java", "second": "Джеймс Гослинг"}
    ]
)
```

### Создать степ с вводом строки (CTF-задача)

```
stepik_create_string_step(
    lesson_id=123456,
    question="<p>Введите флаг:</p>",
    pattern="CTF{s3cr3t_fl4g}",
    case_sensitive=True
)
```

## Порядок создания контента

Stepik требует строгую последовательность:

1. `stepik_create_course` → получить `course_id`
2. `stepik_create_section(course_id=...)` → получить `section_id`
3. `stepik_create_lesson(...)` → получить `lesson_id`
4. `stepik_create_unit(section_id=..., lesson_id=...)` — привязать урок к секции
5. `stepik_create_text_step(lesson_id=...)` / `stepik_create_quiz_step(...)` / ... — добавить контент
6. `stepik_publish_course(course_id=...)` — опубликовать
