import os
from fuzzywuzzy import fuzz
from flask import Flask, request
from datetime import datetime, timedelta
import pytz
import urllib.parse
import json
import difflib
from pathlib import Path
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / 'data'
user_state = {}

@app.route("/")
def health_check():
    return "Servidor operativo", 200

@app.route("/home")
def home():
    return "Servidor Flask funcionando correctamente 🎉"

def get_available_slots():
    try:
        tz = pytz.timezone('America/Santiago')
        today = datetime.now(tz).strftime('%Y-%m-%d')

        with open(DATA_DIR / 'citas.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        citas_hoy = [c for c in data['citas'] if c['fecha'] == today and c['disponible'] == 1]
        citas_hoy.sort(key=lambda x: x['hora'])

        return [
            (c['fecha'], datetime.strptime(c['hora'], '%H:%M:%S').time(), c['medico'], c['especialidad'])
            for c in citas_hoy[:3]
        ]
    except Exception as e:
        print("Error leyendo citas:", e)
        return []

def generar_google_calendar_link(fecha, hora, medico, especialidad):
    tz = pytz.timezone('America/Santiago')
    dt_inicio = tz.localize(datetime.combine(datetime.strptime(fecha, '%Y-%m-%d').date(), hora))
    dt_fin = dt_inicio + timedelta(minutes=30)

    start_str = dt_inicio.strftime('%Y%m%dT%H%M%S')
    end_str = dt_fin.strftime('%Y%m%dT%H%M%S')

    params = {
        'action': 'TEMPLATE',
        'text': f'Cita médica con {medico}',
        'dates': f'{start_str}/{end_str}',
        'details': f'Especialidad: {especialidad}',
        'location': 'Hospital DIPRECA',
    }

    return 'https://www.google.com/calendar/render?' + urllib.parse.urlencode(params)

def buscar_respuesta_faq(user_input, from_number):
    try:
        with open(DATA_DIR / 'faqs.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        user_input = user_input.lower().strip()
        coincidencias = []

        for faq in data['faqs']:
            score = fuzz.partial_ratio(user_input, faq['pregunta'].lower())
            if score > 60:  # Puedes ajustar el umbral
                coincidencias.append((score, faq))

        coincidencias.sort(reverse=True, key=lambda x: x[0])
        top_matches = [c[1] for c in coincidencias[:5]]

        if len(top_matches) == 0:
            return "🤔 No encontré una coincidencia clara. ¿Podrías reformular tu pregunta?"

        elif len(top_matches) == 1:
            return top_matches[0]['respuesta']

        else:
            user_state[from_number] = {
                "estado": "esperando_faq_opcion",
                "opciones_faq": top_matches
            }
            texto = "🤔 ¿A qué te refieres exactamente?\n\n"
            for i, faq in enumerate(top_matches, 1):
                texto += f"{i}. {faq['pregunta']}\n"
            texto += "\nEscribe el *número* de la opción correcta."
            return texto

    except Exception as e:
        print("Error leyendo FAQs:", e)
        return "Disculpa, estoy teniendo problemas para acceder a las preguntas frecuentes."

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    from_number = request.form.get('From')
    user_msg = request.form.get('Body').strip().lower()
    response = MessagingResponse()
    msg = response.message()

    estado = user_state.get(from_number, {}).get("estado", "inicio")

    if estado == "inicio":
        if "agendar" in user_msg or "hora" in user_msg or "cita" in user_msg:
            slots = get_available_slots()
            if slots:
                texto = "📅 *Opciones de cita disponibles:*\n\n"
                for i, row in enumerate(slots, 1):
                    texto += f"{i}. {row[1].strftime('%H:%M')} - {row[2]}\n"
                texto += "\nEscribe el *número* de la opción que deseas reservar ✅"
                user_state[from_number] = {"estado": "esperando_opcion", "slots": slots}
                msg.body(texto)
            else:
                msg.body("⛔ No hay horas disponibles por ahora. Intenta más tarde.")
        else:
            respuesta = buscar_respuesta_faq(user_msg, from_number)
            msg.body(respuesta)

    elif estado == "esperando_faq_opcion":
        if user_msg.isdigit():
            seleccion = int(user_msg) - 1
            opciones = user_state[from_number].get("opciones_faq", [])
            if 0 <= seleccion < len(opciones):
                msg.body(opciones[seleccion]["respuesta"])
                user_state[from_number] = {"estado": "inicio"}  # Reinicia estado
            else:
                msg.body("❌ Número inválido. Por favor responde con un número válido.")
        else:
            msg.body("❌ Por favor responde con el *número* correspondiente a una de las opciones.")

    elif estado == "esperando_faq_opcion":
        if user_msg.isdigit():
            seleccion = int(user_msg) - 1
            opciones = user_state[from_number].get("opciones_faq", [])
            if 0 <= seleccion < len(opciones):
                msg.body(opciones[seleccion]["respuesta"])
                user_state[from_number] = {"estado": "inicio"}
            else:
                msg.body("❌ Número inválido. Por favor responde con un número válido.")
        else:
            msg.body("❌ Por favor responde con un número correspondiente a una opción.")

    elif estado == "confirmado":
        if "agendar" in user_msg:
            slots = get_available_slots()
            if slots:
                texto = "📅 *Opciones de cita disponibles:*\n\n"
                for i, row in enumerate(slots, 1):
                    texto += f"{i}. {row[1].strftime('%H:%M')} - {row[2]}\n"
                texto += "\nEscribe el *número* de la opción que deseas reservar ✅"
                user_state[from_number] = {"estado": "esperando_opcion", "slots": slots}
                msg.body(texto)
        else:
            msg.body("🎉 Ya has agendado tu cita. Si deseas otra, escribe *'agendar'* o haz una nueva pregunta.")

    return str(response)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
