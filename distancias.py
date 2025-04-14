import geopandas as gpd
import matplotlib.pyplot as plt

# Cargar un mapa del mundo desde GeoPandas
world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))

# Mostrar los primeros registros
print(world.head())

# Graficar el mapa
world.plot(figsize=(10, 6), color="lightblue", edgecolor="black")
plt.title("Mapa del Mundo con GeoPandas")
plt.show()
