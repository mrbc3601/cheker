import asyncio
import html
import json
import logging
import os
import re
import sqlite3
import struct

from datetime import datetime, timedelta, timezone, time
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv


# =====================================================
# CONFIGURATION
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

RCON_HOST = os.getenv("RCON_HOST", "")
RCON_PORT = int(os.getenv("RCON_PORT", "25640"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD", "")

DB_PATH = BASE_DIR / os.getenv(
    "DATABASE_PATH",
    "../Adm-bot/cloverteam.sqlite3"
)

ADMINS_PATH = BASE_DIR / os.getenv(
    "ADMINS_FILE",
    "admins.json"
)

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
MAIN_CHAT_ID = int(os.getenv("MAIN_CHAT_ID", "0"))

APPLICATION_THREAD_ID = int(
    os.getenv("APPLICATION_THREAD_ID", "0")
)

REST_THREAD_ID = int(
    os.getenv("REST_THREAD_ID", "0")
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

REST_MAX_DAYS = 3650


# =====================================================
# LOGGING
# =====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

log = logging.getLogger("cloverteam")


# =====================================================
# CONSTANTS
# =====================================================

RANKS = [
    "legacy",
    "player",
    "rest",
    "helper",
    "moder",
    "eventor",
    "tech_admin",
    "admin",
    "st_admin",
    "owner",
]

STAFF_RANKS = set(RANKS[3:])
JAVA_RANKS = {"owner", "st_admin"}

REST_ELIGIBLE_RANKS = {
    "player",
    "helper",
    "moder",
    "eventor",
    "tech_admin",
    "admin",
    "st_admin",
    "owner",
}

MC_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")

APPLICATION_TEXT = (
    "🍀 Анкета для подачи заявки в CloverTeam 🍀\n\n"
    "Приветствуем! Чтобы попасть в CloverTeam, заполни "
    "анкету одним сообщением в ответ на это сообщение.\n\n"

    "⚠️ На нашем проекте есть лор и сюжетные ивенты. "
    "Если тебе неинтересен сюжетный игровой процесс, проект может тебе не подойти. \n\n"

    "1. Как к тебе можно обращаться?\n"
    "2. Дата рождения (дд.мм.гггг).\n"
    "3. Твой Minecraft-ник.\n"
    "4. Какое издание используешь: Java или Bedrock?\n"
    "5. Пол\n"
    "6. Telegram username (если есть).\n"
    "7. Оцени свою предполагаемую активность на сервере и в чате от 1 до 10.\n"
    "8. Играл(а) ли ты на похожих проектах? На каких?\n"
    "9. Как относишься к лору и сюжетным событиям?\n"
    "10. Почему хочешь присоединиться именно к CloverTeam?\n"
    "11. Есть ли у тебя RP-персонаж? (необязательно)\n"

)


REST_SELF_TEXT = (
    "Чтобы подать рест, заполните заявку одним сообщением "
    "в ответ на это сообщение.\n\n"
    "1. Причина, по которой вы хотите взять рест.\n"
    "2. Сколько дней вам потребуется? Указывать цифрами, "
    "минимум 1 день.\n"
    "3. Ваш Telegram username.\n"
    "4. Ваш Minecraft-ник."
)


REST_FRIEND_TEXT = (
    "Чтобы подать рест для друга, заполните заявку одним "
    "сообщением в ответ на это сообщение.\n\n"
    "1. Причина, по которой ваш друг хочет взять рест.\n"
    "2. Сколько дней потребуется другу? Минимум 1 день.\n"
    "3. Telegram username вашего друга.\n"
    "4. Minecraft-ник вашего друга.\n\n"
    "После заполнения формы бот попросит прислать "
    "скриншот доказательства и разрешения друга."
)


REST_EXTEND_TEXT = (
    "Для продления реста заполните заявку одним сообщением "
    "в ответ на это сообщение.\n\n"
    "1. До какого числа продлить рест? (ДД.ММ.ГГГГ)\n"
    "2. По какой причине вы хотите продлить рест?"
)


# =====================================================
# TEXT HELPERS
# =====================================================

def extract_command(message: Message) -> str:
    text = message.text or ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def safe_html(value) -> str:
    return html.escape(str(value))


def format_code(value: str) -> str:
    return f"<pre><code>{safe_html(value)}</code></pre>"


def normalize_username(value: str) -> str:
    return value.strip().lstrip("@").lower()


def moscow_now() -> datetime:
    return datetime.now(MOSCOW_TZ)


def moscow_iso(value: datetime) -> str:
    return value.astimezone(MOSCOW_TZ).isoformat()


def parse_rest_lines(text: str, expected: int):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    cleaned = []

    for line in lines:
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        cleaned.append(line.strip())

    if len(cleaned) != expected:
        return None

    if any(not item for item in cleaned):
        return None

    return cleaned


def parse_date(value: str):
    try:
        return datetime.strptime(
            value.strip(),
            "%d.%m.%Y"
        ).date()
    except ValueError:
        return None


# =====================================================
# ADMINS.JSON
# =====================================================

def load_admins() -> dict:
    try:
        data = json.loads(
            ADMINS_PATH.read_text(encoding="utf-8")
        )
        return data if isinstance(data, dict) else {}

    except FileNotFoundError:
        return {}

    except Exception:
        log.exception("Cannot load admins.json")
        return {}


def get_admin(telegram_id: int):
    value = load_admins().get(str(telegram_id))
    return value if isinstance(value, dict) else None


# =====================================================
# SQLITE
# =====================================================

def db_connect():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=15
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with db_connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                telegram_username TEXT,
                minecraft_nickname TEXT UNIQUE COLLATE NOCASE,
                rank TEXT NOT NULL DEFAULT 'player'
            )
        """)

        # Миграция старой схемы: у legacy пока нет Minecraft-ника,
        # поэтому minecraft_nickname должен допускать NULL.
        user_columns = {
            row["name"]: row
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }

        if user_columns.get("minecraft_nickname") and user_columns["minecraft_nickname"]["notnull"]:
            conn.execute("""
                CREATE TABLE users_new (
                    telegram_id INTEGER PRIMARY KEY,
                    telegram_username TEXT,
                    minecraft_nickname TEXT UNIQUE COLLATE NOCASE,
                    rank TEXT NOT NULL DEFAULT 'player'
                )
            """)
            conn.execute("""
                INSERT INTO users_new
                    (telegram_id, telegram_username, minecraft_nickname, rank)
                SELECT telegram_id, telegram_username, minecraft_nickname, rank
                FROM users
            """)
            conn.execute("DROP TABLE users")
            conn.execute("ALTER TABLE users_new RENAME TO users")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                telegram_username TEXT,
                prompt_message_id INTEGER,
                admin_message_id INTEGER,
                application_text TEXT,
                status TEXT NOT NULL DEFAULT 'awaiting_reply',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                telegram_id INTEGER PRIMARY KEY,
                reason TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Постоянная блокировка подачи анкет по Telegram ID.
        # Отдельная таблица гарантирует, что /unreg не снимет этот запрет.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ank_bans (
                telegram_id INTEGER PRIMARY KEY,
                telegram_username TEXT,
                admin_id INTEGER NOT NULL,
                application_id INTEGER,
                created_at TEXT NOT NULL
            )
        """)

        # Сводка активных варнов по Telegram ID. История хранится отдельно.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                telegram_id INTEGER PRIMARY KEY,
                warn_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS warn_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                days INTEGER NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                server_notified INTEGER NOT NULL DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_warn_history_active
            ON warn_history(telegram_id, status, expires_at)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rest_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                target_id INTEGER,
                request_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                days INTEGER,
                target_username TEXT,
                target_nickname TEXT,
                requested_until TEXT,
                proof_file_id TEXT,
                admin_message_id INTEGER,
                reject_prompt_message_id INTEGER,
                reject_admin_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rest_periods (
                telegram_id INTEGER PRIMARY KEY,
                original_rank TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                request_id INTEGER
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rest_sessions (
                telegram_id INTEGER PRIMARY KEY,
                mode TEXT NOT NULL,
                step TEXT NOT NULL,
                prompt_message_id INTEGER,
                data_json TEXT NOT NULL DEFAULT '{}'
            )
        """)

        # Безопасные миграции старой базы.

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(rest_requests)"
            ).fetchall()
        }

        if "reject_prompt_message_id" not in columns:
            conn.execute("""
                ALTER TABLE rest_requests
                ADD COLUMN reject_prompt_message_id INTEGER
            """)

        if "reject_admin_id" not in columns:
            conn.execute("""
                ALTER TABLE rest_requests
                ADD COLUMN reject_admin_id INTEGER
            """)

        period_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(rest_periods)"
            ).fetchall()
        }

        if "original_rank" not in period_columns:
            conn.execute("""
                ALTER TABLE rest_periods
                ADD COLUMN original_rank TEXT NOT NULL DEFAULT 'player'
            """)

        conn.commit()


# =====================================================
# DATABASE HELPERS
# =====================================================

def get_user(telegram_id: int):
    with db_connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()


def ensure_legacy_user(telegram_id: int, telegram_username: str = "") -> bool:
    """Создаёт legacy-запись для замеченного участника основного чата."""
    if get_admin(telegram_id):
        return False

    with db_connect() as conn:
        existing = conn.execute(
            "SELECT rank FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()

        if existing:
            if existing["rank"] == "legacy":
                conn.execute(
                    "UPDATE users SET telegram_username = ? WHERE telegram_id = ?",
                    (telegram_username or "", telegram_id)
                )
                conn.commit()
            return False

        conn.execute(
            """
            INSERT INTO users
                (telegram_id, telegram_username, minecraft_nickname, rank)
            VALUES (?, ?, NULL, 'legacy')
            """,
            (telegram_id, telegram_username or "")
        )
        conn.commit()

    log.info("Added legacy user: telegram_id=%s username=%s", telegram_id, telegram_username or "")
    return True


def get_user_by_nickname(nickname: str):
    with db_connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM users
            WHERE minecraft_nickname = ? COLLATE NOCASE
            """,
            (nickname,)
        ).fetchone()


def get_rest_period(telegram_id: int):
    with db_connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM rest_periods
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        ).fetchone()


