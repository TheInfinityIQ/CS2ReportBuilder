from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from awpy.nav import Nav
from awpy.visibility import VisibilityChecker

M4_VERSION = "4.0-v0.1"
SPATIAL_SCHEMA_VERSION = "1.0.0-alpha1"
DEFAULT_ROUNDS = 4
DEFAULT_GRID_STEP_TICKS = 64
COMBAT_EVENT_NAMES = {
    "player_death", "player_hurt", "weapon_fire",
    "smokegrenade_detonate", "smokegrenade_expired",
    "inferno_startburn", "inferno_expire",
    "bomb_planted", "bomb_defused", "bomb_exploded",
}

PLAYER_SPATIAL_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("steamid", pa.string(), nullable=False),
    pa.field("side", pa.string()),
    pa.field("x", pa.float64()), pa.field("y", pa.float64()), pa.field("z", pa.float64()),
    pa.field("place_name_literal", pa.string()),
    pa.field("nav_area_id", pa.int64()),
    pa.field("nav_assignment_mode", pa.string()),
    pa.field("nav_assignment_distance", pa.float64()),
    pa.field("static_collision_status", pa.string(), nullable=False),
    pa.field("static_clear_enemy_count", pa.int16()),
    pa.field("static_exposed_to_enemy_count", pa.int16()),
    pa.field("nearest_enemy_distance", pa.float64()),
    pa.field("nearest_static_clear_enemy_distance", pa.float64()),
    pa.field("nearest_known_active_smoke_segment_distance", pa.float64()),
    pa.field("known_active_smoke_count", pa.int16(), nullable=False),
    pa.field("unknown_end_smoke_count", pa.int16(), nullable=False),
    pa.field("dynamic_world_uncertainty", pa.bool_(), nullable=False),
])

PAIR_SCHEMA = pa.schema([
    pa.field("demo_id", pa.string(), nullable=False),
    pa.field("tick", pa.int64(), nullable=False),
    pa.field("round", pa.int32()),
    pa.field("t_steamid", pa.string(), nullable=False),
    pa.field("ct_steamid", pa.string(), nullable=False),
    pa.field("distance_units", pa.float64()),
    pa.field("collision_evaluated", pa.bool_(), nullable=False),
    pa.field("collision_status", pa.string(), nullable=False),
    pa.field("t_to_ct_any_static_ray_clear", pa.bool_()),
    pa.field("t_to_ct_static_clear_fraction", pa.float64()),
    pa.field("t_to_ct_head_static_ray_clear", pa.bool_()),
    pa.field("ct_to_t_any_static_ray_clear", pa.bool_()),
    pa.field("ct_to_t_static_clear_fraction", pa.float64()),
    pa.field("ct_to_t_head_static_ray_clear", pa.bool_()),
    pa.field("nearest_known_active_smoke_segment_distance", pa.float64()),
    pa.field("known_active_smoke_count", pa.int16(), nullable=False),
    pa.field("unknown_end_smoke_count", pa.int16(), nullable=False),
    pa.field("dynamic_world_uncertainty", pa.bool_(), nullable=False),
    pa.field("truth_class", pa.string(), nullable=False),
])


def write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def table_from_rows(rows: list[dict], schema: pa.Schema) -> pa.Table:
    arrays=[]
    for field in schema:
        vals=[r.get(field.name) for r in rows]
        arrays.append(pa.array(vals, type=field.type, from_pandas=True))
    return pa.Table.from_arrays(arrays, schema=schema)


