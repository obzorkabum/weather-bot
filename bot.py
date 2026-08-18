import os
import sys
import asyncio
import aiohttp
import asyncpg
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWM_API_KEY = os.environ["OWM_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
OWM_BASE = "https://api.openweathermap.org/data/2.5/forecast"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
db = None

WMO_EMOJI = {
    (200, 232): "\u26c8\ufe0f",
    (300, 321): "\U0001f327\ufe0f",
    (322, 322): "\U0001f328\ufe0f",
    (500, 531): "\U0001f329\ufe0f",
    (600, 622): "\u2744\ufe0f",
    (701, 781): "\U0001f32b\ufe0f",
    (800, 800): "\u2600\ufe0f",
    (801, 804): "\u26c5",
}

RUSSIAN_CITIES = {
    "москва": "Moscow,RU",
    "санкт-петербург": "Saint Petersburg,RU",
    "петербург": "Saint Petersburg,RU",
    "питер": "Saint Petersburg,RU",
    "новосибирск": "Novosibirsk,RU",
    "екатеринбург": "Yekaterinburg,RU",
    "казань": "Kazan,RU",
    "нижний новгород": "Nizhny Novgorod,RU",
    "челябинск": "Chelyabinsk,RU",
    "самара": "Samara,RU",
    "омск": "Omsk,RU",
    "ростов-на-дону": "Rostov-on-Don,RU",
    "уфа": "Ufa,RU",
    "красноярск": "Krasnoyarsk,RU",
    "воронеж": "Voronezh,RU",
    "пермь": "Perm,RU",
    "волгоград": "Volgograd,RU",
    "краснодар": "Krasnodar,RU",
    "саратов": "Saratov,RU",
    "тюмень": "Tyumen,RU",
    "тула": "Tula,RU",
    "иркутск": "Irkutsk,RU",
    "барнаул": "Barnaul,RU",
    "житомир": "Zhytomyr,UA",
    "харьков": "Kharkiv,UA",
    "одесса": "Odesa,UA",
    "киев": "Kyiv,UA",
    "минск": "Minsk,BY",
}

WEEKDAYS_RU = {
    0: "\U0001f519 Пн",
    1: "\U0001f519 Вт",
    2: "\U0001f519 Ср",
    3: "\U0001f519 Чт",
    4: "\U0001f519 Пт",
    5: "\U0001f520 Сб",
    6: "\U0001f521 Вс",
}

MAX_FAVORITES = 3

user_state = {}


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="\U0001f3ef \u041c\u043e\u0438 \u0433\u043e\u0440\u043e\u0434\u0430")],
            [KeyboardButton(text="\u2795 \u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434"), KeyboardButton(text="\u2796 \u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434")],
            [KeyboardButton(text="\u2139\ufe0f \u041f\u043e\u043c\u043e\u0449\u044c")],
        ],
        resize_keyboard=True,
    )


