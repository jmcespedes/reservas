import os
from fuzzywuzzy import fuzz
from flask import Flask, request, make_response
from datetime import datetime, timedelta
import pytz
import urllib.parse
import json
from pathlib import Path
from twilio.twiml.messaging_response import MessagingResponse
import logging

# Configuración avanzada de logging
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

@app.route("/")
def health_check():
    return "Servidor operativo", 200

@app.route("/home")
def home():
    return "Servidor Flask funcionando correctamente 🎉"

def get_available_slots():
    """Obtiene las citas disponibles para hoy"""
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

def buscar_respuesta_faq(usuario_input, from_number):
    try:
        with open(DATA_DIR / 'faqs.json', 'r', encoding='utf-8') as f:
            faqs_data = json.load(f)
        
        input_limpio = usuario_input.lower().strip()
        coincidencias = []
        
        for faq in faqs_data['faqs']:
            # Búsqueda en pregunta y keywords
            score_pregunta = fuzz.token_set_ratio(input_limpio, faq['pregunta'].lower())
            score_keywords = max(
                fuzz.partial_ratio(input_limpio, kw.lower()) 
                for kw in faq.get('keywords', '').split(', ')
            )
            score_max = max(score_pregunta, score_keywords)
            
            if score_max > 70:  # Umbral más alto para mayor precisión
                coincidencias.append({
                    "score": score_max,
                    "faq": faq,
                    "tipo": "pregunta" if score_pregunta > score_keywords else "keyword"
                })
        
        if not coincidencias:
            return "❓ No encontré información sobre eso. Intenta con:\n- 'Agendar cita'\n- 'Horario atención'\n- 'Ubicación'"
        
        # Ordenar por score y priorizar matches exactos
        coincidencias.sort(key=lambda x: (-x['score'], x['tipo'] == 'keyword'))
        
        # Si hay un claro ganador (diferencia > 15 puntos)
        if len(coincidencias) > 1 and (coincidencias[0]['score'] - coincidencias[1]['score'] > 15):
            return coincidencias[0]['faq']['respuesta']
        
        # Mostrar opciones si hay empate técnico
        user_state[from_number] = {
            "estado": "esperando_faq_opcion",
            "opciones": [c['faq'] for c in coincidencias[:3]],
            "timestamp": datetime.now()
        }
        
        respuesta = "🔍 Encontré varias opciones:\n\n"
        for i, opcion in enumerate(coincidencias[:3], 1):
            respuesta += f"{i}. {opcion['faq']['pregunta']}\n"
        respuesta += "\nResponde con el número de la opción que necesitas."
        
        return respuesta

    except Exception as e:
        logger.error(f"Error buscando FAQ: {str(e)}")
        return "⚠️ Ocurrió un error al buscar la información. Por favor intenta nuevamente."

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

        # Limpieza de estado inactivo
        current_time = datetime.now()
        if from_number in user_state:
            last_active = user_state[from_number].get("timestamp")
            if last_active and (current_time - last_active) > timedelta(minutes=15):
                user_state[from_number] = {"estado": "inicio"}
                logger.debug(f"Reseteado estado por inactividad para {from_number}")

        estado = user_state.get(from_number, {}).get("estado", "inicio")
        user_msg_lower = user_msg.lower()

        # Comandos globales
        if user_msg_lower in ['menu', 'inicio', 'volver', 'hola', 'hi']:
            user_state[from_number] = {
                "estado": "inicio",
                "timestamp": current_time
            }
            return build_twiml_response(
                "🏠 *Menú Principal* 🏠\n\n"
                "1. 📅 Agendar cita médica\n"
                "2. ❓ Preguntas frecuentes\n"
                "3. 🏥 Información del hospital\n"
                "4. 🕒 Horarios de atención\n\n"
                "Responde con el número de tu consulta o escribe tu pregunta."
            )

        # Lógica principal de estados
        if estado == "inicio":
            if any(palabra in user_msg_lower for palabra in ["agendar", "hora", "cita", "reservar", "1"]):
                slots = get_available_slots()
                if not slots:
                    return build_twiml_response(
                        "⏳ No hay citas disponibles en este momento.\n\n"
                        "Puedes:\n• Intentar más tarde\n• Preguntar por otras especialidades\n"
                        "• Escribir 'menu' para otras opciones"
                    )
                
                texto = "📅 *Citas disponibles para hoy:*\n\n"
                for i, (fecha, hora, medico, especialidad) in enumerate(slots, 1):
                    texto += f"{i}. ⏰ {hora.strftime('%H:%M')} - 👨‍⚕️ Dr. {medico} ({especialidad})\n"
                texto += "\n🔢 Responde con el *número* de la opción que prefieres."
                
                user_state[from_number] = {
                    "estado": "esperando_opcion",
                    "slots": slots,
                    "timestamp": current_time
                }
                return build_twiml_response(texto)
            
            elif any(palabra in user_msg_lower for palabra in ["preguntas", "faq", "2"]):
                return build_twiml_response(
                    "❓ *Preguntas Frecuentes:*\n\n"
                    "Escribe tu pregunta o elige un tema:\n\n"
                    "1. Requisitos para atención\n"
                    "2. Especialidades\n"
                    "3. Documentación necesaria\n"
                    "4. Ubicación y contacto"
                )
            
            else:
                respuesta = buscar_respuesta_faq(user_msg, from_number)
                return build_twiml_response(respuesta)

        elif estado == "esperando_opcion":
            if user_msg.isdigit():
                seleccion = int(user_msg) - 1
                slots = user_state[from_number].get("slots", [])
                
                if not 0 <= seleccion < len(slots):
                    return build_twiml_response(f"❌ Por favor elige un número entre 1 y {len(slots)}.")
                
                fecha, hora, medico, especialidad = slots[seleccion]
                
                # Verificar disponibilidad nuevamente
                slots_actuales = get_available_slots()
                if (fecha, hora, medico, especialidad) not in slots_actuales:
                    return build_twiml_response("❌ Esa cita ya no está disponible. Por favor escribe 'menu' para volver a empezar.")
                
                if not actualizar_disponibilidad(fecha, hora, medico):
                    return build_twiml_response("⚠️ No pude reservar la cita. Por favor intenta nuevamente.")
                
                link = generar_google_calendar_link(fecha, hora, medico, especialidad)
                user_state[from_number] = {"estado": "inicio"}  # Reset completo
                
                return build_twiml_response(
                    f"✅ *Cita agendada con éxito!*\n\n"
                    f"👨‍⚕️ *Doctor:* Dr. {medico}\n"
                    f"📌 *Especialidad:* {especialidad}\n"
                    f"📅 *Fecha:* {fecha}\n"
                    f"⏰ *Hora:* {hora.strftime('%H:%M')}\n\n"
                    f"📲 *Agregar al calendario:*\n{link}\n\n"
                    f"Escribe 'menu' para volver al inicio."
                )
            else:
                return build_twiml_response("🔢 Por favor responde solo con el *número* de la cita que deseas o 'menu' para volver.")

        elif estado == "esperando_faq_opcion":
            if user_msg.isdigit():
                seleccion = int(user_msg) - 1
                opciones = user_state[from_number].get("opciones_faq", [])
                
                if not 0 <= seleccion < len(opciones):
                    return build_twiml_response(f"❌ Por favor elige un número entre 1 y {len(opciones)}.")
                
                respuesta = opciones[seleccion]['respuesta'] + "\n\nEscribe 'menu' para volver al inicio."
                user_state[from_number] = {"estado": "inicio"}
                return build_twiml_response(respuesta)
            else:
                return build_twiml_response("🔢 Por favor responde con el *número* de la opción que necesitas o 'menu' para volver.")

    except Exception as e:
        logger.error(f"Error en whatsapp_reply: {str(e)}")
        return build_twiml_response("⚠️ Ocurrió un error interno. Por favor intenta nuevamente más tarde.")

def build_twiml_response(message_text):
    """Construye una respuesta TwiML adecuada"""
    try:
        response = MessagingResponse()
        response.message(message_text)
        twiml = str(response)
        logger.debug(f"Enviando respuesta TwiML: {twiml}")
        
        # Crear respuesta Flask con headers correctos
        flask_response = make_response(twiml)
        flask_response.headers['Content-Type'] = 'text/xml'
        return flask_response
    except Exception as e:
        logger.error(f"Error al construir respuesta TwiML: {str(e)}")
        response = MessagingResponse()
        response.message("Error interno del sistema")
        return str(response), 500, {'Content-Type': 'text/xml'}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)