# GIS Utsunomiya LRT Spatial Analysis

## Project Overview

This repository contains a preliminary GIS workflow for analyzing the **Utsunomiya Light Rail Transit (LRT)** project in Tochigi Prefecture, Japan. The project focuses on spatially evaluating the social benefits and costs of the LRT by combining administrative boundaries, population, public transportation, land price, road, railway, and station passenger datasets.

The main research goal is to understand how the new LRT system may affect:

- Public transportation accessibility
- Mobility support for children and elderly residents
- Car dependency and traffic congestion
- Land value changes around LRT corridors
- Future population demand around stations and transit corridors

---

## Repository Structure

```text
GIS_Utsunomiya_LRT/
├── README.md
├── UtsunomiyaLRT.ipynb
└── dat/                  # Local data folder, not tracked if files are too large
```

> Note: Large raw geospatial datasets should generally be stored locally in `dat/` and excluded from GitHub using `.gitignore`.

---

## Data Sources

This project uses multiple geospatial datasets, mainly from **GADM** and **国土数値情報 / National Land Numerical Information**.

### 1. Administrative Boundary Data

| Item | Description |
|---|---|
| File names | `gadm41_JPN_0.shp`, `gadm41_JPN_1.shp`, `gadm41_JPN_2.shp` |
| Coverage | Japan nationwide; administrative levels 0, 1, and 2 |
| Year | 2018 |
| CRS | EPSG:4326, WGS 84 |
| Geometry | Polygon administrative boundaries |

Main attributes include country code, country name, prefecture name, municipality name, alternative names, administrative types, and unique IDs.

For this project, the data should be transformed from **EPSG:4326** to **EPSG:6678 / JGD2011** for distance-based analysis in meters.

---

### 2. 250m Mesh Future Population Data

| Item | Description |
|---|---|
| Identifier | `250m_mesh_2024_09.shp` |
| Coverage | Tochigi Prefecture, 250m mesh units |
| Geometry | Polygon / `GM_Surface` |
| Base year | 2020 |
| Projection years | 2025 to 2070, every 5 years |
| Estimate version | 2024 / R6 national land policy estimate |

This dataset provides future population estimates by 250m mesh, including total population and age-group populations.

Important fields include:

| Attribute | Description |
|---|---|
| `MESH_ID` | Quarter regional mesh code |
| `SHICODE` | Municipality code based on JIS X 0401 and JIS X 0402 |
| `PTN_2020` | Total population in 2020 |
| `PTN_20XX` | Total population for future year 20XX without suppression |
| `PT00_20XX` | Total population for year 20XX |
| `PT01_20XX` - `PT20_20XX` | Population by 5-year age groups |
| `PTA_20XX` | Population aged 0-14 |
| `PTB_20XX` | Population aged 15-64 |
| `PTC_20XX` | Population aged 65 and older |
| `PTD_20XX` | Population aged 75 and older |
| `PTE_20XX` | Population aged 80 and older |
| `RTA_20XX` - `RTE_20XX` | Age-group population ratios |

Use cases in this project:

- Estimate future LRT demand
- Identify population within walking distance of LRT stations
- Analyze elderly and child population access to public transportation
- Detect future transit-dependent areas

---

### 3. Bus Stop Data

| Item | Description |
|---|---|
| File name | `P11-22_09.shp` |
| Identifier | `P11` |
| Coverage | Tochigi Prefecture |
| Geometry | Point / `GM_Point` |
| Year | 2022 / Reiwa 4 |

This dataset contains bus stops for private route buses, public route buses, and community buses.

Important fields include:

| Attribute | Description |
|---|---|
| `P11_001` | Bus stop name |
| `P11_002` | Bus operator name; municipality name for community buses |
| `P11_003_01` - `P11_003_35` | Bus route names or route numbers |
| `P11_004_01` - `P11_004_35` | Bus category codes |
| `P11_005` | Notes |

Use cases in this project:

- Measure bus access around LRT stations
- Identify public transportation gaps
- Evaluate bus-LRT connectivity
- Compare pre-existing bus access with new LRT access

---

### 4. Land Price Publication Data

