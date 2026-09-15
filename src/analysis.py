"""Метрики покрытия, дефицитные зоны и рекомендация размещения сервиса.

Наложение изохрон на границы города, расчёт доли покрытия по площади,
поиск «пустынь доступа» и жадный max-coverage выбор точки для нового объекта.
"""

import numpy as np
import networkx as nx
import geopandas as gpd
import osmnx as ox


def _area_km2(geom):
    """Площадь геометрии (EPSG:4326) в км² через метрическую проекцию."""
    return gpd.GeoSeries([geom], crs="EPSG:4326").to_crs("EPSG:3857").area.iloc[0] / 1e6


def coverage_metrics(place, isochrones):
    """Доля площади города, покрытая зоной доступа каждого сервиса.

    Parameters
    ----------
    place : str
        Название места (для получения границ города).
    isochrones : dict
        {имя_сервиса: полигон | None}.

    Returns
    -------
    (list[dict], dict)
        Список метрик по сервисам и словарь {имя: полигон дефицита}.
    """
    city = ox.geocode_to_gdf(place).to_crs("EPSG:4326")
    city_poly = city.geometry.iloc[0]
    city_area = _area_km2(city_poly)

    rows, deserts = [], {}
    for name, iso in isochrones.items():
        if iso is None:
            rows.append({"service": name, "covered_km2": 0.0,
                         "desert_km2": round(city_area, 1), "coverage_share": 0.0})
            continue
        covered = city_poly.intersection(iso)
        cov_area = _area_km2(covered)
        deserts[name] = city_poly.difference(iso)
        rows.append({
            "service": name,
            "covered_km2": round(cov_area, 1),
            "desert_km2": round(city_area - cov_area, 1),
            "coverage_share": round(cov_area / city_area, 3),
        })
    return rows, deserts


def population_proxy_coverage(place, isochrones):
    """Прокси покрытия населения через плотность жилой застройки OSM.

    Доля жилых зданий внутри зоны доступа ≈ доля обеспеченного населения.

    Returns
    -------
    dict
        {имя_сервиса: доля (0..1)}.
    """
    residential = ["residential", "apartments", "house",
                   "detached", "terrace", "dormitory"]
    buildings = ox.features_from_place(place, {"building": True})
    res = buildings[buildings.get("building").isin(residential)].copy()
    res = res[res.geometry.notna()]
    res["geometry"] = res.geometry.centroid
    res = res.to_crs("EPSG:4326")
    total = len(res)

    result = {}
    for name, iso in isochrones.items():
        if iso is None or total == 0:
            result[name] = 0.0
        else:
            result[name] = res.geometry.within(iso).sum() / total
    return result


def best_new_location(G, existing_times, cutoff=15, sample=200, seed=42):
    """Жадный max-coverage: узел, максимально сокращающий дефицит доступа.

    Среди узлов вне текущей зоны доступа ищет тот, что охватит максимум
    таких же недоступных узлов за cutoff минут — кандидат на новый сервис.

    Parameters
    ----------
    G : networkx.MultiDiGraph
    existing_times : dict
        {узел: минуты} — текущее покрытие сервисом.
    cutoff : float
        Порог доступности, минут.
    sample : int
        Размер случайной выборки узлов-кандидатов (ради скорости).
    seed : int
        Зерно генератора для воспроизводимости.

    Returns
    -------
    (node_id | None, int)
        Узел-кандидат и число охваченных ранее недоступных узлов.
    """
    desert = [n for n in G.nodes if n not in existing_times]
    if not desert:
        return None, 0
    desert_set = set(desert)
    rng = np.random.default_rng(seed)
    cand = rng.choice(desert, size=min(sample, len(desert)), replace=False)

    G_rev = G.reverse(copy=True)
    best_node, best_gain = None, -1
    for c in cand:
        reach = nx.single_source_dijkstra_path_length(
            G_rev, c, cutoff=cutoff, weight="time"
        )
        gain = len(desert_set & reach.keys())
        if gain > best_gain:
            best_node, best_gain = c, gain
    return best_node, best_gain
