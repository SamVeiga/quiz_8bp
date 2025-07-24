from flask import Flask, request
import telebot
import os
import json
import time
import random
import threading
from datetime import datetime, timedelta

# CONFIG
GRUPO_ID = -1002363575666
DONO_ID = 1481389775
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# CAMINHOS
PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"
respostas_pendentes = {}
perguntas_feitas = []

# LOAD
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
    visto = {p["id"]: p for p in perguntas_feitas}
    with open("perguntas_feitas.json", "w", encoding="utf-8") as f:
        json.dump(list(visto.values()), f)

def carregar_perguntas_feitas():
    global perguntas_feitas
    try:
        with open("perguntas_feitas.json", "r", encoding="utf-8") as f:
            perguntas_feitas = json.load(f)
    except:
        perguntas_feitas = []

def escolher_pergunta():
    agora = time.time()
    ultimos_3_dias = agora - (3 * 86400)
    recentes = [p for p in perguntas_feitas if p["tempo"] > ultimos_3_dias]
    ids_recentes = [p["id"] for p in recentes]
    candidatas = [p for p in perguntas if p["id"] not in ids_recentes]
    return random.choice(candidatas) if candidatas else None

def mandar_pergunta():
    pergunta = escolher_pergunta()
    if not pergunta:
        return

    pid = str(time.time())
    respostas_pendentes[pid] = {"pergunta": pergunta, "respostas": {}}

    markup = telebot.types.InlineKeyboardMarkup()
    for i, opcao in enumerate(pergunta["opcoes"]):
        markup.add(telebot.types.InlineKeyboardButton(opcao, callback_data=f"{pid}|{i}"))

    bot.send_message(GRUPO_ID, f"❓ *Pergunta:* {pergunta['pergunta']}", parse_mode="Markdown", reply_markup=markup)

    bot.send_message(
        GRUPO_ID,
        "🎯 Clique abaixo para pedir um novo desafio!",
        reply_markup=telebot.types.InlineKeyboardMarkup().add(
            telebot.types.InlineKeyboardButton("Novo Desafio", callback_data="novo_desafio")
        )
    )

    perguntas_feitas.append({"id": pergunta["id"], "tempo": time.time()})
    salvar_perguntas_feitas()

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
            nome = bot.get_chat(u).first_name
        except:
            nome = str(u)
        acertadores.append(nome)

    salvar_ranking()

    texto = f"✅ *Resposta correta:* {pergunta['opcoes'][pergunta['correta']]}\n\n"
    if acertadores:
        texto += "🎉 *Quem acertou:*\n" + "\n".join(f"• {n}" for n in acertadores)
    else:
        texto += "😢 Ninguém acertou.\n"

    if ranking:
        texto += "\n\n🏆 *Ranking atual:*\n"
        top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)[:10]
        for i, (u, p) in enumerate(top, 1):
            try:
                nome = bot.get_chat(u).first_name
            except:
                nome = str(u)
            texto += f"{i}º - {nome}: {p} ponto(s)\n"

    bot.send_message(GRUPO_ID, texto, parse_mode="Markdown")

# COMANDO /FORCAR
@bot.message_handler(commands=["forcar"])
def cmd_forcar(msg):
    if msg.from_user.id != DONO_ID:
        return bot.reply_to(msg, "Sem permissão.")
    if respostas_pendentes:
        pid = next(iter(respostas_pendentes))
        revelar_resposta(pid)
        time.sleep(30)
    mandar_pergunta()

# BOTÕES
@bot.callback_query_handler(func=lambda c: "|" in c.data)
def responder(call):
    pid, opcao = call.data.split("|")
    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "Expirada.")
    pend = respostas_pendentes[pid]
    if call.from_user.id in pend["respostas"]:
        return bot.answer_callback_query(call.id, "Já respondeu.")
    pend["respostas"][call.from_user.id] = int(opcao)
    nome = call.from_user.first_name or call.from_user.username or "Alguém"
    bot.send_message(GRUPO_ID, f"✅ {nome} respondeu.")
    bot.answer_callback_query(call.id, "Salvo!")

# NOVO DESAFIO
ultimo_pedido = 0
@bot.callback_query_handler(func=lambda c: c.data == "novo_desafio")
def novo_desafio(call):
    global ultimo_pedido
    agora = time.time()
    if agora - ultimo_pedido < 300:
        restante = int(300 - (agora - ultimo_pedido))
        return bot.answer_callback_query(call.id, f"Espere {restante}s", show_alert=True)
    ultimo_pedido = agora
    if respostas_pendentes:
        pid = next(iter(respostas_pendentes))
        revelar_resposta(pid)
        time.sleep(30)
    mandar_pergunta()
    bot.answer_callback_query(call.id, "Enviado!")

# RANKING DIÁRIO
ultimo_dia = None
def zerar_ranking_diario():
    global ultimo_dia
    while True:
        agora = datetime.utcnow() - timedelta(hours=3)
        hoje = agora.date()
        if agora.hour == 0 and agora.minute == 0 and ultimo_dia != hoje:
            top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
            if top:
                vencedor = top[0][0]
                try:
                    nome = bot.get_chat(vencedor).first_name
                except:
                    nome = str(vencedor)
                texto = f"🎉 *Vitória do Dia!* 🎉\n\nParabéns {nome}! Você foi o melhor do dia!\n\n"
                texto += "🥇 *Top 3:*\n"
                for i, (u, p) in enumerate(top[:3], 1):
                    try:
                        nome = bot.get_chat(u).first_name
                    except:
                        nome = str(u)
                    texto += f"{i}º - {nome}: {p} ponto(s)\n"
                bot.send_message(GRUPO_ID, texto, parse_mode="Markdown")

            desde_ontem = time.time() - 86400
            feitas = [p for p in perguntas_feitas if p["tempo"] > desde_ontem]
            ids = {p["id"] for p in feitas}
            repetidas = len(feitas) - len(ids)

            relatorio = (
                "📊 *Relatório Diário do Quiz* 📊\n\n"
                f"📝 Perguntas feitas hoje: {len(feitas)}\n"
                f"🔁 Repetidas nos últimos 3 dias: {repetidas}\n"
                f"🆕 Novas perguntas hoje: {len(ids)}\n\n"
                "🕛 Relatório gerado automaticamente à meia-noite."
            )
            bot.send_message(GRUPO_ID, relatorio, parse_mode="Markdown")

            ranking.clear()
            salvar_ranking()
            ultimo_dia = hoje
        time.sleep(30)

# WEBHOOK
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

# START
if __name__ == "__main__":
    carregar_perguntas_feitas()
    threading.Thread(target=zerar_ranking_diario).start()
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
