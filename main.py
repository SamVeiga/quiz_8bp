# ✅ IMPORTAÇÕES E CONFIGURAÇÕES INICIAIS (NÃO ALTERAR) ⛔
from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime

# ⛔ CONFIGURAÇÕES DO GRUPO E TOKENS
GRUPO_ID = -1002363575666
DONO_ID = 1481389775
TOKEN = os.getenv("TELEGRAM_TOKEN")
AUTORIZADOS = {DONO_ID, 7889195722}  # dono + Mateus
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ⛔ CAMINHOS DE ARQUIVOS
PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"
respostas_pendentes = {}
perguntas_feitas = []
mensagens_anteriores = []
mensagens_respostas = []

# Variável para controlar apenas um desafio ativo por vez
desafio_ativo = None

# Para apagar mensagens privadas por usuário
mensagens_privadas = {}

# ⛔ CARREGAMENTO INICIAL
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

# 🔐 Escolha de perguntas
def escolher_pergunta():
    agora = time.time()
    ultimos_3_dias = agora - (3 * 86400)
    recentes = [p for p in perguntas_feitas if p["tempo"] > ultimos_3_dias]
    ids_recentes = [p["id"] for p in recentes]
    candidatas = [p for p in perguntas if p["id"] not in ids_recentes]
    return random.choice(candidatas) if candidatas else None

# 🌟 Enviar botão de desafio no grupo
def mandar_desafio_grupo():
    global desafio_ativo
    if desafio_ativo is not None:
        return

    desafio = telebot.types.InlineKeyboardMarkup()
    desafio.add(telebot.types.InlineKeyboardButton("🎯 Novo Desafio", callback_data="novo_desafio"))
    msg = bot.send_message(GRUPO_ID, "👉 Clique abaixo para pedir um novo Desafio. A pergunta será enviada no PRIVADO de cada um que clicar!", reply_markup=desafio)
    mensagens_anteriores.append(msg.message_id)

    while len(mensagens_anteriores) > 3:
        msg_id = mensagens_anteriores.pop(0)
        try:
            bot.delete_message(GRUPO_ID, msg_id)
        except:
            pass

# ⚖️ Revelar resposta no grupo
def revelar_resposta(pid):
    global desafio_ativo
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

    resp = f"❓ *Pergunta:* {pergunta['pergunta']}\n\n"
    resp += f"✅ *Resposta correta:* {pergunta['opcoes'][pergunta['correta']]}\n\n"

    if "explicacao" in pergunta and pergunta["explicacao"].strip():
        resp += f"💡 *Explicação:* {pergunta['explicacao']}\n\n"

    resp += "🎉 *Quem acertou:*\n" + "\n".join(f"• {nome}" for nome in acertadores) if acertadores else "😢 Ninguém acertou.\n"

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

    msg = bot.send_message(GRUPO_ID, resp, parse_mode="Markdown")
    mensagens_anteriores.append(msg.message_id)

    desafio_ativo = None
    mandar_desafio_grupo()

# 🎮 Comando manual /quiz
@bot.message_handler(commands=["quiz"])
def comando_quiz(message):
    if message.from_user.id in AUTORIZADOS:
        mandar_desafio_grupo()
    else:
        bot.reply_to(message, "🚫 Você não tem permissão para iniciar desafios.")

# 🎯 Botão "Novo Desafio" → abre privado
@bot.callback_query_handler(func=lambda c: c.data == "novo_desafio")
def desafio_callback(call):
    global desafio_ativo
    agora = time.time()

    if desafio_ativo is not None:
        pend = respostas_pendentes.get(desafio_ativo)
        if pend:
            restante = int(pend['revelar_em'] - agora)
            if restante > 0:
                minutos = restante // 60
                segundos = restante % 60
                return bot.answer_callback_query(
                    call.id,
                    f"⏳ Aguarde {minutos}m {segundos}s para a próxima pergunta.",
                    show_alert=True
                )

    bot.answer_callback_query(call.id)

    pergunta = escolher_pergunta()
    if not pergunta:
        return bot.send_message(call.from_user.id, "❌ Não há perguntas disponíveis.")

    pid = str(time.time())
    respostas_pendentes[pid] = {
        "pergunta": pergunta,
        "respostas": {},
        "limites": {},
        "revelar_em": time.time() + 300
    }
    desafio_ativo = pid

    perguntas_feitas.append({"id": pergunta["id"], "tempo": time.time()})
    salvar_perguntas_feitas()

    def revelar():
        time.sleep(300)
        revelar_resposta(pid)

    threading.Thread(target=revelar).start()

    bot.send_message(
        call.from_user.id,
        "🎯 Clique abaixo para receber sua nova pergunta:",
        reply_markup=telebot.types.InlineKeyboardMarkup().add(
            telebot.types.InlineKeyboardButton("👉 Nova Pergunta", callback_data=f"pergunta_privada|{pid}")
        ),
    )

