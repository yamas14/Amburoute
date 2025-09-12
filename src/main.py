from routing.mapbox_router import MapboxRouter
from hospital.hospital_manager import HospitalManager, Hospital
from typing import List, Tuple, Dict
import folium
import polyline
import requests
from config import MAPBOX_ACCESS_TOKEN, REALTIME_BEDS_API_URL, HOSPITAL_NAME_TO_ID, AUTO_DISCOVER_HOSPITAL_IDS
import random
import time
import argparse
from datetime import datetime

class EmergencyRoutingSystem:
    def __init__(self):
        # Initialize Mapbox router with real-time traffic profile
        self.router = MapboxRouter(access_token=MAPBOX_ACCESS_TOKEN)
        self.hospital_manager = HospitalManager()
        self.api_base = REALTIME_BEDS_API_URL
        self.name_to_id = HOSPITAL_NAME_TO_ID or {}
        # Cache of most recent bed counts from API
        self.current_beds: Dict[str, Dict[str, int]] = {}
        # Cache of metadata (e.g., last_updated and id) per hospital name
        self.current_meta: Dict[str, Dict[str, str]] = {}
        # Default weights (normalized later if overridden)
        self.time_weight = 0.5
        self.beds_weight = 0.5

    def set_weights(self, time_weight: float, beds_weight: float):
        tw = max(0.0, float(time_weight))
        bw = max(0.0, float(beds_weight))
        if tw == 0 and bw == 0:
            tw = 1.0
            bw = 0.0
        total = tw + bw
        self.time_weight = tw / total
        self.beds_weight = bw / total

    def auto_discover_hospital_ids(self, max_probe_id: int = 200):
        """Probe the API to discover hospital IDs by name and merge into mapping.
        Will not overwrite existing explicit mappings.
        """
        if not self.api_base:
            return
        discovered = {}
        base = self.api_base.rstrip('/')
        for hid in range(1, max_probe_id + 1):
            try:
                resp = requests.get(f"{base}/api/beds/current/{hid}", timeout=3)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                name = data.get('hospital_name')
                if name:
                    discovered[name] = hid
            except Exception:
                continue
        # Merge without overwriting existing entries
        for name, hid in discovered.items():
            if name not in self.name_to_id:
                self.name_to_id[name] = hid
        if discovered:
            print(f"Auto-discovered {len(discovered)} hospital IDs from API")

    def bootstrap_hospital_ids_from_api(self):
        """Fetch /hospitals/ list from API and map name -> id for quicker, reliable mapping."""
        if not self.api_base:
            return
        try:
            resp = requests.get(f"{self.api_base.rstrip('/')}/hospitals/", timeout=5)
            resp.raise_for_status()
            items = resp.json()
            added = 0
            for h in items:
                name = h.get('name')
                hid = h.get('id')
                if name and hid and name not in self.name_to_id:
                    self.name_to_id[name] = hid
                    added += 1
            if added:
                print(f"Bootstrapped {added} hospital IDs from /hospitals endpoint")
        except Exception as e:
            print(f"Warning: failed to bootstrap hospital IDs: {e}")

    def ensure_backend_seeded(self):
        """Ensure the backend has the same hospital list as our CSV. If /hospitals/ is empty,
        POST each hospital from HospitalManager to /hospitals/ so real-time bed APIs operate
        on the exact same dataset used for routing.
        """
        if not self.api_base:
            return
        base = self.api_base.rstrip('/')
        try:
            resp = requests.get(f"{base}/hospitals/", timeout=5)
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            print(f"Warning: could not query backend hospitals: {e}")
            return

        if items:
            return  # already seeded

        # Seed from local manager list
        added = 0
        for h in self.hospital_manager.hospitals:
            payload = {
                "name": h.name,
                "latitude": h.location[0],
                "longitude": h.location[1],
                "address": None,
                "contact_number": None,
                "total_beds": int(max(0, h.available_beds)),
                "available_beds": int(max(0, h.available_beds)),
                "total_icu_beds": int(max(0, round(h.available_beds * 0.2))),
                "available_icu_beds": int(max(0, round(h.available_beds * 0.2))),
                "specialties": []
            }
            try:
                r = requests.post(f"{base}/hospitals/", json=payload, timeout=5)
                r.raise_for_status()
                added += 1
            except Exception as e:
                print(f"Warning: failed to seed hospital '{h.name}': {e}")
        if added:
            print(f"Seeded backend with {added} hospitals from CSV")

    def refresh_beds_from_api(self):
        """Refresh available_beds for known hospitals from real-time API if configured."""
        if not self.api_base or not self.name_to_id:
            # Attempt auto-discovery if enabled
            if self.api_base and AUTO_DISCOVER_HOSPITAL_IDS:
                # Prefer bootstrap via /hospitals, then probe as fallback
                self.bootstrap_hospital_ids_from_api()
                if not self.name_to_id:
                    self.auto_discover_hospital_ids()
            else:
                return
        for h in self.hospital_manager.hospitals:
            hid = self.name_to_id.get(h.name)
            if not hid:
                # Try to discover missing mapping on demand
                if AUTO_DISCOVER_HOSPITAL_IDS:
                    self.bootstrap_hospital_ids_from_api()
                    if h.name not in self.name_to_id:
                        self.auto_discover_hospital_ids()
                    hid = self.name_to_id.get(h.name)
                
                continue
            try:
                resp = requests.get(f"{self.api_base.rstrip('/')}/api/beds/current/{hid}", timeout=5)
                resp.raise_for_status()
                data = resp.json()
                # Update general beds on model for backward-compat visuals
                gen_avail = int(data.get('general_beds', {}).get('available', h.available_beds))
                icu_avail = int(data.get('icu_beds', {}).get('available', 0))
                h.available_beds = gen_avail
                # Store both general and ICU in cache for scoring
                self.current_beds[h.name] = {"general": gen_avail, "icu": icu_avail}
                # Store metadata for display
                self.current_meta[h.name] = {
                    "id": str(hid),
                    "last_updated": data.get('last_updated') or ''
                }
            except Exception as e:
                print(f"Warning: failed to refresh beds for {h.name}: {e}")
    
    def build_route_data(self, origin: Tuple[float, float], destination: Tuple[float, float]) -> Dict:
        """Query Mapbox for traffic and baseline, return normalized route dict."""
        raw = self.router.get_route(origin, destination)
        if not raw.get('routes'):
            raise ValueError("No routes found")
        route0 = raw['routes'][0]
        distance = route0['distance']
        duration = route0['duration']
        legs = route0.get('legs', [])
        geometry = route0.get('geometry', {})
        annotations = (legs[0].get('annotation', {}) if legs else {})
        congestion = annotations.get('congestion', [])
        seg_durations = annotations.get('duration', [])  # seconds per segment
        seg_distances = annotations.get('distance', [])  # meters per segment
        try:
            raw_baseline = self.router.get_route(origin, destination, profile="driving")
            baseline_duration = raw_baseline['routes'][0]['duration'] if raw_baseline.get('routes') else None
        except Exception:
            baseline_duration = None

        coordinates_lonlat = geometry.get('coordinates', [])
        coordinates_latlon = [(latlon[1], latlon[0]) for latlon in coordinates_lonlat]
        route_data = {
            'overview_polyline': {'points': coordinates_latlon},
            'legs': [{
                'duration': {'text': f"{int(duration/60)} mins", 'value': duration},
                'distance': {'text': f"{distance/1000:.1f} km", 'value': distance},
                'steps': legs[0].get('steps', []) if legs else [],
                'traffic_delay': 0
            }],
            'congestion': congestion,
            'segments': [
                {
                    'congestion': (congestion[i] if i < len(congestion) else None),
                    'duration_s': (seg_durations[i] if i < len(seg_durations) else None),
                    'distance_m': (seg_distances[i] if i < len(seg_distances) else None)
                }
                for i in range(max(len(coordinates_latlon) - 1, 0))
            ],
            'traffic_info': {
                'profile': 'driving-traffic',
                'duration_seconds': duration,
                'baseline_duration_seconds': baseline_duration
            }
        }
        return route_data

    def score_hospital(self, hospital: Hospital, route_data: Dict, need_icu: bool) -> float:
        """Compute a combined score using time and live bed availability.
        Uses ICU beds if need_icu is True; otherwise general beds. Balances time and beds 50/50
        to make bed changes impactful in selection.
        """
        total_time = route_data['legs'][0]['duration']['value']  # seconds
        # Normalize time to minutes to keep scale similar to bed score
        time_minutes = total_time / 60.0
        time_score = time_minutes * self.time_weight

        beds = self.current_beds.get(hospital.name) or {"general": hospital.available_beds, "icu": 0}
        avail = beds["icu"] if need_icu else beds["general"]
        # Inverse proportional score: more beds -> lower score. Cap denominator to avoid division spikes.
        bed_score = (1000.0 / max(1, avail)) * self.beds_weight
        return time_score + bed_score

    def get_routes_for_hospitals(self, ambulance_location: Tuple[float, float], need_icu: bool, min_beds: int):
        available_hospitals = self.hospital_manager.get_available_hospitals(min_beds=min_beds, need_icu=need_icu)
        if not available_hospitals:
            raise ValueError("No hospitals with required resources available")
        results = []
        for hospital in available_hospitals:
            try:
                rd = self.build_route_data(ambulance_location, hospital.location)
                score = self.score_hospital(hospital, rd, need_icu)
                results.append((hospital, rd, score))
            except Exception as e:
                print(f"Error calculating route to {hospital.name}: {e}")
        if not results:
            raise ValueError("Could not find a valid route to any hospital")
        # Sort by score ascending (best first)
        results.sort(key=lambda x: x[2])
        return results
    
    def visualize_route(self, route: Dict, hospital: Hospital, ambulance_location: Tuple[float, float]):
        """Visualize the route with ambulance position and green corridor"""
        # Handle simulation route format
        if isinstance(route['overview_polyline']['points'], list):
            coordinates = route['overview_polyline']['points']
        else:
            coordinates = polyline.decode(route['overview_polyline']['points'])
        
        # Create map centered between ambulance and hospital
        center_lat = (ambulance_location[0] + hospital.location[0]) / 2
        center_lng = (ambulance_location[1] + hospital.location[1]) / 2
        m = folium.Map(location=(center_lat, center_lng), zoom_start=12)
        
        # Add all hospitals to the map (removed min_beds filter)
        for h in self.hospital_manager.hospitals:  # Access all hospitals directly
            color = 'red' if h == hospital else 'orange'
            folium.Marker(
                h.location,
                popup=f"""
                Hospital: {h.name}
                Available Beds: {h.available_beds}
                ICU Available: {'Yes' if h.has_icu else 'No'}
                Selected: {'Yes' if h == hospital else 'No'}
                """,
                icon=folium.Icon(color=color, icon='info-sign')
            ).add_to(m)

        # Add ambulance marker
        folium.Marker(
            ambulance_location,
            popup="Ambulance Current Position",
            icon=folium.Icon(color='green', icon='ambulance', prefix='fa')
        ).add_to(m)
        
        # Add hospital marker
        folium.Marker(
            hospital.location,
            popup=f"Hospital: {hospital.name}\nAvailable Beds: {hospital.available_beds}",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
        
        # Add intersections (replacing traffic signals)
        if 'steps' in route['legs'][0]:
            for step in route['legs'][0]['steps']:
                if 'intersections' in step:
                    for intersection in step['intersections']:
                        folium.CircleMarker(
                            location=(intersection['location'][1], intersection['location'][0]),
                            radius=5,
                            color='yellow',
                            fill=True,
                            popup=f"Intersection - {step.get('distance', 0)}m"
                        ).add_to(m)
        
        # Add route colored by congestion if available
        congestion = route.get('congestion')
        if congestion and len(congestion) == max(0, len(coordinates)-1):
            def cong_color(c):
                if c in ("low", "lowCongestion", "low-medium"):
                    return 'green'
                if c in ("moderate", "medium", "moderateCongestion"):
                    return 'orange'
                if c in ("heavy", "severe", "heavyCongestion"):
                    return 'red'
                return 'gray'
            seg_infos = route.get('segments', [])
            for i in range(len(coordinates)-1):
                seg = [coordinates[i], coordinates[i+1]]
                info = seg_infos[i] if i < len(seg_infos) else {}
                cong_val = info.get('congestion', congestion[i] if i < len(congestion) else None)
                dur_s = info.get('duration_s')
                dist_m = info.get('distance_m')
                tooltip_txt = f"{cong_val or 'unknown'}"
                if dist_m is not None:
                    tooltip_txt += f" • {dist_m:.0f} m"
                if dur_s is not None:
                    tooltip_txt += f" • {dur_s:.0f} s"
                folium.PolyLine(
                    seg,
                    weight=6,
                    color=cong_color(congestion[i]),
                    opacity=0.9,
                    tooltip=tooltip_txt
                ).add_to(m)
        else:
            # Fallback: single green line
            folium.PolyLine(
                coordinates,
                weight=4,
                color='green',
                opacity=0.8
            ).add_to(m)

        # Add legend for congestion colors
        legend_html = '''
        <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999; background: white; padding: 10px; border: 2px solid #444; border-radius: 6px;">
            <b>Traffic</b><br>
            <span style="display:inline-block;width:18px;height:8px;background:green;margin-right:6px;"></span>Low<br>
            <span style="display:inline-block;width:18px;height:8px;background:orange;margin-right:6px;"></span>Moderate<br>
            <span style="display:inline-block;width:18px;height:8px;background:red;margin-right:6px;"></span>Heavy<br>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
        
        return m

    def visualize_all_routes(self, routes: List[Tuple[Hospital, Dict, float]], ambulance_location: Tuple[float, float]):
        """Visualize all routes: best in green, others in red, with popups showing metrics."""
        best_hospital, best_route, best_score = routes[0]
        # Center map between ambulance and best hospital
        center_lat = (ambulance_location[0] + best_hospital.location[0]) / 2
        center_lng = (ambulance_location[1] + best_hospital.location[1]) / 2
        m = folium.Map(location=(center_lat, center_lng), zoom_start=12)

        # Markers for all hospitals
        for (h, rd, sc) in routes:
            color = 'red' if h != best_hospital else 'green'
            ti = rd.get('traffic_info', {})
            popup_txt = f"""
            Hospital: {h.name}
            Beds: {h.available_beds}
            Duration (traffic): {rd['legs'][0]['duration']['text']}
            Baseline: {int((ti.get('baseline_duration_seconds') or 0)/60)} mins
            Score: {sc:.0f}
            Selected: {'Yes' if h == best_hospital else 'No'}
            """
            folium.Marker(
                h.location,
                popup=popup_txt,
                icon=folium.Icon(color=color, icon='info-sign')
            ).add_to(m)

        # Ambulance marker
        folium.Marker(
            ambulance_location,
            popup="Ambulance Current Position",
            icon=folium.Icon(color='blue', icon='ambulance', prefix='fa')
        ).add_to(m)

        # Draw non-selected routes in red
        for (h, rd, sc) in routes[1:]:
            coords = rd['overview_polyline']['points'] if isinstance(rd['overview_polyline']['points'], list) else polyline.decode(rd['overview_polyline']['points'])
            folium.PolyLine(coords, weight=4, color='red', opacity=0.6).add_to(m)

        # Draw selected route with congestion colors (if available), else green
        if isinstance(best_route['overview_polyline']['points'], list):
            best_coords = best_route['overview_polyline']['points']
        else:
            best_coords = polyline.decode(best_route['overview_polyline']['points'])
        best_cong = best_route.get('congestion')
        if best_cong and len(best_cong) == max(0, len(best_coords)-1):
            def cong_color(c):
                if c in ("low", "lowCongestion", "low-medium"):
                    return 'green'
                if c in ("moderate", "medium", "moderateCongestion"):
                    return 'orange'
                if c in ("heavy", "severe", "heavyCongestion"):
                    return 'red'
                return 'gray'
            seg_infos = best_route.get('segments', [])
            for i in range(len(best_coords)-1):
                seg = [best_coords[i], best_coords[i+1]]
                info = seg_infos[i] if i < len(seg_infos) else {}
                cong_val = info.get('congestion', best_cong[i] if i < len(best_cong) else None)
                dur_s = info.get('duration_s')
                dist_m = info.get('distance_m')
                tooltip_txt = f"{cong_val or 'unknown'}"
                if dist_m is not None:
                    tooltip_txt += f" • {dist_m:.0f} m"
                if dur_s is not None:
                    tooltip_txt += f" • {dur_s:.0f} s"
                folium.PolyLine(seg, weight=6, color=cong_color(best_cong[i]), opacity=0.95, tooltip=tooltip_txt).add_to(m)
        else:
            folium.PolyLine(best_coords, weight=6, color='green', opacity=0.95).add_to(m)

        # Legend
        legend_html = '''
        <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999; background: white; padding: 10px; border: 2px solid #444; border-radius: 6px;">
            <b>Routes</b><br>
            <span style="display:inline-block;width:18px;height:8px;background:green;margin-right:6px;"></span>Selected (low traffic)
            <br>
            <span style="display:inline-block;width:18px;height:8px;background:red;margin-right:6px;"></span>Other options (heavier traffic or lower beds)
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        # Status panel
        ti = best_route.get('traffic_info', {})
        bmin = int((ti.get('baseline_duration_seconds') or 0)/60) if ti else None
        tmin = int((ti.get('duration_seconds') or 0)/60) if ti else None
        delta = (tmin - bmin) if (tmin is not None and bmin is not None) else None
        beds_live = self.current_beds.get(best_hospital.name, {"general": best_hospital.available_beds, "icu": 0})
        meta = self.current_meta.get(best_hospital.name, {})
        hid = meta.get('id', 'n/a')
        lu = meta.get('last_updated', 'n/a')
        status_html = f'''
        <div style="position: fixed; top: 20px; right: 20px; z-index: 9999; background: white; padding: 12px 14px; border: 2px solid #444; border-radius: 6px; min-width: 260px;">
            <div style="font-weight: 700; margin-bottom: 6px;">Selected</div>
            <div><b>Hospital:</b> {best_hospital.name} (ID: {hid})</div>
            <div><b>Beds (Gen/ICU):</b> {beds_live.get('general', 0)} / {beds_live.get('icu', 0)}</div>
            <div><b>ETA (traffic):</b> {best_route['legs'][0]['duration']['text']}</div>
            <div><b>Baseline:</b> {bmin if bmin is not None else 'n/a'} mins</div>
            <div><b>Traffic Δ:</b> {('+' if (delta is not None and delta>=0) else '') + (str(delta)+' mins' if delta is not None else 'n/a')}</div>
            <div><b>Last updated:</b> {lu}</div>
            <div style="margin-top:6px; font-size: 12px; color: #555;">Weights — Time: {self.time_weight:.2f}, Beds: {self.beds_weight:.2f}</div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(status_html))
        return m

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emergency routing with Mapbox traffic and real-time beds")
    parser.add_argument("--watch", action="store_true", help="Continuously regenerate the route map")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between refresh cycles when --watch is enabled")
    parser.add_argument("--min-beds", type=int, default=5, help="Minimum beds required")
    parser.add_argument("--need-icu", action="store_true", help="Require ICU availability")
    parser.add_argument("--html-autorefresh", type=int, default=0, help="Auto-reload the generated HTML in browser every N seconds (0=disabled)")
    parser.add_argument("--time-weight", type=float, default=0.5, help="Weight for travel time in selection score")
    parser.add_argument("--beds-weight", type=float, default=0.5, help="Weight for bed availability in selection score")
    args = parser.parse_args()

    # Initialize system
    system = EmergencyRoutingSystem()
    
    # Load hospitals from CSV
    from utils.data_loader import load_hospitals
    hospitals = load_hospitals('bengaluru_hospitals.csv')
    
    # Add hospitals to the system and print count
    for hospital in hospitals:
        system.hospital_manager.add_hospital(hospital)
    
    print(f"Total hospitals loaded: {len(system.hospital_manager.hospitals)}")
    for h in system.hospital_manager.hospitals:
        print(f"Hospital: {h.name}, Beds: {h.available_beds}, Location: {h.location}")
    
    # Generate random ambulance location within Bangalore boundaries
    BANGALORE_BOUNDS = {
        'min_lat': 12.8,
        'max_lat': 13.05,
        'min_lng': 77.45,
        'max_lng': 77.75
    }
    ambulance_location = (
        random.uniform(BANGALORE_BOUNDS['min_lat'], BANGALORE_BOUNDS['max_lat']),
        random.uniform(BANGALORE_BOUNDS['min_lng'], BANGALORE_BOUNDS['max_lng'])
    )

    # Apply scoring weights
    system.set_weights(args.time_weight, args.beds_weight)

    # Ensure backend uses the same hospital list as our CSV (once)
    system.ensure_backend_seeded()

    def one_cycle():
        try:
            # Refresh beds via API before computing routes
            system.refresh_beds_from_api()

            # Compute routes for all candidate hospitals
            routes = system.get_routes_for_hospitals(
                ambulance_location,
                need_icu=args.need_icu,
                min_beds=args.min_beds
            )

            best_hospital, best_route, best_score = routes[0]

            # Visualize all routes
            map_view = system.visualize_all_routes(routes, ambulance_location)
            # Inject auto-reload script if requested
            if args.html_autorefresh and args.html_autorefresh > 0:
                refresh_ms = max(1, args.html_autorefresh) * 1000
                auto_reload = f"""
                <script>
                (function(){{ setTimeout(function(){{ location.reload(true); }}, {refresh_ms}); }})();
                </script>
                """
                map_view.get_root().html.add_child(folium.Element(auto_reload))
            map_view.save('emergency_route.html')
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Selected hospital: {best_hospital.name}")
            print(f"Available beds: {best_hospital.available_beds}")
            bl = self.current_beds.get(best_hospital.name)
            if bl:
                print(f"Live bed cache — General/ICU: {bl.get('general')}/{bl.get('icu')}")
            print(f"Estimated travel time (traffic): {best_route['legs'][0]['duration']['text']}")
            print(f"Distance: {best_route['legs'][0]['distance']['text']}")
            ti = best_route.get('traffic_info', {})
            if ti and ti.get('baseline_duration_seconds') is not None:
                t_min = int((ti['duration_seconds'] or 0) / 60)
                b_min = int((ti['baseline_duration_seconds'] or 0) / 60)
                delta = t_min - b_min
                print(f"Baseline (no-traffic) time: {b_min} mins")
                print(f"Traffic impact: {delta:+d} mins compared to baseline")
            else:
                print("Baseline duration unavailable; showing traffic-adjusted time only.")
            print("All route options saved to emergency_route.html")
        except Exception as e:
            print(f"Error: {e}")

    if args.watch:
        print(f"Starting watch mode (interval={args.interval}s). Press Ctrl+C to stop.")
        try:
            while True:
                one_cycle()
                time.sleep(max(1, args.interval))
        except KeyboardInterrupt:
            print("Stopped watch mode.")
    else:
        one_cycle()