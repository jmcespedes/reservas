from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json
from pathlib import Path
import logging
from fuzzywuzzy import fuzz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / 'data'
user_state = {}  # Aquí guardamos el estado de cada número

def cargar_faqs():
    try:
        with open(DATA_DIR / 'faqs.json', 'r', encoding='utf-8') as f:
            return json.load(f)['faqs']
    except Exception as e:
        logger.error(f"Error cargando FAQs: {str(e)}")
        return []

FAQS = cargar_faqs()

def buscar_respuesta_faq(pregunta_usuario):
    pregunta_usuario = pregunta_usuario.lower().strip()
    mejor_respuesta = None
    mejor_puntaje = 0

    for faq in FAQS:
        puntaje_pregunta = fuzz.ratio(pregunta_usuario, faq['pregunta'].lower())
        keywords = [kw.strip().lower() for kw in faq.get('keywords', '').split(',')]
        puntaje_keywords = max([fuzz.ratio(pregunta_usuario, kw) for kw in keywords] + [0])
        puntaje_total = max(puntaje_keywords, puntaje_pregunta * 0.8)

        if puntaje_total > 50 and puntaje_total > mejor_puntaje:
            mejor_puntaje = puntaje_total
            mejor_respuesta = faq['respuesta']

    return mejor_respuesta

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        user_msg = request.form.get('Body', '').strip()
        user_number = request.form.get('From')  # Número del usuario
        user_msg_lower = user_msg.lower()

        # Estado actual del usuario
        estado = user_state.get(user_number, {}).get('estado')

        # 🌀 Manejo del flujo de agendamiento
        if estado == 'pidiendo_nombre':
            user_state[user_number]['nombre'] = user_msg
            user_state[user_number]['estado'] = 'pidiendo_dia'
            return build_twiml_response("📅 ¿Qué día deseas agendar la cita?")

        elif estado == 'pidiendo_dia':
            user_state[user_number]['dia'] = user_msg
            user_state[user_number]['estado'] = 'pidiendo_hora'
            return build_twiml_response("🕒 ¿A qué hora deseas tu cita?")

        elif estado == 'pidiendo_hora':
            user_state[user_number]['hora'] = user_msg
            datos = user_state[user_number]
            user_state.pop(user_number, None)  # Limpiar estado
            return build_twiml_response(
                f"✅ Cita agendada:\n"
                f"👤 Nombre: {datos['nombre']}\n"
                f"📅 Día: {datos['dia']}\n"
                f"🕒 Hora: {datos['hora']}\n\n"
                "¡Gracias por agendar con nosotros!"
            )

        # 🚀 Inicio del flujo de agendamiento
        if "agendar" in user_msg_lower:
            user_state[user_number] = {'estado': 'pidiendo_nombre'}
            return build_twiml_response("👤 ¿Cuál es tu nombre para la cita?")

        # 📚 Si no está en un flujo, intentamos responder con FAQ
        respuesta_faq = buscar_respuesta_faq(user_msg)
        if respuesta_faq:
            return build_twiml_response(respuesta_faq)

        # 🧭 Mensaje por defecto
        return build_twiml_response(
            "¡Hola! 👋 ¿En qué puedo ayudarte?\n\n"
            "Puedes preguntarme sobre:\n"
            "⏰ Horarios de atención\n"
            "📍 Ubicación\n"
            "📄 Requisitos para citas\n"
            "⚠️ Contacto de emergencia\n\n"
            "O escribe *AGENDAR* para información sobre citas. 📅"
        )

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return build_twiml_response("⚠️ Error interno. Por favor, intenta nuevamente.")

def build_twiml_response(message_text):
    response = MessagingResponse()
    response.message(message_text)
    return str(response), 200, {'Content-Type': 'text/xml'}

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)