def get_account(telegram_id: int):
    """
    Сначала проверяем активный рест.
    Это позволяет корректно обрабатывать admins.json,
    не переписывая сам файл.
    """

    admin = get_admin(telegram_id)
    user = get_user(telegram_id)
    period = get_rest_period(telegram_id)

    if admin:
        base_rank = admin.get("rank")
        nickname = admin.get("minecraft")
        telegram = admin.get("telegram") or ""

    elif user:
        base_rank = user["rank"]
        nickname = user["minecraft_nickname"]
        telegram = user["telegram_username"] or ""

    else:
        return None

    if base_rank not in RANKS:
        return None

    if base_rank == "legacy":
        nickname = nickname or ""
    elif (
        not isinstance(nickname, str)
        or not MC_NAME_RE.fullmatch(nickname)
    ):
        return None

    if period:
        return {
            "rank": "rest",
            "minecraft": nickname,
            "telegram": telegram,
            "original_rank": period["original_rank"],
            "ends_at": period["ends_at"],
        }

    return {
        "rank": base_rank,
        "minecraft": nickname,
        "telegram": telegram,
    }


def is_senior_admin(telegram_id: int) -> bool:
    """
    Проверяем исходный административный ранг.
    Если администратор находится в ресте, его полномочия
    временно не действуют.
    """

    if get_rest_period(telegram_id):
        return False

    admin = get_admin(telegram_id)

    return bool(
        admin
        and admin.get("rank") in {"owner", "st_admin"}
    )


def is_banned(telegram_id: int) -> bool:
    """Общая проверка блокировок, включая запрет подачи анкет."""
    with db_connect() as conn:
        result = conn.execute(
            """
            SELECT 1 FROM bans WHERE telegram_id = ?
            UNION ALL
            SELECT 1 FROM ank_bans WHERE telegram_id = ?
            UNION ALL
            SELECT 1 FROM users WHERE telegram_id = ? AND rank = 'warnbanned'
            LIMIT 1
            """,
            (telegram_id, telegram_id, telegram_id)
        ).fetchone()

    return result is not None


WARN_RANK_LEVEL = {
    "player": 0,
    "helper": 1,
    "moder": 2,
    "admin": 3,
    "tech_admin": 3,
    "st_admin": 4,
    "owner": 5,
}


def get_warn_target(identifier: str):
    """Ищет зарегистрированного игрока/администратора по TG ID, username или MC нику."""
    value = identifier.strip()
    if not value:
        return None

    with db_connect() as conn:
        if value.isdigit():
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (int(value),)
            ).fetchone()
            if row:
                return {"telegram_id": int(row["telegram_id"]),
                        "username": row["telegram_username"] or "",
                        "minecraft": row["minecraft_nickname"] or "",
                        "rank": row["rank"]}

        row = conn.execute(
            "SELECT * FROM users WHERE minecraft_nickname = ? COLLATE NOCASE",
            (value,)
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM users WHERE lower(ltrim(telegram_username, '@')) = ?",
                (normalize_username(value),)
            ).fetchone()
        if row:
            return {"telegram_id": int(row["telegram_id"]),
                    "username": row["telegram_username"] or "",
                    "minecraft": row["minecraft_nickname"] or "",
                    "rank": row["rank"]}

    # Администраторы могут храниться в admins.json, а не в users.
    needle = normalize_username(value)
    for telegram_id, data in load_admins().items():
        if not isinstance(data, dict):
            continue
        admin_tg = str(telegram_id)
        admin_username = normalize_username(str(data.get("telegram") or data.get("username") or ""))
        admin_mc = str(data.get("minecraft") or data.get("minecraft_nickname") or "")
        if value.isdigit() and admin_tg == value:
            match = True
        else:
            match = (needle and needle == admin_username) or (admin_mc and admin_mc.lower() == value.lower())
        if match:
            return {"telegram_id": int(telegram_id), "username": admin_username,
                    "minecraft": admin_mc, "rank": data.get("rank", "player")}
    return None


def refresh_warn_count(conn, telegram_id: int, now: datetime | None = None) -> int:
    now = now or moscow_now()
    now_iso = moscow_iso(now)
    conn.execute(
        "UPDATE warn_history SET status = 'expired' "
        "WHERE telegram_id = ? AND status = 'active' "
        "AND expires_at IS NOT NULL AND expires_at <= ?",
        (telegram_id, now_iso)
    )
    count = conn.execute(
        "SELECT COUNT(*) FROM warn_history WHERE telegram_id = ? AND status = 'active'",
        (telegram_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO warns(telegram_id, warn_count, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET warn_count = excluded.warn_count, "
        "updated_at = excluded.updated_at",
        (telegram_id, count, now_iso)
    )
    return int(count)


async def warn_expiration_worker():
    while True:
        try:
            with db_connect() as conn:
                ids = [r[0] for r in conn.execute(
                    "SELECT DISTINCT telegram_id FROM warn_history WHERE status = 'active' "
                    "AND expires_at IS NOT NULL"
                ).fetchall()]
                for telegram_id in ids:
                    refresh_warn_count(conn, int(telegram_id))
                conn.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Warn expiration worker failed")
        await asyncio.sleep(60)


def get_rest_session(telegram_id: int):
    with db_connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM rest_sessions
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        ).fetchone()


def save_rest_session(
    telegram_id: int,
    mode: str,
    step: str,
    prompt_message_id: int,
    data: dict
):
    with db_connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO rest_sessions
            (
                telegram_id,
                mode,
                step,
                prompt_message_id,
                data_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                telegram_id,
                mode,
                step,
                prompt_message_id,
                json.dumps(data, ensure_ascii=False)
            )
        )
        conn.commit()


def delete_rest_session(telegram_id: int):
    with db_connect() as conn:
        conn.execute(
            """
            DELETE FROM rest_sessions
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )
        conn.commit()


# =====================================================
# REST PERIOD HELPERS
# =====================================================

def activate_rest(
    conn,
    telegram_id: int,
    original_rank: str,
    end_time: datetime,
    request_id: int
):
    now = moscow_now()

    conn.execute(
        """
        UPDATE users
        SET rank = 'rest'
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO rest_periods
        (
            telegram_id,
            original_rank,
            started_at,
            ends_at,
            request_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            telegram_id,
            original_rank,
            moscow_iso(now),
            moscow_iso(end_time),
            request_id
        )
    )


def restore_rest(conn, telegram_id: int):
    period = conn.execute(
        """
        SELECT *
        FROM rest_periods
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    ).fetchone()

    if not period:
        return None

    original_rank = period["original_rank"]

    conn.execute(
        """
        UPDATE users
        SET rank = ?
        WHERE telegram_id = ?
        AND rank = 'rest'
        """,
        (original_rank, telegram_id)
    )

    conn.execute(
        """
        DELETE FROM rest_periods
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )

    return original_rank


# =====================================================
# LEGACY TRACKING AND COMMAND ACCESS
# =====================================================

class LegacyAccessMiddleware(BaseMiddleware):
    """Отмечает замеченных участников основного чата и блокирует legacy-команды."""

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        user = event.from_user

        # Постоянно заблокированным пользователям не даём пользоваться
        # ботом ни через команды, ни через обычные сообщения.
        if not user.is_bot and is_banned(user.id):
            if event.chat.type == "private":
                account_row = get_user(user.id)
                if account_row and account_row["rank"] == "warnbanned":
                    await event.reply(
                        "Вы были забанены в CloverTeam навсегда\n\n"
                        "Причина: Достижение максимального количества варнов"
                    )
                else:
                    await event.reply(
                        "Администрация запретила вам писать анкеты и пользоваться ботом."
                    )
            return None

        if (
            MAIN_CHAT_ID
            and event.chat.id == MAIN_CHAT_ID
            and not user.is_bot
        ):
            ensure_legacy_user(user.id, user.username or "")

        text = event.text or event.caption or ""
        if text.startswith("/") and not get_admin(user.id):
            row = get_user(user.id)
            if row and row["rank"] == "legacy":
                command_token = text.split(maxsplit=1)[0]
                command_name = command_token.split("@", 1)[0].lstrip("/").lower()

                if command_name != "reg":
                    await event.reply(
                        "Ваш статус — <b>legacy</b>.\n\n"
                        "Для активации аккаунта доступна только команда:\n"
                        "<code>/reg MinecraftNick</code>"
                    )
                    return None

        return await handler(event, data)


async def track_legacy_chat_member(event: ChatMemberUpdated):
    if not MAIN_CHAT_ID or event.chat.id != MAIN_CHAT_ID:
        return

    member = event.new_chat_member
    user = member.user
    if user.is_bot:
        return

    is_member = member.status in {"creator", "administrator", "member"}
    if member.status == "restricted":
        is_member = bool(getattr(member, "is_member", False))

    if is_member:
        ensure_legacy_user(user.id, user.username or "")


# =====================================================
# REGISTRATION CHECK
# =====================================================

async def require_registered(message: Message):

    if not message.from_user:
        return None

    telegram_id = message.from_user.id

    if is_banned(telegram_id):
        await message.reply(
            "Администрация ограничила доступ к командам бота."
        )
        return None

    account = get_account(telegram_id)

    if not account:
        await message.reply(
            "Вы не зарегистрированы в базе данных.\n\n"
            "Для начала подайте заявку через /start, "
            "затем используйте /reg."
        )
        return None

    return account


# =====================================================
# /START
# =====================================================

