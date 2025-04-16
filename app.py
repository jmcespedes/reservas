from flask import Flask, request
from datetime import datetime, timedelta
import pytz
import urllib.parse
import json
from pathlib import Path
from twilio.twiml.messaging_response import MessagingResponse
import logging
import re
from fuzzywuzzy import fuzz

# Configuración de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / 'data'
user_state = {}

# Asegurar que el directorio data existe
DATA_DIR.mkdir(exist_ok=True)


def get_available_slots():
    """Obtiene las 5 primeras citas disponibles para hoy"""
    try:
        tz = pytz.timezone('America/Santiago')
        today = datetime.now(tz).strftime('%Y-%m-%d')
        with open(DATA_DIR / 'citas.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        citas_hoy = [
            c for c in data['citas']
            if c['fecha'] == today and c['disponible'] == 1
        ]
        citas_hoy.sort(key=lambda x: x['hora'])
        return [
            (c['fecha'], datetime.strptime(c['hora'], '%H:%M:%S').time(), c['medico'], c['especialidad'])
            for c in citas_hoy[:5]
        ]
    except Exception as e:
        logger.error(f"Error leyendo citas: {str(e)}")
        return []


def buscar_respuesta_faq(pregunta_usuario, from_number):
    """Busca en FAQs y devuelve la mejor respuesta o un menú si hay varias opciones"""
    try:
        with open(DATA_DIR / 'faqs.json', 'r', encoding='utf-8') as f:
            faqs = json.load(f)

        pregunta_usuario = pregunta_usuario.lower().strip()
        coincidencias = []

        for faq in faqs['faqs']:
            puntaje_pregunta = fuzz.ratio(pregunta_usuario, faq['pregunta'].lower())
            keywords = [kw.strip().lower() for kw in faq.get('keywords', '').split(',')]
            puntaje_keywords = max([fuzz.ratio(pregunta_usuario, kw) for kw in keywords] + [0])
            puntaje_total = max(puntaje_keywords, puntaje_pregunta * 0.7)
            if puntaje_total > 50:
                coincidencias.append({
                    "pregunta": faq['pregunta'],
                    "respuesta": faq['respuesta'],
                    "puntaje": puntaje_total
                })

        if not coincidencias:
            return None

        coincidencias.sort(key=lambda x: -x['puntaje'])

        if len(coincidencias) > 1 and (coincidencias[0]['puntaje'] - coincidencias[1]['puntaje'] > 15):
            return coincidencias[0]['respuesta']

        # Guardar estado para que el usuario seleccione una opción
        user_state[from_number] = {
            "estado": "esperando_opcion_faq",
            "opciones": [c['respuesta'] for c in coincidencias[:3]],
            "timestamp": datetime.now()
        }

        texto = "🔍 *Encontré varias coincidencias:*\n\n"
        for i, opcion in enumerate(coincidencias[:3], 1):
            texto += f"{i}. ❓ *{opcion['pregunta']}*\n"
        texto += "\n✏️ Responde con el *número* de la opción que necesitas."
        return texto

    except Exception as e:
        logger.error(f"Error buscando FAQ: {str(e)}")
        return None


def generar_google_calendar_link(fecha, hora, medico, especialidad):
    tz = pytz.timezone('America/Santiago')
    dt_inicio = tz.localize(datetime.combine(datetime.strptime(fecha, '%Y-%m-%d').date(), hora))
    dt_fin = dt_inicio + timedelta(minutes=30)

    params = {
        'action': 'TEMPLATE',
        'text': f'Cita médica con {medico}',
        'dates': f"{dt_inicio.strftime('%Y%m%dT%H%M%S')}/{dt_fin.strftime('%Y%m%dT%H%M%S')}",
        'details': f"Especialidad: {especialidad}\nReservado vía WhatsApp Bot",
        'location': 'Hospital DIPRECA, Santiago, Chile',
        'ctz': 'America/Santiago'
    }

    return 'https://www.google.com/calendar/render?' + urllib.parse.urlencode(params)


def actualizar_disponibilidad(fecha, hora, medico):
    try:
        with open(DATA_DIR / 'citas.json', 'r+', encoding='utf-8') as f:
            data = json.load(f)
            for cita in data['citas']:
                if (cita['fecha'] == fecha and
                    cita['hora'] == hora.strftime('%H:%M:%S') and
                    cita['medico'] == medico):
                    cita['disponible'] = 0
                    break

            f.seek(0)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.truncate()
        return True
    except Exception as e:
        logger.error(f"Error actualizando disponibilidad: {str(e)}")
        return False