| Item | Description |
|---|---|
| File / identifier | `L01-26_09.shp` |
| Coverage | Tochigi Prefecture |
| Geometry | Point / `GM_Point` |
| Main reference date | January 1 of each year |
| Included years | Showa 58 to Reiwa 8 price and attribute history |
| Metadata note | Data standard year is listed as 2023 / Reiwa 5 |

This dataset contains official land price points based on Japan's land price publication system.

Important fields include:

| Attribute | Description |
|---|---|
| `L01_001` | Administrative area code |
| `L01_002` | Land use category |
| `L01_007` | Year |
| `L01_008` | Published land price, yen per square meter |
| `L01_009` | Year-over-year change rate |
| `L01_024` | Standard land point name |
| `L01_025` | Location and lot number |
| `L01_027` | Land area in square meters |
| `L01_048` | Nearest station or bus stop name |
| `L01_050` | Road distance to nearest station, meters |
| `L01_057` | Building coverage ratio limit |
| `L01_058` | Floor area ratio limit |
| `L01_062` - `L01_105` | Published prices from Showa 58 to Reiwa 8 |

Use cases in this project:

- Analyze land price changes near the LRT corridor
- Compare LRT station areas with non-station areas
- Apply hedonic pricing models
- Apply Difference-in-Differences analysis if pre/post LRT data are available

---

### 5. Road Data

| Item | Description |
|---|---|
| Identifier | `N13-24_5439` |
| Coverage | Japan mesh area `5439`, including Utsunomiya and surrounding areas |
| Geometry | Line / `GM_Curve` |
| Date field | `N13_001`, data registration date |

This dataset contains road line features from the digital national base map.

Important fields include:

| Attribute | Description |
|---|---|
| `N13_001` | Data registration date; not the road opening date |
| `N13_002` | Road type |
| `N13_003` | Road classification |
| `N13_004` | Road status |
| `N13_005` | Vertical layer order |
| `N13_006` | Road width category |
| `N13_007` | Toll road category |
| `N13_008` | Secondary mesh number |

Use cases in this project:

- Analyze road network density
- Estimate access distance to LRT stations
- Create walking-distance or network-distance buffers
- Compare LRT corridors with surrounding road infrastructure

---

### 6. Railway Time-Series Data

| Item | Description |
|---|---|
| File names | `RailroadSection2.shp`, `Station2.shp` |
| Identifier | `N05` |
| Coverage | Nationwide railway lines and stations |
| Geometry | Railway sections: line / `GM_Curve`; stations: point / `GM_Point` |
| Time fields | Opening year, installation start year, installation end year |

This dataset records railway lines and stations over time.

Common fields include:

| Attribute | Description |
|---|---|
| `N05_001` | Railway operator category |
| `N05_002` | Railway line name |
| `N05_003` | Operating company |
| `N05_004` | Opening year; unknown is `999` |
| `N05_005b` | Installation start year; before 1950 is coded as `1950` |
| `N05_005e` | Installation end year; current facilities are coded as `9999` |
| `N05_006` | Relation ID |
| `N05_007` | Transition ID |
| `N05_008` | Transition notes |
| `N05_009` | Notes on location or geometry accuracy |
| `N05_010` | Relation notes for railway sections |
| `N05_011` | Station name |

Use cases in this project:

- Locate existing railway lines and stations
- Compare LRT with existing railway networks
- Track station and line changes over time
- Define treatment and control areas around rail infrastructure

---

### 7. Station Passenger Data

| Item | Description |
|---|---|
| Identifier | `S12-25_NumberOfPassengers` |
| Coverage | Railway stations nationwide |
| Geometry | Station location, based on National Land Numerical Information station data |
| Years | 2011 to 2024 |
| Latest data | 2024 passenger data, prepared in 2025 |

This dataset provides daily passenger counts by station.

Important fields include:

| Attribute | Description |
|---|---|
| `S12_001` | Station name |
| `S12_001c` | Station code |
| `S12_001g` | Group code for stations within 300m with the same name |
| `S12_002` | Operating company |
| `S12_003` | Railway line name |
| `S12_004` | Railway category |
| `S12_005` | Operator category |
| `S12_006`, `010`, `014`, ..., `058` | Duplicate codes for 2011-2024 |
| `S12_007`, `011`, `015`, ..., `059` | Data availability codes for 2011-2024 |
| `S12_008`, `012`, `016`, ..., `060` | Notes and source information for 2011-2024 |
| `S12_009`, `013`, `017`, ..., `061` | Daily passenger counts for 2011-2024 |

