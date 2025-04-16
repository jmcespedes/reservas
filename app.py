from flask import Flask, request, make_response
from twilio.twiml.messaging_response import MessagingResponse
import json
from pathlib import Path
import logging
from fuzzywuzzy import fuzz
import re


# Configuración básica
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / 'data'
user_state = {}

# Cargar FAQs al inicio (para mayor eficiencia)
def cargar_faqs():
    try:
        with open(DATA_DIR / 'faqs.json', 'r', encoding='utf-8') as f:
            return json.load(f)['faqs']
    except Exception as e:
        logger.error(f"Error cargando FAQs: {str(e)}")
        return []

FAQS = cargar_faqs()

# Buscar la mejor respuesta en FAQs
def buscar_respuesta_faq(pregunta_usuario):
    pregunta_usuario = pregunta_usuario.lower().strip()
    mejor_respuesta = None
    mejor_puntaje = 0

    for faq in FAQS:
        # Puntaje por pregunta exacta
        puntaje_pregunta = fuzz.ratio(pregunta_usuario, faq['pregunta'].lower())
        
        # Puntaje por keywords (usamos el máximo)
        keywords = [kw.strip().lower() for kw in faq.get('keywords', '').split(',')]
        puntaje_keywords = max([fuzz.ratio(pregunta_usuario, kw) for kw in keywords] + [0])
        
        # Puntaje total (priorizamos keywords)
        puntaje_total = max(puntaje_keywords, puntaje_pregunta * 0.8)  # Keywords valen más
        
        if puntaje_total > 50 and puntaje_total > mejor_puntaje:  # Umbral bajo
            mejor_puntaje = puntaje_total
            mejor_respuesta = faq['respuesta']

    return mejor_respuesta

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        user_msg = request.form.get('Body', '').strip()
        user_msg_lower = user_msg.lower()

        # 1. Priorizar FAQs
        respuesta_faq = buscar_respuesta_faq(user_msg)
        if respuesta_faq:
            return build_twiml_response(respuesta_faq)

        # 2. Opción secundaria: Agendamiento
        if "agendar" in user_msg_lower:
            return build_twiml_response(
                "📅 Para agendar una cita, por favor contáctenos directamente al:\n"
                "📞 +56 9 1234 5678\n"
                "⏳ Horario de atención: Lunes a Viernes, 8:00 - 18:00"
            )

        # 3. Respuesta por defecto
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