@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    try:
        logger.debug(f"Datos recibidos de Twilio: {request.form}")

        from_number = request.form.get('From', '').strip()
        user_msg = request.form.get('Body', '').strip()

        if not from_number or not user_msg:
            logger.error("Datos incompletos recibidos")
            return build_twiml_response("Error: solicitud incompleta")

        user_msg_clean = re.sub(r'[^0-9]', '', user_msg)
        user_msg_lower = user_msg.lower()

        # ⚡ Manejo de estado: esperando selección de FAQ
        if from_number in user_state and user_state[from_number].get("estado") == "esperando_opcion_faq":
            opciones = user_state[from_number].get("opciones", [])
            if user_msg_clean.isdigit():
                seleccion = int(user_msg_clean) - 1
                if 0 <= seleccion < len(opciones):
                    respuesta = opciones[seleccion]
                    user_state[from_number] = {"estado": "inicio"}
                    return build_twiml_response(
                        f"📝 *Respuesta:*\n\n{respuesta}\n\n¿Necesitas algo más? Escribe una nueva pregunta o *AGENDAR*."
                    )
                else:
                    return build_twiml_response(f"❌ Opción inválida. Elige un número entre 1 y {len(opciones)}.")
            else:
                return build_twiml_response("✋ Por favor, responde solo con el *número* de la opción que deseas.")

        # 🗓️ Comando global: AGENDAR
        if "agendar" in user_msg_lower:
            slots = get_available_slots()
            if not slots:
                return build_twiml_response("⏳ No hay citas disponibles hoy. Intenta más tarde.")
            respuesta = "📅 *Citas disponibles hoy:*\n\n"
            for i, (fecha, hora, medico, especialidad) in enumerate(slots, 1):
                respuesta += (
                    f"{i}. ⏰ *Hora:* {hora.strftime('%H:%M')}\n"
                    f"   👨‍⚕️ *Doctor:* Dr. {medico}\n"
                    f"   📌 *Especialidad:* {especialidad}\n\n"
                )
            respuesta += "🔢 *Responde con el número de la cita que deseas* (ej: 1, 2, 3...)."
            user_state[from_number] = {
                "estado": "esperando_seleccion_cita",
                "slots": slots,
                "timestamp": datetime.now()
            }
            return build_twiml_response(respuesta)

        # ✅ Confirmar selección de cita
        elif from_number in user_state and user_state[from_number]["estado"] == "esperando_seleccion_cita":
            if not user_msg_clean.isdigit():
                return build_twiml_response("❌ Por favor, responde *solo con el número* de la cita (ej: 1, 2, 3...).")

            seleccion = int(user_msg_clean) - 1
            slots = user_state[from_number].get("slots", [])

            if seleccion < 0 or seleccion >= len(slots):
                return build_twiml_response(f"❌ Opción inválida. Elige un número del 1 al {len(slots)}.")

            fecha, hora, medico, especialidad = slots[seleccion]

            if not actualizar_disponibilidad(fecha, hora, medico):
                return build_twiml_response("⚠️ Error al reservar. Intenta nuevamente.")

            link = generar_google_calendar_link(fecha, hora, medico, especialidad)
            user_state[from_number] = {"estado": "inicio"}

            return build_twiml_response(
                f"✅ *Cita agendada con éxito:*\n\n"
                f"📅 *Fecha:* {fecha}\n"
                f"⏰ *Hora:* {hora.strftime('%H:%M')}\n"
                f"👨‍⚕️ *Doctor:* Dr. {medico}\n"
                f"📌 *Especialidad:* {especialidad}\n\n"
                f"📲 *Agendar en calendario:*\n{link}\n\n"
                "¡Gracias por tu reserva! 😊"
            )

        # 🔍 Buscar en FAQ
        respuesta_faq = buscar_respuesta_faq(user_msg, from_number)
        if respuesta_faq:
            return build_twiml_response(respuesta_faq)

        # Si no se entendió nada
        return build_twiml_response(
            "👋 *Bienvenido al Hospital Dipreca*.\n\n"
            "📅 Para agendar una cita, escribe *AGENDAR*.\n"
            "❓ Para preguntas frecuentes, intenta con:\n"
            "  - Horarios de atención\n"
            "  - Ubicación\n"
            "  - Requisitos\n"
        )

    except Exception as e:
        logger.error(f"Error en whatsapp_reply: {str(e)}")
        return build_twiml_response("⚠️ Error interno. Por favor, intenta nuevamente.")


def build_twiml_response(message_text):
    """Genera y retorna la respuesta Twilio en formato XML"""
    response = MessagingResponse()
    response.message(message_text)
    return str(response)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