Use cases in this project:

- Analyze rail station demand
- Compare station usage before and after LRT opening
- Identify comparable stations around Utsunomiya
- Support transit demand estimation

---

## Suggested Analysis Workflow

### 1. Data Loading and CRS Standardization

Load all shapefiles using GeoPandas and standardize coordinate reference systems.

```python
import geopandas as gpd

boundary = gpd.read_file("dat/gadm41_JPN_2.shp")
boundary = boundary.to_crs(epsg=6678)
```

For distance-based analysis, use **EPSG:6678 / JGD2011** instead of EPSG:4326.

---

### 2. Study Area Extraction

Extract Tochigi Prefecture and Utsunomiya-related municipalities from national or prefecture-level datasets.

Possible study area definitions:

- Utsunomiya City only
- Utsunomiya City and Haga Town
- LRT corridor buffer area
- Station walking catchment areas, such as 500m, 800m, or 1km buffers

---

### 3. Accessibility Analysis

Potential indicators:

- Population within walking distance of LRT stations
- Elderly population within walking distance of LRT stations
- Child population within walking distance of LRT stations
- Distance from each 250m mesh to the nearest station or bus stop
- Public transportation gap areas outside both LRT and bus stop catchments

---

### 4. Land Price Analysis

Potential methods:

- Compare land price points near and far from LRT stations
- Measure price changes before and after LRT opening
- Use station-distance variables in a hedonic pricing model
- Apply Difference-in-Differences using treatment and control areas

Example treatment definitions:

| Area | Definition |
|---|---|
| Treatment area | Land price points within 800m of LRT stations |
| Control area | Land price points farther than 800m but within the same municipality |
| Alternative treatment | Points within 500m or 1km of LRT stations |

---

### 5. Transportation Network Analysis

Potential indicators:

- Road density around LRT stations
- Bus stop density around LRT stations
- Distance to nearest bus stop or railway station
- LRT connection to existing bus and railway systems
- Areas where LRT may reduce car dependency

---

## Data Role Summary

| Dataset | Main Analytical Role |
|---|---|
| 250m mesh future population | Future demand estimation, elderly/child population access, walking catchment population |
| Bus stop data | Bus access, LRT-bus connectivity, public transportation gap detection |
| Land price data | Land value change, hedonic analysis, Difference-in-Differences analysis |
| Road data | Road network structure, access distance, road density |
| Railway time-series data | Existing rail network and station location comparison |
| Station passenger data | Rail demand, passenger trends, comparison with LRT station areas |
| Administrative boundaries | Study area clipping, municipal-level aggregation, mapping |

---

## Notes on Large Data Files

Because shapefiles and geospatial datasets can be large, the `dat/` directory may be excluded from GitHub.

Recommended `.gitignore` setting:

```text
dat/
.DS_Store
.ipynb_checkpoints/
```

If the data files must be shared through GitHub, use **Git LFS**.

```bash
git lfs install
git lfs track "*.shp"
git lfs track "*.dbf"
git lfs track "*.shx"
git lfs track "*.csv"
git add .gitattributes
git commit -m "Track geospatial data with Git LFS"
```

---

## Requirements

Recommended Python packages:

```bash
pip install geopandas pandas matplotlib contextily shapely pyproj fiona
```

Optional packages for network and spatial analysis:

```bash
pip install osmnx networkx folium mapclassify
```

---

## Research Direction

This project can support a preliminary cost-benefit and policy evaluation of the Utsunomiya LRT by integrating demographic, transportation, land price, and infrastructure datasets. The main empirical question is whether the LRT improves transportation access and produces measurable spatial benefits, especially for residents who are more dependent on public transportation.

Potential final outputs include:

- Maps of LRT station catchment areas
- Population and elderly population served by LRT
- Public transportation gap maps
- Land price comparison around LRT stations
- Pre/post accessibility comparison
- Preliminary cost-benefit discussion based on spatial indicators