async def cmd_start(message: Message):

    if not message.from_user:
        return

    if message.chat.type != "private":
        try:
            await message.bot.send_message(
                message.from_user.id,
                "Для подачи заявки напишите мне в личные сообщения: /start"
            )
        except Exception:
            await message.reply(
                "Сначала откройте личные сообщения с ботом "
                "и отправьте ему /start."
            )
        return

    telegram_id = message.from_user.id

    if is_banned(telegram_id):
        await message.reply(
            "Администрация ограничила доступ к анкетам "
            "и командам бота."
        )
        return

    if get_user(telegram_id) or get_admin(telegram_id):
        await message.reply(
            "Вы уже зарегистрированы на данный момент."
        )
        return

    with db_connect() as conn:

        pending = conn.execute(
            """
            SELECT id
            FROM applications
            WHERE telegram_id = ?
            AND status IN ('awaiting_reply', 'pending')
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_id,)
        ).fetchone()

        if pending:
            await message.reply(
                "Ваша заявка уже отправлена "
                "или ожидает заполнения."
            )
            return

        cur = conn.execute(
            """
            INSERT INTO applications
            (
                telegram_id,
                telegram_username,
                status,
                created_at
            )
            VALUES (?, ?, 'awaiting_reply', ?)
            """,
            (
                telegram_id,
                message.from_user.username or "",
                datetime.now(timezone.utc).isoformat(),
            )
        )

        app_id = cur.lastrowid
        conn.commit()

    prompt = await message.reply(APPLICATION_TEXT)

    with db_connect() as conn:
        conn.execute(
            """
            UPDATE applications
            SET prompt_message_id = ?
            WHERE id = ?
            """,
            (prompt.message_id, app_id)
        )
        conn.commit()


# =====================================================
# APPLICATION REPLY
# =====================================================

async def application_reply(message: Message):

    if not message.from_user or not message.text:
        return

    if message.chat.type != "private":
        return

    telegram_id = message.from_user.id

    if is_banned(telegram_id):
        await message.reply(
            "Администрация ограничила доступ к анкетам."
        )
        return

    with db_connect() as conn:
        app = conn.execute(
            """
            SELECT *
            FROM applications
            WHERE telegram_id = ?
            AND status = 'awaiting_reply'
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_id,)
        ).fetchone()

    if not app:
        return

    if (
        not message.reply_to_message
        or message.reply_to_message.message_id
        != app["prompt_message_id"]
    ):
        return

    if len(message.text) > 5000:
        await message.reply(
            "Анкета слишком длинная. Максимум 5000 символов."
        )
        return

    if ADMIN_CHAT_ID == 0:
        await message.reply(
            "Ошибка: ADMIN_CHAT_ID не настроен."
        )
        return

    username = (
        "@" + message.from_user.username
        if message.from_user.username
        else "не указан"
    )

    admin_text = (
        "<b>Новая заявка CloverTeam</b>\n\n"
        f"Telegram: {safe_html(username)}\n"
        f"Telegram ID: <code>{telegram_id}</code>\n"
        f"Заявка №: <code>{app['id']}</code>\n\n"
        f"<b>Ответы:</b>\n{safe_html(message.text)}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"app_approve:{app['id']}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"app_reject:{app['id']}"
                )
            ]
        ]
    )

    try:
        sent = await message.bot.send_message(
            ADMIN_CHAT_ID,
            admin_text,
            reply_markup=keyboard
        )

        with db_connect() as conn:
            conn.execute(
                """
                UPDATE applications
                SET application_text = ?,
                    admin_message_id = ?,
                    status = 'pending'
                WHERE id = ?
                """,
                (
                    message.text,
                    sent.message_id,
                    app["id"]
                )
            )
            conn.commit()

        await message.reply(
            "✅ Анкета успешно отправлена администрации!"
        )

    except Exception:
        log.exception("Application forwarding failed")
        await message.reply(
            "❌ Не удалось отправить анкету администрации."
        )


# =====================================================
# /ANKBAN — PERMANENT APPLICATION BAN
# =====================================================

