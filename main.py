import requests
import sqlite3
import random
import string
import time
import json
from datetime import datetime

TOKEN = "8909395502:AAHCyQZo4geNvJypphkeLECyoPS6d5LqtlA"
ADMIN_IDS = [8428048355, 8164031956]

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, reg_date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS promo_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, is_used INTEGER DEFAULT 0, used_by INTEGER DEFAULT NULL, created_at TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tariff TEXT, promo_code TEXT, date TEXT)")
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM promo_codes")
    if cursor.fetchone()[0] == 0:
        for _ in range(25):
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            cursor.execute("INSERT INTO promo_codes (code, created_at) VALUES (?, ?)", (code, datetime.now().isoformat()))
        conn.commit()

init_db()

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload)

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"https://api.telegram.org/bot{TOKEN}/editMessageText", json=payload)

def answer_callback(callback_id):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})

def get_updates(offset=None):
    payload = {"timeout": 30}
    if offset:
        payload["offset"] = offset
    resp = requests.post(f"https://api.telegram.org/bot{TOKEN}/getUpdates", json=payload, timeout=35)
    return resp.json().get("result", []) if resp.status_code == 200 else []

def get_free_promo():
    cursor.execute("SELECT code FROM promo_codes WHERE is_used=0 LIMIT 1")
    row = cursor.fetchone()
    return row[0] if row else None

def use_promo(code, user_id):
    cursor.execute("UPDATE promo_codes SET is_used=1, used_by=? WHERE code=?", (user_id, code))
    conn.commit()
    return cursor.rowcount > 0

def add_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (id, username, reg_date) VALUES (?, ?, ?)", (user_id, username, datetime.now().isoformat()))
    conn.commit()

def add_purchase(user_id, tariff, promo):
    cursor.execute("INSERT INTO purchases (user_id, tariff, promo_code, date) VALUES (?, ?, ?, ?)", (user_id, tariff, promo, datetime.now().isoformat()))
    conn.commit()

def main_menu():
    return {"inline_keyboard": [
        [{"text": "💎 Купить подписку", "callback_data": "buy"}],
        [{"text": "📋 Мои подписки", "callback_data": "my_subs"}],
        [{"text": "🆘 Поддержка", "callback_data": "support"}],
        [{"text": "📊 Статистика", "callback_data": "stats"}],
        [{"text": "⚙️ Админ-панель", "callback_data": "admin"}]
    ]}

def tariffs_menu():
    return {"inline_keyboard": [
        [{"text": "⭐ 7 дней — 50 ★", "callback_data": "tariff_7"}],
        [{"text": "⭐ 30 дней — 250 ★", "callback_data": "tariff_30"}],
        [{"text": "⭐ 90 дней — 500 ★", "callback_data": "tariff_90"}],
        [{"text": "👑 Навсегда — 600 ★", "callback_data": "tariff_forever"}],
        [{"text": "🔙 Назад", "callback_data": "back"}]
    ]}

def admin_menu():
    return {"inline_keyboard": [
        [{"text": "➕ Добавить промо", "callback_data": "add_promo"}],
        [{"text": "📦 Список промо", "callback_data": "list_promo"}],
        [{"text": "👥 Список пользователей", "callback_data": "list_users"}],
        [{"text": "📈 Статистика", "callback_data": "admin_stats"}],
        [{"text": "🔙 Назад", "callback_data": "back"}]
    ]}

def back_button():
    return {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "back"}]]}

def handle_start(chat_id, username):
    add_user(chat_id, username)
    send_message(chat_id, "🔥 *PlutoniumDLL* — лучший софт для Standoff 2!\n\n💎 Премиум функции:\n• Aimbot\n• ESP\n• Бесшумный режим\n• Анти-бан\n\n⬇️ Выберите действие:", main_menu())

