import pyodbc
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
import matplotlib.pyplot as plt
import seaborn as sns

conn_str = (
    'DRIVER={SQL Server};'
    'SERVER=168.88.162.158;'
    'DATABASE=dbhospital;'
    'UID=cli_abas;'
    'PWD=cli_abas'
)

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

query = """
SELECT id_Tpacientes, cod_sexo, edad, total_cuenta
FROM JMC_PAQUETES_HOSPITALARIOS WHERE COD_PRESTACION = '190205508'
"""  
df = pd.read_sql(query, conn)

bins = [0, 18, 30, 40, 50, 60, 100]  
labels = ['0-18', '19-30', '31-40', '41-50', '51-60', '61+']  
df['tramo_edad'] = pd.cut(df['edad'], bins=bins, labels=labels, right=False)

df['cod_sexo'] = df['cod_sexo'].map({'M': 0, 'F': 1})  
df['tramo_edad'] = df['tramo_edad'].astype('category').cat.codes  

X = df[['cod_sexo', 'tramo_edad']]
y = df['total_cuenta']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.4, random_state=42)

model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

nuevos_datos = pd.DataFrame({
    'cod_sexo': [1,0,1,0,1,0,1,0,1,0,1,0],  
    'tramo_edad': [0,0, 1,1,2,2,3,3,4,4,5,5] 
})

nuevos_datos['precio_proyectado'] = model.predict(nuevos_datos)

create_table_query = """
IF OBJECT_ID('JMC_PAQUETES_HOSPITALARIOS_python', 'U') IS NOT NULL 
    DROP TABLE JMC_PAQUETES_HOSPITALARIOS_python;
CREATE TABLE JMC_PAQUETES_HOSPITALARIOS_python (
    cod_sexo INT,
    tramo_edad INT,
    precio_proyectado FLOAT
);
"""

cursor.execute(create_table_query)
conn.commit()

for _, row in nuevos_datos.iterrows():
    insert_query = """
    INSERT INTO JMC_PAQUETES_HOSPITALARIOS_python (cod_sexo, tramo_edad, precio_proyectado)
    VALUES (?, ?, ?)
    """
    cursor.execute(insert_query, row['cod_sexo'], row['tramo_edad'], row['precio_proyectado'])

conn.commit()

cursor.close()
conn.close()