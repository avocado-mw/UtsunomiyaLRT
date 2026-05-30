# GIS Utsunomiya LRT Preliminary Spatial Analysis

## Project Overview

This repository contains a shapefile-based GIS workflow for a preliminary spatial analysis of the **Utsunomiya Light Rail Transit (LRT / Lightline)** project in Tochigi Prefecture, Japan. The analysis evaluates where the LRT may generate social benefits by combining administrative boundaries, population mesh data, public transportation facilities, land price points, road infrastructure, and optional hospital / clinic locations.

The main research goal is to understand how the LRT may affect:

- Public transportation accessibility
- Mobility support for elderly residents and children
- Access to medical facilities when optional hospital / clinic data are available
- Bus-LRT and railway-LRT connectivity
- Car dependency and road-network burden
- Land value differences around LRT corridors
- Future residential location demand around LRT stations and feeder-bus corridors
- Preliminary cost-benefit evaluation using the Sasaki / Sato-style household relocation model

The workflow is designed for **preliminary analysis**. It prepares harmonized spatial layers, creates walking catchments around LRT stops, summarizes population and elderly population within those catchments, evaluates transportation and medical-facility connectivity, compares land prices by LRT distance zone, and implements a simplified replication of the Sasaki / Sato logit-based location-choice and cost-benefit framework.

---

## Repository Structure

```text
GIS_Utsunomiya_LRT/
├── README.md
├── UtsunomiyaLRT.ipynb
├── sasaki_lrt_shapefile_preliminary_analysis_fixed_geometry.ipynb
├── data/                         # Local raw shapefiles and optional layers
│   ├── gadm41_JPN_1.shp
│   ├── gadm41_JPN_2.shp
│   ├── 250m_mesh_2024_09.shp
│   ├── P11-22_09.shp
│   ├── RailroadSection2.shp
│   ├── Station2.shp
│   ├── L01-26_09.shp
│   ├── N13-24_5439.shp
│   ├── lrt_stops.shp
│   ├── feeder_stops.shp              # Optional
│   ├── hospital_locations.shp        # Optional
│   └── clinic_locations.shp          # Optional
└── outputs/
    ├── figures/
    ├── tables/
    └── shapefiles/
```

> Shapefiles require all related sidecar files, especially `.shp`, `.shx`, `.dbf`, and `.prj`. If a `.prj` file is missing, the notebook assigns the documented source CRS before reprojecting to the analysis CRS.

Large raw geospatial datasets should usually be stored locally in `data/` and excluded from GitHub using `.gitignore`.

---

## Coordinate Reference System

All distance-based analysis is performed in:

```text
EPSG:6678 / JGD2011
```

The workflow converts each input layer to this CRS before calculating distances, buffers, areas, road length, nearest-neighbor distances, or walking-time proxy variables.

Common CRS handling:

| Dataset | Original CRS used in source description | Analysis CRS |
|---|---:|---:|
| GADM administrative boundaries | EPSG:4326 / WGS 84 | EPSG:6678 |
| MLIT / National Land Numerical Information layers | EPSG:6668 / JGD2011 when documented | EPSG:6678 |
| User-created LRT, feeder, hospital, and clinic shapefiles | Must be set or detected from `.prj` | EPSG:6678 |

---

## Data Sources Used in the Analysis

This project uses geospatial datasets mainly from **GADM** and **国土数値情報 / National Land Numerical Information**. Only datasets used in the current preliminary analysis are listed below.

---

### 1. Administrative Boundary Data

| Item | Description |
|---|---|
| File names | `gadm41_JPN_0.shp`, `gadm41_JPN_1.shp`, `gadm41_JPN_2.shp` |
| Coverage | Japan nationwide; administrative levels 0, 1, and 2 |
| Year | 2018 |
| CRS | EPSG:4326 / WGS 84 |
| Geometry | Polygon administrative boundaries |

Main attributes include country code, country name, prefecture name, municipality name, alternative names, administrative types, and unique IDs.

Important fields include:

