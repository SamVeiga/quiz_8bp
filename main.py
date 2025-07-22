from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime

GRUPO_ID = -1002363575666
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"
RESPONDIDAS_PATH = "respondidas.json"
respostas_pendentes = {}

# Carregar dados
try:
    perguntas = json.load(open(PERGUNTAS_PATH, encoding="utf-8"))
except:
    perguntas = []

try:
    ranking = json.load(open(RANKING_PATH, encoding="utf-8"))
except:
    ranking = {}

try:
    respondidas = json.load(open(RESPONDIDAS_PATH, encoding="utf-8"))
except:
    respondidas = {}

def salvar_ranking():
    with open(RANKING_PATH, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

def salvar_respondidas():
    with open(RESPONDIDAS_PATH, "w", encoding="utf-8") as f:
        json.dump(respondidas, f, ensure_ascii=False, indent=2)

def escolher_pergunta():
    agora = time.time()
    candidatas = [
        p for p in perguntas if str(p["id"]) not in respondidas or (agora - respondidas[str(p["id"])]) > 432000
    ]
    return random.choice(candidatas) if candidatas else None

def mandar_pergunta():
    while True:
        hora = datetime.now().hour
        if 6 <= hora <= 23:
            pergunta = escolher_pergunta()
            if pergunta:
                pid = str(time.time())
                respostas_pendentes[pid] = {"pergunta": pergunta, "respostas": {}}

                markup = telebot.types.InlineKeyboardMarkup()
                for i, opc in enumerate(pergunta["opcoes"]):
                    markup.add(telebot.types.InlineKeyboardButton(opc, callback_data=f"{pid}|{i}"))

                bot.send_message(
                    GRUPO_ID,
                    f"❓ *Pergunta:* {pergunta['pergunta']}",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

                timer = threading.Timer(900, revelar_resposta, args=[pid])  # 15 minutos
                respostas_pendentes[pid]["timer"] = timer
                respostas_pendentes[pid]["id_pergunta"] = pergunta["id"]
                timer.start()

        time.sleep(900)  # Espera 15 minutos
        # A resposta anterior será revelada antes da nova, veja abaixo

@bot.callback_query_handler(func=lambda c: "|" in c.data)
def responder_quiz(call):
    pid, opcao = call.data.split("|")
    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "❌ Pergunta expirada.")
    
    pend = respostas_pendentes[pid]
    user = call.from_user.id

    if user in pend["respostas"]:
        return bot.answer_callback_query(call.id, "⚠️ Você já respondeu.")
    
    pend["respostas"][user] = int(opcao)
    nome = call.from_user.first_name or call.from_user.username or "Alguém"
    
    bot.answer_callback_query(call.id, "✅ Resposta registrada!")
    bot.send_message(GRUPO_ID, f"✅ {nome} respondeu.")

    if len(pend["respostas"]) >= 10:
        pend["timer"].cancel()
        revelar_resposta(pid)

def revelar_resposta(pid):
    pend = respostas_pendentes.pop(pid, None)
    if not pend:
        return

    pergunta = pend["pergunta"]
    id_pergunta = pend.get("id_pergunta")
    if id_pergunta:
        respondidas[str(id_pergunta)] = time.time()
        salvar_respondidas()

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

    texto = f"✅ *Resposta correta:* {pergunta['opcoes'][pergunta['correta']]}\n\n"

    if acertadores:
        texto += "🎉 *Quem acertou:*\n" + "\n".join(f"• {nome}" for nome in acertadores) + "\n"
    else:
        texto += "😢 Ninguém acertou dessa vez.\n"

    if ranking:
        texto += "\n🏆 *Ranking atual:*\n"
        top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
        for i, (u, p) in enumerate(top, start=1):
            try:
                user = bot.get_chat(u)
                nome = user.first_name or user.username or str(u)
            except:
                nome = str(u)
            texto += f"{i}º – {nome}: {p} ponto(s)\n"

    bot.send_message(GRUPO_ID, texto, parse_mode="Markdown")

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
    threading.Thread(target=mandar_pergunta).start()
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
