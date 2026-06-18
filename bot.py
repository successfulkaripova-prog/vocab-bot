import os
import re
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

def get_student(data: dict, user_id: int):
    return data["students"].get(str(user_id))

def is_admin(data: dict, user_id: int) -> bool:
    return user_id in data.get("admin_ids", [])

def get_all_words(student: dict) -> list:
    return [w for lesson_words in student.get("lessons", {}).values() for w in lesson_words]

def normalize(text: str) -> str:
    """Нормализует ответ для мягкой проверки."""
    t = text.lower().strip()
    # Убираем транскрипцию [ˈɒbstəkl]
    t = re.sub(r"\[.*?\]", "", t).strip()
    # Убираем 'to ' в начале английских слов
    if t.startswith("to "):
        t = t[3:]
    # Убираем знаки препинания
    t = t.strip(".,!?;:-")
    return t

def is_answer_correct(user_answer: str, correct: str) -> bool:
    """Мягкая проверка: точное совпадение или совпадение корней."""
    u = normalize(user_answer)
    c = normalize(correct)

    if u == c:
        return True

    # Прямое вхождение
    if u in c or c in u:
        return True

    # Сравниваем корни: убираем окончания глаголов RU и EN
    ru_endings = ["ться", "ать", "ять", "еть", "ить", "уть", "овать", "евать", "ивать",
                  "тся", "ся", "ть"]
    en_endings = ["ing", "tion", "ed", "er", "ly", "ness", "ment"]

    def get_root(word, endings):
        for e in sorted(endings, key=len, reverse=True):
            if word.endswith(e) and len(word) > len(e) + 2:
                return word[:-len(e)]
        return word

    u_root = get_root(u, ru_endings + en_endings)
    c_root = get_root(c, ru_endings + en_endings)

    if len(u_root) >= 3 and (u_root in c_root or c_root in u_root):
        return True

    return False

def get_words_for_period(student: dict, days: int) -> list:
    lessons = student.get("lessons", {})
    lesson_dates = student.get("lesson_dates", {})
    cutoff = datetime.now() - timedelta(days=days)
    words = []
    for lesson_id, lesson_words in lessons.items():
        date_str = lesson_dates.get(lesson_id)
        if date_str:
            if datetime.fromisoformat(date_str) >= cutoff:
                words.extend(lesson_words)
        else:
            words.extend(lesson_words)
    return words