| Attribute | Description |
|---|---|
| `GID_0` | Country-level ID |
| `NAME_0` | Country name |
| `GID_1` | Prefecture-level ID |
| `NAME_1` | Prefecture name |
| `GID_2` | Municipality-level ID |
| `NAME_2` | Municipality name |
| `TYPE_1`, `TYPE_2` | Administrative boundary type |
| `ENGTYPE_1`, `ENGTYPE_2` | English administrative type |
| `HASC_1`, `HASC_2` | Hierarchical administrative code |

Use cases in this project:

- Extract Tochigi Prefecture
- Extract Utsunomiya City
- Optionally include Haga Town because the LRT corridor extends toward Haga-Takanezawa Industrial Park
- Clip national and prefectural datasets to the study area
- Map municipality boundaries
- Aggregate statistics by municipality or corridor

---

### 2. 250m Mesh Future Population Data

| Item | Description |
|---|---|
| Identifier / file name | `250m_mesh_2024_09.shp` |
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

Fields retained for the current workflow:

| Field | Role |
|---|---|
| `MESH_ID` | Zone identifier |
| `SHICODE` | Municipality code |
| `PT00_2025` | 2025 total population |
| `PTA_2025` | 2025 child population, if present |
| `PTB_2025` | 2025 working-age population, if present |
| `PTC_2025` | 2025 elderly population |
| `RTC_2025` | 2025 elderly population share, if present |
| `geometry` | Mesh polygon |

Use cases in this project:

- Estimate future LRT demand
- Identify population within 500m and 800m walking catchments of LRT stops
- Estimate elderly and child population access to public transportation
- Detect future transit-dependent areas
- Construct 500m analysis zones for the Sasaki / Sato-style population redistribution model
- Calculate zone centroids for ZA, ZB, ZC, and ZD variables

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

Pre-processing notes:

- Bus stop names are cleaned by removing full-width and half-width spaces.
- Duplicate or near-duplicate stops can occur because multiple operators may have separate records near the same location.
- For preliminary analysis, stops are clipped to the study area and counted within LRT station buffers.

Use cases in this project:

- Measure bus access around LRT stations
- Identify public transportation gaps
- Evaluate bus-LRT connectivity
- Estimate nearest public transport access time for ZA
- Compare pre-existing bus access with new LRT access
- Support the feeder-bus scenario in the Sasaki / Sato-style model

---

### 4. Railway Time-Series Data

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

Pre-processing notes:

- The raw railway datasets are nationwide and must be clipped to Tochigi, Utsunomiya, Haga, or the LRT corridor.
- Station records may include duplicated station names or multiple records for the same station across lines.
- Station features are cleaned by station name, dissolved when needed, and converted to station point features using centroids.

Use cases in this project:

- Locate existing railway lines and stations
- Compare LRT with existing railway networks
- Define transit access to existing rail stations
- Estimate nearest public transport access time for ZA
- Estimate connection to JR Utsunomiya station for ZB
- Define treatment and control areas around existing rail infrastructure

---

### 5. Land Price Publication Data

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

Pre-processing notes:

- Land price points are clipped to the study area.
- Each point is assigned a distance to the nearest LRT stop.
- Distance zones are created, usually `0-500m`, `500-1000m`, `1000-2000m`, and `2000m+`.
- Land price can also be spatially joined to administrative boundaries or LRT buffer areas.

Use cases in this project:

- Analyze land price differences near the LRT corridor
- Compare LRT station areas with non-station areas
- Use land price or rent proxy as the `r` variable in the Sasaki / Sato-style household utility model
- Support future hedonic pricing or Difference-in-Differences analysis if pre/post data are available

---

### 6. Road Data

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

Pre-processing notes:

- The source mesh area is broader than Utsunomiya, so it must be clipped to the target municipality or LRT corridor.
- `N13_001` should not be interpreted as the road opening year.
- Road length is recalculated after reprojection to EPSG:6678.

Use cases in this project:

- Analyze road network density
- Estimate access distance to LRT stations
- Support walking-distance proxy calculations
- Compare LRT corridors with surrounding road infrastructure
- Discuss potential reduction in car dependency or road burden

---

### 7. LRT Stop Data

| Item | Description |
|---|---|
| Expected file name | `lrt_stops.shp` |
| Coverage | Utsunomiya LRT corridor, from Utsunomiya Station East Exit toward Haga-Takanezawa Industrial Park |
| Geometry | Point |
| Source | User-created shapefile from LRT stop coordinate list or official stop information |

Required fields:

| Attribute | Description |
|---|---|
| `stop_name` | LRT stop name |
| `geometry` | LRT stop point |

Use cases in this project:

- Create 500m and 800m walking catchments
- Calculate distance from population meshes and land price points to nearest LRT stop
- Calculate LRT station catchment population
- Calculate bus-LRT and hospital-LRT connectivity
- Estimate LRT scenario improvements for ZA and ZB
- Define treatment zones in land price and cost-benefit analysis

---

### 8. Feeder Bus Stop Data, Optional

| Item | Description |
|---|---|
| Expected file name | `feeder_stops.shp` |
| Coverage | Candidate or planned feeder-bus nodes around the LRT corridor |
| Geometry | Point |
| Source | User-created or policy-scenario layer |

Required fields:

| Attribute | Description |
|---|---|
| `stop_name` | Feeder stop name, if available |
| `geometry` | Feeder stop point |

Use cases in this project:

- Represent the LRT + feeder bus scenario
- Estimate additional access improvements beyond LRT-only access
- Compare population redistribution in LRT-only and LRT + FBS scenarios
- Map feeder-bus-related accessibility benefits

---

### 9. Hospital and Clinic Location Data, Optional

| Item | Description |
|---|---|
| Expected file names | `hospital_locations.shp`, `clinic_locations.shp` |
| Coverage | Utsunomiya and surrounding municipalities, depending on input list |
| Geometry | Point |
| Source | OpenStreetMap or user-provided hospital / clinic lists converted to shapefile |

Recommended fields:

| Attribute | Description |
|---|---|
| `name` | Hospital or clinic name |
| `type` | Facility type, such as hospital or clinic |
| `geometry` | Facility point |

Use cases in this project:

- Measure access to medical facilities from LRT stops
- Count hospitals and clinics within LRT catchments
- Support the elderly-mobility and care-access component of preliminary analysis
- Create the optional hospital / clinic connectivity map

This layer is optional. The core LRT population, transportation, land price, road, and cost-benefit workflow runs without it.

---

## Preliminary Analysis Workflow

### Kiyohara public-transport isochrone workflow

For the Kiyohara industrial-area accessibility request, use:

```bash
python3 scripts/kiyohara_transit_isochrone.py --check-inputs
python3 scripts/kiyohara_transit_isochrone.py \
  --target-stop-regex "清原|工業団地" \
  --thresholds 30 60
```

The same workflow is available in `kiyohara_transit_isochrone_analysis.ipynb`.
It estimates `Z` from cumulative LRT stop-to-stop length at 20 km/h and
estimates `Y` from the attached N07 bus route line layer (`N07-11_09_GML.shp`)
at 20 km/h when present. The bus network permits additive multi-route travel
(`bus -> bus -> LRT`) and direct bus access to the destination
(`bus -> bus -> destination`) when those paths are connected in the route
network. Remaining time is used for road-network walking isochrones from
bus/LRT access nodes.

For road-network walking, the script combines all available Utsunomiya N13
road mesh shapefiles under `data/`, including `N13-24_5439.shp`,
`N13-24-5440.shp`, `N13-24-5539.shp`, and `N13-24-5540.shp` when present.
Complete shapefile sidecars must be placed under `data/`; the script reports
missing inputs before analysis.

### 1. Load Data and Standardize CRS

Load all shapefiles using GeoPandas and reproject to EPSG:6678.

