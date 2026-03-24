# Telegram AI Bot на базе OpenRouter

Бот с искусственным интеллектом и поддержкой множественных чатов.

## Установка

1. **Установите зависимости:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Получите Telegram токен:**
   - Откройте [@BotFather](https://t.me/BotFather)
   - Отправьте `/newbot` и получите токен

3. **Получите OpenRouter API ключ:**
   - Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai/)
   - Создайте ключ в [Keys](https://openrouter.ai/keys)

4. **Настройте `.env`:**
   ```
   TELEGRAM_TOKEN=ваш_токен
   OPENROUTER_API_KEY=ваш_openrouter_ключ
   OPENROUTER_MODEL=google/gemma-2-9b-it:free
   ```

## Запуск

### Локально:
```bash
python main.py
```

### На Render:

1. Запушьте код в GitHub
2. Зарегистрируйтесь на [render.com](https://render.com)
3. Создайте новый **Web Service**
4. Подключите ваш репозиторий
5. Настройте переменные окружения:
   - `TELEGRAM_TOKEN` — токен бота
   - `OPENROUTER_API_KEY` — API ключ OpenRouter
   - `OPENROUTER_MODEL` — модель (опционально)
6. Deploy!

Render автоматически определит `render.yaml` и настроит сервис.

## Команды

- `/start` — Запустить бота
- `/menu` — Показать главное меню

## Кнопки меню

| Кнопка | Описание |
|--------|----------|
| 📋 Список чатов | Показать все чаты |
| ➕ Новый чат | Создать новый чат |
| 🔙 Назад в меню | Вернуться в главное меню |
| Название чата | Переключиться на чат |

## Особенности

- ✅ Множественные чаты на одного пользователя
- ✅ История сообщений в каждом чате
- ✅ Быстрое переключение между чатами
- ✅ Автоматическое создание чата при первом сообщении

## Доступные модели

Измените `OPENROUTER_MODEL` в `.env`:

- `google/gemma-2-9b-it:free` (по умолчанию)
- `mistralai/mistral-7b-instruct:free`
- `microsoft/phi-3-mini-128k-instruct:free`
- `openchat/openchat-7b:free`

[Все модели](https://openrouter.ai/models)
