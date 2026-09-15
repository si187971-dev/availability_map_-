import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import MultiPoint
from shapely.ops import unary_union
import folium
import warnings
import os
warnings.filterwarnings("ignore")

# настройки OSM
ox.settings.use_cache = True
ox.settings.log_console = True
ox.settings.overpass_url = "https://overpass.kumi.systems/api/interpreter"
print("OSMnx", ox.__version__)

PLACE = "Фрунзенский район, Санкт-Петербург"   # ← замените на нужный город
WALK_SPEED_KMH = 4.5        # средняя скорость пешехода
CUTOFF = 15                 # порог доступности, минут
BUFFER_M = 40               # буфер вокруг достижимых узлов для полигона изохроны

SERVICE_TAGS = {
    "hospital": {"amenity": "doctors"},
    "school":   {"amenity": "school"},
}
COLORS = {"hospital": "#d1495b", "school": "#00798c"}

meters_per_min = WALK_SPEED_KMH * 1000 / 60
print(f"Скорость: {meters_per_min:.0f} м/мин · порог: {CUTOFF} мин "
      f"(~{meters_per_min*CUTOFF/1000:.1f} км по сети)")

# --- ОСНОВНОЙ вариант: весь город / район из PLACE ---
G = ox.graph_from_place(PLACE, network_type="walk")

# --- АЛЬТЕРНАТИВА для очень больших городов: круг радиусом N км от центра ---
# center_point = (59.9391, 30.3159)   # Дворцовая площадь
# G = ox.graph_from_point(center_point, dist=5000, network_type="walk")

for _, _, data in G.edges(data=True):
    data["time"] = data["length"] / meters_per_min   # минуты

print(f"Узлов: {len(G.nodes):,} · рёбер: {len(G.edges):,}")

# загрузка общественных сервисов
services = {}
for name, tag in SERVICE_TAGS.items():
    try:
        gdf = ox.features_from_place(PLACE, tag)
        gdf = gdf[gdf.geometry.notna()].copy()
        gdf["geometry"] = gdf.geometry.centroid
        gdf = gdf.to_crs("EPSG:4326")
        services[name] = gdf
        print(f"{name:9s}: {len(gdf):4d} объектов")
    except Exception as e:
        services[name] = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        print(f"{name:9s}: 0 (нет данных — {type(e).__name__})")


# Каждый сервис сажаем на ближайший перекресток графа
service_nodes = {}
for name, gdf in services.items():
    if len(gdf) == 0:
        service_nodes[name] = []
        continue
    nodes = ox.distance.nearest_nodes(G, X=gdf.geometry.x.values,
                                          Y=gdf.geometry.y.values)
    service_nodes[name] = list(np.unique(nodes))
    print(f"{name:9s}: привязано к {len(service_nodes[name])} узлам")

# Расчет времени для ближайшего сервиса
def travel_times_to_service(G, source_nodes, cutoff):
    """{узел: минуты до ближайшего сервиса}, ограничено cutoff."""
    G_rev = G.reverse(copy=True)   # от сервиса КО всем узлам
    best = {}
    for s in source_nodes:
        lengths = nx.single_source_dijkstra_path_length(
            G_rev, s, cutoff=cutoff, weight="time")
        for node, t in lengths.items():
            if node not in best or t < best[node]:
                best[node] = t
    return best

access_times = {}
for name, nodes in service_nodes.items():
    access_times[name] = travel_times_to_service(G, nodes, CUTOFF) if nodes else {}
    reachable = len(access_times[name])
    print(f"{name:9s}: {reachable:,} узлов в пределах {CUTOFF} мин "
          f"({reachable/len(G.nodes):.0%} сети)")


nodes_gdf = ox.graph_to_gdfs(G, edges=False)

# Построение полигонов изохрон
def make_isochrone(times_dict, buffer_m=BUFFER_M):
    if not times_dict:
        return None
    pts = nodes_gdf.loc[list(times_dict.keys())].geometry
    pts_m = pts.to_crs("EPSG:3857")
    poly = pts_m.buffer(buffer_m).unary_union
    return gpd.GeoSeries([poly], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]

isochrones = {name: make_isochrone(t) for name, t in access_times.items()}
for name, iso in isochrones.items():
    if iso is not None:
        area_km2 = gpd.GeoSeries([iso], crs="EPSG:4326").to_crs("EPSG:3857").area.iloc[0]/1e6
        print(f"{name:9s}: зона доступа ≈ {area_km2:.1f} км²")