async def cmd_ankban(message: Message) -> bool:
    """Блокирует автора анкеты, на сообщение которой ответила администрация."""
    if (
        message.chat.id != ADMIN_CHAT_ID
        or not message.from_user
        or not message.reply_to_message
        or not message.text
        or not message.text.split(maxsplit=1)[0].split("@", 1)[0].lower() == "/ankban"
    ):
        return False

    if not is_senior_admin(message.from_user.id):
        await message.reply("Команда доступна только st_admin и owner.")
        return True

    replied_message_id = message.reply_to_message.message_id

    with db_connect() as conn:
        app = conn.execute(
            """
            SELECT * FROM applications
            WHERE admin_message_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (replied_message_id,)
        ).fetchone()

        if not app:
            await message.reply(
                "Не удалось найти анкету. Ответьте командой /ankban "
                "непосредственно на сообщение с анкетой в админ-чате."
            )
            return True

        target_id = int(app["telegram_id"])
        username = (app["telegram_username"] or "").strip().lstrip("@")
        created_at = datetime.now(timezone.utc).isoformat()

        # Отдельная запись блокировки не удаляется командой /unreg.
        conn.execute(
            """
            INSERT INTO ank_bans
                (telegram_id, telegram_username, admin_id, application_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_username = excluded.telegram_username,
                admin_id = excluded.admin_id,
                application_id = excluded.application_id,
                created_at = excluded.created_at
            """,
            (target_id, username, message.from_user.id, app["id"], created_at)
        )

        # В основной таблице также сохраняем ранг banned.
        existing_user = conn.execute(
            "SELECT telegram_id FROM users WHERE telegram_id = ?",
            (target_id,)
        ).fetchone()

        if existing_user:
            conn.execute(
                """
                UPDATE users
                SET telegram_username = ?, rank = 'banned'
                WHERE telegram_id = ?
                """,
                (username, target_id)
            )
        else:
            conn.execute(
                """
                INSERT INTO users
                    (telegram_id, telegram_username, minecraft_nickname, rank)
                VALUES (?, ?, NULL, 'banned')
                """,
                (target_id, username)
            )

        conn.execute(
            "UPDATE applications SET status = 'ank_banned' WHERE id = ?",
            (app["id"],)
        )
        conn.commit()

    try:
        await message.bot.send_message(
            target_id,
            "Администрация запретила вам писать анкеты и пользоваться ботом."
        )
        notification = "Пользователь уведомлён."
    except Exception:
        log.warning("Could not notify ank-banned user %s", target_id, exc_info=True)
        notification = (
            "Не удалось отправить ему личное сообщение "
            "(возможно, пользователь не открывал диалог с ботом)."
        )

    await message.reply(
        "⛔ Пользователь заблокирован.\n"
        f"Telegram ID: <code>{target_id}</code>\n"
        f"Username: <code>{safe_html('@' + username if username else 'не указан')}</code>\n"
        f"Заявка №: <code>{app['id']}</code>\n"
        f"{notification}"
    )
    return True


# =====================================================
# APPLICATION APPROVE / REJECT
# =====================================================

async def application_decision(callback: CallbackQuery):

    if (
        not callback.from_user
        or not is_senior_admin(callback.from_user.id)
    ):
        await callback.answer(
            "Только owner и st_admin могут принимать решения.",
            show_alert=True
        )
        return

    if (
        callback.message
        and callback.message.chat.id != ADMIN_CHAT_ID
    ):
        await callback.answer(
            "Недоступно в этом чате.",
            show_alert=True
        )
        return

    try:
        action, app_id_text = (
            callback.data or ""
        ).split(":", 1)

        app_id = int(app_id_text)

    except (ValueError, AttributeError):
        await callback.answer(
            "Некорректная заявка.",
            show_alert=True
        )
        return

    if action not in {"app_approve", "app_reject"}:
        await callback.answer(
            "Неизвестное действие.",
            show_alert=True
        )
        return

    new_status = (
        "approved"
        if action == "app_approve"
        else "rejected"
    )

    with db_connect() as conn:

        app = conn.execute(
            """
            SELECT *
            FROM applications
            WHERE id = ?
            AND status = 'pending'
            """,
            (app_id,)
        ).fetchone()

        if not app:
            await callback.answer(
                "Заявка уже обработана или не найдена.",
                show_alert=True
            )
            return

        conn.execute(
            """
            UPDATE applications
            SET status = ?
            WHERE id = ?
            """,
            (new_status, app_id)
        )
        conn.commit()

    try:
        if new_status == "approved":

            await callback.bot.send_message(
                app["telegram_id"],
                "Ваша анкета была принята администрацией.\n\n"
                "Чтобы зарегистрироваться, используйте команду:\n"
                "/reg Minecraft_Nickname\n\n"
                "Введите свой настоящий Minecraft Java-ник."
            )

            label = "✅ Заявка одобрена"

        else:

            await callback.bot.send_message(
                app["telegram_id"],
                "Ваша анкета была отклонена администрацией. "
                "Спасибо за проявленный интерес."
            )

            label = "❌ Заявка отклонена"

    except Exception:
        log.exception(
            "Could not notify applicant about decision"
        )
        label = (
            "Решение сохранено, "
            "но уведомить пользователя не удалось"
        )

    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
        await callback.message.reply(label)

    await callback.answer("Готово")


# =====================================================
# /REG
# =====================================================

async def cmd_reg(message: Message):

    if not message.from_user:
        return

    telegram_id = message.from_user.id

    if message.chat.type != "private" and message.chat.id != MAIN_CHAT_ID:
        await message.reply(
            "Используйте /reg в личных сообщениях бота "
            "или в основном чате CloverTeam."
        )
        return

    if is_banned(telegram_id):
        await message.reply(
            "Администрация ограничила доступ к анкетам "
            "и командам бота."
        )
        return

    # Если команда отправлена в основном чате, фиксируем участника сразу.
    if message.chat.id == MAIN_CHAT_ID:
        ensure_legacy_user(telegram_id, message.from_user.username or "")

    # При вызове в ЛС проверяем, состоит ли пользователь в основном чате.
    # Для надёжной проверки Telegram требует, чтобы бот был администратором чата.
    elif MAIN_CHAT_ID:
        try:
            member = await message.bot.get_chat_member(MAIN_CHAT_ID, telegram_id)
            already_member = (
                member.status in {"creator", "administrator", "member"}
                or (
                    member.status == "restricted"
                    and getattr(member, "is_member", False)
                )
            )
            if already_member:
                ensure_legacy_user(telegram_id, message.from_user.username or "")
        except Exception:
            log.warning(
                "Could not verify main-chat membership for /reg: telegram_id=%s",
                telegram_id,
                exc_info=True
            )

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.reply(
            "Использование: <code>/reg MinecraftNick</code>"
        )
        return

    nickname = parts[1].strip()
    if not MC_NAME_RE.fullmatch(nickname):
        await message.reply(
            "Данный никнейм некорректен. Используйте 3–16 символов: "
            "латинские буквы, цифры или _."
        )
        return

    if get_admin(telegram_id):
        await message.reply("Ваш аккаунт уже зарегистрирован как администрация.")
        return

    existing = get_user(telegram_id)
    legacy = bool(existing and existing["rank"] == "legacy")

    if existing and not legacy:
        await message.reply(
            "Вы уже зарегистрированы на данный момент."
        )
        return

    # Сохраняем старую систему: новые участники регистрируются
    # только после одобрения анкеты администрацией.
    if not legacy:
        with db_connect() as conn:
            approved = conn.execute(
                """
                SELECT id
                FROM applications
                WHERE telegram_id = ?
                AND status = 'approved'
                ORDER BY id DESC
                LIMIT 1
                """,
                (telegram_id,)
            ).fetchone()

        if not approved:
            await message.reply(
                "У вас нет доступа к этой команде. Сначала подайте анкету "
                "через /start и дождитесь её одобрения."
            )
            return

    other = get_user_by_nickname(nickname)
    if other and other["telegram_id"] != telegram_id:
        await message.reply(
            "Этот Minecraft-ник уже привязан к другому аккаунту."
        )
        return

    try:
        with db_connect() as conn:
            if legacy:
                conn.execute(
                    """
                    UPDATE users
                    SET telegram_username = ?,
                        minecraft_nickname = ?,
                        rank = 'player'
                    WHERE telegram_id = ?
                    AND rank = 'legacy'
                    """,
                    (
                        message.from_user.username or "",
                        nickname,
                        telegram_id,
                    )
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users
                    (telegram_id, telegram_username, minecraft_nickname, rank)
                    VALUES (?, ?, ?, 'player')
                    """,
                    (
                        telegram_id,
                        message.from_user.username or "",
                        nickname,
                    )
                )
            conn.commit()

    except sqlite3.IntegrityError:
        await message.reply(
            "Не удалось сохранить регистрацию: этот Minecraft-ник уже используется."
        )
        return

    invite_text = ""

    if message.chat.id == MAIN_CHAT_ID:
        invite_text = "\n\nВы уже состоите в основном чате CloverTeam."
    elif MAIN_CHAT_ID:
        try:
            member = await message.bot.get_chat_member(MAIN_CHAT_ID, telegram_id)
            already_member = (
                member.status in {"creator", "administrator", "member"}
                or (
                    member.status == "restricted"
                    and getattr(member, "is_member", False)
                )
            )

            if not already_member:
                invite = await message.bot.create_chat_invite_link(
                    chat_id=MAIN_CHAT_ID,
                    creates_join_request=True,
                    expire_date=(
                        datetime.now(timezone.utc) + timedelta(hours=24)
                    ),
                    name=f"CloverTeam_{telegram_id}"
                )
                invite_text = (
                    "\n\n🍀 <b>Приглашение в основной чат CloverTeam</b>\n\n"
                    "Перейдите по ссылке ниже и отправьте заявку на вступление:\n"
                    f"{safe_html(invite.invite_link)}\n\n"
                    "⏳ Ссылка действует 24 часа."
                )
            else:
                invite_text = "\n\nВы уже состоите в основном чате CloverTeam."

        except Exception:
            log.exception(
                "Could not create/check main chat join-request invite"
            )
            invite_text = (
                "\n\nРегистрация сохранена, но не удалось создать ссылку "
                "для вступления. Обратитесь к администрации."
            )

    await message.reply(
        "✅ Регистрация успешно завершена!\n\n"
        f"Telegram ID: <code>{telegram_id}</code>\n"
        f"Minecraft: <code>{safe_html(nickname)}</code>\n"
        "Ранг: <b>player</b>"
        f"{invite_text}"
    )


# =====================================================
# /UNREG
# =====================================================

async def cmd_unreg(message: Message):

    if not message.from_user:
        return

    if message.chat.type != "private":
        await message.reply(
            "Используйте /unreg в личных сообщениях бота."
        )
        return

    if not is_senior_admin(message.from_user.id):
        await message.reply(
            "У вас недостаточно прав для использования этой команды!"
        )
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) != 2:
        await message.reply(
            "Использование:\n"
            "/unreg Telegram_ID\n"
            "/unreg Minecraft_Nickname\n"
            "/unreg @username"
        )
        return

    target = parts[1].strip()

    if not target:
        await message.reply("Укажите пользователя.")
        return

    username = target.lstrip("@")

    with db_connect() as conn:

        user = None

        if target.isdigit():
            user = conn.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id = ?
                """,
                (int(target),)
            ).fetchone()

            if not user:
                user = conn.execute(
                    """
                    SELECT *
                    FROM users
                    WHERE minecraft_nickname = ? COLLATE NOCASE
                    """,
                    (target,)
                ).fetchone()

        else:
            matches = conn.execute(
                """
                SELECT *
                FROM users
                WHERE minecraft_nickname = ? COLLATE NOCASE
                   OR telegram_username = ? COLLATE NOCASE
                   OR telegram_username = ? COLLATE NOCASE
                """,
                (
                    target,
                    username,
                    "@" + username
                )
            ).fetchall()

            if len(matches) > 1:
                await message.reply(
                    "Найдено несколько совпадений.\n"
                    "Укажите точный Telegram ID пользователя."
                )
                return

            user = matches[0] if matches else None

        if not user:
            await message.reply(
                "Пользователь не найден в базе данных."
            )
            return

        telegram_id = user["telegram_id"]
        nickname = user["minecraft_nickname"]
        telegram_username = user["telegram_username"] or "не указан"
        old_rank = user["rank"]

        conn.execute(
            "DELETE FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )

        conn.execute(
            "DELETE FROM rest_periods WHERE telegram_id = ?",
            (telegram_id,)
        )

        conn.execute(
            "DELETE FROM rest_sessions WHERE telegram_id = ?",
            (telegram_id,)
        )

        conn.execute(
            """
            UPDATE rest_requests
            SET status = 'cancelled'
            WHERE applicant_id = ?
            AND status IN (
                'pending',
                'awaiting_proof',
                'awaiting_rejection_reason'
            )
            """,
            (telegram_id,)
        )

        conn.commit()

    await message.reply(
        "✅ Регистрация пользователя удалена из базы данных.\n\n"
        f"Telegram ID: <code>{telegram_id}</code>\n"
        f"Username: <code>{safe_html(telegram_username)}</code>\n"
        f"Minecraft: <code>{safe_html(nickname)}</code>\n"
        f"Прежний ранг: <code>{safe_html(old_rank)}</code>"
    )

    try:
        await message.bot.send_message(
            telegram_id,
            "Ваша регистрация в CloverTeam была удалена администрацией."
        )
    except Exception:
        log.warning(
            "Could not notify unregistered user: %s",
            telegram_id
        )


# =====================================================
# REST KEYBOARDS
# =====================================================

def rest_start_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Взять рест на себя",
                    callback_data="rest_self"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Взять рест для друга",
                    callback_data="rest_friend"
                )
            ]
        ]
    )


def rest_manage_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Продлить",
                    callback_data="rest_extend"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Снять самостоятельно",
                    callback_data="rest_remove"
                )
            ]
        ]
    )


def rest_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да",
                    callback_data="rest_remove_yes"
                ),
                InlineKeyboardButton(
                    text="Нет",
                    callback_data="rest_remove_no"
                )
            ]
        ]
    )


def rest_admin_keyboard(request_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"rest_approve:{request_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"rest_reject:{request_id}"
                )
            ]
        ]
    )


# =====================================================
# /REST
# =====================================================

async def cmd_rest(message: Message):

    if not message.from_user:
        return

    telegram_id = message.from_user.id

    if message.chat.type != "private":
        try:
            await message.bot.send_message(
                telegram_id,
                "Для использования /rest перейдите в личные сообщения бота."
            )
        except Exception:
            await message.reply(
                "Сначала откройте личные сообщения с ботом "
                "и отправьте ему /rest."
            )
        return

    if is_banned(telegram_id):
        await message.reply(
            "Администрация ограничила доступ к командам бота."
        )
        return

    account = get_account(telegram_id)

    if not account:
        await message.reply(
            "Вы не зарегистрированы в базе данных."
        )
        return

    if get_rest_session(telegram_id):
        await message.reply(
            "У вас уже есть незавершённая анкета. "
            "Завершите её, прежде чем начинать новую."
        )
        return

    if account["rank"] == "rest":
        period = get_rest_period(telegram_id)

        if period:
            end = datetime.fromisoformat(
                period["ends_at"]
            ).astimezone(MOSCOW_TZ)

            await message.reply(
                "Что вы хотите сделать с рестом?\n\n"
                f"Текущий срок окончания: "
                f"<b>{end.strftime('%d.%m.%Y %H:%M')} МСК</b>",
                reply_markup=rest_manage_keyboard()
            )
        else:
            await message.reply(
                "Что вы хотите сделать с рестом?",
                reply_markup=rest_manage_keyboard()
            )

        return

    if account["rank"] not in REST_ELIGIBLE_RANKS:
        await message.reply(
            "Игроки с вашим рангом не могут подавать заявку на рест."
        )
        return

    with db_connect() as conn:
        pending = conn.execute(
            """
            SELECT id
            FROM rest_requests
            WHERE applicant_id = ?
            AND status IN (
                'pending',
                'awaiting_proof',
                'awaiting_rejection_reason'
            )
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_id,)
        ).fetchone()

    if pending:
        await message.reply(
            "У вас уже есть заявка на рест, "
            "которая ожидает рассмотрения."
        )
        return

    await message.reply(
        "Как вы хотите подать рест?",
        reply_markup=rest_start_keyboard()
    )


# =====================================================
# REST CALLBACKS: START FORM
# =====================================================

async def rest_start_callback(callback: CallbackQuery):

    if not callback.from_user or not callback.message:
        return

    telegram_id = callback.from_user.id

    if callback.message.chat.type != "private":
        await callback.answer(
            "Используйте кнопки в личных сообщениях с ботом.",
            show_alert=True
        )
        return

    if is_banned(telegram_id):
        await callback.answer(
            "Доступ ограничен.",
            show_alert=True
        )
        return

    account = get_account(telegram_id)

    if not account:
        await callback.answer(
            "Вы не зарегистрированы.",
            show_alert=True
        )
        return

    if get_rest_session(telegram_id):
        await callback.answer(
            "У вас уже есть незавершённая анкета.",
            show_alert=True
        )
        return

    if account["rank"] == "rest":
        await callback.answer(
            "Вы уже находитесь в ресте.",
            show_alert=True
        )
        return

    if account["rank"] not in REST_ELIGIBLE_RANKS:
        await callback.answer(
            "Ваш ранг не позволяет подать заявку.",
            show_alert=True
        )
        return

    action = callback.data

    if action == "rest_self":
        mode = "self"
        text = REST_SELF_TEXT

    elif action == "rest_friend":
        mode = "friend"
        text = REST_FRIEND_TEXT

    else:
        await callback.answer("Неизвестное действие.")
        return

    prompt = await callback.message.reply(text)

    save_rest_session(
        telegram_id,
        mode,
        "form",
        prompt.message_id,
        {}
    )

    await callback.answer()


# =====================================================
# REST: SUBMIT REQUEST
# =====================================================

