import pyodbc
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse
from flask import Flask

app = Flask(__name__)

@app.route("/")
def inicio():
    return "¡Hola desde Flask en Render!"


# Datos de Twilio
account_sid = 'ACca96871739ae16b72c725adec77012c8'
auth_token = 'd588793b92fd6e40c94691a9a37ec2a5'
twilio_whatsapp_number = 'whatsapp:+14155238886'
your_phone = 'whatsapp:+56942675794'

# Config DB
db_config = {
    'driver': '{ODBC Driver 17 for SQL Server}',
    'server': '168.88.162.158',
    'database': 'DB_INFORMATICA',
    'uid': 'cli_abas',
    'pwd': 'cli_abas'
}

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

        return rows if rows else []

    except Exception as e:
        print(f"Error al consultar SQL Server: {e}")
        return []

def send_whatsapp_options(to, opciones):
    body = "📅 *Selecciona una hora para reservar:*\n\n"
    for i, row in enumerate(opciones, 1):
        hora = row[1].strftime('%H:%M')
        medico = row[2]
        body += f"{i}. {hora} - {medico}\n"

    body += "\nResponde con el número de la opción que deseas ✅"

    data = {
        'To': to,
        'From': twilio_whatsapp_number,
        'Body': body
    }

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    response = requests.post(
        url,
        auth=(account_sid, auth_token),
        data=data
    )

    print(f"📤 Respuesta Twilio (opciones): {response.status_code} - {response.text}")

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

    url = 'https://www.google.com/calendar/render?' + urllib.parse.urlencode(params)
    return url

def send_calendar_link(to, slot):
    fecha = slot[0]
    hora = slot[1]
    medico = slot[2]
    especialidad = slot[3]

    link = generar_google_calendar_link(fecha, hora, medico, especialidad)

    body = f"✅ Tu cita médica con *{medico}* ha sido agendada.\n🩺 Especialidad: {especialidad}\n📅 Fecha: {fecha.strftime('%Y-%m-%d')} a las {hora.strftime('%H:%M')}\n\n📲 Agrega la cita a tu calendario:\n{link}"

    data = {
        'To': to,
        'From': twilio_whatsapp_number,
        'Body': body
    }

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    response = requests.post(
        url,
        auth=(account_sid, auth_token),
        data=data
    )

    print(f"📤 Respuesta Twilio (calendar link): {response.status_code} - {response.text}")

# --- MAIN ---

if __name__ == '__main__':
    print("🔎 Obteniendo horas médicas disponibles...")

    slots = get_available_slots()

    if slots:
        print(f"📨 Enviando opciones a {your_phone}...")
        send_whatsapp_options(your_phone, slots)

        # 🔁 Simulamos que el usuario eligió la primera opción (índice 0)
        seleccion = 0
        print("🗓️ Enviando enlace de calendario para la opción seleccionada...")
        send_calendar_link(your_phone, slots[seleccion])
    else:
        print("⛔ No hay horas disponibles para hoy.")