# 🚀 Pergunta no privado
@bot.callback_query_handler(func=lambda c: c.data.startswith("pergunta_privada|"))
def mandar_pergunta_privada(call):
    global mensagens_privadas
    user_id = call.from_user.id
    _, pid = call.data.split("|")

    if pid not in respostas_pendentes:
        return bot.send_message(user_id, "❌ Esse desafio já expirou.")

    pend = respostas_pendentes[pid]
    pergunta = pend["pergunta"]

    if user_id in mensagens_privadas:
        for msg_id in mensagens_privadas[user_id]:
            try:
                bot.delete_message(user_id, msg_id)
            except:
                pass
    mensagens_privadas[user_id] = []

    markup = telebot.types.InlineKeyboardMarkup()
    for i, opc in enumerate(pergunta["opcoes"]):
        markup.add(telebot.types.InlineKeyboardButton(opc, callback_data=f"{pid}|{i}"))

    msg = bot.send_message(
        user_id,
        f"⏳ Você tem *10 segundos* para responder:\n\n❓ {pergunta['pergunta']}",
        parse_mode="Markdown",
        reply_markup=markup,
    )
    mensagens_privadas[user_id].append(msg.message_id)

    pend["limites"][user_id] = time.time() + 10

    def timeout():
        time.sleep(10)
        if user_id not in pend["respostas"]:
            nome = call.from_user.first_name or call.from_user.username or "Alguém"
            bot.send_message(user_id, "⏰ Seu tempo expirou! Você não pode mais responder.")
            bot.send_message(GRUPO_ID, f"⏰ {nome} perdeu a vez. Aguarde resultado final.")

    threading.Thread(target=timeout).start()

# 📊 Resposta do quiz (somente no privado)
@bot.callback_query_handler(func=lambda c: "|" in c.data and not c.data.startswith("pergunta_privada|"))
def responder_privado(call):
    pid, opcao = call.data.split("|")
    if pid not in respostas_pendentes:
        return bot.answer_callback_query(call.id, "Pergunta expirada.")

    pend = respostas_pendentes[pid]
    user_id = call.from_user.id

    if user_id in pend["respostas"]:
        return bot.answer_callback_query(call.id, "Você já respondeu!")

    limite = pend["limites"].get(user_id)
    if not limite or time.time() > limite:
        return bot.answer_callback_query(call.id, "⏰ Seu tempo expirou!")

    pend["respostas"][user_id] = int(opcao)
    bot.answer_callback_query(call.id, "✅ Resposta registrada!")

    pergunta = pend["pergunta"]
    resposta_escolhida = pergunta["opcoes"][int(opcao)]
    bot.send_message(
        user_id,
        f"📩 Você respondeu: *{resposta_escolhida}*\n\n⏳ Aguarde 5 minutos para saber se acertou 👀",
        parse_mode="Markdown"
    )

    nome = call.from_user.first_name or call.from_user.username or "Alguém"
    msg = bot.send_message(GRUPO_ID, f"✅ {nome} respondeu. Aguarde resultado final.")
    mensagens_respostas.append(msg.message_id)

    if "lembrete_enviado" not in pend:
        bot.send_message(GRUPO_ID, "⏳ Resultado sai em 5 minutos...")
        pend["lembrete_enviado"] = True

    while len(mensagens_respostas) > 10:
        msg_id = mensagens_respostas.pop(0)
        try:
            bot.delete_message(GRUPO_ID, msg_id)
        except:
            pass

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

# ⏰ Zerar ranking diário
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
                texto = f"🎉 *Vitória do Dia!*\n\nParabéns {nome}! Você foi o melhor do dia!\n\n"
                texto += "🥇 *Top 3 do Dia:*\n"
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

# 🔧 Iniciar tudo
if __name__ == "__main__":
    carregar_perguntas_feitas()
    mandar_desafio_grupo()
    threading.Thread(target=zerar_ranking_diario).start()
    threading.Thread(target=manter_vivo).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
