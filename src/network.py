"""Загрузка и подготовка пешеходной сети из OpenStreetMap.

Функции для скачивания дорожного графа города, добавления времени в пути
на рёбра и загрузки общественных сервисов (POI) по тегам OSM.
"""

import osmnx as ox
import numpy as np
import geopandas as gpd

ox.settings.use_cache = True
ox.settings.log_console = False


def load_walk_network(place, walk_speed_kmh=4.5):
    """Загрузить пешеходный граф города и проставить время прохождения рёбер.

    Parameters
    ----------
    place : str
        Название места для геокодирования, напр. "Saint Petersburg, Russia".
    walk_speed_kmh : float
        Средняя скорость пешехода, км/ч.

    Returns
    -------
    networkx.MultiDiGraph
        Граф с атрибутом ``time`` (минуты) на каждом ребре.
    """
    G = ox.graph_from_place(place, network_type="walk")
    meters_per_min = walk_speed_kmh * 1000 / 60
    for _, _, data in G.edges(data=True):
        data["time"] = data["length"] / meters_per_min
    return G


def load_network_from_point(center_point, dist=5000, walk_speed_kmh=4.5):
    """Вариант для больших городов: граф в радиусе dist (м) от точки.

    Parameters
    ----------
    center_point : tuple(float, float)
        Координаты центра (lat, lon).
    dist : int
        Радиус в метрах.
    walk_speed_kmh : float
        Средняя скорость пешехода, км/ч.
    """
    G = ox.graph_from_point(center_point, dist=dist, network_type="walk")
    meters_per_min = walk_speed_kmh * 1000 / 60
    for _, _, data in G.edges(data=True):
        data["time"] = data["length"] / meters_per_min
    return G


def load_services(place, service_tags):
    """Загрузить общественные сервисы из OSM по словарю тегов.

    Parameters
    ----------
    place : str
        Название места.
    service_tags : dict
        {имя_сервиса: {osm_key: osm_value}},
        напр. {"hospital": {"amenity": "hospital"}}.

    Returns
    -------
    dict
        {имя_сервиса: GeoDataFrame точек (центроидов) в EPSG:4326}.
    """
    services = {}
    for name, tag in service_tags.items():
        try:
            gdf = ox.features_from_place(place, tag)
            gdf = gdf[gdf.geometry.notna()].copy()
            gdf["geometry"] = gdf.geometry.centroid
            services[name] = gdf.to_crs("EPSG:4326")
        except Exception:
            services[name] = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return services


def snap_services_to_nodes(G, services):
    """Привязать каждый сервис к ближайшему узлу графа.

    Returns
    -------
    dict
        {имя_сервиса: список уникальных id узлов}.
    """
    service_nodes = {}
    for name, gdf in services.items():
        if len(gdf) == 0:
            service_nodes[name] = []
            continue
        nodes = ox.distance.nearest_nodes(
            G, X=gdf.geometry.x.values, Y=gdf.geometry.y.values
        )
        service_nodes[name] = list(np.unique(nodes))
    return service_nodes