async def init_db():
    global db
    db = await asyncpg.create_pool(DATABASE_URL)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id BIGINT,
            city    TEXT NOT NULL,
            query   TEXT NOT NULL,
            PRIMARY KEY (user_id, city)
        )
    """)


async def add_favorite(user_id: int, city: str, query: str) -> tuple[bool, str]:
    count = await db.fetchval(
        "SELECT COUNT(*) FROM favorites WHERE user_id = $1", user_id
    )
    if count >= MAX_FAVORITES:
        return False, f"\u274c \u041c\u0430\u043a\u0441\u0438\u043c\u0443\u043c {MAX_FAVORITES} \u043c\u0435\u0441\u0442. \u0423\u0434\u0430\u043b\u0438 \u043b\u0438\u0431\u043e \u0434\u0440\u0443\u0433\u043e\u0435 \u0441 /remove."
    exists = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM favorites WHERE user_id=$1 AND city=$2)",
        user_id, city,
    )
    if exists:
        return False, f"\u274c {city} \u0443\u0436\u0435 \u0432 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u043c."
    await db.execute(
        "INSERT INTO favorites (user_id, city, query) VALUES ($1, $2, $3)",
        user_id, city, query,
    )
    return True, f"\u2705 {city} \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e!"


async def remove_favorite(user_id: int, city: str) -> tuple[bool, str]:
    result = await db.execute(
        "DELETE FROM favorites WHERE user_id=$1 AND city=$2",
        user_id, city,
    )
    if result == "DELETE 0":
        return False, f"\u274c {city} \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0432 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u043c."
    return True, f"\u2705 {city} \u0443\u0434\u0430\u043b\u0435\u043d \u0438\u0437 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e."


async def get_favorites(user_id: int) -> list[asyncpg.Record]:
    return await db.fetch(
        "SELECT city, query FROM favorites WHERE user_id=$1 ORDER BY city",
        user_id,
    )


def resolve_city(text: str) -> tuple[str, str]:
    lookup = text.strip().lower()
    query = RUSSIAN_CITIES.get(lookup, text.strip())
    city_display = text.strip().title() if query == text.strip() else text.strip()
    return city_display, query


def get_emoji(code: int) -> str:
    for (lo, hi), emoji in WMO_EMOJI.items():
        if lo <= code <= hi:
            return emoji
    return "\U0001f324\ufe0f"


async def fetch_weather(city: str) -> dict:
    params = {
        "q": city,
        "appid": OWM_API_KEY,
        "units": "metric",
        "lang": "ru",
        "cnt": 40,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(OWM_BASE, params=params) as resp:
            body = await resp.text()
            print(f"[OWM] status={resp.status} city={city} key_present={bool(OWM_API_KEY)} body={body[:200]}", file=sys.stderr)
            if resp.status == 404:
                raise ValueError("city_not_found")
            if resp.status != 200:
                raise ValueError("api_error")
            return await resp.json()


def format_forecast(data: dict) -> str:
    city_name = data["city"]["name"]
    country = data["city"]["country"]
    daily = {}

    for item in data["list"]:
        dt = datetime.fromtimestamp(item["dt"])
        day = dt.date()
        if day not in daily:
            daily[day] = []
        daily[day].append(item)

    lines = [f"\U0001f4cd <b>{city_name}, {country}</b>\n"]

    for day, items in list(daily.items())[:5]:
        temps_min = [i["main"]["temp_min"] for i in items]
        temps_max = [i["main"]["temp_max"] for i in items]
        humidity = [i["main"]["humidity"] for i in items]
        wind = [i["wind"]["speed"] for i in items]

        t_min = round(min(temps_min))
        t_max = round(max(temps_max))
        avg_hum = round(sum(humidity) / len(humidity))
        avg_wind = round(sum(wind) / len(wind), 1)

        mid_item = items[len(items) // 2]
        main_code = mid_item["weather"][0]["id"]
        desc = mid_item["weather"][0]["description"]
        emoji = get_emoji(main_code)

        weekday = WEEKDAYS_RU[day.weekday()]
        date_str = day.strftime("%d.%m")

        lines.append(
            f"<b>{weekday} {date_str}</b>  {emoji} {desc}\n"
            f"    \U0001f321\ufe0f {t_min}\u00b0 .. {t_max}\u00b0  "
            f"\U0001f4a7 {avg_hum}%  "
            f"\U0001f32c\ufe0f {avg_wind} \u043c/\u0441"
        )

    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "\U0001f324\ufe0f <b>\u041f\u043e\u0433\u043e\u0434\u043d\u044b\u0439 \u0431\u043e\u0442</b>\n\n"
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u0440\u043e\u0434\u0430 \u2014 \u043f\u043e\u043b\u0443\u0447\u0438\u0448\u044c \u043f\u0440\u043e\u0433\u043d\u043e\u0437 \u043d\u0430 5 \u0434\u043d\u0435\u0439.\n\n"
        "\U0001f3ee \u041f\u0440\u0438\u043c\u0435\u0440\u044b: <code>\u041c\u043e\u0441\u043a\u0432\u0430</code>, <code>London</code>, <code>Paris</code>",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "\U0001f4cb <b>\u041a\u043e\u043c\u0430\u043d\u0434\u044b:</b>\n\n"
        "\U0001f3ef <b>\u041c\u043e\u0438 \u0433\u043e\u0440\u043e\u0434\u0430</b> \u2014 \u0441\u043f\u0438\u0441\u043e\u043a \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u044b\u0445\n"
        "\u2795 <b>\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434</b> \u2014 \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0432 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0435 (max 3)\n"
        "\u2796 <b>\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434</b> \u2014 \u0443\u0431\u0440\u0430\u0442\u044c \u0438\u0437 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e\n\n"
        "\u0418\u043b\u0438 \u043f\u0440\u043e\u0441\u0442\u043e \u043d\u0430\u043f\u0438\u0448\u0438 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u0440\u043e\u0434\u0430.",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("cities"))
async def cmd_cities(message: Message):
    user_id = message.from_user.id
    favorites = await get_favorites(user_id)

    if not favorites:
        await message.answer(
            "\U0001f4cd \u0423 \u0442\u0435\u0431\u044f \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u044b\u0445 \u0433\u043e\u0440\u043e\u0434\u043e\u0432.\n\n"
            "\u0421\u043e\u0445\u0440\u0430\u043d\u0438: <code>/save \u041c\u043e\u0441\u043a\u0432\u0430</code>",
            parse_mode="HTML",
        )
        return

    buttons = []
    for row in favorites:
        buttons.append(
            [InlineKeyboardButton(text=f"\U0001f324\ufe0f {row['city']}", callback_data=f"fav:{row['query']}")]
        )

    await message.answer(
        "\U0001f4cd <b>\u0418\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0435</b> \u2014 \u043d\u0430\u0436\u043c\u0438 \u043d\u0430 \u0433\u043e\u0440\u043e\u0434:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("fav:"))
async def handle_fav_callback(callback: CallbackQuery):
    query = callback.data.removeprefix("fav:")
    await callback.answer()

    try:
        data = await fetch_weather(query)
    except ValueError as e:
        if str(e) == "city_not_found":
            await callback.message.answer(
                f"\u274c \u0413\u043e\u0440\u043e\u0434 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d. \u0423\u0434\u0430\u043b\u0438 \u0435\u0433\u043e \u0438\u0437 /cities \u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u0438 \u0437\u0430\u043d\u043e\u0432\u043e."
            )
        else:
            await callback.message.answer("\u274c \u041e\u0448\u0438\u0431\u043a\u0430 API \u043f\u043e\u0433\u043e\u0434\u044b. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u043f\u043e\u0437\u0436\u0435.")
        return
    except Exception:
        await callback.message.answer("\u274c \u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u043f\u043e\u0437\u0436\u0435.")
        return

    text = format_forecast(data)
    await callback.message.answer(text, parse_mode="HTML")


@router.message(Command("save"))
async def cmd_save(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "\u274c \u0423\u043a\u0430\u0436\u0438 \u0433\u043e\u0440\u043e\u0434: /save \u041c\u043e\u0441\u043a\u0432\u0430"
        )
        return

    city_name = args[1].strip()
    city_display, query = resolve_city(city_name)
    ok, text = await add_favorite(message.from_user.id, city_display, query)
    await message.answer(text)


@router.message(Command("remove"))
async def cmd_remove(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "\u274c \u0423\u043a\u0430\u0436\u0438 \u0433\u043e\u0440\u043e\u0434: /remove \u041c\u043e\u0441\u043a\u0432\u0430"
        )
        return

    city_name = args[1].strip()
    _, query = resolve_city(city_name)
    favorites = await get_favorites(message.from_user.id)
    target_city = None
    for fav in favorites:
        if fav["query"] == query or fav["city"].lower() == city_name.lower():
            target_city = fav["city"]
            break

    if not target_city:
        target_city = city_name.title()

    ok, text = await remove_favorite(message.from_user.id, target_city)
    await message.answer(text)


@router.message(F.text == "\U0001f3ef \u041c\u043e\u0438 \u0433\u043e\u0440\u043e\u0434\u0430")
async def btn_my_cities(message: Message):
    await cmd_cities(message)


@router.message(F.text == "\u2795 \u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434")
async def btn_save_city(message: Message):
    user_state[message.from_user.id] = "save"
    await message.answer(
        "\u2795 \u041d\u0430\u043f\u0438\u0448\u0438 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u0440\u043e\u0434\u0430:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(F.text == "\u2796 \u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434")
async def btn_remove_city(message: Message):
    favorites = await get_favorites(message.from_user.id)
    if not favorites:
        await message.answer(
            "\U0001f4cd \u0423 \u0442\u0435\u0431\u044f \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u044b\u0445 \u0433\u043e\u0440\u043e\u0434\u043e\u0432.",
            reply_markup=main_keyboard(),
        )
        return
    user_state[message.from_user.id] = "remove"
    buttons = [[InlineKeyboardButton(text=f"\u274c {fav['city']}", callback_data=f"del:{fav['city']}")] for fav in favorites]
    await message.answer(
        "\u2796 \u0412\u044b\u0431\u0435\u0440\u0438 \u0433\u043e\u0440\u043e\u0434 \u0434\u043b\u044f \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u044f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("del:"))
async def handle_del_callback(callback: CallbackQuery):
    city = callback.data.removeprefix("del:")
    await callback.answer()
    user_state.pop(callback.from_user.id, None)
    ok, text = await remove_favorite(callback.from_user.id, city)
    await callback.message.answer(text, reply_markup=main_keyboard())


@router.message(F.text == "\u2139\ufe0f \u041f\u043e\u043c\u043e\u0449\u044c")
async def btn_help(message: Message):
    await cmd_help(message)


@router.message(F.text)
async def handle_city(message: Message):
    user_id = message.from_user.id
    state = user_state.pop(user_id, None)

    if state == "save":
        city_name = message.text.strip()
        city_display, query = resolve_city(city_name)
        ok, text = await add_favorite(user_id, city_display, query)
        await message.answer(text, reply_markup=main_keyboard())
        return

    if state == "remove":
        city_name = message.text.strip()
        _, query = resolve_city(city_name)
        favorites = await get_favorites(user_id)
        target_city = None
        for fav in favorites:
            if fav["query"] == query or fav["city"].lower() == city_name.lower():
                target_city = fav["city"]
                break
        if not target_city:
            target_city = city_name.title()
        ok, text = await remove_favorite(user_id, target_city)
        await message.answer(text, reply_markup=main_keyboard())
        return

    city_input = message.text.strip()
    city_query = RUSSIAN_CITIES.get(city_input.lower(), city_input)

    try:
        data = await fetch_weather(city_query)
    except ValueError as e:
        if str(e) == "city_not_found":
            await message.answer(
                f"\u274c \u0413\u043e\u0440\u043e\u0434 {city_input} \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.\n"
                "\u041f\u0440\u043e\u0432\u0435\u0440\u044c \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0438 \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u0435\u0449\u0451 \u0440\u0430\u0437."
            )
        else:
            await message.answer("\u274c \u041e\u0448\u0438\u0431\u043a\u0430 API \u043f\u043e\u0433\u043e\u0434\u044b. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u043f\u043e\u0437\u0436\u0435.")
        return
    except Exception:
        await message.answer("\u274c \u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u043f\u043e\u0437\u0436\u0435.")
        return

    text = format_forecast(data)
    await message.answer(text, parse_mode="HTML")


async def main():
    await init_db()
    dp.include_router(router)
    print("Bot is starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
