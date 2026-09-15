# Urban Accessibility Analysis — Saint Petersburg

Оценка пешеходной доступности общественных сервисов (**больницы, школы**)
с помощью сетевого анализа поверх данных OpenStreetMap. Для каждого сервиса строятся
**изохроны** — зоны, из которых до ближайшего объекта можно дойти пешком за ≤ 15 минут, —
после чего выявляются «пустыни доступа» и предлагается оптимальное место для нового сервиса.

> Проект демонстрирует полный цикл GIS Data Science: сбор гео-данных → сетевой анализ →
> пространственные метрики → визуализация → actionable-рекомендация для городского планирования.

---

## 🗺️ Демо

<!-- Замените на свои скриншоты из outputs/ -->
![Карта доступности](https://si187971-dev.github.io/availability_map_-/outputs/maps/accessibility_overview.png)

*Интерактивная версия: [`accessibility_map.html`](https://si187971-dev.github.io/availability_map_-/outputs/accessibility_map.html) — слои можно включать/выключать.*

| Зоны доступа | Дефицитные районы |
|---|---|
| ![изохроны](https://si187971-dev.github.io/availability_map_-/outputs/maps/isochrones.png) | ![необходимость размещения](https://si187971-dev.github.io/availability_map_-/outputs/maps/deserts.png) |

---

## 📊 Ключевые результаты

<!-- Заполните числами после запуска ноутбука -->

| Сервис    | Покрытие площади | Покрытие населения (прокси) |
|-----------|:----------------:|:---------------------------:|
| Больницы  |        90%       |             __%             |
| Школы     |        93%       |             __%             |


**Главные выводы:**
- Больницы: основные пробелы доступа — районы `Волковки`; рекомендуемая точка для нового
  объекта охватывает ~`5-10` ранее недоступных перекрёстков за 15 минут пешком.
- Школы: на 93% закрывают потребность района.


---

## 🔧 Стек

`Python` · `OSMnx` · `NetworkX` · `GeoPandas` · `Shapely` · `Folium`

- **OSMnx** — загрузка пешеходной сети и POI из OpenStreetMap
- **NetworkX** — многоисточниковый алгоритм Дейкстры для расчёта времени в пути
- **GeoPandas / Shapely** — построение полигонов изохрон и пространственные операции
- **Folium** — интерактивная карта со слоями

---

## ⚙️ Как запустить

```bash
pip install osmnx geopandas networkx folium mapclassify contextily shapely
jupyter notebook urban_accessibility_analysis.ipynb
```

Или откройте ноутбук в **Google Colab** и выполните *Run All* (раскомментируйте
`!pip install ...` в первой ячейке).

**Сменить город/район** — одна строка в Шаге 1:

```python
PLACE = "Saint Petersburg, Russia"
# или отдельный район (быстрее и аккуратнее для демо):
PLACE = "Vasileostrovsky District, Saint Petersburg, Russia"
```

> ⚠️ Полный граф мегаполиса — сотни тысяч узлов. Для первого запуска и скриншотов
> рекомендуется один район: считается за секунды и надёжно влезает в память Colab.

---

## 🧠 Как это работает

1. **Дорожная сеть.** Загружается пешеходный граф города; каждому ребру присваивается
   время прохождения (длина ÷ скорость пешехода).
2. **Сервисы.** Больницы и школы берутся из OSM по тегам и привязываются к ближайшим узлам графа.
3. **Изохроны.** Алгоритм Дейкстра на обратном графе даёт для каждого узла
   время до *ближайшего* сервиса; узлы за пределами порога — дефицит.
4. **Метрики.** Полигоны зон доступа накладываются на границы города и плотность
   жилой застройки (прокси населения) → доля покрытия по площади и по людям.
5. **Рекомендация.** Max-coverage алгоритм ищет узел, размещение сервиса в
   котором максимально сокращает число недоступных территорий.

---

## 🐍 Использование модулей

Весь анализ можно собрать из функций `src/` без ноутбука:

```python
from src.network import load_walk_network, load_services, snap_services_to_nodes
from src.isochrones import compute_access_times, build_isochrones
from src.analysis import coverage_metrics, best_new_location

PLACE = "Vasileostrovsky District, Saint Petersburg, Russia"
TAGS = {
    "hospital": {"amenity": "hospital"},
    "school":   {"amenity": "school"},
    "park":     {"leisure": "park"},
}

# 1. Сеть и сервисы
G = load_walk_network(PLACE, walk_speed_kmh=4.5)
services = load_services(PLACE, TAGS)
service_nodes = snap_services_to_nodes(G, services)

# 2. Времена доступа и изохроны (порог 15 минут)
access_times = compute_access_times(G, service_nodes, cutoff=15)
isochrones = build_isochrones(G, access_times, buffer_m=40)

# 3. Метрики покрытия и рекомендация размещения новой больницы
metrics, deserts = coverage_metrics(PLACE, isochrones)
node, gain = best_new_location(G, access_times["hospital"], cutoff=15)

print(metrics)
print(f"Кандидат под новую больницу: узел {node}, охват +{gain} узлов")
```

---

## 📁 Структура репозитория

```
urban-accessibility/
├── README.md
├── urban_accessibility_analysis.ipynb   # демо: полный пайплайн по шагам
├── src/                                # переиспользуемая логика
│   ├── network.py                      # загрузка сети и сервисов из OSM
│   ├── isochrones.py                   # расчёт времени в пути и изохрон
│   └── analysis.py                     # метрики, дефицит, рекомендация
├── outputs/
│   ├── https://si187971-dev.github.io/availability_map_-/accessibility_map.html           # интерактивная карта
│   └── maps/                            # PNG-скриншоты для README
├── .gitattributes                      # карта исключена из языковой статистики
└── requirements.txt
```

Ноутбук — это демонстрация пайплайна по шагам; переиспользуемая логика вынесена
в модули `src/`, чтобы функции можно было импортировать и тестировать отдельно.

---

## ⚠️ Ограничения

- Полнота данных OSM различается по районам (для больниц покрытие обычно хорошее,
  для школ/парков — местами неполное).
- Население аппроксимируется плотностью жилой застройки; для точного анализа
  подключается растр **WorldPop** или **GHS-POP**.
- Скорость пешехода взята усреднённой — рельеф, переходы и барьеры не учитываются.

---

## 📈 Возможные расширения

- Замена прокси населения на растр WorldPop с зональной статистикой (`rasterio`).
- Учёт общественного транспорта (GTFS) для мультимодальной доступности.
- Индекс равенства доступа (сопоставление покрытия с доходами районов).
