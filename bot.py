import os
import json
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ─── Config ────────────────────────────────────────────────────────────────────
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
            "Команды:\n"
            "📚 /words — список слов текущего урока\n"
            "✅ /test — проверить слова\n"
            "📊 /stats — мой прогресс"
        )
        return

    keyboard = [
        [InlineKeyboardButton("Я — Ибрахим 👦", callback_data="register_ibrahim")],
        [InlineKeyboardButton("Я — Мухаммад 👦", callback_data="register_muhammad")],
        [InlineKeyboardButton("Я — мама 👩", callback_data="register_mama")],
    ]
    await update.message.reply_text(
        "Привет! Это бот-тренажёр слов для курса английского языка 🇬🇧\n\n"
        "Кто ты?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── Registration callback ──────────────────────────────────────────────────────
async def cb_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    uid = query.from_user.id
    choice = query.data  # register_ibrahim / register_muhammad / register_mama

    if choice == "register_mama":
        data["admin_ids"] = list(set(data.get("admin_ids", []) + [uid]))
        save_data(data)
        await query.edit_message_text(
            "✅ Вы зарегистрированы как мама (администратор).\n\n"
            "Команды:\n"
            "➕ /addwords — добавить слова после урока\n"
            "📊 /report — прогресс детей"
        )
        return

    name = "Ибрахим" if choice == "register_ibrahim" else "Мухаммад"
    data["students"][str(uid)] = {
        "name": name,
        "lessons": {}       # lesson_id → [{"en": ..., "ru": ...}, ...]
    }
    save_data(data)
    await query.edit_message_text(
        f"✅ Привет, {name}! Теперь ты зарегистрирован.\n\n"
        "После каждого урока мама добавит сюда слова.\n"
        "Потом ты сможешь:\n"
        "📚 /words — посмотреть слова\n"
        "✅ /test — пройти тест"
    )

# ─── /addwords (admin only) ─────────────────────────────────────────────────────
# Usage: reply to a student or choose via buttons, then paste word list
# Format mama sends:
#   /addwords Ibrahim 7
#   to admire — восхищаться
#   magnificent — великолепный
#   ...
async def cmd_addwords(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id

    if not is_admin(data, uid):
        await update.message.reply_text("❌ Эта команда только для мамы.")
        return

    # Parse: /addwords <Ibrahim|Muhammad> <lesson_number>
    # Then words on next lines
    full_text = update.message.text or ""
    lines = [l.strip() for l in full_text.strip().split("\n") if l.strip()]

    if len(lines) < 3:
        await update.message.reply_text(
            "📋 Формат добавления слов:\n\n"
            "<code>/addwords Ибрахим 7\n"
            "to admire — восхищаться\n"
            "magnificent — великолепный\n"
            "to explore — исследовать</code>\n\n"
            "Ученик: <b>Ибрахим</b> или <b>Мухаммад</b>\n"
            "После тире — русский перевод.",
            parse_mode="HTML"
        )
        return

    header = lines[0]  # /addwords Ибрахим 7
    parts = header.split()
    if len(parts) < 3:
        await update.message.reply_text("❌ Укажи имя ученика и номер урока.\nПример: /addwords Ибрахим 7")
        return

    student_name = parts[1]  # Ибрахим / Мухаммад
    lesson_id = parts[2]     # 7

    # Find student by name
    target_uid = None
    for sid, sdata in data["students"].items():
        if sdata["name"].lower() == student_name.lower():
            target_uid = sid
            break

    if not target_uid:
        await update.message.reply_text(f"❌ Ученик «{student_name}» не найден. Проверь имя.")
        return

    # Parse word pairs
    words = []
    for line in lines[1:]:
        if "—" in line:
            en, ru = line.split("—", 1)
        elif "-" in line:
            en, ru = line.split("-", 1)
        else:
            continue
        words.append({"en": en.strip(), "ru": ru.strip()})

    if not words:
        await update.message.reply_text("❌ Не нашла ни одного слова. Проверь формат:\nto admire — восхищаться")
        return

    data["students"][target_uid]["lessons"][lesson_id] = words
    save_data(data)

    name = data["students"][target_uid]["name"]
    await update.message.reply_text(
        f"✅ Добавлено {len(words)} слов для {name}, урок #{lesson_id}!\n\n"
        + "\n".join(f"• {w['en']} — {w['ru']}" for w in words)
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

    # Show latest lesson
    latest_lesson = max(lessons.keys(), key=lambda x: int(x))
    words = lessons[latest_lesson]

    text = f"📚 Слова урока #{latest_lesson}:\n\n"
    for w in words:
        text += f"🔹 {w['en']} — {w['ru']}\n"
    text += f"\nВсего: {len(words)} слов\n\nГотов проверить себя? → /test"

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

    # Collect all words from all lessons
    all_words = []
    for lesson_words in lessons.values():
        all_words.extend(lesson_words)

    if not all_words:
        await update.message.reply_text("Слов нет!")
        return

    # Pick random word
    word = random.choice(all_words)

    # Randomly choose direction: EN→RU or RU→EN
    direction = random.choice(["en_to_ru", "ru_to_en"])

    if direction == "en_to_ru":
        question = word["en"]
        answer = word["ru"]
        prompt = f"🇬🇧 Переведи на русский:\n\n<b>{question}</b>"
    else:
        question = word["ru"]
        answer = word["en"]
        prompt = f"🇷🇺 Переведи на английский:\n\n<b>{question}</b>"

    # Save current question in user context
    ctx.user_data["test"] = {
        "answer": answer.lower().strip(),
        "question": question,
        "direction": direction,
        "word": word,
    }

    await update.message.reply_text(prompt, parse_mode="HTML")

# ─── Handle test answers ────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Check if admin is adding words via plain text (shouldn't happen, but guard)
    if is_admin(data, uid):
        await update.message.reply_text(
            "Для добавления слов используй команду:\n"
            "<code>/addwords Ибрахим 7\n"
            "to admire — восхищаться\n"
            "magnificent — великолепный</code>",
            parse_mode="HTML"
        )
        return

    # If there's an active test question
    if "test" in ctx.user_data:
        test = ctx.user_data.pop("test")
        correct = test["answer"]
        word = test["word"]

        # Flexible check: accept if answer is contained or close enough
        user_answer = text.lower().strip()
        is_correct = (
            user_answer == correct or
            correct in user_answer or
            user_answer in correct
        )

        if is_correct:
            # Update stats
            student = get_student(data, uid)
            if student:
                stats = student.setdefault("stats", {"correct": 0, "wrong": 0, "streak": 0})
                stats["correct"] += 1
                stats["streak"] = stats.get("streak", 0) + 1
                save_data(data)
            streak = data["students"][str(uid)]["stats"]["streak"]
            streak_msg = f" 🔥 Серия: {streak}!" if streak >= 3 else ""

            await update.message.reply_text(
                f"✅ Правильно!{streak_msg}\n\n"
                f"🔹 {word['en']} — {word['ru']}\n\n"
                "Следующее слово → /test\nВсе слова → /words"
            )
        else:
            # Update stats
            student = get_student(data, uid)
            if student:
                stats = student.setdefault("stats", {"correct": 0, "wrong": 0, "streak": 0})
                stats["wrong"] += 1
                stats["streak"] = 0
                save_data(data)

            await update.message.reply_text(
                f"❌ Почти! Правильный ответ:\n\n"
                f"🔹 {word['en']} — {word['ru']}\n\n"
                "Попробуй ещё → /test"
            )
        return

    # No active test
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
    lessons = student.get("lessons", {})
    total_words = sum(len(v) for v in lessons.values())

    name = student["name"]
    await update.message.reply_text(
        f"📊 Статистика — {name}\n\n"
        f"📚 Всего слов в базе: {total_words}\n"
        f"✅ Правильных ответов: {stats['correct']}\n"
        f"❌ Ошибок: {stats['wrong']}\n"
        f"🎯 Точность: {pct}%\n"
        f"🔥 Текущая серия: {stats.get('streak', 0)}"
    )

# ─── /report (admin only) ───────────────────────────────────────────────────────
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
        name = sdata["name"]
        stats = sdata.get("stats", {"correct": 0, "wrong": 0, "streak": 0})
        total = stats["correct"] + stats["wrong"]
        pct = round(stats["correct"] / total * 100) if total else 0
        lessons = sdata.get("lessons", {})
        total_words = sum(len(v) for v in lessons.values())

        text += (
            f"👦 {name}\n"
            f"  📚 Слов в базе: {total_words}\n"
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
    app.add_handler(CallbackQueryHandler(cb_register, pattern="^register_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