# Определяем зоны доступности
city = ox.geocode_to_gdf(PLACE).to_crs("EPSG:4326")
city_poly = city.geometry.iloc[0]
city_area = gpd.GeoSeries([city_poly], crs="EPSG:4326").to_crs("EPSG:3857").area.iloc[0]/1e6

rows = []
deserts = {}
for name, iso in isochrones.items():
    if iso is None:
        rows.append([name, 0, city_area, 0.0]); continue
    covered = city_poly.intersection(iso)
    cov_area = gpd.GeoSeries([covered], crs="EPSG:4326").to_crs("EPSG:3857").area.iloc[0]/1e6
    deserts[name] = city_poly.difference(iso)
    rows.append([name, round(cov_area,1), round(city_area-cov_area,1), cov_area/city_area])

coverage = pd.DataFrame(rows, columns=["service","covered_km2","desert_km2","coverage_share"])
coverage["coverage_share"] = (coverage["coverage_share"]*100).round(1).astype(str)+"%"
coverage


# Прокси населения по плотности застройки
try:
    buildings = ox.features_from_place(PLACE, {"building": True})
    res = buildings[buildings.get("building").isin(
        ["residential","apartments","house","detached","terrace","dormitory"])].copy()
    res = res[res.geometry.notna()]
    res["geometry"] = res.geometry.centroid
    res = res.to_crs("EPSG:4326")
    total = len(res)
    print(f"Жилых зданий (прокси населения): {total:,}\n")

    pop_rows = []
    for name, iso in isochrones.items():
        if iso is None:
            pop_rows.append([name, "0%"]); continue
        inside = res.geometry.within(iso).sum()
        pop_rows.append([name, f"{inside/total*100:.0f}%"])
    pop_cov = pd.DataFrame(pop_rows, columns=["service","population_covered_proxy"])
    display(pop_cov)
except Exception as e:
    print("Прокси населения недоступен:", type(e).__name__, e)


# Интерактивная карта
center = [city_poly.centroid.y, city_poly.centroid.x]
m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")

# контур города
folium.GeoJson(city_poly, name="Граница города",
               style_function=lambda x: {"fill": False, "color": "#333", "weight": 2}
               ).add_to(m)

for name, iso in isochrones.items():
    if iso is None:
        continue
    c = COLORS[name]
    folium.GeoJson(
        iso, name=f"Доступность ≤{CUTOFF}мин: {name}",
        style_function=lambda x, c=c: {"fillColor": c, "color": c,
                                       "weight": 1, "fillOpacity": 0.22},
    ).add_to(m)
    fg = folium.FeatureGroup(name=f"Объекты: {name}", show=False)
    for _, row in services[name].iterrows():
        folium.CircleMarker([row.geometry.y, row.geometry.x], radius=3,
                            color=c, fill=True, fill_opacity=0.9).add_to(fg)
    fg.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
m.save("accessibility_map.html")
print("Карта сохранена → accessibility_map.html")
m

# Рекомендации
def best_new_location(G, existing_times, cutoff, sample=400):
    """Возвращает узел-кандидат, максимально сокращающий дефицит."""
    desert = [n for n in G.nodes if n not in existing_times]
    if not desert:
        return None, 0
    desert_set = set(desert)
    # ограничиваем перебор случайной выборкой для скорости
    rng = np.random.default_rng(42)
    cand = rng.choice(desert, size=min(sample, len(desert)), replace=False)
    G_rev = G.reverse(copy=True)
    best_node, best_gain = None, -1
    for c in cand:
        reach = nx.single_source_dijkstra_path_length(G_rev, c, cutoff=cutoff, weight="time")
        gain = len(desert_set & reach.keys())
        if gain > best_gain:
            best_node, best_gain = c, gain
    return best_node, best_gain

# на графе мегаполиса уменьшите sample (напр. 150) ради скорости
node, gain = best_new_location(G, access_times.get("hospital", {}), CUTOFF, sample=200)
if node:
    p = nodes_gdf.loc[node].geometry
    print(f"Кандидат на новую больницу: узел {node} @ ({p.y:.5f}, {p.x:.5f})")
    print(f"Охватит ~{gain:,} ранее недоступных перекрёстков за {CUTOFF} мин пешком.")
else:
    print("Весь город уже покрыт — новая больница не требуется по этому критерию.")

    print("Карта сохранена в:", os.path.abspath("accessibility_map.html"))
