from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


# Configura el WebDriver (ejemplo con Chrome)
driver = webdriver.Chrome()

try:
    # Abrir la página de inicio de sesión
    driver.get("kace.dipreca.cl")

    # Esperar a que el elemento de login esté presente
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "LOGIN_PASSWORD")))

    # Llenar el formulario de inicio de sesión
    driver.find_element(By.NAME, "LOGIN_PASSWORD").send_keys("tu_contraseña")  # Reemplaza con tu contraseña
    driver.find_element(By.NAME, "button_login").click()



    # Seleccionar la opción en el dropdown
    select_element = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, "select2-chosen-1")))
    select_element.click()

    # Elegir la opción "HospDipreca.cl"
    option = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//li[contains(text(), 'HospDipreca.cl')]")))
    option.click()



    # Obtener la tabla de tickets
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    ticket_table = soup.find("table", class_="ticket-table")

    # Imprimir la tabla
    if ticket_table:
        print(ticket_table.prettify())
    else:
        print("No se encontró la tabla de tickets")

finally:
    # Cerrar el navegador
    driver.quit()