# ─── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id

    if is_admin(data, uid):
        await update.message.reply_text(
            "👩 Вы зарегистрированы как мама.\n\n"
            "➕ /addwords — добавить слова урока\n"
            "📊 /report — прогресс детей"
        )
        return

    student = get_student(data, uid)
    if student:
        await update.message.reply_text(
            f"👋 С возвращением, {student['name']}!\n\n"
            "📚 /words — слова последнего урока\n"
            "✅ /test — случайный тест\n"
            "📅 /weeklytest — проверка за неделю\n"
            "📆 /monthlytest — проверка за месяц\n"
            "📊 /stats — мой прогресс"
        )
        return

    keyboard = [
        [InlineKeyboardButton("Я — Ибрахим 👦", callback_data="register_ibrahim")],
        [InlineKeyboardButton("Я — Мухаммад 👦", callback_data="register_muhammad")],
        [InlineKeyboardButton("Я — мама 👩", callback_data="register_mama")],
    ]
    await update.message.reply_text(
        "Привет! Это бот-тренажёр слов для курса английского 🇬🇧\n\nКто ты?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── Registration ───────────────────────────────────────────────────────────────
async def cb_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    uid = query.from_user.id

    if query.data == "register_mama":
        data["admin_ids"] = list(set(data.get("admin_ids", []) + [uid]))
        save_data(data)
        await query.edit_message_text(
            "✅ Зарегистрированы как мама.\n\n"
            "➕ /addwords — добавить слова урока\n"
            "📊 /report — прогресс детей"
        )
        return

    name = "Ибрахим" if query.data == "register_ibrahim" else "Мухаммад"
    data["students"][str(uid)] = {"name": name, "lessons": {}, "lesson_dates": {}}
    save_data(data)
    await query.edit_message_text(
        f"✅ Привет, {name}! Ты зарегистрирован.\n\n"
        "📚 /words — слова урока\n"
        "✅ /test — тест\n"
        "📅 /weeklytest — проверка за неделю\n"
        "📆 /monthlytest — проверка за месяц"
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

# ─── Шаг 2: выбор номера урока ─────────────────────────────────────────────────
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

    lessons = student.get("lessons", {})
    last = max((int(k) for k in lessons.keys()), default=0)
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

# ─── Шаг 3: выбрали номер кнопкой или вручную ─────────────────────────────────
async def cb_addw_lesson(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    raw = query.data.replace("addw_lesson_", "")
    if raw == "manual":
        ctx.user_data["addw_waiting_lesson_number"] = True
        student_id = ctx.user_data.get("addw_student_id", "")
        name = data["students"].get(student_id, {}).get("name", "")
        await query.edit_message_text(
            f"👦 Ученик: <b>{name}</b>\n\nНапиши номер урока цифрой:",
            parse_mode="HTML"
        )
        return

    await ask_for_words_query(query, ctx, data, raw)

async def ask_for_words_query(query, ctx, data, lesson_id: str):
    student_id = ctx.user_data.get("addw_student_id")
    student = data["students"].get(student_id)
    if not student:
        await query.edit_message_text("❌ Что-то пошло не так. Начни заново — /addwords")
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
        f"magnificent — великолепный</code>",
        parse_mode="HTML"
    )

async def ask_for_words_message(update, ctx, data, lesson_id: str):
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

# ─── Шаг 4: сохраняем список слов ──────────────────────────────────────────────
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
                # Убираем транскрипцию [ˈɒbstəkl] из английского слова
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
    text += f"\n\nВсего: {len(words)} слов\n\n✅ /test — проверь себя"
    await update.message.reply_text(text)

# ─── /test — тест по очереди без повторов ─────────────────────────────────────
def make_test_queue(words: list) -> list:
    """Каждое слово — один вопрос, направление случайное, перемешано."""
    queue = []
    for word in words:
        direction = random.choice(["en_to_ru", "ru_to_en"])
        if direction == "en_to_ru":
            queue.append({"word": word, "prompt": f"🇬🇧 Переведи на русский:\n\n<b>{word['en']}</b>", "answer": word["ru"].lower().strip()})
        else:
            queue.append({"word": word, "prompt": f"🇷🇺 Переведи на английский:\n\n<b>{word['ru']}</b>", "answer": word["en"].lower().strip()})
    random.shuffle(queue)
    return queue

async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    student = get_student(data, uid)

    if not student:
        await update.message.reply_text("Сначала зарегистрируйся — /start")
        return

    all_words = get_all_words(student)
    if not all_words:
        await update.message.reply_text("📭 Слов пока нет!")
        return

    # Если очередь уже идёт — продолжаем
    if ctx.user_data.get("test_queue"):
        q = ctx.user_data["test_queue"]
        item = q[0]
        await update.message.reply_text(item["prompt"], parse_mode="HTML")
        return

    # Новая очередь — все слова, каждое по одному разу
    queue = make_test_queue(all_words)
    ctx.user_data["test_queue"] = queue
    ctx.user_data["test_session"] = {"correct": 0, "wrong": 0, "total": len(queue)}

    item = queue[0]
    total = len(queue)
    await update.message.reply_text(
        f"🃏 Начинаем тест! Всего слов: {total}\n"
        f"Каждое слово — один раз, повторов нет.\n\n"
        + item["prompt"],
        parse_mode="HTML"
    )

# ─── Период-тест: старт ────────────────────────────────────────────────────────
async def start_period_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE, words: list, label: str):
    if not words:
        await update.message.reply_text(f"📭 Нет слов для теста «{label}».")
        return

    random.shuffle(words)
    word = words[0]
    direction = random.choice(["en_to_ru", "ru_to_en"])

    if direction == "en_to_ru":
        prompt = f"🇬🇧 {word['en']}"
        answer = word["ru"].lower().strip()
    else:
        prompt = f"🇷🇺 {word['ru']}"
        answer = word["en"].lower().strip()

    ctx.user_data["period_test"] = {
        "words": words,
        "index": 0,
        "correct": 0,
        "wrong": 0,
        "label": label,
        "total": len(words),
        "answer": answer,
    }

    total = len(words)
    await update.message.reply_text(
        f"🧪 {label}\nВсего слов: {total}\n\n"
        f"Вопрос 1 / {total}:\n{prompt}\n\nНапиши перевод:"
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
        # Нет дат — берём последние 2 урока
        lessons = student.get("lessons", {})
        sorted_ids = sorted(lessons.keys(), key=lambda x: int(x), reverse=True)[:2]
        words = [w for lid in sorted_ids for w in lessons[lid]]

    await start_period_test(update, ctx, words, "📅 Еженедельная проверка")

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
        words = get_all_words(student)

    await start_period_test(update, ctx, words, "📆 Ежемесячная проверка")

# ─── handle_message ────────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Мама
    if is_admin(data, uid):
        if ctx.user_data.get("addw_waiting"):
            await handle_addw_words(update, ctx, data)
        elif ctx.user_data.get("addw_waiting_lesson_number"):
            if not text.isdigit():
                await update.message.reply_text("❌ Введи просто цифру, например: 12")
                return
            ctx.user_data.pop("addw_waiting_lesson_number", None)
            await ask_for_words_message(update, ctx, data, text)
        else:
            await update.message.reply_text(
                "Команды для мамы:\n"
                "➕ /addwords — добавить слова урока\n"
                "📊 /report — прогресс детей"
            )
        return

    # Период-тест (еженедельный / ежемесячный)
    if "period_test" in ctx.user_data:
        pt = ctx.user_data["period_test"]
        user_answer = text.lower().strip()
        correct = pt["answer"]
        word = pt["words"][pt["index"]]
        is_correct = is_answer_correct(user_answer, correct)

        if is_correct:
            pt["correct"] += 1
            feedback = f"✅ Правильно!  {word['en']} — {word['ru']}"
        else:
            pt["wrong"] += 1
            feedback = f"❌ Нет.  {word['en']} — {word['ru']}"

        pt["index"] += 1

        if pt["index"] >= pt["total"]:
            ctx.user_data.pop("period_test")
            pct = round(pt["correct"] / pt["total"] * 100)
            emoji = "🌟 Отлично!" if pct >= 80 else "💪 Нужно повторить!" if pct >= 50 else "📚 Повтори слова ещё раз!"
            result = (
                feedback + "\n\n"
                + f"🏁 {pt['label']} завершена!\n\n"
                + f"📊 Результат: {pt['correct']} / {pt['total']} ({pct}%)\n"
                + emoji
            )
            await update.message.reply_text(result)
        else:
            next_word = pt["words"][pt["index"]]
            direction = random.choice(["en_to_ru", "ru_to_en"])
            if direction == "en_to_ru":
                prompt = f"🇬🇧 {next_word['en']}"
                pt["answer"] = next_word["ru"].lower().strip()
            else:
                prompt = f"🇷🇺 {next_word['ru']}"
                pt["answer"] = next_word["en"].lower().strip()

            idx = pt["index"] + 1
            tot = pt["total"]
            await update.message.reply_text(
                feedback + "\n\n"
                + f"Вопрос {idx} / {tot}:\n{prompt}\n\nНапиши перевод:"
            )
        return

    # Обычный тест (очередь без повторов)
    if "test_queue" in ctx.user_data and ctx.user_data["test_queue"]:
        queue = ctx.user_data["test_queue"]
        session = ctx.user_data.get("test_session", {"correct": 0, "wrong": 0, "total": len(queue)})
        item = queue[0]
        word = item["word"]
        user_answer = text.lower().strip()
        correct = item["answer"]
        is_correct = is_answer_correct(user_answer, correct)

        # Обновляем статистику в БД
        student = get_student(data, uid)
        if student:
            stats = student.setdefault("stats", {"correct": 0, "wrong": 0, "streak": 0})
            if is_correct:
                stats["correct"] += 1
                stats["streak"] = stats.get("streak", 0) + 1
                session["correct"] += 1
            else:
                stats["wrong"] += 1
                stats["streak"] = 0
                session["wrong"] += 1
            save_data(data)

        ctx.user_data["test_session"] = session

        if is_correct:
            streak = data["students"][str(uid)]["stats"]["streak"]
            streak_msg = f"  🔥 Серия: {streak}!" if streak >= 3 else ""
            feedback = f"✅ Правильно!{streak_msg}\n🔹 {word['en']} — {word['ru']}"
        else:
            feedback = f"❌ Правильный ответ:\n🔹 {word['en']} — {word['ru']}"

        # Убираем слово из очереди
        queue.pop(0)

        if not queue:
            # Тест завершён
            ctx.user_data.pop("test_queue", None)
            ctx.user_data.pop("test_session", None)
            total = session["total"]
            correct_count = session["correct"]
            pct = round(correct_count / total * 100) if total else 0
            emoji = "🌟 Отлично!" if pct >= 80 else "💪 Нужно повторить!" if pct >= 50 else "📚 Повтори слова ещё раз!"
            await update.message.reply_text(
                feedback + "\n\n"
                + f"🏁 Тест завершён!\n"
                + f"📊 Результат: {correct_count} / {total} ({pct}%)\n"
                + emoji + "\n\n"
                + "Начать заново → /test"
            )
        else:
            # Следующий вопрос
            next_item = queue[0]
            remaining = len(queue)
            total = session["total"]
            done = total - remaining
            await update.message.reply_text(
                feedback + f"\n\n"
                + f"Вопрос {done + 1} / {total}:\n"
                + next_item["prompt"],
                parse_mode="HTML"
            )
        return

    await update.message.reply_text(
        "Команды:\n"
        "📚 /words — слова урока\n"
        "✅ /test — тест\n"
        "📅 /weeklytest — проверка за неделю\n"
        "📆 /monthlytest — проверка за месяц\n"
        "📊 /stats — прогресс"
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
    lessons_count = len(student.get("lessons", {}))

    await update.message.reply_text(
        f"📊 Статистика — {student['name']}\n\n"
        f"📚 Уроков в базе: {lessons_count}\n"
        f"🔤 Слов всего: {total_words}\n"
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
            f"  📚 Уроков: {lessons_count}\n"
            f"  🔤 Слов: {total_words}\n"
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
    app.add_handler(CommandHandler("weeklytest", cmd_weeklytest))
    app.add_handler(CommandHandler("monthlytest", cmd_monthlytest))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("addwords", cmd_addwords))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CallbackQueryHandler(cb_register, pattern="^register_"))
    app.add_handler(CallbackQueryHandler(cb_addw_student, pattern="^addw_student_"))
    app.add_handler(CallbackQueryHandler(cb_addw_lesson, pattern="^addw_lesson_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
