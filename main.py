from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime, timedelta

GRUPO_ID = -1002363575666
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"
HISTORICO_PATH = "historico.json"
respostas_pendentes = {}

try:
    perguntas = json.load(open(PERGUNTAS_PATH, encoding="utf-8"))
except:
    perguntas = []

try:
    ranking = json.load(open(RANKING_PATH, encoding="utf-8"))
except:
    ranking = {}

try:
    historico = json.load(open(HISTORICO_PATH, encoding="utf-8"))
except:
    historico = {}

def salvar_ranking():
    with open(RANKING_PATH, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

def salvar_historico():
    with open(HISTORICO_PATH, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)

def filtrar_perguntas():
    agora = datetime.now()
    return [
        p for p in perguntas
        if p["id"] not in historico or
        (agora - datetime.strptime(historico[p["id"]], "%Y-%m-%d")).days > 5
    ]

def ciclo_pergunta():
    while True:
        hora = datetime.now().hour
        if 6 <= hora <= 23:
            pool = filtrar_perguntas()
            if not pool:
                time.sleep(900)
                continue

            pergunta = random.choice(pool)
            pid = str(time.time())
            respostas_pendentes[pid] = {"pergunta": pergunta, "respostas": {}}

            markup = telebot.types.InlineKeyboardMarkup()
            for i, opc in enumerate(pergunta["opcoes"]):
                markup.add(telebot.types.InlineKeyboardButton(opc, callback_data=f"{pid}|{i}"))

            bot.send_message(GRUPO_ID, f"❓ *Pergunta:* {pergunta['pergunta']}", parse_mode="Markdown", reply_markup=markup)

            historico[pergunta["id"]] = datetime.now().strftime("%Y-%m-%d")
            salvar_historico()

            # Espera 15 minutos antes de revelar a resposta
            time.sleep(900)
            revelar_resposta(pid)
        else:
            time.sleep(60)

@bot.callback_query_handler(func=lambda c: "|" in c.data)
def responder_quiz(call):
    pid, opcao = call.data.split("|")
    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "Pergunta expirada.")

    pend = respostas_pendentes[pid]
    user = call.from_user.id

    if user in pend["respostas"]:
        return bot.answer_callback_query(call.id, "Você já respondeu.")

    pend["respostas"][user] = int(opcao)
    nome = call.from_user.first_name or call.from_user.username or "Alguém"
    bot.answer_callback_query(call.id, "✅ Resposta registrada!")
    bot.send_message(GRUPO_ID, f"✅ {nome} respondeu.")

def revelar_resposta(pid):
    pend = respostas_pendentes.pop(pid, None)
    if not pend:
        return
    pergunta = pend["pergunta"]
    corretos = [u for u, o in pend["respostas"].items() if o == pergunta["correta"]]
    acertadores = []

    for u in corretos:
        ranking[u] = ranking.get(u, 0) + 1
        try:
            user = bot.get_chat(u)
            nome = user.first_name or user.username or str(u)
        except:
            nome = str(u)
        acertadores.append(nome)

    salvar_ranking()

    resp = f"✅ *Resposta correta:* {pergunta['opcoes'][pergunta['correta']]}\n\n"
    if acertadores:
        resp += "🎉 *Quem acertou:*\n" + "\n".join(f"• {nome}" for nome in acertadores) + "\n"
    else:
        resp += "😢 Ninguém acertou dessa vez.\n"

    if ranking:
        resp += "\n🏆 *Ranking atual:*\n"
        top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
        for i, (u, p) in enumerate(top, start=1):
            try:
                user = bot.get_chat(u)
                nome = user.first_name or user.username or str(u)
            except:
                nome = str(u)
            resp += f"{i}º – {nome}: {p} ponto(s)\n"

    bot.send_message(GRUPO_ID, resp, parse_mode="Markdown")

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    url = f"{RENDER_URL}/{TOKEN}"
    if bot.get_webhook_info().url != url:
        bot.remove_webhook()
        bot.set_webhook(url=url)
    return "✅", 200

def manter_vivo():
    import requests
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)

if __name__ == "__main__":
    threading.Thread(target=ciclo_pergunta).start()
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