```python
import geopandas as gpd

boundary = gpd.read_file("data/gadm41_JPN_2.shp")
boundary = boundary.to_crs(epsg=6678)
```

All distance-based calculations, including buffers and nearest-neighbor joins, should be performed after CRS standardization.

---

### 2. Define Study Area

The notebook supports several study area definitions:

| Study area | Description |
|---|---|
| Utsunomiya City only | Municipality-level analysis |
| Utsunomiya City + Haga Town | Recommended for LRT corridor analysis because the LRT extends toward Haga |
| LRT station buffers | 500m and 800m walking catchments |
| LRT corridor | Union of LRT buffers or route-oriented corridor |
| Feeder-bus corridor, optional | Used for LRT + feeder bus scenario |

---

### 3. Create Processed Shapefile Layers

Each raw dataset is cleaned, clipped, reprojected, and saved as a processed shapefile under:

```text
outputs/shapefiles/
```

Expected processed layers include:

```text
processed_population_mesh.shp
processed_bus_stops.shp
processed_rail_stations.shp
processed_lrt_stops.shp
lrt_500m_buffers.shp
lrt_800m_buffers.shp
processed_land_price.shp
processed_roads.shp
processed_hospitals.shp       # Optional
processed_clinics.shp         # Optional
sasaki_lrt_spatial_replication_zones.shp
```

---

### 4. LRT Walking-Catchment Population Analysis

The workflow creates 500m and 800m buffers around LRT stops and overlays them with 250m population mesh data.

Main indicators:

| Indicator | Calculation |
|---|---|
| Total population within LRT catchment | Sum of `PT00_2025` inside LRT buffer |
| Elderly population within LRT catchment | Sum of `PTC_2025` inside LRT buffer |
| Child population within LRT catchment | Sum of `PTA_2025`, if available |
| Elderly share inside catchment | `PTC_2025 / PT00_2025` |
| Catchment coverage | Catchment population divided by study-area population |

Expected table output:

```text
outputs/tables/lrt_population_catchment_summary.csv
```

Expected map output:

```text
outputs/figures/map_elderly_population_lrt_500m.png
```

---

### 5. Bus, Rail, Hospital, and Clinic Connectivity Analysis

For each LRT stop, the workflow counts nearby facilities within the selected walking catchment.

Main indicators:

| Indicator | Calculation |
|---|---|
| Nearby bus stops | Count of bus stops within 500m or 800m of each LRT stop |
| Nearby bus operators | Unique count of `P11_002` within the buffer |
| Nearby railway stations | Count of existing railway stations within the buffer |
| Nearby hospitals | Count of hospital points within the buffer, if available |
| Nearby clinics | Count of clinic points within the buffer, if available |

Expected table output:

```text
outputs/tables/lrt_bus_rail_hospital_connectivity_summary.csv
```

Expected map output:

```text
outputs/figures/map_transit_hospital_connectivity.png
```

---

### 6. Land Price Analysis Around LRT Stops

Land price points are assigned to distance zones based on the nearest LRT stop.

Default distance zones:

| Zone | Definition |
|---|---|
| `0-500m` | Direct LRT station catchment |
| `500-1000m` | Near-corridor area |
| `1000-2000m` | Outer corridor comparison area |
| `2000m+` | City or regional control area |

Main indicators:

| Indicator | Calculation |
|---|---|
| Mean land price | Mean of `L01_008` |
| Median land price | Median of `L01_008` |
| Mean year-over-year change | Mean of `L01_009` |
| Number of land price points | Count by zone |

Expected table output:

```text
outputs/tables/lrt_land_price_summary.csv
```

Expected figure outputs:

```text
outputs/figures/map_land_price_lrt_distance.png
outputs/figures/chart_land_price_by_lrt_zone.png
```

---

### 7. Road Density Analysis

Road line features are clipped to the study area and line lengths are calculated in meters.

Main indicators:

| Indicator | Calculation |
|---|---|
| Total road length | Sum of clipped road line length |
| Study area size | Area of study-area polygon |
| Road density | Road length / area |
| Road density by corridor | Same calculation within LRT buffer or corridor |