async def submit_rest_request(
    message: Message,
    mode: str,
    data: dict
):

    if ADMIN_CHAT_ID == 0:
        await message.reply(
            "Ошибка: ADMIN_CHAT_ID не настроен."
        )
        delete_rest_session(message.from_user.id)
        return

    if mode == "self":
        request_type = "self"
        target_id = message.from_user.id
        title = "🍀 <b>Новая заявка на взятие реста</b>"

    elif mode == "friend":
        request_type = "friend"
        target_id = None
        title = "🍀 <b>Новая заявка на взятие реста для друга</b>"

    else:
        return

    target_username = data["username"]
    target_nickname = data["nickname"]

    with db_connect() as conn:

        cur = conn.execute(
            """
            INSERT INTO rest_requests
            (
                applicant_id,
                target_id,
                request_type,
                reason,
                days,
                target_username,
                target_nickname,
                proof_file_id,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                message.from_user.id,
                target_id,
                request_type,
                data["reason"],
                data["days"],
                target_username,
                target_nickname,
                data.get("proof_file_id"),
                moscow_iso(moscow_now())
            )
        )

        request_id = cur.lastrowid
        conn.commit()

    applicant_username = (
        "@" + message.from_user.username
        if message.from_user.username
        else "не указан"
    )

    admin_text = (
        f"{title}\n\n"
        f"<b>Заявка №:</b> <code>{request_id}</code>\n"
        f"<b>Подал:</b> {safe_html(applicant_username)}\n"
        f"<b>Telegram ID подавшего:</b> "
        f"<code>{message.from_user.id}</code>\n\n"
        f"<b>Причина:</b>\n{safe_html(data['reason'])}\n\n"
        f"<b>Срок:</b> {data['days']} дн.\n"
        f"<b>Telegram игрока:</b> "
        f"{safe_html('@' + target_username)}\n"
        f"<b>Minecraft:</b> "
        f"<code>{safe_html(target_nickname)}</code>"
    )

    try:
        if mode == "friend":
            sent = await message.bot.send_photo(
                ADMIN_CHAT_ID,
                data["proof_file_id"],
                caption=admin_text,
                message_thread_id=REST_THREAD_ID or None,
                reply_markup=rest_admin_keyboard(request_id)
            )
        else:
            sent = await message.bot.send_message(
                ADMIN_CHAT_ID,
                admin_text,
                message_thread_id=REST_THREAD_ID or None,
                reply_markup=rest_admin_keyboard(request_id)
            )

        with db_connect() as conn:
            conn.execute(
                """
                UPDATE rest_requests
                SET admin_message_id = ?
                WHERE id = ?
                """,
                (sent.message_id, request_id)
            )
            conn.commit()

        delete_rest_session(message.from_user.id)

        await message.reply(
            "✅ Ваша заявка успешно отправлена администрации!\n"
            "Ожидайте решения в личных сообщениях бота."
        )

    except Exception:
        log.exception("Rest request forwarding failed")

        await message.reply(
            "Не удалось отправить заявку администрации. "
            "Попробуйте позже или обратитесь к администрации."
        )


# =====================================================
# REST: PRIVATE FORM REPLIES
# =====================================================

async def rest_private_input(message: Message) -> bool:

    if (
        not message.from_user
        or message.chat.type != "private"
    ):
        return False

    session = get_rest_session(message.from_user.id)

    if not session:
        return False

    if (
        not message.reply_to_message
        or message.reply_to_message.message_id
        != session["prompt_message_id"]
    ):
        return False

    telegram_id = message.from_user.id

    try:
        data = json.loads(session["data_json"] or "{}")
    except json.JSONDecodeError:
        data = {}

    mode = session["mode"]
    step = session["step"]

    # -------------------------------------------------
    # Основная анкета
    # -------------------------------------------------

    if step == "form":

        if not message.text:
            await message.reply(
                "Пожалуйста, отправьте ответы текстом "
                "одним сообщением в ответ на анкету."
            )
            return True

        values = parse_rest_lines(message.text, 4)

        if not values:
            await message.reply(
                "Не удалось распознать анкету.\n\n"
                "Укажите ровно 4 пункта, каждый с новой строки."
            )
            return True

        reason, days_text, username, nickname = values

        if len(reason) > 1000:
            await message.reply(
                "Причина слишком длинная. Максимум 1000 символов."
            )
            return True

        if not days_text.isdigit():
            await message.reply(
                "Количество дней необходимо указать числом."
            )
            return True

        days = int(days_text)

        if days < 1:
            await message.reply(
                "Нельзя указать 0 дней. Минимальный срок реста — 1 день."
            )
            return True

        if days > REST_MAX_DAYS:
            await message.reply(
                f"Максимальный срок реста — {REST_MAX_DAYS} дней."
            )
            return True

        username = normalize_username(username)

        if not re.fullmatch(r"[a-zA-Z0-9_]{5,32}", username):
            await message.reply(
                "Укажите корректный Telegram username без символа @."
            )
            return True

        if not MC_NAME_RE.fullmatch(nickname):
            await message.reply(
                "Minecraft-ник указан некорректно."
            )
            return True

        data = {
            "reason": reason,
            "days": days,
            "username": username,
            "nickname": nickname
        }

        if mode == "self":

            prompt = await message.reply(
                "Проверяю данные вашей регистрации..."
            )

            account = get_account(telegram_id)

            if not account:
                await prompt.edit_text(
                    "Не удалось найти вашу регистрацию."
                )
                delete_rest_session(telegram_id)
                return True

            actual_username = normalize_username(
                account["telegram"]
            )

            current_username = normalize_username(
                message.from_user.username or ""
            )

            if (
                username != current_username
                or username != actual_username
                or nickname.lower() != account["minecraft"].lower()
            ):
                await prompt.edit_text(
                    "Данные не совпадают с вашей регистрацией.\n\n"
                    "Проверьте Telegram username и Minecraft-ник."
                )
                return True

            await submit_rest_request(
                message,
                "self",
                data
            )
            return True

        if mode == "friend":

            data["proof_file_id"] = None

            prompt = await message.reply(
                "Теперь отправьте скриншот доказательства "
                "и разрешения вашего друга.\n\n"
                "Прикрепите изображение и отправьте его "
                "ответом на это сообщение."
            )

            save_rest_session(
                telegram_id,
                mode,
                "proof",
                prompt.message_id,
                data
            )
            return True

    # -------------------------------------------------
    # Скриншот друга
    # -------------------------------------------------

    if step == "proof":

        if not message.photo:
            await message.reply(
                "Для заявки на друга необходимо отправить "
                "скриншот изображением."
            )
            return True

        data["proof_file_id"] = message.photo[-1].file_id

        await submit_rest_request(
            message,
            "friend",
            data
        )
        return True

    # -------------------------------------------------
    # Продление
    # -------------------------------------------------

    if step == "extend":

        if not message.text:
            await message.reply(
                "Отправьте ответы текстом."
            )
            return True

        values = parse_rest_lines(message.text, 2)

        if not values:
            await message.reply(
                "Укажите ровно два пункта, каждый с новой строки."
            )
            return True

        date_text, reason = values
        requested_date = parse_date(date_text)

        if not requested_date:
            await message.reply(
                "Неверный формат даты.\n"
                "Используйте ДД.ММ.ГГГГ, например 25.12.2026."
            )
            return True

        if requested_date <= moscow_now().date():
            await message.reply(
                "Дата продления должна быть в будущем."
            )
            return True

        if not reason or len(reason) > 1000:
            await message.reply(
                "Причина должна содержать не более 1000 символов."
            )
            return True

        account = get_account(telegram_id)

        if not account or account["rank"] != "rest":
            await message.reply(
                "Вы больше не находитесь в ресте."
            )
            delete_rest_session(telegram_id)
            return True

        period = get_rest_period(telegram_id)

        if not period:
            await message.reply(
                "Не удалось найти срок вашего реста."
            )
            delete_rest_session(telegram_id)
            return True

        old_end = datetime.fromisoformat(
            period["ends_at"]
        ).astimezone(MOSCOW_TZ)

        requested_end = datetime.combine(
            requested_date,
            time(23, 59, 59),
            tzinfo=MOSCOW_TZ
        )

        if requested_end <= old_end:
            await message.reply(
                "Новая дата должна быть позже текущей даты окончания реста.\n"
                f"Сейчас рест заканчивается: "
                f"{old_end.strftime('%d.%m.%Y %H:%M')} МСК."
            )
            return True

        if ADMIN_CHAT_ID == 0:
            await message.reply(
                "Ошибка: ADMIN_CHAT_ID не настроен."
            )
            return True

        with db_connect() as conn:

            pending = conn.execute(
                """
                SELECT id
                FROM rest_requests
                WHERE applicant_id = ?
                AND request_type = 'extend'
                AND status = 'pending'
                """,
                (telegram_id,)
            ).fetchone()

            if pending:
                await message.reply(
                    "У вас уже есть заявка на продление, "
                    "ожидающая рассмотрения."
                )
                return True

            cur = conn.execute(
                """
                INSERT INTO rest_requests
                (
                    applicant_id,
                    target_id,
                    request_type,
                    reason,
                    target_username,
                    target_nickname,
                    requested_until,
                    status,
                    created_at
                )
                VALUES (?, ?, 'extend', ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    telegram_id,
                    telegram_id,
                    reason,
                    message.from_user.username or "",
                    account["minecraft"],
                    moscow_iso(requested_end),
                    moscow_iso(moscow_now())
                )
            )

            request_id = cur.lastrowid
            conn.commit()

        username = (
            "@" + message.from_user.username
            if message.from_user.username
            else "не указан"
        )

        admin_text = (
            "🍀 <b>Заявка на продление реста</b>\n\n"
            f"<b>Заявка №:</b> <code>{request_id}</code>\n"
            f"<b>Игрок:</b> {safe_html(username)}\n"
            f"<b>Telegram ID:</b> <code>{telegram_id}</code>\n"
            f"<b>Minecraft:</b> "
            f"<code>{safe_html(account['minecraft'])}</code>\n\n"
            f"<b>Продлить до:</b> "
            f"{requested_date.strftime('%d.%m.%Y')} 23:59 МСК\n\n"
            f"<b>Причина:</b>\n{safe_html(reason)}"
        )

        try:
            sent = await message.bot.send_message(
                ADMIN_CHAT_ID,
                admin_text,
                message_thread_id=REST_THREAD_ID or None,
                reply_markup=rest_admin_keyboard(request_id)
            )

            with db_connect() as conn:
                conn.execute(
                    """
                    UPDATE rest_requests
                    SET admin_message_id = ?
                    WHERE id = ?
                    """,
                    (sent.message_id, request_id)
                )
                conn.commit()

            delete_rest_session(telegram_id)

            await message.reply(
                "✅ Заявка на продление реста отправлена администрации."
            )

        except Exception:
            log.exception("Rest extension forwarding failed")
            await message.reply(
                "Не удалось отправить заявку администрации."
            )

        return True

    return False


