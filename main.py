from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime

# === INFORMAÇÕES DO GRUPO ===
GRUPO_ID = -1002363575666  # Chat 8bp Oficial
GRUPO_LINK = "https://t.me/Chat8bpOficial"
GRUPO_NOME = "Chat 8bp Oficial"

# === INFORMAÇÃO DO DONO ===
DONO_ID = 1481389775  # Samuel 🦅
DONO_USER = "@samuel_gpm"

# === TOKENS E CONFIGURAÇÃO ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"

try:
    with open(PERGUNTAS_PATH, "r", encoding="utf-8") as f:
        perguntas = json.load(f)
except:
    perguntas = []

try:
    with open(RANKING_PATH, "r", encoding="utf-8") as f:
        ranking = json.load(f)
except:
    ranking = {}

respostas_pendentes = {}

def salvar_ranking():
    with open(RANKING_PATH, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

def mandar_pergunta():
    while True:
        hora = datetime.now().hour
        if 6 <= hora <= 23 and perguntas:
            pergunta = random.choice(perguntas)
            pergunta_id = str(time.time())
            respostas_pendentes[pergunta_id] = {
                "pergunta": pergunta,
                "respostas": {}
            }

            opcoes = pergunta["opcoes"]
            markup = telebot.types.InlineKeyboardMarkup()
            for i, opcao in enumerate(opcoes):
                btn = telebot.types.InlineKeyboardButton(
                    text=opcao,
                    callback_data=f"{pergunta_id}|{i}"
                )
                markup.add(btn)

            bot.send_message(
                GRUPO_ID,
                f"❓ *Pergunta do Quiz:*\n{pergunta['pergunta']}",
                parse_mode="Markdown",
                reply_markup=markup
            )

            threading.Timer(30, revelar_resposta, args=[pergunta_id]).start()  # 30 segundos para teste
        time.sleep(1800)  # espera 30 minutos para a próxima

def revelar_resposta(pergunta_id):
    if pergunta_id not in respostas_pendentes:
        return
    dados = respostas_pendentes.pop(pergunta_id)
    pergunta = dados["pergunta"]
    corretas = []
    texto = f"✅ *Resposta correta:* {pergunta['opcoes'][pergunta['correta']]}\n\n"

    for user_id, escolha in dados["respostas"].items():
        if escolha == pergunta["correta"]:
            corretas.append(user_id)
            ranking[user_id] = ranking.get(user_id, 0) + 1

    salvar_ranking()

    if corretas:
        texto += "🎉 *Quem acertou:*\n"
        for uid in corretas:
            texto += f"• [{uid}](tg://user?id={uid})\n"
    else:
        texto += "😢 Ninguém acertou dessa vez."

    if ranking:
        texto += "\n\n🏆 *Ranking:*\n"
        top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)[:5]
        for i, (uid, pontos) in enumerate(top, start=1):
            texto += f"{i}º - [{uid}](tg://user?id={uid}): {pontos} ponto(s)\n"

    bot.send_message(GRUPO_ID, texto, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def responder_quiz(call):
    bot.answer_callback_query(call.id, "Resposta registrada!")
    try:
        pergunta_id, opcao = call.data.split("|")
        if pergunta_id not in respostas_pendentes:
            return
        if call.from_user.id in respostas_pendentes[pergunta_id]["respostas"]:
            return
        respostas_pendentes[pergunta_id]["respostas"][call.from_user.id] = int(opcao)
    except Exception as e:
        print("Erro:", e)

@app.route(f"/{TOKEN}", methods=["POST"])
def receber():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

@app.route("/", methods=["GET"])
def configurar_webhook():
    url = f"{RENDER_URL}/{TOKEN}"
    info = bot.get_webhook_info()
    if info.url != url:
        bot.remove_webhook()
        bot.set_webhook(url=url)
    return "✅ Webhook pronto!", 200

def manter_vivo():
    while True:
        try:
            import requests
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)

if __name__ == "__main__":
    threading.Thread(target=mandar_pergunta).start()
    threading.Thread(target=manter_vivo).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
