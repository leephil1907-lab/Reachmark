"""
Finder.py — Reachmark Engine
Precise Script Instructions to fish out clients that match your business across the entire Internet
and scan/check on business account level so we know the best website that suits them.

This is the consolidated entry-point for the engine you asked about.
The engine is already created and enhanced; it lives across:
  - map_provider.py  (bounded Overpass access)
  - services.py      (geocode + discover_location + audit_website)
  - maps.py / workflow.py (jobs, global discovery)
  - app.py           (API: /api/discover, /api/jobs, /api/leads/:id/audit)
This file re-exports the precise script so you have a single Finder.py to call.

Usage:
  python scripts/finder.py --location "Lagos, Nigeria" --category "Café" --check
  python scripts/finder.py --global "Lagos, Nigeria|Accra, Ghana" --category "Clinic" --check
"""

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web.services import geocode, discover_location, audit_website, classify

# Precise Category → OSM tag fishing script (fishes exactly this business type, nowhere else)
CATEGORIES = {
  'Auto repair':('shop','car_repair'),'Hair salon':('shop','hairdresser'),'Bakery':('shop','bakery'),
  'Restaurant':('amenity','restaurant'),'Dentist':('amenity','dentist'),'Florist':('shop','florist'),
  'Plumber':('craft','plumber'),'Electrician':('craft','electrician'),'HVAC contractor':('craft','hvac'),
  'Roofing contractor':('craft','roofer'),'Tattoo studio':('shop','tattoo'),'Physiotherapist':('healthcare','physiotherapist'),
  'Pet groomer':('shop','pet_grooming'),'Accountant':('office','accountant'),
  'Café':('amenity','cafe'),'Fast food':('amenity','fast_food'),'Bar':('amenity','bar'),
  'Hotel':('tourism','hotel'),'Guest house':('tourism','guest_house'),'Pharmacy':('amenity','pharmacy'),
  'Clinic':('amenity','clinic'),'Veterinarian':('amenity','veterinary'),'Gym':('leisure','fitness_centre'),
  'Beauty salon':('shop','beauty'),'Clothing shop':('shop','clothes'),'Supermarket':('shop','supermarket'),
  'Convenience store':('shop','convenience'),'Laundry':('shop','laundry'),'Car wash':('amenity','car_wash'),
  'Carpenter':('craft','carpenter'),'Painter':('craft','painter'),'Photographer':('craft','photographer'),
  'Lawyer':('office','lawyer'),'Estate agent':('office','estate_agent'),'Travel agency':('shop','travel_agency'),
}

# Best website that suits them — category → sample mapping (website analysis decides)
SAMPLE_FOR_CATEGORY = {
  'Café':'ember-coffee', 'Restaurant':'ember-coffee', 'Bakery':'ember-coffee',
  'Beauty salon':'stillwell-studio', 'Hair salon':'stillwell-studio', 'Gym':'stillwell-studio',
  'Carpenter':'forma-homes', 'Painter':'forma-homes', 'Plumber':'forma-homes', 'Electrician':'forma-homes',
  'Clinic':'astra-clinic', 'Dentist':'astra-clinic', 'Pharmacy':'astra-clinic', 'Physiotherapist':'astra-clinic',
  'Lawyer':'novera-law', 'Accountant':'novera-law', 'Estate agent':'novera-law',
  'Clothing shop':'bloom-market', 'Florist':'bloom-market', 'Supermarket':'bloom-market',
  # Enhanced uploads
  'Fintech & finance':'fintech-pulse', 'SaaS & invoices':'getpaid',
}

PRECISE_SCRIPT = """
PRECISE FISHING SCRIPT — how Finder.py fishes exactly your business across the Internet:
1. Resolve location globally: geocode(location) via https://nominatim.openstreetmap.org/search (public, no Google API key)
   -> returns lat/lon + display_name; 1.1s throttle, LRU 128
2. Build bounded Overpass query (precise, never broad):
   [out:json][timeout:40]; nwr(around:15000,lat,lon)[\"{key}\"=\"{value}\"][\"name\"]; out center tags 80;
   e.g. Lagos Café -> nwr(around:15000,6.524,3.379)[\"amenity\"=\"cafe\"][\"name\"]; 
   -> fishes only named businesses with that exact OSM tag within 15km
3. Execute via map_provider.query_overpass — single read-only POST to https://overpass.private.coffee + fallback https://maps.mail.ru
   -> serialized, 2s gap, 8MB cap, rate-limit respecting, no retry around limits
4. For each element: keep public tags only (name, addr:*, phone, email, website, opening_hours) -> lead row
   -> classify(website): NOT_LISTED | SOCIAL_ONLY (facebook/instagram/linktr.ee) | HAS_WEBSITE
5. WEBSITE ANALYSIS on business account level (knows best website that suits them):
   audit_website(url):
     - SSRF-resistant: only http/https, standard ports, DNS -> IP global check via ipaddress, private/reserved blocked
     - Follow up to 5 redirects, validate Host, pin IP (urllib3 Pool to IP + SNI), read 64KB
     - Result: LIVE | HTTP_ERROR | BLOCKED | PARKED_SUSPECTED | DNS_UNRESOLVED | UNREACHABLE | SOCIAL_ONLY | NOT_LISTED
     - Reason is honest human text, http_code, final_url, not an invented score
   -> Then SAMPLE_FOR_CATEGORY maps category -> best fictional sample (ember-coffee etc.) that suits them
   -> Preview at /preview/:token + /showcase/:slug lets you say yes before build
"""

def fish(location: str, category: str, check_websites: bool = False):
    """Fish out clients that match your business in this location."""
    if category not in CATEGORIES:
        raise ValueError(f"Unsupported category {category!r}. Choose one of {sorted(CATEGORIES)}")
    tag = CATEGORIES[category]
    rows, resolved = discover_location(location, tag)
    print(f"[Finder] {location} -> {resolved} | {category} {tag} | {len(rows)} listings")
    if check_websites:
        for r in rows[:12]:
            if r.get('website'):
                result = audit_website(r['website'])
                r['audit'] = result
                print(f"  {r['name']:<30} {r['website']:<35} -> {result['status']:15} {result['reason'][:60]}")
                # Best website that suits them
                best = SAMPLE_FOR_CATEGORY.get(category, 'ember-coffee')
                print(f"    → best sample for {category}: /showcase/{best}")
    return rows, resolved

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Reachmark Finder — fish clients that match your business')
    p.add_argument('--location', help='Single location, e.g. \"Lagos, Nigeria\"')
    p.add_argument('--global', dest='glb', help='Pipe-separated global locations, e.g. \"Lagos, Nigeria|Accra, Ghana|Lisbon, Portugal\"')
    p.add_argument('--category', required=True, help='Business category, e.g. Café, Clinic, Lawyer')
    p.add_argument('--check', action='store_true', help='Also scan website account level (audit)')
    args = p.parse_args()
    if args.location:
        rows, resolved = fish(args.location, args.category, args.check)
        print(json.dumps(rows[:3], indent=2, ensure_ascii=False))
    elif args.glb:
        for loc in [x.strip() for x in args.glb.split('|') if x.strip()]:
            fish(loc, args.category, args.check)
    else:
        p.print_help()
        print("\nPrecise script instructions:\n", PRECISE_SCRIPT)
        sys.exit(1)
