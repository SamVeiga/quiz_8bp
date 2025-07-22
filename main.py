from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime

GRUPO_ID = -1002363575666
DONO_ID = 1481389775
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"
respostas_pendentes = {}
perguntas_feitas = []

try:
    perguntas = json.load(open(PERGUNTAS_PATH, encoding="utf-8"))
except:
    perguntas = []
try:
    ranking = json.load(open(RANKING_PATH, encoding="utf-8"))
except:
    ranking = {}

def salvar_ranking():
    with open(RANKING_PATH, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

def salvar_perguntas_feitas():
    with open("perguntas_feitas.json", "w", encoding="utf-8") as f:
        json.dump(perguntas_feitas, f)

def carregar_perguntas_feitas():
    global perguntas_feitas
    try:
        with open("perguntas_feitas.json", "r", encoding="utf-8") as f:
            perguntas_feitas = json.load(f)
    except:
        perguntas_feitas = []

def escolher_pergunta():
    agora = time.time()
    ultimos_5_dias = agora - (5 * 86400)
    recentes = [p for p in perguntas_feitas if p["tempo"] > ultimos_5_dias]
    ids_recentes = [p["id"] for p in recentes]

    candidatas = [p for p in perguntas if p["id"] not in ids_recentes]
    if not candidatas:
        return None
    return random.choice(candidatas)

def mandar_pergunta():
    hora = datetime.now().hour
    if not (6 <= hora <= 23):
        return

    pergunta = escolher_pergunta()
    if not pergunta:
        return

    pid = str(time.time())
    respostas_pendentes[pid] = {"pergunta": pergunta, "respostas": {}}

    markup = telebot.types.InlineKeyboardMarkup()
    for i, opc in enumerate(pergunta["opcoes"]):
        markup.add(telebot.types.InlineKeyboardButton(opc, callback_data=f"{pid}|{i}"))

    bot.send_message(GRUPO_ID, f"❓ *Pergunta:* {pergunta['pergunta']}", parse_mode="Markdown", reply_markup=markup)

    perguntas_feitas.append({"id": pergunta["id"], "tempo": time.time()})
    salvar_perguntas_feitas()

    timer = threading.Timer(900, revelar_resposta, args=[pid])
    respostas_pendentes[pid]["timer"] = timer
    timer.start()

@bot.message_handler(commands=["forcar"])
def forcar_pergunta(m):
    if m.from_user.id == DONO_ID:
        bot.send_message(GRUPO_ID, "🚨 Enviando nova pergunta agora!")
        mandar_pergunta()
    else:
        bot.reply_to(m, "Você não tem permissão pra isso.")

@bot.callback_query_handler(func=lambda c: "|" in c.data)
def responder_quiz(call):
    pid, opcao = call.data.split("|")
    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "Pergunta expirada.")

    pend = respostas_pendentes[pid]
    user = call.from_user.id
    nome = call.from_user.first_name or call.from_user.username or "Alguém"

    if user in pend["respostas"]:
        return bot.answer_callback_query(call.id, "Você já respondeu.")

    pend["respostas"][user] = int(opcao)
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

def ciclo_perguntas():
    while True:
        agora = datetime.now()
        if 6 <= agora.hour < 24:
            mandar_pergunta()
        time.sleep(900)  # 15 minutos

if __name__ == "__main__":
    carregar_perguntas_feitas()
    threading.Thread(target=ciclo_perguntas).start()
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
