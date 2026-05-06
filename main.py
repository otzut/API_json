import pandas as pd
import numpy as np
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from typing import Optional

app = FastAPI(title="Mon API CSV - OData v4", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ──────────────────────────────────────────
BASE_URL = "https://apijson-production.up.railway.app"
VAL_DATE = [45292, 45382, 45473, 45565, 45657]
TRIM_RANGES = {
    1: range(VAL_DATE[0], VAL_DATE[1] + 1),
    2: range(VAL_DATE[1] + 1, VAL_DATE[2] + 1),
    3: range(VAL_DATE[2] + 1, VAL_DATE[3] + 1),
    4: range(VAL_DATE[3] + 1, VAL_DATE[4] + 1),
}

# ── Chargement CSV ───────────────────────────────────
df = pd.read_csv("Compta_2024.csv", sep=";").replace({np.nan: None})

# ── Middleware OData headers ─────────────────────────
@app.middleware("http")
async def add_odata_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["OData-Version"] = "4.0"
    return response

# ── Helpers ──────────────────────────────────────────
def build_metadata() -> str:
    type_map = {
        "int64":   "Edm.Int64",
        "float64": "Edm.Decimal",
        "object":  "Edm.String",
        "bool":    "Edm.Boolean",
    }
    first_col = df.columns[0]
    properties = "\n        ".join(
        f'<Property Name="{col}" Type="{type_map.get(str(df[col].dtype), "Edm.String")}" Nullable="true"/>'
        for col in df.columns
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="ComptaAPI" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Compta">
        <Key><PropertyRef Name="{first_col}"/></Key>
        {properties}
      </EntityType>
      <EntityContainer Name="Default">
        <EntitySet Name="Compta" EntityType="ComptaAPI.Compta"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

def filter_trim(data: pd.DataFrame, trim_str: str) -> pd.DataFrame:
    date = []
    for t in [int(v) for v in trim_str.split(",")]:
        if t in TRIM_RANGES:
            date.extend(TRIM_RANGES[t])
    return data[data["desc_017_dtfin"].isin(date)]

def filter_dept(data: pd.DataFrame, dept_str: str) -> pd.DataFrame:
    vals = [float(v) for v in dept_str.split(",")]
    return data[data["desc_011_deptagc"].isin(vals)]

def odata_response(data: pd.DataFrame) -> JSONResponse:
    return JSONResponse(
        content={
            "@odata.context": f"{BASE_URL}/odata/$metadata#Compta",
            "@odata.count": len(data),
            "value": data.to_dict(orient="records"),
        },
        headers={
            "OData-Version": "4.0",
            "Content-Type": "application/json;odata.metadata=minimal",
        }
    )

# ── Routes OData ─────────────────────────────────────
@app.get("/odata")
def odata_root():
    """Racine OData — lue en premier par Tableau/SAP"""
    return JSONResponse(
        content={
            "@odata.context": f"{BASE_URL}/odata/$metadata",
            "value": [{"name": "Compta", "kind": "EntitySet", "url": "Compta"}]
        },
        headers={"OData-Version": "4.0"}
    )

@app.get("/odata/$metadata")
def odata_metadata():
    """Schéma de données — généré dynamiquement depuis le CSV"""
    return Response(
        content=build_metadata(),
        media_type="application/xml",
        headers={"OData-Version": "4.0"}
    )

@app.get("/odata/Compta")
def odata_compta(
    dept: Optional[str] = Query(None, description="Ex: 22 ou 22,33"),
    trim: Optional[str] = Query(None, description="Ex: 1 ou 2,3 ou 1,2,3,4"),
    skip: int = Query(0, alias="$skip"),
    top:  int = Query(1000, alias="$top"),
):
    result = df.copy()

    if dept:
        result = filter_dept(result, dept)
    if trim:
        result = filter_trim(result, trim)

    result = result.iloc[skip:skip + top]
    return odata_response(result)
