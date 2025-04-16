from flask import Flask, request, make_response
from datetime import datetime, timedelta
import pytz
import urllib.parse
import json
from pathlib import Path
from twilio.twiml.messaging_response import MessagingResponse
import logging
import re

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
            for c in citas_hoy[:5]  # Mostrar hasta 5 opciones
        ]
    except Exception as e:
        logger.error(f"Error leyendo citas: {str(e)}")
        return []

def generar_google_calendar_link(fecha, hora, medico, especialidad):
    """Genera link para agregar al calendario"""
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
    """Marca una cita como no disponible"""
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

        # Limpieza del mensaje: eliminar espacios y caracteres no numéricos
        user_msg_clean = re.sub(r'[^0-9]', '', user_msg)  # Solo números
        user_msg_lower = user_msg.lower()

        # Comando global: AGENDAR o MENÚ
        if "agendar" in user_msg_lower or "menú" in user_msg_lower:
            slots = get_available_slots()
            if not slots:
                return build_twiml_response(
                    "⏳ No hay citas disponibles hoy. Intenta mañana o escribe 'AGENDAR' más tarde."
                )
            
            # Mostrar opciones numeradas (1, 2, 3...)
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

        # Si el usuario ya está en modo selección de cita
        elif from_number in user_state and user_state[from_number]["estado"] == "esperando_seleccion_cita":
            if not user_msg_clean.isdigit():
                return build_twiml_response("❌ Por favor, responde *solo con el número* de la cita (ej: 1, 2, 3...).")
            
            seleccion = int(user_msg_clean) - 1  # Convertir a índice
            slots = user_state[from_number].get("slots", [])
            
            if seleccion < 0 or seleccion >= len(slots):
                return build_twiml_response(f"❌ Opción inválida. Elige un número del 1 al {len(slots)}.")
            
            fecha, hora, medico, especialidad = slots[seleccion]
            
            # Reservar la cita
            if not actualizar_disponibilidad(fecha, hora, medico):
                return build_twiml_response("⚠️ Error al reservar. Intenta nuevamente.")
            
            link = generar_google_calendar_link(fecha, hora, medico, especialidad)
            user_state[from_number] = {"estado": "inicio"}  # Reiniciar estado
            
            return build_twiml_response(
                f"✅ *Cita agendada con éxito:*\n\n"
                f"📅 *Fecha:* {fecha}\n"
                f"⏰ *Hora:* {hora.strftime('%H:%M')}\n"
                f"👨‍⚕️ *Doctor:* Dr. {medico}\n"
                f"📌 *Especialidad:* {especialidad}\n\n"
                f"📲 *Agendar en calendario:*\n{link}\n\n"
                "¡Gracias por tu reserva!"
            )

        # Para cualquier otro mensaje
        return build_twiml_response(
            "¡Hola! 👋 Para agendar una cita, escribe *AGENDAR*.\n"
            "Si ya estás en proceso, responde con el número de la cita."
        )

    except Exception as e:
        logger.error(f"Error en whatsapp_reply: {str(e)}")
        return build_twiml_response("⚠️ Error interno. Por favor, intenta nuevamente.")

def build_twiml_response(message_text):
    """Construye una respuesta TwiML"""
    response = MessagingResponse()
    response.message(message_text)
    return str(response)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)