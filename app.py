import os
from fuzzywuzzy import fuzz
from flask import Flask, request
from datetime import datetime, timedelta
import pytz
import urllib.parse
import json
from pathlib import Path
from twilio.twiml.messaging_response import MessagingResponse
import logging

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
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

def buscar_respuesta_faq(user_input, from_number):
    """Busca la mejor respuesta en las FAQs usando fuzzy matching"""
    try:
        with open(DATA_DIR / 'faqs.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        user_input = user_input.lower().strip()
        logger.info(f"Buscando FAQ para: {user_input}")

        coincidencias = []
        for faq in data['faqs']:
            # Búsqueda mejorada: compara tanto con pregunta como con palabras clave
            score_pregunta = fuzz.token_set_ratio(user_input, faq['pregunta'].lower())
            score_keywords = fuzz.partial_ratio(user_input, faq.get('keywords', '').lower())
            score = max(score_pregunta, score_keywords)
            
            if score > 65:  # Umbral más alto para mejores resultados
                coincidencias.append((score, faq))

        if not coincidencias:
            return "🤔 No encontré información sobre eso. ¿Podrías reformular tu pregunta o escribir 'agendar' para reservar hora?"

        coincidencias.sort(reverse=True, key=lambda x: x[0])
        top_matches = [c[1] for c in coincidencias[:3]]  # Mostrar máximo 3 opciones

        if len(top_matches) == 1:
            return top_matches[0]['respuesta']
        else:
            user_state[from_number] = {
                "estado": "esperando_faq_opcion",
                "opciones_faq": top_matches,
                "timestamp": datetime.now()
            }
            
            texto = "📚 Encontré varias opciones:\n\n"
            for i, faq in enumerate(top_matches, 1):
                texto += f"{i}. {faq['pregunta']}\n"
            texto += "\n🔢 Responde con el *número* de tu opción o 'menu' para volver."
            return texto

    except Exception as e:
        logger.error(f"Error en FAQs: {str(e)}")
        return "⚠️ Disculpa, estoy teniendo problemas técnicos. Intenta nuevamente más tarde."

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
    from_number = request.form.get('From')
    user_msg = request.form.get('Body').strip()
    response = MessagingResponse()
    msg = response.message()

    # Limpieza de estado inactivo
    if from_number in user_state:
        last_active = user_state[from_number].get("timestamp")
        if last_active and (datetime.now() - last_active) > timedelta(minutes=15):
            user_state[from_number] = {"estado": "inicio"}

    estado = user_state.get(from_number, {}).get("estado", "inicio")
    user_msg_lower = user_msg.lower()

    # Comandos globales
    if user_msg_lower in ['menu', 'inicio', 'volver']:
        user_state[from_number] = {"estado": "inicio", "timestamp": datetime.now()}
        msg.body("🏠 Menú principal:\n\n• Escribe 'agendar' para reservar hora\n• Haz tu pregunta y te ayudaré")
        return str(response)

    # Lógica principal de estados
    if estado == "inicio":
        if any(palabra in user_msg_lower for palabra in ["agendar", "hora", "cita", "reservar"]):
            slots = get_available_slots()
            if slots:
                texto = "📅 *Citas disponibles para hoy:*\n\n"
                for i, (fecha, hora, medico, especialidad) in enumerate(slots, 1):
                    texto += f"{i}. ⏰ {hora.strftime('%H:%M')} - 👨‍⚕️ Dr. {medico} ({especialidad})\n"
                texto += "\n🔢 Responde con el *número* de la opción que prefieres."
                
                user_state[from_number] = {
                    "estado": "esperando_opcion",
                    "slots": slots,
                    "timestamp": datetime.now()
                }
                msg.body(texto)
            else:
                msg.body("⏳ No hay citas disponibles en este momento.\n\nPuedes:\n• Intentar más tarde\n• Preguntar por otras especialidades\n• Escribir 'menu' para otras opciones")
        else:
            respuesta = buscar_respuesta_faq(user_msg, from_number)
            msg.body(respuesta)

    elif estado == "esperando_opcion":
        if user_msg.isdigit():
            seleccion = int(user_msg) - 1
            slots = user_state[from_number].get("slots", [])
            
            if 0 <= seleccion < len(slots):
                fecha, hora, medico, especialidad = slots[seleccion]
                
                # Verificar disponibilidad nuevamente
                slots_actuales = get_available_slots()
                if (fecha, hora, medico, especialidad) not in slots_actuales:
                    msg.body("❌ Esa cita ya no está disponible. Estas son las opciones actuales:")
                    # Mostrar slots disponibles nuevamente...
                else:
                    if actualizar_disponibilidad(fecha, hora, medico):
                        link = generar_google_calendar_link(fecha, hora, medico, especialidad)
                        msg.body(
                            f"✅ *Cita agendada con éxito!*\n\n"
                            f"👨‍⚕️ *Doctor:* Dr. {medico}\n"
                            f"📌 *Especialidad:* {especialidad}\n"
                            f"📅 *Fecha:* {fecha}\n"
                            f"⏰ *Hora:* {hora.strftime('%H:%M')}\n\n"
                            f"📲 *Agregar al calendario:*\n{link}\n\n"
                            f"Escribe 'menu' para volver al inicio."
                        )
                    else:
                        msg.body("⚠️ No pude reservar la cita. Por favor intenta nuevamente.")
                    
                    user_state[from_number] = {"estado": "inicio"}  # Reset completo
            else:
                msg.body(f"❌ Por favor elige un número entre 1 y {len(slots)}.")
        else:
            msg.body("🔢 Por favor responde solo con el *número* de la cita que deseas o 'menu' para volver.")

    elif estado == "esperando_faq_opcion":
        if user_msg.isdigit():
            seleccion = int(user_msg) - 1
            opciones = user_state[from_number].get("opciones_faq", [])
            
            if 0 <= seleccion < len(opciones):
                msg.body(opciones[seleccion]['respuesta'] + "\n\nEscribe 'menu' para volver al inicio.")
            else:
                msg.body(f"❌ Por favor elige un número entre 1 y {len(opciones)}.")
            
            user_state[from_number] = {"estado": "inicio"}  # Siempre reset después de FAQ
        else:
            msg.body("🔢 Por favor responde con el *número* de la opción que necesitas o 'menu' para volver.")

    return str(response)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)