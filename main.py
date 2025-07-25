# ✅ IMPORTAÇÕES E CONFIGURAÇÕES INICIAIS (NÃO ALTERAR) ⛔
from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime

# ⛔ CONFIGURAÇÕES DO GRUPO E TOKENS (PODE ALTERAR SOMENTE O GRUPO_ID E DONO_ID)
GRUPO_ID = -1002363575666
DONO_ID = 1481389775
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ⛔ CAMINHOS DE ARQUIVOS (NÃO ALTERAR)
PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"
respostas_pendentes = {}
perguntas_feitas = []
mensagens_anteriores = []  # Armazena mensagens para referência futura (sem exclusão agora)

# ⛔ CARREGAMENTO INICIAL DE DADOS (NÃO ALTERAR)
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

# 🔐 BLOCO DE ESCOLHA DE PERGUNTAS (NÃO ALTERAR)
def escolher_pergunta():
    agora = time.time()
    ultimos_3_dias = agora - (3 * 86400)
    recentes = [p for p in perguntas_feitas if p["tempo"] > ultimos_3_dias]
    ids_recentes = [p["id"] for p in recentes]
    candidatas = [p for p in perguntas if p["id"] not in ids_recentes]
    return random.choice(candidatas) if candidatas else None

# 🌟 ENVIO DA PRÓXIMA PERGUNTA

def mandar_pergunta():
    pergunta = escolher_pergunta()
    if not pergunta:
        return

    pid = str(time.time())
    respostas_pendentes[pid] = {"pergunta": pergunta, "respostas": {}}

    markup = telebot.types.InlineKeyboardMarkup()
    for i, opc in enumerate(pergunta["opcoes"]):
        markup.add(telebot.types.InlineKeyboardButton(opc, callback_data=f"{pid}|{i}"))

    msg = bot.send_message(GRUPO_ID, f"❓ *Pergunta:* {pergunta['pergunta']}", parse_mode="Markdown", reply_markup=markup)
    mensagens_anteriores.append(msg.message_id)

    # Botão "Novo Desafio"
    desafio = telebot.types.InlineKeyboardMarkup()
    desafio.add(telebot.types.InlineKeyboardButton("🎯 Novo Desafio", callback_data="novo_desafio"))
    desafio_msg = bot.send_message(GRUPO_ID, "Clique abaixo para pedir um novo desafio!", reply_markup=desafio)
    mensagens_anteriores.append(desafio_msg.message_id)

    perguntas_feitas.append({"id": pergunta["id"], "tempo": time.time()})
    salvar_perguntas_feitas()

# ⚖️ RANKING + BALÃO DE RESPOSTA

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
    resp += "\U0001f389 *Quem acertou:*\n" + "\n".join(f"• {nome}" for nome in acertadores) if acertadores else "😢 Ninguém acertou.\n"

    if ranking:
        resp += "\n🏆 *Ranking atual:*\n"
        top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)[:10]
        for i, (u, p) in enumerate(top, 1):
            try:
                user = bot.get_chat(u)
                nome = user.first_name or user.username or str(u)
            except:
                nome = str(u)
            resp += f"{i}º - {nome}: {p} ponto(s)\n"

    bot.send_message(GRUPO_ID, resp, parse_mode="Markdown")

# 🚀 /FORCAR SÓ DONO
@bot.message_handler(commands=["forcar"])
def forcar_pergunta(m):
    if m.from_user.id != DONO_ID:
        return bot.reply_to(m, "Sem permissão!")
    if respostas_pendentes:
        pid = next(iter(respostas_pendentes))
        revelar_resposta(pid)
        time.sleep(30)
    mandar_pergunta()

# 📊 RESPOSTA DO QUIZ
@bot.callback_query_handler(func=lambda c: "|" in c.data)
def responder_quiz(call):
    pid, opcao = call.data.split("|")
    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "Pergunta expirada.")
    pend = respostas_pendentes[pid]
    user = call.from_user.id
    if user in pend["respostas"]:
        return bot.answer_callback_query(call.id, "Já respondeu!")
    pend["respostas"][user] = int(opcao)
    bot.answer_callback_query(call.id, "✅ Resposta salva!")
    nome = call.from_user.first_name or call.from_user.username or "Alguém"
    bot.send_message(GRUPO_ID, f"✅ {nome} respondeu.")

# 🎯 BOTÃO NOVO DESAFIO
ultimo_pedido = 0
@bot.callback_query_handler(func=lambda c: c.data == "novo_desafio")
def desafio_callback(call):
    global ultimo_pedido
    agora = time.time()
    if agora - ultimo_pedido < 300:
        restante = int(300 - (agora - ultimo_pedido))
        return bot.answer_callback_query(call.id, f"Aguarde {restante}s para novo desafio.", show_alert=True)
    ultimo_pedido = agora
    if respostas_pendentes:
        pid = next(iter(respostas_pendentes))
        revelar_resposta(pid)
        time.sleep(30)
    mandar_pergunta()
    bot.answer_callback_query(call.id, "Novo desafio enviado!")

# 🚀 WEBHOOK
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

# ❌ SEM PERGUNTAS AUTOMÁTICAS AGORA

# ⏰ ZERAR RANKING MEIA-NOITE

def zerar_ranking_diario():
    while True:
        agora = datetime.now()
        if agora.hour == 3 and agora.minute == 0:
            top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
            if top:
                vencedor = top[0][0]
                try:
                    user = bot.get_chat(vencedor)
                    nome = user.first_name or user.username or str(vencedor)
                except:
                    nome = str(vencedor)
                texto = f"\U0001f389 *Vitória do Dia!* \U0001f389\n\nParabéns {nome}! Você foi o melhor do dia!\n\n"
                texto += "🎖️ *Top 3 do Dia:*\n"
                for i, (u, p) in enumerate(top[:3], 1):
                    try:
                        user = bot.get_chat(u)
                        nome_u = user.first_name or user.username or str(u)
                    except:
                        nome_u = str(u)
                    texto += f"{i}º - {nome_u}: {p} ponto(s)\n"
                bot.send_message(GRUPO_ID, texto, parse_mode="Markdown")
            ranking.clear()
            salvar_ranking()
            time.sleep(60)
        time.sleep(30)

# 🔧 INICIAR TUDO
if __name__ == "__main__":
    carregar_perguntas_feitas()
    threading.Thread(target=zerar_ranking_diario).start()
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
