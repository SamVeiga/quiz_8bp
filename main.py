from flask import Flask, request
import telebot
import os
import random
import time

# =======================================
# CONFIGURAÇÕES INICIAIS
# =======================================
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise Exception("❌ Bot token não definido. Configure BOT_TOKEN no Render.")

# IDs dos donos
OWNER_IDS = {1481389775, 7889195722}  # você e Mateus

# URL base do Render (configure no seu serviço Render)
RENDER_URL = os.getenv("RENDER_URL")  # ex: "https://quiz-8bp.onrender.com"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# =======================================
# ESTADOS DO JOGO
# =======================================
current_challenge = None  # desafio atual
user_answers = {}         # respostas por usuário
private_msgs = {}         # mensagens enviadas no privado (para apagar depois)
challenge_start_time = 0  # horário que começou
CHALLENGE_DURATION = 300  # 5 minutos

# =======================================
# FUNÇÕES AUXILIARES
# =======================================
def load_questions():
    # exemplo básico
    return [
        {
            "pergunta": "Quem é o deus do trovão?",
            "opcoes": ["Zeus", "Loki", "Thor", "Odin"],
            "resposta": "Thor",
            "explicacao": "Na mitologia nórdica, Thor é o deus do trovão."
        },
        {
            "pergunta": "Qual deusa é associada à sabedoria?",
            "opcoes": ["Afrodite", "Atena", "Hera", "Deméter"],
            "resposta": "Atena",
            "explicacao": "Atena é a deusa da sabedoria, estratégia e justiça."
        }
    ]

QUESTIONS = load_questions()

def new_challenge():
    global current_challenge, user_answers, challenge_start_time
    current_challenge = random.choice(QUESTIONS)
    user_answers = {}
    challenge_start_time = time.time()
    return current_challenge

# =======================================
# HANDLERS
# =======================================
@bot.message_handler(commands=["quiz"])
def cmd_quiz(message):
    if message.chat.type != "private":
        if message.from_user.id not in OWNER_IDS:
            bot.reply_to(message, "🚫 Apenas os administradores podem iniciar o quiz com /quiz.")
            return

    challenge = new_challenge()

    markup = telebot.types.InlineKeyboardMarkup()
    for opt in challenge["opcoes"]:
        markup.add(telebot.types.InlineKeyboardButton(opt, callback_data=f"answer:{opt}"))

    if message.chat.type == "private":
        bot.send_message(message.chat.id, "⚡ Novo desafio iniciado no grupo! Vá até lá para participar.")
    else:
        bot.send_message(message.chat.id, f"📢 Novo Desafio!\n\n❓ {challenge['pergunta']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("answer:"))
def handle_answer(call):
    global user_answers

    if not current_challenge:
        bot.answer_callback_query(call.id, "❌ Nenhum desafio ativo.")
        return

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    escolha = call.data.split(":", 1)[1]

    elapsed = time.time() - challenge_start_time
    if elapsed > CHALLENGE_DURATION:
        bot.answer_callback_query(call.id, "⏰ Seu tempo expirou!")
        try:
            bot.send_message(user_id, "⏰ Seu tempo expirou! Aguarde o próximo desafio.")
        except:
            pass
        return

    if user_id in user_answers:
        bot.answer_callback_query(call.id, "❌ Você já respondeu!")
        return

    user_answers[user_id] = escolha

    # apagar pergunta anterior no privado
    if user_id in private_msgs:
        try:
            bot.delete_message(user_id, private_msgs[user_id])
        except:
            pass

    # manda confirmação no privado
    try:
        msg = bot.send_message(user_id, f"✅ Você respondeu: *{escolha}*\n\nAguarde 5 minutos para saber se acertou 👀", parse_mode="Markdown")
        private_msgs[user_id] = msg.message_id
    except:
        pass

    # notifica no grupo
    if chat_id < 0:  # grupo
        bot.send_message(chat_id, f"👤 {call.from_user.first_name} respondeu ao desafio!")

# =======================================
# FINALIZAÇÃO DO DESAFIO
# =======================================
def finalize_challenge(group_id):
    global current_challenge
    if not current_challenge:
        return

    correct = current_challenge["resposta"]
    winners = [uid for uid, ans in user_answers.items() if ans == correct]

    txt = f"🏁 Fim do desafio!\n\n❓ {current_challenge['pergunta']}\n"
    txt += f"✅ Resposta correta: *{correct}*\n"
    txt += f"📖 Explicação: {current_challenge['explicacao']}\n\n"

    if winners:
        txt += "🎉 Acertaram:\n" + "\n".join([f"• {bot.get_chat(uid).first_name}" for uid in winners])
    else:
        txt += "😢 Ninguém acertou."

    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("➡️ Novo Desafio", callback_data="novo_desafio"))

    bot.send_message(group_id, txt, parse_mode="Markdown", reply_markup=markup)
    current_challenge = None

@bot.callback_query_handler(func=lambda call: call.data == "novo_desafio")
def novo_desafio(call):
    if call.message.chat.type == "private":
        bot.answer_callback_query(call.id, "🚫 Esse botão só funciona no grupo.")
        return
    cmd_quiz(call.message)

# =======================================
# FLASK (WEBHOOK)
# =======================================
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
    return "Bot rodando com webhook ✅", 200

# =======================================
# FINALIZAÇÃO AUTOMÁTICA DO DESAFIO
# =======================================
@app.before_request
def check_challenge_timeout():
    global current_challenge
    if current_challenge:
        elapsed = time.time() - challenge_start_time
        if elapsed > CHALLENGE_DURATION:
            finalize_challenge(-1001234567890)  # substitua pelo ID do grupo onde roda
