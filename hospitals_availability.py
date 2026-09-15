import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
import folium
import networkx as nx
import re

# настройки OSM
ox.settings.use_cache = True
ox.settings.log_console = True

place = "Фрунзенский район, Санкт-Петербург"

# графы
g_walk = ox.graph_from_place(place, network_type="walk")
g_drive = ox.graph_from_place(place, network_type="drive")

print(f"Пешеходная сеть: {len(g_walk)} узлов, {g_walk.size()} рёбер")
print(f"Дорожная сеть: {len(g_drive)} узлов, {g_drive.size()} рёбер")

# пешеход: скорость 4.5 км/ч = 75 м/мин
walk_speed_m_per_min = 75

for u, v, data in g_walk.edges(data=True):
    # если length отсутствует, пропускаем или ставим 0
    length = data.get("length", 0)
    data["time"] = length / walk_speed_m_per_min  # минуты

# авто: скорости и время
g_drive = ox.add_edge_speeds(g_drive)
g_drive = ox.add_edge_travel_times(g_drive)

# больницы/поликлиники
doctors = ox.features_from_place(place, {"amenity": "doctors"})
doctors = doctors[doctors.geometry.notna()]

if doctors.empty:
    raise ValueError("Не найдено объектов amenity=doctors в указанном районе")

# компилируем шаблон один раз
pattern = re.compile(r"(поликлиника|цовп)", flags=re.IGNORECASE)

def matches_name(name):
    if not isinstance(name, str):
        return False
    return bool(pattern.search(name))

mask = doctors["name"].apply(matches_name)
doctors = doctors[mask]

print(f"Отфильтровано поликлиник/ЦОВП: {len(doctors)}")
if doctors.empty:
    raise ValueError("После фильтрации по названию не осталось объектов. Проверьте ключевые слова.")

# центроиды в EPSG:4326
# сначала в метрическую проекцию, чтобы центроид был геометрически корректным, потом обратно
doctors_proj = doctors.to_crs("EPSG:3857")
doctors_proj["geometry"] = doctors_proj.geometry.centroid
doctors_pts = doctors_proj.to_crs("EPSG:4326")

# ближайшие узлы графа
doctors_nodes = ox.distance.nearest_nodes(
    g_walk,
    X=doctors_pts.geometry.x,  # долгота
    Y=doctors_pts.geometry.y   # широта
)

def make_isochrone(g, source_node, max_time, weight="time"):
    """Полигон зоны достижимости из узла за max_time минут (грубое приближение)."""
    subgraph = nx.ego_graph(g, source_node, radius=max_time, distance=weight)
    node_points = [
        Point(g.nodes[n]["x"], g.nodes[n]["y"])
        for n in subgraph.nodes()
    ]
    if len(node_points) < 3:
        return None
    gdf_nodes = gpd.GeoDataFrame(geometry=node_points, crs="EPSG:4326")
    return gdf_nodes.unary_union.convex_hull

trip_time = 10  # минут
isochrones = []
for node in doctors_nodes:
    poly = make_isochrone(g_walk, node, trip_time)
    if poly is not None:
        isochrones.append(poly)

if not isochrones:
    raise RuntimeError("Не удалось построить ни одной изохроны. Проверьте веса рёбер (time).")

covered_area = unary_union(isochrones)
covered_gdf = gpd.GeoDataFrame(geometry=[covered_area], crs="EPSG:4326")

# жилые зоны (landuse=residential)
residential = ox.features_from_place(
    place, {"landuse": "residential"}
)
if residential.empty:
    raise ValueError("Не найдены жилые зоны (landuse=residential). Попробуйте расширить район.")

# для расчётов площадей используем UTM (более равноплощадная проекция для СПб)
# EPSG:32636 = UTM 36N
utm_crs = "EPSG:32636"
residential_utm = residential.to_crs(utm_crs)
covered_utm = covered_gdf.to_crs(utm_crs)

covered_res = gpd.overlay(residential_utm[["geometry"]], covered_utm, how="intersection")
pct_covered = covered_res.area.sum() / residential_utm.area.sum() * 100
print(f"Доля жилых зон в 10‑мин доступности: {pct_covered:.1f}%")

# карта
center = [doctors_pts.geometry.y.mean(), doctors_pts.geometry.x.mean()]
m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")

folium.GeoJson(
    covered_gdf,
    name="10‑мин доступность",
    style_function=lambda x: {
        "fillColor": "green", "color": "green",
        "weight": 1, "fillOpacity": 0.25
    },
).add_to(m)

deserts = gpd.overlay(
    residential[["geometry"]],
    covered_gdf,
    how="difference"
)
folium.GeoJson(
    deserts,
    name="Дефицит доступности",
    style_function=lambda x: {
        "fillColor": "red", "color": "red",
        "weight": 1, "fillOpacity": 0.4
    },
).add_to(m)

for _, row in doctors_pts.iterrows():
    folium.CircleMarker(
        [row.geometry.y, row.geometry.x],
        radius=6, color="blue", fill=True, fill_color="blue",
        popup=row.get("name", "Поликлиника"),
    ).add_to(m)

folium.LayerControl().add_to(m)
m.save("accessibility_map.html")
