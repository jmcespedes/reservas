import pyodbc
from datetime import datetime
import pytz
import requests

account_sid = 'ACca96871739ae16b72c725adec77012c8'
auth_token = 'd588793b92fd6e40c94691a9a37ec2a5'
twilio_whatsapp_number = 'whatsapp:+14155238886'
your_phone = 'whatsapp:+56942675794'

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
    body = "📅 *Selecciona una hora para reservar:*\n"
    
    buttons = []
    for row in opciones:
        hora = row[1].strftime('%H:%M')
        medico = row[2]
        label = f"{hora} - {medico}"
        buttons.append({
            'type': 'reply',
            'reply': {
                'id': f"{hora}-{medico}",
                'title': label
            }
        })

    # Limitar los botones a 3
    buttons = buttons[:3]

    # Estructura correcta para el mensaje interactivo con botones
    data = {
        'To': to,
        'From': twilio_whatsapp_number,
        'Body': body,
        'Interactive': '{"type":"button", "header":{"type":"text", "text":"Confirmación de cita médica"}, "body":{"text":"Selecciona una hora para reservar:"}, "footer":{"text":"Selecciona una opción para confirmar tu cita."}, "action":{"buttons":' + str(buttons).replace("'", "\"") + '}}'
    }

    # Enviar mensaje a Twilio usando su API
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    
    # Enviamos los datos como application/x-www-form-urlencoded
    response = requests.post(
        url,
        auth=(account_sid, auth_token),
        data=data  # Enviamos los datos como x-www-form-urlencoded
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