Expected table output:

```text
outputs/tables/road_density_summary.csv
```

---

## Sasaki / Sato-Style Location Choice and Cost-Benefit Model

The notebook includes a simplified replication of the population-distribution and cost-benefit framework from:

```text
Sato, T., Sasaki, T., & Chikuma, M. (2018).
Cost–Benefit Analysis of Developing a Light Rail Transit and Feeder Bus System
in Utsunomiya City Considering the Change in Population Distribution.
Asian Transport Studies, 5(1), 151–164.
```

The original paper estimates future population distribution using a household relocation model and evaluates LRT and feeder-bus scenarios through equivalent variation and cost-benefit analysis.

---

### 1. Analysis Unit

The paper uses 500m × 500m zones in the urbanization promotion area of Utsunomiya City and Haga Town. The current workflow approximates this logic by using 250m mesh population data and creating or aggregating analysis zones as needed.

The main spatial unit in the notebook is:

```text
zone_id
```

Each zone is represented by a polygon and a centroid point for nearest-distance calculations.

---

### 2. Variables ZA, ZB, ZC, ZD, and r

The location-choice utility model uses the following explanatory variables:

| Variable | Meaning | Implementation in this workflow |
|---|---|---|
| `ZA` | Required time from home to nearest railway, LRT, or bus stop | Zone centroid to nearest public transport stop, converted to walking minutes |
| `ZB` | Required time from nearest railway, LRT, or bus stop to JR Utsunomiya Station | Estimated from nearest public transport node to JR Utsunomiya |
| `ZC` | Required time from home to nearest grocery store | Optional if grocery data exist; otherwise a fallback proxy is used |
| `ZD` | Estimated maximum flood depth | Optional flood layer; otherwise a default or proxy value is used |
| `r` | Land price or rent | Estimated from land price points or nearest land price value |

Walking time follows the paper's approximation:

```text
walking_time_minutes = direct_distance_meters × 1.1666 / 80
```

where:

- `1.1666` converts straight-line distance to approximate road distance.
- `80 m/min` is the assumed walking speed.

Geometry handling note:

- Zone centroids are converted into a new GeoDataFrame whose active geometry column is named `geometry`.
- This avoids GeoPandas errors where an inactive or missing geometry column is accidentally used during `sjoin_nearest`.

---

### 3. Logit Destination Choice Model

For each household type, destination choice probability is calculated using a logit model:

```text
P_i,k = exp(theta × V_i,k) / Σ_i exp(theta × V_i,k)
```

where:

| Symbol | Meaning |
|---|---|
| `P_i,k` | Probability that household type `k` chooses zone `i` |
| `V_i,k` | Partial utility of zone `i` for household type `k` |
| `theta` | Logit scale parameter |

The workflow uses:

```text
theta = 1
```

---

### 4. Utility Function Parameters

The simplified utility function follows the structure of the Sasaki / Sato paper:

```text
V = a ln(ZA) + b ln(ZB) + c ln(ZC) + d f(ZD) + e ln(r)
```

The notebook applies safe transformations to avoid invalid values such as `ln(0)`.

Parameter values used in the workflow:

| Housing type | Age group | a | b | c | d | e | Log-likelihood |
|---|---|---:|---:|---:|---:|---:|---:|
| Owned detached house | 20s / 30s | -0.164 | -0.628 | -1.250 | -1.581 | -1.469 | -131.53 |
| Owned detached house | 40s / 50s | — | — | -0.174 | -1.434 | -1.444 | -230.12 |
| Rental apartment | 20s / 30s | -0.165 | -0.426 | -0.446 | -0.897 | -1.856 | -116.20 |
| Rental apartment | 40s / 50s | -0.006 | -0.300 | -0.515 | -0.933 | -3.467 | -82.38 |

Interpretation:

- Negative coefficients mean that longer travel time, deeper flood risk, or higher land price / rent reduce location utility.
- Missing coefficients in the paper are treated as unused for that household group in the simplified implementation.
- Because this is a preliminary replication, the model should be interpreted as a scenario-based estimate, not a full causal estimate.

---

### 5. Moving-Intention Rates and Housing-Type Transition Rates

The model applies the moving-intention rates reported in the Sasaki / Sato paper.

| Age group | Rate of respondents intending to move within five years |
|---|---:|
| 20s / 30s | 16.28% |
| 40s / 50s | 5.88% |
| 60s and above | 0.00% |

Housing-type transition rates used in the simplified workflow:

| Age group | Current housing type | Desired owned detached house | Desired rental apartment |
|---|---|---:|---:|
| 20s / 30s | Owned detached house | 0.00% | 0.00% |
| 20s / 30s | Rental apartment | 9.91% | 6.37% |
| 40s / 50s | Owned detached house | 0.00% | 0.00% |
| 40s / 50s | Rental apartment | 3.63% | 2.25% |
| 60s and above | Owned detached house | 0.00% | 0.00% |
| 60s and above | Rental apartment | 0.00% | 0.00% |

---

### 6. Residential Land / Floor Demand Parameters

The residential land or floor demand function uses the following parameters:

| Housing type | h |
|---|---:|
| Owned detached house | 0.291 |
| Rental apartment | 0.064 |

The logit parameter is:

```text
theta = 1
```

---

### 7. Scenario Definitions

The notebook compares the following scenarios:

| Scenario | Description |
|---|---|
| No LRT | Baseline transport condition using existing bus and rail access |
| LRT only | Adds LRT stops and improves access around LRT stations |
| LRT + feeder bus | Adds LRT stops and optional feeder-bus stops, improving access beyond the immediate LRT corridor |

Population change is calculated as:

```text
population_change_pct = (population_with_project - population_without_project)
                        / population_without_project × 100
```

---

### 8. Equivalent Variation and Cost-Benefit Analysis

The model estimates household location benefit using equivalent variation:

```text
EV_i,k = y × (V_with_i,k - V_without_i,k)
```

where:

| Symbol | Meaning |
|---|---|
| `EV_i,k` | Equivalent variation benefit for household type `k` in zone `i` |
| `y` | Household income |
| `V_with_i,k` | Utility with LRT or LRT + feeder bus |
| `V_without_i,k` | Utility without the project |

Zone benefit is calculated by multiplying household-level benefit by the number of households in each zone. Area-wide benefit is the sum across zones.

The original paper uses:

| Setting | Value |
|---|---:|
| Base year | 2016 |
| Discount rate | 4% |
| Analysis period | 40 years after LRT opening |
| LRT construction period assumption | 2017-2019 |
| Time preference rate | 4% per year |

Original cost-benefit results reported in the paper:

| Scenario | Benefit, million yen | Cost, million yen | Net present value, million yen | Benefit-cost ratio |
|---|---:|---:|---:|---:|
| LRT without feeder buses | 60,719.7 | 59,615.6 | 1,104.1 | 1.0185 |
| LRT with feeder buses | 69,440.0 | 63,617.6 | 5,822.4 | 1.0915 |

The current workflow also supports a latest-cost comparison by replacing the original LRT project cost with an updated cost assumption while keeping the paper's benefit values as a sensitivity check.

Expected outputs:

```text
outputs/tables/sasaki_logit_model_summary.csv
outputs/tables/cba_comparison_sasaki_latest.csv
outputs/tables/sasaki_lrt_spatial_replication_table.csv
outputs/figures/map_pop_change_lrt_only.png
outputs/figures/map_pop_change_lrt_fbs.png
outputs/figures/map_annual_benefit_lrt.png
outputs/figures/bcr_comparison_sasaki_latest.png
outputs/shapefiles/sasaki_lrt_spatial_replication_zones.shp
```

---

## Data Role Summary

