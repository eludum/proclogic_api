from typing import List, Optional, Tuple, Dict

from app.models.company_models import Sector
from app.schemas.company_schemas import SectorSchema


en_sectors = {
    "03000000": "Agricultural, farming, fishing, forestry and related products",
    "09000000": "Petroleum products, fuel, electricity and other sources of energy",
    "14000000": "Mining, basic metals and related products",
    "15000000": "Food, beverages, tobacco and related products",
    "16000000": "Agricultural machinery",
    "18000000": "Clothing, footwear, luggage articles and accessories",
    "19000000": "Leather and textile fabrics, plastic and rubber materials",
    "22000000": "Printed matter and related products",
    "24000000": "Chemical products",
    "30000000": "Office and computing machinery, equipment and supplies except furniture and software packages",
    "31000000": "Electrical machinery, apparatus, equipment and consumables; lighting",
    "32000000": "Radio, television, communication, telecommunication and related equipment",
    "33000000": "Medical equipments, pharmaceuticals and personal care products",
    "34000000": "Transport equipment and auxiliary products to transportation",
    "35000000": "Security, fire-fighting, police and defence equipment",
    "37000000": "Musical instruments, sport goods, games, toys, handicraft, art materials and accessories",
    "38000000": "Laboratory, optical and precision equipments (excl. glasses)",
    "39000000": "Furniture (incl. office furniture), furnishings, domestic appliances (excl. lighting) and cleaning products",
    "41000000": "Collected and purified water",
    "42000000": "Industrial machinery",
    "43000000": "Machinery for mining, quarrying, construction equipment",
    "44000000": "Construction structures and materials; auxiliary products to construction (except electric apparatus)",
    "45000000": "Construction work",
    "48000000": "Software package and information systems",
    "50000000": "Repair and maintenance services",
    "51000000": "Installation services (except software)",
    "55000000": "Hotel, restaurant and retail trade services",
    "60000000": "Transport services (excl. Waste transport)",
    "63000000": "Supporting and auxiliary transport services; travel agencies services",
    "64000000": "Postal and telecommunications services",
    "65000000": "Public utilities",
    "66000000": "Financial and insurance services",
    "70000000": "Real estate services",
    "71000000": "Architectural, construction, engineering and inspection services",
    "72000000": "IT services: consulting, software development, Internet and support",
    "73000000": "Research and development services and related consultancy services",
    "75000000": "Administration, defence and social security services",
    "76000000": "Services related to the oil and gas industry",
    "77000000": "Agricultural, forestry, horticultural, aquacultural and apicultural services",
    "79000000": "Business services: law, marketing, consulting, recruitment, printing and security",
    "80000000": "Education and training services",
    "85000000": "Health and social work services",
    "90000000": "Sewage, refuse, cleaning and environmental services",
    "92000000": "Recreational, cultural and sporting services",
    "98000000": "Other community, social and personal services",
}

nl_sectors = {
    "03000000": "Landbouw-, veeteelt-, visserij-, bosbouw- en aanverwante producten",
    "09000000": "Aardolieproducten, brandstof, elektriciteit en andere energiebronnen",
    "14000000": "Mijnbouw, basismetalen en aanverwante producten",
    "15000000": "Voedingsmiddelen, dranken, tabak en aanverwante producten",
    "16000000": "Landbouwmachines",
    "18000000": "Kleding, schoeisel, bagageartikelen en accessoires",
    "19000000": "Leder- en textielstoffen, kunststof- en rubbermaterialen",
    "22000000": "Gedrukt materiaal en aanverwante producten",
    "24000000": "Chemische producten",
    "30000000": "Kantoor- en computerapparatuur, machines en benodigdheden, met uitzondering van meubels en softwarepakketten",
    "31000000": "Elektrische machines, apparaten, apparatuur en verbruiksartikelen; verlichting",
    "32000000": "Radio-, televisie-, communicatie-, telecommunicatie- en aanverwante apparatuur",
    "33000000": "Medische apparatuur, farmaceutische producten en persoonlijke verzorgingsproducten",
    "34000000": "Vervoersmaterieel en hulpstukken voor transport",
    "35000000": "Beveiligings-, brandbestrijdings-, politie- en defensieapparatuur",
    "37000000": "Muziekinstrumenten, sportartikelen, spellen, speelgoed, handwerk- en kunstbenodigdheden en accessoires",
    "38000000": "Laboratorium-, optische en precisieapparatuur (excl. brillen)",
    "39000000": "Meubelen (incl. kantoormeubelen), inrichting, huishoudelijke apparaten (excl. verlichting) en schoonmaakproducten",
    "41000000": "Opgevangen en gezuiverd water",
    "42000000": "Industriële machines",
    "43000000": "Machines voor mijnbouw, steengroeven en bouwmaterieel",
    "44000000": "Bouwconstructies en -materialen; hulpstukken voor de bouw (behalve elektrische apparaten)",
    "45000000": "Bouwwerkzaamheden",
    "48000000": "Softwarepakketten en informatiesystemen",
    "50000000": "Reparatie- en onderhoudsdiensten",
    "51000000": "Installatiediensten (excl. software)",
    "55000000": "Hotel-, restaurant- en detailhandeldiensten",
    "60000000": "Transportdiensten (excl. afvaltransport)",
    "63000000": "Ondersteunende en aanvullende transportdiensten; reisbureaudiensten",
    "64000000": "Post- en telecommunicatiediensten",
    "65000000": "Openbare nutsvoorzieningen",
    "66000000": "Financiële en verzekeringsdiensten",
    "70000000": "Vastgoeddiensten",
    "71000000": "Architectuur-, bouw-, engineering- en inspectiediensten",
    "72000000": "IT-diensten: consulting, softwareontwikkeling, internet en ondersteuning",
    "73000000": "Onderzoeks- en ontwikkelingsdiensten en aanverwante adviesdiensten",
    "75000000": "Overheids-, defensie- en sociale zekerheidsdiensten",
    "76000000": "Diensten gerelateerd aan de olie- en gasindustrie",
    "77000000": "Landbouw-, bosbouw-, tuinbouw-, aquacultuur- en bijenteeltdiensten",
    "79000000": "Zakelijke diensten: recht, marketing, consulting, werving, drukwerk en beveiliging",
    "80000000": "Onderwijs- en opleidingsdiensten",
    "85000000": "Gezondheidszorg- en maatschappelijke diensten",
    "90000000": "Riolering, afvalverwerking, schoonmaak- en milieudiensten",
    "92000000": "Recreatieve, culturele en sportdiensten",
    "98000000": "Overige gemeenschaps-, sociale en persoonlijke diensten",
}

