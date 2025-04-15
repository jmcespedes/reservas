from flask import Flask, request
from datetime import datetime, timedelta
import pytz
import urllib.parse
import json
from pathlib import Path
from twilio.twiml.messaging_response import MessagingResponse


app = Flask(__name__)


DATA_DIR = Path(__file__).parent / 'data'

@app.route("/")
def home():
    return "Servidor Flask funcionando correctamente 🎉"

user_state = {}

account_sid = 'ACca96871739ae16b72c725adec77012c8'
auth_token = 'd588793b92fd6e40c94691a9a37ec2a5'
twilio_whatsapp_number = 'whatsapp:+14155238886'

def get_available_slots():
    try:
        tz = pytz.timezone('America/Santiago')
        today = datetime.now(tz).strftime('%Y-%m-%d')
        print("Buscando horas para:", today)

        with open(DATA_DIR / 'citas.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            

        citas_hoy = [
            c for c in data['citas'] 
            if c['fecha'] == today and c['disponible'] == 1
        ]
        

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
    dt_inicio = tz.localize(datetime.combine(
        datetime.strptime(fecha, '%Y-%m-%d').date(),
        hora
    ))
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

def buscar_respuesta_faq(user_input):
    try:
        with open(DATA_DIR / 'faqs.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        user_input = user_input.lower()
        for faq in data['faqs']:
            if user_input in faq['pregunta'].lower():
                return faq['respuesta']
        return None
        
    except Exception as e:
        print("Error leyendo FAQs:", e)
        return None

@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    from_number = request.form.get('From')
    user_msg = request.form.get('Body').strip().lower()
    response = MessagingResponse()
    msg = response.message()

    estado = user_state.get(from_number, {}).get("estado", "inicio")

    if estado == "inicio":
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
                msg.body("⛔ No hay horas disponibles por ahora. Intenta más tarde.")
        else:
            respuesta_faq = buscar_respuesta_faq(user_msg)
            if respuesta_faq:
                msg.body(respuesta_faq)
            else:
                msg.body("👋 Hola, escribe *'Quiero agendar una hora'* para ver las citas disponibles o haz una pregunta sobre el hospital.")
    
    elif estado == "esperando_opcion":
        if user_msg.isdigit():
            seleccion = int(user_msg) - 1
            slots = user_state[from_number]["slots"]

            if 0 <= seleccion < len(slots):
                slot = slots[seleccion]
                link = generar_google_calendar_link(slot[0], slot[1], slot[2], slot[3])

                msg.body(
                    f"✅ Cita con *{slot[2]}* agendada para el {slot[0]} a las {slot[1].strftime('%H:%M')}.\n\n"
                    f"📲 Agrega al calendario aquí:\n{link}"
                )

                user_state[from_number]["estado"] = "confirmado"
            else:
                msg.body("❌ Opción no válida. Por favor escribe un número del 1 al 3.")
        else:
            msg.body("❌ Por favor responde solo con el número de la opción (1, 2 o 3).")
    
    elif estado == "confirmado":
        msg.body("🎉 Ya has agendado tu cita. Si deseas otra, escribe *'agendar'*.")
    
    return str(response)

if __name__ == "__main__":
    app.run(debug=True, port=5000)