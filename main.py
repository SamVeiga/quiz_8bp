# 📌 CONFIGURAÇÕES E IMPORTAÇÕES
from flask import Flask, request
import telebot
import os
import random
import json
import threading
import time
from datetime import datetime

# 📍 CONSTANTES DO BOT
GRUPO_ID = -1002363575666
DONO_ID = 1481389775
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 📚 CAMINHOS DOS ARQUIVOS
PERGUNTAS_PATH = "perguntas.json"
RANKING_PATH = "ranking.json"
FEITAS_PATH = "perguntas_feitas.json"

# 🔒 VARIÁVEIS DE CONTROLE
respostas_pendentes = {}
perguntas_feitas = []
ranking = {}
ultimo_pedido_membro = 0

# 🔐 RANKING: Carrega e salva pontuação
def carregar_ranking():
    global ranking
    try:
        with open(RANKING_PATH, "r", encoding="utf-8") as f:
            ranking = json.load(f)
    except:
        ranking = {}

def salvar_ranking():
    with open(RANKING_PATH, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

# 🔄 PERGUNTAS FEITAS
def carregar_perguntas_feitas():
    global perguntas_feitas
    try:
        with open(FEITAS_PATH, "r", encoding="utf-8") as f:
            perguntas_feitas = json.load(f)
    except:
        perguntas_feitas = []

def salvar_perguntas_feitas():
    with open(FEITAS_PATH, "w", encoding="utf-8") as f:
        json.dump(perguntas_feitas, f)

# 🧠 ESCOLHER PERGUNTA NOVA
def escolher_pergunta():
    agora = time.time()
    ultimos_5_dias = agora - (5 * 86400)
    ids_recentes = [p["id"] for p in perguntas_feitas if p["tempo"] > ultimos_5_dias]

    candidatas = [p for p in perguntas if p["id"] not in ids_recentes]
    if not candidatas:
        return None
    return random.choice(candidatas)

# ❓ MANDAR PERGUNTA NO GRUPO
def mandar_pergunta():
    global ultima_msg_id
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

    msg = bot.send_message(GRUPO_ID, f"❓ *Pergunta:* {pergunta['pergunta']}", parse_mode="Markdown", reply_markup=markup)

    # Excluir a penúltima pergunta (não balão)
    try:
        if hasattr(mandar_pergunta, "ultima_pergunta_id"):
            bot.delete_message(GRUPO_ID, mandar_pergunta.ultima_pergunta_id)
        mandar_pergunta.ultima_pergunta_id = msg.message_id
    except:
        pass

    perguntas_feitas.append({"id": pergunta["id"], "tempo": time.time()})
    salvar_perguntas_feitas()

    timer = threading.Timer(30, revelar_resposta, args=[pid])
    respostas_pendentes[pid]["timer"] = timer
    timer.start()

# 🚨 COMANDO /forcar (sem restrição de tempo)
@bot.message_handler(commands=["forcar"])
def forcar_pergunta(m):
    if m.from_user.id != DONO_ID:
        return bot.reply_to(m, "Você não tem permissão pra isso.")

    if respostas_pendentes:
        pid = next(iter(respostas_pendentes))
        revelar_resposta(pid)
        time.sleep(2)

    mandar_pergunta()

# 🎯 BOTÃO DE MEMBRO: /desafio (apenas 1 a cada 10 min)
@bot.message_handler(commands=["desafio"])
def membro_pedir_pergunta(m):
    global ultimo_pedido_membro
    if m.from_user.id == DONO_ID:
        return

    agora = time.time()
    if agora - ultimo_pedido_membro < 600:
        return bot.reply_to(m, "⏳ Aguarde um pouco para pedir outra pergunta...")

    if respostas_pendentes:
        pid = next(iter(respostas_pendentes))
        revelar_resposta(pid)
        time.sleep(2)

    bot.send_message(GRUPO_ID, "🎯 *Novo desafio solicitado!*")
    ultimo_pedido_membro = agora
    mandar_pergunta()

# ✅ RESPOSTAS DOS USUÁRIOS
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

# 🎉 BALÃO DE RESPOSTA
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

    texto = f"✅ *Resposta correta:* {pergunta['opcoes'][pergunta['correta']]}\n\n"
    if acertadores:
        texto += "🎉 *Quem acertou:*\n" + "\n".join(f"• {nome}" for nome in acertadores) + "\n"
    else:
        texto += "😢 Ninguém acertou dessa vez.\n"

    if ranking:
        texto += "\n🏆 *Ranking atual:*\n"
        top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
        for i, (u, p) in enumerate(top[:10], start=1):
            try:
                user = bot.get_chat(u)
                nome = user.first_name or user.username or str(u)
            except:
                nome = str(u)
            texto += f"{i}º – {nome}: {p} ponto(s)\n"

    bot.send_message(GRUPO_ID, texto, parse_mode="Markdown")

# 🏁 ZERAR RANK DIARIAMENTE À MEIA-NOITE
def resetar_ranking_diariamente():
    while True:
        agora = datetime.now()
        if agora.hour == 0 and agora.minute == 0:
            top = sorted(ranking.items(), key=lambda x: x[1], reverse=True)[:3]
            if top:
                vencedor_msg = "🏆 *Vitorioso do dia!*\n\n"
                emojis = "🎉👏🥇🥈🥉"

                for i, (u, p) in enumerate(top, 1):
                    try:
                        user = bot.get_chat(u)
                        nome = user.first_name or user.username or str(u)
                    except:
                        nome = str(u)
                    if i == 1:
                        vencedor_msg += f"🥇 *{nome}* foi o grande destaque do dia com *{p}* ponto(s)! {emojis}\n\n"
                    else:
                        vencedor_msg += f"{i}º – {nome}: {p} ponto(s)\n"

                bot.send_message(GRUPO_ID, vencedor_msg, parse_mode="Markdown")

            ranking.clear()
            salvar_ranking()
            time.sleep(60)
        time.sleep(30)

# 🌐 FLASK ROUTES
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

# 🔁 CICLO AUTOMÁTICO DE PERGUNTAS
def ciclo_automatico():
    while True:
        hora = datetime.now().hour
        if 6 <= hora <= 23:
            if respostas_pendentes:
                pid = next(iter(respostas_pendentes))
                revelar_resposta(pid)
                time.sleep(2)
            mandar_pergunta()
        time.sleep(3600)  # a cada 1 hora

# 🔋 MANTER VIVO (render)
def manter_vivo():
    import requests
    while True:
        try:
            requests.get(RENDER_URL)
        except:
            pass
        time.sleep(600)

# 🚀 INICIAR SERVIDOR
if __name__ == "__main__":
    try:
        perguntas = json.load(open(PERGUNTAS_PATH, encoding="utf-8"))
    except:
        perguntas = []

    carregar_perguntas_feitas()
    carregar_ranking()

    threading.Thread(target=ciclo_automatico).start()
    threading.Thread(target=manter_vivo).start()
    threading.Thread(target=resetar_ranking_diariamente).start()

    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