fr_sectors = {
    "03000000": "Produits agricoles, d'élevage, de pêche, de foresterie et produits connexes",
    "09000000": "Produits pétroliers, carburants, électricité et autres sources d'énergie",
    "14000000": "Exploitation minière, métaux de base et produits connexes",
    "15000000": "Produits alimentaires, boissons, tabac et produits connexes",
    "16000000": "Machines agricoles",
    "18000000": "Vêtements, chaussures, articles de bagagerie et accessoires",
    "19000000": "Cuir et tissus textiles, matières plastiques et caoutchouc",
    "22000000": "Imprimés et produits connexes",
    "24000000": "Produits chimiques",
    "30000000": "Matériel, équipements et fournitures de bureau et d'informatique, à l'exception des meubles et des logiciels",
    "31000000": "Machines, appareils, équipements et consommables électriques; éclairage",
    "32000000": "Équipements de radio, télévision, communication, télécommunications et produits connexes",
    "33000000": "Équipements médicaux, produits pharmaceutiques et de soins personnels",
    "34000000": "Matériel de transport et produits auxiliaires pour le transport",
    "35000000": "Équipements de sécurité, de lutte contre l'incendie, de police et de défense",
    "37000000": "Instruments de musique, articles de sport, jeux, jouets, artisanat, matériel artistique et accessoires",
    "38000000": "Matériel de laboratoire, optique et de précision (hors lunettes)",
    "39000000": "Meubles (y compris meubles de bureau), ameublement, appareils domestiques (hors éclairage) et produits de nettoyage",
    "41000000": "Eau collectée et purifiée",
    "42000000": "Machines industrielles",
    "43000000": "Machines pour l'exploitation minière, les carrières et matériel de construction",
    "44000000": "Structures et matériaux de construction; produits auxiliaires pour la construction (sauf appareils électriques)",
    "45000000": "Travaux de construction",
    "48000000": "Logiciels et systèmes d'information",
    "50000000": "Services de réparation et d'entretien",
    "51000000": "Services d'installation (hors logiciels)",
    "55000000": "Services d'hôtellerie, de restauration et de commerce de détail",
    "60000000": "Services de transport (hors transport de déchets)",
    "63000000": "Services de soutien et auxiliaires au transport; services d'agences de voyage",
    "64000000": "Services postaux et de télécommunications",
    "65000000": "Services de services publics",
    "66000000": "Services financiers et d'assurance",
    "70000000": "Services immobiliers",
    "71000000": "Services d'architecture, de construction, d'ingénierie et d'inspection",
    "72000000": "Services informatiques : conseil, développement de logiciels, Internet et support",
    "73000000": "Services de recherche et de développement et services de conseil connexes",
    "75000000": "Services d'administration, de défense et de sécurité sociale",
    "76000000": "Services liés à l'industrie du pétrole et du gaz",
    "77000000": "Services agricoles, forestiers, horticoles, aquacoles et apicoles",
    "79000000": "Services aux entreprises : droit, marketing, conseil, recrutement, impression et sécurité",
    "80000000": "Services d'éducation et de formation",
    "85000000": "Services de santé et d'action sociale",
    "90000000": "Services d'assainissement, de gestion des déchets, de nettoyage et de protection de l'environnement",
    "92000000": "Services récréatifs, culturels et sportifs",
    "98000000": "Autres services communautaires, sociaux et personnels",
}


def get_cpv_sector_and_description(input_cpv: str, language: str) -> str:
    """Get sector description based on CPV code and language."""
    # Extract the main part of the CPV code before the hyphen
    sectors = {
        "en": en_sectors,
        "fr": fr_sectors,
        "nl": nl_sectors,
    }
    cpv_main = input_cpv.split("-")[0]  # e.g., "45232440-8" -> "45232440"

    # Extract first two digits and form the sector code
    first_two = cpv_main[:2] + "000000"

    if first_two in sectors[language].keys():
        return sectors[language][first_two]

    return "N/A"


def check_if_publication_is_in_your_sector(interested_sectors: List[Sector], cpv_main_code: str) -> bool:
    """Check if a publication's CPV code matches any of the company's interested sectors."""
    for sector in interested_sectors:
        if sector.sector == get_cpv_sector_and_description(cpv_main_code, "nl"):
            return True
    return False
