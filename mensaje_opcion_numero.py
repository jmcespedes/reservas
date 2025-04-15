from flask import Flask, request
from datetime import datetime, timedelta
import pyodbc
import pytz
import urllib.parse

from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/")
def home():
    return "Servidor Flask funcionando correctamente 🎉"


# Estado de usuarios temporal (se recomienda Redis o DB real para producción)
user_state = {}

# Twilio config
account_sid = 'ACca96871739ae16b72c725adec77012c8'
auth_token = 'd588793b92fd6e40c94691a9a37ec2a5'
twilio_whatsapp_number = 'whatsapp:+14155238886'

# DB config
db_config = {
    'driver': '{ODBC Driver 17 for SQL Server}',
    'server': '168.88.162.158',
    'database': 'DB_INFORMATICA',
    'uid': 'cli_abas',
    'pwd': 'cli_abas'
}

# Obtener horas disponibles
def get_available_slots():
    try:
        tz = pytz.timezone('America/Santiago')
        today = datetime.now(tz).strftime('%Y-%m-%d')

        conn_str = f"DRIVER={db_config['driver']};SERVER={db_config['server']};DATABASE={db_config['database']};UID={db_config['uid']};PWD={db_config['pwd']}"
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        query = """
        SELECT TOP 3 fecha, hora, medico, especialidad
        FROM Reservas
        WHERE CONVERT(DATE, fecha) = ? AND disponible = 1
        ORDER BY hora
        """

        cursor.execute(query, (today,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        print("Error DB:", e)
        return []


# Generar link calendario
def generar_google_calendar_link(fecha, hora, medico, especialidad):
    tz = pytz.timezone('America/Santiago')
    dt_inicio = tz.localize(datetime.combine(fecha, hora))
    dt_fin = dt_inicio + timedelta(minutes=30)

    start_str = dt_inicio.strftime('%Y%m%dT%H%M%S')
    end_str = dt_fin.strftime('%Y%m%dT%H%M%S')

    params = {
        'action': 'TEMPLATE',
        'text': f'Cita médica con {medico}',
        'dates': f'{start_str}/{end_str}',
        'details': f'Especialidad: {especialidad}',
        'location': 'Clínica Central',
    }

    return 'https://www.google.com/calendar/render?' + urllib.parse.urlencode(params)


# Webhook de WhatsApp
@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    from_number = request.form.get('From')
    user_msg = request.form.get('Body').strip().lower()
    response = MessagingResponse()
    msg = response.message()

    estado = user_state.get(from_number, {}).get("estado", "inicio")

    # 🟢 Etapa 1: Inicio
    if estado == "inicio":
        if "agendar" in user_msg:
            slots = get_available_slots()
            if slots:
                texto = "📅 *Opciones de cita disponibles:*\n\n"
                for i, row in enumerate(slots, 1):
                    texto += f"{i}. {row[1].strftime('%H:%M')} - {row[2]}\n"
                texto += "\nEscribe el *número* de la opción que deseas reservar ✅"

                # Guardamos el estado y las opciones
                user_state[from_number] = {"estado": "esperando_opcion", "slots": slots}
                msg.body(texto)
            else:
                msg.body("⛔ No hay horas disponibles por ahora. Intenta más tarde.")
        else:
            msg.body("👋 Hola, escribe *'Quiero agendar una hora'* para ver las citas disponibles.")
    
    # 🟡 Etapa 2: Esperando número
    elif estado == "esperando_opcion":
        if user_msg.isdigit():
            seleccion = int(user_msg) - 1
            slots = user_state[from_number]["slots"]

            if 0 <= seleccion < len(slots):
                slot = slots[seleccion]
                link = generar_google_calendar_link(slot[0], slot[1], slot[2], slot[3])

                msg.body(
                    f"✅ Cita con *{slot[2]}* agendada para el {slot[0].strftime('%Y-%m-%d')} a las {slot[1].strftime('%H:%M')}.\n\n"
                    f"📲 Agrega al calendario aquí:\n{link}"
                )

                user_state[from_number]["estado"] = "confirmado"
            else:
                msg.body("❌ Opción no válida. Por favor escribe un número del 1 al 3.")
        else:
            msg.body("❌ Por favor responde solo con el número de la opción (1, 2 o 3).")
    
    # 🔵 Etapa 3: Confirmado
    elif estado == "confirmado":
        msg.body("🎉 Ya has agendado tu cita. Si deseas otra, escribe *'agendar'*.")
    
    return str(response)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