def handle_callback(callback):
    data = callback["data"]
    chat_id = callback["from"]["id"]
    msg_id = callback["message"]["message_id"]

    if data == "back":
        edit_message(chat_id, msg_id, "🔥 Главное меню:", main_menu())
        answer_callback(callback["id"])
        return

    if data == "buy":
        edit_message(chat_id, msg_id, "💎 Выберите тариф:", tariffs_menu())
        answer_callback(callback["id"])
        return

    if data.startswith("tariff_"):
        tariff_map = {"tariff_7": "7 дней", "tariff_30": "30 дней", "tariff_90": "90 дней", "tariff_forever": "Навсегда"}
        tariff_name = tariff_map[data]
        promo = get_free_promo()
        if not promo:
            edit_message(chat_id, msg_id, "❌ Промо-коды кончились. Напишите @oryke")
            answer_callback(callback["id"])
            return
        use_promo(promo, chat_id)
        add_purchase(chat_id, tariff_name, promo)
        edit_message(chat_id, msg_id, f"✅ Подписка *{tariff_name}* активирована!\n\n🎫 Ваш промо-код:\n`{promo}`\n\n🔗 Активация: https://plut.cc", back_button())
        answer_callback(callback["id"])
        return

    if data == "my_subs":
        cursor.execute("SELECT tariff, promo_code, date FROM purchases WHERE user_id=? ORDER BY date DESC LIMIT 5", (chat_id,))
        rows = cursor.fetchall()
        if not rows:
            text = "❌ Нет активных подписок."
            kb = {"inline_keyboard": [[{"text": "💎 Купить", "callback_data": "buy"}], [{"text": "🔙 Назад", "callback_data": "back"}]]}
        else:
            text = "📋 *Ваши подписки:*\n\n"
            for tariff, promo, date in rows:
                text += f"▫️ *{tariff}* — `{promo}`\n"
            kb = back_button()
        edit_message(chat_id, msg_id, text, kb)
        answer_callback(callback["id"])
        return

    if data == "support":
        edit_message(chat_id, msg_id, "🆘 *Поддержка:*\n@oryke — техподдержка\n@shezik — оплата", back_button())
        answer_callback(callback["id"])
        return

    if data == "stats":
        total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_purchases = cursor.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
        free_promos = cursor.execute("SELECT COUNT(*) FROM promo_codes WHERE is_used=0").fetchone()[0]
        edit_message(chat_id, msg_id, f"📊 *Статистика:*\n👥 Пользователей: {total_users}\n💳 Продаж: {total_purchases}\n🎫 Свободных промо: {free_promos}", back_button())
        answer_callback(callback["id"])
        return

    if data == "admin":
        if chat_id not in ADMIN_IDS:
            answer_callback(callback["id"])
            return
        edit_message(chat_id, msg_id, "⚙️ *Админ-панель:*", admin_menu())
        answer_callback(callback["id"])
        return

    if data in ["add_promo", "list_promo", "list_users", "admin_stats"]:
        if chat_id not in ADMIN_IDS:
            answer_callback(callback["id"])
            return
        if data == "add_promo":
            edit_message(chat_id, msg_id, "➕ Используйте команду:\n`/addpromo КОЛИЧЕСТВО`", back_button())
        elif data == "list_promo":
            cursor.execute("SELECT code, is_used FROM promo_codes LIMIT 20")
            rows = cursor.fetchall()
            text = "📦 *Промо-коды:*\n"
            for code, used in rows:
                text += f"{'❌' if used else '✅'} `{code}`\n"
            edit_message(chat_id, msg_id, text, back_button())
        elif data == "list_users":
            cursor.execute("SELECT id, username, reg_date FROM users ORDER BY reg_date DESC LIMIT 20")
            rows = cursor.fetchall()
            text = "👥 *Пользователи:*\n"
            for uid, uname, reg in rows:
                text += f"▫️ {uname} (ID: {uid})\n"
            edit_message(chat_id, msg_id, text, back_button())
        elif data == "admin_stats":
            total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_purchases = cursor.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
            free_promos = cursor.execute("SELECT COUNT(*) FROM promo_codes WHERE is_used=0").fetchone()[0]
            edit_message(chat_id, msg_id, f"📈 *Полная статистика:*\n👥 {total_users}\n💳 {total_purchases}\n🎫 Свободных промо: {free_promos}", back_button())
        answer_callback(callback["id"])
        return

def handle_message(chat_id, text, username):
    add_user(chat_id, username)

    if text.startswith("/addpromo"):
        if chat_id not in ADMIN_IDS:
            send_message(chat_id, "⛔ Нет прав")
            return
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ Пример: /addpromo 5")
            return
        try:
            count = int(parts[1])
        except:
            send_message(chat_id, "❌ Введите число")
            return
        codes = [''.join(random.choices(string.ascii_uppercase + string.digits, k=12)) for _ in range(count)]
        added = 0
        for code in codes:
            try:
                cursor.execute("INSERT INTO promo_codes (code, created_at) VALUES (?, ?)", (code, datetime.now().isoformat()))
                added += 1
            except:
                pass
        conn.commit()
        send_message(chat_id, f"✅ Добавлено {added} промо-кодов.")
        return

    if text.startswith("/delpromo"):
        if chat_id not in ADMIN_IDS:
            send_message(chat_id, "⛔ Нет прав")
            return
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ Пример: /delpromo ABC123")
            return
        code = parts[1]
        cursor.execute("DELETE FROM promo_codes WHERE code=?", (code,))
        conn.commit()
        if cursor.rowcount > 0:
            send_message(chat_id, f"✅ Код `{code}` удалён.")
        else:
            send_message(chat_id, f"❌ Код `{code}` не найден.")
        return

    if text.startswith("/crack"):
        cursor.execute("SELECT promo_code FROM purchases WHERE user_id=? ORDER BY date DESC LIMIT 1", (chat_id,))
        row = cursor.fetchone()
        if not row:
            send_message(chat_id, "❌ *Доступ закрыт!*\nКупите подписку: /pay", {"inline_keyboard": [[{"text": "💎 Купить", "callback_data": "buy"}]]})
            return
        promo = row[0]
        send_message(chat_id, f"✅ *Доступ открыт!*\n\n🎫 Ваш промо-код:\n`{promo}`\n\n🔗 Активация: https://plut.cc", back_button())
        return

    if text == "/pay":
        send_message(chat_id, "💎 Выберите тариф:", tariffs_menu())
        return

    if text == "/price":
        send_message(chat_id, "📋 *Прайс-лист:*\n\n⭐ 7 дней — 50 ★\n⭐ 30 дней — 250 ★\n⭐ 90 дней — 500 ★\n👑 Навсегда — 600 ★\n\nДля покупки: /pay", back_button())
        return

    if text == "/functions":
        send_message(chat_id, "📌 *Команды:*\n\n/start — Главное меню\n/pay — Купить\n/price — Прайс\n/crack — Получить промо\n/functions — Список\n\n🔹 *Админ:*\n/addpromo N\n/delpromo CODE", back_button())
        return

    if text == "/start":
        handle_start(chat_id, username)
        return

    send_message(chat_id, "🔍 Используйте кнопки или /start", main_menu())

def main():
    print("🚀 Бот @Plutonum_bot запущен!")
    last_update_id = 0
    while True:
        try:
            updates = get_updates(last_update_id + 1 if last_update_id else None)
            for update in updates:
                last_update_id = update["update_id"]
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                elif "message" in update:
                    msg = update["message"]
                    if "text" in msg:
                        chat_id = msg["from"]["id"]
                        username = msg["from"].get("username", "NoName")
                        text = msg["text"]
                        handle_message(chat_id, text, username)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(5)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