| Dataset | Main analytical role |
|---|---|
| Administrative boundaries | Study area clipping, municipal aggregation, mapping |
| 250m mesh future population | Future demand estimation, elderly / child access, walking catchment population, model zones |
| Bus stop data | Existing bus access, LRT-bus connectivity, public transportation gap detection, ZA baseline |
| Railway time-series data | Existing rail network and station access, ZB baseline, rail control areas |
| LRT stop data | LRT access, catchment buffers, treatment zones, LRT scenario |
| Feeder bus stop data, optional | LRT + FBS scenario and feeder-corridor accessibility |
| Land price data | LRT distance-zone comparison, rent / price proxy `r`, future hedonic or DID analysis |
| Road data | Road network structure, road density, walking-time proxy support |
| Hospital / clinic data, optional | Medical access and elderly-care accessibility around LRT stops |

---

## Expected Final Outputs

### Figures

```text
outputs/figures/map_elderly_population_lrt_500m.png
outputs/figures/map_transit_hospital_connectivity.png
outputs/figures/map_land_price_lrt_distance.png
outputs/figures/chart_land_price_by_lrt_zone.png
outputs/figures/map_pop_change_lrt_only.png
outputs/figures/map_pop_change_lrt_fbs.png
outputs/figures/map_annual_benefit_lrt.png
outputs/figures/bcr_comparison_sasaki_latest.png
```

### Tables

```text
outputs/tables/lrt_population_catchment_summary.csv
outputs/tables/lrt_bus_rail_hospital_connectivity_summary.csv
outputs/tables/lrt_land_price_summary.csv
outputs/tables/road_density_summary.csv
outputs/tables/sasaki_logit_model_summary.csv
outputs/tables/cba_comparison_sasaki_latest.csv
outputs/tables/sasaki_lrt_spatial_replication_table.csv
```

### Processed Shapefiles

```text
outputs/shapefiles/processed_population_mesh.shp
outputs/shapefiles/processed_bus_stops.shp
outputs/shapefiles/processed_rail_stations.shp
outputs/shapefiles/processed_lrt_stops.shp
outputs/shapefiles/lrt_500m_buffers.shp
outputs/shapefiles/lrt_800m_buffers.shp
outputs/shapefiles/processed_land_price.shp
outputs/shapefiles/processed_roads.shp
outputs/shapefiles/processed_hospitals.shp
outputs/shapefiles/processed_clinics.shp
outputs/shapefiles/sasaki_lrt_spatial_replication_zones.shp
```

---

## Requirements

Recommended Python packages:

```bash
pip install geopandas pandas numpy matplotlib shapely pyproj fiona mapclassify
```

Optional packages for basemaps, network analysis, and interactive maps:

```bash
pip install contextily osmnx networkx folium
```

---

## Notes on Large Data Files

Because shapefiles and geospatial datasets can be large, the `data/` directory may be excluded from GitHub.

Recommended `.gitignore` setting:

```text
data/
outputs/
.DS_Store
.ipynb_checkpoints/
```

If geospatial files must be shared through GitHub, use **Git LFS**.

```bash
git lfs install
git lfs track "*.shp"
git lfs track "*.dbf"
git lfs track "*.shx"
git lfs track "*.prj"
git lfs track "*.cpg"
git lfs track "*.csv"
git add .gitattributes
git commit -m "Track geospatial data with Git LFS"
```

---

## Research Direction

This project supports a preliminary spatial cost-benefit and policy evaluation of the Utsunomiya LRT. The core empirical question is whether the LRT improves public transportation accessibility and produces measurable spatial benefits, especially for residents who are more dependent on public transportation, including elderly residents and households without convenient car access.

Potential final outputs include:

- LRT station catchment maps
- Population and elderly population served by LRT
- Optional medical-access maps using hospital and clinic locations
- Public transportation gap maps
- Bus-LRT and rail-LRT connectivity summaries
- Land price comparison around LRT stations
- Road density and car-dependency discussion
- Preliminary LRT-only and LRT + feeder bus population redistribution maps
- Preliminary cost-benefit discussion based on spatial indicators and Sasaki / Sato-style equivalent variation
