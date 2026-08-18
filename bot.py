import os
import asyncio
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWM_API_KEY = os.environ["OWM_API_KEY"]
OWM_BASE = "https://api.openweathermap.org/data/2.5/forecast"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

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
        "\u041f\u0440\u0438\u043c\u0435\u0440\u044b: <code>\u041c\u043e\u0441\u043a\u0432\u0430</code>, <code>London</code>, <code>Paris</code>"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "\u041f\u0440\u043e\u0441\u0442\u043e \u043d\u0430\u043f\u0438\u0448\u0438 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u0440\u043e\u0434\u0430 \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c \u0438\u043b\u0438 \u0430\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u043e\u043c.\n"
        "\u0411\u043e\u0442 \u043f\u043e\u043a\u0430\u0436\u0435\u0442 \u043f\u043e\u0433\u043e\u0434\u0443 \u043d\u0430 5 \u0434\u043d\u0435\u0439."
    )


@router.message(F.text)
async def handle_city(message: Message):
    city_input = message.text.strip()
    city_query = RUSSIAN_CITIES.get(city_input.lower(), city_input)

    await message.answer(f"\U0001f50d \u0418\u0449\u0443 \u043f\u043e\u0433\u043e\u0434\u0443 \u0434\u043b\u044f <b>{city_input}</b>...")

    try:
        data = await fetch_weather(city_query)
    except ValueError as e:
        if str(e) == "city_not_found":
            await message.answer(
                f"\u274c \u0413\u043e\u0440\u043e\u0434 <b>{city_input}</b> \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.\n"
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
    dp.include_router(router)
    print("Bot is starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