# =====================================================
# REST: MANAGE CALLBACKS
# =====================================================

async def rest_manage_callback(callback: CallbackQuery):

    if not callback.from_user or not callback.message:
        return

    telegram_id = callback.from_user.id
    account = get_account(telegram_id)

    if not account or account["rank"] != "rest":
        await callback.answer(
            "Эта функция доступна только игрокам в ресте.",
            show_alert=True
        )
        return

    if callback.data == "rest_extend":

        if get_rest_session(telegram_id):
            await callback.answer(
                "У вас уже есть незавершённая анкета.",
                show_alert=True
            )
            return

        prompt = await callback.message.reply(
            REST_EXTEND_TEXT
        )

        save_rest_session(
            telegram_id,
            "extend",
            "extend",
            prompt.message_id,
            {}
        )

        await callback.answer()
        return

    if callback.data == "rest_remove":

        await callback.message.reply(
            "Вы уверены, что хотите снять рест?",
            reply_markup=rest_confirm_keyboard()
        )

        await callback.answer()
        return

    if callback.data == "rest_remove_yes":

        with db_connect() as conn:
            original_rank = restore_rest(
                conn,
                telegram_id
            )
            conn.commit()

        if original_rank is None:
            await callback.answer(
                "Вы уже не находитесь в ресте.",
                show_alert=True
            )
            return

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

        await callback.message.reply(
            "Вы сняли свой рест. Добро пожаловать обратно!\n"
            f"Ваш восстановленный ранг: <b>{safe_html(original_rank)}</b>"
        )

        await callback.answer("Рест снят.")
        return

    if callback.data == "rest_remove_no":

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

        await callback.message.reply(
            "Что вы хотите сделать с рестом?",
            reply_markup=rest_manage_keyboard()
        )

        await callback.answer()
        return


# =====================================================
# REST: ADMIN APPROVE / REJECT
# =====================================================

async def rest_admin_decision(callback: CallbackQuery):

    if (
        not callback.from_user
        or not is_senior_admin(callback.from_user.id)
    ):
        await callback.answer(
            "Только owner и st_admin могут принимать решения.",
            show_alert=True
        )
        return

    if not callback.message:
        await callback.answer()
        return

    if callback.message.chat.id != ADMIN_CHAT_ID:
        await callback.answer(
            "Недоступно в этом чате.",
            show_alert=True
        )
        return

    try:
        action, request_id_text = (
            callback.data or ""
        ).split(":", 1)

        request_id = int(request_id_text)

    except (ValueError, AttributeError):
        await callback.answer(
            "Некорректная заявка.",
            show_alert=True
        )
        return

    if action not in {
        "rest_approve",
        "rest_reject"
    }:
        await callback.answer(
            "Неизвестное действие.",
            show_alert=True
        )
        return

    with db_connect() as conn:

        request = conn.execute(
            """
            SELECT *
            FROM rest_requests
            WHERE id = ?
            AND status = 'pending'
            """,
            (request_id,)
        ).fetchone()

        if not request:
            await callback.answer(
                "Заявка уже обработана или не найдена.",
                show_alert=True
            )
            return

        if action == "rest_reject":

            prompt = await callback.message.reply(
                "По какой причине отклоняете рест?\n\n"
                "Ответьте текстом на это сообщение."
            )

            conn.execute(
                """
                UPDATE rest_requests
                SET status = 'awaiting_rejection_reason',
                    reject_prompt_message_id = ?,
                    reject_admin_id = ?
                WHERE id = ?
                AND status = 'pending'
                """,
                (
                    prompt.message_id,
                    callback.from_user.id,
                    request_id
                )
            )

            conn.commit()

            await callback.answer(
                "Ожидаю причину отклонения."
            )
            return

        request_type = request["request_type"]
        target_id = None
        target_user = None
        original_rank = None

        if request_type == "self":

            target_id = request["applicant_id"]

            admin = get_admin(target_id)

            if admin:
                target_user = {
                    "rank": admin.get("rank"),
                    "minecraft_nickname": admin.get("minecraft"),
                    "telegram_username": normalize_username(
                        admin.get("telegram") or ""
                    )
                }
            else:
                target_user = conn.execute(
                    """
                    SELECT *
                    FROM users
                    WHERE telegram_id = ?
                    """,
                    (target_id,)
                ).fetchone()

            if not target_user:
                await callback.answer(
                    "Такого игрока не существует. "
                    "Проверьте свои данные.",
                    show_alert=True
                )
                return

            actual_nickname = (
                target_user["minecraft_nickname"]
                if isinstance(target_user, dict)
                else target_user["minecraft_nickname"]
            )

            actual_username = normalize_username(
                target_user["telegram_username"] or ""
            )

            if (
                actual_nickname.lower()
                != request["target_nickname"].lower()
                or actual_username
                != normalize_username(request["target_username"] or "")
            ):
                await callback.answer(
                    "Данные игрока не совпадают с регистрацией.",
                    show_alert=True
                )
                return

            original_rank = target_user["rank"]

        elif request_type == "friend":

            target_username = normalize_username(
                request["target_username"] or ""
            )

            target_nickname = request["target_nickname"] or ""

            target_user = conn.execute(
                """
                SELECT *
                FROM users
                WHERE minecraft_nickname = ? COLLATE NOCASE
                AND LOWER(REPLACE(telegram_username, '@', '')) = ?
                """,
                (
                    target_nickname,
                    target_username
                )
            ).fetchone()

            if not target_user:
                await callback.answer(
                    "Такого игрока не существует. "
                    "Проверьте его данные.",
                    show_alert=True
                )

                try:
                    await callback.bot.send_message(
                        request["applicant_id"],
                        "Такого игрока не существует. "
                        "Проверьте его данные."
                    )
                except Exception:
                    pass

                return

            target_id = target_user["telegram_id"]
            original_rank = target_user["rank"]

        elif request_type == "extend":

            target_id = request["applicant_id"]

            target_user = get_account(target_id)

            if not target_user or target_user["rank"] != "rest":
                await callback.answer(
                    "Игрок больше не находится в ресте.",
                    show_alert=True
                )
                return

            period = conn.execute(
                """
                SELECT *
                FROM rest_periods
                WHERE telegram_id = ?
                """,
                (target_id,)
            ).fetchone()

            if not period:
                await callback.answer(
                    "Не найден действующий срок реста.",
                    show_alert=True
                )
                return

            end_time = datetime.fromisoformat(
                request["requested_until"]
            ).astimezone(MOSCOW_TZ)

            old_end = datetime.fromisoformat(
                period["ends_at"]
            ).astimezone(MOSCOW_TZ)

            if end_time <= old_end:
                await callback.answer(
                    "Новая дата уже не позже текущей даты окончания.",
                    show_alert=True
                )
                return

            conn.execute(
                """
                UPDATE rest_periods
                SET ends_at = ?,
                    request_id = ?
                WHERE telegram_id = ?
                """,
                (
                    moscow_iso(end_time),
                    request_id,
                    target_id
                )
            )

        else:
            await callback.answer(
                "Неизвестный тип заявки.",
                show_alert=True
            )
            return

        if request_type in {"self", "friend"}:

            if original_rank not in REST_ELIGIBLE_RANKS:
                await callback.answer(
                    "Игрок не может получить рест с текущим рангом.",
                    show_alert=True
                )
                return

            if get_rest_period(target_id):
                await callback.answer(
                    "Игрок уже находится в ресте.",
                    show_alert=True
                )
                return

            now = moscow_now()

            end_time = now + timedelta(
                days=int(request["days"])
            )

            activate_rest(
                conn,
                target_id,
                original_rank,
                end_time,
                request_id
            )

        conn.execute(
            """
            UPDATE rest_requests
            SET status = 'approved',
                target_id = ?
            WHERE id = ?
            """,
            (target_id, request_id)
        )

        conn.commit()

    try:

        if request_type == "extend":
            notification = (
                "Ваша заявка на продление реста была принята.\n\n"
                f"Теперь ваш рест действует до "
                f"{end_time.strftime('%d.%m.%Y %H:%M')} МСК."
            )
        else:
            notification = (
                "Ваша заявка на рест была принята.\n\n"
                f"Теперь вы находитесь в ресте до "
                f"{end_time.strftime('%d.%m.%Y %H:%M')} МСК."
            )

        await callback.bot.send_message(
            target_id,
            notification
        )

        notify_label = "Игрок уведомлён."

    except Exception:
        log.exception(
            "Could not notify rest user: %s",
            target_id
        )
        notify_label = (
            "Не удалось отправить уведомление игроку."
        )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.reply(
        "✅ Заявка одобрена.\n"
        f"{notify_label}"
    )

    await callback.answer("Заявка одобрена.")


# =====================================================
# REST: REJECTION REASON
# =====================================================

async def rest_rejection_reply(message: Message) -> bool:

    if (
        not message.from_user
        or message.chat.id != ADMIN_CHAT_ID
        or not message.reply_to_message
        or not message.text
    ):
        return False

    if not is_senior_admin(message.from_user.id):
        return False

    reason = message.text.strip()

    if not reason:
        await message.reply(
            "Причина не может быть пустой."
        )
        return True

    if len(reason) > 1500:
        await message.reply(
            "Причина слишком длинная. Максимум 1500 символов."
        )
        return True

    with db_connect() as conn:

        request = conn.execute(
            """
            SELECT *
            FROM rest_requests
            WHERE reject_prompt_message_id = ?
            AND reject_admin_id = ?
            AND status = 'awaiting_rejection_reason'
            """,
            (
                message.reply_to_message.message_id,
                message.from_user.id
            )
        ).fetchone()

        if not request:
            return False

        conn.execute(
            """
            UPDATE rest_requests
            SET status = 'rejected'
            WHERE id = ?
            AND status = 'awaiting_rejection_reason'
            """,
            (request["id"],)
        )

        conn.commit()

    # При отклонении уведомляем заявителя.
    try:
        await message.bot.send_message(
            request["applicant_id"],
            "Вашу заявку на рест отклонили.\n\n"
            f"Причина: {reason}"
        )

        result = "Заявка отклонена. Заявитель уведомлён."

    except Exception:
        log.exception(
            "Could not notify rejected rest applicant"
        )

        result = (
            "Заявка отклонена, "
            "но уведомить заявителя не удалось."
        )

    await message.reply(result)

    return True


# =====================================================
# REST EXPIRATION WORKER
# =====================================================

