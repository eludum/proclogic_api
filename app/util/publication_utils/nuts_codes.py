from typing import List


nuts_codes = {
    "BE100": "Arr. de Bruxelles-Capitale/Arr. Brussel-Hoofdstad",
    "BE10": "Région de Bruxelles-Capitale/ Brussels Hoofdstedelijk Gewest",
    "BE1": "Région de Bruxelles-Capitale/Brussels Hoofdstedelijk Gewest",
    "BE211": "Arr. Antwerpen",
    "BE212": "Arr. Mechelen",
    "BE213": "Arr. Turnhout",
    "BE21": "Prov. Antwerpen",
    "BE223": "Arr. Tongeren",
    "BE224": "Arr. Hasselt",
    "BE225": "Arr. Maaseik",
    "BE22": "Prov. Limburg (BE)",
    "BE231": "Arr. Aalst",
    "BE232": "Arr. Dendermonde",
    "BE233": "Arr. Eeklo",
    "BE234": "Arr. Gent",
    "BE235": "Arr. Oudenaarde",
    "BE236": "Arr. Sint-Niklaas",
    "BE23": "Prov. Oost-Vlaanderen",
    "BE241": "Arr. Halle-Vilvoorde",
    "BE242": "Arr. Leuven",
    "BE24": "Prov. Vlaams-Brabant",
    "BE251": "Arr. Brugge",
    "BE252": "Arr. Diksmuide",
    "BE253": "Arr. Ieper",
    "BE254": "Arr. Kortrijk",
    "BE255": "Arr. Oostende",
    "BE256": "Arr. Roeselare",
    "BE257": "Arr. Tielt",
    "BE258": "Arr. Veurne",
    "BE25": "Prov. West-Vlaanderen",
    "BE2": "Vlaams Gewest",
    "BE310": "Arr. Nivelles",
    "BE31": "Prov. Brabant Wallon",
    "BE323": "Arr. Mons",
    "BE328": "Arr. Tournai-Mouscron",
    "BE329": "Arr. La Louvière",
    "BE32A": "Arr. Ath",
    "BE32B": "Arr. Charleroi",
    "BE32C": "Arr. Soignies",
    "BE32D": "Arr. Thuin",
    "BE32": "Prov. Hainaut",
    "BE331": "Arr. Huy",
    "BE332": "Arr. Liège",
    "BE336": "Bezirk Verviers — Deutschsprachige Gemeinschaft",
    "BE335": "Arr. Verviers — communes francophones",
    "BE334": "Arr. Waremme",
    "BE33": "Prov. Liège",
    "BE341": "Arr. Arlon",
    "BE342": "Arr. Bastogne",
    "BE343": "Arr. Marche-en-Famenne",
    "BE344": "Arr. Neufchâteau",
    "BE345": "Arr. Virton",
    "BE34": "Prov. Luxembourg (BE)",
    "BE351": "Arr. Dinant",
    "BE352": "Arr. Namur",
    "BE353": "Arr. Philippeville",
    "BE35": "Prov. Namur",
    "BE3": "Région wallonne",
    "BE": "België"
}

def get_nuts_code_as_str(code: str):
    return nuts_codes[code] if code in nuts_codes else None

def check_if_publication_is_in_your_region(company_regions: List[str], publication_regions: List[str]) -> bool:
    if not company_regions or not publication_regions:
        return False
        
    # Create sets for quick lookup
    company_region_set = set(company_regions)
    publication_region_set = set(publication_regions)
    
    # Direct match
    if company_region_set.intersection(publication_region_set):
        return True
    
    # Check parent-child relationships
    for pub_region in publication_regions:
        # Check if any company region is a parent of this publication region
        for company_region in company_regions:
            # A region is a parent if it's a prefix of the publication region
            # and the publication region is longer (more specific)
            if pub_region.startswith(company_region) and len(pub_region) > len(company_region):
                return True
            
            # Also check the reverse - if company has a specific region that belongs to a broader
            # publication region
            if company_region.startswith(pub_region) and len(company_region) > len(pub_region):
                return True
    
    return False
