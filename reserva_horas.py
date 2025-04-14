from twilio.rest import Client
import pyodbc
from datetime import datetime
import pytz

# Configuración de Twilio
account_sid = 'ACca96871739ae16b72c725adec77012c8'
auth_token = 'd588793b92fd6e40c94691a9a37ec2a5'
twilio_whatsapp_number = 'whatsapp:+14155238886'
your_phone = 'whatsapp:+56942675794'

# Configuración SQL Server
db_config = {
    'driver': '{ODBC Driver 17 for SQL Server}',  # O ajusta según tu versión
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
        SELECT top 5 fecha, hora, medico, especialidad
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

def send_whatsapp_message(to, body):
    """Envía un mensaje por WhatsApp usando Twilio"""
    client = Client(account_sid, auth_token)

    message = client.messages.create(
        body=body,
        from_=twilio_whatsapp_number,
        to=to
    )

    return message.sid


if __name__ == '__main__':
    print("Obteniendo horas médicas disponibles...")

    slots = get_available_slots()

    if slots:
        message = "📅 *Agenda Médica - Horas disponibles para hoy*\n\n"
        for row in slots:
            fecha = row[0].strftime('%d-%m-%Y')
            hora = row[1].strftime('%H:%M')
            medico = row[2]
            especialidad = row[3]
            message += f"• {hora} - {medico} ({especialidad})\n"
        message += "\nResponde con 'RESERVAR [hora] [médico]' para reservar una hora."
    else:
        message = "⛔ No hay horas disponibles para hoy."

    print(f"Enviando mensaje a {your_phone}...")
    sid = send_whatsapp_message(your_phone, message)
    print(f"✅ Mensaje enviado. SID: {sid}")