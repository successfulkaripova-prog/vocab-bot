import os
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

groq_client = Groq(api_key=GROQ_API_KEY)

MODE_PROMPTS = {
    "learn": """Ты репетитор по английскому словарному запасу. Когда пользователь называет слово или просит научить — дай:
1. Слово + транскрипцию
2. Часть речи и перевод на русский
3. Запоминалку или этимологию (откуда слово)
4. 2 живых примера предложений
5. Синонимы/антонимы (2–3 штуки)
Если просит несколько слов по теме — давай каждое по этой же структуре, но кратко. Отвечай на русском с английскими примерами.""",

    "quiz": """Ты репетитор, режим ПРОВЕРКИ. Задавай вопросы на знание слов:
- Переведи слово
- Выбери правильное значение из 3 вариантов
- Вставь слово в предложение
- Назови синоним
После ответа пользователя — оцени, объясни правильный ответ и дай следующий вопрос. Отвечай на русском, слова — на английском.""",

    "context": """Ты репетитор, режим КОНТЕКСТ. Учи слова через истории и диалоги:
- Дай короткий текст (3–5 предложений) на английском с выделенными новыми словами *вот так*
- После текста объясни каждое выделенное слово по-русски
- Задай вопрос по тексту чтобы проверить понимание
Тексты делай интересными — путешествия, истории, ситуации из жизни.""",

    "theme": """Ты репетитор, режим ТЕМЫ. Когда пользователь называет тему — дай 8–10 самых полезных слов по этой теме:
Формат каждого: слово [транскрипция] — перевод — краткий пример
В конце — совет как запомнить эту группу слов. Отвечай на русском.""",

    "phrasal": """Ты репетитор, режим ФРАЗОВЫЕ ГЛАГОЛЫ. Учи phrasal verbs:
1. Глагол + транскрипция
2. Значение (их может быть несколько — дай основные)
3. Разговорный пример для каждого значения
4. Частые ошибки русскоязычных с этим глаголом
5. Похожие фразовые глаголы
Отвечай на русском с английскими примерами.""",
}

LEVEL_CONTEXT = {
    "beginner": "Уровень пользователя: начинающий (A1-A2). Используй простые слова и короткие предложения в примерах.",
    "intermediate": "Уровень пользователя: средний (B1-B2). Примеры могут быть сложнее, вводи идиомы и устойчивые выражения.",
    "advanced": "Уровень пользователя: продвинутый (C1-C2). Вводи редкие слова, нюансы употребления, академический стиль.",
}

MODE_NAMES = {
    "learn": "📖 Учить слова",
    "quiz": "❓ Проверка",
    "context": "💬 В контексте",
    "theme": "🗂 По теме",
    "phrasal": "🔗 Фразовые глаголы",
}

LEVEL_NAMES = {
    "beginner": "🟢 A1–A2",
    "intermediate": "🟡 B1–B2",
    "advanced": "🔴 C1–C2",
}

user_sessions: dict[int, dict] = {}


def get_session(user_id: int) -> dict:
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "learn",
            "level": "intermediate",
            "history": [],
        }
    return user_sessions[user_id]


def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Учить слова", callback_data="mode_learn"),
            InlineKeyboardButton("❓ Проверка", callback_data="mode_quiz"),
        ],
        [
            InlineKeyboardButton("💬 В контексте", callback_data="mode_context"),
            InlineKeyboardButton("🗂 По теме", callback_data="mode_theme"),
        ],
        [
            InlineKeyboardButton("🔗 Фразовые глаголы", callback_data="mode_phrasal"),
        ],
        [
            InlineKeyboardButton("🟢 A1–A2", callback_data="level_beginner"),
            InlineKeyboardButton("🟡 B1–B2", callback_data="level_intermediate"),
            InlineKeyboardButton("🔴 C1–C2", callback_data="level_advanced"),
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    get_session(user_id)
    await update.message.reply_text(
        "👋 Hi! Я ваш репетитор по английскому словарному запасу.\n\n"
        "Выберите режим и уровень кнопками ниже, затем просто напишите слово или тему.\n\n"
        "Например:\n"
        "• «научи слову ambiguous»\n"
        "• «5 слов по теме путешествия»\n"
        "• «проверь меня на 5 слов»",
        reply_markup=main_keyboard(),
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    mode = MODE_NAMES[session["mode"]]
    level = LEVEL_NAMES[session["level"]]
    await update.message.reply_text(
        f"⚙️ Текущие настройки:\nРежим: {mode}\nУровень: {level}",
        reply_markup=main_keyboard(),
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = get_session(user_id)
    data = query.data

    if data.startswith("mode_"):
        mode = data[5:]
        session["mode"] = mode
        session["history"] = []
        await query.edit_message_text(
            f"Режим: {MODE_NAMES[mode]}\nУровень: {LEVEL_NAMES[session['level']]}\n\nПишите слово или тему — начнём!",
            reply_markup=main_keyboard(),
        )
    elif data.startswith("level_"):
        level = data[6:]
        session["level"] = level
        await query.edit_message_text(
            f"Режим: {MODE_NAMES[session['mode']]}\nУровень: {LEVEL_NAMES[level]}\n\nПишите слово или тему — начнём!",
            reply_markup=main_keyboard(),
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session(user_id)
    user_text = update.message.text.strip()

    session["history"].append({"role": "user", "content": user_text})
    if len(session["history"]) > 20:
        session["history"] = session["history"][-20:]

    system_prompt = MODE_PROMPTS[session["mode"]] + "\n\n" + LEVEL_CONTEXT[session["level"]]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            messages=[{"role": "system", "content": system_prompt}] + session["history"],
        )
        reply = response.choices[0].message.content
        session["history"].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply, reply_markup=main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
