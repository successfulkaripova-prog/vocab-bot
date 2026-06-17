import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.environ["TELEGRAM_TOKEN"]
DATA_FILE = "data.json"

# ─── Data layer ────────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"students": {}, "admin_ids": []}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_student(data: dict, user_id: int) -> dict | None:
    return data["students"].get(str(user_id))

def is_admin(data: dict, user_id: int) -> bool:
    return user_id in data.get("admin_ids", [])

# ─── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    student = get_student(data, uid)

    if student:
        name = student["name"]
        await update.message.reply_text(
            f"👋 С возвращением, {name}!\n\n"
            "📚 /words — слова последнего урока\n"
            "✅ /test — случайный тест\n"
            "📊 /stats — мой прогресс"
        )
        return

    if is_admin(data, uid):
        await update.message.reply_text(
            "👩 Вы уже зарегистрированы как мама.\n\n"
            "➕ /addwords — добавить слова урока\n"
            "📊 /report — прогресс детей"
        )
        return

    keyboard = [
        [InlineKeyboardButton("Я — Ибрахим 👦", callback_data="register_ibrahim")],
        [InlineKeyboardButton("Я — Мухаммад 👦", callback_data="register_muhammad")],
        [InlineKeyboardButton("Я — мама 👩", callback_data="register_mama")],
    ]
    await update.message.reply_text(
        "Привет! Это бот-тренажёр слов для курса английского языка 🇬🇧\n\nКто ты?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── Registration ───────────────────────────────────────────────────────────────
async def cb_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    uid = query.from_user.id
    choice = query.data

    if choice == "register_mama":
        data["admin_ids"] = list(set(data.get("admin_ids", []) + [uid]))
        save_data(data)
        await query.edit_message_text(
            "✅ Вы зарегистрированы как мама.\n\n"
            "➕ /addwords — добавить слова урока\n"
            "📊 /report — прогресс детей"
        )
        return

    name = "Ибрахим" if choice == "register_ibrahim" else "Мухаммад"
    data["students"][str(uid)] = {"name": name, "lessons": {}}
    save_data(data)
    await query.edit_message_text(
        f"✅ Привет, {name}! Ты зарегистрирован.\n\n"
        "После каждого урока мама добавит сюда слова.\n"
        "📚 /words — посмотреть слова\n"
        "✅ /test — пройти тест"
    )

# ─── /addwords — шаг 1: выбор ученика ─────────────────────────────────────────
async def cmd_addwords(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id

    if not is_admin(data, uid):
        await update.message.reply_text("❌ Эта команда только для мамы.")
        return

    students = data.get("students", {})
    if not students:
        await update.message.reply_text("❌ Ученики ещё не зарегистрированы.")
        return

    keyboard = [
        [InlineKeyboardButton(f"👦 {s['name']}", callback_data=f"addw_student_{sid}")]
        for sid, s in students.items()
    ]
    await update.message.reply_text(
        "➕ Добавление слов урока\n\nДля кого слова?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── Шаг 2: выбор номера урока (динамические кнопки) ──────────────────────────
async def cb_addw_student(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    student_id = query.data.replace("addw_student_", "")
    student = data["students"].get(student_id)
    if not student:
        await query.edit_message_text("❌ Ученик не найден.")
        return

    ctx.user_data["addw_student_id"] = student_id
    name = student["name"]

    # Находим последний урок
    lessons = student.get("lessons", {})
    last = max((int(k) for k in lessons.keys()), default=0)

    # 5 кнопок вокруг последнего урока + следующий
    if last == 0:
        nums = [1, 2, 3, 4, 5]
    else:
        start = max(1, last - 1)
        nums = list(range(start, start + 5))

    row = [InlineKeyboardButton(str(n), callback_data=f"addw_lesson_{n}") for n in nums]
    buttons = [
        row,
        [InlineKeyboardButton("✏️ Ввести номер вручную", callback_data="addw_lesson_manual")]
    ]

    last_info = f"Последний урок в базе: #{last}" if last > 0 else "Уроков ещё нет"
    await query.edit_message_text(
        f"👦 Ученик: <b>{name}</b>\n📌 {last_info}\n\nНомер урока?",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )

# ─── Шаг 3а: выбрали номер кнопкой ───────────────────────────────────────────
async def cb_addw_lesson(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    raw = query.data.replace("addw_lesson_", "")

    # Нажали "ввести вручную"
    if raw == "manual":
        ctx.user_data["addw_waiting_lesson_number"] = True
        student_id = ctx.user_data.get("addw_student_id")
        name = data["students"].get(student_id, {}).get("name", "")
        await query.edit_message_text(
            f"👦 Ученик: <b>{name}</b>\n\nНапиши номер урока цифрой:",
            parse_mode="HTML"
        )
        return

    await _ask_for_words(query, ctx, data, raw)

# ─── Шаг 3б: ввели номер вручную ─────────────────────────────────────────────
async def handle_manual_lesson(update: Update, ctx: ContextTypes.DEFAULT_TYPE, data: dict):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Введи просто цифру, например: 12")
        return

    ctx.user_data.pop("addw_waiting_lesson_number", None)
    await _ask_for_words_msg(update, ctx, data, text)

# ─── Общая функция: подтверждение и ожидание списка слов ──────────────────────
async def _ask_for_words(query, ctx, data, lesson_id: str):
    student_id = ctx.user_data.get("addw_student_id")
    if not student_id:
        await query.edit_message_text("❌ Что-то пошло не так. Начни заново — /addwords")
        return

    student = data["students"].get(student_id)
    if not student:
        await query.edit_message_text("❌ Ученик не найден.")
        return

    name = student["name"]
    ctx.user_data["addw_lesson_id"] = lesson_id
    ctx.user_data["addw_waiting"] = True

    existing = student.get("lessons", {}).get(lesson_id)
    note = f"\n⚠️ Урок #{lesson_id} уже есть ({len(existing)} слов) — слова заменятся." if existing else ""

    await query.edit_message_text(
        f"👦 Ученик: <b>{name}</b>\n"
        f"📚 Урок: <b>#{lesson_id}</b>{note}\n\n"
        f"Теперь отправь список слов:\n\n"
        f"<code>to admire — восхищаться\n"
        f"magnificent — великолепный\n"
        f"to explore — исследовать</code>",
        parse_mode="HTML"
    )

async def _ask_for_words_msg(update, ctx, data, lesson_id: str):
    student_id = ctx.user_data.get("addw_student_id")
    student = data["students"].get(student_id)
    name = student["name"]
    ctx.user_data["addw_lesson_id"] = lesson_id
    ctx.user_data["addw_waiting"] = True

    existing = student.get("lessons", {}).get(lesson_id)
    note = f"\n⚠️ Урок #{lesson_id} уже есть ({len(existing)} слов) — слова заменятся." if existing else ""

    await update.message.reply_text(
        f"👦 Ученик: <b>{name}</b>\n"
        f"📚 Урок: <b>#{lesson_id}</b>{note}\n\n"
        f"Теперь отправь список слов:\n\n"
        f"<code>to admire — восхищаться\n"
        f"magnificent — великолепный</code>",
        parse_mode="HTML"
    )

# ─── Шаг 4: получаем и сохраняем список слов ──────────────────────────────────
async def handle_addw_words(update: Update, ctx: ContextTypes.DEFAULT_TYPE, data: dict):
    text = update.message.text.strip()
    student_id = ctx.user_data.get("addw_student_id")
    lesson_id = ctx.user_data.get("addw_lesson_id")

    if not student_id or not lesson_id:
        await update.message.reply_text("❌ Что-то пошло не так. Начни заново — /addwords")
        ctx.user_data.clear()
        return

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    words = []
    for line in lines:
        for sep in ["—", " - "]:
            if sep in line:
                en, ru = line.split(sep, 1)
                words.append({"en": en.strip(), "ru": ru.strip()})
                break

    if not words:
        await update.message.reply_text(
            "❌ Не нашла ни одного слова. Проверь формат:\n\n"
            "<code>to admire — восхищаться\nmagnificent — великолепный</code>",
            parse_mode="HTML"
        )
        return

    name = data["students"][student_id]["name"]
    data["students"][student_id].setdefault("lessons", {})[lesson_id] = words
    data["students"][student_id].setdefault("lesson_dates", {})[lesson_id] = datetime.now().isoformat()
    save_data(data)

    ctx.user_data.pop("addw_waiting", None)
    ctx.user_data.pop("addw_student_id", None)
    ctx.user_data.pop("addw_lesson_id", None)

    word_list = "\n".join(f"• {w['en']} — {w['ru']}" for w in words)
    await update.message.reply_text(
        f"✅ Сохранено <b>{len(words)} слов</b> для {name}, урок #{lesson_id}!\n\n"
        f"{word_list}\n\n"
        f"Добавить ещё? → /addwords",
        parse_mode="HTML"
    )

# ─── /words ────────────────────────────────────────────────────────────────────
async def cmd_words(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    student = get_student(data, uid)

    if not student:
        await update.message.reply_text("Сначала зарегистрируйся — /start")
        return

    lessons = student.get("lessons", {})
    if not lessons:
        await update.message.reply_text("📭 Слов пока нет. После урока мама добавит их сюда!")
        return

    latest = max(lessons.keys(), key=lambda x: int(x))
    words = lessons[latest]

    text = f"📚 Слова урока #{latest}:\n\n"
    text += "\n".join(f"🔹 {w['en']} — {w['ru']}" for w in words)
    text += f"\n\nВсего: {len(words)} слов\n\nГотов проверить себя? → /test"
    await update.message.reply_text(text)

# ─── /test ─────────────────────────────────────────────────────────────────────
async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    student = get_student(data, uid)

    if not student:
        await update.message.reply_text("Сначала зарегистрируйся — /start")
        return

    lessons = student.get("lessons", {})
    if not lessons:
        await update.message.reply_text("📭 Слов пока нет. После урока мама добавит их сюда!")
        return

    all_words = [w for lesson_words in lessons.values() for w in lesson_words]
    word = random.choice(all_words)
    direction = random.choice(["en_to_ru", "ru_to_en"])

    if direction == "en_to_ru":
        prompt = f"🇬🇧 Переведи на русский:\n\n<b>{word['en']}</b>"
        answer = word["ru"]
    else:
        prompt = f"🇷🇺 Переведи на английский:\n\n<b>{word['ru']}</b>"
        answer = word["en"]

    ctx.user_data["test"] = {"answer": answer.lower().strip(), "word": word}
    await update.message.reply_text(prompt, parse_mode="HTML")

# ─── Handle all messages ───────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Мама
    if is_admin(data, uid):
        if ctx.user_data.get("addw_waiting"):
            await handle_addw_words(update, ctx, data)
        elif ctx.user_data.get("addw_waiting_lesson_number"):
            await handle_manual_lesson(update, ctx, data)
        else:
            await update.message.reply_text(
                "Команды для мамы:\n"
                "➕ /addwords — добавить слова урока\n"
                "📊 /report — прогресс детей"
            )
        return

    # Ученик — период-тест (еженедельный / ежемесячный)
    if "period_test" in ctx.user_data:
        pt = ctx.user_data["period_test"]
        user_answer = text.lower().strip()
        correct = pt["answer"]
        word = pt["words"][pt["index"]]
        is_correct = (user_answer == correct or correct in user_answer or user_answer in correct)

        if is_correct:
            pt["correct"] += 1
            feedback = f"✅ Правильно! {word['en']} — {word['ru']}"
        else:
            pt["wrong"] += 1
            feedback = f"❌ Нет. Правильно: {word['en']} — {word['ru']}"

        pt["index"] += 1

        if pt["index"] >= pt["total"]:
            # Тест завершён
            ctx.user_data.pop("period_test")
            total = pt["total"]
            correct_count = pt["correct"]
            pct = round(correct_count / total * 100)
            label = pt['label']
            emoji = "🌟 Отлично!" if pct >= 80 else "💪 Нужно повторить!" if pct >= 50 else "📚 Повтори слова ещё раз!"
            msg = feedback + "\n\n" + f"🏁 {label} завершена!\n\n" + f"📊 Результат: {correct_count} / {total} ({pct}%)\n" + emoji
            await update.message.reply_text(msg)
        else:
            # Следующий вопрос
            next_word = pt["words"][pt["index"]]
            direction = random.choice(["en_to_ru", "ru_to_en"])
            pt["direction"] = direction
            if direction == "en_to_ru":
                prompt = f"🇬🇧 {next_word['en']}"
                pt["answer"] = next_word["ru"].lower().strip()
            else:
                prompt = f"🇷🇺 {next_word['ru']}"
                pt["answer"] = next_word["en"].lower().strip()

            idx = pt['index'] + 1
            tot = pt['total']
            next_msg = feedback + "\n\n" + f"Вопрос {idx} / {tot}:\n{prompt}\n\nНапиши перевод:"
            await update.message.reply_text(next_msg)
        return

    # Ученик — активный тест
    if "test" in ctx.user_data:
        test = ctx.user_data.pop("test")
        correct = test["answer"]
        word = test["word"]
        user_answer = text.lower().strip()

        is_correct = (user_answer == correct or correct in user_answer or user_answer in correct)

        student = get_student(data, uid)
        if student:
            stats = student.setdefault("stats", {"correct": 0, "wrong": 0, "streak": 0})
            if is_correct:
                stats["correct"] += 1
                stats["streak"] = stats.get("streak", 0) + 1
            else:
                stats["wrong"] += 1
                stats["streak"] = 0
            save_data(data)

        if is_correct:
            streak = data["students"][str(uid)]["stats"]["streak"]
            streak_msg = f" 🔥 Серия: {streak}!" if streak >= 3 else ""
            await update.message.reply_text(
                f"✅ Правильно!{streak_msg}\n\n"
                f"🔹 {word['en']} — {word['ru']}\n\n"
                "Следующее слово → /test"
            )
        else:
            await update.message.reply_text(
                f"❌ Почти! Правильный ответ:\n\n"
                f"🔹 {word['en']} — {word['ru']}\n\n"
                "Попробуй ещё → /test"
            )
        return

    await update.message.reply_text(
        "Команды:\n"
        "📚 /words — слова урока\n"
        "✅ /test — тест\n"
        "📊 /stats — мой прогресс"
    )

# ─── /stats ────────────────────────────────────────────────────────────────────
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    student = get_student(data, uid)

    if not student:
        await update.message.reply_text("Сначала зарегистрируйся — /start")
        return

    stats = student.get("stats", {"correct": 0, "wrong": 0, "streak": 0})
    total = stats["correct"] + stats["wrong"]
    pct = round(stats["correct"] / total * 100) if total else 0
    total_words = sum(len(v) for v in student.get("lessons", {}).values())

    await update.message.reply_text(
        f"📊 Статистика — {student['name']}\n\n"
        f"📚 Всего слов в базе: {total_words}\n"
        f"✅ Правильных: {stats['correct']}\n"
        f"❌ Ошибок: {stats['wrong']}\n"
        f"🎯 Точность: {pct}%\n"
        f"🔥 Текущая серия: {stats.get('streak', 0)}"
    )

# ─── /report (admin) ───────────────────────────────────────────────────────────
async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id

    if not is_admin(data, uid):
        await update.message.reply_text("❌ Эта команда только для мамы.")
        return

    students = data.get("students", {})
    if not students:
        await update.message.reply_text("Ученики ещё не зарегистрированы.")
        return

    text = "📊 Отчёт по ученикам:\n\n"
    for sid, sdata in students.items():
        stats = sdata.get("stats", {"correct": 0, "wrong": 0, "streak": 0})
        total = stats["correct"] + stats["wrong"]
        pct = round(stats["correct"] / total * 100) if total else 0
        total_words = sum(len(v) for v in sdata.get("lessons", {}).values())
        lessons_count = len(sdata.get("lessons", {}))

        text += (
            f"👦 {sdata['name']}\n"
            f"  📚 Уроков в базе: {lessons_count}\n"
            f"  🔤 Слов всего: {total_words}\n"
            f"  ✅ Правильно: {stats['correct']} / {total} ({pct}%)\n"
            f"  🔥 Серия: {stats.get('streak', 0)}\n\n"
        )

    await update.message.reply_text(text)

# ─── Main ───────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("words", cmd_words))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("addwords", cmd_addwords))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("weeklytest", cmd_weeklytest))
    app.add_handler(CommandHandler("monthlytest", cmd_monthlytest))
    app.add_handler(CallbackQueryHandler(cb_register, pattern="^register_"))
    app.add_handler(CallbackQueryHandler(cb_addw_student, pattern="^addw_student_"))
    app.add_handler(CallbackQueryHandler(cb_addw_lesson, pattern="^addw_lesson_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()

# ─── Helpers: собрать слова за период ──────────────────────────────────────────
def get_words_for_period(student: dict, days: int) -> list:
    """Возвращает слова из уроков добавленных за последние N дней."""
    lessons = student.get("lessons", {})
    lesson_dates = student.get("lesson_dates", {})
    cutoff = datetime.now() - timedelta(days=days)

    words = []
    for lesson_id, lesson_words in lessons.items():
        date_str = lesson_dates.get(lesson_id)
        if date_str:
            lesson_date = datetime.fromisoformat(date_str)
            if lesson_date >= cutoff:
                words.extend(lesson_words)
        else:
            # Если дата урока не сохранена — включаем всё (для старых уроков)
            words.extend(lesson_words)
    return words

async def run_period_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE, words: list, label: str):
    """Запускает тест по набору слов с итогом в конце."""
    if not words:
        await update.message.reply_text(f"📭 Нет слов для {label} теста.")
        return

    random.shuffle(words)
    ctx.user_data["period_test"] = {
        "words": words,
        "index": 0,
        "correct": 0,
        "wrong": 0,
        "label": label,
        "total": len(words),
    }

    word = words[0]
    direction = random.choice(["en_to_ru", "ru_to_en"])
    ctx.user_data["period_test"]["direction"] = direction

    if direction == "en_to_ru":
        prompt = f"🇬🇧 {word['en']}"
        ctx.user_data["period_test"]["answer"] = word["ru"].lower().strip()
    else:
        prompt = f"🇷🇺 {word['ru']}"
        ctx.user_data["period_test"]["answer"] = word["en"].lower().strip()

    await update.message.reply_text(
        f"🧪 {label}\n"
        f"Всего слов: {len(words)}\n\n"
        f"Вопрос 1 / {len(words)}:\n{prompt}\n\n"
        "Напиши перевод:"
    )

# ─── /weeklytest ───────────────────────────────────────────────────────────────
async def cmd_weeklytest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    student = get_student(data, uid)

    if not student:
        await update.message.reply_text("Сначала зарегистрируйся — /start")
        return

    words = get_words_for_period(student, days=7)
    if not words:
        # Если нет слов за 7 дней — берём последние 2 урока
        lessons = student.get("lessons", {})
        sorted_lessons = sorted(lessons.keys(), key=lambda x: int(x), reverse=True)[:2]
        words = [w for lid in sorted_lessons for w in lessons[lid]]

    await run_period_test(update, ctx, words, "📅 Еженедельная проверка")

# ─── /monthlytest ──────────────────────────────────────────────────────────────
async def cmd_monthlytest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    student = get_student(data, uid)

    if not student:
        await update.message.reply_text("Сначала зарегистрируйся — /start")
        return

    words = get_words_for_period(student, days=30)
    if not words:
        # Если дат нет — берём все слова из базы
        lessons = student.get("lessons", {})
        words = [w for lesson_words in lessons.values() for w in lesson_words]

    await run_period_test(update, ctx, words, "📆 Ежемесячная проверка")