def write_rows(rows: list[dict], schema: pa.Schema, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    table=table_from_rows(rows, schema)
    tmp=path.with_suffix(path.suffix+".tmp")
    pq.write_table(table,tmp,compression="zstd")
    tmp.replace(path)
    return {"rows":table.num_rows,"bytes":path.stat().st_size,"sha256":sha256_file(path)}


def safe_int(v: Any) -> int | None:
    try:
        if pd.isna(v): return None
        return int(v)
    except Exception:
        return None


def safe_float(v: Any) -> float | None:
    try:
        if pd.isna(v): return None
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def side_value(v: Any) -> str | None:
    if v is None or (isinstance(v,float) and math.isnan(v)): return None
    s=str(v).upper()
    if s in {"T","CT"}: return s
    return None


def resolve_existing_path(raw: str | None) -> Path | None:
    if not raw: return None
    p=Path(raw)
    if p.exists(): return p
    # Historical registries were created on the same Windows workstation but
    # preserve an absolute user profile. Make only the LocalAppData prefix portable.
    s=str(raw).replace("/","\\")
    marker="\\AppData\\Local\\CS2Coach\\"
    idx=s.lower().find(marker.lower())
    local=os.environ.get("LOCALAPPDATA")
    if idx>=0 and local:
        q=Path(local + "\\CS2Coach\\" + s[idx+len(marker):])
        if q.exists(): return q
    return p


def profile_for_dataset(dataset: str) -> str:
    k=(dataset or "").lower()
    if k=="austinmajor_2025": return "austin_major_2025"
    if k=="starladder_2025": return "starladder_major_2025"
    if k=="iemcolognemajor2026": return "live_current_iem_proxy"
    if k in {"faceit","premier_batch1"}: return "live_current"
    return "unknown"


def point_in_poly(x: float, y: float, poly: list[tuple[float,float,float]]) -> bool:
    inside=False; n=len(poly)
    if n<3: return False
    j=n-1
    for i in range(n):
        xi,yi=poly[i][0],poly[i][1]; xj,yj=poly[j][0],poly[j][1]
        den=(yj-yi) if (yj-yi)!=0 else 1e-12
        if ((yi>y)!=(yj>y)) and (x < (xj-xi)*(y-yi)/den+xi): inside=not inside
        j=i
    return inside


def vxyz(v: Any) -> tuple[float,float,float]:
    if all(hasattr(v,k) for k in ("x","y","z")):
        return float(v.x),float(v.y),float(v.z)
    a=list(v); return float(a[0]),float(a[1]),float(a[2])


class NavLocator:
    def __init__(self, nav: Nav, cell: float=512.0):
        self.recs=[]; self.grid=defaultdict(list); self.cell=cell
        for aid,a in nav.areas.items():
            pts=[vxyz(c) for c in a.corners]
            if len(pts)<3: continue
            cx,cy,cz=vxyz(a.centroid); xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
            rec={"id":int(aid),"poly":pts,"centroid":(cx,cy,cz),"minx":min(xs),"maxx":max(xs),"miny":min(ys),"maxy":max(ys)}
            idx=len(self.recs); self.recs.append(rec)
            for gx in range(math.floor(rec["minx"]/cell),math.floor(rec["maxx"]/cell)+1):
                for gy in range(math.floor(rec["miny"]/cell),math.floor(rec["maxy"]/cell)+1):
                    self.grid[(gx,gy)].append(idx)

    def locate(self,p: tuple[float,float,float]):
        x,y,z=p; gx=math.floor(x/self.cell); gy=math.floor(y/self.cell)
        cand=set()
        for dx in (-1,0,1):
            for dy in (-1,0,1): cand.update(self.grid.get((gx+dx,gy+dy),[]))
        if not cand: cand=range(len(self.recs))
        containing=[]
        for i in cand:
            r=self.recs[i]
            if r["minx"]-2<=x<=r["maxx"]+2 and r["miny"]-2<=y<=r["maxy"]+2 and point_in_poly(x,y,r["poly"]):
                containing.append(r)
        if containing:
            r=min(containing,key=lambda q:abs(q["centroid"][2]-z))
            return r["id"],"contains_xy",abs(r["centroid"][2]-z)
        recs=[self.recs[i] for i in cand]
        if not recs: return None,"unavailable",None
        r=min(recs,key=lambda q:(q["centroid"][0]-x)**2+(q["centroid"][1]-y)**2+(q["centroid"][2]-z)**2)
        return r["id"],"nearest_centroid",math.dist(r["centroid"],p)


def static_clear(checker: VisibilityChecker, src: tuple[float,float,float], dst: tuple[float,float,float]) -> dict:
    # M3 canonical state does not yet preserve crouch amount. This pilot therefore
    # uses the already-calibrated standing geometry pattern only and labels it explicitly.
    ax,ay,az=src; bx,by,bz=dst
    dx=bx-ax; dy=by-ay; L=math.hypot(dx,dy)
    px,py=(1.0,0.0) if L<1e-9 else (-dy/L,dx/L)
    eye=(ax,ay,az+64.0)
    heights=[64.0,53.0,41.0,28.0]
    vals=[]
    for h in heights:
        for off in (-8.0,0.0,8.0):
            vals.append(bool(checker.is_visible(eye,(bx+px*off,by+py*off,bz+h))))
    head=bool(checker.is_visible(eye,(bx,by,bz+64.0)))
    return {"any":any(vals),"fraction":sum(vals)/len(vals),"head":head,"rays":len(vals)+1}


def point_segment_distance(p: tuple[float,float,float], a: tuple[float,float,float], b: tuple[float,float,float]) -> float:
    px,py,pz=p; ax,ay,az=a; bx,by,bz=b
    ab=(bx-ax,by-ay,bz-az); ap=(px-ax,py-ay,pz-az)
    den=sum(v*v for v in ab)
    if den<=1e-12: return math.dist(p,a)
    t=max(0.0,min(1.0,sum(ap[i]*ab[i] for i in range(3))/den))
    q=(ax+t*ab[0],ay+t*ab[1],az+t*ab[2])
    return math.dist(p,q)


def smoke_state_at_tick(ui: pd.DataFrame, tick: int, rd: int | None):
    if ui.empty: return [],0
    s=ui[ui["utility_type"].astype(str)=="smoke"]
    if rd is not None and "round" in s.columns:
        rr=pd.to_numeric(s["round"],errors="coerce")
        s=s[(rr.isna()) | (rr==rd)]
    known=[]; unknown=0
    for _,r in s.iterrows():
        st=safe_int(r.get("start_tick")); en=safe_int(r.get("end_tick")); end_known=bool(r.get("end_known")) if not pd.isna(r.get("end_known")) else False
        if st is None or tick<st: continue
        if end_known and en is not None:
            if tick<=en:
                xyz=tuple(safe_float(r.get(k)) for k in ("x","y","z"))
                if None not in xyz: known.append(xyz)
        else:
            unknown+=1
    return known,unknown


def source_event_ticks(cmanifest: dict, round_bounds: list[tuple[int,int,int]], fallback_player: pd.DataFrame) -> set[int]:
    evidence_path=Path(str((cmanifest.get("source_evidence") or {}).get("path") or ""))
    ep=evidence_path/"events.parquet"
    if not ep.exists():
        return set(int(x) for x in fallback_player.loc[fallback_player["sample_event_tick"].fillna(False),"tick"].tolist())
    try:
        ev=pq.read_table(ep,columns=["event_name","tick","segment_round"]).to_pandas()
    except Exception:
        ev=pq.read_table(ep).to_pandas()
    if "event_name" not in ev or "tick" not in ev: return set()
    ev=ev[ev["event_name"].astype(str).isin(COMBAT_EVENT_NAMES)]
    out=set()
    for _,r in ev.iterrows():
        t=safe_int(r.get("tick")); rd=safe_int(r.get("segment_round"))
        if t is None: continue
        if any(a<=t<=b and (rd is None or rd==rno) for rno,a,b in round_bounds): out.add(t)
    return out


def choose_ticks(ps: pd.DataFrame, rs: pd.DataFrame, cmanifest: dict, rounds_n: int, step_ticks: int):
    rsort=rs.sort_values("round").head(rounds_n)
    bounds=[]
    for _,r in rsort.iterrows():
        rd=safe_int(r.get("round")); a=safe_int(r.get("freeze_end_tick")) or safe_int(r.get("start_tick")); b=safe_int(r.get("end_tick"))
        if rd is not None and a is not None and b is not None and b>=a: bounds.append((rd,a,b))
    ticks=set()
    # Regular ~1 Hz grid, snapped to existing canonical observations.
    uniq=sorted(set(int(x) for x in ps["tick"].tolist()))
    for rd,a,b in bounds:
        inr=[t for t in uniq if a<=t<=b]
        if not inr: continue
        last=None
        for t in inr:
            if last is None or t-last>=step_ticks:
                ticks.add(t); last=t
        ticks.add(inr[-1])
    ticks |= source_event_ticks(cmanifest,bounds,ps)
    return sorted(ticks),bounds


def discover_canonical(output_folder: Path) -> list[Path]:
    parent=output_folder.resolve().parent
    root=parent/"Stage3_M31"/"canonical"
    if not root.exists():
        root=parent/"Stage3_M3"/"canonical"
    if not root.exists(): return []
    return sorted([p for p in root.iterdir() if p.is_dir() and (p/"manifest.json").exists()])


def process_demo(cdir: Path, registry: dict, output_root: Path, checker_cache: dict, nav_cache: dict, rounds_n: int, step_ticks: int) -> dict:
    t0=time.perf_counter(); cm=read_json(cdir/"manifest.json")
    demo_id=str(cm.get("demo_id") or cdir.name); dataset=str(cm.get("dataset") or "unknown"); map_name=str(cm.get("map_name") or "unknown")
    profile=profile_for_dataset(dataset); key=f"{profile}::{map_name}"; entry=(registry.get("profiles") or {}).get(key)
    res={"demo_id":demo_id,"dataset":dataset,"map_name":map_name,"profile":profile,"registry_key":key,"success":False,"errors":[],"warnings":[],"timings":{}}
    out=output_root/"spatial"/demo_id; tmp=output_root/"spatial"/f".{demo_id}.tmp"; shutil.rmtree(tmp,ignore_errors=True); tmp.mkdir(parents=True,exist_ok=True)
    try:
        p=time.perf_counter(); ps=pq.read_table(cdir/"player_state.parquet").to_pandas(); rs=pq.read_table(cdir/"round_state.parquet").to_pandas(); ui=pq.read_table(cdir/"utility_intervals.parquet").to_pandas(); res["timings"]["read_canonical_s"]=time.perf_counter()-p
        ticks,bounds=choose_ticks(ps,rs,cm,rounds_n,step_ticks)
        ps=ps[ps["tick"].isin(ticks)].copy(); ps=ps[ps["is_alive"].fillna(False)].copy()
        if entry is None:
            collision_status="registry_missing"; tri=None; nav_status="registry_missing"; locator=None; checker=None
        else:
            tri=resolve_existing_path(entry.get("tri_path")); navp=resolve_existing_path(entry.get("nav_path"))
            if entry.get("known_quarantine") or (entry.get("exposure_ready") is False):
                collision_status="quarantined" if entry.get("known_quarantine") else ("deferred" if entry.get("known_deferred") else "not_ready")
                checker=None
            elif tri is None or not tri.exists():
                collision_status="asset_missing"; checker=None
            else:
                collision_status="ready"
                ckey=str(tri)
                if ckey not in checker_cache: checker_cache[ckey]=VisibilityChecker(path=tri)
                checker=checker_cache[ckey]
            if entry.get("nav_backend_ready") and navp is not None and navp.exists():
                try:
                    nkey=str(navp)
                    if nkey not in nav_cache: nav_cache[nkey]=Nav.from_path(navp)
                    locator=NavLocator(nav_cache[nkey]); nav_status="ready"
                except Exception as exc:
                    locator=None; nav_status=f"load_error:{type(exc).__name__}"
            else:
                locator=None; nav_status="backend_unavailable" if entry.get("nav_backend_ready") is False else "asset_missing"
        p=time.perf_counter(); player_rows=[]; pair_rows=[]; ray_count=0; pair_count=0; collision_pairs=0; nav_assigned=0; nav_fallback=0; smoke_known_tick_count=0; smoke_unknown_tick_count=0
        for tick,g in ps.groupby("tick",sort=True):
            tick=int(tick); players=[]
            for _,r in g.iterrows():
                x,y,z=(safe_float(r.get("X")),safe_float(r.get("Y")),safe_float(r.get("Z")))
                sid=str(r.get("steamid")) if not pd.isna(r.get("steamid")) else None; side=side_value(r.get("side")); rd=safe_int(r.get("round"))
                if sid is None or side not in {"T","CT"} or None in (x,y,z): continue
                nav_id=nav_dist=None; nav_mode=nav_status
                if locator is not None:
                    nav_id,nav_mode,nav_dist=locator.locate((x,y,z)); nav_assigned+=1
                    if nav_mode=="nearest_centroid": nav_fallback+=1
                players.append({"steamid":sid,"side":side,"round":rd,"pos":(x,y,z),"row":r,"nav_id":nav_id,"nav_mode":nav_mode,"nav_dist":nav_dist})
            if not players: continue
            rd=next((p["round"] for p in players if p["round"] is not None),None)
            smokes,unknown_smokes=smoke_state_at_tick(ui,tick,rd)
            if smokes: smoke_known_tick_count+=1
            if unknown_smokes: smoke_unknown_tick_count+=1
            accum={p["steamid"]:{"clear":0,"exposed":0,"dist":[],"clear_dist":[],"smoke_dist":[]} for p in players}
            ts=[p for p in players if p["side"]=="T"]; cts=[p for p in players if p["side"]=="CT"]
            for a in ts:
                for b in cts:
                    pair_count+=1; d=math.dist(a["pos"],b["pos"]); accum[a["steamid"]]["dist"].append(d); accum[b["steamid"]]["dist"].append(d)
                    smoke_d=min((point_segment_distance(s,a["pos"],b["pos"]) for s in smokes),default=None)
                    if smoke_d is not None:
                        accum[a["steamid"]]["smoke_dist"].append(smoke_d); accum[b["steamid"]]["smoke_dist"].append(smoke_d)
                    ab=ba=None
                    if checker is not None:
                        ab=static_clear(checker,a["pos"],b["pos"]); ba=static_clear(checker,b["pos"],a["pos"]); collision_pairs+=1; ray_count+=ab["rays"]+ba["rays"]
                        if ab["any"]: accum[a["steamid"]]["clear"]+=1; accum[a["steamid"]]["clear_dist"].append(d); accum[b["steamid"]]["exposed"]+=1
                        if ba["any"]: accum[b["steamid"]]["clear"]+=1; accum[b["steamid"]]["clear_dist"].append(d); accum[a["steamid"]]["exposed"]+=1
                    pair_rows.append({
                        "demo_id":demo_id,"tick":tick,"round":rd,"t_steamid":a["steamid"],"ct_steamid":b["steamid"],"distance_units":d,
                        "collision_evaluated":checker is not None,"collision_status":collision_status,
                        "t_to_ct_any_static_ray_clear":None if ab is None else ab["any"],"t_to_ct_static_clear_fraction":None if ab is None else ab["fraction"],"t_to_ct_head_static_ray_clear":None if ab is None else ab["head"],
                        "ct_to_t_any_static_ray_clear":None if ba is None else ba["any"],"ct_to_t_static_clear_fraction":None if ba is None else ba["fraction"],"ct_to_t_head_static_ray_clear":None if ba is None else ba["head"],
                        "nearest_known_active_smoke_segment_distance":smoke_d,"known_active_smoke_count":len(smokes),"unknown_end_smoke_count":unknown_smokes,
                        "dynamic_world_uncertainty":True,
                        "truth_class":"deterministic_static_geometry_relation" if checker is not None else "spatial_relation_unavailable",
                    })
            for p0 in players:
                a=accum[p0["steamid"]]; r=p0["row"]
                player_rows.append({
                    "demo_id":demo_id,"tick":tick,"round":p0["round"],"steamid":p0["steamid"],"side":p0["side"],"x":p0["pos"][0],"y":p0["pos"][1],"z":p0["pos"][2],
                    "place_name_literal":None if pd.isna(r.get("last_place_name")) else str(r.get("last_place_name")),"nav_area_id":p0["nav_id"],"nav_assignment_mode":p0["nav_mode"],"nav_assignment_distance":p0["nav_dist"],
                    "static_collision_status":collision_status,"static_clear_enemy_count":a["clear"] if checker is not None else None,"static_exposed_to_enemy_count":a["exposed"] if checker is not None else None,
                    "nearest_enemy_distance":min(a["dist"]) if a["dist"] else None,"nearest_static_clear_enemy_distance":min(a["clear_dist"]) if a["clear_dist"] else None,
                    "nearest_known_active_smoke_segment_distance":min(a["smoke_dist"]) if a["smoke_dist"] else None,"known_active_smoke_count":len(smokes),"unknown_end_smoke_count":unknown_smokes,"dynamic_world_uncertainty":True,
                })
        res["timings"]["spatial_compute_s"]=time.perf_counter()-p
        p=time.perf_counter(); outputs={}
        outputs["player_spatial_samples"]=write_rows(player_rows,PLAYER_SPATIAL_SCHEMA,tmp/"player_spatial_samples.parquet")
        outputs["pair_spatial_relations"]=write_rows(pair_rows,PAIR_SCHEMA,tmp/"pair_spatial_relations.parquet")
        manifest={
            "m4_version":M4_VERSION,"spatial_schema_version":SPATIAL_SCHEMA_VERSION,"demo_id":demo_id,"map_name":map_name,"dataset":dataset,"source_family":cm.get("source_family"),"segmented_hint":bool(cm.get("segmented_hint")),
            "source_canonical":{"path":str(cdir),"canonical_schema_version":cm.get("canonical_schema_version")},
            "geometry_profile":{"profile":profile,"registry_key":key,"registry_entry":entry,"resolved_tri_path":str(tri) if tri else None,"collision_status":collision_status,"nav_status":nav_status},
            "sampling":{"rounds_requested":rounds_n,"round_bounds":bounds,"grid_step_ticks":step_ticks,"sample_tick_count":len(ticks),"policy":"first live rounds; ~1 Hz canonical grid plus combat/objective/smoke event ticks"},
            "model_semantics":{
                "static_collision":"AWPy VisibilityChecker over versioned .tri. A clear ray means static collision did not block that ray; it does NOT mean a player saw/was aware of the target.",
                "body_sampling":"Pilot uses fixed standing eye/body offsets because M3 canonical state does not yet preserve crouch amount. Results are labeled static geometry relations, not final hitbox truth.",
                "smoke":"No smoke-occlusion boolean is asserted. Sidecar reports distance from the player-pair segment to centers of event-paired, known-active smoke intervals; unpaired smoke ends remain explicit uncertainty.",
                "dynamic_world":"Doors, breakables, players, dropped items and other dynamic props are not modeled by the static .tri sensor. dynamic_world_uncertainty is therefore true.",
                "nav":"NAV area assignment is emitted only when the versioned registry marks the NAV backend ready and loading succeeds. last_place_name remains separate literal parser evidence.",
            },
            "counts":{"player_rows":len(player_rows),"pair_rows":len(pair_rows),"collision_pair_evaluations":collision_pairs,"estimated_visibility_rays":ray_count,"nav_assignments":nav_assigned,"nav_nearest_centroid_fallbacks":nav_fallback,"ticks_with_known_active_smoke":smoke_known_tick_count,"ticks_with_unpaired_smoke_uncertainty":smoke_unknown_tick_count},
            "outputs":outputs,"awpy_used_for_spatial_only":True,"demo_reparsed":False,"coaching_generated":False,"candidate_detection":False,
        }
        write_json(manifest,tmp/"manifest.json"); res["timings"]["write_s"]=time.perf_counter()-p
        # Gates respect quarantine/defer semantics instead of treating unavailable sensors as false.
        pair_gate=len(pair_rows)>0 and len(player_rows)>0
        collision_gate=(collision_pairs>0) if collision_status=="ready" else (collision_pairs==0)
        nav_gate=(nav_assigned>0) if nav_status=="ready" else True
        res["gates"]={"rows_nonzero":pair_gate,"collision_policy_respected":collision_gate,"nav_policy_respected":nav_gate}
        if not all(res["gates"].values()): raise RuntimeError(f"M4 gates failed: {res['gates']}")
        if out.exists(): shutil.rmtree(out)
        tmp.replace(out)
        res.update({"success":True,"collision_status":collision_status,"nav_status":nav_status,"sample_tick_count":len(ticks),"round_bounds":bounds,"counts":manifest["counts"],"output_dir":str(out)})
    except Exception as exc:
        res["errors"].append(f"{type(exc).__name__}: {exc}"); res["traceback"]=traceback.format_exc(); shutil.rmtree(tmp,ignore_errors=True)
    res["wall_seconds"]=time.perf_counter()-t0
    return res


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--input-folder",required=True)
    ap.add_argument("--output-folder",required=True)
    ap.add_argument("--registry",required=True)
    ap.add_argument("--rounds",type=int,default=DEFAULT_ROUNDS)
    ap.add_argument("--grid-step-ticks",type=int,default=DEFAULT_GRID_STEP_TICKS)
    args=ap.parse_args()
    started=time.perf_counter(); output=Path(args.output_folder); output.mkdir(parents=True,exist_ok=True)
    registry=read_json(Path(args.registry)); cdirs=discover_canonical(output)
    report={"m4_version":M4_VERSION,"spatial_schema_version":SPATIAL_SCHEMA_VERSION,"generated_at_local":time.strftime("%Y-%m-%d %H:%M:%S"),"input_folder":args.input_folder,"output_folder":str(output),"registry":str(Path(args.registry).resolve()),"discovered_canonical_demos":len(cdirs),"selected_count":len(cdirs),"results":[]}
    checker_cache={}; nav_cache={}
    for cdir in cdirs:
        report["results"].append(process_demo(cdir,registry,output,checker_cache,nav_cache,args.rounds,args.grid_step_ticks))
    success=[r for r in report["results"] if r.get("success")]; fail=[r for r in report["results"] if not r.get("success")]
    report["success_count"]=len(success); report["failure_count"]=len(fail)
    report["segmented_source_included"]=any(read_json(Path(r["output_dir"])/"manifest.json").get("segmented_hint") for r in success if r.get("output_dir"))
    report["collision_status_counts"]={k:sum(r.get("collision_status")==k for r in success) for k in sorted({r.get("collision_status") for r in success if r.get("collision_status")})}
    report["nav_status_counts"]={k:sum(r.get("nav_status")==k for r in success) for k in sorted({r.get("nav_status") for r in success if r.get("nav_status")})}
    report["total_collision_pair_evaluations"]=sum((r.get("counts") or {}).get("collision_pair_evaluations",0) for r in success)
    report["total_visibility_rays"]=sum((r.get("counts") or {}).get("estimated_visibility_rays",0) for r in success)
    report["wall_seconds"]=time.perf_counter()-started
    pass_gate=(len(cdirs)>=6 and len(fail)==0 and report["segmented_source_included"] and report["total_collision_pair_evaluations"]>0)
    report["decision"]="M4_PASS: historical-profile-aware spatial sidecar integrated without demo reparse; quarantine/NAV/UNKNOWN policies preserved. Proceed to deterministic relationship/state-transition layer." if pass_gate else "M4_FAIL: spatial sidecar promotion gates not met."
    report["next_stage"]="M5 deterministic relationships and neutral state transitions; no coaching semantics." if pass_gate else "Repair M4 only; do not rerun upstream decode/canonical reconstruction."
    write_json(report,output/"M4_report.json")
    print(json.dumps({"decision":report["decision"],"success":f"{len(success)}/{len(cdirs)}","wall_seconds":report["wall_seconds"],"visibility_rays":report["total_visibility_rays"]},indent=2))
    return 0 if pass_gate else 2

if __name__=="__main__":
    raise SystemExit(main())
