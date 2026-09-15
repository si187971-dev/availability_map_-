"""Расчёт зон пешеходной доступности (изохрон).

Для каждого узла графа вычисляется время до ближайшего сервиса
(многоисточниковый Дейкстра), затем достижимые узлы превращаются
в площадные полигоны изохрон.
"""

import networkx as nx
import geopandas as gpd
import osmnx as ox


def travel_times_to_service(G, source_nodes, cutoff=15):
    """Время до ближайшего сервиса для каждого узла графа.

    Запускает поиск кратчайших путей от каждого сервиса на обратном графе
    и оставляет по каждому узлу минимальное время.

    Parameters
    ----------
    G : networkx.MultiDiGraph
        Граф с атрибутом ``time`` на рёбрах.
    source_nodes : list
        Узлы, к которым привязаны сервисы.
    cutoff : float
        Порог доступности в минутах.

    Returns
    -------
    dict
        {узел: минуты до ближайшего сервиса}, только узлы в пределах cutoff.
    """
    G_rev = G.reverse(copy=True)
    best = {}
    for s in source_nodes:
        lengths = nx.single_source_dijkstra_path_length(
            G_rev, s, cutoff=cutoff, weight="time"
        )
        for node, t in lengths.items():
            if node not in best or t < best[node]:
                best[node] = t
    return best


def compute_access_times(G, service_nodes, cutoff=15):
    """Посчитать времена доступа для всех типов сервисов.

    Returns
    -------
    dict
        {имя_сервиса: {узел: минуты}}.
    """
    return {
        name: travel_times_to_service(G, nodes, cutoff) if nodes else {}
        for name, nodes in service_nodes.items()
    }


def make_isochrone(times_dict, nodes_gdf, buffer_m=40):
    """Построить полигон изохроны из достижимых узлов.

    Буфер вокруг каждого узла + объединение. Работает в метрической
    проекции (EPSG:3857), результат возвращается в EPSG:4326.

    Parameters
    ----------
    times_dict : dict
        {узел: минуты} — результат travel_times_to_service.
    nodes_gdf : GeoDataFrame
        Узлы графа (ox.graph_to_gdfs(G, edges=False)).
    buffer_m : float
        Радиус буфера вокруг узла, метры.

    Returns
    -------
    shapely.geometry.base.BaseGeometry | None
        Полигон зоны доступа, либо None если сервисов нет.
    """
    if not times_dict:
        return None
    pts = nodes_gdf.loc[list(times_dict.keys())].geometry
    pts_m = pts.to_crs("EPSG:3857")
    poly = pts_m.buffer(buffer_m).unary_union
    return gpd.GeoSeries([poly], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]


def build_isochrones(G, access_times, buffer_m=40):
    """Построить изохроны для всех сервисов.

    Returns
    -------
    dict
        {имя_сервиса: полигон | None}.
    """
    nodes_gdf = ox.graph_to_gdfs(G, edges=False)
    return {
        name: make_isochrone(times, nodes_gdf, buffer_m)
        for name, times in access_times.items()
    }
