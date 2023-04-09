import asyncio
from telethon import TelegramClient
from telethon.tl.custom import Button
from config import *
import requests
import sqlite3
from templates import *
import requests
from flask import Flask, request
import threading
import random

games = sqlite3.connect("games.sqlite3", check_same_thread=False)
games.execute(
    """CREATE TABLE IF NOT EXISTS games (message_id INTEGER PRIMARY KEY, start_ton_price REAL, end_ton_price REAL, game_number INTEGER, players TEXT)"""
)

app = Flask(__name__)

headers = {
    "Rocket-Pay-Key": api_key,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

short_players = {}
zero_players = {}
long_players = {}

global total_short, total_zero, total_long
total_short = 0
total_zero = 0
total_long = 0

data = {
    "minPayment": 0.1,
    "numPayments": 0,
    "currency": "TONCOIN",
    "description": "Tones of Rav — раунд #%s",
    "hiddenMessage": "Вы успешно поставили в раунде #%s!",
    "callbackUrl": "https://t.me/tones_ravw",
    "payload": "%s",
    "expiredIn": bet_time,
}

global client
client = TelegramClient("bot", api_id, api_hash)


def merge(dict1, dict2, dict3):
    dict2.update(dict1)
    dict3.update(dict2)
    return dict3


def generate_transfer(tg_id, game_number, amount):
    data = {
        "tgUserId": tg_id,
        "currency": "TONCOIN",
        "amount": amount,
        "transferId": str(random.randint(1, 100000000000000000)),
        "description": "Tones of Rav — раунд #%s — победа!" % game_number,
    }
    return data


def generate_refund(tg_id, game_number, amount):
    data = {
        "tgUserId": tg_id,
        "currency": "TONCOIN",
        "amount": amount,
        "transferId": str(random.randint(1, 100000000000000000)),
        "description": "Tones of Rav — раунд #%s — автоматический возврат"
        % game_number,
    }
    return data


async def send_telegram_message(text_template, buttons=None):
    async with client:
        result = await client.send_message(channel_id, text_template, buttons=buttons)
    return result.id


global current_ton_price, game_number, short_coefficient, zero_coefficient, long_coefficient
short_coefficient = float()
zero_coefficient = float()
long_coefficient = float()
current_ton_price = 0
try:
    game_number = (
        int(
            games.execute(
                "SELECT game_number FROM games ORDER BY game_number DESC LIMIT 1"
            ).fetchone()[0]
        )
        + 1
    )
except TypeError:
    game_number = 1


async def update_telegram_message(
    message_id, text_template, include_buttons, buttons=None
):
    async with client:
        if include_buttons:
            await client.edit_message(
                channel_id, message_id, text_template, buttons=buttons
            )
        else:
            await client.edit_message(channel_id, message_id, text_template)


def results(start_ton_price, current_ton_price):
    if start_ton_price < current_ton_price:
        return "🟢"
    elif start_ton_price > current_ton_price:
        return "🔴"
    else:
        return "🟡"


def convert_result(result):
    if result == "🔴":
        return "short"
    elif result == "🟡":
        return "zero"
    else:
        return "long"


def calculate_coefficients(
    short_players, zero_players, long_players, game_comission=game_comission
):
    short_sum = 0
    for player in short_players:
        short_sum += short_players[player]
    zero_sum = 0
    for player in zero_players:
        zero_sum += zero_players[player]
    long_sum = 0
    for player in long_players:
        long_sum += long_players[player]

    try:
        short_coefficient = ((short_sum + zero_sum + long_sum) / short_sum) * (
            1 - game_comission
        )
    except ZeroDivisionError:
        short_coefficient = 0

    try:
        zero_coefficient = ((short_sum + zero_sum + long_sum) / zero_sum) * (
            1 - game_comission
        )
    except ZeroDivisionError:
        zero_coefficient = 0

    try:
        long_coefficient = ((short_sum + zero_sum + long_sum) / long_sum) * (
            1 - game_comission
        )
    except ZeroDivisionError:
        long_coefficient = 0

    return short_coefficient, zero_coefficient, long_coefficient


short_coefficient, zero_coefficient, long_coefficient = calculate_coefficients(
    short_players, zero_players, long_players
)


def sth(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)


@app.route("/", methods=["POST"])
async def webhook():
    global total_short, total_zero, total_long
    if request.method == "POST":
        amount = request.json["data"]["payment"]["paymentAmount"]
        user = request.json["data"]["payment"]["userId"]
        result = request.json["data"]["payload"]
        if result == "short":
            if user not in short_players:
                short_players[user] = amount
                total_short += amount
            else:
                short_players[user] += amount
                total_short += amount
        elif result == "zero":
            if user not in zero_players:
                zero_players[user] = amount
                total_zero += amount
            else:
                zero_players[user] += amount
                total_zero += amount
        else:
            if user not in long_players:
                long_players[user] = amount
                total_long += amount
            else:
                long_players[user] += amount
                total_long += amount
    return "ok"


async def main():
    global game_number, short_coefficient, zero_coefficient, long_coefficient
    data["description"] = data["description"] % game_number
    data["hiddenMessage"] = data["hiddenMessage"] % game_number
    data["payload"] = "short"
    short_link = requests.post(
        f"{endpoint}tg-invoices", headers=headers, json=data
    ).json()["data"]["link"]
    data["payload"] = "zero"
    zero_link = requests.post(
        f"{endpoint}tg-invoices", headers=headers, json=data
    ).json()["data"]["link"]
    data["payload"] = "long"
    long_link = requests.post(
        f"{endpoint}tg-invoices", headers=headers, json=data
    ).json()["data"]["link"]
    buttons = [
        [Button.url("🔴", short_link)],
        [Button.url("🟡", zero_link)],
        [Button.url("🟢", long_link)],
    ]

    global bet_time, waiting_time, current_ton_price
    start_ton_price = current_ton_price = float(
        requests.get(
            "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"
        ).json()["data"]["price"]
    ).__round__(3)
    game_message_id = await send_telegram_message(
        text_template=create_template.format(
            game_number,
            sth(bet_time),
            sth(waiting_time + bet_time),
            start_ton_price,
            current_ton_price,
            str("%.3f" % short_coefficient),
            total_short,
            str("%.3f" % zero_coefficient),
            total_zero,
            str("%.3f" % long_coefficient),
            total_long,
        ),
        buttons=buttons,
    )
    while bet_time > 0:
        current_ton_price = float(
            requests.get(
                "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"
            ).json()["data"]["price"]
        ).__round__(3)
        short_coefficient, zero_coefficient, long_coefficient = calculate_coefficients(
            short_players, zero_players, long_players
        )
        try:
            await update_telegram_message(
                game_message_id,
                create_template.format(
                    game_number,
                    sth(bet_time),
                    sth(bet_time + waiting_time),
                    start_ton_price,
                    current_ton_price,
                    str("%.3f" % short_coefficient),
                    total_short,
                    str("%.3f" % zero_coefficient),
                    total_zero,
                    str("%.3f" % long_coefficient),
                    total_long,
                ),
                include_buttons=True,
                buttons=buttons,
            )
        except:
            pass
        await asyncio.sleep(15)
        bet_time -= 15
    while waiting_time > 0:
        current_ton_price = float(
            requests.get(
                "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT"
            ).json()["data"]["price"]
        ).__round__(3)
        short_coefficient, zero_coefficient, long_coefficient = calculate_coefficients(
            short_players, zero_players, long_players
        )
        await update_telegram_message(
            game_message_id,
            waiting_template.format(
                game_number,
                sth(waiting_time),
                start_ton_price,
                current_ton_price,
                str("%.3f" % short_coefficient),
                total_short,
                str("%.3f" % zero_coefficient),
                total_zero,
                str("%.3f" % long_coefficient),
                total_long,
            ),
            include_buttons=False,
        )
        await asyncio.sleep(15)
        waiting_time -= 15
    result = results(start_ton_price, current_ton_price)
    await update_telegram_message(
        game_message_id,
        end_template.format(
            game_number,
            start_ton_price,
            current_ton_price,
            result,
            str("%.3f" % short_coefficient),
            total_short,
            str("%.3f" % zero_coefficient),
            total_zero,
            str("%.3f" % long_coefficient),
            total_long,
        ),
        include_buttons=False,
    )
    result = convert_result(result)

    if result == "short":
        players = short_players
    elif result == "zero":
        players = zero_players
    else:
        players = long_players
    async with client:
        if len(players) > 0:
            await client.send_message(
                channel_id,
                f"Поздравляем победителей! Количество победителей — {len(players)}",
            )
        else:
            await client.send_message(
                channel_id, no_one_won_template.format(game_number)
            )
            all_players = merge(short_players, zero_players, long_players)
            for player in all_players:
                requests.post(
                    f"{endpoint}app/transfer",
                    headers=headers,
                    json=generate_refund(
                        player, game_number, all_players[player] * 0.985
                    ),
                )

    for player in players:
        requests.post(
            f"{endpoint}app/transfer",
            headers=headers,
            json=generate_transfer(
                player, game_number, players[player] * eval(f"{result}_coefficient")
            ),
        )
    allplayers = merge(short_players, zero_players, long_players)
    games.execute(
        """
        INSERT INTO games (message_id, start_ton_price, end_ton_price, game_number, players)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            game_message_id,
            start_ton_price,
            current_ton_price,
            game_number,
            str(allplayers),
        ),
    )
    games.commit()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

main_thread = threading.Thread(target=loop.run_until_complete, args=(main(),))
flask_thread = threading.Thread(target=app.run, kwargs={"host": "0.0.0.0"})

main_thread.start()
flask_thread.start()

main_thread.join()
flask_thread.join()