async def rest_expiration_worker(bot: Bot):

    while True:

        try:
            now = moscow_now()

            with db_connect() as conn:

                expired = conn.execute(
                    """
                    SELECT *
                    FROM rest_periods
                    WHERE ends_at <= ?
                    """,
                    (moscow_iso(now),)
                ).fetchall()

                restored = []

                for item in expired:

                    original_rank = restore_rest(
                        conn,
                        item["telegram_id"]
                    )

                    if original_rank is not None:
                        restored.append({
                            "telegram_id": item["telegram_id"],
                            "original_rank": original_rank
                        })

                conn.commit()

            for item in restored:

                try:
                    await bot.send_message(
                        item["telegram_id"],
                        "Срок вашего реста закончился.\n\n"
                        "Ваш прежний ранг восстановлен: "
                        f"<b>{safe_html(item['original_rank'])}</b>.\n"
                        "Добро пожаловать обратно в CloverTeam!"
                    )

                except Exception:
                    log.warning(
                        "Could not notify expired rest user: %s",
                        item["telegram_id"]
                    )

        except Exception:
            log.exception(
                "Rest expiration worker error"
            )

        await asyncio.sleep(60)


# =====================================================
# RCON
# =====================================================

def create_rcon_packet(
    request_id: int,
    packet_type: int,
    payload: str
) -> bytes:

    encoded = payload.encode("utf-8") + b"\x00\x00"
    length = 4 + 4 + len(encoded)

    return (
        struct.pack("<i", length)
        + struct.pack("<i", request_id)
        + struct.pack("<i", packet_type)
        + encoded
    )


async def read_rcon_packet(reader: asyncio.StreamReader):

    length_data = await reader.readexactly(4)
    length = struct.unpack("<i", length_data)[0]

    if length < 10 or length > 4_194_304:
        raise RuntimeError(
            f"Некорректный размер RCON-пакета: {length}"
        )

    packet_data = await reader.readexactly(length)

    if len(packet_data) < 10:
        raise RuntimeError("Неполный RCON-пакет")

    request_id, packet_type = struct.unpack(
        "<ii",
        packet_data[:8]
    )

    payload = packet_data[8:-2].decode(
        "utf-8",
        errors="replace"
    )

    return request_id, packet_type, payload


async def rcon_sync(command: str) -> str:

    if not RCON_HOST or not RCON_PASSWORD:
        raise RuntimeError("RCON configuration is missing")

    reader = None
    writer = None

    try:
        reader, writer = await asyncio.open_connection(
            RCON_HOST,
            RCON_PORT
        )

        writer.write(
            create_rcon_packet(
                1,
                3,
                RCON_PASSWORD
            )
        )
        await writer.drain()

        auth_id, auth_type, auth_response = (
            await read_rcon_packet(reader)
        )

        if auth_id == -1:
            raise RuntimeError("RCON authentication failed")

        if auth_id != 1:
            raise RuntimeError(
                "Invalid RCON authentication response"
            )

        writer.write(
            create_rcon_packet(
                2,
                2,
                command
            )
        )
        await writer.drain()

        response_parts = []

        while True:
            response_id, response_type, response = (
                await read_rcon_packet(reader)
            )

            if response_id != 2:
                raise RuntimeError(
                    f"Invalid RCON response ID: {response_id}"
                )

            response_parts.append(response)

            if len(response) < 4096:
                break

        return "".join(response_parts)

    finally:
        if writer:
            writer.close()

            try:
                await writer.wait_closed()
            except Exception:
                pass


async def rcon_command(command: str) -> str:
    return await asyncio.wait_for(
        rcon_sync(command),
        timeout=15
    )


# =====================================================
# /WARN — PLAYER WARNINGS
# =====================================================

async def cmd_warn(message: Message):
    if not message.from_user:
        return

    actor_id = message.from_user.id
    actor = get_account(actor_id)
    if not actor:
        await message.reply("Ваш аккаунт не найден или недоступен.")
        return

    actor_rank = actor.get("rank")
    if actor_rank == "eventor" or actor_rank not in WARN_RANK_LEVEL and actor_rank != "owner":
        await message.reply("У вас недостаточно прав для использования этой команды.")
        return
    if actor_rank not in {"moder", "admin", "tech_admin", "st_admin", "owner"}:
        await message.reply("Выдавать варны могут администраторы ранга moder и выше (eventor исключён).")
        return

    args = extract_command(message)
    parts = args.split(maxsplit=2)
    if len(parts) != 3:
        await message.reply(
            "Использование:\n<code>/warn &lt;MinecraftNick/TG username/TG ID&gt; &lt;дни&gt; &lt;причина&gt;</code>\n\n"
            "Укажите 0 для перманентного варна."
        )
        return

    target_key, days_raw, reason = parts
    if not days_raw.isdigit():
        await message.reply("Количество дней должно быть целым неотрицательным числом.")
        return
    days = int(days_raw)
    reason = reason.strip()
    if not reason or len(reason) > 350 or any(c in reason for c in "\r\n\x00"):
        await message.reply("Причина должна быть одной строкой длиной до 350 символов.")
        return

    target = get_warn_target(target_key)
    if not target:
        await message.reply("Игрок не найден. Он должен быть зарегистрирован в CloverTeam.")
        return
    target_id = target["telegram_id"]
    target_rank = target.get("rank", "player")
    if target_rank in {"banned", "warnbanned"}:
        await message.reply("Этот пользователь уже заблокирован.")
        return

    # Уровень admin и tech_admin одинаковый. Нельзя варнить равного или старшего.
    if actor_rank != "owner":
        actor_level = WARN_RANK_LEVEL.get(actor_rank, -1)
        target_level = WARN_RANK_LEVEL.get(target_rank, -1)
        if target_rank in {"eventor", "rest"}:
            target_level = WARN_RANK_LEVEL.get(
                get_account(target_id).get("original_rank") if get_account(target_id) else "", -1
            ) if target_rank == "rest" else WARN_RANK_LEVEL.get("moder", 2)
        if target_level >= actor_level:
            await message.reply(
                "Вы не можете выдать варн администратору выше своего ранга/одному рангу."
            )
            return

    if not target["minecraft"] or not MC_NAME_RE.fullmatch(target["minecraft"]):
        await message.reply("У пользователя не указан корректный Minecraft-ник.")
        return

    now = moscow_now()
    expires_at = None if days == 0 else moscow_iso(now + timedelta(days=days))
    issued_at = moscow_iso(now)

    try:
        with db_connect() as conn:
            count = refresh_warn_count(conn, target_id, now)
            conn.execute(
                "INSERT INTO warn_history "
                "(telegram_id, admin_id, reason, days, issued_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active')",
                (target_id, actor_id, reason, days, issued_at, expires_at)
            )
            count = refresh_warn_count(conn, target_id, now)
            should_ban = count >= 3

            if should_ban:
                conn.execute(
                    "UPDATE users SET rank = 'warnbanned' WHERE telegram_id = ?",
                    (target_id,)
                )
                conn.commit()
            else:
                conn.commit()
    except Exception:
        log.exception("Could not store warn")
        await message.reply("Не удалось сохранить варн в базе данных.")
        return

    if should_ban:
        # Если пользователь является записью admins.json, ранг в users также создаётся.
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO users(telegram_id, telegram_username, minecraft_nickname, rank) "
                "VALUES (?, ?, ?, 'warnbanned') "
                "ON CONFLICT(telegram_id) DO UPDATE SET rank = 'warnbanned'",
                (target_id, target["username"], target["minecraft"] or None)
            )
            conn.commit()

        server_results = []
        try:
            await rcon_command(
                "ban " + target["minecraft"] + " " +
                "Достижение максимального количества варнов"
            )
            server_results.append("бан Minecraft выполнен")
        except Exception:
            log.exception("Minecraft ban via RCON failed for %s", target["minecraft"])
            server_results.append("ошибка Minecraft-бана")
        for command in (f"swl remove {target['minecraft']}", "swl reload"):
            try:
                await rcon_command(command)
                server_results.append(f"{command}: OK")
            except Exception:
                log.exception("RCON command failed: %s", command)
                server_results.append(f"{command}: ошибка")

        try:
            await message.bot.send_message(
                target_id,
                "Вы были забанены в CloverTeam навсегда\n\n"
                "Причина: Достижение максимального количества варнов"
            )
            dm_result = "Личное уведомление отправлено."
        except Exception:
            dm_result = "Не удалось отправить ЛС (пользователь мог не открыть диалог с ботом)."

        await message.reply(
            "⛔ Достигнут лимит варнов: пользователь заблокирован.\n"
            f"Игрок: <code>{safe_html(target['minecraft'])}</code>\n"
            f"Активных варнов: <b>{count}</b>\n"
            f"{safe_html(dm_result)}\n"
            f"RCON: {safe_html('; '.join(server_results))}"
        )
        return

    # Команда плагина получает причину в Base64 URL-safe, чтобы пробелы и символы
    # причины не ломали аргументы RCON.
    import base64
    encoded_reason = base64.urlsafe_b64encode(reason.encode("utf-8")).decode("ascii").rstrip("=")
    duration_arg = "PERMANENT" if days == 0 else str(days)
    try:
        await rcon_command(
            f"cloverwarn {target['minecraft']} {duration_arg} {encoded_reason}"
        )
        with db_connect() as conn:
            conn.execute(
                "UPDATE warn_history SET server_notified = 1 "
                "WHERE id = (SELECT MAX(id) FROM warn_history WHERE telegram_id = ?)",
                (target_id,)
            )
            conn.commit()
    except Exception:
        log.exception("Could not send warn to Minecraft plugin")
        await message.reply(
            "Варн сохранён в базе данных, но не удалось отправить его на сервер через RCON. "
            "Проверьте, что обновлённый плагин установлен."
        )
        return

    until_text = "перманентно" if days == 0 else expires_at
    try:
        await message.bot.send_message(
            target_id,
            "Вам был выдан варн\n"
            f"Причина: {safe_html(reason)}\n"
            f"До: {safe_html(until_text)}"
        )
        dm_result = "Игрок уведомлён в личных сообщениях."
    except Exception:
        dm_result = "Не удалось отправить игроку ЛС (возможно, он не открывал диалог с ботом)."

    await message.reply(
        "Варн выдан.\n"
        f"Игрок: <code>{safe_html(target['minecraft'])}</code>\n"
        f"Активных варнов: <b>{count}/3</b>\n"
        f"Срок: <b>{safe_html(until_text)}</b>\n"
        f"{safe_html(dm_result)}"
    )


# =====================================================
# /UNWARN — REMOVE ONE ACTIVE WARNING
# =====================================================

