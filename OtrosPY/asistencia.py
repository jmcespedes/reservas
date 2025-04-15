import pyodbc
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE
from sklearn.impute import SimpleImputer
import matplotlib.pyplot as plt
from imblearn.combine import SMOTEENN
from datetime import datetime

hora_inicio = datetime.now()
print(f"Hora de Inicio: {hora_inicio}")




conn_str = (
    'DRIVER={SQL Server};'
    'SERVER=168.88.162.158;'
    'DATABASE=dbhospital;'
    'UID=cli_abas;'
    'PWD=cli_abas'
)
conn = pyodbc.connect(conn_str)

query = """
SELECT RUN, NOMBRE_DIA, FECHA_ADD, HORA, EDAD, COD_SEXO, COD_ASISTENCIA, ID_GRUPO, 
       NOMBRE_GRUPO, NOMBRE_PRESTACION, CONFIRMACION_TELEFONICA    
FROM JMC_PREDICCION_ASISTENCIA
"""

df = pd.read_sql(query, conn)
conn.close()

df["FECHA_ADD"] = pd.to_datetime(df["FECHA_ADD"])
df["HORA"] = pd.to_datetime(df["HORA"], format="%H:%M:%S", errors="coerce").dt.hour
df["ASISTENCIA"] = df["COD_ASISTENCIA"].map({"A": 1, "S": 1, "N": 0})

dias_semana = {"LUNES": 0, "MARTES": 1, "MIERCOLES": 2, "JUEVES": 3, "VIERNES": 4, "SABADO": 5, "DOMINGO": 6}
df["DIA_NUM"] = df["NOMBRE_DIA"].map(dias_semana)

df["NOMBRE_PRESTACION"] = df["NOMBRE_PRESTACION"].astype("category").cat.codes
df["COD_SEXO"] = df["COD_SEXO"].map({"F": 1, "M": 0})

historial = df.groupby("RUN").agg(
    TOTAL_CITAS=("ASISTENCIA", "count"),
    TOTAL_ASISTENCIAS=("ASISTENCIA", "sum")
).reset_index()
historial["PORCENTAJE_ASISTENCIA"] = historial["TOTAL_ASISTENCIAS"] / historial["TOTAL_CITAS"]

df = df.merge(historial, on="RUN", how="left")

df["TOTAL_CITAS"] = df["TOTAL_CITAS"].fillna(0)
df["TOTAL_ASISTENCIAS"] = df["TOTAL_ASISTENCIAS"].fillna(0)
df["PORCENTAJE_ASISTENCIA"] = df["PORCENTAJE_ASISTENCIA"].fillna(0)

features = ["EDAD", "COD_SEXO", "DIA_NUM", "HORA", "ID_GRUPO", "NOMBRE_PRESTACION",
             "TOTAL_ASISTENCIAS", "PORCENTAJE_ASISTENCIA"]
X = df[features]
y = df["ASISTENCIA"]

imputer = SimpleImputer(strategy='mean')
X_imputed = imputer.fit_transform(X)

smote_enn = SMOTEENN(random_state=42)
X_resampled, y_resampled = smote_enn.fit_resample(X_imputed, y)

X_train, X_test, y_train, y_test = train_test_split(X_resampled, y_resampled, test_size=0.4, random_state=42)

# Modelo de Random Forest
modelo = RandomForestClassifier(random_state=42)

param_grid = {
    'n_estimators': [100, 200, 300],
    'max_depth': [None, 10, 20, 30],
    'min_samples_split': [2, 5, 10],
    'min_samples_leaf': [1, 2, 4],
    'max_features': ['auto', 'sqrt', 'log2']
}

random_search = RandomizedSearchCV(estimator=modelo, param_distributions=param_grid, n_iter=10, cv=20, n_jobs=-1, verbose=2, random_state=42)
random_search.fit(X_train, y_train)

modelo_mejorado = random_search.best_estimator_

y_pred = modelo_mejorado.predict(X_test)
print("Exactitud:", accuracy_score(y_test, y_pred))
print(classification_report(y_test, y_pred))

cm = confusion_matrix(y_test, y_pred)
print("Matriz de Confusión:\n", cm)

df["PROBABILIDAD_ASISTENCIA"] = modelo_mejorado.predict_proba(X_imputed)[:, 1]

probabilidades_df = df[["RUN", "PROBABILIDAD_ASISTENCIA", "TOTAL_ASISTENCIAS", "PORCENTAJE_ASISTENCIA"]]

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

cursor.execute("""
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='PROBABILIDAD_ASISTENCIA' AND xtype='U')
BEGIN
    CREATE TABLE PROBABILIDAD_ASISTENCIA (
        RUN VARCHAR(50),
        PROBABILIDAD_ASISTENCIA FLOAT,
        TOTAL_ASISTENCIAS INT,
        PORCENTAJE_ASISTENCIA FLOAT
    )
END
""")

conn.commit()

probabilidades_df["PROBABILIDAD_ASISTENCIA"] = probabilidades_df["PROBABILIDAD_ASISTENCIA"].fillna(0)
probabilidades_df = probabilidades_df.drop_duplicates(subset=["RUN"], keep="first")
probabilidades_df["RUN"] = probabilidades_df["RUN"].astype(str)

cursor.execute("DELETE FROM PROBABILIDAD_ASISTENCIA")
conn.commit()

for index, row in probabilidades_df.iterrows():
    cursor.execute("INSERT INTO PROBABILIDAD_ASISTENCIA (RUN, PROBABILIDAD_ASISTENCIA, TOTAL_ASISTENCIAS, PORCENTAJE_ASISTENCIA) VALUES (?, ?, ?, ?)", 
                   row["RUN"], row["PROBABILIDAD_ASISTENCIA"], row["TOTAL_ASISTENCIAS"], row["PORCENTAJE_ASISTENCIA"])

conn.commit()
cursor.close()
conn.close()

inasistencias_por_dia = df[df["ASISTENCIA"] == 0].groupby("NOMBRE_DIA").size().sort_values(ascending=False)
plt.figure(figsize=(10, 6))
inasistencias_por_dia.plot(kind='bar', color='skyblue')
plt.title('Días con más inasistencias')
plt.xlabel('Día de la semana')
plt.ylabel('Número de inasistencias')
plt.xticks(rotation=45)
plt.show()
0
inasistencias_por_genero = df[df["ASISTENCIA"] == 0].groupby("COD_SEXO").size()

if inasistencias_por_genero.empty:
    print("No hay registros de inasistencias.")
else:
    inasistencias_por_genero = inasistencias_por_genero.sort_values(ascending=False).head(2)

    plt.figure(figsize=(10, 6))
    inasistencias_por_genero.plot(kind='bar', color='lightcoral')
    plt.title('Asistencia por Genero')
    plt.xlabel('Genero')
    plt.ylabel('Número de inasistencias')
    plt.xticks(rotation=0)
    plt.show()

top_grupo_servicio_inasistencias = df[df["ASISTENCIA"] == 0].groupby("NOMBRE_GRUPO").size().sort_values(ascending=False).head(5)
print("Top 5 de grupo_servicio con más inasistencias:")
print(top_grupo_servicio_inasistencias)

hora_termino = datetime.now()
print(f"Hora de Termino: {hora_termino}")
diferencia = hora_termino - hora_inicio


print("La diferencia de tiempo es:", diferencia)

print("FIN")
