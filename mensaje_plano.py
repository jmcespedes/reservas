import pyodbc
from datetime import datetime
import pytz
import requests
import urllib.parse

# Configuración de Twilio
account_sid = 'ACca96871739ae16b72c725adec77012c8'
auth_token = 'd588793b92fd6e40c94691a9a37ec2a5'
twilio_whatsapp_number = 'whatsapp:+14155238886'
your_phone = 'whatsapp:+56942675794'

# Configuración SQL Server
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

def send_whatsapp_with_buttons(to, opciones):
    # Creamos el mensaje con quick replies (botones simulados)
    body = "📅 *Selecciona una hora para reservar:*\n"
    persistent_actions = []

    for row in opciones:
        hora = row[1].strftime('%H:%M')
        medico = row[2]
        label = f"{hora} - {medico}"
        persistent_actions.append(f"reply:{label}")

    # Limitamos a 3 botones
    persistent_actions = persistent_actions[:3]

    # Enviar el mensaje
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = {
        'To': to,
        'From': twilio_whatsapp_number,
        'Body': body,
        'PersistentAction': ','.join(persistent_actions)
    }

    response = requests.post(
        url,
        auth=(account_sid, auth_token),
        data=data
    )

    print(f"📤 Respuesta Twilio: {response.status_code} - {response.text}")

if __name__ == '__main__':
    print("🔎 Obteniendo horas médicas disponibles...")

    slots = get_available_slots()

    if slots:
        print(f"📨 Enviando opciones a {your_phone}...")
        send_whatsapp_with_buttons(your_phone, slots)
    else:
        print("⛔ No hay horas disponibles para hoy.")