async def cmd_unwarn(message: Message):
    if not message.from_user:
        return

    actor_id = message.from_user.id
    actor = get_account(actor_id)
    if not actor:
        await message.reply("Ваш аккаунт не найден или недоступен.")
        return

    actor_rank = actor.get("rank")
    if actor_rank == "eventor" or actor_rank not in {
        "moder", "admin", "tech_admin", "st_admin", "owner"
    }:
        await message.reply(
            "Снимать варны могут администраторы ранга moder и выше (eventor исключён)."
        )
        return

    args = extract_command(message)
    parts = args.split()
    if len(parts) != 1:
        await message.reply(
            "Использование:\n"
            "<code>/unwarn &lt;MinecraftNick/TG username/TG ID&gt;</code>"
        )
        return

    target = get_warn_target(parts[0])
    if not target:
        await message.reply("Игрок не найден. Он должен быть зарегистрирован в CloverTeam.")
        return

    target_id = target["telegram_id"]
    target_rank = target.get("rank", "player")

    # Те же ограничения иерархии, что и у /warn.
    if actor_rank != "owner":
        actor_level = WARN_RANK_LEVEL.get(actor_rank, -1)
        target_level = WARN_RANK_LEVEL.get(target_rank, -1)
        if target_rank == "rest":
            target_account = get_account(target_id)
            target_level = WARN_RANK_LEVEL.get(
                target_account.get("original_rank") if target_account else "", -1
            )
        elif target_rank == "eventor":
            target_level = WARN_RANK_LEVEL["moder"]

        if target_level >= actor_level:
            await message.reply(
                "Вы не можете снимать варн администратору выше своего ранга/одному рангу."
            )
            return

    now = moscow_now()
    try:
        with db_connect() as conn:
            # Сначала обновляем просроченные записи, затем снимаем ровно
            # один самый поздний из оставшихся активных варнов.
            active_count = refresh_warn_count(conn, target_id, now)
            latest = conn.execute(
                "SELECT id, reason, days, issued_at FROM warn_history "
                "WHERE telegram_id = ? AND status = 'active' "
                "ORDER BY id DESC LIMIT 1",
                (target_id,)
            ).fetchone()

            if not latest:
                conn.commit()
                await message.reply("У этого игрока нет активных варнов.")
                return

            conn.execute(
                "UPDATE warn_history SET status = 'removed' WHERE id = ?",
                (latest["id"],)
            )
            remaining = refresh_warn_count(conn, target_id, now)
            conn.commit()
    except Exception:
        log.exception("Could not remove warning")
        await message.reply("Не удалось снять варн из базы данных.")
        return

    await message.reply(
        "Один активный варн снят.\n"
        f"Игрок: <code>{safe_html(target['minecraft'] or target['username'] or target_id)}</code>\n"
        f"Снятый варн: <code>#{int(latest['id'])}</code>\n"
        f"Причина: {safe_html(latest['reason'])}\n"
        f"Осталось активных варнов: <b>{remaining}/3</b>\n\n"
        "Ранг и серверные блокировки не изменялись."
    )


# =====================================================
# /ONLINE
# =====================================================

async def cmd_online(message: Message):

    account = await require_registered(message)

    if not account:
        return

    if account["rank"] == "legacy":
        await message.reply(
            "У вас недостаточно прав для использования этой команды!"
        )
        return

    try:
        response = await rcon_command("cloverstats")

        log.info(
            "RAW CLOVERSTATS RESPONSE: %r",
            response
        )

        match = re.search(
            r"CLOVER_STATS\s+players=(\d+)\s+ops=(\d+)\s+names=(.*)",
            response,
            re.DOTALL
        )

        if not match:
            await message.reply(
                "Не удалось обработать ответ Paper-плагина.\n"
                "Проверьте вывод команды cloverstats."
            )
            return

        players = int(match.group(1))
        ops = int(match.group(2))
        names = match.group(3).strip()

        if names == "-":
            names = "Нет игроков"

        await message.reply(
            "<b>Кол-во онлайн в сервере</b>\n\n"
            f"Игроков онлайн: <b>{players}</b>\n"
            f"Из них OP: <b>{ops}</b>\n\n"
            f"<b>Список игроков:</b>\n"
            f"{safe_html(names)}"
        )

    except asyncio.TimeoutError:
        await message.reply(
            "Время ожидания ответа RCON истекло."
        )

    except Exception:
        log.exception("Online command failed")
        await message.reply(
            "Не удалось получить онлайн сервера. "
            "Проверьте RCON и плагин."
        )


# =====================================================
# /SAY
# =====================================================

async def cmd_say(message: Message):

    account = await require_registered(message)

    if not account:
        return

    if account["rank"] not in STAFF_RANKS:
        await message.reply(
            "У вас недостаточно прав для использования этой команды!"
        )
        return

    text = extract_command(message)

    if not text:
        await message.reply(
            "Использование:\n/say текст"
        )
        return

    if (
        len(text) > 400
        or "\n" in text
        or "\r" in text
        or "\x00" in text
    ):
        await message.reply(
            "Сообщение слишком длинное "
            "или имеет недопустимый формат."
        )
        return

    telegram = (
        account["telegram"]
        or ("ID " + str(message.from_user.id))
    )

    payload = {
        "text": "",
        "extra": [
            {
                "text": "[TLG] ",
                "color": "aqua"
            },
            {
                "text": account["minecraft"],
                "color": "red"
            },
            {
                "text": f" (TG: {telegram}): ",
                "color": "gray"
            },
            {
                "text": text,
                "color": "white"
            }
        ]
    }

    try:
        await rcon_command(
            "tellraw @a "
            + json.dumps(
                payload,
                ensure_ascii=False
            )
        )

        await message.reply(
            "Сообщение отправлено в игровой чат."
        )

    except Exception:
        log.exception("Say command failed")
        await message.reply(
            "Не удалось отправить сообщение через RCON."
        )


# =====================================================
# /JAVA
# =====================================================

async def cmd_java(message: Message):

    account = await require_registered(message)

    if not account:
        return

    if account["rank"] not in JAVA_RANKS:
        await message.reply(
            "У вас недостаточно прав для использования этой команды!"
        )
        return

    command = extract_command(message).lstrip("/")

    if not command:
        await message.reply(
            "Использование:\n/java команда"
        )
        return

    if (
        len(command) > 240
        or any(c in command for c in "\r\n\x00")
    ):
        await message.reply(
            "Команда имеет недопустимый формат."
        )
        return

    try:
        status = await message.reply(
            "Отправка команды:\n"
            f"<code>{safe_html(command)}</code>"
        )

        output = await rcon_command(command)

        if not output:
            output = "Консоль не вернула результат."

        output = output[:3000]

        await status.edit_text(
            "Отправка команды:\n"
            f"<code>{safe_html(command)}</code>\n\n"
            "Результат:\n"
            f"{format_code(output)}"
        )

    except asyncio.TimeoutError:
        await message.reply(
            "Время ожидания ответа RCON истекло."
        )

    except Exception:
        log.exception("Java command failed")
        await message.reply(
            "Не удалось выполнить команду через RCON."
        )


# =====================================================
# PRIVATE MESSAGE ROUTER
# =====================================================

async def private_reply_router(message: Message):

    if message.chat.type != "private":
        return

    handled = await rest_private_input(message)

    if handled:
        return

    await application_reply(message)


# =====================================================
# ADMIN CHAT REPLY ROUTER
# =====================================================

async def admin_reply_router(message: Message):

    if message.chat.id != ADMIN_CHAT_ID:
        return

    handled = await cmd_ankban(message)

    if handled:
        return

    handled = await rest_rejection_reply(message)

    if handled:
        return


# =====================================================
# STARTUP
# =====================================================

async def main():

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    if not RCON_HOST or not RCON_PASSWORD:
        raise RuntimeError("RCON settings are missing")

    init_db()

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )

    dp = Dispatcher()
    dp.message.outer_middleware(LegacyAccessMiddleware())

    # ---------------------------------------------
    # User commands
    # ---------------------------------------------

    dp.message.register(
        cmd_start,
        Command("start")
    )

    dp.message.register(
        cmd_rest,
        Command("rest")
    )

    dp.message.register(
        cmd_reg,
        Command("reg")
    )

    dp.message.register(
        cmd_unreg,
        Command("unreg")
    )

    dp.message.register(
        cmd_online,
        Command("online")
    )

    dp.message.register(
        cmd_say,
        Command("say")
    )

    dp.message.register(
        cmd_java,
        Command("java")
    )

    dp.message.register(
        cmd_warn,
        Command("warn")
    )

    dp.message.register(
        cmd_unwarn,
        Command("unwarn")
    )

    # ---------------------------------------------
    # Private replies
    # ---------------------------------------------

    dp.message.register(
        private_reply_router,
        F.chat.type == "private",
        F.reply_to_message
    )

    # ---------------------------------------------
    # Admin replies
    # ---------------------------------------------

    dp.message.register(
        admin_reply_router,
        F.chat.id == ADMIN_CHAT_ID,
        F.reply_to_message,
        F.text
    )

    # ---------------------------------------------
    # Main chat membership tracking
    # ---------------------------------------------

    dp.chat_member.register(track_legacy_chat_member)

    # ---------------------------------------------
    # Rest callbacks
    # ---------------------------------------------

    dp.callback_query.register(
        rest_start_callback,
        F.data.in_({
            "rest_self",
            "rest_friend"
        })
    )

    dp.callback_query.register(
        rest_manage_callback,
        F.data.in_({
            "rest_extend",
            "rest_remove",
            "rest_remove_yes",
            "rest_remove_no"
        })
    )

    dp.callback_query.register(
        rest_admin_decision,
        F.data.startswith("rest_approve:")
        | F.data.startswith("rest_reject:")
    )

    # ---------------------------------------------
    # Application callbacks
    # ---------------------------------------------

    dp.callback_query.register(
        application_decision,
        F.data.startswith("app_")
    )

    # ---------------------------------------------
    # Background task
    # ---------------------------------------------

    expiration_task = asyncio.create_task(
        rest_expiration_worker(bot)
    )

    warn_expiration_task = asyncio.create_task(
        warn_expiration_worker()
    )

    log.info("CloverTeam bot started")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )

    finally:
        expiration_task.cancel()
        warn_expiration_task.cancel()

        for task in (expiration_task, warn_expiration_task):
            try:
                await task
            except asyncio.CancelledError:
                pass

        await bot.session.close()




if __name__ == "__main__":
    asyncio.run(main())